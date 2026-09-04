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
typedef void (*app_audio_wake_cb_t)(void);
void app_audio_set_mic_sink(app_audio_mic_sink_t sink);
void app_audio_set_wake_cb(app_audio_wake_cb_t cb);
void app_audio_set_standby(bool on);
void app_audio_flush_preroll(void);
void app_audio_play_pcm16(const int16_t *stereo, int samples);
bool app_audio_is_playing(void);
void app_audio_play_end(void);
void app_audio_play_abort(void);
bool app_audio_radio_start(const char *url);
void app_audio_radio_stop(void);
bool app_audio_is_radio(void);
