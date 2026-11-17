export function createControlsView(playback) {
  const $ = (s) => document.querySelector(s);
  const clock = $("#elapsed"),
    rate = $("#playback-speed"),
    toggle = $("#toggle"),
    speed = $("#speed"),
    bar = $("#playback-position");
  let lastClock, lastRate, lastPlaying, lastSelection, lastFraction;
  return {
    render() {
      const seconds = Math.floor(playback.position / 1000);
      const text =
        [
          Math.floor(seconds / 3600),
          Math.floor(seconds / 60) % 60,
          seconds % 60,
        ]
          .map((v) => String(v).padStart(2, "0"))
          .join(":") +
        `.${String(Math.floor(playback.position % 1000)).padStart(3, "0")}`;
      if (text !== lastClock) {
        clock.textContent = text;
        lastClock = text;
      }
      const value = playback.actualSpeed;
      const formatted = value
        .toFixed(value < 0.01 ? 4 : value < 1 ? 3 : 2)
        .replace(/\.?0+$/, "");
      const rateText = `${formatted}×`;
      if (rateText !== lastRate) {
        rate.textContent = rateText;
        rate.title = `当前实际倍速；思考区间 ${playback.speed}×`;
        lastRate = rateText;
      }
      if (lastPlaying !== playback.playing) {
        toggle.classList.toggle("playing", playback.playing);
        toggle.setAttribute("aria-label", playback.playing ? "暂停" : "播放");
        toggle.setAttribute("aria-pressed", String(playback.playing));
        toggle.title = `${playback.playing ? "暂停" : "播放"}（空格）`;
        lastPlaying = playback.playing;
      }
      const selection = playback.plan ? "rec" : String(playback.speed);
      if (selection !== lastSelection) {
        speed.value = selection;
        lastSelection = selection;
      }
      const fraction = Math.round(
        (playback.duration ? playback.position / playback.duration : 0) * 10000,
      );
      if (fraction !== lastFraction) {
        bar.value = String(fraction);
        bar.style.setProperty("--played", `${fraction / 100}%`);
        bar.setAttribute(
          "aria-valuetext",
          `${text}，${(fraction / 100).toFixed(1)}%`,
        );
        lastFraction = fraction;
      }
    },
  };
}
