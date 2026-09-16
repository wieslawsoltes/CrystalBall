#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum { ORB_DIAG_WIDTH = 320, ORB_DIAG_HEIGHT = 240 };
typedef enum {
    ORB_PATTERN_BLACK, ORB_PATTERN_WHITE, ORB_PATTERN_RGB,
    ORB_PATTERN_CHECKER, ORB_PATTERN_RAMP, ORB_PATTERN_COUNT
} orb_pattern_t;
typedef struct {
    uint32_t samples, rms, peak, clipped, zero_crossings;
    int32_t dc;
} orb_pcm_stats_t;

/* Host-order RGB565. Refuses an undersized framebuffer without touching it. */
bool orb_diag_pattern(uint16_t *pixels, size_t count, orb_pattern_t pattern);
/* Signed 16-bit little-endian PCM; counts are digital, not calibrated SPL. */
bool orb_diag_pcm_stats(const uint8_t *pcm, size_t bytes, orb_pcm_stats_t *out);
/* Exactly 24 samples/cycle at 24 kHz; peak <=2048, no heap or floating point. */
int16_t orb_diag_tone_sample(uint32_t frame, uint32_t total);
