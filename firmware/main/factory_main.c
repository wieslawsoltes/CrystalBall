#include "diagnostics.h"
#include "audio.h"
#include "display.h"
#include "halo.h"
#include "pins.h"
#include "driver/gpio.h"

/* Deliberately no configuration, NVS, network, time synchronization or API path. */
void app_main(void) {
    gpio_config_t inputs={.pin_bit_mask=(1ULL<<PIN_PTT)|(1ULL<<PIN_NEXT),
        .mode=GPIO_MODE_INPUT,.pull_up_en=GPIO_PULLUP_ENABLE};
    ESP_ERROR_CHECK(gpio_config(&inputs));
    ESP_ERROR_CHECK(orb_audio_init());
    ESP_ERROR_CHECK(orb_halo_init());
    ESP_ERROR_CHECK(orb_display_init());
    orb_diagnostics_run();
}
