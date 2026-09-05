#include "ui.h"

#include <stdint.h>
#include <string.h>

#include "ST77916.h"
#include "app_audio.h"
#include "app_brain.h"
#include "app_wifi.h"
#include "ui_pages.h"
#include "ui_theme.h"

static lv_obj_t *s_tv;
static lv_obj_t *s_tiles[3];
static lv_obj_t *s_nav_icon[3];
static lv_obj_t *s_dots[3];
static ui_page_t s_page = UI_PAGE_HOME;
static bool s_shown_listen;
static bool s_asleep;
static int s_saved_bl = 70;
static char s_radio_title[96];

static const char *s_nav_icons[] = {
    LV_SYMBOL_HOME,
    LV_SYMBOL_AUDIO,
    LV_SYMBOL_SETTINGS,
};

static void style_tile(lv_obj_t *tile)
{
    lv_obj_set_style_bg_opa(tile, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(tile, 0, 0);
    lv_obj_set_style_pad_all(tile, 0, 0);
    lv_obj_set_style_radius(tile, 0, 0);
    lv_obj_clear_flag(tile, LV_OBJ_FLAG_SCROLLABLE);
}

static void nav_set_active(ui_page_t page)
{
    s_page = page;
    for (int i = 0; i < 3; i++) {
        lv_color_t c = lv_color_hex(i == (int)page ? UI_COLOR_ACCENT : UI_COLOR_MUTED);
        if (s_nav_icon[i]) {
            lv_obj_set_style_text_color(s_nav_icon[i], c, 0);
        }
        if (s_dots[i]) {
            lv_obj_set_style_bg_color(s_dots[i], c, 0);
            lv_obj_set_style_bg_opa(s_dots[i], i == (int)page ? LV_OPA_COVER : LV_OPA_40, 0);
        }
    }
}

void ui_go_page(ui_page_t page)
{
    if (!s_tv) {
        return;
    }
    lv_obj_set_tile_id(s_tv, (uint32_t)page, 0, LV_ANIM_OFF);
    nav_set_active(page);
}

void ui_swipe_lock(bool lock)
{
    if (!s_tv) {
        return;
    }
    if (lock) {
        lv_obj_clear_flag(s_tv, LV_OBJ_FLAG_SCROLLABLE);
    } else {
        lv_obj_add_flag(s_tv, LV_OBJ_FLAG_SCROLLABLE);
    }
}

static void on_nav(lv_event_t *e)
{
    ui_page_t page = (ui_page_t)(intptr_t)lv_event_get_user_data(e);
    ui_go_page(page);
}

static void on_tile_changed(lv_event_t *e)
{
    lv_obj_t *tile = lv_tileview_get_tile_act(lv_event_get_target(e));
    for (int i = 0; i < 3; i++) {
        if (tile == s_tiles[i]) {
            nav_set_active((ui_page_t)i);
            return;
        }
    }
}

static void set_listen_visual(bool on)
{
    s_shown_listen = on;
    lv_obj_t *scr = lv_scr_act();
    lv_obj_set_style_bg_color(scr, lv_color_hex(on ? UI_COLOR_BG_LISTEN : UI_COLOR_BG), 0);
    ui_home_set_listen(on, s_asleep);
}

static const char *friendly_status(void)
{
    if (s_asleep && !app_audio_is_listening()) {
        return "Сон";
    }
    if (app_audio_is_listening()) {
        return "Слушаю";
    }
    if (app_wifi_is_setup_ap()) {
        return "Настрой Wi-Fi";
    }
    if (!app_wifi_connected()) {
        return "Нет связи";
    }
    const char *b = app_brain_status();
    if (strstr(b, "thinking") || strstr(b, "stt") || strstr(b, "live")) {
        return "Думаю";
    }
    if (strstr(b, "speaking") || strstr(b, "tts")) {
        return "Говорю";
    }
    if (strstr(b, "radio")) {
        return "Радио";
    }
    if (strstr(b, "connecting")) {
        return "Связь";
    }
    if (strstr(b, "down") || strstr(b, "error") || strstr(b, "err ") ||
        strstr(b, "fail") || strstr(b, "retry") || strstr(b, "wait wifi")) {
        return "Нет связи";
    }
    if (!app_brain_ready()) {
        return "Нет связи";
    }
    return "Готов";
}

void ui_handle_wake(void)
{
    if (app_audio_is_listening() || !app_brain_ready()) {
        return;
    }
    if (app_audio_is_radio() || app_audio_is_playing()) {
        app_brain_radio_stop();
    }
    if (s_asleep) {
        ui_set_asleep(false);
    }
    /* On-device wake already accepted the word; gateway must not filter again. */
    app_brain_set_wake_mode(false);
    app_audio_set_listen(true);
    app_brain_set_listen(true);
    ui_go_page(UI_PAGE_HOME);
}

void ui_handle_listen_click(void)
{
    bool next = !app_audio_is_listening();
    if (s_asleep) {
        ui_set_asleep(false);
    }
    app_brain_set_wake_mode(false);
    if (next && app_audio_is_radio()) {
        app_audio_radio_stop();
    }
    app_audio_set_listen(next);
    app_brain_set_listen(next);
    set_listen_visual(next);
    app_audio_beep(next ? 880 : 440, 80);
    if (next) {
        ui_go_page(UI_PAGE_HOME);
    }
}

void ui_handle_radio_stop(void)
{
    app_brain_radio_stop();
    s_radio_title[0] = 0;
    ui_media_set_playing(false, NULL);
}

void ui_handle_brightness(int percent)
{
    if (percent < 5) {
        percent = 5;
    }
    s_saved_bl = percent;
    if (!s_asleep) {
        Set_Backlight((uint8_t)percent);
    }
}

static void create_nav(lv_obj_t *scr)
{
    lv_obj_t *bar = lv_obj_create(scr);
    lv_obj_set_size(bar, 240, 44);
    lv_obj_align(bar, LV_ALIGN_TOP_MID, 0, UI_NAV_TOP);
    lv_obj_set_style_bg_opa(bar, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(bar, 0, 0);
    lv_obj_set_style_pad_all(bar, 0, 0);
    lv_obj_clear_flag(bar, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_clear_flag(bar, LV_OBJ_FLAG_SCROLL_CHAIN);
    lv_obj_move_foreground(bar);

    static const int xoff[] = {-78, 0, 78};
    for (int i = 0; i < 3; i++) {
        lv_obj_t *btn = lv_obj_create(bar);
        lv_obj_set_size(btn, 56, 44);
        lv_obj_align(btn, LV_ALIGN_CENTER, xoff[i], 0);
        lv_obj_set_style_bg_opa(btn, LV_OPA_TRANSP, 0);
        lv_obj_set_style_border_width(btn, 0, 0);
        lv_obj_set_style_pad_all(btn, 0, 0);
        lv_obj_clear_flag(btn, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_clear_flag(btn, LV_OBJ_FLAG_EVENT_BUBBLE);
        lv_obj_add_event_cb(btn, on_nav, LV_EVENT_CLICKED, (void *)(intptr_t)i);

        lv_obj_t *icon = lv_label_create(btn);
        lv_label_set_text(icon, s_nav_icons[i]);
#if LV_FONT_MONTSERRAT_16
        lv_obj_set_style_text_font(icon, &lv_font_montserrat_16, 0);
#else
        lv_obj_set_style_text_font(icon, LV_FONT_DEFAULT, 0);
#endif
        lv_obj_center(icon);
        s_nav_icon[i] = icon;
    }
}

static void create_dots(lv_obj_t *scr)
{
    lv_obj_t *row = lv_obj_create(scr);
    lv_obj_set_size(row, 56, 14);
    lv_obj_align(row, LV_ALIGN_BOTTOM_MID, 0, -UI_DOTS_BOTTOM);
    lv_obj_set_style_bg_opa(row, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(row, 0, 0);
    lv_obj_set_style_pad_all(row, 0, 0);
    lv_obj_clear_flag(row, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_clear_flag(row, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_move_foreground(row);

    static const int xoff[] = {-14, 0, 14};
    for (int i = 0; i < 3; i++) {
        lv_obj_t *dot = lv_obj_create(row);
        lv_obj_set_size(dot, 8, 8);
        lv_obj_align(dot, LV_ALIGN_CENTER, xoff[i], 0);
        lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
        lv_obj_set_style_border_width(dot, 0, 0);
        lv_obj_set_style_bg_opa(dot, LV_OPA_40, 0);
        lv_obj_set_style_bg_color(dot, lv_color_hex(UI_COLOR_MUTED), 0);
        lv_obj_clear_flag(dot, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_clear_flag(dot, LV_OBJ_FLAG_CLICKABLE);
        s_dots[i] = dot;
    }
}

void ui_show_home(void)
{
    lv_obj_t *scr = lv_scr_act();
    lv_obj_set_style_bg_color(scr, lv_color_hex(UI_COLOR_BG), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

    s_tv = lv_tileview_create(scr);
    lv_obj_set_style_bg_opa(s_tv, LV_OPA_TRANSP, 0);
    lv_obj_set_style_bg_color(s_tv, lv_color_hex(UI_COLOR_BG), 0);
    lv_obj_set_scrollbar_mode(s_tv, LV_SCROLLBAR_MODE_OFF);
    lv_obj_add_event_cb(s_tv, on_tile_changed, LV_EVENT_VALUE_CHANGED, NULL);

    s_tiles[UI_PAGE_HOME] = lv_tileview_add_tile(s_tv, 0, 0, LV_DIR_RIGHT);
    style_tile(s_tiles[UI_PAGE_HOME]);

    s_tiles[UI_PAGE_MEDIA] = lv_tileview_add_tile(s_tv, 1, 0, LV_DIR_HOR);
    style_tile(s_tiles[UI_PAGE_MEDIA]);

    s_tiles[UI_PAGE_SETTINGS] = lv_tileview_add_tile(s_tv, 2, 0, LV_DIR_LEFT);
    style_tile(s_tiles[UI_PAGE_SETTINGS]);

    ui_home_create(s_tiles[UI_PAGE_HOME]);
    ui_media_create(s_tiles[UI_PAGE_MEDIA]);
    ui_settings_create(s_tiles[UI_PAGE_SETTINGS]);
    create_nav(scr);
    create_dots(scr);
    nav_set_active(UI_PAGE_HOME);

    app_audio_set_wake_cb(ui_handle_wake);
    app_audio_set_standby(true);
    Set_Backlight((uint8_t)s_saved_bl);
}

void ui_tick(void)
{
    if (!s_tv) {
        return;
    }

    ui_home_set_status(friendly_status());
    ui_home_set_heard(app_brain_heard());
    ui_home_set_reply(app_brain_reply());
    ui_settings_set_diag(app_wifi_status(), app_brain_status());

    bool listening = app_audio_is_listening();
    if (listening != s_shown_listen) {
        set_listen_visual(listening);
        app_brain_set_listen(listening);
        if (listening) {
            ui_go_page(UI_PAGE_HOME);
        }
    }
    ui_home_set_mic((listening || !s_asleep) ? app_audio_mic_level() : 0);

    bool radio = app_audio_is_radio();
    ui_media_set_playing(radio, s_radio_title[0] ? s_radio_title : app_brain_reply());
    ui_media_set_volume(app_audio_get_volume());
    ui_settings_set_volume(app_audio_get_volume());

    char cmd[24];
    int value = 0;
    if (app_brain_take_cmd(cmd, sizeof(cmd), &value)) {
        if (strcmp(cmd, "radio_play") == 0) {
            /* A late radio_play after the user re-opened listen would set
             * s_radio and mute the mic while the UI still says «Слушаю». */
            if (app_audio_is_listening()) {
                ESP_LOGW("ui", "ignore radio_play while listening");
            } else {
                const char *url = app_brain_cmd_url();
                const char *title = app_brain_cmd_title();
                if (app_audio_radio_start(url)) {
                    if (title && title[0]) {
                        strncpy(s_radio_title, title, sizeof(s_radio_title) - 1);
                        s_radio_title[sizeof(s_radio_title) - 1] = 0;
                    }
                    ui_home_set_heard("");
                    ui_home_set_reply("");
                    ui_media_set_playing(true, s_radio_title[0] ? s_radio_title : title);
                    ui_go_page(UI_PAGE_MEDIA);
                }
            }
        } else if (strcmp(cmd, "radio_stop") == 0) {
            ui_handle_radio_stop();
        } else if (strcmp(cmd, "volume") == 0) {
            app_audio_set_volume(value);
            ui_media_set_volume(app_audio_get_volume());
            ui_settings_set_volume(app_audio_get_volume());
        } else if (strcmp(cmd, "brightness") == 0) {
            ui_handle_brightness(value);
            if (!s_asleep) {
                ui_settings_set_brightness(s_saved_bl);
            }
        } else if (strcmp(cmd, "power_off") == 0) {
            ui_set_asleep(true);
        } else if (strcmp(cmd, "power_on") == 0) {
            ui_set_asleep(false);
        }
    }
}

void ui_set_asleep(bool on)
{
    s_asleep = on;
    if (on) {
        Set_Backlight(0);
        ui_home_set_listen(false, true);
    } else {
        if (s_saved_bl < 5) {
            s_saved_bl = 70;
        }
        ui_settings_set_brightness(s_saved_bl);
        Set_Backlight((uint8_t)s_saved_bl);
        if (!s_shown_listen) {
            ui_home_set_listen(false, false);
        }
    }
}

bool ui_is_asleep(void)
{
    return s_asleep;
}
