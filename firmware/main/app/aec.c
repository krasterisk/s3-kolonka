#include "aec.h"

#include <string.h>

#define AEC_TAPS 64
#define AEC_W_MAX 49152
#define AEC_ADAPT_SHIFT 19

static int16_t s_x[AEC_TAPS];
static int32_t s_w[AEC_TAPS];
static int s_xi;

void aec_reset(void)
{
    memset(s_x, 0, sizeof(s_x));
    memset(s_w, 0, sizeof(s_w));
    s_xi = 0;
}

int16_t aec_process(int16_t mic, int16_t ref)
{
    s_x[s_xi] = ref;

    int64_t y = 0;
    int j = s_xi;
    for (int i = 0; i < AEC_TAPS; i++) {
        y += (int64_t)s_w[i] * s_x[j];
        if (--j < 0) {
            j = AEC_TAPS - 1;
        }
    }

    int32_t e = (int32_t)mic - (int32_t)(y >> 15);
    j = s_xi;
    for (int i = 0; i < AEC_TAPS; i++) {
        int32_t nw = s_w[i] + ((e * (int32_t)s_x[j]) >> AEC_ADAPT_SHIFT);
        if (nw > AEC_W_MAX) {
            nw = AEC_W_MAX;
        } else if (nw < -AEC_W_MAX) {
            nw = -AEC_W_MAX;
        }
        s_w[i] = nw;
        if (--j < 0) {
            j = AEC_TAPS - 1;
        }
    }

    if (++s_xi >= AEC_TAPS) {
        s_xi = 0;
    }
    if (e > 32767) {
        e = 32767;
    } else if (e < -32768) {
        e = -32768;
    }
    return (int16_t)e;
}
