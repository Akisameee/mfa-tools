import { eventTime, indexAt } from "./timeline.mjs";
import { ease, operationMotion } from "./motion.mjs";
import { animationDuration, INSPECTION_DURATION } from "./tempo.mjs";

// Every action owns its recorded call interval. TempoMap gives that interval
// enough screen time; presentation never truncates it at the following action.
export class Presentation {
  constructor(events) {
    const results = new Map(
      events.filter((e) => e.kind === "end").map((e) => [e.call, e]),
    );
    this.windows = events
      .filter((e) => e.kind === "begin" && e.motion)
      .map((event) => ({
        real: eventTime(event),
        time: eventTime(event),
        event,
        result: results.get(event.call),
        end: results.has(event.call)
          ? eventTime(results.get(event.call))
          : eventTime(event),
        nominal: animationDuration(event),
      }));
    this.inspections = events.filter(
      (e) => e.kind === "begin" && e.tool === "glyph",
    );
    this.resetInspections();
  }
  resetInspections() {
    this.inspectionTempo = null;
    this.inspectionStarts = new Map();
    this.inspectionPosition = -1;
  }
  plans() {
    return this.windows;
  }
  motion(position, tempo) {
    const plan = this.windows[indexAt(this.windows, position)];
    if (!plan) return null;
    const fullDuration = tempo.toView(plan.end) - tempo.toView(plan.real);
    const age = tempo.toView(position) - tempo.toView(plan.real);
    const duration = Math.min(plan.nominal, fullDuration);
    // If the real call was slow, keep the brief input animation at its end.
    const at = age - Math.max(0, fullDuration - duration);
    const motion = operationMotion(
      plan.event,
      position >= plan.end ? Math.max(plan.nominal, duration, at) : at,
      0,
      duration,
    );
    return {
      ...motion,
      age: at,
      hash: plan.event.args.hash,
      page: plan.event.motion.page,
      call: plan.event.call,
      opacity: 1 - ease((age - fullDuration - 1200) / 650),
    };
  }
  inspection(position, tempo, frame) {
    if (position < this.inspectionPosition) this.resetInspections();
    const now = tempo.toView(position);
    if (this.inspectionTempo && this.inspectionTempo !== tempo) {
      const oldNow = this.inspectionTempo.toView(position);
      // Preserve each effect's physical age across a thinking-speed change.
      // Include expired effects so a faster setting cannot resurrect them.
      for (const event of this.inspections) {
        if (eventTime(event) > position) break;
        const start =
          this.inspectionStarts.get(event.call) ??
          this.inspectionTempo.toView(eventTime(event));
        this.inspectionStarts.set(event.call, now - (oldNow - start));
      }
    }
    this.inspectionTempo = tempo;
    this.inspectionPosition = position;
    const effects = [];
    for (let i = indexAt(this.inspections, position); i >= 0; i--) {
      const event = this.inspections[i];
      const start =
        this.inspectionStarts.get(event.call) ?? tempo.toView(eventTime(event));
      const age = now - start;
      if (age >= INSPECTION_DURATION) break;
      this.inspectionStarts.set(event.call, start);
      const cells =
        frame && event.focus?.key && event.focus.page === frame.page
          ? frame.cells.filter((c) => c.word === event.focus.key)
          : [];
      effects.push({ age, cells, key: event.focus?.key, call: event.call });
    }
    return {
      effects,
      cells: effects.flatMap((effect) => effect.cells),
      age: effects[0]?.age ?? INSPECTION_DURATION,
    };
  }
}
