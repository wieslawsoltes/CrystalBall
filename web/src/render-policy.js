/** Bounded render-surface planning, independent of DOM and adapter implementation. */
const positive = (x, fallback) => Number.isFinite(x) && x > 0 ? x : fallback;
export function surfaceSize(width, height, dpr = 1, quality = 1, limit = 8192) {
  width = positive(width, 1); height = positive(height, 1);
  limit = Math.max(1, Math.floor(positive(limit, 8192)));
  // Cap area as well as height: ultra-wide windows otherwise allocate huge surfaces.
  const scale = Math.min(positive(dpr, 1), 1.5, 1000 / height,
    Math.sqrt(1_200_000 / width / height), limit / width, limit / height)
    * Math.min(1, positive(quality, 1));
  return {width: Math.max(1, Math.min(limit, Math.floor(width * scale))),
    height: Math.max(1, Math.min(limit, Math.floor(height * scale)))};
}

/** Scene seconds exclude paused/hidden intervals and clamp suspension discontinuities. */
export class SceneClock {
  constructor() { this.time = 0; this.last = null; }
  reset(now) { this.last = now; }
  advance(now, animate) {
    if (!Number.isFinite(now)) return this.time;
    if (this.last !== null && animate) this.time += Math.max(0, Math.min(100, now - this.last)) / 1000;
    this.last = now;
    return this.time;
  }
}

/** Hysteresis uses submission-completion latency, not a claimed GPU timer. */
export class ResolutionBudget {
  constructor() { this.quality = 1; this.reset(); }
  reset() { this.slow = 0; this.fast = 0; }
  sample(milliseconds) {
    if (!Number.isFinite(milliseconds) || milliseconds < 0) return false;
    this.slow = milliseconds > 27 ? this.slow + 1 : 0;
    this.fast = milliseconds < 12 ? this.fast + 1 : 0;
    const before = this.quality;
    if (this.slow >= 8) this.quality = Math.max(.5, Math.round((this.quality - .1) * 10) / 10);
    if (this.fast >= 120) this.quality = Math.min(1, Math.round((this.quality + .1) * 10) / 10);
    if (this.slow >= 8 || this.fast >= 120) this.reset();
    return before !== this.quality;
  }
}
