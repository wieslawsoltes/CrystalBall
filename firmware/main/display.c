#include "display.h"
#include "core.h"
#include "pins.h"
#include "glyphs.h"
#include "sdkconfig.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>
#include <stdio.h>
static spi_device_handle_t dev;
static uint16_t *fb,*dma;
#define WIDTH 320
#define HEIGHT 240
#define WHITE 0xffff
#define LILAC 0xb3bf
#define CHECK(call) do{esp_err_t e=(call);if(e!=ESP_OK)return e;}while(0)
static esp_err_t transfer(const void *p,size_t n){spi_transaction_t t={.length=n*8,.tx_buffer=p};return spi_device_transmit(dev,&t);}
static esp_err_t command(uint8_t cmd,const uint8_t *data,size_t n){
    gpio_set_level(PIN_LCD_DC,0);CHECK(transfer(&cmd,1));gpio_set_level(PIN_LCD_DC,1);if(n)CHECK(transfer(data,n));return ESP_OK;
}
static void pixel(int x,int y,uint16_t c){if(x>=0&&x<WIDTH&&y>=0&&y<HEIGHT)fb[y*WIDTH+x]=c;}
static void label(int x,int y,const char *t,int scale,uint16_t c){
    for(;*t;t++,x+=6*scale){unsigned ch=(unsigned char)*t;if(ch<32||ch>127)ch='?';
      for(int yy=0;yy<7;yy++)for(int xx=0;xx<5;xx++)if(orb_glyphs[ch-32][yy]&(1u<<(4-xx)))
        for(int dy=0;dy<scale;dy++)for(int dx=0;dx<scale;dx++)pixel(x+xx*scale+dx,y+yy*scale+dy,c);
    }
}
static esp_err_t flush(void){
    uint8_t col[]={0,0,1,63},row[]={0,0,0,239};CHECK(command(0x2a,col,4));CHECK(command(0x2b,row,4));CHECK(command(0x2c,NULL,0));
    for(int y=0;y<HEIGHT;y+=4){
        for(int j=0;j<4;j++)for(int x=0;x<WIDTH;x++){
            int sx=x,sy=y+j;
#ifdef CONFIG_ORB_MIRROR_X
            sx=WIDTH-1-sx;
#endif
#ifdef CONFIG_ORB_MIRROR_Y
            sy=HEIGHT-1-sy;
#endif
            uint16_t c=fb[sy*WIDTH+sx];dma[j*WIDTH+x]=(uint16_t)((c<<8)|(c>>8));
        }
        CHECK(transfer(dma,WIDTH*4*2));
    }
    return ESP_OK;
}
esp_err_t orb_display_init(void){
    fb=heap_caps_calloc(WIDTH*HEIGHT,2,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    dma=heap_caps_malloc(WIDTH*4*2,MALLOC_CAP_DMA|MALLOC_CAP_INTERNAL);if(!fb||!dma)return ESP_ERR_NO_MEM;
    gpio_config_t g={.pin_bit_mask=(1ULL<<PIN_LCD_DC)|(1ULL<<PIN_LCD_RST)|(1ULL<<PIN_LCD_BL),.mode=GPIO_MODE_OUTPUT};CHECK(gpio_config(&g));
    gpio_set_level(PIN_LCD_BL,0);gpio_set_level(PIN_LCD_RST,0);vTaskDelay(pdMS_TO_TICKS(30));gpio_set_level(PIN_LCD_RST,1);vTaskDelay(pdMS_TO_TICKS(150));
    spi_bus_config_t b={.mosi_io_num=PIN_LCD_MOSI,.miso_io_num=-1,.sclk_io_num=PIN_LCD_SCK,.quadwp_io_num=-1,.quadhd_io_num=-1,.max_transfer_sz=WIDTH*4*2};
    CHECK(spi_bus_initialize(SPI2_HOST,&b,SPI_DMA_CH_AUTO));
    spi_device_interface_config_t d={.clock_speed_hz=10000000,.mode=0,.spics_io_num=PIN_LCD_CS,.queue_size=1};CHECK(spi_bus_add_device(SPI2_HOST,&d,&dev));
    CHECK(command(0x01,NULL,0));vTaskDelay(pdMS_TO_TICKS(150));CHECK(command(0x28,NULL,0));
    const struct{uint8_t c,n,d[16];} seq[]={
        {0xcf,3,{0x00,0xc1,0x30}},{0xed,4,{0x64,0x03,0x12,0x81}},{0xe8,3,{0x85,0x00,0x78}},
        {0xcb,5,{0x39,0x2c,0x00,0x34,0x02}},{0xf7,1,{0x20}},{0xea,2,{0,0}},
        {0xc0,1,{0x23}},{0xc1,1,{0x10}},{0xc5,2,{0x3e,0x28}},{0xc7,1,{0x86}},
        {0x36,1,{0x28}},{0x3a,1,{0x55}},{0xb1,2,{0x00,0x18}},{0xb6,3,{0x08,0x82,0x27}},
        {0xf2,1,{0}},{0x26,1,{1}},
        {0xe0,15,{0x0f,0x31,0x2b,0x0c,0x0e,0x08,0x4e,0xf1,0x37,0x07,0x10,0x03,0x0e,0x09,0x00}},
        {0xe1,15,{0x00,0x0e,0x14,0x03,0x11,0x07,0x31,0xc1,0x48,0x08,0x0f,0x0c,0x31,0x36,0x0f}}};
    for(size_t i=0;i<sizeof(seq)/sizeof(seq[0]);i++)CHECK(command(seq[i].c,seq[i].d,seq[i].n));
    CHECK(command(0x11,NULL,0));vTaskDelay(pdMS_TO_TICKS(150));CHECK(command(0x29,NULL,0));CHECK(flush());gpio_set_level(PIN_LCD_BL,1);return ESP_OK;
}
esp_err_t orb_display_status(const char *title,const char *body){
    if (!fb) { return ESP_ERR_INVALID_STATE; }
    memset(fb,0,WIDTH*HEIGHT*2);
    label(28,14,title,2,LILAC);char lines[ORB_ROWS][ORB_COLUMNS+1];orb_page(body,0,lines);
    for (int i=0;i<ORB_ROWS;i++) { label(28,44+i*17,lines[i],2,WHITE); }
    orb_wipe(lines,sizeof lines);
    return flush();
}
esp_err_t orb_display_page(const char *text,size_t offset,unsigned page){
    char heading[32];snprintf(heading,sizeof heading,"REFLECTION / %u",page);
    CHECK(orb_display_status(heading,text+offset));label(28,224,"PAGE TO CONTINUE",1,LILAC);return flush();
}
esp_err_t orb_display_calibration(void){
    memset(fb,0,WIDTH*HEIGHT*2);
    for(int x=0;x<WIDTH;x+=20)for(int y=0;y<HEIGHT;y++)pixel(x,y,0x4208);
    for(int y=0;y<HEIGHT;y+=20)for(int x=0;x<WIDTH;x++)pixel(x,y,0x4208);
    label(28,24,"LEFT 123 / RIGHT ABC",2,WHITE);label(28,108,"TELLER SEES THIS",2,LILAC);
    label(28,192,"TOP / UP ARROW ^",2,WHITE);return flush();
}
