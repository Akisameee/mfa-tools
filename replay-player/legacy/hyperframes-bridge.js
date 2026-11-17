// HyperFrames owns capture and encoding; this bridge supplies replay frames.
(() => {
  const settings = window.REPLAY_EXPORT;
  const iframe = document.querySelector("#replay-frame");
  let player, currentFrame = -1, pixelRatioScale = 1;
  const ready = new Promise((resolve, reject) => {
    const initialize = () => {
      try {
        if (iframe.contentWindow?.player) {
          player = iframe.contentWindow.player;
          const childRatio = iframe.contentWindow.devicePixelRatio || 1;
          pixelRatioScale = (window.devicePixelRatio || 1) * settings.width /
            settings.layoutWidth / childRatio;
          player.startExport({ plan: settings.plan, pixelRatioScale });
          window.removeEventListener("message", onMessage);
          resolve();
        }
      } catch (error) { reject(error); }
    };
    const onMessage = (event) => {
      if (event.source === iframe.contentWindow && event.origin === window.location.origin &&
          event.data?.type === "aliens-replay-ready") initialize();
    };
    window.addEventListener("message", onMessage);
    initialize();
  });

  function render(time) {
    const target = Math.max(0, Math.round((time + settings.start) * settings.fps));
    if (target === currentFrame) return;
    if (target < currentFrame || target - currentFrame > settings.fps * 8) {
      const warmup = Math.max(0, target - settings.fps * 8);
      player.startExport({ startTime: warmup * 1000 / settings.fps,
        plan: settings.plan, pixelRatioScale });
      currentFrame = warmup - 1;
    }
    while (currentFrame < target)
      player.renderExportFrame(++currentFrame * 1000 / settings.fps);
  }

  window.__hyperframes.registerFrameSource({
    element: document.querySelector("#composition"), ready, render,
  });
})();
