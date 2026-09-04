#include "aec.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static int run_case(const char *name, int delay, int n)
{
    int16_t *ref = malloc((size_t)n * sizeof(int16_t));
    if (!ref) {
        fprintf(stderr, "alloc failed\n");
        return 1;
    }

    aec_reset();
    double echo_in_acc = 0;
    double echo_out_acc = 0;
    for (int i = 0; i < n; i++) {
        ref[i] = (int16_t)(12000.0 * sin(2.0 * M_PI * 440.0 * i / 16000.0));
        int16_t echo = (i >= delay) ? (int16_t)(ref[i - delay] * 3 / 5) : 0;
        int16_t y = aec_process(echo, ref[i]);
        if (i >= n / 2) {
            echo_in_acc += (double)echo * (double)echo;
            echo_out_acc += (double)y * (double)y;
        }
    }
    float echo_in = (float)sqrt(echo_in_acc / (double)(n / 2));
    float echo_out = (float)sqrt(echo_out_acc / (double)(n / 2));
    if (echo_out >= echo_in * 0.45f) {
        fprintf(stderr, "%s echo not suppressed: in=%.1f out=%.1f\n", name, echo_in, echo_out);
        free(ref);
        return 1;
    }

    aec_reset();
    double voice_acc = 0;
    double out_acc = 0;
    for (int i = 0; i < n; i++) {
        int16_t voice = (int16_t)(5000.0 * sin(2.0 * M_PI * 220.0 * i / 16000.0));
        int16_t echo = (i >= delay) ? (int16_t)(ref[i - delay] * 2 / 3) : 0;
        int16_t y = aec_process((int16_t)(voice + echo), ref[i]);
        if (i >= n / 2) {
            voice_acc += (double)voice * (double)voice;
            out_acc += (double)y * (double)y;
        }
    }
    float voice_rms = (float)sqrt(voice_acc / (double)(n / 2));
    float kept = (float)sqrt(out_acc / (double)(n / 2));
    free(ref);
    if (kept < voice_rms * 0.35f) {
        fprintf(stderr, "%s ate voice: voice=%.1f out=%.1f\n", name, voice_rms, kept);
        return 1;
    }
    printf("%s ok echo_in=%.1f echo_out=%.1f voice=%.1f kept=%.1f\n",
           name, echo_in, echo_out, voice_rms, kept);
    return 0;
}

int main(void)
{
    if (run_case("same-sample", 0, 8000) != 0) {
        return 1;
    }
    if (run_case("delay-6", 6, 8000) != 0) {
        return 1;
    }
    if (run_case("delay-40", 40, 12000) != 0) {
        return 1;
    }
    return 0;
}
