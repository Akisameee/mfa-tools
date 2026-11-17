import { eventTime } from "./timeline.mjs";
import { characters, clickDuration, pointerMoveDuration } from "./motion.mjs";

export const INSPECTION_DURATION = 1000;
export const GLYPH_CALL_DURATION = 160;
export const DEFAULT_SPEED = 8;
export const COMPACTION_SPEED = 32;
export function animationDuration(event) {
  if (event.tool === "note")
    return (
      Math.max(130, pointerMoveDuration(event.motion)) +
      220 +
      Math.min(2400, characters(event.args.text || "").length * 65)
    );
  if (event.tool === "click") return clickDuration(event);
  return (
    {
      look: 80,
      glyph: GLYPH_CALL_DURATION,
      wait: 180,
      launch_game: 400,
    }[event.tool] ?? 180
  );
}

function segmentAt(segments, value, key) {
  let low = 0,
    high = segments.length;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (segments[middle][key] <= value) low = middle + 1;
    else high = middle;
  }
  return segments[Math.max(0, low - 1)];
}
export function viewAt(segments, source) {
  const s = segmentAt(segments, source, "sourceStart");
  return (
    s.viewStart +
    (Math.max(s.sourceStart, Math.min(s.sourceEnd, source)) - s.sourceStart) /
      s.rate
  );
}
export function sourceAt(segments, view) {
  const s = segmentAt(segments, view, "viewStart");
  return (
    s.sourceStart +
    (Math.max(s.viewStart, Math.min(s.viewEnd, view)) - s.viewStart) * s.rate
  );
}
export function rateAt(segments, source) {
  return segmentAt(segments, source, "sourceStart").rate;
}

// Continuous, invertible mapping between recorded time and screen time.
// Only thinking uses the selected speed. Every tool interval has its own fixed
// screen duration, including tools whose original calls were unusually slow.
export class TempoMap {
  constructor(events, speed = DEFAULT_SPEED, speedChanges = []) {
    const duration = eventTime(events.at(-1));
    const results = new Map(
      events.filter((e) => e.kind === "end").map((e) => [e.call, e]),
    );
    const points = new Map([
      [0, []],
      [duration, []],
    ]);
    const add = (at, change) => {
      if (!points.has(at)) points.set(at, []);
      points.get(at).push(change);
    };
    for (const change of speedChanges) add(change.at, { speed: change.speed });
    for (const event of events) {
      if (event.kind !== "begin") continue;
      const begin = eventTime(event),
        end = results.has(event.call)
          ? eventTime(results.get(event.call))
          : begin;
      if (end <= begin) continue;
      const cap =
        event.tool === "compact_context"
          ? COMPACTION_SPEED
          : (end - begin) / animationDuration(event);
      add(begin, { id: event.call, cap });
      add(end, { id: event.call });
    }
    const times = [...points.keys()].sort((a, b) => a - b),
      caps = new Map();
    this.segments = [];
    let view = 0,
      thinkingSpeed = speed;
    for (let i = 0; i < times.length - 1; i++) {
      const start = times[i],
        end = times[i + 1];
      for (const { id, cap, speed: nextSpeed } of points.get(start)) {
        if (nextSpeed !== undefined) thinkingSpeed = nextSpeed;
        else if (cap === undefined) caps.delete(id);
        else caps.set(id, cap);
      }
      const rate = caps.size ? Math.min(...caps.values()) : thinkingSpeed;
      const next = view + (end - start) / rate;
      this.segments.push({
        sourceStart: start,
        sourceEnd: end,
        viewStart: view,
        viewEnd: next,
        rate,
        thinkingSpeed,
      });
      view = next;
    }
    this.displayDuration = view;
  }
  toView(source) {
    return viewAt(this.segments, source);
  }
  toSource(view) {
    return sourceAt(this.segments, view);
  }
  rate(source) {
    return rateAt(this.segments, source);
  }
  thinkingRate(source) {
    return segmentAt(this.segments, source, "sourceStart").thinkingSpeed;
  }
}
