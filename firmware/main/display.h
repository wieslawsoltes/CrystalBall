#pragma once
#include "esp_err.h"
#include <stddef.h>
esp_err_t orb_display_init(void);
esp_err_t orb_display_status(const char *title,const char *body);
esp_err_t orb_display_page(const char *text,size_t offset,unsigned page);
esp_err_t orb_display_calibration(void);
