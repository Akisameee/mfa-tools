import assert from "node:assert/strict";
import {
  indexAt,
  replayState,
  knownNote,
  applyEvent,
  eventTime,
} from "../src/core/timeline.mjs";
import {
  operationMotion,
  characters,
  CLICK_MIN_DURATION,
  pointerMoveDuration,
  clickDuration,
  POINTER_MAX_SPEED,
} from "../src/core/motion.mjs";
import { Playback } from "../src/core/playback.mjs";
import { Presentation } from "../src/core/presentation.mjs";
import {
  TempoMap,
  INSPECTION_DURATION,
  animationDuration,
} from "../src/core/tempo.mjs";
import {
  dividerLines,
  frameLines,
  underlineLines,
} from "../src/render/geometry.mjs";
import { annotationScore, annotationTooltip } from "../src/core/grading.mjs";
import { messageText } from "../src/core/conversation.mjs";
const escapedUser = {
  role: "user",
  text: "1\\. 目标\n\\- 使用 \\`note\\`\nC:\\notes\\file.txt\n保留 \\n",
};
assert.equal(
  messageText(escapedUser),
  "1. 目标\n- 使用 `note`\nC:\\notes\\file.txt\n保留 \\n",
);
assert(escapedUser.text.includes("1\\."));
assert.equal(
  messageText({ ...escapedUser, role: "assistant" }),
  escapedUser.text,
);
const gradeFixture = {
  lookup: {
    word: {
      早期译文: { grade: "wrong", reason: "x" },
      后来译文: { grade: "correct", reason: "y" },
      部分译文: { grade: "partial", reason: "z" },
    },
  },
};
assert.equal(
  annotationScore(gradeFixture, "word", "早期译文").status,
  "incorrect",
);
assert.equal(
  annotationScore(gradeFixture, "word", "后来译文").status,
  "correct",
);
assert.equal(annotationScore(gradeFixture, "word", "部分译文").status, "close");
assert.equal(
  annotationScore(gradeFixture, "word", "其他版本").status,
  "pending",
);
assert.equal(annotationScore(gradeFixture, "word", "?").status, "unknown");
const inputHistory = replayState([], -1);
applyEvent(inputHistory, {
  kind: "begin",
  tool: "note",
  call: "input",
  args: { text: "一" },
});
applyEvent(inputHistory, {
  kind: "end",
  tool: "note",
  call: "input",
  status: "ok",
  character: { key: "1" },
  updates: { 1: "一 (106)" },
  state: 0,
});
assert.equal(inputHistory.writtenNotes.get("1"), "一");
assert.equal(inputHistory.notes.get("1"), "一 (106)");
applyEvent(inputHistory, {
  kind: "begin",
  tool: "note",
  call: "failed-input",
  args: { text: "错译" },
});
applyEvent(inputHistory, {
  kind: "end",
  tool: "note",
  call: "failed-input",
  status: "error",
  character: { key: "1" },
  updates: {},
  state: 0,
});
assert.equal(inputHistory.writtenNotes.get("1"), "一");
applyEvent(inputHistory, {
  kind: "begin",
  tool: "note",
  call: "clear-input",
  args: { text: "" },
});
applyEvent(inputHistory, {
  kind: "end",
  tool: "note",
  call: "clear-input",
  status: "ok",
  character: { key: "1" },
  updates: { 1: "? (106)" },
  state: 0,
});
assert.equal(inputHistory.writtenNotes.get("1"), "");
const underlines = underlineLines([
  { row: 1, col: 12, underlined: true },
  { row: 1, col: 13, underlined: true },
  { row: 1, col: 15, underlined: true },
]);
assert.equal(underlines.length, 2);
assert(underlines.some((l) => l.points[0] === 12 && l.points[2] === 14));
// Two adjacent boxes share one complete edge and uninterrupted top/bottom lines.
const adjacent = frameLines({
  frames: [
    [1, 12, 1, 12],
    [1, 13, 1, 13],
  ],
  boxes: [
    [1, 12],
    [1, 13],
  ],
});
assert.equal(adjacent.filter((l) => l[0] === 13 && l[2] === 13).length, 1);
assert(adjacent.some((l) => l.join(",") === "12,1.5,14,1.5"));
assert(adjacent.some((l) => l.join(",") === "12,2.5,14,2.5"));
assert.equal(adjacent.length, 5);
const card = frameLines({ frames: [[1, 14, 2, 14]] });
assert(card.some((l) => l.join(",") === "14,1.5,14,4.5"));
// Upper and lower panels can span several rows. The separator is the upper
// edge of the lower panel, never the start of the upper panel.
for (const [lowerRow, expected] of [
  [7, null],
  [6, 3],
  [5, 4.5],
  [3, 7.5],
  [0, 12],
]) {
  const lines = dividerLines({
    center_line: 12,
    right_title: [12, 8],
    right_message_u: [12, 7],
    right_message_d: [12, lowerRow],
  });
  assert.deepEqual(lines.slice(0, 2), [
    [12, 0, 12, 13.5],
    [0, 1.5, 24, 1.5],
  ]);
  assert.deepEqual(
    lines[2],
    expected === null ? undefined : [12, expected, 24, expected],
  );
}
const events = [
  { kind: "message", time: 0, real: 0, text: "start" },
  { kind: "begin", time: 500, real: 500, tool: "note", args: { text: "猜测" } },
  {
    kind: "end",
    time: 1000,
    real: 1000,
    state: 0,
    completed: 0,
    updates: { key: "猜测" },
  },
  { kind: "begin", time: 2000, real: 2000, tool: "note", args: { text: "" } },
  {
    kind: "end",
    time: 3000,
    real: 3000,
    state: 1,
    completed: 1,
    updates: { key: "?" },
  },
];
assert.equal(indexAt(events, -1), -1);
assert.equal(eventTime({ time: 100, real: 10000 }), 100);
assert.equal(indexAt(events, 999), 1);
assert.equal(indexAt(events, 1000), 2);
assert.equal(indexAt(events, 1000), 2);
assert.equal(knownNote("?"), false);
assert.equal(knownNote("未知?"), true);
assert.equal(replayState(events, 1).notes.has("key"), false);
assert.equal(replayState(events, 2).notes.get("key"), "猜测");
assert.equal(knownNote(replayState(events, 4).notes.get("key")), false);
let incremental = replayState([], -1);
events.forEach((event) => applyEvent(incremental, event));
assert.deepEqual(incremental, replayState(events, 4));
const note = {
  tool: "note",
  args: { text: "中文👨‍👩‍👧‍👦" },
  motion: { from: [0, 0], target: [3, 4], cell: [2, 3], oldText: "旧标注" },
};
assert.equal(characters(note.args.text).length, 3);
assert.equal(operationMotion(note, 0, 0, 1000).x, 0);
const middle = operationMotion(note, 600, 0, 1000);
assert.equal(middle.text, "中");
assert.equal(middle.editing, true);
assert.equal(operationMotion(note, 1000, 0, 1000).editing, false);
assert.equal(operationMotion(note, 1000, 0, 1000).text, note.args.text);
assert.equal(operationMotion(note, 1000, 0, 1000).x, 3);
const click = { ...note, tool: "click" };
assert.equal(
  operationMotion(click, CLICK_MIN_DURATION - 1, 0, CLICK_MIN_DURATION).pressed,
  false,
);
assert.equal(
  operationMotion(click, CLICK_MIN_DURATION, 0, CLICK_MIN_DURATION).x,
  3,
);
assert.equal(
  operationMotion(click, CLICK_MIN_DURATION - 1, 0, CLICK_MIN_DURATION)
    .clickAge,
  -1,
);
// A stationary pointer still waits the full minimum. Arriving early never
// triggers a click; the press and recorded result begin together at the configured minimum.
for (const stationary of [false, true]) {
  const operation = {
    ...click,
    motion: {
      ...click.motion,
      from: stationary ? [3, 4] : [0, 0],
      target: [3, 4],
    },
  };
  const arrived = operationMotion(
    operation,
    CLICK_MIN_DURATION - 1,
    0,
    CLICK_MIN_DURATION,
  );
  assert.equal(arrived.x, 3);
  assert.equal(arrived.y, 4);
  assert.equal(arrived.pressed, false);
  assert.equal(
    operationMotion(operation, CLICK_MIN_DURATION - 1, 0, CLICK_MIN_DURATION)
      .pressed,
    false,
  );
  assert.equal(
    operationMotion(operation, CLICK_MIN_DURATION, 0, CLICK_MIN_DURATION)
      .pressed,
    true,
  );
}
// Longer trips take more time with a modest speed increase, bounded even at
// the smoothstep peak. Neither click nor note selection can precede arrival.
let previousTravel = 0,
  previousSpeed = 0;
for (const distance of [1, 5, 12, 24]) {
  const operation = {
    ...click,
    motion: { ...click.motion, from: [0, 0], target: [distance, 0] },
  };
  const travel = pointerMoveDuration(operation.motion);
  const duration = clickDuration(operation);
  assert(travel > previousTravel);
  assert(distance / travel >= previousSpeed);
  const position = (at) => operationMotion(operation, at, 0, duration).x;
  const peak = position(travel / 2 + 0.5) - position(travel / 2 - 0.5);
  assert(peak <= POINTER_MAX_SPEED + 1e-6);
  assert(position(1) - position(0) < peak);
  assert(position(travel) - position(travel - 1) < peak);
  assert.equal(position(travel), distance);
  assert(duration >= travel + 40);
  assert.equal(
    operationMotion(operation, duration - 1, 0, duration).pressed,
    false,
  );
  assert.equal(operationMotion(operation, duration, 0, duration).pressed, true);
  const editing = { ...operation, tool: "note" };
  assert.equal(
    operationMotion(editing, travel - 1, 0, animationDuration(editing)).editing,
    false,
  );
  previousTravel = travel;
  previousSpeed = distance / travel;
}
// The source clock advances through tool execution and preserves all gaps.
const clock = {
  postMessage(value) {
    this.last = value;
  },
};
const playback = new Playback(events, clock);
assert.equal(playback.speed, 8);
playback.seek(500);
playback.toggle();
clock.onmessage({
  data: { revision: clock.last.revision, position: 750, playing: true },
});
assert.equal(playback.position, 750);
assert.equal(playback.cursor, 1);
playback.setSpeed(4);
clock.onmessage({
  data: { revision: clock.last.revision - 1, position: 999, playing: true },
});
assert.equal(playback.position, 750);
playback.jump(3000);
assert.equal(playback.playing, false);
playback.jump(500);
assert.equal(playback.state.notes.has("key"), false);
// Rewinding leaves the time-zero message pending, including replay after end.
playback.rewind();
assert.equal(playback.position, 0);
assert.equal(playback.cursor, -1);
assert.equal(playback.state.frame, null);
let delivered;
playback.onUpdate = (update) => (delivered = update);
playback.toggle();
clock.onmessage({
  data: { revision: clock.last.revision, position: 0, playing: true },
});
assert.equal(delivered.first, 0);
assert.equal(delivered.last, 0);
assert.equal(playback.cursor, 0);
playback.jump(playback.duration);
playback.toggle();
assert.equal(playback.position, 0);
assert.equal(playback.cursor, -1);
assert.equal(playback.playing, true);
// Single-step navigation visits messages and tool results in recorded order,
// even when a compacted user turn has the same timestamp as an assistant reply.
const navigableEvents = [
  { kind: "message", role: "user", time: 0, text: "start" },
  { kind: "message", role: "assistant", time: 100, text: "working" },
  { kind: "begin", call: "c", tool: "look", time: 200, args: {} },
  { kind: "end", call: "c", tool: "look", time: 210, state: 0, updates: {} },
  { kind: "message", role: "assistant", time: 300, text: "done" },
  { kind: "message", role: "user", time: 300, text: "continue" },
];
const navigation = new Playback(navigableEvents, { postMessage() {} });
navigation.rewind();
for (const expected of [0, 1, 3, 4, 5]) {
  navigation.step(1);
  assert.equal(navigation.cursor, expected);
  assert.equal(navigation.playing, false);
}
for (const expected of [4, 3, 1, 0, -1]) {
  navigation.step(-1);
  assert.equal(navigation.cursor, expected);
}
navigation.step(1, true);
assert.equal(navigation.cursor, 0);
navigation.step(1, true);
assert.equal(navigation.cursor, 1);
navigation.step(1, true);
assert.equal(navigation.cursor, 4);
// Dense calls receive full screen time, with positive, continuous source rates.
const visualEvents = [
  {
    kind: "begin",
    call: "n",
    tool: "note",
    real: 100,
    args: { text: "中文字符" },
    motion: { ...note.motion, key: "k", page: "p" },
  },
  { kind: "end", call: "n", tool: "note", real: 110, status: "ok" },
  {
    kind: "begin",
    call: "n2",
    tool: "note",
    real: 115,
    args: { text: "第二个字" },
    motion: { ...note.motion, key: "k2", page: "p" },
  },
  { kind: "end", call: "n2", tool: "note", real: 120, status: "ok" },
  {
    kind: "begin",
    call: "c",
    tool: "click",
    real: 1500,
    args: { row: 1, col: 1 },
    motion: note.motion,
  },
  { kind: "end", call: "c", tool: "click", real: 1540, status: "ok" },
  { kind: "message", real: 3000, text: "done" },
];
const presentation = new Presentation(visualEvents),
  tempo = new TempoMap(visualEvents, 2);
const noteDuration = animationDuration(visualEvents[0]);
assert(Math.abs(tempo.toView(110) - tempo.toView(100) - noteDuration) < 1e-6);
assert(Math.abs(tempo.toView(120) - tempo.toView(115) - noteDuration) < 1e-6);
assert(
  Math.abs(tempo.toView(1540) - tempo.toView(1500) - CLICK_MIN_DURATION) < 1e-6,
);
assert.equal(tempo.rate(500), 2);
assert(tempo.rate(105) > 0 && tempo.rate(105) < 1);
// The source clock continues inside the slowed call; there is no catch-up jump.
const firstStart = tempo.toView(100);
const p1 = tempo.toSource(firstStart + 200),
  p2 = tempo.toSource(firstStart + 300);
assert(p1 > 100 && p2 > p1 && p2 < 110);
const mid = tempo.toSource(firstStart + noteDuration * 0.73);
const visualNote = presentation.motion(mid, tempo);
assert(visualNote.editing && visualNote.typing);
assert(visualNote.text.length > 0 && visualNote.text.length < 4);
assert.equal(presentation.motion(110, tempo).text, "中文字符");
assert.equal(presentation.motion(110, tempo).editing, false);
assert.equal(presentation.motion(115, tempo).call, "n2");
assert.equal(presentation.motion(1540, tempo).pressed, true);
for (const segment of tempo.segments) {
  assert(segment.rate > 0);
  for (const source of [
    segment.sourceStart,
    (segment.sourceStart + segment.sourceEnd) / 2,
    segment.sourceEnd,
  ])
    assert(Math.abs(tempo.toSource(tempo.toView(source)) - source) < 1e-6);
}
const failure = new Presentation(
  visualEvents.map((e) =>
    e.call === "n" && e.kind === "end" ? { ...e, status: "error" } : e,
  ),
);
assert.equal(failure.motion(110, tempo).editing, false);
// Global speed only changes waiting. Even a slow original tool call gets the
// same full screen duration, cursor phase, and shine phase at every setting.
for (const [tool, expected] of [
  ["click", CLICK_MIN_DURATION],
  ["note", noteDuration],
  ["look", 80],
  ["glyph", 160],
  ["wait", 180],
  ["launch_game", 400],
]) {
  const event = {
    kind: "begin",
    call: "fixed",
    tool,
    real: 100,
    args: { text: "中文字符" },
    focus: { page: "p", key: "k" },
  };
  if (tool === "click" || tool === "note")
    event.motion = { ...note.motion, key: "k", page: "p" };
  const fixedEvents = [
    event,
    { kind: "end", call: "fixed", tool, real: 2100, status: "ok" },
    { kind: "message", real: 5000 },
  ];
  const effects = new Presentation(fixedEvents);
  for (const speed of [0.5, 1, 2, 4, 8]) {
    const map = new TempoMap(fixedEvents, speed);
    assert(Math.abs(map.toView(2100) - map.toView(100) - expected) < 1e-6);
    assert.equal(map.rate(50), speed);
    assert.equal(map.rate(2200), speed);
    if (tool === "note") {
      const source = map.toSource(map.toView(100) + noteDuration * 0.73);
      const motion = effects.motion(source, map);
      assert(Math.abs(motion.age - noteDuration * 0.73) < 1e-6);
      assert.equal(motion.text, "中文");
    }
    if (tool === "glyph") {
      const mid = effects.inspection(1100, map, {
        page: "p",
        cells: [{ word: "k" }],
      });
      assert(Math.abs(mid.age - 80) < 1e-6);
      assert.equal(mid.cells.length, 1);
      assert.equal(
        effects.inspection(2100, map, { page: "p", cells: [{ word: "k" }] })
          .cells.length,
        1,
      );
    }
  }
}
// Glyph effects outlive their brief calls and overlap later glyphs/operations.
const parallelEvents = [
  {
    kind: "begin",
    tool: "glyph",
    call: "g1",
    real: 100,
    focus: { page: "p", key: "a" },
  },
  { kind: "end", tool: "glyph", call: "g1", real: 110 },
  {
    kind: "begin",
    tool: "glyph",
    call: "g2",
    real: 120,
    focus: { page: "p", key: "b" },
  },
  { kind: "end", tool: "glyph", call: "g2", real: 130 },
  {
    kind: "begin",
    tool: "click",
    call: "c1",
    real: 150,
    motion: note.motion,
    args: {},
  },
  { kind: "end", tool: "click", call: "c1", real: 200 },
  { kind: "message", real: 20000 },
];
const parallelFrame = { page: "p", cells: [{ word: "a" }, { word: "b" }] };
const parallelTempo = new TempoMap(parallelEvents, 2),
  parallelEffects = new Presentation(parallelEvents);
assert.equal(
  parallelEffects.inspection(160, parallelTempo, parallelFrame).effects.length,
  2,
);
const beforeSpeedChange = parallelEffects.inspection(
  200,
  parallelTempo,
  parallelFrame,
);
assert.equal(beforeSpeedChange.effects.length, 2);
const fastTempo = new TempoMap(parallelEvents, 8);
const afterSpeedChange = parallelEffects.inspection(
  200,
  fastTempo,
  parallelFrame,
);
assert.deepEqual(
  afterSpeedChange.effects.map((e) => e.age),
  beforeSpeedChange.effects.map((e) => e.age),
);
const expire = fastTempo.toSource(fastTempo.toView(200) + INSPECTION_DURATION);
assert.equal(
  parallelEffects.inspection(expire, fastTempo, parallelFrame).effects.length,
  0,
);
assert.equal(
  parallelEffects.inspection(
    expire,
    new TempoMap(parallelEvents, 16),
    parallelFrame,
  ).effects.length,
  0,
);
parallelEffects.resetInspections();
assert.equal(
  parallelEffects.inspection(125, parallelTempo, parallelFrame).effects.length,
  2,
);
// Repeated reads of the same state must not restart its transition.
const transition = replayState(events, 2);
applyEvent(transition, {
  kind: "end",
  state: 0,
  time: 350,
  completed: 0,
  updates: {},
});
assert.equal(transition.frameChangedAt.time, 1000);
console.log(
  "Timeline seeking, historical annotations, clearing, and incremental playback passed",
);

const tooltip = annotationTooltip(
  {
    lookup: {
      word: { 玩家译文: { grade: "wrong", reason: "different meanings" } },
    },
    references: {
      word: {
        english: "author key",
        meaning_raw: "author meaning",
        dictionary_text: "complete author dictionary",
      },
    },
  },
  "word",
  "玩家译文",
);
assert(tooltip.includes("译文：玩家译文"));
assert(tooltip.includes("author key"));
assert(tooltip.includes("complete author dictionary"));
assert(tooltip.includes("评分：错误"));
assert(tooltip.includes("评分理由：different meanings"));
assert(annotationTooltip(null, "word", "").includes("未标注"));

// Cache layout measurements while restoring the exact font used for drawing.
const { annotationLayout } = await import("../src/render/annotation.mjs");
let measureCalls = 0;
const measuringContext = {
  font: "",
  measureText(text) {
    measureCalls++;
    return { width: [...text].length * parseFloat(this.font) };
  },
};
const longNote = "这一条标注比较长需要换行";
const firstLayout = annotationLayout(measuringContext, longNote);
const measuredFont = measuringContext.font,
  measuredCalls = measureCalls;
measuringContext.font = "different font";
assert.deepEqual(annotationLayout(measuringContext, longNote), firstLayout);
assert.equal(measuringContext.font, measuredFont);
assert.equal(measureCalls, measuredCalls);
annotationLayout(measuringContext, longNote, 0.4);
assert(measureCalls > measuredCalls);
assert.deepEqual(characters("👨‍👩‍👧‍👦中文"), ["👨‍👩‍👧‍👦", "中", "文"]);

// Context compaction has its own speed and must not clear the current game.
const compactionEvents = [
  { kind: "message", time: 0 },
  { kind: "begin", tool: "compact_context", call: "c", time: 100 },
  {
    kind: "end",
    tool: "compact_context",
    call: "c",
    time: 32100,
    status: "ok",
  },
  { kind: "message", time: 40000 },
];
for (const speed of [0.5, 2, 8, 16]) {
  const map = new TempoMap(compactionEvents, speed);
  assert.equal(map.rate(1000), 32);
  assert(Math.abs(map.toView(32100) - map.toView(100) - 1000) < 1e-6);
  assert.equal(map.rate(35000), speed);
}
const compactState = replayState(
  [
    {
      kind: "end",
      state: 4,
      completed: 7,
      progress: { texts: ["p"], questions: [], games: [] },
      updates: { k: "标注" },
    },
    ...compactionEvents,
  ],
  compactionEvents.length,
);
assert.equal(compactState.frame, 4);
assert.equal(compactState.completed, 7);
assert.equal(compactState.notes.get("k"), "标注");
