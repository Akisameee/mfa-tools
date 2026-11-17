import { applyEvent, eventTime, indexAt, replayState } from "./timeline.mjs";
import { TempoMap, DEFAULT_SPEED } from "./tempo.mjs";

// Recorded time remains the playhead. TempoMap changes its rate through each
// segment; the worker keeps advancing while controls have focus.
export class Playback {
  constructor(events, clock, plan = null) {
    this.events = events;
    this.clock = clock;
    this.duration = eventTime(events.at(-1));
    this.position = 0;
    this.cursor = -1;
    this.state = replayState([], -1);
    this.playing = false;
    this.plan = plan;
    this.tempo = new TempoMap(
      events,
      plan?.defaultSpeed ?? DEFAULT_SPEED,
      plan?.changes,
    );
    this.revision = 0;
    this.onUpdate = () => {};
    clock.onmessage = ({ data }) => {
      if (data.revision !== this.revision || !this.playing) return;
      this.advanceTo(data.position, data.playing);
    };
  }
  advanceTo(position, playing = true) {
    if (position < this.position)
      throw Error("Incremental playback cannot run backwards");
    const first = this.cursor + 1;
    this.position = Math.min(this.duration, position);
    const next = indexAt(this.events, this.position);
    while (this.cursor < next)
      applyEvent(this.state, this.events[++this.cursor]);
    this.playing = playing;
    this.onUpdate({ reset: false, first, last: this.cursor, force: !playing });
  }
  sync() {
    this.clock.postMessage({
      position: this.position,
      playing: this.playing,
      speed: this.speed,
      duration: this.duration,
      segments: this.tempo.segments,
      revision: ++this.revision,
    });
  }
  seek(value, { beforeFirst = false, eventIndex = null } = {}) {
    this.position = Math.max(0, Math.min(this.duration, value));
    this.cursor = beforeFirst
      ? -1
      : Number.isInteger(eventIndex)
        ? Math.max(-1, Math.min(this.events.length - 1, eventIndex))
        : indexAt(this.events, this.position);
    this.state = replayState(this.events, this.cursor);
    this.sync();
    this.onUpdate({ reset: true, first: 0, last: this.cursor, force: true });
  }
  rewind() {
    this.playing = false;
    // Time-zero messages must still be delivered as live events on play.
    this.seek(0, { beforeFirst: true });
  }
  toggle() {
    if (!this.playing && this.position >= this.duration) this.rewind();
    this.playing = !this.playing;
    this.sync();
    this.onUpdate({ first: 1, last: 0, force: true });
  }
  setSpeed(value) {
    if (!Number.isFinite(value) || value <= 0) return;
    this.plan = null;
    this.tempo = new TempoMap(this.events, value);
    this.sync();
    this.onUpdate({ first: 1, last: 0, force: true });
  }
  setPlan(plan) {
    this.plan = plan;
    this.tempo = new TempoMap(this.events, plan.defaultSpeed, plan.changes);
    this.sync();
    this.onUpdate({ first: 1, last: 0, force: true });
  }
  get speed() {
    return this.tempo.thinkingRate(this.position);
  }
  jump(value, options) {
    this.playing = false;
    this.seek(value, options);
  }
  get actualSpeed() {
    return this.tempo.rate(this.position);
  }
  step(direction, onlyMessages = false) {
    let next = this.cursor + direction;
    while (next >= 0 && next < this.events.length) {
      const kind = this.events[next].kind;
      if (kind === "message" || (!onlyMessages && kind === "end")) {
        // Idle cuts can put the assistant reply and following user message at
        // the same time. Keep their individual positions in the event stream.
        this.jump(eventTime(this.events[next]), { eventIndex: next });
        return;
      }
      next += direction;
    }
    if (direction > 0) this.jump(this.duration);
    else this.rewind();
  }
}
