import fs from "node:fs/promises";
import path from "node:path";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { parseArgs } from "node:util";
import { resolveSpeedPlan } from "../core/speed-plan.mjs";
import { TempoMap } from "../core/tempo.mjs";
import { messageDuration } from "../core/motion.mjs";
import { messageText } from "../core/conversation.mjs";

export async function loadRecordingSettings() {
  const root = path.resolve(
    path.dirname(fileURLToPath(import.meta.url)),
    "../..",
  );
  const { values } = parseArgs({
    options: {
      seconds: { type: "string" },
      start: { type: "string", default: "0" },
      fps: { type: "string", default: "60" },
      width: { type: "string", default: "1920" },
      height: { type: "string", default: "1080" },
      "layout-width": { type: "string", default: "1707" },
      bitrate: { type: "string", default: "16000000" },
      diagnostics: { type: "boolean", default: false },
      output: { type: "string", default: "exports/1115-rec-browser.mp4" },
    },
  });
  const options = {
    start: +values.start,
    fps: +values.fps,
    width: +values.width,
    height: +values.height,
    layoutWidth: +values["layout-width"],
    bitrate: +values.bitrate,
  };
  options.diagnostics = values.diagnostics;
  if (
    ![options.fps, options.width, options.height, options.bitrate].every(
      (v) => Number.isInteger(v) && v > 0,
    ) ||
    options.width % 2 ||
    options.height % 2 ||
    !Number.isFinite(options.layoutWidth) ||
    options.layoutWidth < 640 ||
    !Number.isFinite(options.start) ||
    options.start < 0 ||
    (values.seconds !== undefined &&
      (!Number.isFinite(+values.seconds) || +values.seconds <= 0))
  )
    throw Error("Invalid dimensions, FPS, bitrate, start time or duration");
  const output = path.resolve(root, values.output),
    partial = output.replace(/\.mp4$/i, ".partial.mp4");
  if (!/\.mp4$/i.test(output) || existsSync(output) || existsSync(partial))
    throw Error(
      "Choose a new .mp4 output (neither final nor .partial.mp4 may exist)",
    );
  const executablePath =
    process.env.CHROME_PATH ||
    [
      "C:/Program Files/Google/Chrome/Application/chrome.exe",
      "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
      path.join(
        process.env.LOCALAPPDATA || "",
        "Google/Chrome/Application/chrome.exe",
      ),
    ].find(existsSync);
  if (!executablePath)
    throw Error("Chrome not found. Install Chrome or set CHROME_PATH.");
  let ffmpeg = process.env.FFMPEG_PATH;
  if (!ffmpeg) {
    const found = spawnSync(
      "uv",
      [
        "run",
        "--offline",
        "--isolated",
        "--no-project",
        "--with",
        "imageio-ffmpeg",
        "python",
        "-c",
        "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())",
      ],
      { encoding: "utf8", windowsHide: true },
    );
    if (found.status !== 0)
      throw Error(
        "FFmpeg not found. Set FFMPEG_PATH or run the Python exporter's dependency setup.",
      );
    ffmpeg = found.stdout.trim();
  }

  const bundle = JSON.parse(
    await fs.readFile(path.join(root, "data/replay.json"), "utf8"),
  );
  const plan = resolveSpeedPlan(
    JSON.parse(
      await fs.readFile(path.join(root, "recording-plan.json"), "utf8"),
    ),
    bundle,
  );
  const tempo = new TempoMap(bundle.events, plan.defaultSpeed, plan.changes);
  const textEnd = Math.max(
    0,
    ...bundle.events
      .filter((e) => e.kind === "message")
      .map((e) => tempo.toView(e.time) + messageDuration(messageText(e))),
  );
  const fullSeconds = (Math.max(tempo.displayDuration, textEnd) + 1000) / 1000;
  if (options.start >= fullSeconds)
    throw Error("--start is past the end of the video");
  options.seconds = Math.min(
    +(values.seconds ?? fullSeconds),
    fullSeconds - options.start,
  );
  options.sourceStart = tempo.toSource(
    Math.min(options.start * 1000, tempo.displayDuration),
  );
  await fs.mkdir(path.dirname(output), { recursive: true });
  return {
    root,
    options,
    output,
    partial,
    executablePath,
    ffmpeg,
    plan,
    recording: bundle.recording,
  };
}
