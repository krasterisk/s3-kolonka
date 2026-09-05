#include "ST77916.h"
#include "TCA9554PWR.h"
#include "LVGL_Driver.h"
#include "BAT_Driver.h"
#include "app_audio.h"
#include "app_brain.h"
#include "app_version.h"
#include "app_wifi.h"
#include "esp_board_init.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "ui.h"

static const char *TAG = "app";

void app_main(void)
{
    esp_err_t nvs = nvs_flash_init();
    if (nvs == ESP_ERR_NVS_NO_FREE_PAGES || nvs == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        nvs = nvs_flash_init();
    }
    ESP_ERROR_CHECK(nvs);

    ESP_ERROR_CHECK(esp_board_init(16000, 2, 16));
    EXIO_Init();
    BAT_Init();
    LCD_Init();
    LVGL_Init();
    ui_show_home();

    app_wifi_start();
    if (!app_wifi_is_setup_ap()) {
        app_brain_start();
    } else {
        ESP_LOGI(TAG, "setup AP: skip brain until Wi-Fi is saved");
    }
    app_audio_start();
    ESP_LOGI(TAG, "s3-kolonka ready firmware=%s", KOLONKA_VERSION_FULL);

    uint32_t tick = 0;
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(10));
        lv_timer_handler();
        if ((++tick % 10) == 0) {
            ui_tick();
        }
    }
}
