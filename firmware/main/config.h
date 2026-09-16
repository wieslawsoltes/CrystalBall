#pragma once
#include "esp_err.h"
typedef struct {char ssid[33],password[65],url[192],token[129],unit[33];} orb_config_t;
esp_err_t orb_config_load(orb_config_t *out);
