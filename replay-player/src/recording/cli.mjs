import fs from "node:fs/promises";
import { createInterface } from "node:readline";
import { chromium } from "playwright-core";
import { recordPage } from "./browser-recorder.mjs";
import { loadRecordingSettings } from "./settings.mjs";
import { openRecordingServer } from "./local-server.mjs";
import { finalizeRecording } from "./finalize.mjs";

const wallStart = performance.now();
const {
  root,
  options,
  output,
  partial,
  executablePath,
  ffmpeg,
  plan,
  recording,
} = await loadRecordingSettings();
const server = await openRecordingServer({ root, partial });
let browser, page, controller, progressTimer;
const title = `Aliens Replay Recording ${process.pid}`;
const stop = () => {
  controller?.evaluate(() => window.__browserRecording?.stop()).catch(() => {});
};
process.on("SIGINT", stop);
const keyboard = createInterface({ input: process.stdin, crlfDelay: Infinity });
keyboard.on("line", stop);
try {
  browser = await chromium.launch({
    executablePath,
    headless: true,
    args: [
      `--auto-select-tab-capture-source-by-title=${title}`,
      "--allow-http-screen-capture",
      "--disable-background-timer-throttling",
      "--disable-renderer-backgrounding",
      "--disable-backgrounding-occluded-windows",
      "--disable-lcd-text",
      "--force-color-profile=srgb",
    ],
  });
  page = await browser.newPage({
    viewport: { width: options.width, height: options.height },
    deviceScaleFactor: 1,
  });
  const errors = [];
  page.on("pageerror", (e) => {
    errors.push(String(e));
    console.error(e.message);
  });
  await page.goto(server.url);
  await page.waitForFunction(() => window.player, null, { timeout: 120000 });
  await page.evaluate(
    async ({ title, options }) => {
      document.title = title;
      // Match the existing 1707px layout while capturing a physical 1920px tab.
      // CSS zoom keeps text vector-rasterized at the capture resolution.
      const zoom = options.width / options.layoutWidth;
      document.body.style.zoom = String(zoom);
      const screen = document.querySelector("#screen");
      screen.style.width = `${options.layoutWidth}px`;
      screen.style.height = `${options.height / zoom}px`;
      const style = document.createElement("style");
      style.textContent = `.tool-list{max-height:${options.height / zoom / 2}px}`;
      document.head.append(style);
      await document.fonts.ready;
      player.command("plan");
      player.command("home");
      if (options.sourceStart > 0) player.seek(options.sourceStart);
      await new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve)),
      );
    },
    { title, options },
  );
  const opened = page.context().waitForEvent("page");
  await page.evaluate(() => window.open("/__record/controller", "recorder"));
  controller = await opened;
  await controller.waitForLoadState();
  console.log(
    `Recording ${options.seconds.toFixed(1)}s, ${options.width}x${options.height}, requested ${options.fps} FPS, rec. Press Enter to stop and save.`,
  );
  progressTimer = setInterval(async () => {
    try {
      const status = await controller.evaluate(
        () => window.__browserRecording?.status,
      );
      if (status)
        console.log(
          `${status.elapsedSeconds.toFixed(1)} / ${options.seconds.toFixed(1)}s | ${(status.bytes / 1048576).toFixed(1)} MiB`,
        );
    } catch {
      /* Browser shutdown. */
    }
  }, 10000);
  const result = await controller.evaluate(recordPage, options);
  if (errors.length) throw Error(errors.join("\n"));
  const remuxSeconds = await finalizeRecording({
    ffmpeg,
    partial,
    output,
    options,
    result,
  });
  await fs.writeFile(
    output.replace(/\.mp4$/i, ".json"),
    JSON.stringify(
      {
        recorder: "Chrome getDisplayMedia + MediaRecorder",
        recording,
        options,
        plan,
        ...result,
        remuxSeconds,
        wallSeconds: (performance.now() - wallStart) / 1000,
        output,
      },
      null,
      2,
    ),
  );
  console.log(`Saved ${output}`);
} finally {
  clearInterval(progressTimer);
  process.removeListener("SIGINT", stop);
  keyboard.close();
  await browser?.close();
  await server.close();
}
