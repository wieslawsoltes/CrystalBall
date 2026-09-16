#pragma once
#include "esp_err.h"
#include <stdint.h>
#include <stddef.h>
esp_err_t orb_audio_init(void);
esp_err_t orb_audio_record(uint8_t **wav,size_t *bytes);
esp_err_t orb_audio_play(const uint8_t *pcm,size_t bytes);
void orb_audio_mute(void);
/* Factory tone: hold TALK, <=1 second; never automatic repeat. */
esp_err_t orb_audio_test_tone(void);
