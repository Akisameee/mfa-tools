// Runs inside our isolated Chrome tab. Captures its compositor output directly.
export async function recordPage(options) {
  const player = window.opener.player;
  if (!MediaRecorder.isTypeSupported("video/mp4;codecs=avc1"))
    throw Error(
      "This Chrome cannot record H.264 MP4 with MediaRecorder. Update Chrome.",
    );
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: {
      displaySurface: "browser",
      cursor: "never",
      width: { ideal: options.width, max: options.width },
      height: { ideal: options.height, max: options.height },
      frameRate: { ideal: options.fps, max: options.fps },
    },
    audio: false,
  });
  const track = stream.getVideoTracks()[0],
    settings = track.getSettings();
  if (
    settings.displaySurface !== "browser" ||
    settings.width !== options.width ||
    settings.height !== options.height
  ) {
    stream.getTracks().forEach((t) => t.stop());
    throw Error(
      `Unexpected capture surface or size: ${JSON.stringify(settings)}`,
    );
  }
  await track.applyConstraints({
    frameRate: { min: options.fps, ideal: options.fps, max: options.fps },
  });
  const recorder = new MediaRecorder(stream, {
    mimeType: "video/mp4;codecs=avc1",
    videoBitsPerSecond: options.bitrate,
  });
  let uploads = Promise.resolve(),
    bytes = 0,
    chunks = 0,
    error = null;
  let timer,
    stoppedBy = "duration",
    started = 0,
    mediaStarted = 0;
  const rawFrames = {
    frames: 0,
    maxGapMs: 0,
    gapsOver50ms: 0,
    gapsOver100ms: 0,
  };
  let rawReader, rawTrack, rawLoop, previousTimestamp;
  if (options.diagnostics && window.MediaStreamTrackProcessor) {
    rawTrack = track.clone();
    rawReader = new MediaStreamTrackProcessor({
      track: rawTrack,
    }).readable.getReader();
    rawLoop = (async () => {
      while (true) {
        const { value: frame, done } = await rawReader.read();
        if (done) break;
        if (started) {
          if (previousTimestamp !== undefined) {
            const gap = (frame.timestamp - previousTimestamp) / 1000;
            rawFrames.maxGapMs = Math.max(rawFrames.maxGapMs, gap);
            if (gap > 50) rawFrames.gapsOver50ms++;
            if (gap > 100) rawFrames.gapsOver100ms++;
          }
          previousTimestamp = frame.timestamp;
          rawFrames.frames++;
        }
        frame.close();
      }
    })();
  }
  const before = player.status;
  const result = new Promise((resolve, reject) => {
    recorder.ondataavailable = ({ data }) => {
      if (!data.size) return;
      bytes += data.size;
      chunks++;
      uploads = uploads
        .then(async () => {
          const response = await fetch("/__record/chunk", {
            method: "POST",
            body: data,
          });
          if (!response.ok) throw Error(await response.text());
        })
        .catch((e) => {
          error ??= e;
          stop("write-error");
        });
    };
    recorder.onerror = (event) => {
      error ??= event.error || Error("MediaRecorder failed");
      stop("recorder-error");
    };
    recorder.onstart = () => {
      // Keep the player paused until the native encoder is producing frames.
      // The launcher removes this pre-roll by copying the encoded video stream.
      started = performance.now();
      clearTimeout(timer);
      player.command("toggle");
      timer = setTimeout(() => stop("duration"), options.seconds * 1000);
    };
    recorder.onstop = async () => {
      clearTimeout(timer);
      if (player.status.playing) player.command("toggle");
      stream.getTracks().forEach((t) => t.stop());
      rawTrack?.stop();
      await rawReader?.cancel();
      await rawLoop;
      await uploads;
      try {
        if (!started)
          throw Error(
            "Recording stopped before capture was ready; playback was not started",
          );
        if (error) throw error;
        const response = await fetch("/__record/finish", { method: "POST" });
        if (!response.ok) throw Error(await response.text());
        resolve({
          mimeType: recorder.mimeType,
          videoBitsPerSecond: recorder.videoBitsPerSecond,
          capture: settings,
          elapsedSeconds: (performance.now() - started) / 1000,
          warmupSeconds: (started - mediaStarted) / 1000,
          requestedSeconds: options.seconds,
          bytes,
          chunks,
          stoppedBy,
          sourceStart: before.position,
          sourceEnd: player.status.position,
          startCursor: before.cursor,
          endCursor: player.status.cursor,
          rendering: player.status.rendering,
          rawCapture: options.diagnostics ? rawFrames : undefined,
          browser: navigator.userAgent,
          devicePixelRatio,
          layoutWidth: options.layoutWidth,
        });
      } catch (e) {
        reject(e);
      }
    };
  });
  function stop(reason = "interrupted") {
    stoppedBy = reason;
    if (recorder.state !== "inactive") recorder.stop();
  }
  track.onended = () => stop("capture-ended");
  window.__browserRecording = {
    stop,
    get status() {
      return {
        state: recorder.state,
        bytes,
        chunks,
        position: player.status.position,
        elapsedSeconds: started ? (performance.now() - started) / 1000 : 0,
      };
    },
  };
  mediaStarted = performance.now();
  recorder.start(1000);
  timer = setTimeout(() => {
    error ??= Error("Chrome capture/encoder initialization timed out");
    stop("startup-timeout");
  }, 45000);
  return result;
}
