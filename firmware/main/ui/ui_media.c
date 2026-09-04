#include "ui_pages.h"

#include "app_audio.h"
#include "fonts.h"
#include "ui_theme.h"

static lv_obj_t *s_empty;
static lv_obj_t *s_hint;
static lv_obj_t *s_title;
static lv_obj_t *s_stop;
static lv_obj_t *s_vol;

static void on_stop(lv_event_t *e)
{
    (void)e;
    ui_handle_radio_stop();
}

static void on_vol(lv_event_t *e)
{
    lv_event_code_t code = lv_event_get_code(e);
    if (code == LV_EVENT_PRESSED) {
        ui_swipe_lock(true);
        return;
    }
    if (code == LV_EVENT_RELEASED || code == LV_EVENT_PRESS_LOST) {
        ui_swipe_lock(false);
    }
    if (code == LV_EVENT_VALUE_CHANGED) {
        app_audio_set_volume(lv_slider_get_value(lv_event_get_target(e)));
    }
}

void ui_media_create(lv_obj_t *parent)
{
    s_empty = lv_label_create(parent);
    lv_label_set_text(s_empty, "Ничего не играет");
    lv_obj_set_width(s_empty, 240);
    lv_obj_set_style_text_align(s_empty, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(s_empty, lv_color_hex(UI_COLOR_TEXT), 0);
    lv_obj_set_style_text_font(s_empty, &font_ru_14, 0);
    lv_obj_align(s_empty, LV_ALIGN_CENTER, 0, -24);

    s_hint = lv_label_create(parent);
    lv_label_set_text(s_hint, "Скажи: включи радио");
    lv_obj_set_width(s_hint, 240);
    lv_label_set_long_mode(s_hint, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_align(s_hint, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(s_hint, lv_color_hex(UI_COLOR_MUTED), 0);
    lv_obj_set_style_text_font(s_hint, &font_ru_12, 0);
    lv_obj_align(s_hint, LV_ALIGN_CENTER, 0, 8);

    s_title = lv_label_create(parent);
    lv_label_set_text(s_title, "");
    lv_obj_set_width(s_title, 250);
    lv_obj_set_height(s_title, 40);
    lv_label_set_long_mode(s_title, LV_LABEL_LONG_DOT);
    lv_obj_set_style_text_align(s_title, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(s_title, lv_color_hex(UI_COLOR_TEXT), 0);
    lv_obj_set_style_text_font(s_title, &font_ru_14, 0);
    lv_obj_align(s_title, LV_ALIGN_CENTER, 0, -36);
    lv_obj_add_flag(s_title, LV_OBJ_FLAG_HIDDEN);

    s_stop = lv_btn_create(parent);
    lv_obj_set_size(s_stop, 100, 32);
    lv_obj_align(s_stop, LV_ALIGN_CENTER, 0, 20);
    lv_obj_clear_flag(s_stop, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_add_event_cb(s_stop, on_stop, LV_EVENT_CLICKED, NULL);
    lv_obj_add_flag(s_stop, LV_OBJ_FLAG_HIDDEN);
    lv_obj_t *sl = lv_label_create(s_stop);
    lv_label_set_text(sl, "Стоп");
    lv_obj_set_style_text_font(sl, &font_ru_12, 0);
    lv_obj_center(sl);

    lv_obj_t *vol_l = lv_label_create(parent);
    lv_label_set_text(vol_l, "Громкость");
    lv_obj_set_style_text_color(vol_l, lv_color_hex(UI_COLOR_MUTED), 0);
    lv_obj_set_style_text_font(vol_l, &font_ru_12, 0);
    lv_obj_align(vol_l, LV_ALIGN_BOTTOM_MID, 0, -76);

    s_vol = lv_slider_create(parent);
    lv_obj_set_width(s_vol, UI_SLIDER_W);
    lv_slider_set_range(s_vol, 0, 100);
    lv_slider_set_value(s_vol, app_audio_get_volume(), LV_ANIM_OFF);
    lv_obj_align(s_vol, LV_ALIGN_BOTTOM_MID, 0, -52);
    lv_obj_clear_flag(s_vol, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_clear_flag(s_vol, LV_OBJ_FLAG_SCROLL_CHAIN);
    lv_obj_add_event_cb(s_vol, on_vol, LV_EVENT_ALL, NULL);
}

void ui_media_set_playing(bool on, const char *title)
{
    if (!s_empty) {
        return;
    }
    if (on) {
        lv_obj_add_flag(s_empty, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s_hint, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(s_title, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(s_stop, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(s_title, title && title[0] ? title : "Радио");
    } else {
        lv_obj_clear_flag(s_empty, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(s_hint, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s_title, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s_stop, LV_OBJ_FLAG_HIDDEN);
    }
}

void ui_media_set_volume(int percent)
{
    if (!s_vol) {
        return;
    }
    if (lv_slider_get_value(s_vol) != percent) {
        lv_slider_set_value(s_vol, percent, LV_ANIM_OFF);
    }
}
