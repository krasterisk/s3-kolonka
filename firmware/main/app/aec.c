#include "aec.h"

#include <string.h>

#define AEC_TAPS 128
#define AEC_HP_A 32440 /* 0.995 in Q15 */
#define AEC_MU_Q15 8192 /* mu = 0.25 */
#define AEC_PWR_MIN 8000
#define AEC_W_MAX 131072

typedef struct {
    int32_t x1;
    int32_t y1;
} hp_state_t;

static int16_t s_x[AEC_TAPS];
static int32_t s_w[AEC_TAPS];
static int s_xi;
static hp_state_t s_mic_hp;
static hp_state_t s_ref_hp;

static int16_t hp_filter(hp_state_t *st, int16_t x)
{
    int32_t y = (int32_t)x - st->x1 + (int32_t)(((int64_t)st->y1 * AEC_HP_A) >> 15);
    st->x1 = x;
    st->y1 = y;
    if (y > 32767) {
        y = 32767;
    } else if (y < -32768) {
        y = -32768;
    }
    return (int16_t)y;
}

void aec_reset(void)
{
    memset(s_x, 0, sizeof(s_x));
    memset(s_w, 0, sizeof(s_w));
    memset(&s_mic_hp, 0, sizeof(s_mic_hp));
    memset(&s_ref_hp, 0, sizeof(s_ref_hp));
    s_xi = 0;
}

int16_t aec_process(int16_t mic, int16_t ref)
{
    mic = hp_filter(&s_mic_hp, mic);
    ref = hp_filter(&s_ref_hp, ref);
    s_x[s_xi] = ref;

    int64_t y_acc = 0;
    int64_t pwr = 1;
    int j = s_xi;
    for (int i = 0; i < AEC_TAPS; i++) {
        int32_t r = s_x[j];
        y_acc += (int64_t)s_w[i] * r;
        pwr += (int64_t)r * r;
        if (--j < 0) {
            j = AEC_TAPS - 1;
        }
    }

    int32_t e = (int32_t)mic - (int32_t)(y_acc >> 15);
    if (e > 32767) {
        e = 32767;
    } else if (e < -32768) {
        e = -32768;
    }

    if (pwr > AEC_PWR_MIN) {
        j = s_xi;
        for (int i = 0; i < AEC_TAPS; i++) {
            int32_t r = s_x[j];
            int32_t dw = (int32_t)(((int64_t)e * r * AEC_MU_Q15) / pwr);
            int32_t nw = s_w[i] + dw;
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
    }

    if (++s_xi >= AEC_TAPS) {
        s_xi = 0;
    }
    return (int16_t)e;
}
