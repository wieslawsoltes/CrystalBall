#include "network.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_http_client.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "cJSON.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
extern const char gateway_ca_start[] asm("_binary_gateway_ca_pem_start");
static EventGroupHandle_t events;
static const orb_config_t *cfg;
#define ONLINE BIT0
#define CHECK(call) do{esp_err_t e=(call);if(e!=ESP_OK)return e;}while(0)
static void event(void *arg,esp_event_base_t base,int32_t id,void *data){
    (void)arg;(void)data;
    if(base==WIFI_EVENT&&id==WIFI_EVENT_STA_START)esp_wifi_connect();
    if(base==WIFI_EVENT&&id==WIFI_EVENT_STA_DISCONNECTED){xEventGroupClearBits(events,ONLINE);esp_wifi_connect();}
    if(base==IP_EVENT&&id==IP_EVENT_STA_GOT_IP)xEventGroupSetBits(events,ONLINE);
}
esp_err_t orb_network_init(const orb_config_t *config){
    cfg=config;events=xEventGroupCreate();if(!events)return ESP_ERR_NO_MEM;
    CHECK(esp_netif_init());CHECK(esp_event_loop_create_default());if(!esp_netif_create_default_wifi_sta())return ESP_FAIL;
    wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();CHECK(esp_wifi_init(&init));
    CHECK(esp_event_handler_register(WIFI_EVENT,ESP_EVENT_ANY_ID,event,NULL));CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,event,NULL));
    wifi_config_t w={0};memcpy(w.sta.ssid,cfg->ssid,strlen(cfg->ssid));memcpy(w.sta.password,cfg->password,strlen(cfg->password));
    w.sta.threshold.authmode=WIFI_AUTH_WPA2_PSK;w.sta.pmf_cfg.capable=true;
    CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));CHECK(esp_wifi_set_mode(WIFI_MODE_STA));CHECK(esp_wifi_set_config(WIFI_IF_STA,&w));CHECK(esp_wifi_start());
    /* SNTP starts with the network and continues on reconnect. No TLS until time is plausible. */
    esp_sntp_config_t sn=ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");esp_netif_sntp_init(&sn);
    if(!(xEventGroupWaitBits(events,ONLINE,pdFALSE,pdFALSE,pdMS_TO_TICKS(30000))&ONLINE))return ESP_ERR_TIMEOUT;
    return esp_netif_sntp_sync_wait(pdMS_TO_TICKS(30000));
}
bool orb_network_online(void){return events&&(xEventGroupGetBits(events)&ONLINE)&&time(NULL)>1735689600;}
typedef struct{uint8_t *data;size_t size,capacity;bool overflow;} buffer_t;
static esp_err_t http_event(esp_http_client_event_t *e){
    buffer_t *b=e->user_data;
    if(e->event_id==HTTP_EVENT_ON_DATA&&e->data_len>0){
        if((size_t)e->data_len>b->capacity-b->size){b->overflow=true;return ESP_ERR_NO_MEM;}
        memcpy(b->data+b->size,e->data,e->data_len);b->size+=(size_t)e->data_len;
    }
    return ESP_OK;
}
static esp_err_t post(const char *path,const char *type,const void *body,size_t count,buffer_t *result){
    if(!orb_network_online())return ESP_ERR_INVALID_STATE;
    char url[240],authorization[150];int n=snprintf(url,sizeof url,"%s%s",cfg->url,path);
    if(n<0||(size_t)n>=sizeof url)return ESP_ERR_INVALID_SIZE;
    snprintf(authorization,sizeof authorization,"Bearer %s",cfg->token);
    esp_http_client_config_t h={.url=url,.method=HTTP_METHOD_POST,.cert_pem=gateway_ca_start,
      .timeout_ms=60000,.event_handler=http_event,.user_data=result,.buffer_size=4096,
      .disable_auto_redirect=true,.keep_alive_enable=false};
    esp_http_client_handle_t c=esp_http_client_init(&h);if(!c){orb_wipe(authorization,sizeof authorization);return ESP_ERR_NO_MEM;}
    esp_err_t e=esp_http_client_set_header(c,"Authorization",authorization);
    if(e==ESP_OK)e=esp_http_client_set_header(c,"Content-Type",type);
    if(e==ESP_OK)e=esp_http_client_set_post_field(c,body,(int)count);
    if(e==ESP_OK)e=esp_http_client_perform(c);
    int status=esp_http_client_get_status_code(c);esp_http_client_cleanup(c);orb_wipe(authorization,sizeof authorization);
    if(result->overflow)return ESP_ERR_INVALID_SIZE;
    return e!=ESP_OK?e:status!=200?ESP_FAIL:ESP_OK;
}
esp_err_t orb_fortune(const uint8_t *wav,size_t bytes,char text[ORB_TEXT_MAX+1]){
    text[0]=0;uint8_t reply[4097]={0};buffer_t b={.data=reply,.capacity=sizeof reply-1};
    esp_err_t e=post("/v1/fortune","audio/wav",wav,bytes,&b);if(e!=ESP_OK)return e;
    cJSON *j=cJSON_ParseWithLength((char*)reply,b.size);if(!j)return ESP_ERR_INVALID_RESPONSE;
    const cJSON *t=cJSON_GetObjectItemCaseSensitive(j,"text");e=ESP_ERR_INVALID_RESPONSE;
    if(cJSON_IsString(t)&&t->valuestring){size_t n=strlen(t->valuestring);if(n>0&&n<=ORB_TEXT_MAX){
        bool valid=true;for(size_t i=0;i<n;i++)if((unsigned char)t->valuestring[i]<32||(unsigned char)t->valuestring[i]>126)valid=false;
        if(valid){memcpy(text,t->valuestring,n+1);e=ESP_OK;}
    }}
    cJSON_Delete(j);orb_wipe(reply,sizeof reply);return e;
}
esp_err_t orb_speech(const char *text,uint8_t **pcm,size_t *bytes){
    *pcm=NULL;*bytes=0;cJSON *j=cJSON_CreateObject();if(!j)return ESP_ERR_NO_MEM;
    cJSON_AddStringToObject(j,"text",text);char *body=cJSON_PrintUnformatted(j);cJSON_Delete(j);if(!body)return ESP_ERR_NO_MEM;
    size_t max=45*24000*2;uint8_t *out=heap_caps_malloc(max,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!out){free(body);return ESP_ERR_NO_MEM;}
    buffer_t b={.data=out,.capacity=max};esp_err_t e=post("/v1/speech","application/json",body,strlen(body),&b);
    orb_wipe(body,strlen(body));free(body);
    if(e!=ESP_OK||!b.size||b.size%2){orb_wipe(out,b.size);free(out);return e!=ESP_OK?e:ESP_ERR_INVALID_SIZE;}
    *pcm=out;*bytes=b.size;return ESP_OK;
}
