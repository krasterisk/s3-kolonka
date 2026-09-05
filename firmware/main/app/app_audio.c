#include "app_audio.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#include "driver/gpio.h"
#include "esp_audio_simple_player.h"
#include "esp_audio_simple_player_advance.h"
#include "esp_board_init.h"
#if __has_include("esp_gmf_rate_cvt.h")
#include "esp_gmf_bit_cvt.h"
#include "esp_gmf_ch_cvt.h"
#include "esp_gmf_pipeline.h"
#include "esp_gmf_rate_cvt.h"
#define RADIO_HAS_CVT 1
#endif
#include "aec.h"
#include "afe_aec.h"
#include "app_brain.h"
#include "app_wifi.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#ifdef CONFIG_FREERTOS_TASK_CREATE_ALLOW_EXT_MEM
#include "freertos/idf_additions.h"
#endif
#include "mww.h"

#define PA_GPIO GPIO_NUM_15
#define SAMPLE_RATE 16000
#define MIC_CHANNELS 4
#define MIC_REF_CH 0
#define MIC_L_CH 1
#define MIC_UI_DIV 80
#define MIC_UI_GATE 8

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
static volatile bool s_radio_http;
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
    if (on) {
        /* pcm:// radio_play leaves s_radio set; if the stream errors without
         * idle, mic uplink stays muted while the UI still shows «Слушаю». */
        if (s_radio) {
            app_audio_radio_stop();
        }
        if (s_playing) {
            app_audio_play_abort();
        }
    }
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

static void set_radio(bool on)
{
    s_radio = on;
    /* Radio leaks into the mics; a slightly lower bar still hears Hey Jarvis. */
    mww_set_cutoff(on ? 238 : 247);
}

static void maybe_wake(const int16_t *mono, int frames)
{
    if (!s_mww || s_listen || !s_standby || !mono || frames <= 0) {
        return;
    }
    if (mww_feed(mono, frames)) {
        ESP_LOGI(TAG, "wake hey-jarvis radio=%d play=%d", s_radio ? 1 : 0,
                 s_playing ? 1 : 0);
        if (s_wake_cb) {
            s_wake_cb();
        }
    }
}

static void handle_mono(const int16_t *mono, int frames, bool do_wake)
{
    if (!mono || frames <= 0) {
        return;
    }
    int64_t acc = 0;
    for (int i = 0; i < frames; i++) {
        acc += (int32_t)mono[i] * (int32_t)mono[i];
    }
    int level = (int)(sqrtf((float)acc / (float)frames) / (float)MIC_UI_DIV);
    if (level < MIC_UI_GATE) {
        level = 0;
    } else {
        level -= MIC_UI_GATE;
    }
    if (level > 100) {
        level = 100;
    }
    s_mic_level = (s_mic_level * 2 + level) / 3;

    if (s_listen) {
        /* Explicit listen wins over a sticky pcm:// radio flag so uplink is not
         * muted while the UI shows «Слушаю». */
        if (s_radio) {
            set_radio(false);
            s_radio_http = false;
        }
        s_listen_samples += frames;
        /* Do not cut on a short pause — the gateway VAD ends the turn. */
        if (s_listen_samples >= SAMPLE_RATE * 12) {
            s_listen = false;
            s_mic_level = 0;
        }
        if (s_mic_sink) {
            s_mic_sink(mono, frames);
        }
    }

    if (do_wake) {
        maybe_wake(mono, frames);
    }
}

static void raw_mic_task(void *arg)
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
        bool cancel = s_playing || s_radio;
        for (int i = 0; i < frames; i++) {
            const int16_t *slot = &buf[MIC_CHANNELS * i];
            mono[i] = cancel ? aec_cancel(slot[MIC_L_CH], slot[MIC_REF_CH]) : slot[MIC_L_CH];
        }
        handle_mono(mono, frames, true);
    }
}

static void afe_feed_task(void *arg)
{
    (void)arg;
    int samples = afe_aec_feed_samples();
    int ch = afe_aec_feed_ch();
    if (samples <= 0 || ch <= 0) {
        ESP_LOGE(TAG, "afe feed size bad");
        vTaskDelete(NULL);
        return;
    }
    int bytes = samples * ch * (int)sizeof(int16_t);
    int16_t *buf = heap_caps_malloc((size_t)bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!buf) {
        buf = malloc((size_t)bytes);
    }
    if (!buf) {
        ESP_LOGE(TAG, "afe feed alloc failed");
        vTaskDelete(NULL);
        return;
    }
    int16_t *wake_mono = heap_caps_malloc((size_t)samples * sizeof(int16_t),
                                          MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!wake_mono) {
        wake_mono = malloc((size_t)samples * sizeof(int16_t));
    }
    if (!wake_mono) {
        ESP_LOGW(TAG, "wake raw buffer missing, silence wake uses AFE");
    }

    while (1) {
        if (esp_get_feed_data(true, buf, bytes) != ESP_OK) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }
        afe_aec_feed(buf);
        /* Hey Jarvis was trained on raw mic. AFE output in silence misses.
         * Listen must still run if pcm:// left s_radio stuck without idle. */
        if (wake_mono && !s_playing && (!s_radio || s_listen)) {
            for (int i = 0; i < samples; i++) {
                wake_mono[i] = buf[ch * i + MIC_L_CH];
            }
            if (!s_listen) {
                maybe_wake(wake_mono, samples);
            }
            if (s_listen) {
                /* STT uses raw mic; AFE after radio/TTS gates the voice as echo. */
                handle_mono(wake_mono, samples, false);
            }
        }
    }
}

static void afe_fetch_task(void *arg)
{
    (void)arg;
    int16_t *mono = heap_caps_malloc(1024 * sizeof(int16_t), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!mono) {
        mono = malloc(1024 * sizeof(int16_t));
    }
    if (!mono) {
        ESP_LOGE(TAG, "afe fetch alloc failed");
        vTaskDelete(NULL);
        return;
    }

    while (1) {
        int n = afe_aec_fetch(mono, 1024);
        if (n <= 0) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }
        if (!(s_listen && !s_radio)) {
            handle_mono(mono, n, false);
        }
        if (s_playing || s_radio) {
            maybe_wake(mono, n);
        }
    }
}

static void start_mic_task(TaskFunction_t fn, const char *name, uint32_t stack, int prio,
                           int core)
{
#ifdef CONFIG_FREERTOS_TASK_CREATE_ALLOW_EXT_MEM
    if (xTaskCreatePinnedToCoreWithCaps(fn, name, stack, NULL, prio, NULL, core,
                                        MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT) == pdPASS) {
        return;
    }
    ESP_LOGW(TAG, "%s PSRAM stack failed, using internal", name);
#endif
    xTaskCreatePinnedToCore(fn, name, stack, NULL, prio, NULL, core);
}

static void mic_boot_task(void *arg)
{
    (void)arg;
    for (int i = 0; i < 150; i++) {
        if (app_brain_ready()) {
            break;
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }

    size_t intern = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    ESP_LOGI(TAG, "mic boot heap=%u internal=%u brain=%d",
             (unsigned)esp_get_free_heap_size(), (unsigned)intern,
             app_brain_ready() ? 1 : 0);

    if (intern > 40000 && afe_aec_start()) {
        start_mic_task(afe_feed_task, "afe_feed", 8192, 4, 0);
        start_mic_task(afe_fetch_task, "afe_fetch", 8192, 5, 1);
        ESP_LOGI(TAG, "audio ready afe-aec volume=%d wake=%s", s_volume,
                 s_mww ? "hey-jarvis" : "no");
    } else {
        start_mic_task(raw_mic_task, "mic", 8192, 4, 0);
        ESP_LOGW(TAG, "audio ready raw-mic volume=%d wake=%s internal=%u", s_volume,
                 s_mww ? "hey-jarvis" : "no", (unsigned)intern);
    }
    vTaskDelete(NULL);
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
    if (s_radio_http) {
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
        aec_reset();
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
        aec_reset();
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
    pa_on();
    /* Match the Waveshare demo: short timeout, no I2S mutex. A long block
     * starves the mic/wake task on the same core. */
    if (esp_audio_play((int16_t *)data, data_size, pdMS_TO_TICKS(80)) != ESP_OK) {
        ESP_LOGW(TAG, "radio out drop %d", data_size);
    }
    return 0;
}

static int radio_event_cb(esp_asp_event_pkt_t *event, void *ctx)
{
    (void)ctx;
    if (!event) {
        return 0;
    }
    if (event->type == ESP_ASP_EVENT_TYPE_MUSIC_INFO && event->payload) {
        esp_asp_music_info_t info = {0};
        memcpy(&info, event->payload, event->payload_size);
        ESP_LOGI(TAG, "radio info rate=%d ch=%u bits=%u", info.sample_rate,
                 (unsigned)info.channels, (unsigned)info.bits);
    } else if (event->type == ESP_ASP_EVENT_TYPE_STATE && event->payload) {
        esp_asp_state_t st = ESP_ASP_STATE_NONE;
        memcpy(&st, event->payload, event->payload_size);
        ESP_LOGI(TAG, "radio state %s", esp_audio_simple_player_state_to_str(st));
        if (st == ESP_ASP_STATE_ERROR || st == ESP_ASP_STATE_FINISHED) {
            s_radio_http = false;
            set_radio(false);
            if (!s_playing) {
                pa_off();
            }
        }
    }
    return 0;
}

#if RADIO_HAS_CVT
/* 0.9.x prev hook is (esp_asp_handle_t *, void *); 1.0 changed it to a handle. */
static int radio_prev(esp_asp_handle_t *handle, void *ctx)
{
    (void)ctx;
    if (!handle || !*handle) {
        return 0;
    }
    esp_gmf_pipeline_handle_t pipe = NULL;
    if (esp_audio_simple_player_get_pipeline(*handle, &pipe) != ESP_OK || !pipe) {
        return 0;
    }
    esp_gmf_element_handle_t el = NULL;
    if (esp_gmf_pipeline_get_el_by_name(pipe, "aud_rate_cvt", &el) == ESP_OK && el) {
        esp_gmf_rate_cvt_set_dest_rate(el, SAMPLE_RATE);
    }
    if (esp_gmf_pipeline_get_el_by_name(pipe, "aud_ch_cvt", &el) == ESP_OK && el) {
        esp_gmf_ch_cvt_set_dest_channel(el, 2);
    }
    if (esp_gmf_pipeline_get_el_by_name(pipe, "aud_bit_cvt", &el) == ESP_OK && el) {
        esp_gmf_bit_cvt_set_dest_bits(el, 16);
    }
    return 0;
}
#endif

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

static void radio_uri_for_player(const char *url, char *out, size_t out_sz)
{
    if (!out || out_sz < 16) {
        return;
    }
    strncpy(out, url ? url : "", out_sz - 1);
    out[out_sz - 1] = 0;
    char *hash = strchr(out, '#');
    if (hash) {
        *hash = 0;
    }
    char *query = strchr(out, '?');
    const char *path_end = query ? query : out + strlen(out);
    const char *dot = NULL;
    for (const char *p = out; p < path_end; p++) {
        if (*p == '.') {
            dot = p;
        }
        if (*p == '/') {
            dot = NULL;
        }
    }
    bool has_ext = false;
    if (dot && path_end - dot <= 5) {
        has_ext = true;
    }
    if (!has_ext && strlen(out) + 11 < out_sz) {
        strcat(out, "#stream.mp3");
    }
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
    set_radio(false);
    s_radio_http = false;
    /* pcm:// YouTube leaves s_playing true via play_pcm16; clearing only
     * s_radio left the mic uplink muted forever (is_playing gate). */
    app_audio_play_abort();
    aec_reset();
}

bool app_audio_radio_start(const char *url)
{
    char uri[288];
    if (url && strncmp(url, "pcm://", 6) == 0) {
        app_audio_play_abort();
        app_audio_radio_stop();
        s_radio_http = false;
        set_radio(true);
        pa_on();
        ESP_LOGI(TAG, "radio pcm");
        return true;
    }
    if (!radio_url_ok(url) || !s_radio_player) {
        ESP_LOGW(TAG, "radio reject url");
        return false;
    }
    radio_uri_for_player(url, uri, sizeof(uri));
    app_audio_play_abort();
    app_audio_radio_stop();
    s_radio_http = true;
    set_radio(true);
    pa_on();
    if (esp_audio_simple_player_run(s_radio_player, uri, NULL) != ESP_OK) {
        ESP_LOGW(TAG, "radio run fail %s", uri);
        set_radio(false);
        pa_off();
        return false;
    }
    ESP_LOGI(TAG, "radio start %s", uri);
    return true;
}

bool app_audio_is_radio(void)
{
    return s_radio;
}

void app_audio_start(void)
{
    aec_reset();
    gpio_reset_pin(PA_GPIO);
    gpio_set_direction(PA_GPIO, GPIO_MODE_OUTPUT);
    pa_off();
    s_i2s = xSemaphoreCreateMutex();

    app_audio_set_volume(s_volume);
    app_audio_chime();
    if (app_wifi_is_setup_ap()) {
        ESP_LOGI(TAG, "setup AP: skip mww/afe so the portal has RAM");
        return;
    }
    esp_asp_cfg_t radio_cfg = {
        .in.cb = NULL,
        .in.user_ctx = NULL,
        .out.cb = radio_out_cb,
        .out.user_ctx = NULL,
        .task_prio = 3,
        .task_stack = 8192,
        .task_core = 1,
        .task_stack_in_ext = true,
#if RADIO_HAS_CVT
        .prev = radio_prev,
#endif
    };
    if (esp_audio_simple_player_new(&radio_cfg, &s_radio_player) != ESP_OK) {
        s_radio_player = NULL;
        ESP_LOGW(TAG, "radio player init failed");
    } else {
        esp_audio_simple_player_set_event(s_radio_player, radio_event_cb, NULL);
    }
    s_mww = mww_start();
    if (!s_mww) {
        ESP_LOGW(TAG, "mww off, tap listen only");
    }
    /* AFE after the brain socket: AEC used to starve internal RAM so
     * esp_websocket_client_start() returned ESP_FAIL. */
    xTaskCreatePinnedToCore(mic_boot_task, "mic_boot", 4096, NULL, 3, NULL, 0);
}
