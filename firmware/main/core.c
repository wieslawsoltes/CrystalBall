#include "core.h"
#include <string.h>
#include <limits.h>
static void u16(uint8_t *p,uint16_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void u32(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
void orb_wav_header(uint8_t out[44],uint32_t samples){
    memset(out,0,44);memcpy(out,"RIFF",4);u32(out+4,36+samples*2);memcpy(out+8,"WAVEfmt ",8);
    u32(out+16,16);u16(out+20,1);u16(out+22,1);u32(out+24,16000);u32(out+28,32000);
    u16(out+32,2);u16(out+34,16);memcpy(out+36,"data",4);u32(out+40,samples*2);
}
int16_t orb_sample(int32_t raw,unsigned shift){
    if(shift>30)return 0;
    /* Division rather than signed right-shift: defined by C11 for negative samples. */
    int32_t v=raw/(int32_t)(1u<<shift);
    return v>INT16_MAX?INT16_MAX:v<INT16_MIN?INT16_MIN:(int16_t)v;
}
size_t orb_page(const char *text,size_t pos,char lines[ORB_ROWS][ORB_COLUMNS+1]){
    memset(lines,0,ORB_ROWS*(ORB_COLUMNS+1));
    if(!text)return 0;
    size_t length=strlen(text);if(pos>length)pos=length;
    for(size_t row=0;row<ORB_ROWS&&pos<length;row++){
        while(text[pos]==' ')pos++;
        size_t start=pos,end=pos,last_space=SIZE_MAX;
        while(end<length&&text[end]!='\n'&&end-start<ORB_COLUMNS){if(text[end]==' ')last_space=end;end++;}
        if(end<length&&text[end]!='\n'&&text[end]!=' '&&last_space!=SIZE_MAX&&last_space>start)end=last_space;
        size_t count=end-start;memcpy(lines[row],text+start,count);lines[row][count]=0;
        pos=end;while(text[pos]==' ')pos++;if(text[pos]=='\n')pos++;
    }
    return pos;
}
void orb_wipe(void *ptr,size_t count){volatile uint8_t *p=ptr;while(count--)*p++=0;}
bool orb_https_url(const char *url){
    if(!url||strncmp(url,"https://",8))return false;
    const char *p=url+8;if(!*p||*p=='/'||*p==':')return false;
    for(;*p;p++)if((unsigned char)*p<=32||*p=='@'||*p=='?'||*p=='#')return false;
    return true;
}
