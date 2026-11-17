# Runtime notes

Current live verification: Windows x64, Unity `6000.6.8f1`, Mono, Steam build
`26564542`, on 2026-11-13. The earlier Unity `6000.6.6f1` IL2CPP integration was
verified on 2026-11-09; its runtime adapter is retained and covered by binding tests.
The runtime API resolves game fields and methods by name; generated class tables,
process addresses, and decompiled game code are unnecessary for normal operation.

See [architecture](architecture.md) for module boundaries and the error protocol.

## Runtime selection

`game/scripts/runtime.js` selects the loaded `GameAssembly.dll` or `mono-2.0-bdwgc.dll` and
provides one interface to the page and input code. Mono uses its embedding APIs
for assemblies, inherited member lookup, static-field vtables, strings, arrays,
and managed invocation. Image names are normalized with or without `.dll`.
Managed method addresses come from `mono_compile_method` and are cached; an
IL2CPP MethodInfo's first pointer is used only in the IL2CPP adapter.

The Frida worker attaches to the existing runtime domain. On close, Python calls
the script's `dispose` export before detaching Frida so the Mono worker releases
its managed thread. Cleanup still detaches Frida if the game runtime is gone.
No extra Python dependency or replacement game assembly is required.

## Reading a page

- `Global.manager` is the live `Draw` controller. No singleton scan is needed.
- `Draw.alien_slots` is a column-major `AlienCharacter[24,9]` array. Public
  coordinates use `col = index // 9`, `row = 8 - index % 9`.
- The array reuses objects across pages. A nonempty `alien_txt` can be stale;
  current membership comes from `alien_left_title`, `alien_left_menu`,
  `alien_left_text`, `alien_right_title`, `alien_right_menu`,
  `alien_right_text_up`, `alien_right_text_down`, and `alien_right_text_grid`.
  Both reading and clicking must respect these lists.
- `AlienCharacter.alien_txt` is an internal word key; only its opaque four-character
  ID crosses the normal public snapshot boundary. `GlyphIds` starts with CRC32
  modulo 36^4, encoded in lowercase base36, and resolves collisions by linear
  probing. The complete catalogue is registered in sorted order before a snapshot
  assigns IDs. Discovered/generated words receive unused IDs without changing
  previous assignments. `look` and `glyph` share this connection-local index.
  Reconnects rebuild it: clients should refresh IDs with `look`. An unchanged
  catalogue receives the same initial mapping independent of enumeration order.
- The matching `Draw.txt_slots` entry is a `TMP_InputField`. Its `text` is the
  player's current annotation, including when the window is in the background.
  This replaces dictionary discovery, CJK-based heuristics, and disk caches.

## Layout and decorations

- `Draw.center_line`, `right_title_pos`, `right_message_pos_u`, and
  `right_message_pos_d` define the divider geometry.
- `Draw.slots` is an interaction list, not evidence of a visible outline. It is
  not read when classifying decorations; some interaction cells have only an
  underline. Boxes come exclusively from rendered rectangle geometry.
- `game/scripts/decorations.js` reads the current `Draw.selected` line renderers. Enabled,
  visible two-point horizontal segments at the glyph underline baseline identify
  underlined cells. Vertical cursor lines are excluded. Local-space line
  positions are transformed to world coordinates before classification.
- `Draw.DrawRectRenderer(float, float, Vector2, int)` creates five-position,
  closed axis-aligned outlines in the same list. Their bounds are matched against
  every grid sprite's world position, including inactive empty cells. Only complete
  rectangular grid regions are published as `frames: [[top, left, bottom, right]]`.
  Single-cell outlines merge with `boxes`; multirow frames use top corners, middle
  sides, and bottom corners. The smallest enclosing multi-cell region supplies
  per-cell edge flags; a nested single-cell selection remains inside that outline.
  `look` and pre-click target capture use the same geometry and spelling.
- `Draw.DrawLineRenderer(Vector2, Vector2, int)` is the named drawing entry used
  by `Draw.Write`; Mono can locate its JIT address through method metadata.
  Reading existing renderers also handles a page drawn before the MCP connected.
  The underline baseline is the `Draw.Write` offset of 0.92 world units below the
  sprite center; this layout assumption should be rechecked after game changes.
- Dim state compares `AlienCharacter.sp.color` with `Draw.DefaultColor(3)`, using
  the current palette and a small float tolerance. Equal normal and dim palette
  colors are not marked dim. This reads renderer state, without screenshot OCR.
- `[condition]` tokens control entry visibility; they do not mean that an entry
  has an underline. Hidden entries also change visible line numbering. No menu
  marker or source-line parser is used to infer styles.
- Highlighting comes directly from each `AlienCharacter.background` GameObject's
  `activeSelf`. This matches `AlienCharacter.Highlight(bool)` and avoids guessing
  from `marked_word` or reading the internals of `Global.word_source`.
- Markdown escapes player text so pipes, newlines and decoration delimiters
  cannot change table structure. JSON preserves the original text.
- Snapshots reject a page change detected between the start and end of a read.
  The worker-thread read is not an atomic snapshot of all UI state; changes
  within the same page can still occur during a read.

## Background input

Game-specific click branches live in `Draw.Update`, which polls legacy Unity
input. Calling a navigation method directly would cover only some click actions.
The implementation instead supplies input to the normal Update:

1. Find the `UnityWndClass` window belonging to the attached PID and its thread.
2. Queue work on that thread via its message loop and wake it with `WM_NULL`.
3. Resolve the native `Application.get_runInBackground` and
   `Application.set_runInBackground` bindings through the runtime adapter.
   IL2CPP uses `il2cpp_resolve_icall`; Mono resolves the declared internal-call
   methods with `mono_lookup_internal_call`. Call the setter on the main
   thread; calling it from Frida's worker thread triggered a native breakpoint.
4. Locate the requested grid cell and project its transform with
   `Camera.WorldToScreenPoint`. This handles camera scaling and letterboxing.
5. During the first `Draw.Update`, provide the selected button's down/held state
   and the projected mouse position. During the next, provide release state.
   Input hooks apply only inside that controller Update on the game thread.
6. Restore the previous background setting before completing the request.

Input state must be consistent across every query in a frame. Reading
`GetMouseButtonDown` must not consume the coordinates. Hooks are explicitly
flushed before waking the target thread; a delayed second wake covers an already
in-flight wait. Main-thread work is bounded by a timeout.

On Windows x64, the IL2CPP `Input.get_mousePosition` wrapper returns Vector3
through a caller-provided buffer. Mono hooks `get_mousePosition_Injected`'s
explicit out buffer and the native mouse-button internal calls. These are ABI
assumptions to recheck for a new platform or engine build. Mono string and array
access uses embedding APIs; the IL2CPP adapter retains its array data offset.
There are no hardcoded game-object field offsets.

## Glyph geometry

`Draw.StringToCharacter(string)` delegates to `Global.StringToCharacter`, which
reads `AlienInfo.GetCharacter()` and returns a copy of its `List<List<Vector2>>`.
These are the same polylines consumed by the game's `DrawPath1` renderer. Geometry
reads work on the attached Frida worker thread and do not require background
updates, simulated input, or changing the displayed page.

The catalogue comes from `Global.alien_text.get_Keys()` and
`KeyCollection.CopyTo(String[], 0)`. Python builds a private opaque-token index,
also adding generated word keys observed by `look` or on the current page. Hash
collisions are resolved before publishing IDs; unknown tokens produce errors
instead of selecting a wrong glyph. IDs must be exactly four lowercase letters
or digits. Legacy six-character IDs require a fresh `look` and are not accepted.
Only geometry crosses the public tool boundary. List fields are resolved by name;
Vector2 array elements use the selected runtime's array-data accessor and two
inline float32s.

`rendering/glyph.py` uses one aspect-preserving transform for all three formats, flipping
the game's y-up coordinates to a top-left origin. Separate paths stay separate;
open paths are not implicitly closed. Single-point paths are dots. ASCII
resolution accounts for short segments and positive distances between disjoint
segments, ignoring actual intersections and float32 noise near shared endpoints.
PNG output is fixed at 64x64, with four-pixel margins, two-pixel strokes, and
4x supersampling before Lanczos downsampling. No DPI metadata is written.
Raster outputs cannot guarantee separation for arbitrarily small features.
The paths format retains normalized floating-point
coordinates (rounded to nine decimal places). PNG rendering uses Pillow with
antialiasing. The MCP layer wraps PNG bytes in the SDK's Image helper so clients
receive actual image content rather than a base64 text string or file path.

## Repeated look results

The public `look` wrapper keeps independent in-memory cache entries for table and
screenshot modes. It always performs a live grid read or window capture before
comparing, so a stopped process, failed capture, or edited note is not hidden by
cached data. Table comparison uses page identity and the full rendered table;
screenshot comparison uses exact decoded RGB pixels and all reported dimensions
and window style. PNG compression/encoding changes alone do not invalidate an
otherwise identical image. There is no perceptual similarity threshold. Only
the last successful result of each mode is kept; no images are written to disk.

On equality the tool returns a short `Unchanged: ...` text block. `force=True`
still reads the current state and returns the full selected view. The lower-level
`look_json` helper remains an uncached full snapshot for CLI/development callers.
Resetting/reconnecting the Frida session clears both entries. Clicks and notes
do not blindly invalidate a view; the next actual observation detects changes.

## Window screenshots

`look(type="screenshot")` is independent of the grid reader. `game/capture.py` selects
the existing Unity HWND by the attached game's PID and uses `windows-capture`
2.0.1+ (`Windows.Graphics.Capture`) with `window_hwnd`, cursor capture disabled,
and the capture notification border disabled. The game's own title bar and
borders remain visible. BGRA pixels are copied during the frame callback before
the mapped D3D buffer becomes invalid, then encoded as an RGB PNG without resizing.
The capture session is stopped after one frame, or after an eight-second timeout.
There is no desktop capture fallback, focus change, or automatic window restore.
Minimized/hidden windows are rejected before capture.

The MCP response contains a short metadata text block and an image block. Metadata
includes PNG pixel dimensions, client-area pixel dimensions, and captioned versus
borderless style. Client dimensions are queried under a temporary per-thread
PER_MONITOR_AWARE_V2 DPI context, then the previous context is restored; process
DPI settings remain untouched. Borderless style alone does not prove exclusive
fullscreen mode. Screenshots can show selected setting frames and colors that the
table's semantic layout does not currently include.

Automatic number/unit translations need no separate conversion: grid notes come
from `TMP_InputField.text`, after the game has updated its displayed text. A live
settings-page check with translation enabled showed `1 (1)` through `7 (7)`, with
the latter belonging to the character for internal base-seven `1e1`. The tool
retains the opaque token and displayed text; it does not parse numeric word keys
as decimal or expose other internal meanings.

## Scope

Frida is the sole backend. There is no automatic process-memory fallback,
annotation cache, build-profile layer, or standalone reverse-engineering toolchain.
`launch_game` requests game startup through Steam; the game and Steam must be
installed and usable. `note` saves through the game's
own submission flow. Old annotation caches outside the project are unused.

## Annotation commits

`note(hash, text)` resolves the token through the same collision-aware index as
`look` and `glyph`, including previously seen generated words. Unknown tokens
are rejected before native editing. The character need not be on the current page.
It shares `game/scripts/scheduler.js`'s main-thread queue with `click` and calls the game's
`AlienCharacter.EndEdit`, preserving dictionary writes, achievements, special-page
refreshes, and `Global.SaveGame`.

An unfocused grid component provides the native submission context. If it belongs
to another character, its `alien_txt` field is temporarily set through the
runtime's GC-aware reference setter and restored in `finally`, before normal
`Draw.Update` continues. The tool never navigates to find a character or focuses
an input field. After Update, matching components refresh via `UpdateEarthText`.

The stored value is verified with `Global.GetDict`. If submission fails, the
operation attempts to restore the previous committed annotation through the same
submission method. Public results contain the hash and player text, never internal
word keys. The limit is 49 UTF-16 units; native validation also
checks the runtime field's actual limit. Strings are created with
the runtime's UTF-16 string constructor, preserving Chinese and surrogate pairs.

An empty annotation is stored as an empty string. The game subsequently displays
`?` in its input fields, so `look` also shows that placeholder. This is the game's
normal display behaviour, rather than a failure to clear the stored value.

## Incremental minigame time

`wait(seconds)` uses the existing main-thread input queue and background wake-up
mechanism. `game/scripts/time.js` validates the current page and initialized timer state before
modifying anything. It settles pending real elapsed time with `Draw.IdleTimePass`,
then subtracts the requested milliseconds from both `idlestarttime` and
`idlecurrenttime` via `Global.SetFlag`. Shifting both preserves the game's elapsed
time multiplier and production interval. A second native `IdleTimePass` applies
the same batched settlement used when returning to the game; the tool does not
implement its own economy or make purchases.

The ordinary `Draw.Update` completes the redraw and native completion check;
`Global.SaveGame` is invoked afterwards. A settlement error attempts to restore
the previous timestamps and currency. A later save error explicitly reports that
time already advanced. Existing notes, upgrade counts, and the system clock are
unmodified. Each call accepts 0.001..86400 real seconds; an additional capacity
check protects the game's signed-int32 tick calculation. The tool reports only
the advanced seconds, without exposing internal flag keys or formulas.

## Launch and exit

`launch_game()` sends `steam://run/1858720` only if the game process is absent.
It serializes with other tools and waits up to 45 seconds for a Unity window,
Frida connection, and nonempty page. Attaching before the Windows loader/Unity
window is ready caused Frida helper injection failures during live testing, so
the window is checked before injection. Script loading also checks the runtime
domain and game assembly before dereferencing classes. Existing processes are
reused. A timeout or a Steam startup failure is an error, not a ready receipt.

No-process errors are `GameNotRunning` with a `launch_game()` recovery hint. MCP
wrappers preserve these messages as tool errors across table/screenshot look,
click, note, and glyph. Dead sessions and their private glyph indexes are cleared
before reconnecting.

During injected clicks, `game/scripts/effects.js` observes the game's `Application.Quit` native
icall and available managed overloads. The native icall covers IL2CPP inlining.
An exit notification includes the current click request ID and is accepted only
for that request; hooks require the game thread, active injected input, and
observed button/position queries. This notification is distinct from process loss.
Unity can wait for an attached managed worker during shutdown. On a confirmed Quit
request, Python releases Frida instrumentation before waiting up to 15 seconds
for the original PID to disappear. Only then does click return a successful
`game_closed` receipt and `next_tool: launch_game`. Unexpected exit without a Quit
notification is reported with `ok: false` and an unconfirmed click status. A live
process with a broken connection remains an error. Ordinary successful clicks
also include `game_running: true` after a short exit check. There is no special
meaning lookup or hardcoded exit-button coordinate in this logic.

The MCP `click` wrapper renders this internal receipt as one natural-language
English text block including the clicked ID and current player annotation. It
leads with game closure and the `launch_game()` recovery
instruction when the process has exited. An unconfirmed click is explicitly
described as unconfirmed; external URLs are listed verbatim with a statement
that navigation was blocked. The Python `tools.click` API retains its structured
receipt for programmatic state checks. Operational errors remain MCP tool errors.

## Click target and shared guidance

On the first injected frame, `cellPixel` locates the grid cell, projects
its position, and records its internal word key and displayed input-field text on
the game thread before `Draw.Update` handles the click. Normal receipts include
this target; a request-ID-tagged Frida notification also preserves it if the
process exits before the RPC can return. Python converts the key using the shared
`GlyphIds` index and exposes only ID and player text. It never reads the same
coordinates after navigation to guess the target. Missing information remains
unknown, and unconfirmed clicks are not described as completed. Captured cells
identify the source cell at injection time; this is not independent physics-hit
instrumentation of the game's raycast.

Clicks accept blank cells, including empty answer frames. Current block membership
is used only to identify a visible character: stale words in reused cells are
reported as `{empty: true, boxed: ...}` instead. Python preserves that explicit
empty target, and MCP renders it as `blank` or `[blank]`. Annotations address
characters by hash independently of grid occupancy.

Process discovery uses a Windows process snapshot so a process omitted by Frida
can still be recognized. Injection access denial is reported separately from a
missing game and fails `launch_game` immediately. Executable integrity labels also
matter: a low-integrity Python executable cannot attach to a medium-integrity game.

The same capture includes actual underline, dim, highlight-background state,
and rendered rectangle geometry. Python preserves these per-cell flags with the
same `cell_decorations` helper used by `look` and returns only public flags.
Both MCP click messages and table cells call `render_cell`, so `hash:annotation`
spelling, escaping, and underline/highlight/dim/frame nesting stay identical.
These are the pre-click states; decoration changes caused by the click appear in
the next look rather than retroactively changing the captured label.

MCP server initialization `instructions` introduces the game, explains hashes,
and summarizes tool roles. Parameters, coordinate conventions, and cache/force
semantics live in the relevant tool descriptions. Special circumstances are
explained by the actual result rather than enumerated in the descriptions. Normal click results therefore
contain no `The game is still running` or `Call look()` boilerplate. The explicit
`launch_game()` recovery instruction remains on process-exit results. Screenshot
metadata contains only current dimensions and window style; repeated coordinate
and original-resolution explanations live in server instructions/tool descriptions.

## External URLs

`game/scripts/effects.js` replaces the managed `UnityEngine.Application.OpenURL(string)` entry
and its native `OpenURL_Injected(ManagedSpanWrapper&)` icall, resolved by name.
The native replacement covers inlined managed calls. In this Unity 6 Windows x64
build the native span is a UTF-16 data pointer followed by an int32 length; bounds
are validated before decoding. The managed entry accepts an IL2CPP string. If
the required native binding cannot be intercepted, click setup fails before any
input is supplied. If decoding fails during a click, external navigation is
still blocked and the tool reports an error.

While an injected click is pending on the game thread, a replacement collects
distinct URLs on the request and returns without calling the original function.
Normal input cleanup then returns `event: external_url`, `urls: [...]`, and
`opened: false`. Cancelled-but-pending requests also block navigation. Calls
outside a tool-injected click retain normal game behaviour. Replacements are
reverted if input-hook installation fails and on script unload. This does not
rewrite game files or inspect hidden button meanings. Live verification used
both community links at the bottom of the credits page; neither was opened.

Live verification covered Chinese edits, all same-character occurrences, crossing
pages, reconnecting, clearing, the 49-unit boundary, and supplementary Unicode.
Persistence was checked by reading the game's encrypted save through its own
`CryptoHelper.Decrypt` method; this diagnostic is not a public tool. Test edits
were restored in both the live UI and saved data.
