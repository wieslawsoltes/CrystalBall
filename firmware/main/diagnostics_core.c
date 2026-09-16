#include "diagnostics_core.h"
#include <string.h>

static uint32_t integer_sqrt(uint64_t x) {
    uint64_t result = 0, bit = UINT64_C(1) << 62;
    while (bit > x) bit >>= 2;
    while (bit) {
        if (x >= result + bit) { x -= result + bit; result = (result >> 1) + bit; }
        else result >>= 1;
        bit >>= 2;
    }
    return (uint32_t)result;
}

bool orb_diag_pattern(uint16_t *pixels, size_t count, orb_pattern_t pattern) {
    if (!pixels || count < ORB_DIAG_WIDTH * ORB_DIAG_HEIGHT ||
        pattern < ORB_PATTERN_BLACK || pattern >= ORB_PATTERN_COUNT) return false;
    const uint16_t bars[] = {0xffff, 0xffe0, 0x07ff, 0x07e0, 0xf81f, 0xf800, 0x001f, 0};
    for (unsigned y = 0; y < ORB_DIAG_HEIGHT; y++) {
        for (unsigned x = 0; x < ORB_DIAG_WIDTH; x++) {
            uint16_t value = 0;
            switch (pattern) {
                case ORB_PATTERN_WHITE: value = 0xffff; break;
                case ORB_PATTERN_RGB: value = bars[x / 40]; break;
                case ORB_PATTERN_CHECKER: value = ((x / 8 + y / 8) & 1) ? 0xffff : 0; break;
                case ORB_PATTERN_RAMP: {
                    unsigned n = x * 31 / (ORB_DIAG_WIDTH - 1);
                    value = (uint16_t)((n << 11) | ((n * 63 / 31) << 5) | n);
                    break;
                }
                default: break;
            }
            pixels[y * ORB_DIAG_WIDTH + x] = value;
        }
    }
    return true;
}

bool orb_diag_pcm_stats(const uint8_t *pcm, size_t bytes, orb_pcm_stats_t *out) {
    if (!out) return false;
    memset(out, 0, sizeof(*out));
    if (!pcm || !bytes || bytes % 2 || bytes > 128000 * 2) return false;
    int64_t sum = 0; uint64_t squares = 0; int sign = 0;
    for (size_t i = 0; i < bytes; i += 2) {
        uint32_t u = pcm[i] | ((uint32_t)pcm[i + 1] << 8);
        int32_t s = u & 0x8000 ? (int32_t)u - 65536 : (int32_t)u;
        uint32_t magnitude = (uint32_t)(s < 0 ? -s : s);
        if (magnitude > out->peak) out->peak = magnitude;
        if (s == 32767 || s == -32768) out->clipped++;
        sum += s; squares += (uint64_t)((int64_t)s * s);
        int next = s > 0 ? 1 : s < 0 ? -1 : 0;
        if (next && sign && next != sign) out->zero_crossings++;
        if (next) sign = next;
    }
    out->samples = (uint32_t)(bytes / 2);
    out->dc = (int32_t)(sum / out->samples);
    out->rms = integer_sqrt(squares / out->samples);
    return true;
}

int16_t orb_diag_tone_sample(uint32_t frame, uint32_t total) {
    static const int16_t sine[24] = {0,530,1024,1448,1774,1978,2048,1978,1774,1448,1024,530,
                                    0,-530,-1024,-1448,-1774,-1978,-2048,-1978,-1774,-1448,-1024,-530};
    if (!total || total > 24000 || frame >= total) return 0;
    uint32_t envelope = frame < 240 ? frame : 240;
    uint32_t tail = total - 1 - frame;
    if (tail < envelope) envelope = tail;
    return (int16_t)(sine[frame % 24] * (int32_t)envelope / 240);
}
