#include "core.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
static unsigned le32(const unsigned char *p){return p[0]|((unsigned)p[1]<<8)|((unsigned)p[2]<<16)|((unsigned)p[3]<<24);}
int main(void){
    unsigned char wav[44];orb_wav_header(wav,128000);
    assert(!memcmp(wav,"RIFF",4));assert(!memcmp(wav+8,"WAVEfmt ",8));
    assert(le32(wav+4)==256036);assert(le32(wav+24)==16000);assert(le32(wav+40)==256000);
    assert(orb_sample(INT32_MAX,14)==INT16_MAX);assert(orb_sample(INT32_MIN,14)==INT16_MIN);
    assert(orb_sample(-32768,1)==-16384);assert(orb_sample(1234,31)==0);
    char input[402],lines[ORB_ROWS][ORB_COLUMNS+1];memset(input,'A',400);input[400]=0;
    size_t pos=0,pages=0;while(pos<400){size_t next=orb_page(input,pos,lines);assert(next>pos);assert(next<=400);pos=next;pages++;for(int i=0;i<ORB_ROWS;i++)assert(strlen(lines[i])<=ORB_COLUMNS);}
    assert(pages==2);assert(orb_page(NULL,0,lines)==0);assert(orb_page("word",SIZE_MAX,lines)==4);
    assert(orb_page("hello\nworld",0,lines)==11);assert(!strcmp(lines[0],"hello"));assert(!strcmp(lines[1],"world"));
    orb_wipe(input,sizeof input);for(size_t i=0;i<sizeof input;i++)assert(input[i]==0);
    assert(orb_https_url("https://orb.local"));assert(!orb_https_url("http://orb.local"));
    assert(!orb_https_url("https://user@orb.local"));assert(!orb_https_url("https://orb.local#fragment"));
    puts("Firmware host core: WAV, clipping, pagination, erasure and URL checks passed.");
    return 0;
}
