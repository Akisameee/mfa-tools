import fs from "node:fs/promises";
import { spawn } from "node:child_process";

export async function finalizeRecording({
  ffmpeg,
  partial,
  output,
  options,
  result,
}) {
  const remuxStarted = performance.now();
  const remux = spawn(
    ffmpeg,
    [
      "-hide_banner",
      "-loglevel",
      "error",
      "-n",
      "-ss",
      String(result.warmupSeconds),
      "-i",
      partial,
      "-t",
      String(Math.min(options.seconds, result.elapsedSeconds)),
      "-c",
      "copy",
      "-movflags",
      "+faststart",
      output,
    ],
    { windowsHide: true, stdio: ["ignore", "ignore", "pipe"] },
  );
  let remuxError = "";
  remux.stderr.on("data", (data) => {
    remuxError += data;
  });
  const remuxCode = await new Promise((resolve, reject) => {
    remux.on("error", reject);
    remux.on("exit", resolve);
  });
  if (remuxCode !== 0)
    throw Error(
      `MP4 finalization failed; raw recording retained at ${partial}: ${remuxError}`,
    );
  const remuxSeconds = (performance.now() - remuxStarted) / 1000;
  await fs.unlink(partial);
  return remuxSeconds;
}
