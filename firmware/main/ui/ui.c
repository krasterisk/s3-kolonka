#include "ui.h"

#include "ST77916.h"
#include "app_audio.h"
#include "app_brain.h"
#include "app_wifi.h"
#include "esp_system.h"
#include "lvgl.h"

static lv_obj_t *s_status;
static lv_obj_t *s_brain;
static lv_obj_t *s_hint;
static lv_obj_t *s_arc;
static lv_obj_t *s_vol;
static lv_obj_t *s_bl;
static bool s_shown_listen;

static void set_listen_visual(bool on)
{
    s_shown_listen = on;
    lv_obj_t *scr = lv_scr_act();
    lv_obj_set_style_bg_color(scr, lv_color_hex(on ? 0x1A2A22 : 0x101418), 0);
    lv_label_set_text(s_hint, on ? "Listening..." : "Tap to listen");
}

static void on_listen_click(lv_event_t *e)
{
    (void)e;
    bool next = !app_audio_is_listening();
    app_audio_set_listen(next);
    app_brain_set_listen(next);
    set_listen_visual(next);
    app_audio_beep(next ? 880 : 440, 80);
}

static void on_vol(lv_event_t *e)
{
    int v = lv_slider_get_value(lv_event_get_target(e));
    app_audio_set_volume(v);
}

static void on_bl(lv_event_t *e)
{
    int v = lv_slider_get_value(lv_event_get_target(e));
    Set_Backlight((uint8_t)v);
}

static void on_forget(lv_event_t *e)
{
    (void)e;
    app_wifi_forget();
}

void ui_show_home(void)
{
    lv_obj_t *scr = lv_scr_act();
    lv_obj_set_style_bg_color(scr, lv_color_hex(0x101418), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

    lv_obj_t *listen = lv_obj_create(scr);
    lv_obj_set_size(listen, 168, 168);
    lv_obj_align(listen, LV_ALIGN_CENTER, 0, -8);
    lv_obj_set_style_bg_opa(listen, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(listen, 0, 0);
    lv_obj_set_style_pad_all(listen, 0, 0);
    lv_obj_set_style_radius(listen, LV_RADIUS_CIRCLE, 0);
    lv_obj_clear_flag(listen, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_clear_flag(listen, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_add_event_cb(listen, on_listen_click, LV_EVENT_CLICKED, NULL);

    lv_obj_t *title = lv_label_create(scr);
    lv_label_set_text(title, "s3-kolonka");
    lv_obj_set_style_text_color(title, lv_color_hex(0xF2F4F8), 0);
    lv_obj_set_style_text_font(title, &lv_font_montserrat_16, 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, 0, 46);

    s_status = lv_label_create(scr);
    lv_label_set_text(s_status, "Starting...");
    lv_obj_set_style_text_color(s_status, lv_color_hex(0x8AA0B4), 0);
    lv_obj_set_style_text_font(s_status, &lv_font_montserrat_12, 0);
    lv_obj_align(s_status, LV_ALIGN_TOP_MID, 0, 68);

    s_brain = lv_label_create(scr);
    lv_label_set_text(s_brain, "Brain: wait");
    lv_obj_set_width(s_brain, 300);
    lv_label_set_long_mode(s_brain, LV_LABEL_LONG_CLIP);
    lv_obj_set_style_text_align(s_brain, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(s_brain, lv_color_hex(0x3DDC97), 0);
    lv_obj_set_style_text_font(s_brain, &lv_font_montserrat_12, 0);
    lv_obj_align(s_brain, LV_ALIGN_TOP_MID, 0, 84);

    s_arc = lv_arc_create(listen);
    lv_obj_set_size(s_arc, 168, 168);
    lv_obj_center(s_arc);
    lv_arc_set_range(s_arc, 0, 100);
    lv_arc_set_value(s_arc, 0);
    lv_obj_clear_flag(s_arc, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_arc_color(s_arc, lv_color_hex(0x2A3340), LV_PART_MAIN);
    lv_obj_set_style_arc_color(s_arc, lv_color_hex(0x3DDC97), LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(s_arc, lv_color_hex(0x3DDC97), LV_PART_KNOB);
    lv_obj_set_style_opa(s_arc, LV_OPA_0, LV_PART_KNOB);

    s_hint = lv_label_create(listen);
    lv_label_set_text(s_hint, "Tap to listen");
    lv_obj_set_style_text_color(s_hint, lv_color_hex(0xF2F4F8), 0);
    lv_obj_set_style_text_font(s_hint, &lv_font_montserrat_14, 0);
    lv_obj_center(s_hint);

    lv_obj_t *vol_l = lv_label_create(scr);
    lv_label_set_text(vol_l, "VOL");
    lv_obj_set_style_text_color(vol_l, lv_color_hex(0x8AA0B4), 0);
    lv_obj_set_style_text_font(vol_l, &lv_font_montserrat_12, 0);
    lv_obj_align(vol_l, LV_ALIGN_BOTTOM_MID, -110, -78);

    s_vol = lv_slider_create(scr);
    lv_obj_set_width(s_vol, 170);
    lv_slider_set_range(s_vol, 0, 100);
    lv_slider_set_value(s_vol, app_audio_get_volume(), LV_ANIM_OFF);
    lv_obj_align(s_vol, LV_ALIGN_BOTTOM_MID, 16, -80);
    lv_obj_clear_flag(s_vol, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_add_event_cb(s_vol, on_vol, LV_EVENT_VALUE_CHANGED, NULL);

    lv_obj_t *bl_l = lv_label_create(scr);
    lv_label_set_text(bl_l, "BL");
    lv_obj_set_style_text_color(bl_l, lv_color_hex(0x8AA0B4), 0);
    lv_obj_set_style_text_font(bl_l, &lv_font_montserrat_12, 0);
    lv_obj_align(bl_l, LV_ALIGN_BOTTOM_MID, -110, -48);

    s_bl = lv_slider_create(scr);
    lv_obj_set_width(s_bl, 170);
    lv_slider_set_range(s_bl, 5, 100);
    lv_slider_set_value(s_bl, 70, LV_ANIM_OFF);
    lv_obj_align(s_bl, LV_ALIGN_BOTTOM_MID, 16, -50);
    lv_obj_clear_flag(s_bl, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_add_event_cb(s_bl, on_bl, LV_EVENT_VALUE_CHANGED, NULL);
    Set_Backlight(70);

    lv_obj_t *forget = lv_btn_create(scr);
    lv_obj_set_size(forget, 120, 28);
    lv_obj_align(forget, LV_ALIGN_BOTTOM_MID, 0, -14);
    lv_obj_clear_flag(forget, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_add_event_cb(forget, on_forget, LV_EVENT_CLICKED, NULL);
    lv_obj_t *fl = lv_label_create(forget);
    lv_label_set_text(fl, "Reset Wi-Fi");
    lv_obj_set_style_text_font(fl, &lv_font_montserrat_12, 0);
    lv_obj_center(fl);
}

void ui_tick(void)
{
    if (!s_status) {
        return;
    }
    lv_label_set_text(s_status, app_wifi_status());
    lv_label_set_text(s_brain, app_brain_status());
    bool listening = app_audio_is_listening();
    if (listening != s_shown_listen) {
        set_listen_visual(listening);
        app_brain_set_listen(listening);
    }
    lv_arc_set_value(s_arc, listening ? app_audio_mic_level() : 0);
}
