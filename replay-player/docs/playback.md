# Playback behavior and data preparation

### Automatic recording speeds

Open the regular player and select `rec` in the speed dropdown for the fixed
schedule in [`recording-plan.json`](recording-plan.json). The configuration loads
directly on page load; its `name` field supplies the dropdown label. No special
URL or separate page is needed. The player opens paused, ready for OBS.
For recording `1115`, thinking starts at 1×, changes to 8× after the first assistant
reply finishes appearing, to 32× at `03:05:34.979` (dictionary corrections), and to
4× when the final user request to write a reply appears. All timestamps use the
player's recording timer, not the output video's elapsed time. Message triggers
match the transcript; a missing or ambiguous match stops loading with an error.

The speed selector shows `rec` while the plan is active. Choosing a numeric speed
overrides the schedule; selecting `rec` restores it at the current playhead.
Seeking and rewinding automatically select the appropriate scheduled speed.
The regular URL retains the default manual 8× setting, with 32× also available.
Tool animation durations stay fixed, and compaction stays at 32× in both modes.
`look` (table or screenshot) always takes 80ms of screen time. The `rec` schedule
also uses 32× from `00:36:02.746` to `00:41:42.275`, then restores 8×, to shorten
the long silent gap between two look calls.
OBS can load the regular URL directly as a browser source, at 1920×1080 and
60 FPS. Start OBS recording before pressing play; stop after the final message
has finished appearing.

The capture view contains only the reconstructed game, progress squares, and
user/model conversation and tool groups. Its compact top bar puts the timer on
the left, then actual speed, with previous / play-pause / next controls and a
thinking-speed selector on the right. A slim overall playback progress bar fills
the center; click, drag, or use its arrow keys to seek. Seeking pauses playback
and updates the board, conversation, timer, and progress together. There is no
separate control page. Press `F` for browser fullscreen.

Keyboard shortcuts in the capture view:

| Key | Action |
| --- | --- |
| Space | Play/pause |
| Left / Right | Previous / next user message, assistant message, or completed tool call |
| `[` / `]` | Previous / next conversation message |
| Home / End | Start / finish |
| F | Toggle fullscreen |

The inline thinking-speed selector defaults to 8×. Keyboard shortcuts also
support stepping through messages and completed calls together, jumping between
messages only, and seeking to the start/end. Each user and assistant message is
an individual event. Events sharing a timestamp remain separate navigation
stops, including replies and user messages joined by removal of an idle wait.
Playback preserves thinking gaps and tool execution intervals. Only idle waits
between a completed assistant turn and the next user message are removed.
Explicit final replies and logged turn completion/abort signals identify those
waits, including quota stops without a final reply. Active tools and user
interruptions are retained. Playback opens paused at time zero, before the first
event. Pressing play sends the initial user message with the same progressive
reveal as later user and assistant messages. Home and replay after the end
return to this point; no message or game state is prefilled.
The playback clock runs in a Worker, so switching tabs
does not pause it. Browser suspension or closing the capture page stops execution.
The top-right timer is the recording playhead and advances continuously while
playing, including during tool execution. Only thinking/waiting between calls
uses the selected speed. Every tool call has a fixed screen duration independent
of that setting, even at 8× or 0.5×.
The timer includes milliseconds, and its actual current speed appears beside it.
Context compactions appear as independent `压缩上下文` cards with running/completed status.
Their intervals play at a fixed 32× (`COMPACTION_SPEED` in `src/core/tempo.mjs`), independent
of the thinking-speed selector. If the transcript lacks a start marker, preparation
uses the preceding message/tool-result boundary and marks the timing as estimated.
Compaction summary text is never imported, and these events do not change game state.
Grapheme segmentation and annotation layouts use bounded caches. Unchanged
progress squares retain their tooltip and styles, and a static board stops
repainting after active effects finish while the timer continues advancing.
The game board and animations use two stacked canvases. The base canvas retains
the page until its snapshot, annotations, editing cell or size changes; pointer,
note editor and glyph effects render on a transparent overlay without redrawing
the page's glyphs and notes. The browser composites the two layers directly.
The thinking-speed selector keeps its selected value while actions slow down.
Tool rows do not display execution durations.

## Prepare another recording

```powershell
uv run --isolated --no-project --with UnityPy --with pycryptodome python .\replay-player\prepare.py
```

This reads `recordings/events.jsonl` and `recordings/states/` directly. If that
log does not exist or is empty, it falls back to the latest **nonempty** legacy
recording subdirectory. It finds an overlapping Codex
conversation in the local index, and imports user messages and public assistant
messages. Hidden reasoning, developer instructions, injected environment/page
context, and transcript tool payloads are excluded. Tools come from the probe
log, not the conversation. User messages are right aligned with a blue right
border; assistant messages keep their left border. Neither has a role label
or a filled message background.
During playback, both user and assistant messages reveal progressively with a
small trailing cursor. The reveal runs in physical screen time (22ms per
character, 300ms–6s per message), independent of thinking speed. Pausing freezes
the reveal; seeking shows historical messages in full. A final message can
finish revealing after the recording ends without advancing the timer.
Derived events retain original timestamps in `real`; `time` removes between-turn
waits, whose source ranges are stored in `idleCuts`. The timer shows this active
playhead, so omitted idle time does not cause timer jumps.
Preparation also aligns Codex extension retry logs by conversation turn ID and
local timestamp. For each logged failure, it removes the failed request wait
from the preceding transcript activity boundary through the retry backoff
(`retry_delay` or `in ...ms/s`). Consecutive failed attempts start at the previous
backoff's end. An SSE idle timeout uses the last recorded response/progress item;
error-path token counters are not treated as progress. These are transcript
boundaries, rather than packet-level request start times, and may include a
small amount of request preparation. Tool execution is protected, overlapping
cuts are merged, and generation after a retry is retained. Quiet gaps without
a matching failure log are unchanged. Original timestamps remain in `real`.
Matching notices are cached in `data/network-waits.json`, so rebuilding can retain
them after extension logs rotate. The bundle's `networkWaits.removedMs` reports
the additional time removed. Source recordings are never edited.
`--recording`, `--conversation`, and `--assets` override the input paths.
For the direct log, use `--recording recordings`; old recording subdirectories
can still be selected explicitly. MCP restarts append to the same source log.

The default resource path is the local Steam game's `resources.assets`; override
it for another installation. UnityPy is used only during preparation, following
its [sprite extraction interface](https://github.com/K0lb3/UnityPy). The script
reads the assets and writes a private atlas. It neither starts nor modifies the
game. PyCryptodome reads the game's counting sets from its text assets; character
meanings are not exported. Source probe logs, snapshots, and the recorder itself
are left unchanged. Glyph extraction reads both `resources.assets` and
`sharedassets0.assets`, where the game's `0` sprite is stored. Any remaining
fallback keys are listed in `data/glyphs.json`; both asset files participate in
the atlas cache fingerprint.

Preparation also extracts PT Sans Regular and FangZhengHeiTi-GBK-1 from
`sharedassets0.assets` beside the selected resource file. To extract only fonts:

```powershell
uv run --isolated --no-project --with UnityPy python .\replay-player\font_assets.py
```

Generated `data/` contains local game assets and conversation text and is ignored
by version control. The player itself subsequently needs only Python's standard
HTTP server and a browser. Prepared glyphs are cached against the asset hash.

## Grade annotations

See [grading/README.md](grading/README.md) for API key, Base URL, model settings,
offline extraction, cached evaluation, and automatic playback integration.
Scores live under each recording's `grading/` directory; the original event and
snapshot files remain unchanged.
`data/grading.json` is a separate playback copy of the scores and author
references. Grading updates replace only that file, leaving `data/replay.json`
unchanged. Hover a word square to compare its historical player annotation with
the original English key, dictionary definition, numeric value, and score reason.

## Display rules

- The game board uses each captured cell's actual historical note, styles, frames,
  and divider geometry. Raw English character keys are never shown as translations.
  The fixed black/cream palette is an approximation; color settings were not recorded.
  Dividers are reconstructed from layout anchors: the title divider is below
  row 0; the right panel divider is at the lower panel's top edge. The source
  recording does not contain LineRenderer endpoints or visibility flags.
  Game frames use exact cell edges; shared edges are merged. Consecutive
  underlines reach each cell's full width, with no artificial gaps.
  Board annotations and player text use the game's embedded PT Sans Regular,
  with FangZhengHeiTi-GBK-1 (FZHei-B01) for Chinese. Both fonts load locally before
  the first game frame is drawn. Japanese font handling is unchanged.
  Alien glyphs come from sprites.
  Notes start at 0.28 board units (about 16px in a 1920px capture), keeping short
  annotations on one line. Longer annotations wrap and shrink only as needed.
  Annotated fields have a faint background using the footer's annotation color,
  at 16% opacity (`--annotation-tint-opacity`). Unannotated fields have no tint.
  Tints, edit outlines, and selection fills use matching rounded rectangles,
  including in the floating note editor.
  Glyphs themselves keep their original background; dimming and editing overlays
  still apply to the annotation fields.
- The compact footer separates “进度” on the left from “文字”
  on the right with a thin divider. Texts, questions, and games use compact rows;
  each short header has a thin summary bar filling the gap between its left
  label and right legend. Progress combines passed texts, questions, and games;
  words show the green/yellow/red grading fractions, with remaining space grey.
  Without attached grading, existing annotations retain their original green display.
  titles, categories, counts, totals, and legends share one readable font size
  (18px, or 16px in narrow windows), with space reserved for the larger labels.
  each square grid chooses its own row count to fit its available width, so
  the seven game squares do not reserve a tall column of empty space.
  Four labeled square grids show reading texts, questions, games, and word
  translations. Reading texts are completable pages reached through the game's
  reading menus (130 for the current assets). The other totals are 56 questions,
  7 games, and 1,344 eligible words. Tokens and aliases are excluded from words.
  All grids fill from top to bottom, then left to right.
  All four categories use equal fixed square sizes: 7px normally, 6px at widths
  up to 1500px, and 5px up to 1100px. Gaps stay fixed at 2px. Only the row count
  changes to fit the available width; squares and gaps do not stretch to fill
  height. The footer follows its content height, with no forced height ratio.
  `--divider-space: 0.3em` gives header, horizontal, and vertical dividers the
  same padding on both sides, including narrow windows.
  Progress has grey/green legend entries for not passed/passed. The word legend
  shows grey/red/yellow/green for unannotated/incorrect/close/correct. With grading
  attached, hollow squares represent annotated versions still awaiting a score.
  Hover a square to read its grading reason. Cell annotation tints use the same
  grade; unannotated or pending fields have no tint.
  Changes to completion or annotation text briefly highlight the square with a
  fading white outline (650ms). Seeking cancels highlights and restores the
  historical state without flashing every square.
  Initial notes, successful off-page notes, clears, and captured notes after failed
  operations all affect the count. Future annotations do not appear when seeking back.
- Reading/question/game completions are reconstructed from recorded top-right win
  markers and dimmed menu links: Draw renders `(win)` by dimming the linked row.
  Only complete, underlined menu links matching a known page are counted.
  This does not read the current save or
  invent unobserved historical completions. The current recording confirms 49/56
  questions, 3/7 games, 26/130 reading texts, and 403/1,344 annotated words. Missing evidence stays grey.
- The mouse path and annotation editing are simulated from tool arguments, not
  recorded cursor movement. Notes click the field below a visible character,
  select its previous annotation, and type one grapheme at a time. Off-page hash
  notes use a single-cell floating editor with the same glyph size, annotation
  layout, selection, caret, and thin green input border as visible-cell edits.
  No hash is displayed in the floating editor, and no navigation is invented.
  The final board
  always comes from the recorded state, including failed operations.
- Pointer movement uses distance-dependent durations with smoothstep acceleration
  and deceleration. Roughly 1/5/12/24 cells take 108/208/347/554ms. Longer trips
  gain modest average speed, capped at 0.065 board units/ms even at peak speed.
  `pointerMoveDuration` in `src/core/motion.mjs` controls this curve.
  Clicks wait at least `CLICK_MIN_DURATION` (300ms) and at least 40ms after arrival
  before pressing; stationary clicks retain the same 250ms minimum. Note edits
  begin selection and typing after arrival, with travel time added as needed.
  Thinking speed never
  shortens this delay. Its press and recorded result
  appear together, with no board crossfade.
  The pointer is a slender concave four-sided vector arrow, about 21px tall and
  tilted 25 degrees from vertical, with its tip at the click hotspot.
  A faint three-sample afterimage trails movement for up
  to 54ms, capped at 24px in length; stationary pointers leave no trail. Both
  shape and trail keep their screen size across window sizes. The afterimage
  is derived from the motion curve, so seeking does not accumulate old trails.
  Look calls take 80ms; glyph calls take 160ms (`GLYPH_CALL_DURATION` in
  `src/core/tempo.mjs`), spacing consecutive glyph starts further apart. Each glyph
  independently starts a 1,000ms
  marker around the glyph only, excluding its annotation: trace its border first,
  then sweep a 45-degree diagonal down and fade out. The diagonal is twice the
  border's thickness and is clipped inside the frame. Both lines use the same
  cream color as game text, with no fill, gradients, glow, or recolored glyphs.
  The 24px tool-row preview uses the same marker.
  These effects overlap later glyphs, clicks, and notes without holding up the
  timeline. Switching thinking speed preserves their physical age; seeking
  rebuilds them at the requested point. Duplicate effects share one board-cell
  overlay while their individual tool previews continue independently.
  Notes receive 350ms plus 65ms per grapheme (typing allowance capped
  at 2,400ms), so selection and typing finish before the recorded result appears.
  Wait takes 180ms and launch takes 400ms. The global selector never changes
  these durations. Dense calls retain every complete animation.
  Failed notes show the recorded result when the call completes. Every segment
  has a positive rate; boundaries are continuous, with no pause or catch-up jump.
- Tool names, arguments, status, and any glyph preview share one compact row.
  Character hashes are replaced by 24px glyphs on the left: note rows show the
  glyph followed by the annotation, and glyph rows show the glyph without a hash.
  Every tool's execution status is aligned on the right. Expanded details replace
  known hashes with inline glyphs as well; details are rendered only when opened.
  Full results remain accessible by clicking the row. Messages enter gently and
  previous tool groups fold when the next message appears.
- Tool calls are grouped between assistant text messages. A group's count reflects
  only calls reached so far. A new text message folds the preceding tool group.
  Click a group to expand it or a tool row to inspect its arguments/result/error.
- No actions are re-executed. Failed calls are marked failed; the board uses the
  recorded resulting state. A null state clears the board rather than inventing a frame.
