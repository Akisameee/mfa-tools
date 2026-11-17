import fs from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { spawn, spawnSync } from "node:child_process";
import { parseArgs } from "node:util";
import { resolveSpeedPlan } from "../src/core/speed-plan.mjs";
import { TempoMap } from "../src/core/tempo.mjs";
import { messageDuration } from "../src/core/motion.mjs";
import { messageText } from "../src/core/conversation.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);
const { values } = parseArgs({
  options: {
    seconds: { type: "string" },
    start: { type: "string", default: "0" },
    fps: { type: "string", default: "60" },
    workers: { type: "string", default: "1" },
    width: { type: "string", default: "1920" },
    height: { type: "string", default: "1080" },
    "layout-width": { type: "string", default: "1707" },
    output: { type: "string", default: "exports/1115-rec-hyperframes.mp4" },
  },
});
const fps = Number(values.fps),
  width = Number(values.width),
  height = Number(values.height),
  layoutWidth = Number(values["layout-width"]);
if (
  ![fps, width, height].every((v) => Number.isInteger(v) && v > 0) ||
  width % 2 ||
  height % 2 ||
  !Number.isFinite(layoutWidth) ||
  layoutWidth < 640
)
  throw Error("Invalid FPS, resolution or layout width");
if (
  values.seconds !== undefined &&
  !(Number.isFinite(Number(values.seconds)) && Number(values.seconds) > 0)
)
  throw Error("--seconds must be positive");
const start = Number(values.start);
if (!Number.isFinite(start) || start < 0)
  throw Error("--start must be nonnegative");
const workers = Number(values.workers);
if (!Number.isInteger(workers) || workers < 1 || workers > 24)
  throw Error("--workers must be an integer from 1 to 24");
const output = path.resolve(root, values.output);
if (existsSync(output)) throw Error(`Output already exists: ${output}`);
await fs.mkdir(path.dirname(output), { recursive: true });

async function replayInfo() {
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
  const lastText = Math.max(
    0,
    ...bundle.events
      .filter((e) => e.kind === "message")
      .map((e) => tempo.toView(e.time) + messageDuration(messageText(e))),
  );
  return {
    plan,
    recording: bundle.recording,
    duration: (Math.max(tempo.displayDuration, lastText) + 1000) / 1000,
  };
}
const info = await replayInfo();
if (start >= info.duration)
  throw Error("--start is beyond the end of the video");
const duration = Math.min(
  info.duration - start,
  Number(values.seconds ?? info.duration),
);
const layoutHeight = (layoutWidth * height) / width;
const settings = { fps, width, height, layoutWidth, start, plan: info.plan };
await fs.copyFile(
  path.join(root, "index.html"),
  path.join(root, "hyperframes-player.html"),
);
await fs.writeFile(
  path.join(root, "hyperframes.html"),
  `<!doctype html>
<html><head><meta charset="utf-8"><style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#000}
#composition{width:${width}px;height:${height}px;overflow:hidden;position:relative;background:#000}
#replay-frame{width:${layoutWidth}px;height:${layoutHeight}px;border:0;display:block;
transform:scale(${width / layoutWidth});transform-origin:0 0}
</style></head><body>
<div id="composition" data-composition-id="aliens-replay" data-width="${width}"
 data-height="${height}" data-duration="${duration}" data-fps="${fps}" data-no-timeline>
<iframe id="replay-frame" src="hyperframes-player.html"></iframe></div>
<script>window.REPLAY_EXPORT=${JSON.stringify(settings)};</script>
<script src="legacy/hyperframes-bridge.js"></script>
</body></html>`,
);

const env = { ...process.env, HYPERFRAMES_NO_TELEMETRY: "1" };
env.HYPERFRAMES_BROWSER_PATH ||= [
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
].find(existsSync);
env.HYPERFRAMES_FFPROBE_PATH ||= require("@ffprobe-installer/ffprobe").path;
if (!env.HYPERFRAMES_FFMPEG_PATH) {
  const located = spawnSync(
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
  if (located.status !== 0)
    throw Error(`FFmpeg lookup failed: ${located.stderr}`);
  env.HYPERFRAMES_FFMPEG_PATH = located.stdout.trim();
}
const cli = path.join(
  path.dirname(require.resolve("hyperframes/package.json")),
  "bin/hyperframes.mjs",
);
const started = performance.now();
const child = spawn(
  process.execPath,
  [
    cli,
    "render",
    root,
    "--composition",
    "hyperframes.html",
    "--output",
    output,
    "--fps",
    String(fps),
    "--workers",
    String(workers),
    ...(workers === 1 ? ["--low-memory-mode"] : []),
    "--experimental-fast-capture=false",
    "--quality",
    "standard",
  ],
  { cwd: root, env, stdio: "inherit", windowsHide: true },
);
const code = await new Promise((resolve, reject) => {
  child.on("error", reject);
  child.on("exit", (code) => resolve(code ?? 1));
});
if (code !== 0) process.exit(code);
await fs.writeFile(
  output.replace(/\.mp4$/i, ".json"),
  JSON.stringify(
    {
      renderer: "hyperframes",
      version: "0.9.59",
      recording: info.recording,
      fps,
      width,
      height,
      layoutWidth,
      workers,
      startSeconds: start,
      durationSeconds: duration,
      elapsedSeconds: (performance.now() - started) / 1000,
      plan: info.plan,
    },
    null,
    2,
  ),
);
console.log(`Saved ${output}`);
