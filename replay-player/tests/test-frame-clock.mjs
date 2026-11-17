import assert from "node:assert/strict";
import { FrameClock } from "../src/core/frame-clock.mjs";
import { Playback } from "../src/core/playback.mjs";

let time = 0,
  id = 0,
  queue = new Map();
const clock = new FrameClock({
  now: () => time,
  request: (fn) => {
    queue.set(++id, fn);
    return id;
  },
  cancel: (id) => queue.delete(id),
});
const events = [
  { kind: "message", time: 0, role: "user", text: "开始" },
  { kind: "begin", time: 1000, tool: "note", call: "n", args: { text: "一" } },
  {
    kind: "end",
    time: 1200,
    tool: "note",
    call: "n",
    character: { key: "one" },
    status: "ok",
    updates: { one: "一" },
    state: 1,
  },
  { kind: "message", time: 100000, role: "assistant", text: "结束" },
];
const playback = new Playback(events, clock);
let paints = 0;
playback.onUpdate = () => paints++;
function frame(at) {
  time = at;
  const callbacks = [...queue.values()];
  queue.clear();
  assert(callbacks.length <= 1, "Only one display callback may be queued");
  for (const fn of callbacks) fn(at);
}
playback.setSpeed(1);
playback.toggle();
paints = 0;
for (let i = 1; i <= 165; i++) frame((i * 1000) / 165);
assert(
  paints >= 59 && paints <= 61,
  `60 FPS cap on a 165Hz display: ${paints}`,
);
// A stalled frame advances time/events once, without replaying stale render jobs.
const before = paints;
frame(2200);
assert.equal(paints, before + 1);
assert.equal(playback.state.writtenNotes.get("one"), "一");
assert(playback.position > 1500);
playback.toggle();
const paused = playback.position;
frame(7200);
assert.equal(playback.position, paused);
assert.equal(queue.size, 0);
playback.toggle();
frame(7300);
assert(
  Math.abs(playback.position - paused - 100) < 1e-6,
  "Paused wall time must not leak into playback",
);
playback.setSpeed(8);
const changed = playback.position;
frame(7400);
assert(
  Math.abs(playback.position - changed - 800) < 1e-6,
  "Speed changes use a fresh monotonic anchor",
);
clock.terminate();
assert.equal(queue.size, 0);
console.log(
  "Frame clock: display cadence, bounded queue, stalled frames, pause/resume and speed changes passed",
);
