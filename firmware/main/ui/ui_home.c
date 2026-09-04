#include "ui_pages.h"

#include "fonts.h"
#include "ui_theme.h"

static lv_obj_t *s_status;
static lv_obj_t *s_heard;
static lv_obj_t *s_reply;
static lv_obj_t *s_hint;
static lv_obj_t *s_arc;

static void on_listen_click(lv_event_t *e)
{
    (void)e;
    ui_handle_listen_click();
}

void ui_home_create(lv_obj_t *parent)
{
    lv_obj_t *listen = lv_obj_create(parent);
    lv_obj_set_size(listen, UI_LISTEN_SIZE, UI_LISTEN_SIZE);
    lv_obj_align(listen, LV_ALIGN_CENTER, 0, 8);
    lv_obj_set_style_bg_opa(listen, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(listen, 0, 0);
    lv_obj_set_style_pad_all(listen, 0, 0);
    lv_obj_set_style_radius(listen, LV_RADIUS_CIRCLE, 0);
    lv_obj_clear_flag(listen, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_clear_flag(listen, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_add_event_cb(listen, on_listen_click, LV_EVENT_CLICKED, NULL);

    s_status = lv_label_create(parent);
    lv_label_set_text(s_status, "Готов");
    lv_obj_set_width(s_status, 240);
    lv_label_set_long_mode(s_status, LV_LABEL_LONG_DOT);
    lv_obj_set_style_text_align(s_status, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(s_status, lv_color_hex(UI_COLOR_MUTED), 0);
    lv_obj_set_style_text_font(s_status, &font_ru_12, 0);
    lv_obj_align(s_status, LV_ALIGN_TOP_MID, 0, UI_CONTENT_TOP);

    s_heard = lv_label_create(parent);
    lv_label_set_text(s_heard, "");
    lv_obj_set_width(s_heard, 240);
    lv_obj_set_height(s_heard, 28);
    lv_label_set_long_mode(s_heard, LV_LABEL_LONG_DOT);
    lv_obj_set_style_text_align(s_heard, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(s_heard, lv_color_hex(UI_COLOR_HEARD), 0);
    lv_obj_set_style_text_font(s_heard, &font_ru_12, 0);
    lv_obj_align(s_heard, LV_ALIGN_TOP_MID, 0, UI_CONTENT_TOP + 18);

    s_arc = lv_arc_create(listen);
    lv_obj_set_size(s_arc, UI_LISTEN_SIZE, UI_LISTEN_SIZE);
    lv_obj_center(s_arc);
    lv_arc_set_range(s_arc, 0, 100);
    lv_arc_set_value(s_arc, 0);
    lv_obj_clear_flag(s_arc, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_arc_color(s_arc, lv_color_hex(UI_COLOR_ARC_TRACK), LV_PART_MAIN);
    lv_obj_set_style_arc_color(s_arc, lv_color_hex(UI_COLOR_ACCENT), LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(s_arc, lv_color_hex(UI_COLOR_ACCENT), LV_PART_KNOB);
    lv_obj_set_style_opa(s_arc, LV_OPA_0, LV_PART_KNOB);

    s_hint = lv_label_create(listen);
    lv_label_set_text(s_hint, "Скажи hey Jarvis");
    lv_obj_set_width(s_hint, 110);
    lv_label_set_long_mode(s_hint, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_align(s_hint, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(s_hint, lv_color_hex(UI_COLOR_TEXT), 0);
    lv_obj_set_style_text_font(s_hint, &font_ru_12, 0);
    lv_obj_center(s_hint);

    s_reply = lv_label_create(parent);
    lv_label_set_text(s_reply, "");
    lv_obj_set_width(s_reply, 250);
    lv_obj_set_height(s_reply, 32);
    lv_label_set_long_mode(s_reply, LV_LABEL_LONG_DOT);
    lv_obj_set_style_text_align(s_reply, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(s_reply, lv_color_hex(UI_COLOR_TEXT), 0);
    lv_obj_set_style_text_font(s_reply, &font_ru_14, 0);
    lv_obj_align(s_reply, LV_ALIGN_CENTER, 0, 92);
}

void ui_home_set_listen(bool on, bool asleep)
{
    if (!s_hint) {
        return;
    }
    if (asleep && !on) {
        lv_label_set_text(s_hint, "Сон");
    } else {
        lv_label_set_text(s_hint, on ? "Слушаю..." : "Скажи hey Jarvis");
    }
}

void ui_home_set_status(const char *text)
{
    if (s_status && text) {
        lv_label_set_text(s_status, text);
    }
}

void ui_home_set_heard(const char *text)
{
    if (s_heard) {
        lv_label_set_text(s_heard, text && text[0] ? text : "");
    }
}

void ui_home_set_reply(const char *text)
{
    if (s_reply) {
        lv_label_set_text(s_reply, text && text[0] ? text : "");
    }
}

void ui_home_set_mic(int level)
{
    if (s_arc) {
        lv_arc_set_value(s_arc, level);
    }
}
