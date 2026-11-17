# MCP probe recording

The optional probe records MCP tool calls and the native grid data required for
offline replay. It does not replay actions against a new save, record ordinary
model messages, save screenshots, or collect glyph paths. The separate
`replay-player/` imports conversation messages and builds an offline replay.

## Enable

Set the server environment before starting MCP:

```toml
[mcp_servers.message-from-aliens.env]
PYTHONIOENCODING = "utf-8"
ALIENS_MCP_RECORD = "1"
ALIENS_MCP_RECORD_DIR = 'E:\Game\MessageFromAliens\recordings'
```

Merge these two recording variables into the existing MCP environment; preserve
its other values such as `PYTHONPATH`. Reconnect MCP after changing the environment.
Only `ALIENS_MCP_RECORD=1` enables recording; unset it or use `0` to disable.
The default destination is `recordings/` relative to the server working directory.
Files are written directly into this directory. Restarting MCP resumes the same
event log, preserving the original manifest, previous events, and snapshots.
Recording initializes on the first tool call, not on server startup or tool
discovery. An idle server does not create files or reserve the directory.
There are no per-startup or per-conversation subdirectories and no conversation
binding. All calls made with this configuration join the same recording.
There is no model-facing toggle, new tool, or change to tool descriptions or results.
CLI `--look` and `--status` are diagnostics, not MCP calls, and are not recorded.

## Capture rules

| Call | Grid data |
| --- | --- |
| `look(type="table")` | Save the native snapshot already read by that call, including when the model receives an unchanged-cache message. No second read. |
| `click`, `note`, `wait`, `launch_game` | After completion or failure, attempt one native snapshot if a connection is still alive. |
| `glyph` | Record the call and format/hash/key metadata only. No extra grid read and no glyph result payload, including paths and ASCII. |
| `look(type="screenshot")` | Record the call and result metadata with image bytes omitted. No grid read. |

The probe does not start a stopped game, reconnect solely to record, modify the
look caches, or assign new public hashes. It serializes MCP calls through result
capture so another tool cannot run between an action and its snapshot. Normal
game time can still pass during observation; recording is not a continuous or
frame-by-frame video capture.

## Files and schema version 1

```text
recordings/                 # ALIENS_MCP_RECORD_DIR itself
  manifest.json
  events.jsonl
  states/<sha256>.json
```

`manifest.json` contains the schema and MCP versions, recording ID, start time,
and flags indicating which resources are omitted. `events.jsonl` is UTF-8 JSONL.
Every event has a strictly increasing `seq`, UTC `at`, and increasing `elapsed_ns`.
Sequence and call IDs continue after an MCP restart. Elapsed time uses the
process monotonic clock while running, with a restored offset on restart that
includes the gap since the previous event. Existing timestamps are unchanged.
`call.begin` is flushed before execution; `call.end` is flushed after capture.

- `call.begin`: `call_id`, `tool`, `arguments`, `request_id`, `state_ref`.
- `call.end`: `call_id`, `tool`, `status`, `result`, `error`, `completed_at`,
  `completed_elapsed_ns`, `connection`, `state_ref`, `state_observed`, `capture`,
  `capture_error`, `character`.

`call_id` is local to this recording. `request_id`, when available, is the MCP
request ID, not necessarily the model or conversation tool-call ID. Calls outside
a real transport request can have a null request ID. A later importer can use
timestamps, IDs, arguments, and sequence for alignment; the probe does not guess
model-message associations.

Each state file is a full `{connection, snapshot}` object. `snapshot` preserves
the native `page`, `rows`, `cols`, `cells`, `boxes`, `frames`, and `geometry`, plus
`ids` for character keys already known to the public hash registry. Cells retain
their original `word` key, block, coordinates, current note, and rendered flags.
`ids` maps key to hash; an extra probe read never registers an unseen key. Identical
states within a connection share a content-addressed file. A connection generation
distinguishes reconnects, where hash mappings may change.
It also distinguishes MCP restarts, even when local connection counters reset.
The current state reference starts empty after restart until a new grid is read;
an old snapshot is not presented as a fresh observation.

For calls with a known `hash` argument, `character` records `{hash, key}` without
fetching resources. A future player can decode the raw keys using the matching
game resources. Preserve the note in each historical snapshot; using the final
dictionary would reveal later discoveries early.

`capture` is `reused`, `captured`, `not_requested`, `unavailable`, or `failed`.
Read-only calls can reference the last observed state with `state_observed=false`;
that is a timeline anchor, not a new observation. Before the first grid capture,
the reference is null. A failed/unavailable post-action capture clears the current
reference instead of presenting a stale frame as current. The call result/error
still identifies observed closure or a partial effect. `completed_*` marks when
the tool completed, before any extra snapshot work; the event timestamp also
includes that recording overhead.

Recording I/O failures disable the current recorder and log to stderr. The next
tool call retries recording initialization. Failures do not turn a successful
operation into a tool error or cause any game action to be retried.
Snapshot failures are recorded separately from tool failures. Coded partial
failures retain their details, such as time already advanced before saving failed.
After a crash, a begin event without an end event is incomplete, not confirmed
success. Resuming removes only an interrupted final JSONL line before appending;
complete malformed lines disable recording rather than silently losing history.
Incomplete calls are never automatically executed again.

There is no cross-process directory lock or lock-file creation. An idle MCP
process cannot block recording in another process. Counters are refreshed from
new log entries before each call, so sequential use and MCP restarts can continue
the log. Simultaneous writing from multiple processes is not synchronized: use
one actively playing conversation per directory. An old `.recording.lock` file
from previous versions is ignored.

To start a separate recording, stop MCP and choose another directory (or move the
current recording files elsewhere) before restarting. Clearing the game save does
not clear this log. Older timestamp/UUID directories are left untouched and are
not automatically merged into the direct recording.

## Data handling

Recordings include the player's annotations and internal character/page keys.
They remain local and are not returned to the model. `recordings/` is ignored by
version control and excluded from wheel and source distributions. Export this
directory intentionally when building a replay.
