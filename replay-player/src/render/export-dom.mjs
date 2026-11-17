import { ease } from "../core/motion.mjs";

// Export owns animation time. Slow screenshots never advance these clocks.
export class ExportDom {
  constructor(document) {
    this.document = document;
    this.animations = new WeakMap();
    this.scrolls = new Map();
    this.instantScroll = false;
    this.time = 0;
  }
  requestScroll(smooth) {
    if (!smooth) this.instantScroll = true;
  }
  render(time, scrollElements) {
    this.time = time;
    // getAnimations also flushes styles so newly created CSS transitions appear.
    for (const animation of this.document.getAnimations()) {
      let state = this.animations.get(animation);
      if (!state) {
        animation.pause();
        state = {
          start: time,
          end: animation.effect.getComputedTiming().endTime,
        };
        this.animations.set(animation, state);
      }
      animation.currentTime = Math.min(time - state.start, state.end);
    }
    for (const element of scrollElements) {
      const target = Math.max(0, element.scrollHeight - element.clientHeight);
      let state = this.scrolls.get(element);
      if (!state || state.target !== target) {
        state = { from: element.scrollTop, target, start: time };
        this.scrolls.set(element, state);
      }
      element.scrollTop = this.instantScroll
        ? target
        : state.from + (target - state.from) * ease((time - state.start) / 220);
      if (this.instantScroll) state.from = target;
    }
    this.instantScroll = false;
  }
}
