#include "afe_aec.h"

#include <string.h>

#include "esp_afe_sr_iface.h"
#include "esp_afe_sr_models.h"
#include "esp_board_init.h"
#include "esp_err.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"

static const char *TAG = "afe_aec";

static esp_afe_sr_iface_t *s_iface;
static esp_afe_sr_data_t *s_afe;
static int s_feed_samples;
static int s_feed_ch;
static int s_fetch_samples;

int afe_aec_feed_samples(void)
{
    return s_feed_samples;
}

int afe_aec_feed_ch(void)
{
    return s_feed_ch;
}

bool afe_aec_start(void)
{
    if (s_afe) {
        return true;
    }

    const char *fmt = esp_get_input_format();
    if (!fmt || !fmt[0]) {
        fmt = "RMNM";
    }

    /* models=NULL: AEC lives in the AFE library. Do not load WakeNet. */
    afe_config_t *cfg = afe_config_init(fmt, NULL, AFE_TYPE_SR, AFE_MODE_LOW_COST);
    if (!cfg) {
        ESP_LOGE(TAG, "afe_config_init failed fmt=%s", fmt);
        return false;
    }

    cfg->aec_init = true;
    cfg->wakenet_init = false;
    cfg->vad_init = false;
    cfg->se_init = false;
    cfg->memory_alloc_mode = AFE_MEMORY_ALLOC_MORE_PSRAM;
    cfg->afe_ringbuf_size = 16;
    /* Keep AFE work off core 0 so Wi-Fi / LWIP stay responsive. */
    cfg->afe_perferred_core = 1;
    cfg->afe_perferred_priority = 4;

    s_iface = esp_afe_handle_from_config(cfg);
    if (!s_iface) {
        ESP_LOGE(TAG, "esp_afe_handle_from_config failed");
        afe_config_free(cfg);
        return false;
    }

    s_afe = s_iface->create_from_config(cfg);
    afe_config_free(cfg);
    if (!s_afe) {
        ESP_LOGE(TAG, "AFE create failed");
        s_iface = NULL;
        return false;
    }

    s_feed_samples = s_iface->get_feed_chunksize(s_afe);
    s_feed_ch = s_iface->get_feed_channel_num(s_afe);
    s_fetch_samples = s_iface->get_fetch_chunksize(s_afe);
    if (s_feed_samples <= 0 || s_feed_ch <= 0) {
        ESP_LOGE(TAG, "AFE sizes bad feed=%d ch=%d", s_feed_samples, s_feed_ch);
        afe_aec_stop();
        return false;
    }

    ESP_LOGI(TAG, "AEC-only AFE fmt=%s feed=%d ch=%d fetch=%d (no WakeNet)",
             fmt, s_feed_samples, s_feed_ch, s_fetch_samples);
    return true;
}

void afe_aec_stop(void)
{
    if (s_iface && s_afe) {
        s_iface->destroy(s_afe);
    }
    s_afe = NULL;
    s_iface = NULL;
    s_feed_samples = 0;
    s_feed_ch = 0;
    s_fetch_samples = 0;
}

bool afe_aec_feed(const int16_t *interleaved)
{
    if (!s_iface || !s_afe || !interleaved) {
        return false;
    }
    return s_iface->feed(s_afe, interleaved) >= 0;
}

int afe_aec_fetch(int16_t *mono, int max_samples)
{
    if (!s_iface || !s_afe || !mono || max_samples <= 0) {
        return 0;
    }

    afe_fetch_result_t *res = s_iface->fetch_with_delay(s_afe, pdMS_TO_TICKS(80));
    if (!res || res->ret_value == ESP_FAIL || !res->data) {
        return 0;
    }

    int n = res->data_size / (int)sizeof(int16_t);
    if (n <= 0) {
        n = s_fetch_samples;
    }
    if (n > max_samples) {
        n = max_samples;
    }
    memcpy(mono, res->data, (size_t)n * sizeof(int16_t));
    return n;
}
