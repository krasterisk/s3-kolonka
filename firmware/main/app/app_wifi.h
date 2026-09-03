#pragma once

#include <stdbool.h>

void app_wifi_start(void);
bool app_wifi_connected(void);
bool app_wifi_is_setup_ap(void);
const char *app_wifi_status(void);
const char *app_wifi_ip(void);
void app_wifi_forget(void);
