# Local replay player

[English](README.md) | [简体中文](README.zh-CN.md)

Private HTML/CSS/JavaScript player. No frontend framework or build step. Original
recordings are read-only; prepared data, scores, and exported videos stay local.

## Layout

```text
src/
  app.mjs           application wiring and frame invalidation
  core/             event state, time mapping, frame clock, presentation
  render/           board, virtual tool history, progress, controls
  recording/        Chrome capture and CLI implementation
  style.css         layout, fonts, colors, square sizes
recording-plan.json  rec speed schedule
index.html          player markup
serve.py            public local-server entry point
prepare.py          public data-preparation entry point
record-browser.mjs  public recording entry point

tools/              data preparation and performance benchmark
tests/              unit and browser checks
grading/            independent annotation scoring; see its README
legacy/             previous screenshot/HyperFrames exporters
data/, exports/     ignored local data and output
```

## Open

From the workspace root:

```powershell
.\message-from-aliens-mcp\.venv\Scripts\python.exe .\replay-player\serve.py
```

Open <http://127.0.0.1:8765/>. Controls and `rec` are in the clock bar.
Preparation is unnecessary when `data/replay.json` already exists.

## Record with Chrome

Install dependencies once:

```powershell
$env:PUPPETEER_SKIP_DOWNLOAD = "true"
npm --prefix .\replay-player ci
uv run --isolated --no-project --with imageio-ffmpeg python -c "import imageio_ffmpeg"
```

Record a five-minute preview:

```powershell
node .\replay-player\record-browser.mjs --seconds 300 --output exports/browser-preview-5m.mp4
```

Omit `--seconds` for the full run. Press Enter in the terminal to stop and save.
The command starts its own local server and isolated Chrome; the normal player
server need not be running. Only the player tab is captured, using
`getDisplayMedia` + `MediaRecorder`. No screenshot loop or Canvas rewrite is used.
The existing `rec` schedule is used.

Defaults: 1920×1080, requested 60 FPS, 1707px CSS layout, 16 Mbps H.264 MP4.
`--width`, `--height`, `--fps`, `--layout-width`, and `--bitrate` override these.
`--start 658.85 --seconds 15` samples output-video time, rather than the source
clock shown on screen. Output paths are relative to `replay-player`. Existing
final or partial output files are refused.

Recording takes real time plus startup/finalization. Capture and the encoder
warm up with the player paused; FFmpeg removes that pre-roll by copying the
encoded stream, without re-encoding. Chunks are written incrementally to
`.partial.mp4`; after successful finalization it is removed. Metadata is saved
beside the result as JSON. `CHROME_PATH` and `FFMPEG_PATH` select executables.

Chrome can emit variable frame rate. The JSON reports source-render timing under
`rendering`. `--diagnostics` additionally samples raw capture timestamps, allowing
rendering delays, capture gaps, and encoded-file gaps to be distinguished.
Capture diagnostics do not draw or save raw images; frames are counted and closed.

## Playback architecture

The live clock is an elapsed-time anchor sampled by `requestAnimationFrame`, capped
at 60 content updates per second. Missed display frames do not enqueue stale timer
messages, or change tool durations and the selected speed schedule.
Only the current event range is applied. The board keeps its static/effect layers.

Only changed annotation keys update the word grid. Only changed progress updates
completion grids. Historical tool calls stay in the model while at most 64 rows
per open group are mounted; scrolling up reconstructs older rows and their
recorded results. Long histories no longer accumulate thousands of preview
canvases. DOM scroll measurements are batched. Board dimensions are cached by
ResizeObserver.

A renderer can run smoothly while Chrome's capture drops frames. Benchmarks and
recording diagnostics measure these separately. Real-time recording does not
provide frame-accurate offline rendering.

## Prepare / grade

```powershell
uv run --isolated --no-project --with UnityPy --with pycryptodome python .\replay-player\prepare.py
```

Preparation selects the direct recording log when available, with legacy
subdirectories as fallback. `--recording`, `--conversation`, and `--assets`
override input selection. No game actions are replayed and no source log or
save is changed. It imports public messages, not hidden reasoning.

See [playback/data behavior](docs/playback.md) and [grading instructions](grading/README.md).

## Appearance

The progress footer keeps its natural height. The game uses the remaining height
at 16:9, which determines the left column width; chat fills the remaining width.
This is measured on resize, not during playback frames. Windows too small to fit
the fixed-size progress grids retain the intrinsic layout instead of overflowing.

Edit [src/style.css](src/style.css): `#progress --tile-size` (currently 8px),
`--tile-gap`, `--divider-space`, font sizes, and status colors. Existing visual
values are retained. Pointer/typing durations are in
[src/core/motion.mjs](src/core/motion.mjs), and time mapping in
[src/core/tempo.mjs](src/core/tempo.mjs). The `rec` schedule remains in
[recording-plan.json](recording-plan.json).

## Checks

Start `serve.py` before browser checks and the benchmark:

```powershell
npm --prefix .\replay-player test
node .\replay-player\tests\browser.mjs
.\message-from-aliens-mcp\.venv\Scripts\python.exe -m unittest discover -s replay-player/tests -p "test_*.py"
node .\replay-player\tools\benchmark-player.mjs --output artifacts/player-refactor/local.json
```

The benchmark samples early play, the waiting game, late dictionary work, and a
150-cell page. It records update intervals, long tasks, DOM counts, and browser
layout/script costs. Compare at the same viewport and machine load.
Browser checks verify bounded history, historical details, progress, notes,
message animation, seeking, controls, and the compatibility export API.

## Legacy experiments

The serial exporter is at `legacy/export_video.py`; HyperFrames is at
`legacy/export-hyperframes.mjs`. Their public player APIs remain supported, but
these screenshot-based paths are isolated from normal playback and recording.
They are retained for comparison, not selected automatically.
