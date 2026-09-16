#include "halo.h"
#include "pins.h"
#include "driver/rmt_tx.h"
#include "driver/rmt_encoder.h"
static rmt_channel_handle_t channel;
static rmt_encoder_handle_t encoder;
static rmt_symbol_word_t symbols[16*24+1];
esp_err_t orb_halo_init(void){
    rmt_tx_channel_config_t c={.clk_src=RMT_CLK_SRC_DEFAULT,.gpio_num=PIN_LED_DATA,.mem_block_symbols=64,.resolution_hz=10000000,.trans_queue_depth=1};
    esp_err_t e=rmt_new_tx_channel(&c,&channel);if(e!=ESP_OK)return e;
    rmt_copy_encoder_config_t ec={};e=rmt_new_copy_encoder(&ec,&encoder);if(e!=ESP_OK)return e;
    e=rmt_enable(channel);return e==ESP_OK?orb_halo_rgb(0,0,0):e;
}
static esp_err_t transmit(int selected,uint8_t r,uint8_t g,uint8_t b){
    if (!channel || !encoder) return ESP_ERR_INVALID_STATE;
    /* Hard brightness cap is independent of user configuration: <=32/255/channel. */
    if (r>32) { r=32; }
    if (g>32) { g=32; }
    if (b>32) { b=32; }
    uint8_t rgb[3]={g,r,b};unsigned at=0;
    for(unsigned pixel=0;pixel<16;pixel++)for(unsigned c=0;c<3;c++)for(int bit=7;bit>=0;bit--){
        bool one=(selected<0||pixel==(unsigned)selected)&&((rgb[c]>>bit)&1);symbols[at++]=(rmt_symbol_word_t){.level0=1,.duration0=one?8:4,.level1=0,.duration1=one?5:9};
    }
    symbols[at++]=(rmt_symbol_word_t){.level0=0,.duration0=3000,.level1=0,.duration1=3000};
    rmt_transmit_config_t tc={.loop_count=0};esp_err_t e=rmt_transmit(channel,encoder,symbols,at*sizeof(symbols[0]),&tc);
    return e==ESP_OK?rmt_tx_wait_all_done(channel,500):e;
}

esp_err_t orb_halo_rgb(uint8_t r,uint8_t g,uint8_t b){return transmit(-1,r,g,b);}
esp_err_t orb_halo_pixel(unsigned index,uint8_t r,uint8_t g,uint8_t b){
    if (index>=16) return ESP_ERR_INVALID_ARG;
    return transmit((int)index,r,g,b);
}
