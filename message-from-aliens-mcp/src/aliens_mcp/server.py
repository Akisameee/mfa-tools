"""MCP server (stdio transport).

Run with `message-from-aliens-mcp` or `uvx message-from-aliens-mcp`.

The MCP Python SDK renamed FastMCP to MCPServer in 2.0; both are supported so the
package works with either major version."""

from __future__ import annotations

from typing import Literal
import logging
import os

import anyio

try:  # mcp >= 2.0
    from mcp.server.mcpserver import Image as _Image
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError as _ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp import Image as _Image
    from mcp.server.fastmcp.exceptions import ToolError as _ToolError

from . import tools
from .descriptions import INSTRUCTIONS, TOOL_DESCRIPTIONS
from .errors import GameError
from .messages import advanced_time, describe_screenshot
from .messages import describe_click as _describe_click
from .recording import Recorder, bind_call, unbind_call


class RecordingServer(_Server):
    """Observe calls before SDK validation; keep recording out of tool schemas/results."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.recorder = None
        self._record_lock = anyio.Lock()

    async def call_tool(self, name, arguments, *args, **kwargs):
        if self.recorder is None and os.environ.get("ALIENS_MCP_RECORD") != "1":
            return await super().call_tool(name, arguments, *args, **kwargs)
        async with self._record_lock:
            recorder = self.recorder
            try:
                if recorder is None or not recorder.enabled:
                    recorder = await anyio.to_thread.run_sync(
                        Recorder.from_environment
                    )
                    self.recorder = recorder
                else:
                    await anyio.to_thread.run_sync(recorder.refresh)
            except Exception:
                logging.getLogger(__name__).exception("Recording could not resume")
                if recorder is not None:
                    recorder.close()
                recorder = None
            if recorder is None:
                return await super().call_tool(name, arguments, *args, **kwargs)
            return await self._record_tool(recorder, name, arguments, *args, **kwargs)

    async def _record_tool(self, recorder, name, arguments, *args, **kwargs):
        request_id = None
        try:
            context = args[0] if args else kwargs.get("context")
            if context is None and hasattr(self, "get_context"):
                context = self.get_context()
            request_id = context.request_id if context is not None else None
        except (ValueError, LookupError):
            pass
        call = recorder.begin(name, arguments, request_id)
        token = bind_call(call)
        try:
            result = await super().call_tool(name, arguments, *args, **kwargs)
        except Exception as error:
            recorder.finish(call, tools.service, error=error)
            raise
        else:
            recorder.finish(call, tools.service, result=result)
            return result
        finally:
            unbind_call(token)


mcp = RecordingServer("message-from-aliens", instructions=INSTRUCTIONS)


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (ValueError, GameError) as error:
        raise _ToolError(str(error)) from error


@mcp.tool(description=TOOL_DESCRIPTIONS["launch_game"])
def launch_game() -> dict:
    return _call(tools.launch_game)


@mcp.tool(description=TOOL_DESCRIPTIONS["look"])
def look(type: Literal["table", "screenshot"] = "table", force: bool = False):
    from .models import Screenshot

    result = _call(tools.look, type, force=force)
    if isinstance(result, Screenshot):
        return [describe_screenshot(result), _Image(data=result.data, format="png")]
    return result


@mcp.tool(description=TOOL_DESCRIPTIONS["click"])
def click(row: int, col: int, type: Literal["left", "right"] = "left"):
    return _describe_click(_call(tools.click, row, col, type))


@mcp.tool(description=TOOL_DESCRIPTIONS["note"])
def note(hash: str, text: str) -> dict:
    return _call(tools.note, hash, text)


@mcp.tool(description=TOOL_DESCRIPTIONS["wait"])
def wait(seconds: float) -> str:
    result = _call(tools.wait, seconds)
    return advanced_time(result["seconds"])


@mcp.tool(description=TOOL_DESCRIPTIONS["glyph"])
def glyph(hash: str, format: Literal["ascii", "paths", "image"] = "image"):
    result = _call(tools.glyph, hash, format)
    return _Image(data=result, format="png") if isinstance(result, bytes) else result


def run() -> None:
    try:
        mcp.run(transport="stdio")
    finally:
        tools.reset_session()
