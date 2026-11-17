import assert from "node:assert/strict";
import { resolveSpeedPlan } from "../src/core/speed-plan.mjs";
import { TempoMap, animationDuration } from "../src/core/tempo.mjs";
import { Playback } from "../src/core/playback.mjs";
import { messageDuration } from "../src/core/motion.mjs";
import { ExportDom } from "../src/render/export-dom.mjs";

const events = [
  { kind: "message", role: "user", text: "开始", time: 0 },
  { kind: "message", role: "assistant", text: "我会开始游戏。", time: 1000 },
  { kind: "begin", tool: "click", call: "click", time: 5000 },
  {
    kind: "end",
    tool: "click",
    call: "click",
    time: 6000,
    status: "ok",
    updates: {},
    completed: 0,
  },
  { kind: "begin", tool: "compact_context", call: "compact", time: 7000 },
  {
    kind: "end",
    tool: "compact_context",
    call: "compact",
    time: 39000,
    status: "ok",
  },
  { kind: "message", role: "user", text: "写一封回信", time: 40000 },
  { kind: "message", role: "assistant", text: "完成", time: 50000 },
];
const config = {
  recording: "test",
  defaultSpeed: 1,
  changes: [
    {
      afterMessage: { role: "assistant", occurrence: 1 },
      afterReveal: true,
      speed: 8,
    },
    { at: "00:00:05.500", speed: 32 }, // Split a tool without speeding up its animation.
    { afterMessage: { role: "user", text: "写一封回信" }, speed: 4 },
  ],
};
const bundle = { recording: "test", events };
const plan = resolveSpeedPlan(config, bundle);
assert.equal(plan.changes[0].at, 1000 + messageDuration(events[1].text));
assert.equal(plan.changes[1].at, 5500);
assert.equal(plan.changes[2].at, 40000);
const map = new TempoMap(events, plan.defaultSpeed, plan.changes);
assert.equal(map.thinkingRate(0), 1);
assert.equal(map.thinkingRate(plan.changes[0].at - 1), 1);
assert.equal(map.rate(plan.changes[0].at), 8);
assert.equal(map.thinkingRate(5500), 32);
assert.equal(map.rate(39001), 32);
assert.equal(map.rate(40000), 4);
assert(
  Math.abs(map.toView(6000) - map.toView(5000) - animationDuration(events[2])) <
    1e-6,
);
assert(Math.abs(map.toView(39000) - map.toView(7000) - 1000) < 1e-6);
for (const at of [0, 1000, 1300, 5000, 5500, 6000, 20000, 40000, 49999])
  assert(Math.abs(map.toSource(map.toView(at)) - at) < 1e-6);
assert.throws(() =>
  resolveSpeedPlan(config, { ...bundle, recording: "other" }),
);
assert.throws(() =>
  resolveSpeedPlan(
    {
      ...config,
      changes: [{ afterMessage: { role: "user", text: "不存在" }, speed: 4 }],
    },
    bundle,
  ),
);
assert.throws(() =>
  resolveSpeedPlan(
    { ...config, changes: [{ afterMessage: { role: "assistant" }, speed: 4 }] },
    bundle,
  ),
);
const clock = {
  postMessage(data) {
    this.last = data;
  },
};
const playback = new Playback(events, clock, plan);
assert.equal(playback.speed, 1);
playback.seek(45000);
assert.equal(playback.speed, 4);
playback.rewind();
assert.equal(playback.speed, 1);
playback.toggle();
clock.onmessage({
  data: { position: 45000, playing: true, revision: clock.last.revision },
});
assert.equal(playback.speed, 4);
playback.setSpeed(32);
assert.equal(playback.plan, null);
assert.equal(playback.speed, 32);
playback.setPlan(plan);
assert.equal(playback.speed, 4);
playback.rewind();
assert.equal(playback.speed, 1);
// Offline advancement delivers events incrementally, with no seek/reset.
const manual = new Playback(events, { postMessage() {} }, plan);
const updates = [];
manual.onUpdate = (update) => updates.push(update);
manual.advanceTo(1000);
manual.advanceTo(5500);
assert.equal(manual.speed, 32);
assert.equal(manual.cursor, 2);
assert(updates.every((update) => update.reset === false));
assert.throws(() => manual.advanceTo(1000));

// CSS/WAAPI animation and scrolling advance only on explicitly supplied time.
const animation = {
  paused: false,
  pause() {
    this.paused = true;
  },
  effect: { getComputedTiming: () => ({ endTime: 650 }) },
};
const dom = new ExportDom({ getAnimations: () => [animation] });
const scroller = { scrollHeight: 500, clientHeight: 100, scrollTop: 0 };
dom.render(100, [scroller]);
assert.equal(animation.currentTime, 0);
assert(animation.paused);
dom.render(210, [scroller]);
assert.equal(animation.currentTime, 110);
assert.equal(scroller.scrollTop, 200);
dom.render(320, [scroller]);
assert.equal(scroller.scrollTop, 400);
dom.render(1000, [scroller]);
assert.equal(animation.currentTime, 650);
scroller.scrollHeight = 700;
dom.requestScroll(false);
dom.render(1010, [scroller]);
assert.equal(scroller.scrollTop, 600);
console.log(
  "Speed plan: message triggers, fixed animations, compaction, inverse mapping, rewind and manual override passed",
);
