#pragma once

#include "lvgl.h"

#include <stdbool.h>

typedef enum {
    UI_PAGE_HOME = 0,
    UI_PAGE_MEDIA = 1,
    UI_PAGE_SETTINGS = 2,
} ui_page_t;

void ui_go_page(ui_page_t page);
void ui_swipe_lock(bool lock);
void ui_handle_listen_click(void);
void ui_handle_wake(void);
void ui_handle_radio_stop(void);
void ui_handle_brightness(int percent);

void ui_home_create(lv_obj_t *parent);
void ui_home_set_listen(bool on, bool asleep);
void ui_home_set_status(const char *text);
void ui_home_set_heard(const char *text);
void ui_home_set_reply(const char *text);
void ui_home_set_mic(int level);

void ui_media_create(lv_obj_t *parent);
void ui_media_set_playing(bool on, const char *title);
void ui_media_set_volume(int percent);

void ui_settings_create(lv_obj_t *parent);
void ui_settings_set_volume(int percent);
void ui_settings_set_brightness(int percent);
void ui_settings_set_diag(const char *wifi, const char *brain);
