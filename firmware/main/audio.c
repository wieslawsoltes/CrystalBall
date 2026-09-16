#include "audio.h"
#include "diagnostics_core.h"
#include "esp_timer.h"
#include "core.h"
#include "pins.h"
#include "sdkconfig.h"
#include "driver/i2s_std.h"
#include "driver/gpio.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdlib.h>
#include <string.h>
static i2s_chan_handle_t rx,tx;
#define CHECK(call) do{esp_err_t e=(call);if(e!=ESP_OK)return e;}while(0)
void orb_audio_mute(void){gpio_set_level(PIN_AMP_SD,0);gpio_set_level(PIN_REC_LED,0);}
esp_err_t orb_audio_init(void){
    gpio_config_t g={.pin_bit_mask=(1ULL<<PIN_REC_LED)|(1ULL<<PIN_AMP_SD),.mode=GPIO_MODE_OUTPUT};CHECK(gpio_config(&g));orb_audio_mute();
    i2s_chan_config_t r=I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0,I2S_ROLE_MASTER);r.dma_desc_num=4;r.dma_frame_num=128;
    CHECK(i2s_new_channel(&r,NULL,&rx));
    i2s_std_config_t rs={
      .clk_cfg=I2S_STD_CLK_DEFAULT_CONFIG(16000),
      .slot_cfg=I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT,I2S_SLOT_MODE_STEREO),
      .gpio_cfg={.mclk=I2S_GPIO_UNUSED,.bclk=PIN_MIC_BCLK,.ws=PIN_MIC_WS,.dout=I2S_GPIO_UNUSED,.din=PIN_MIC_SD}};
    CHECK(i2s_channel_init_std_mode(rx,&rs));
    i2s_chan_config_t t=I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_1,I2S_ROLE_MASTER);t.dma_desc_num=4;t.dma_frame_num=128;
    CHECK(i2s_new_channel(&t,&tx,NULL));
    i2s_std_config_t ts={
      .clk_cfg=I2S_STD_CLK_DEFAULT_CONFIG(24000),
      .slot_cfg=I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT,I2S_SLOT_MODE_STEREO),
      .gpio_cfg={.mclk=I2S_GPIO_UNUSED,.bclk=PIN_AMP_BCLK,.ws=PIN_AMP_WS,.dout=PIN_AMP_DIN,.din=I2S_GPIO_UNUSED}};
    return i2s_channel_init_std_mode(tx,&ts);
}
esp_err_t orb_audio_record(uint8_t **wav,size_t *bytes){
    *wav=NULL;*bytes=0;const size_t limit=ORB_SAMPLE_RATE*CONFIG_ORB_RECORD_SECONDS;
    uint8_t *buf=heap_caps_malloc(44+limit*2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);if(!buf)return ESP_ERR_NO_MEM;
    gpio_set_level(PIN_REC_LED,1);esp_err_t e=i2s_channel_enable(rx);
    if(e!=ESP_OK){gpio_set_level(PIN_REC_LED,0);free(buf);return e;}
    int32_t raw[256],old_x=0,old_y=0;size_t count=0,warm=0;
    while(count<limit&&!gpio_get_level(PIN_PTT)){
        size_t got=0;e=i2s_channel_read(rx,raw,sizeof(raw),&got,250);if(e!=ESP_OK)break;
        for(size_t i=0;i+1<got/sizeof(int32_t)&&count<limit;i+=2){
            if(warm++<1600)continue; /* 100 ms microphone clock-start settling. */
            int32_t x=orb_sample(raw[i],CONFIG_ORB_MIC_SHIFT);
            int32_t y=x-old_x+(old_y*255)/256;old_x=x;old_y=y;
            int16_t v=y>32767?32767:y<-32768?-32768:(int16_t)y;
            buf[44+count*2]=(uint8_t)v;buf[45+count*2]=(uint8_t)((uint16_t)v>>8);count++;
        }
    }
    (void)i2s_channel_disable(rx);gpio_set_level(PIN_REC_LED,0);orb_wipe(raw,sizeof raw);
    if(e!=ESP_OK||count<4800){orb_wipe(buf,44+limit*2);free(buf);return e==ESP_OK?ESP_ERR_INVALID_SIZE:e;}
    orb_wav_header(buf,(uint32_t)count);*wav=buf;*bytes=44+count*2;return ESP_OK;
}
esp_err_t orb_audio_play(const uint8_t *pcm,size_t bytes){
    if(!pcm||!bytes||bytes%2)return ESP_ERR_INVALID_SIZE;
    esp_err_t e=i2s_channel_enable(tx);if(e!=ESP_OK)return e;
    int16_t stereo[512]={0};size_t sent=0;
    /* Clock and zeros before enabling amplifier; digital volume fixed at 25%. */
    e=i2s_channel_write(tx,stereo,sizeof stereo,&sent,500);
    if(e==ESP_OK)gpio_set_level(PIN_AMP_SD,1);
    for(size_t off=0;e==ESP_OK&&off<bytes;){
        if(!gpio_get_level(PIN_PTT)){e=ESP_ERR_INVALID_STATE;break;}
        size_t n=(bytes-off)/2;if(n>256)n=256;
        for(size_t i=0;i<n;i++){uint16_t u=pcm[off+i*2]|((uint16_t)pcm[off+i*2+1]<<8);int32_t v=(u&0x8000)?(int32_t)u-65536:(int32_t)u;stereo[i*2]=stereo[i*2+1]=(int16_t)(v/4);}
        size_t done=0;while(done<n*4&&e==ESP_OK){sent=0;e=i2s_channel_write(tx,(uint8_t*)stereo+done,n*4-done,&sent,1000);if(!sent&&e==ESP_OK)e=ESP_ERR_TIMEOUT;done+=sent;}
        off+=n*2;
    }
    if(e==ESP_OK){memset(stereo,0,sizeof stereo);(void)i2s_channel_write(tx,stereo,sizeof stereo,&sent,500);vTaskDelay(pdMS_TO_TICKS(80));}
    gpio_set_level(PIN_AMP_SD,0);(void)i2s_channel_disable(tx);orb_wipe(stereo,sizeof stereo);return e;
}

esp_err_t orb_audio_test_tone(void) {
    if (gpio_get_level(PIN_PTT)) return ESP_ERR_INVALID_STATE;
    esp_err_t e=i2s_channel_enable(tx);if(e!=ESP_OK)return e;
    int16_t stereo[256]={0};size_t sent=0;
    e=i2s_channel_write(tx,stereo,sizeof stereo,&sent,100);
    if(e==ESP_OK && sent!=sizeof stereo)e=ESP_ERR_TIMEOUT;
    if(e==ESP_OK)gpio_set_level(PIN_AMP_SD,1);
    const uint32_t total=24000;uint32_t frame=0;
    const int64_t deadline=esp_timer_get_time()+1000000;
    while(e==ESP_OK&&frame<total&&!gpio_get_level(PIN_PTT)&&esp_timer_get_time()<deadline){
        uint32_t n=total-frame;if(n>128)n=128;
        for(uint32_t i=0;i<n;i++)stereo[i*2]=stereo[i*2+1]=orb_diag_tone_sample(frame+i,total);
        sent=0;e=i2s_channel_write(tx,stereo,n*4,&sent,100);
        if(e==ESP_OK&&sent!=n*4)e=ESP_ERR_TIMEOUT;
        frame+=n;
    }
    gpio_set_level(PIN_AMP_SD,0);(void)i2s_channel_disable(tx);
    orb_wipe(stereo,sizeof stereo);return e;
}
