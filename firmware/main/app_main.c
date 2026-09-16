#include "audio.h"
#include "config.h"
#include "display.h"
#include "halo.h"
#include "network.h"
#include "pins.h"
#include "sdkconfig.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdlib.h>
#include <string.h>
static orb_config_t config;
static char text[ORB_TEXT_MAX+1];
static void delay(unsigned ms){vTaskDelay(pdMS_TO_TICKS(ms));}
static void wait_for_release(int pin){while(!gpio_get_level(pin))delay(20);delay(35);}
static bool pressed(int pin){if(gpio_get_level(pin))return false;delay(35);return !gpio_get_level(pin);}
static void fatal(const char *message){orb_audio_mute();(void)orb_halo_rgb(8,0,0);(void)orb_display_status("SERVICE REQUIRED",message);for(;;)delay(1000);}
void app_main(void){
    /* Never log SSIDs, tokens, audio, questions or generated text. */
    esp_log_level_set("HTTP_CLIENT",ESP_LOG_NONE);
    gpio_config_t inputs={.pin_bit_mask=(1ULL<<PIN_PTT)|(1ULL<<PIN_NEXT),.mode=GPIO_MODE_INPUT,.pull_up_en=GPIO_PULLUP_ENABLE};
    ESP_ERROR_CHECK(gpio_config(&inputs));
    ESP_ERROR_CHECK(orb_audio_init());ESP_ERROR_CHECK(orb_halo_init());ESP_ERROR_CHECK(orb_display_init());
#ifdef CONFIG_ORB_CALIBRATION_BOOT
    (void)orb_display_calibration();(void)orb_halo_rgb(0,0,0);for(;;)delay(1000);
#endif
    if(orb_config_load(&config)!=ESP_OK)fatal("NO VALID CONFIG. REMOVE DEVKIT FROM BOTH SOCKETS. PROVISION USB USING THE FACTORY TOOL.");
    (void)orb_display_status("CONNECTING","WAITING FOR WIFI AND A VALID CLOCK. MICROPHONE IS OFF.");
    /* Reconnect continues via event handler after timeout; main loop never skips TLS validation. */
    (void)orb_network_init(&config);
    (void)orb_display_status("AETHER ORB","AI ENTERTAINMENT. HOLD TALK TO RECORD. RELEASE TO ASK. PAGE CHANGES TEXT. VOICE IS OFF BY DEFAULT.");
    size_t offset=0,next=0;unsigned page=1;int64_t erase_at=0;bool disconnected=false;
    for(;;){
        /* Privacy deadline must run even while offline; never retain an old answer
           just because reconnect cannot complete. Clear immediately on disconnect. */
        if(erase_at && esp_timer_get_time() >= erase_at){
            orb_wipe(text,sizeof text);erase_at=0;offset=0;next=0;page=1;
            (void)orb_display_status("READY","LAST RESPONSE ERASED. HOLD TALK TO ASK.");
        }
        if(!orb_network_online()){
            if(!disconnected){orb_wipe(text,sizeof text);erase_at=0;offset=0;next=0;page=1;(void)orb_display_status("OFFLINE","CHECK WIFI, DNS AND CLOCK. NO AUDIO IS RECORDED OR QUEUED.");disconnected=true;}
            (void)orb_halo_rgb(6,2,0);delay(500);continue;
        }
        if(disconnected){(void)orb_display_status("READY","HOLD TALK TO ASK. AI ENTERTAINMENT ONLY.");disconnected=false;}
        if(pressed(PIN_PTT)){
            orb_wipe(text,sizeof text);erase_at=0;offset=0;next=0;page=1;
            (void)orb_display_status("RECORDING","RELEASE TALK TO SEND. MAXIMUM EIGHT SECONDS. RED PANEL LED INDICATES CAPTURE.");(void)orb_halo_rgb(6,0,1);
            uint8_t *wav=NULL;size_t bytes=0;esp_err_t e=orb_audio_record(&wav,&bytes);
            wait_for_release(PIN_PTT);
            if(e==ESP_OK){
                (void)orb_display_status("CONSULTING","MICROPHONE IS OFF. REQUESTING AN AI-GENERATED REFLECTION.");(void)orb_halo_rgb(3,0,12);
                e=orb_fortune(wav,bytes,text);orb_wipe(wav,bytes);free(wav);
            }
            if(e==ESP_OK){
                char lines[ORB_ROWS][ORB_COLUMNS+1];next=orb_page(text,0,lines);orb_wipe(lines,sizeof lines);
                (void)orb_display_page(text,0,page);erase_at=esp_timer_get_time()+(int64_t)CONFIG_ORB_AUTO_ERASE_SECONDS*1000000;
                (void)orb_halo_rgb(1,0,3);
#ifdef CONFIG_ORB_PUBLIC_TTS
                uint8_t *pcm=NULL;size_t pcm_bytes=0;
                if(orb_speech(text,&pcm,&pcm_bytes)==ESP_OK){(void)orb_audio_play(pcm,pcm_bytes);orb_wipe(pcm,pcm_bytes);free(pcm);wait_for_release(PIN_PTT);}
#endif
            }else{
                (void)orb_display_status("PLEASE TRY AGAIN","RECORD AT LEAST HALF A SECOND. CHECK NETWORK AND GATEWAY. NOTHING WAS SAVED ON THE ORB.");(void)orb_halo_rgb(7,1,0);
            }
        }
        if(pressed(PIN_NEXT)){
            wait_for_release(PIN_NEXT);
            if(text[0]){if(next>=strlen(text)){offset=0;page=1;}else{offset=next;page++;}
                char lines[ORB_ROWS][ORB_COLUMNS+1];next=orb_page(text,offset,lines);orb_wipe(lines,sizeof lines);(void)orb_display_page(text,offset,page);}
        }
        if(!text[0]){unsigned phase=(unsigned)(esp_timer_get_time()/200000)%24;unsigned glow=phase<12?phase:24-phase;(void)orb_halo_rgb(2+glow/3,0,4+glow);}
        delay(35);
    }
}
