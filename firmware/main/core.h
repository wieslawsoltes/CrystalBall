#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#define ORB_TEXT_MAX 400
#define ORB_COLUMNS 22
#define ORB_ROWS 10
#define ORB_SAMPLE_RATE 16000
#define ORB_WAV_HEADER 44
void orb_wav_header(uint8_t out[44], uint32_t samples);
int16_t orb_sample(int32_t raw, unsigned shift);
size_t orb_page(const char *text, size_t offset, char lines[ORB_ROWS][ORB_COLUMNS+1]);
void orb_wipe(void *ptr, size_t count);
bool orb_https_url(const char *url);
