#include "ui_pages.h"

#include "app_audio.h"
#include "app_version.h"
#include "app_wifi.h"
#include "fonts.h"
#include "ui_theme.h"

static lv_obj_t *s_vol;
static lv_obj_t *s_bl;
static lv_obj_t *s_wifi;
static lv_obj_t *s_brain;

static void on_slider(lv_event_t *e, bool volume)
{
    lv_event_code_t code = lv_event_get_code(e);
    if (code == LV_EVENT_PRESSED) {
        ui_swipe_lock(true);
        return;
    }
    if (code == LV_EVENT_RELEASED || code == LV_EVENT_PRESS_LOST) {
        ui_swipe_lock(false);
    }
    if (code != LV_EVENT_VALUE_CHANGED) {
        return;
    }
    int v = lv_slider_get_value(lv_event_get_target(e));
    if (volume) {
        app_audio_set_volume(v);
    } else {
        ui_handle_brightness(v);
    }
}

static void on_vol(lv_event_t *e)
{
    on_slider(e, true);
}

static void on_bl(lv_event_t *e)
{
    on_slider(e, false);
}

static void on_forget(lv_event_t *e)
{
    (void)e;
    app_wifi_forget();
}

void ui_settings_create(lv_obj_t *parent)
{
    lv_obj_t *head = lv_label_create(parent);
    lv_label_set_text(head, "Настройки");
    lv_obj_set_style_text_color(head, lv_color_hex(UI_COLOR_TEXT), 0);
    lv_obj_set_style_text_font(head, &font_ru_14, 0);
    lv_obj_align(head, LV_ALIGN_TOP_MID, 0, UI_CONTENT_TOP);

    s_wifi = lv_label_create(parent);
    lv_label_set_text(s_wifi, "");
    lv_obj_set_width(s_wifi, 260);
    lv_label_set_long_mode(s_wifi, LV_LABEL_LONG_DOT);
    lv_obj_set_style_text_align(s_wifi, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(s_wifi, lv_color_hex(UI_COLOR_MUTED), 0);
    lv_obj_set_style_text_font(s_wifi, &font_ru_12, 0);
    lv_obj_align(s_wifi, LV_ALIGN_TOP_MID, 0, UI_CONTENT_TOP + 22);

    s_brain = lv_label_create(parent);
    lv_label_set_text(s_brain, "");
    lv_obj_set_width(s_brain, 260);
    lv_label_set_long_mode(s_brain, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_align(s_brain, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(s_brain, lv_color_hex(UI_COLOR_ACCENT), 0);
    lv_obj_set_style_text_font(s_brain, &font_ru_12, 0);
    lv_obj_align(s_brain, LV_ALIGN_TOP_MID, 0, UI_CONTENT_TOP + 38);

    lv_obj_t *vol_l = lv_label_create(parent);
    lv_label_set_text(vol_l, "Громкость");
    lv_obj_set_style_text_color(vol_l, lv_color_hex(UI_COLOR_MUTED), 0);
    lv_obj_set_style_text_font(vol_l, &font_ru_12, 0);
    lv_obj_align(vol_l, LV_ALIGN_CENTER, 0, -10);

    s_vol = lv_slider_create(parent);
    lv_obj_set_width(s_vol, UI_SLIDER_W);
    lv_slider_set_range(s_vol, 0, 100);
    lv_slider_set_value(s_vol, app_audio_get_volume(), LV_ANIM_OFF);
    lv_obj_align(s_vol, LV_ALIGN_CENTER, 0, 14);
    lv_obj_clear_flag(s_vol, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_clear_flag(s_vol, LV_OBJ_FLAG_SCROLL_CHAIN);
    lv_obj_add_event_cb(s_vol, on_vol, LV_EVENT_ALL, NULL);

    lv_obj_t *bl_l = lv_label_create(parent);
    lv_label_set_text(bl_l, "Яркость");
    lv_obj_set_style_text_color(bl_l, lv_color_hex(UI_COLOR_MUTED), 0);
    lv_obj_set_style_text_font(bl_l, &font_ru_12, 0);
    lv_obj_align(bl_l, LV_ALIGN_CENTER, 0, 48);

    s_bl = lv_slider_create(parent);
    lv_obj_set_width(s_bl, UI_SLIDER_W);
    lv_slider_set_range(s_bl, 5, 100);
    lv_slider_set_value(s_bl, 70, LV_ANIM_OFF);
    lv_obj_align(s_bl, LV_ALIGN_CENTER, 0, 72);
    lv_obj_clear_flag(s_bl, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_clear_flag(s_bl, LV_OBJ_FLAG_SCROLL_CHAIN);
    lv_obj_add_event_cb(s_bl, on_bl, LV_EVENT_ALL, NULL);

    lv_obj_t *forget = lv_btn_create(parent);
    lv_obj_set_size(forget, UI_RESET_WIFI_W, UI_RESET_WIFI_H);
    lv_obj_align(forget, LV_ALIGN_BOTTOM_MID, 0, -42);
    lv_obj_clear_flag(forget, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_add_event_cb(forget, on_forget, LV_EVENT_CLICKED, NULL);
    lv_obj_t *fl = lv_label_create(forget);
    lv_label_set_text(fl, "Сброс Wi-Fi");
    lv_obj_set_style_text_font(fl, &font_ru_12, 0);
    lv_obj_center(fl);

    /* Above the forget button — was -14 and covered the nav dots. */
    lv_obj_t *ver = lv_label_create(parent);
    lv_label_set_text(ver, "Прошивка " KOLONKA_VERSION_FULL);
    lv_obj_set_style_text_color(ver, lv_color_hex(UI_COLOR_MUTED), 0);
    lv_obj_set_style_text_font(ver, &font_ru_12, 0);
    lv_obj_align(ver, LV_ALIGN_BOTTOM_MID, 0, -78);
}

void ui_settings_set_volume(int percent)
{
    if (!s_vol) {
        return;
    }
    if (lv_slider_get_value(s_vol) != percent) {
        lv_slider_set_value(s_vol, percent, LV_ANIM_OFF);
    }
}

void ui_settings_set_brightness(int percent)
{
    if (!s_bl) {
        return;
    }
    if (percent < 5) {
        percent = 5;
    }
    if (lv_slider_get_value(s_bl) != percent) {
        lv_slider_set_value(s_bl, percent, LV_ANIM_OFF);
    }
}

void ui_settings_set_diag(const char *wifi, const char *brain)
{
    if (s_wifi && wifi) {
        lv_label_set_text(s_wifi, wifi);
    }
    if (s_brain && brain) {
        lv_label_set_text(s_brain, brain);
    }
}

