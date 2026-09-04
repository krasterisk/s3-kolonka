#pragma once

#include <stdbool.h>

void app_brain_start(void);
void app_brain_set_listen(bool on);
void app_brain_set_wake_mode(bool on);
bool app_brain_ready(void);
bool app_brain_take_cmd(char *name, int name_len, int *value);
const char *app_brain_status(void);
const char *app_brain_heard(void);
const char *app_brain_reply(void);
