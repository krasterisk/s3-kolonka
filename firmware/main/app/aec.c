#include "aec.h"

#define AEC_G_MAX 49152
#define AEC_ADAPT_SHIFT 20

static int32_t s_g;

void aec_reset(void)
{
    s_g = 0;
}

int16_t aec_cancel(int16_t mic, int16_t ref)
{
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
