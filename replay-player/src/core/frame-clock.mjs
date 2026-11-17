import { viewAt, sourceAt, rateAt } from "./tempo.mjs";

// An anchor plus elapsed time, rather than a queue of timer messages.
export class FrameClock {
  constructor({
    fps = 60,
    now = () => performance.now(),
    request = (callback) => requestAnimationFrame(callback),
    cancel = (id) => cancelAnimationFrame(id),
  } = {}) {
    Object.assign(this, { fps, now, request, cancel });
    this.onmessage = () => {};
    this.pending = null;
    this.state = null;
    this.lastFrame = -Infinity;
    this.stats = { frames: 0, maxGapMs: 0, gapsOver25ms: 0 };
  }
  postMessage(state) {
    if (this.closed) return;
    if (state.playing && !this.state?.playing) {
      this.stats = { frames: 0, maxGapMs: 0, gapsOver25ms: 0 };
      this.lastPaint = null;
    }
    this.state = state;
    this.anchor = this.now();
    this.anchorView = state.segments.length
      ? viewAt(state.segments, state.position)
      : 0;
    this.lastFrame = this.anchor - 1000 / this.fps;
    if (state.playing && this.pending === null)
      this.pending = this.request((t) => this.tick(t));
    if (!state.playing && this.pending !== null) {
      this.cancel(this.pending);
      this.pending = null;
    }
  }
  tick(timestamp) {
    this.pending = null;
    const state = this.state;
    if (this.closed || !state?.playing || !state.segments.length) return;
    const interval = 1000 / this.fps;
    if (timestamp - this.lastFrame >= interval - 0.1) {
      if (this.lastPaint !== null && this.lastPaint !== undefined) {
        const gap = timestamp - this.lastPaint;
        this.stats.maxGapMs = Math.max(this.stats.maxGapMs, gap);
        if (gap > 25) this.stats.gapsOver25ms++;
      }
      this.lastPaint = timestamp;
      this.stats.frames++;
      this.lastFrame +=
        Math.max(1, Math.floor((timestamp - this.lastFrame + 0.1) / interval)) *
        interval;
      const position = sourceAt(
        state.segments,
        this.anchorView + Math.max(0, timestamp - this.anchor),
      );
      if (position >= state.duration) state.playing = false;
      this.onmessage({
        data: {
          position,
          playing: state.playing,
          actualSpeed: rateAt(state.segments, position),
          revision: state.revision,
        },
      });
    }
    if (this.state?.playing && !this.closed && this.pending === null)
      this.pending = this.request((t) => this.tick(t));
  }
  terminate() {
    this.closed = true;
    if (this.pending !== null) this.cancel(this.pending);
    this.pending = null;
  }
}
