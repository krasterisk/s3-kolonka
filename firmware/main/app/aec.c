#include "aec.h"

#define AEC_HP_A 32440 /* 0.995 in Q15 */
#define AEC_G_MAX 49152
#define AEC_ADAPT_SHIFT 20

static int32_t s_g;
static int32_t s_mic_x1;
static int32_t s_mic_y1;
static int32_t s_ref_x1;
static int32_t s_ref_y1;

static int16_t hp_filter(int32_t *x1, int32_t *y1, int16_t x)
{
    int32_t y = (int32_t)x - *x1 + (int32_t)(((int64_t)*y1 * AEC_HP_A) >> 15);
    *x1 = x;
    *y1 = y;
    if (y > 32767) {
        y = 32767;
    } else if (y < -32768) {
        y = -32768;
    }
    return (int16_t)y;
}

void aec_reset(void)
{
    s_g = 0;
    s_mic_x1 = 0;
    s_mic_y1 = 0;
    s_ref_x1 = 0;
    s_ref_y1 = 0;
}

int16_t aec_process(int16_t mic, int16_t ref)
{
    mic = hp_filter(&s_mic_x1, &s_mic_y1, mic);
    ref = hp_filter(&s_ref_x1, &s_ref_y1, ref);

    int32_t e = (int32_t)mic - ((s_g * (int32_t)ref) >> 15);
    s_g += (e * (int32_t)ref) >> AEC_ADAPT_SHIFT;
    if (s_g > AEC_G_MAX) {
        s_g = AEC_G_MAX;
    } else if (s_g < -AEC_G_MAX) {
        s_g = -AEC_G_MAX;
    }
    if (e > 32767) {
        e = 32767;
    } else if (e < -32768) {
        e = -32768;
    }
    return (int16_t)e;
}
