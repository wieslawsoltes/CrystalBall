#pragma once
#include "esp_err.h"
#include "config.h"
#include "core.h"
#include <stddef.h>
#include <stdint.h>
esp_err_t orb_network_init(const orb_config_t *config);
bool orb_network_online(void);
esp_err_t orb_fortune(const uint8_t *wav,size_t bytes,char text[ORB_TEXT_MAX+1]);
esp_err_t orb_speech(const char *text,uint8_t **pcm,size_t *bytes);
