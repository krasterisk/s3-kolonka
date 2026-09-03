#include "app_brain.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "app_audio.h"
#include "app_wifi.h"
#include "cJSON.h"
#include "esp_err.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_websocket_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/ringbuf.h"
#include "freertos/task.h"
#include "sdkconfig.h"

#define BRAIN_HOST CONFIG_KOLONKA_BRAIN_HOST
#define BRAIN_PORT CONFIG_KOLONKA_BRAIN_PORT

static const char *TAG = "brain";
static esp_websocket_client_handle_t s_ws;
static volatile bool s_listen;
static volatile bool s_need_hello;
static volatile bool s_end_listen;
static bool s_listen_sent;
static char s_status[48] = "Brain: wait";
static char s_backend[16] = "gw";
static char s_brain_uri[96];
static RingbufHandle_t s_play_rb;
static RingbufHandle_t s_up_rb;

static const char *brain_uri(void)
{
    snprintf(s_brain_uri, sizeof(s_brain_uri), "ws://%s:%d/", BRAIN_HOST, BRAIN_PORT);
    return s_brain_uri;
}

static void set_status(const char *text)
{
    strncpy(s_status, text, sizeof(s_status) - 1);
    s_status[sizeof(s_status) - 1] = 0;
}

static void send_json(const char *json)
{
    if (!s_ws || !esp_websocket_client_is_connected(s_ws)) {
        return;
    }
    int n = esp_websocket_client_send_text(s_ws, json, (int)strlen(json), pdMS_TO_TICKS(1500));
    if (n < 0) {
        ESP_LOGW(TAG, "send_text fail %d", n);
    }
}

static void flush_uplink(void)
{
    if (!s_up_rb) {
        return;
    }
    while (1) {
        size_t n = 0;
        uint8_t *item = xRingbufferReceive(s_up_rb, &n, 0);
        if (!item) {
            break;
        }
        vRingbufferReturnItem(s_up_rb, item);
    }
}

static void handle_text(const char *data, int len)
{
    cJSON *root = cJSON_ParseWithLength(data, len);
    if (!root) {
        return;
    }
    const cJSON *type = cJSON_GetObjectItem(root, "type");
    const cJSON *state = cJSON_GetObjectItem(root, "state");
    const cJSON *backend = cJSON_GetObjectItem(root, "backend");
    if (cJSON_IsString(backend) && backend->valuestring) {
        strncpy(s_backend, backend->valuestring, sizeof(s_backend) - 1);
    }
    if (cJSON_IsString(type) && type->valuestring) {
        if (strcmp(type->valuestring, "hello") == 0) {
            snprintf(s_status, sizeof(s_status), "Brain: %s", s_backend);
        } else if (strcmp(type->valuestring, "status") == 0 && cJSON_IsString(state) && state->valuestring) {
            const char *st = state->valuestring;
            if (strcmp(st, "idle") == 0) {
                snprintf(s_status, sizeof(s_status), "Brain: %s", s_backend);
            } else {
                snprintf(s_status, sizeof(s_status), "Brain: %s", st);
            }
            if (strcmp(st, "thinking") == 0 || strcmp(st, "speaking") == 0 ||
                strcmp(st, "idle") == 0 || strcmp(st, "error") == 0) {
                s_end_listen = true;
            }
        }
    }
    cJSON_Delete(root);
}

static void on_ws(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    (void)base;
    esp_websocket_event_data_t *ev = data;
    switch (id) {
    case WEBSOCKET_EVENT_CONNECTED:
        ESP_LOGI(TAG, "connected");
        set_status("Brain: online");
        s_need_hello = true;
        s_listen_sent = false;
        break;
    case WEBSOCKET_EVENT_DISCONNECTED:
        set_status("Brain: down");
        break;
    case WEBSOCKET_EVENT_DATA:
        if (!ev || ev->data_len <= 0 || !ev->data_ptr) {
            break;
        }
        if (ev->op_code == 1) {
            handle_text(ev->data_ptr, ev->data_len);
        } else if (ev->op_code == 2 && s_play_rb) {
            xRingbufferSend(s_play_rb, ev->data_ptr, (size_t)ev->data_len, 0);
        }
        break;
    case WEBSOCKET_EVENT_ERROR:
        if (ev) {
            snprintf(s_status, sizeof(s_status), "Brain: err %d",
                     ev->error_handle.esp_transport_sock_errno);
        } else {
            set_status("Brain: error");
        }
        break;
    default:
        break;
    }
}

static void play_task(void *arg)
{
    (void)arg;
    const int chunk = 320;
    int16_t *stereo = heap_caps_malloc((size_t)chunk * 2 * sizeof(int16_t),
                                       MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!stereo) {
        stereo = malloc((size_t)chunk * 2 * sizeof(int16_t));
    }
    if (!stereo) {
        vTaskDelete(NULL);
        return;
    }

    while (1) {
        size_t n = 0;
        uint8_t *item = xRingbufferReceive(s_play_rb, &n, pdMS_TO_TICKS(80));
        if (!item) {
            if (app_audio_is_playing()) {
                app_audio_play_end();
            }
            continue;
        }
        const int16_t *mono = (const int16_t *)item;
        int samples = (int)n / (int)sizeof(int16_t);
        int off = 0;
        while (off < samples) {
            int take = samples - off;
            if (take > chunk) {
                take = chunk;
            }
            for (int i = 0; i < take; i++) {
                stereo[2 * i] = mono[off + i];
                stereo[2 * i + 1] = mono[off + i];
            }
            app_audio_play_pcm16(stereo, take * 2);
            off += take;
        }
        vRingbufferReturnItem(s_play_rb, item);
    }
}

static void mic_sink(const int16_t *mono, int samples)
{
    if (!s_listen || !s_up_rb || samples <= 0) {
        return;
    }
    if (app_audio_is_playing()) {
        return;
    }
    if (xRingbufferSend(s_up_rb, mono, (size_t)samples * sizeof(int16_t), 0) != pdTRUE) {
        ESP_LOGW(TAG, "uplink drop");
    }
}

static void brain_destroy(void)
{
    if (!s_ws) {
        return;
    }
    /* destroy() stops a running client; stop() on a never-started one is ESP_FAIL */
    esp_websocket_client_destroy(s_ws);
    s_ws = NULL;
}

static void brain_task(void *arg)
{
    (void)arg;
    int wait_ticks = 0;
    while (1) {
        if (!app_wifi_connected() || app_wifi_is_setup_ap()) {
            set_status("Brain: wait wifi");
            brain_destroy();
            wait_ticks = 0;
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }

        if (!s_ws) {
            set_status("Brain: connecting");
            wait_ticks = 0;
            ESP_LOGI(TAG, "ws start heap=%u uri=%s", (unsigned)esp_get_free_heap_size(), brain_uri());
            esp_websocket_client_config_t cfg = {
                .uri = s_brain_uri,
                .host = BRAIN_HOST,
                .port = BRAIN_PORT,
                .path = "/",
                .transport = WEBSOCKET_TRANSPORT_OVER_TCP,
                .buffer_size = 4096,
                .network_timeout_ms = 10000,
                .reconnect_timeout_ms = 3000,
                .disable_auto_reconnect = false,
            };
            s_ws = esp_websocket_client_init(&cfg);
            if (!s_ws) {
                set_status("Brain: init fail");
                ESP_LOGE(TAG, "init fail heap=%u", (unsigned)esp_get_free_heap_size());
                vTaskDelay(pdMS_TO_TICKS(2000));
                continue;
            }
            esp_websocket_register_events(s_ws, WEBSOCKET_EVENT_ANY, on_ws, NULL);
            esp_err_t err = esp_websocket_client_start(s_ws);
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "start fail %s heap=%u", esp_err_to_name(err),
                         (unsigned)esp_get_free_heap_size());
                brain_destroy();
                snprintf(s_status, sizeof(s_status), "Brain: st %s", esp_err_to_name(err));
                vTaskDelay(pdMS_TO_TICKS(2000));
            }
            continue;
        }

        if (!esp_websocket_client_is_connected(s_ws)) {
            flush_uplink();
            if (++wait_ticks >= 24) {
                set_status("Brain: retry");
                brain_destroy();
                wait_ticks = 0;
            }
            vTaskDelay(pdMS_TO_TICKS(500));
            continue;
        }

        wait_ticks = 0;
        if (s_need_hello) {
            s_need_hello = false;
            send_json("{\"type\":\"hello\",\"device\":\"s3-kolonka\"}");
        }
        if (s_end_listen) {
            s_end_listen = false;
            s_listen = false;
            app_audio_set_listen(false);
        }
        if (s_listen != s_listen_sent) {
            s_listen_sent = s_listen;
            if (!s_listen) {
                flush_uplink();
            }
            send_json(s_listen ? "{\"type\":\"listen\"}" : "{\"type\":\"stop\"}");
        }

        size_t n = 0;
        uint8_t *item = xRingbufferReceive(s_up_rb, &n, pdMS_TO_TICKS(s_listen ? 20 : 200));
        if (!item) {
            continue;
        }
        int sent = esp_websocket_client_send_bin(s_ws, (const char *)item, (int)n, pdMS_TO_TICKS(1500));
        if (sent < 0) {
            ESP_LOGW(TAG, "uplink send %d", sent);
        }
        vRingbufferReturnItem(s_up_rb, item);
    }
}

void app_brain_start(void)
{
    s_play_rb = xRingbufferCreateWithCaps(64 * 1024, RINGBUF_TYPE_NOSPLIT, MALLOC_CAP_SPIRAM);
    if (!s_play_rb) {
        s_play_rb = xRingbufferCreate(32 * 1024, RINGBUF_TYPE_NOSPLIT);
    }
    s_up_rb = xRingbufferCreateWithCaps(16 * 1024, RINGBUF_TYPE_NOSPLIT, MALLOC_CAP_SPIRAM);
    if (!s_up_rb) {
        s_up_rb = xRingbufferCreate(8 * 1024, RINGBUF_TYPE_NOSPLIT);
    }
    app_audio_set_mic_sink(mic_sink);
    xTaskCreatePinnedToCore(play_task, "brain_play", 4096, NULL, 5, NULL, 1);
    xTaskCreatePinnedToCore(brain_task, "brain", 4096, NULL, 4, NULL, 0);
    ESP_LOGI(TAG, "brain ws://%s:%d", BRAIN_HOST, BRAIN_PORT);
}

void app_brain_set_listen(bool on)
{
    s_listen = on;
}

const char *app_brain_status(void)
{
    return s_status;
}
