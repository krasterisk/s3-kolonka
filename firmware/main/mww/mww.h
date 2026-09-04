#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

bool mww_start(void);
void mww_reset(void);
bool mww_feed(const int16_t *mono, int samples);

#ifdef __cplusplus
}
#endif
