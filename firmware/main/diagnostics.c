#include "diagnostics.h"
#include "diagnostics_core.h"
#include "audio.h"
#include "core.h"
#include "display.h"
#include "halo.h"
#include "pins.h"
#include "driver/gpio.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

enum { HELP, GRID, BLACK, WHITE, RGB, CHECKER, RAMP, PIXELS, TONE, MICROPHONE, PAGE_COUNT };
typedef struct { bool raw, stable; int64_t changed; } button_t;
static bool edge(button_t *button, bool pressed, int64_t now) {
    if (button->raw != pressed) { button->raw = pressed; button->changed = now; }
    if (now - button->changed < 35000 || button->stable == button->raw) return false;
    button->stable = button->raw;
    return button->stable;
}
static void page(unsigned current) {
    orb_audio_mute(); (void)orb_halo_rgb(0,0,0);
    if (current == GRID) { (void)orb_display_calibration(); return; }
    if (current >= BLACK && current <= RAMP) {
        (void)orb_display_pattern((orb_pattern_t)(current - BLACK)); return;
    }
    const char *title = "BENCH DIAGNOSTICS", *body =
        "NO CLOUD OR WIFI. PAGE SELECTS TEST. TALK RUNS SELECTED TEST. FLASH ONLY WHILE DEVKIT IS REMOVED FROM BOTH SOCKETS. NOT CUSTOMER FIRMWARE.";
    if (current == PIXELS) { title="PIXEL WALK";body="TAP TALK FOR NEXT PIXEL. SIXTEEN PIXELS IN RED, GREEN, BLUE ORDER. PAGE TURNS ALL OFF. LOW BRIGHTNESS TEST ONLY."; }
    if (current == TONE) { title="1 KHZ TEST TONE";body="HOLD TALK TO PLAY. RELEASE TO STOP. ONE SECOND MAXIMUM. KEEP SPEAKER AWAY FROM EARS. NO AUTOMATIC REPEAT."; }
    if (current == MICROPHONE) { title="MICROPHONE LEVEL";body="HOLD TALK TO CAPTURE. RELEASE FOR DIGITAL RMS, PEAK AND CLIP COUNTS. RED LED MEANS CAPTURE. NO SAVE OR UPLOAD. NOT CALIBRATED SPL."; }
    (void)orb_display_status(title,body);
}
void orb_diagnostics_run(void) {
    unsigned current=HELP,pixel=0;button_t next={0},talk={0};
    /* Require both buttons released after boot; a held button cannot start sound. */
    bool armed=false;page(current);
    for (;;) {
        bool ptt=!gpio_get_level(PIN_PTT),pg=!gpio_get_level(PIN_NEXT);
        int64_t now=esp_timer_get_time();
        bool step=edge(&next,pg,now),run=edge(&talk,ptt,now);
        if (!ptt&&!pg&&!talk.stable&&!next.stable) armed=true;
        if (armed&&step) { current=(current+1)%PAGE_COUNT;pixel=0;page(current); }
        else if (armed&&run) {
            if (current==PIXELS) {
                unsigned channel=pixel/16,index=pixel%16;uint8_t level=12;
                esp_err_t e=orb_halo_pixel(index,channel==0?level:0,channel==1?level:0,channel==2?level:0);
                char text[100];snprintf(text,sizeof text,"PIXEL %u / 16. COLOR %s. DRIVER %s. VERIFY VISUALLY; NOT AN AUTOMATIC PASS.",index+1,channel==0?"RED":channel==1?"GREEN":"BLUE",e==ESP_OK?"OK":"ERROR");
                (void)orb_display_status("PIXEL WALK",text);orb_wipe(text,sizeof text);pixel=(pixel+1)%48;
            } else if (current==TONE) {
                esp_err_t e=orb_audio_test_tone();orb_audio_mute();
                (void)orb_display_status("TONE COMPLETE",e==ESP_OK?"OUTPUT STOPPED. RELEASE TALK BEFORE RETEST. DRIVER COMPLETION DOES NOT PROVE ACOUSTIC OUTPUT.":"I2S DRIVER ERROR. OUTPUT MUTED. INSPECT HARDWARE BEFORE RETEST.");
            } else if (current==MICROPHONE) {
                uint8_t *wav=NULL;size_t bytes=0;orb_pcm_stats_t stats={0};
                (void)orb_display_status("CAPTURING", "RELEASE TALK FOR RESULT. MICROPHONE ACTIVE ONLY WHILE HELD, UP TO THE CONFIGURED LIMIT.");
                esp_err_t e=orb_audio_record(&wav,&bytes);orb_audio_mute();
                bool valid=e==ESP_OK&&bytes>=44&&orb_diag_pcm_stats(wav+44,bytes-44,&stats);
                if (wav) { orb_wipe(wav,bytes);free(wav); }
                char text[220];
                if (valid) snprintf(text,sizeof text,"N=%"PRIu32" RMS=%"PRIu32" PEAK=%"PRIu32" DC=%"PRId32" CLIP=%"PRIu32" ZC=%"PRIu32". DIGITAL COUNTS ONLY. NO AUDIO SAVED. HEAP=%u.",stats.samples,stats.rms,stats.peak,stats.dc,stats.clipped,stats.zero_crossings,(unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
                else snprintf(text,sizeof text,"NO VALID CAPTURE. HOLD TALK LONGER OR INSPECT I2S. RESULT IS NOT A PASS. DRIVER=0x%X.",(unsigned)e);
                (void)orb_display_status("MICROPHONE RESULT",text);orb_wipe(text,sizeof text);orb_wipe(&stats,sizeof stats);
            }
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}
