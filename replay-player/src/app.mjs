import { loadReplay } from "./core/assets.mjs";
import { Playback } from "./core/playback.mjs";
import { FrameClock } from "./core/frame-clock.mjs";
import { Presentation } from "./core/presentation.mjs";
import { knownNote } from "./core/timeline.mjs";
import { createBoardView } from "./render/board-view.mjs";
import { createProgressView } from "./render/progress-view.mjs";
import { createChatView } from "./render/chat-view.mjs";
import { createControlsView } from "./render/controls-view.mjs";
import { createExportSession } from "./render/export-session.mjs";
import { createPageLayout } from "./render/page-layout.mjs";

const $ = (selector) => document.querySelector(selector);
try {
  const {
    bundle,
    plan: recordingPlan,
    atlas,
    hashGlyphs,
    callResults,
  } = await loadReplay();
  const playback = new Playback(bundle.events, new FrameClock());
  const presentation = new Presentation(bundle.events);
  let chat,
    exporter,
    lastFrame = null;
  const offline = () => exporter?.current;
  const board = createBoardView({
    bundle,
    atlas,
    playback,
    presentation,
    previewForCall: (call) => chat?.previewForCall(call),
    getOfflineExport: offline,
  });
  const progress = createProgressView({ bundle, playback });
  createPageLayout({ reflowProgress: progress.reflow });
  const controls = createControlsView(playback);
  chat = createChatView({
    bundle,
    playback,
    hashGlyphs,
    callResults,
    getBoard: () => board,
    getOfflineExport: offline,
  });
  exporter = createExportSession({ bundle, playback, recordingPlan, chat });
  $("#automatic-speed").textContent = recordingPlan.name;

  playback.onUpdate = ({ reset = false, first = 1, last = 0 }) => {
    const keys = new Set();
    let progressChanged = false;
    for (let i = first; i <= last && !reset; i++) {
      const event = bundle.events[i];
      if (event.kind !== "end") continue;
      progressChanged ||= !!event.progress;
      if (!bundle.grading)
        for (const key of Object.keys(event.updates || {})) keys.add(key);
      if (
        event.tool === "note" &&
        event.status === "ok" &&
        event.character?.key
      )
        keys.add(event.character.key);
    }
    if (reset) {
      document.body.classList.add("seeking");
      presentation.resetInspections();
      chat.reset(playback.cursor);
    } else {
      chat.advanceMessages();
      for (let i = first; i <= last; i++) chat.event(i);
    }
    chat.revealMessages();
    chat.finishTail();
    if (reset || keys.size || progressChanged)
      progress.update({ reset, keys, progress: progressChanged });
    board.invalidate({
      frame: reset || playback.state.frame !== lastFrame,
      notes: reset || keys.size > 0,
    });
    lastFrame = playback.state.frame;
    // Layout reads (scroll targets) precede canvas/timer writes.
    chat.flushScroll();
    board.draw();
    controls.render();
    if (reset)
      requestAnimationFrame(() => document.body.classList.remove("seeking"));
  };
  function command(name, value) {
    const actions = {
      toggle: () => playback.toggle(),
      previous: () => playback.step(-1),
      next: () => playback.step(1),
      previousMessage: () => playback.step(-1, true),
      nextMessage: () => playback.step(1, true),
      home: () => playback.rewind(),
      end: () => playback.jump(playback.duration),
      seekFraction: () =>
        playback.jump(playback.duration * Math.max(0, Math.min(1, value))),
      speed: () => playback.setSpeed(value),
      plan: () => playback.setPlan(recordingPlan),
    };
    actions[name]?.();
  }
  document.querySelectorAll("[data-command]").forEach((button) => {
    button.onclick = () => command(button.dataset.command);
  });
  $("#speed").onchange = (event) =>
    command(
      event.target.value === "rec" ? "plan" : "speed",
      Number(event.target.value),
    );
  $("#playback-position").oninput = (event) => {
    const fraction = Number(event.target.value) / 10000;
    playback.playing = false;
    playback.seek(playback.duration * fraction, {
      beforeFirst: fraction === 0,
    });
  };
  window.addEventListener("keydown", (event) => {
    if (
      ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) ||
      (event.target.closest("button") && [" ", "Enter"].includes(event.key))
    )
      return;
    const key = {
      " ": "toggle",
      ArrowLeft: "previous",
      ArrowRight: "next",
      Home: "home",
      End: "end",
      "[": "previousMessage",
      "]": "nextMessage",
    }[event.key];
    if (key) {
      event.preventDefault();
      command(key);
    }
    if (event.key.toLowerCase() === "f")
      document.fullscreenElement
        ? document.exitFullscreen()
        : document.documentElement.requestFullscreen();
  });
  $("#loading").hidden = true;
  playback.rewind();
  window.player = {
    seek: (value) => playback.seek(value),
    command,
    startExport: (options) => exporter.start(options),
    renderExportFrame: (time) => exporter.frame(time),
    get status() {
      return {
        position: playback.position,
        cursor: playback.cursor,
        frame: playback.state.frame,
        playing: playback.playing,
        speed: playback.speed,
        automaticSpeed: !!playback.plan,
        actualSpeed: playback.actualSpeed,
        completed: playback.state.completed,
        annotated: [...playback.state.notes.values()].filter(knownNote).length,
        progress: {
          texts: playback.state.progress.texts.length,
          questions: playback.state.progress.questions.length,
          games: playback.state.progress.games.length,
          words: progress.annotated,
        },
        motion: board.motion(),
        inspection: board.inspection(),
        elapsed: playback.position,
        duration: playback.duration,
        rendering: {
          mountedToolRows: chat.mountedRows,
          clock: "requestAnimationFrame",
          targetFps: 60,
          ...playback.clock.stats,
        },
      };
    },
    bundle,
  };
  if (window.parent !== window)
    window.parent.postMessage(
      { type: "aliens-replay-ready" },
      window.location.origin,
    );
} catch (error) {
  $("#loading").textContent = error.message;
  console.error(error);
}
