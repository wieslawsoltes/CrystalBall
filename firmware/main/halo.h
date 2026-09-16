#pragma once
#include "esp_err.h"
#include <stdint.h>
esp_err_t orb_halo_init(void);
esp_err_t orb_halo_rgb(uint8_t r,uint8_t g,uint8_t b);
