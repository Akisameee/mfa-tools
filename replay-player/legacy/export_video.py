# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.48", "imageio-ffmpeg>=0.6"]
# ///
"""Export the existing player, frame by frame, without real-time recording."""

import argparse
import base64
import json
import math
import os
from pathlib import Path
import subprocess
import struct
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def browser_executable():
    for path in (
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
    ):
        if path.is_file():
            return str(path)
    return None


def export(args):
    output_width = round(args.width * args.scale)
    output_height = round(args.height * args.scale)
    # Layout is independent of the physical output resolution and Windows DPI.
    # A narrower CSS viewport produces larger text and the original wrapping.
    layout_width = args.layout_width
    layout_height = layout_width * args.height / args.width
    viewport_width, viewport_height = math.ceil(layout_width), math.ceil(layout_height)
    pixel_ratio = output_width / layout_width
    output = Path(args.output).resolve()
    partial_output = output.with_name(output.stem + ".partial.mp4")
    if output.exists() or partial_output.exists():
        raise FileExistsError(f"Output already exists: {output} or {partial_output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    status_path = output.with_suffix(".progress.json")
    log_path = output.with_suffix(".ffmpeg.log")
    metadata_path = output.with_suffix(".json")
    status = {"stage": "loading", "output": str(output), "fps": args.fps,
              "width": output_width, "height": output_height,
              "viewportWidth": viewport_width, "viewportHeight": viewport_height,
              "layoutWidth": layout_width, "layoutHeight": layout_height,
              "scale": args.scale, "pixelRatio": pixel_ratio, "frames": 0}

    def report(**values):
        status.update(values)
        temporary = status_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(status_path)

    report()
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    encoder = None
    started = time.monotonic()
    try:
        with sync_playwright() as playwright, log_path.open("wb") as log:
            browser = playwright.chromium.launch(
                executable_path=browser_executable(), headless=True,
                args=["--hide-scrollbars", "--disable-background-timer-throttling", "--disable-lcd-text"],
            )
            page = browser.new_page(viewport={"width": viewport_width, "height": viewport_height},
                                    device_scale_factor=pixel_ratio)
            cdp = page.context.new_cdp_session(page)
            # Screenshot scaling is scoped to the CDP session. Apply it here as
            # well as in Playwright so captureScreenshot returns physical pixels.
            cdp.send("Emulation.setDeviceMetricsOverride", {
                "width": viewport_width, "height": viewport_height,
                "deviceScaleFactor": pixel_ratio, "mobile": False,
            })
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/", wait_until="load")
            page.wait_for_function("window.player", timeout=120000)
            page.evaluate("document.fonts.ready")
            info = page.evaluate("player.startExport()")
            seconds = min(args.seconds, info["duration"] / 1000) if args.seconds else info["duration"] / 1000
            frame_count = math.ceil(seconds * args.fps)
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            command = [
                ffmpeg, "-hide_banner", "-loglevel", "info", "-n",
                "-f", "image2pipe", "-framerate", str(args.fps), "-vcodec", "png", "-i", "pipe:0",
                "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-fps_mode", "cfr", "-frames:v", str(frame_count),
                "-movflags", "+faststart", str(partial_output),
            ]
            encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
            last_report = 0
            report(stage="rendering", totalFrames=frame_count, durationSeconds=frame_count / args.fps,
                   recording=info["recording"], plan=info["plan"])
            print(f"Exporting {frame_count} frames, {output_width}x{output_height}, {args.fps} FPS to {output}", flush=True)
            for index in range(frame_count):
                frame = page.evaluate("time => player.renderExportFrame(time)", index * 1000 / args.fps)
                screenshot = cdp.send("Page.captureScreenshot", {
                    "format": "png", "fromSurface": True, "captureBeyondViewport": False,
                    "optimizeForSpeed": True,
                    "clip": {"x": 0, "y": 0, "width": layout_width,
                             "height": layout_height, "scale": 1},
                })
                image = base64.b64decode(screenshot["data"])
                if index == 0 and struct.unpack(">II", image[16:24]) != (output_width, output_height):
                    raise RuntimeError("Browser screenshot dimensions do not match the requested video resolution")
                encoder.stdin.write(image)
                now = time.monotonic()
                completed = index + 1
                if now - last_report >= 5 or index == frame_count - 1:
                    elapsed = now - started
                    report(stage="rendering", frames=completed, elapsedSeconds=round(elapsed, 2),
                           renderFps=round(completed / elapsed, 2), sourcePosition=frame["position"])
                    print(f"{completed}/{frame_count} ({100 * completed / frame_count:.1f}%) "
                          f"{completed / elapsed:.1f} frames/s", flush=True)
                    last_report = now
                if errors:
                    raise RuntimeError("Browser rendering failed: " + "; ".join(errors))
            encoder.stdin.close()
            report(stage="encoding")
            if encoder.wait() != 0:
                raise RuntimeError(f"FFmpeg failed; see {log_path}")
            browser.close()
            partial_output.replace(output)
            report(stage="complete", bytes=output.stat().st_size,
                   elapsedSeconds=round(time.monotonic() - started, 2))
            metadata_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Saved {output}", flush=True)
    except BaseException as error:
        if encoder and encoder.poll() is None:
            if encoder.stdin and not encoder.stdin.closed:
                try:
                    encoder.stdin.close()
                except BrokenPipeError:
                    pass
            encoder.terminate()
            encoder.wait()
        report(stage="failed", error=str(error))
        raise
    finally:
        server.shutdown()
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(ROOT / "exports/1115-rec-60fps.mp4"))
    parser.add_argument("--seconds", type=float, help="Output video duration, not the recording playhead")
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--width", type=int, default=1920, help="Output width before --scale")
    parser.add_argument("--height", type=int, default=1080, help="Output height before --scale")
    parser.add_argument("--scale", type=float, default=1,
                        help="Render scale without changing layout; 2 exports 3840x2160 from the default viewport")
    parser.add_argument("--layout-width", type=float, default=1707,
                        help="CSS viewport width; controls font proportions and wrapping independently of output pixels")
    args = parser.parse_args()
    if args.fps <= 0 or args.width <= 0 or args.height <= 0 or args.width % 2 or args.height % 2:
        parser.error("FPS must be positive; width and height must be positive even numbers")
    if args.seconds is not None and args.seconds <= 0:
        parser.error("--seconds must be positive")
    if not math.isfinite(args.scale) or args.scale <= 0:
        parser.error("--scale must be finite and positive")
    if not math.isfinite(args.layout_width) or args.layout_width < 640:
        parser.error("--layout-width must be finite and at least 640 CSS pixels")
    if any(round(size * args.scale) <= 0 or round(size * args.scale) % 2 for size in (args.width, args.height)):
        parser.error("Scaled output dimensions must be positive even numbers")
    export(args)


if __name__ == "__main__":
    main()
