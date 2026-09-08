#pragma once

#include <stdint.h>

void aec_reset(void);
int16_t aec_cancel(int16_t mic, int16_t ref);
