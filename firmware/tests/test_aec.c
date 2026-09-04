#include "aec.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static float rms(const int16_t *x, int n)
{
    double acc = 0;
    for (int i = 0; i < n; i++) {
        acc += (double)x[i] * (double)x[i];
    }
    return (float)sqrt(acc / (double)n);
}

int main(void)
{
    const int n = 16000;
    int16_t *ref = malloc((size_t)n * sizeof(int16_t));
    int16_t *mic = malloc((size_t)n * sizeof(int16_t));
    int16_t *out = malloc((size_t)n * sizeof(int16_t));
    if (!ref || !mic || !out) {
        fprintf(stderr, "alloc failed\n");
        return 1;
    }

    for (int i = 0; i < n; i++) {
        ref[i] = (int16_t)(12000.0 * sin(2.0 * M_PI * 440.0 * i / 16000.0));
        int16_t echo = (i >= 6) ? (int16_t)(ref[i - 6] * 3 / 5) : 0;
        int16_t voice = (int16_t)(4000.0 * sin(2.0 * M_PI * 220.0 * i / 16000.0));
        mic[i] = (int16_t)(echo + voice);
    }

    aec_reset();
    for (int i = 0; i < n; i++) {
        out[i] = aec_process(mic[i], ref[i]);
    }

    float echo_in = rms(mic + 12000, 4000);
    float echo_out = rms(out + 12000, 4000);
    if (echo_out >= echo_in * 0.45f) {
        fprintf(stderr, "aec did not suppress echo: in=%.1f out=%.1f\n", echo_in, echo_out);
        return 1;
    }

    aec_reset();
    double voice_acc = 0;
    double out_acc = 0;
    for (int i = 0; i < n; i++) {
        int16_t voice = (int16_t)(5000.0 * sin(2.0 * M_PI * 220.0 * i / 16000.0));
        int16_t echo = (int16_t)(ref[i] * 2 / 3);
        int16_t y = aec_process((int16_t)(voice + echo), ref[i]);
        if (i >= 12000) {
            voice_acc += (double)voice * (double)voice;
            out_acc += (double)y * (double)y;
        }
    }
    float voice_rms = (float)sqrt(voice_acc / 4000.0);
    float kept = (float)sqrt(out_acc / 4000.0);
    if (kept < voice_rms * 0.35f) {
        fprintf(stderr, "aec ate the voice: voice=%.1f out=%.1f\n", voice_rms, kept);
        return 1;
    }

    printf("aec ok echo_in=%.1f echo_out=%.1f voice=%.1f kept=%.1f\n",
           echo_in, echo_out, voice_rms, kept);
    return 0;
}
