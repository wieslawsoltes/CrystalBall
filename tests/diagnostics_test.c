#include "diagnostics_core.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
static uint16_t pixels[ORB_DIAG_WIDTH*ORB_DIAG_HEIGHT+1];
int main(void) {
    pixels[0]=123;assert(!orb_diag_pattern(NULL,76800,ORB_PATTERN_RGB));
    assert(!orb_diag_pattern(pixels,76799,ORB_PATTERN_RGB));assert(pixels[0]==123);
    assert(!orb_diag_pattern(pixels,76800,(orb_pattern_t)-1));
    pixels[76800]=1234;
    for(unsigned p=0;p<ORB_PATTERN_COUNT;p++)assert(orb_diag_pattern(pixels,76800,(orb_pattern_t)p));
    assert(pixels[76800]==1234);
    orb_diag_pattern(pixels,76800,ORB_PATTERN_BLACK);for(int i=0;i<76800;i++)assert(!pixels[i]);
    orb_diag_pattern(pixels,76800,ORB_PATTERN_WHITE);for(int i=0;i<76800;i++)assert(pixels[i]==0xffff);
    orb_diag_pattern(pixels,76800,ORB_PATTERN_RGB);assert(pixels[0]==0xffff&&pixels[200]==0xf800&&pixels[240]==0x001f&&pixels[319]==0);
    orb_diag_pattern(pixels,76800,ORB_PATTERN_CHECKER);assert(pixels[0]==0&&pixels[8]==0xffff&&pixels[8*320]==0xffff);
    orb_diag_pattern(pixels,76800,ORB_PATTERN_RAMP);assert(pixels[0]==0&&pixels[319]==0xffff);
    orb_pcm_stats_t stats;memset(&stats,255,sizeof stats);
    assert(!orb_diag_pcm_stats(NULL,2,&stats));assert(!stats.samples);
    uint8_t pcm[]={0,0,0xff,0x7f,0,0x80,0,0};
    assert(orb_diag_pcm_stats(pcm,sizeof pcm,&stats));
    assert(stats.samples==4&&stats.peak==32768&&stats.clipped==2&&stats.zero_crossings==1&&stats.dc==0&&stats.rms==23170);
    assert(!orb_diag_pcm_stats(pcm,3,&stats));assert(!stats.samples);
    assert(!orb_diag_pcm_stats(pcm,256002,&stats));assert(!orb_diag_pcm_stats(pcm,4,NULL));
    uint8_t tone[48000];
    for(uint32_t i=0;i<24000;i++){
        int16_t value=orb_diag_tone_sample(i,24000);assert(value>=-2048&&value<=2048);
        tone[i*2]=(uint8_t)value;tone[i*2+1]=(uint8_t)((uint16_t)value>>8);
    }
    assert(orb_diag_tone_sample(0,24000)==0&&orb_diag_tone_sample(23999,24000)==0);
    assert(!orb_diag_tone_sample(UINT32_MAX,24000)&&!orb_diag_tone_sample(1,UINT32_MAX));
    assert(orb_diag_pcm_stats(tone,sizeof tone,&stats));assert(stats.rms>1400&&stats.rms<1450&&stats.clipped==0&&stats.dc==0);
    assert(stats.zero_crossings>=1998&&stats.zero_crossings<=2000);
    puts("Diagnostics host tests: bounded patterns, exact RGB565, PCM statistics and gated-tone envelope passed.");
    return 0;
}
