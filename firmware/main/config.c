#include "config.h"
#include "core.h"
#include "nvs_flash.h"
#include "nvs.h"
#include <string.h>
esp_err_t orb_config_load(orb_config_t *out){
    memset(out,0,sizeof(*out));
    /* Do not silently erase NVS on a schema or flash error: provision again explicitly. */
    esp_err_t e=nvs_flash_init();if(e!=ESP_OK)return e;
    nvs_handle_t h;e=nvs_open("orb",NVS_READONLY,&h);if(e!=ESP_OK)return e;
#define READ(key,field) do {size_t n=sizeof(out->field);e=nvs_get_str(h,key,out->field,&n);if(e!=ESP_OK)goto done;}while(0)
    READ("ssid",ssid);READ("password",password);READ("url",url);READ("token",token);READ("unit",unit);
    if(!orb_https_url(out->url)||strlen(out->token)<32||!out->ssid[0])e=ESP_ERR_INVALID_ARG;
    for(const char *p=out->token;*p;p++)if((unsigned char)*p<33||(unsigned char)*p>126)e=ESP_ERR_INVALID_ARG;
done:nvs_close(h);if(e!=ESP_OK)orb_wipe(out,sizeof(*out));return e;
#undef READ
}
