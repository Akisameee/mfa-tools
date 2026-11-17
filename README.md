# Message From Aliens workspace

[English](README.md) | [简体中文](README.zh-CN.md)

This directory holds the MCP project, local game documentation, and private
investigation files.

| Path | Contents |
| --- | --- |
| [instruction.md](instruction.md) / [中文指令](instruction.zh-CN.md) | Spoiler-free startup instructions for an agent playthrough. |
| [message-from-aliens-mcp/](message-from-aliens-mcp/) | MCP source, tests, package metadata, README, license, development environment, and built distributions. |
| [replay-player/](replay-player/README.md) | Framework-free local replay player, browser recording, asset preparation, and annotation grading. |
| [message-from-aliens-mcp/docs/](message-from-aliens-mcp/docs/) | MCP runtime details and release checks. |
| `artifacts/` | Optional local investigation references, diagnostics, and generated previews; ignored by Git. |

Game documentation and other workspace material can live alongside the MCP
project. Private artifacts are ignored and are not included in the package.

## Work on the MCP server

Run development and release commands from the project directory:

```powershell
Set-Location .\message-from-aliens-mcp
uv sync
uv run python -B -m unittest discover -s tests -q
uv run message-from-aliens-mcp --help
uv build --no-sources
```

See the [MCP README](message-from-aliens-mcp/README.md) for user setup and the
[release checks](message-from-aliens-mcp/docs/releasing.md) for publishing.

Codex starts the project's `.venv` Python directly, with `PYTHONPATH` pointing to
`message-from-aliens-mcp/src/`. Reconnect the MCP server after changing source code.

The optional [MCP probe](message-from-aliens-mcp/docs/recording.md) records tool
events and native grid states for later replay. Recording is disabled by default.

## Local artifacts

`recordings/`, `artifacts/`, prepared player data, exported videos, and local API
configuration are ignored by Git and are not included in this repository.
An existing local `artifacts/` directory may contain its own reference index.
