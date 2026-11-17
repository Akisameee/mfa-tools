import { ExportDom } from "./export-dom.mjs";
import { messageDuration } from "../core/motion.mjs";
import { messageText } from "../core/conversation.mjs";
import { eventTime } from "../core/timeline.mjs";
export function createExportSession({ bundle, playback, recordingPlan, chat }) {
  let offlineExport = null;
  function startExport({
    startTime = 0,
    plan = recordingPlan,
    pixelRatioScale = 1,
  } = {}) {
    playback.playing = false;
    playback.sync();
    playback.clock.terminate();
    playback.setPlan(plan);
    offlineExport = {
      time: startTime - 1,
      dom: new ExportDom(document),
      pixelRatioScale,
    };
    playback.rewind();
    if (startTime > 0)
      playback.jump(
        playback.tempo.toSource(
          Math.min(startTime, playback.tempo.displayDuration),
        ),
      );
    document.body.classList.remove("seeking");
    document.body.classList.add("exporting");
    const lastTextEnd = Math.max(
      0,
      ...bundle.events
        .filter((event) => event.kind === "message")
        .map(
          (event) =>
            playback.tempo.toView(eventTime(event)) +
            messageDuration(messageText(event)),
        ),
    );
    return {
      recording: bundle.recording,
      plan: playback.plan,
      duration: Math.max(playback.tempo.displayDuration, lastTextEnd) + 1000,
    };
  }

  function renderExportFrame(time) {
    if (!offlineExport || time < offlineExport.time)
      throw Error("Export frames must advance in order");
    const duration = playback.tempo.displayDuration;
    const previous = offlineExport.time;
    offlineExport.time = time;
    playback.advanceTo(
      playback.tempo.toSource(Math.min(time, duration)),
      time < duration,
    );
    if (time > duration)
      chat.revealMessages(time - Math.max(previous, duration));
    offlineExport.dom.render(time, [
      ...chat.openLists(),
      document.querySelector("#conversation-scroll"),
    ]);
    return {
      position: playback.position,
      speed: playback.speed,
      cursor: playback.cursor,
    };
  }

  return {
    start: startExport,
    frame: renderExportFrame,
    get current() {
      return offlineExport;
    },
  };
}
