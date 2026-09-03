#pragma once

#include <stdbool.h>
#include <stdint.h>

void app_audio_start(void);
void app_audio_set_volume(int percent);
int app_audio_get_volume(void);
void app_audio_chime(void);
void app_audio_beep(int hz, int ms);
void app_audio_set_listen(bool on);
bool app_audio_is_listening(void);
int app_audio_mic_level(void);

typedef void (*app_audio_mic_sink_t)(const int16_t *mono, int samples);
void app_audio_set_mic_sink(app_audio_mic_sink_t sink);
void app_audio_play_pcm16(const int16_t *stereo, int samples);
bool app_audio_is_playing(void);
void app_audio_play_end(void);
