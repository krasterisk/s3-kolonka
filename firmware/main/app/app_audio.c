#include "app_audio.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#include "driver/gpio.h"
#include "esp_audio_simple_player.h"
#include "esp_board_init.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "mww.h"

#define PA_GPIO GPIO_NUM_15
#define SAMPLE_RATE 16000
#define MIC_CHANNELS 4

static const char *TAG = "audio";
static int s_volume = 50;
static volatile bool s_listen;
static volatile bool s_standby = true;
static volatile bool s_playing;
static volatile int s_mic_level;
static volatile int s_listen_samples;
static volatile int s_silence_samples;
static volatile bool s_speech_seen;
static SemaphoreHandle_t s_i2s;
static app_audio_mic_sink_t s_mic_sink;
static app_audio_wake_cb_t s_wake_cb;
static bool s_mww;
static volatile bool s_radio;
static esp_asp_handle_t s_radio_player;

static void pa_on(void)
{
    gpio_set_level(PA_GPIO, 1);
}

static void pa_off(void)
{
    gpio_set_level(PA_GPIO, 0);
}

static int32_t *alloc_pcm(size_t bytes)
{
    int32_t *buf = heap_caps_malloc(bytes, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (!buf) {
        buf = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    }
    if (!buf) {
        buf = malloc(bytes);
    }
    return buf;
}

static void write_silence(int ms)
{
    const int frames = SAMPLE_RATE * ms / 1000;
    const size_t bytes = (size_t)frames * 2 * sizeof(int32_t);
    int32_t *z = alloc_pcm(bytes);
    if (!z) {
        return;
    }
    memset(z, 0, bytes);
    esp_audio_play((int16_t *)z, (int)bytes, portMAX_DELAY);
    free(z);
}

static void play_tone(int hz, int ms, float amp)
{
    const int fade = SAMPLE_RATE * 20 / 1000;
    const int frames = SAMPLE_RATE * ms / 1000;
    const size_t bytes = (size_t)frames * 2 * sizeof(int32_t);
    int32_t *buf = alloc_pcm(bytes);
    if (!buf) {
        return;
    }

    for (int i = 0; i < frames; i++) {
        float env = 1.0f;
        if (i < fade) {
            env = (float)i / (float)fade;
        } else if (i > frames - fade) {
            env = (float)(frames - i) / (float)fade;
        }
        float s = sinf(2.0f * (float)M_PI * (float)hz * (float)i / (float)SAMPLE_RATE);
        int32_t v = (int32_t)(s * env * amp * 1400000000.0f);
        buf[2 * i] = v;
        buf[2 * i + 1] = v;
    }

    if (s_i2s) {
        xSemaphoreTake(s_i2s, portMAX_DELAY);
    }
    s_playing = true;
    pa_on();
    vTaskDelay(pdMS_TO_TICKS(15));
    esp_audio_play((int16_t *)buf, (int)bytes, portMAX_DELAY);
    free(buf);
    write_silence(60);
    pa_off();
    s_playing = false;
    if (s_i2s) {
        xSemaphoreGive(s_i2s);
    }
}

void app_audio_beep(int hz, int ms)
{
    play_tone(hz, ms, 0.25f);
}

void app_audio_chime(void)
{
    play_tone(660, 90, 0.22f);
    play_tone(880, 140, 0.22f);
}

void app_audio_set_volume(int percent)
{
    if (percent < 0) {
        percent = 0;
    }
    if (percent > 100) {
        percent = 100;
    }
    s_volume = percent;
    esp_audio_set_play_vol(percent);
}

int app_audio_get_volume(void)
{
    return s_volume;
}

bool app_audio_is_listening(void)
{
    return s_listen;
}

int app_audio_mic_level(void)
{
    return s_mic_level;
}

void app_audio_set_listen(bool on)
{
    s_listen = on;
    s_listen_samples = 0;
    s_silence_samples = 0;
    s_speech_seen = false;
    if (!on) {
        s_mic_level = 0;
        if (s_mww) {
            mww_reset();
        }
    }
}

void app_audio_set_standby(bool on)
{
    s_standby = on;
}

void app_audio_set_wake_cb(app_audio_wake_cb_t cb)
{
    s_wake_cb = cb;
}

void app_audio_flush_preroll(void)
{
}

static void mic_task(void *arg)
{
    (void)arg;
    const int frames = 160;
    const int bytes = frames * MIC_CHANNELS * (int)sizeof(int16_t);
    int16_t *buf = heap_caps_malloc((size_t)bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!buf) {
        buf = malloc((size_t)bytes);
    }
    if (!buf) {
        ESP_LOGE(TAG, "mic buffer alloc failed");
        vTaskDelete(NULL);
        return;
    }

    while (1) {
        if (!s_listen && !s_standby) {
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }

        if (esp_get_feed_data(true, buf, bytes) != ESP_OK) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }

        int16_t mono[160];
        int64_t acc = 0;
        for (int i = 0; i < frames; i++) {
            int16_t a = buf[MIC_CHANNELS * i + 0];
            int16_t b = buf[MIC_CHANNELS * i + 1];
            acc += (int32_t)a * a + (int32_t)b * b;
            int32_t mix = (int32_t)a + (int32_t)b;
            mono[i] = (int16_t)(mix / 2);
        }
        int level = (int)(sqrtf((float)acc / (float)(frames * 2)) / 80.0f);
        if (level > 100) {
            level = 100;
        }
        s_mic_level = level;

        if (s_listen && !s_playing) {
            s_listen_samples += frames;
            if (s_listen_samples > SAMPLE_RATE * 4 / 10) {
                if (level >= 12) {
                    s_speech_seen = true;
                    s_silence_samples = 0;
                } else if (s_speech_seen) {
                    s_silence_samples += frames;
                    if (s_silence_samples >= SAMPLE_RATE * 12 / 10) {
                        s_listen = false;
                        s_mic_level = 0;
                    }
                }
            }
            if (s_listen_samples >= SAMPLE_RATE * 12) {
                s_listen = false;
                s_mic_level = 0;
            }
        }

        if (s_mic_sink && !s_playing && s_listen) {
            s_mic_sink(mono, frames);
        }

        if (s_mww && !s_listen && s_standby && !s_playing) {
            if (mww_feed(mono, frames)) {
                if (s_wake_cb) {
                    s_wake_cb();
                }
            }
        }
    }
}

void app_audio_set_mic_sink(app_audio_mic_sink_t sink)
{
    s_mic_sink = sink;
}

bool app_audio_is_playing(void)
{
    return s_playing;
}

void app_audio_play_pcm16(const int16_t *stereo, int samples)
{
    if (s_radio) {
        return;
    }
    if (!stereo || samples <= 0) {
        return;
    }
    if (s_i2s) {
        xSemaphoreTake(s_i2s, portMAX_DELAY);
    }
    if (!s_playing) {
        pa_on();
        vTaskDelay(pdMS_TO_TICKS(10));
        s_playing = true;
    }
    esp_audio_play(stereo, samples * (int)sizeof(int16_t), portMAX_DELAY);
    if (s_i2s) {
        xSemaphoreGive(s_i2s);
    }
}

void app_audio_play_end(void)
{
    if (s_i2s) {
        xSemaphoreTake(s_i2s, portMAX_DELAY);
    }
    if (s_playing) {
        write_silence(40);
        pa_off();
        s_playing = false;
        if (s_mww) {
            mww_reset();
        }
    }
    if (s_i2s) {
        xSemaphoreGive(s_i2s);
    }
}

void app_audio_play_abort(void)
{
    if (s_i2s) {
        xSemaphoreTake(s_i2s, portMAX_DELAY);
    }
    if (s_playing) {
        pa_off();
        s_playing = false;
        if (s_mww) {
            mww_reset();
        }
    }
    if (s_i2s) {
        xSemaphoreGive(s_i2s);
    }
}

static int radio_out_cb(uint8_t *data, int data_size, void *ctx)
{
    (void)ctx;
    if (!s_radio || !data || data_size <= 0) {
        return 0;
    }
    if (s_i2s) {
        xSemaphoreTake(s_i2s, portMAX_DELAY);
    }
    pa_on();
    esp_audio_play((int16_t *)data, data_size, portMAX_DELAY);
    if (s_i2s) {
        xSemaphoreGive(s_i2s);
    }
    return 0;
}

static bool radio_url_ok(const char *url)
{
    if (!url || !url[0]) {
        return false;
    }
    if (strncmp(url, "http://", 7) != 0 && strncmp(url, "https://", 8) != 0) {
        return false;
    }
    if (strstr(url, ".m3u8") || strstr(url, ".m3u")) {
        return false;
    }
    return true;
}

void app_audio_radio_stop(void)
{
    if (s_radio_player) {
        esp_asp_state_t st = ESP_ASP_STATE_NONE;
        if (esp_audio_simple_player_get_state(s_radio_player, &st) == ESP_OK &&
            st != ESP_ASP_STATE_NONE) {
            esp_audio_simple_player_stop(s_radio_player);
        }
    }
    s_radio = false;
    if (!s_playing) {
        pa_off();
    }
    if (s_mww) {
        mww_reset();
    }
}

bool app_audio_radio_start(const char *url)
{
    if (!radio_url_ok(url) || !s_radio_player) {
        ESP_LOGW(TAG, "radio reject url");
        return false;
    }
    app_audio_play_abort();
    app_audio_radio_stop();
    s_radio = true;
    pa_on();
    if (esp_audio_simple_player_run(s_radio_player, url, NULL) != ESP_OK) {
        ESP_LOGW(TAG, "radio run fail");
        s_radio = false;
        pa_off();
        return false;
    }
    ESP_LOGI(TAG, "radio start");
    return true;
}

bool app_audio_is_radio(void)
{
    return s_radio;
}

void app_audio_start(void)
{
    gpio_reset_pin(PA_GPIO);
    gpio_set_direction(PA_GPIO, GPIO_MODE_OUTPUT);
    pa_off();
    s_i2s = xSemaphoreCreateMutex();

    app_audio_set_volume(s_volume);
    app_audio_chime();
    esp_asp_cfg_t radio_cfg = {
        .in.cb = NULL,
        .in.user_ctx = NULL,
        .out.cb = radio_out_cb,
        .out.user_ctx = NULL,
    };
    if (esp_audio_simple_player_new(&radio_cfg, &s_radio_player) != ESP_OK) {
        s_radio_player = NULL;
        ESP_LOGW(TAG, "radio player init failed");
    }
    s_mww = mww_start();
    if (!s_mww) {
        ESP_LOGW(TAG, "mww off, tap listen only");
    }
    xTaskCreatePinnedToCore(mic_task, "mic", 8192, NULL, 4, NULL, 1);
    ESP_LOGI(TAG, "audio ready, volume=%d wake=%s", s_volume, s_mww ? "hey-jarvis" : "no");
}
