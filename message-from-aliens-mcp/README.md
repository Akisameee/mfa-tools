# Message From Aliens MCP

[English](README.md) | [简体中文](README.zh-CN.md)

An MCP server for **Message From Aliens**, a game about deciphering a pictographic
alien language. Let a model read the current page, inspect character shapes,
click characters, and save your annotations.

Reading, clicking, and annotating work in the background without moving the
system mouse or activating the game window. Launching the game may bring Steam
or the new game window to the foreground.

## Requirements

- Windows x64. Linux and macOS are not supported.
- An installed copy of [Message From Aliens on Steam](https://store.steampowered.com/app/1858720/),
  with Steam available and signed in.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for the recommended
  setup, and an MCP client that supports local stdio servers.
- Python 3.10 or later; uv can provision a compatible interpreter when needed.
- Run the server as the same Windows user and at the same privilege level as
  the game.
- Screenshot mode requires Windows.Graphics.Capture support and a visible,
  non-minimized game window. Image results require an MCP client and model that
  support image content; table, ASCII, and path results are plain text.

The server automatically selects Mono or IL2CPP runtime bindings. The current
Windows x64 Mono build, Steam build `26564542`, uses Unity `6000.6.8f1` and has
been verified. The earlier IL2CPP integration was verified with Unity
`6000.6.6f1`; its adapter is retained. Game updates may require integration changes.

## Setup

After the package is published to PyPI, add this stdio server configuration to
your MCP client:

```json
{
  "mcpServers": {
    "message-from-aliens": {
      "command": "uvx",
      "args": ["message-from-aliens-mcp"]
    }
  }
}
```

Restart or reconnect the MCP client after changing its configuration. If it
cannot find `uvx`, use the absolute path to `uvx.exe` as `command`.

uvx installs the package and dependencies into an isolated environment on demand;
a separate `pip install` is unnecessary. To pin a published version, use
`"args": ["message-from-aliens-mcp==0.1.6"]`.

To try the server from a source checkout before publication:

```powershell
uv run message-from-aliens-mcp --help
```

For a persistent installation after publication:

```powershell
uv tool install message-from-aliens-mcp
```

The `aliens-mcp` command remains available as a compatibility alias.

## Tools

All grid coordinates are zero-based: rows `0..8` run from top to bottom, and
columns `0..23` run from left to right.

| Tool | Purpose |
| --- | --- |
| `launch_game()` | Start the game through Steam, or connect to an existing instance. |
| `look(type="table", force=False)` | Read the current 9x24 grid with annotations and layout markers. |
| `look(type="screenshot", force=False)` | Capture the game window as a PNG, with pixel dimensions and window style. |
| `click(row, col, type="left")` | Click any grid cell, including blank cells, with either mouse button; return the target and outcome. |
| `note(hash, text)` | Save an annotation for every occurrence of a character, even when it is absent from the current page. |
| `wait(seconds)` | Advance game time on supported pages, applying normal time updates and saving the result. |
| `glyph(hash, format="image")` | Inspect a character as a PNG, ASCII art, or coordinate paths. |

### Reading and identifying characters

Table cells use `hash:annotation`, such as `abcd:my note`. Hashes contain four
lowercase letters or digits. The same character keeps its hash across pages in
the current connection. After a reconnect or game restart, call `look` again to
obtain current hashes.

The table preserves dividers and marks underlines with `\underline{...}`,
highlights with `\hl{...}`, dim text with `\dim{...}`, and frames with `[...]`.
Frames reflect visible rectangle outlines, not internal interaction slots.
Multirow card frames retain their grouping: `┌...┐` on the first row,
`│...│` on intermediate rows, and `└...┘` on the last row. Empty slots keep
the same outlines. Each cell retains its normal click coordinates.
Annotations reflect the game's live text, including automatic number and unit
translations when enabled.

Underlines come from the game's current line-renderer geometry; dim text comes
from each glyph renderer's color and the current palette. These are runtime
renderer states. Menu unlock conditions and hidden entries do not determine the
reported styles. Rectangular outlines come from closed, five-position line
renderers and are mapped onto the grid using glyph positions, including empty
cells. Click target labels use the same captured states and frame edges.

Table and screenshot modes keep separate in-memory caches. Each call reads the
current state; an identical result produces a short unchanged message instead
of repeating the content. Use `force=True` to request the full result.

Screenshots capture only the game window, including its borders when present.
An occluded window can be captured without activating or resizing it. Use table
coordinates for `click`.

### Clicking and annotating

Choose coordinates from the current table. `click` accepts `type="left"` or
`type="right"` and reports its target in the same format as `look`. Call `look`
after an interaction to inspect the new page. Blank cells, including empty
answer frames, can be clicked and are reported as `blank` or `[blank]` without
inventing a character hash.
Background clicks with an unfocused window have been verified;
minimized-window clicking has not been separately verified.

If a click requests external navigation, the server returns the requested URLs
and prevents that click from opening a browser. If the game closes, the result
directs the model to `launch_game()`. The MCP server remains available.

`note(hash, text)` accepts a hash from `look`, updates all occurrences across pages,
and saves through the game's normal annotation handler. The character does not
need to remain on the current page. Text must be one line of at most 49 UTF-16
units. An empty string clears the annotation. Successful results contain
`ok`, `hash`, and `text`.

### Advancing game time

On supported pages, `wait(seconds)` advances game time without sleeping.
For example, `wait(60)` skips one minute of real-world time. Each call accepts
0.001 to 86400 seconds, rounded to milliseconds. The game applies its normal
time updates, refreshes the page, and saves the result.

Calls on unsupported pages return an error. The system clock is unchanged.

### Character shapes

`glyph` accepts a hash from the current `look` and returns one selected format:

- `"image"` (default): a fixed 64x64 PNG drawn from the game's vector geometry,
  with two-pixel black strokes on white and antialiasing. No screenshot or DPI
  metadata is included.
- `"ascii"`: spaces and `#` on an adaptive grid, at least 10x10 and capped at
  121 rows by 241 columns. Display it in a monospaced font. Very close strokes
  may merge at the size cap.
- `"paths"`: JSON polylines fitted proportionally into a 100x100 coordinate
  range. The origin is top-left, x increases right, and y increases down.
  Connect consecutive points within each path only. A repeated first point
  closes the path; a single point is a dot. These are drawing paths, not a
  writing stroke order.

Character shapes and tables do not expose the game's internal word keys or
meanings.

## Back up, reset, and restore saves

Use these steps to start a clean playthrough or prepare a fresh model test.
They affect local annotations, solutions, completion records, bookmarks, and
other saved progress across all slots and Steam-account subfolders in the game
data directory. Steam achievements are managed separately.

### Before changing save files

1. Disconnect or disable this server in the MCP client, then exit the game.
   Confirm that `MessageFromAliens.exe` is no longer running in Task Manager.
   A running game can write its in-memory progress back over changed files.
2. In Steam, right-click the game in your Library, open **Properties > General**,
   and disable Steam Cloud for this game. Keep it disabled during the reset and
   verification so a cloud copy cannot replace the local test save. See
   [Steam's Cloud instructions](https://help.steampowered.com/en/faqs/view/68D2-35AB-09A9-7678).
3. Press **Win+R** and open:

   ```text
   %USERPROFILE%\AppData\LocalLow\Artless Games
   ```

The game data folder is named `MessageFromAliens`. It can contain both older
top-level saves and newer saves inside a numeric Steam ID subfolder:

```text
MessageFromAliens/
├── alienmessage1.sav
├── alienmessage2.sav
├── alienmessage3.sav
├── alienmessage1.sav<version>.backup
├── setting.sav
└── <SteamID>/
    ├── alienmessage1.sav
    └── setting.sav
```

The exact files depend on the game version and slots used. Back up the entire
folder, including account subfolders and version backups; copying only the
top-level `alienmessage1.sav` can miss the active save.

### Make a backup

Copy the entire `MessageFromAliens` folder to a dated directory outside the game
data folder, for example:

```text
%USERPROFILE%\MessageFromAliens-backups\<timestamp>\MessageFromAliens
```

Wait for the copy to finish and check that the files and subfolders are present.
Keep this original backup intact when creating subsequent test backups. Saves
are encrypted; retain the original files rather than editing them as text.

### Clear progress

From a source checkout or source distribution, close the game and disable Steam
Cloud, then run the standalone PowerShell helper. It preserves all `setting.sav`
files and moves progress files from every slot/account, including migration
backups, to the Windows Recycle Bin. It creates no additional backup and leaves
the game closed:

```powershell
# Preview the exact files; no changes:
.\scripts\reset-save.ps1 -WhatIf

# Clear progress:
.\scripts\reset-save.ps1
```

The helper refuses to run while `MessageFromAliens.exe` is running or if the save
path contains symbolic links or junctions. Its optional `-SaveDirectory` must
point to a `MessageFromAliens` directory inside `Artless Games`. It does not change
Steam Cloud settings or reset Steam achievements. For an archive-based manual
reset instead, follow the steps below.

With the backup complete, the game closed, and Steam Cloud disabled:

1. In the `Artless Games` directory, rename the existing `MessageFromAliens`
   folder to `MessageFromAliens.before-reset-<timestamp>`. Leave it beside the
   original location, outside the new game data folder. This archives all old
   slots and migration backups together.
2. To reset progress **and settings**, leave the original folder name absent.
   To **preserve settings**, create a new empty `MessageFromAliens` folder and
   copy only the `setting.sav` files from the backup, preserving their relative
   paths, including `<SteamID>/setting.sav`. This retains display, color, and
   translation preferences. Do not copy progress files into the new folder.
3. Launch the game through Steam, or reconnect the MCP server and call
   `launch_game()`. The game creates fresh progress in its normal data folder.
4. Call `look(force=True)` and check that previous annotations are gone and
   the opening page is available. Unannotated characters normally display `?`.
   If settings were preserved, automatic number/unit translations can still
   appear; turn those off in the game if your test requires no translation hints.

Moving only one save file can leave another slot, account copy, or legacy save
available for migration. Archiving the whole folder avoids leaving those copies
in the active data directory. Keep Steam Cloud disabled for an isolated test
playthrough; local files are not being backed up to Steam while it is off.

### Restore the original progress

1. Disconnect the MCP server, close the game, and keep Steam Cloud disabled.
2. Rename the current `MessageFromAliens` folder to
   `MessageFromAliens.before-restore-<timestamp>` so the test progress is also
   retained outside the active data directory.
3. Copy the backed-up `MessageFromAliens` folder back into `Artless Games`, with
   that exact folder name. Restore the whole directory rather than merging it
   into the test save; a merge can leave newer account or slot files in place.
4. Start the game and reconnect the MCP server. Call `look(force=True)` and
   check the restored annotations and progress. Read current hashes again.

If you re-enable Steam Cloud later, check which save you intend to synchronize.
If Steam reports a conflict, select the copy containing the progress you want;
an old cloud copy and a reset or restored local copy can differ.

## Troubleshooting

| Problem | Action |
| --- | --- |
| The game is not running | Call `launch_game()`. Other tools do not start it automatically. |
| Launch times out | Check that Steam is signed in and the game can launch normally, then retry. |
| The server cannot attach | Check the Windows user and privilege level of both processes. |
| Screenshot fails while minimized | Restore the game window. It can remain behind other windows. |
| Images are missing in the client | Use table mode and `glyph(format="ascii")` or `glyph(format="paths")`. |
| A hash is unknown after reconnecting | Read a fresh table with `look`. |
| Frida cannot write its temporary files | Set `ALIENS_MCP_TMP` to a writable directory in the server environment. |

## Development

For optional local tool/grid recording, see [MCP probe recording](docs/recording.md).
It is disabled by default and captures no screenshots or glyph resources.

From a source checkout:

```powershell
uv sync
uv run python -B -m unittest discover -s tests -v
uv run message-from-aliens-mcp --status
uv run message-from-aliens-mcp --look
```

Without CLI options, the command serves MCP over stdio. `--status` checks the
game connection and detected runtime; `--look` prints the current table. `--look --json` prints JSON.
`--look --raw` exposes internal word keys for development and can spoil puzzles.

See [architecture](docs/architecture.md) for module responsibilities and where
to change game operations, descriptions, and messages;
[runtime notes](docs/runtime.md) for implementation details; and
[release checks](docs/releasing.md) for compatibility tests and publication.

## License

MIT; see [LICENSE](LICENSE). This is an unofficial integration. Game assets,
decompiled game code, saves, and player annotation files are not distributed.
The server instruments the running game with Frida and does not patch game files.
