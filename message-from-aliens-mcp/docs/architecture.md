# Architecture

The public MCP API has six tools. Internal game names and implementation details
stay behind the service boundary. Tool descriptions remain spoiler-free.

```text
MCP server / CLI
       |
       v
tools.py                 shared entry points
       |
       v
GameService              validation, connection-scoped hashes, exact look caches
       |
       v
GameClient               game interaction API
       |
       +-- FridaTransport --> injected scripts --> game
       +-- windows.py     --> process, window, Steam
       +-- capture.py     --> background window capture
```

## Python responsibilities

| File | Responsibility |
| --- | --- |
| `server.py` | Register tools, adapt results to MCP text/image content, translate exceptions to MCP errors. |
| `tools.py` | Expose the shared service instance to MCP and CLI. |
| `service.py` | Serialize operations, maintain hash and cache lifetimes, validate requests, filter native data into public results. |
| `validation.py` | Reject invalid public inputs before connecting. |
| `hashes.py` | Assign and resolve connection-local character tokens. |
| `models.py` | Shared cell styles, click receipts, screenshot data and comparison keys. |
| `rendering/` | Pure table/cell formatting and glyph rasterization; no game interaction. |
| `game/client.py` | The entry point for launching, reading, capturing, clicking, annotating, waiting, and reading glyph paths. |
| `game/transport.py` | Own the Frida session, assemble scripts, decode RPC errors, release resources. |
| `game/windows.py` | Find the process/window and request Steam launch. |
| `game/capture.py` | Capture the game HWND without desktop fallback. |

`GameClient` accepts internal character identities and returns native data. It
does not assign public hashes or compose tool responses. `GameService` seeds the
full vocabulary before assigning hashes, then registers generated characters.
Reconnection clears both hash state and look caches. Only `launch_game` starts
the game; other operations report the centralized recovery hint.

The service filters a click target once, using `CellStyle` and `ClickResult`.
The table and click response share the same cell renderer. Native interaction
slot membership never supplies a visual frame; only rendered geometry does.

## Descriptions and errors

- Edit `descriptions.py` for server instructions, tool descriptions, and CLI help.
- Edit `messages.py` for success receipts, unchanged messages, screenshot metadata,
  and error wording. These messages are English.
- `errors.py` defines typed failures with a stable `code` and structured `details`.
  Python and JavaScript use codes instead of matching English error strings.

Injected RPC calls return successful native results unchanged. Failures cross the
bridge as `{error: {code, details, diagnostic}}`. `FridaTransport` raises a typed
`GameError`, and the presentation boundary renders its centralized message.
Unexpected native diagnostics go to stderr logging, not tool responses.

Effectful failures retain their state. For example, `TIME_SAVE_FAILED` carries
`advanced: true` and `seconds`; its message explicitly says time already advanced.
The transport does not retry an RPC operation automatically. Click completion
remains unconfirmed unless the game actually observed the injected input or exit.

## Injected scripts

`game/transport.py` defines the only script load order. All scripts share one
Frida context; no JavaScript bundler or Node runtime is needed by the server.

| Script | Responsibility |
| --- | --- |
| `protocol.js` | Internal coded errors and operation-handler registry. |
| `runtime.js` | Mono/IL2CPP bindings. |
| `state.js` | Managed field access, grid snapshots, vocabulary and glyph paths. |
| `decorations.js` | Read actual line geometry, colors, and highlight state. |
| `managed.js` | Checked managed invocation and string argument construction. |
| `annotations.js` | Native annotation commit, restoration, refresh, and verification. |
| `click.js` | Grid projection, pre-click target capture, mouse input hooks. |
| `effects.js` | External URL interception and observed exit events. |
| `time.js` | Supported timer advancement, rollback, and final save. |
| `scheduler.js` | Main-thread queue, background wake-up, timeout and setting restoration. |
| `exports.js` | Read-only RPC registration, cleanup, and the common sync/async error boundary. |

Write operations register `enter` and `leave` handlers with the scheduler. Native
`Draw.Update` still runs normally between these hooks. Keep capture-before-click,
annotation identity restoration, release-frame completion, background restoration,
and save-after-update ordering intact when changing handlers.

## Validation

The optional [recording probe](recording.md) observes MCP calls before SDK
validation. Explicit table reads pass their native snapshot through a call-local
observer; post-action reads use the service's non-connecting recording accessor.
The recorder has its own storage and does not use public look caches or allocate
hashes for unseen characters.

Run `python -B -m unittest discover -s tests -q`. The existing behavioral tests
cover rendering, cache, validation, lifecycle, native bindings, and public output.
Additional tests preserve the pre-refactor MCP contract, verify structured errors,
keep diagnostics private, and check partial failures without automatic retries.

For interaction changes also compare a live snapshot, perform an inert blank
click, round-trip an existing annotation without changing its text, and test a
small supported time interval. Screenshot integration requires a non-minimized
window. Package checks must verify all eleven JavaScript assets are included.
