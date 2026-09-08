#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ESP-SR AFE acoustic echo cancellation only. No WakeNet, no MultiNet. */

bool afe_aec_start(void);
void afe_aec_stop(void);
int afe_aec_feed_samples(void);
int afe_aec_feed_ch(void);
bool afe_aec_feed(const int16_t *interleaved);
int afe_aec_fetch(int16_t *mono, int max_samples);

#ifdef __cplusplus
}
#endif
