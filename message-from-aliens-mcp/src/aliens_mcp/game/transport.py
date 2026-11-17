"""Frida session, script assembly, and structured RPC failures."""

from __future__ import annotations

import logging
import os
from pathlib import Path

# Configure Frida's temporary directory before importing it.
if directory := os.environ.get("ALIENS_MCP_TMP"):
    Path(directory).mkdir(parents=True, exist_ok=True)
    os.environ["TMP"] = os.environ["TEMP"] = str(Path(directory).resolve())

import frida  # noqa: E402

from ..errors import GameAccessDenied, GameError, GameNotRunning
from .windows import running_pid

log = logging.getLogger(__name__)
SCRIPT_FILES = (
    "runtime.js",
    "state.js",
    "decorations.js",
    "managed.js",
    "annotations.js",
    "click.js",
    "effects.js",
    "time.js",
    "scheduler.js",
    "exports.js",
)


def script_source() -> str:
    root = Path(__file__).with_name("scripts")
    protocol = (root / "protocol.js").read_text(encoding="utf-8")
    body = "\n".join((root / name).read_text(encoding="utf-8") for name in SCRIPT_FILES)
    return (
        protocol
        + "\ntry {\n"
        + body
        + "\n} catch (error) { send({event: 'agent_error', error: rpcFailure(error).error}); }"
    )


class FridaTransport:
    def __init__(self, on_event) -> None:
        self._session = None
        self._errors: list[GameError] = []
        self._on_event = on_event
        self.pid = running_pid()
        if self.pid is None:
            raise GameNotRunning()
        try:
            self._session = frida.get_local_device().attach(self.pid)
            self._script = self._session.create_script(script_source())
            self._script.on("message", self._on_message)
            self._script.load()
            if self._errors:
                raise self._errors.pop(0)
        except Exception as error:
            self.close()
            if isinstance(error, frida.PermissionDeniedError):
                raise GameAccessDenied() from error
            if isinstance(error, GameError):
                raise
            if running_pid() != self.pid:
                raise GameNotRunning() from error
            raise GameError("CONNECT_FAILED", detail=str(error)) from error

    @property
    def alive(self) -> bool:
        return self._session is not None and not self._session.is_detached

    @staticmethod
    def _failure(data: dict) -> GameError:
        if diagnostic := data.get("diagnostic"):
            level = (
                logging.ERROR if data.get("code") == "INTERNAL_ERROR" else logging.DEBUG
            )
            log.log(level, "Game script failure: %s", diagnostic)
        code = data.get("code")
        details = data.get("details")
        return GameError(
            code if isinstance(code, str) else "INTERNAL_ERROR",
            **details if isinstance(details, dict) else {},
        )

    def _on_message(self, message: dict, _data) -> None:
        payload = message.get("payload", {})
        if message.get("type") == "error":
            log.debug(
                "Game script error: %s",
                message.get("stack", message.get("description")),
            )
            self._errors.append(GameError("INTERNAL_ERROR"))
        elif message.get("type") == "send" and isinstance(payload, dict):
            if payload.get("event") == "agent_error":
                self._errors.append(self._failure(payload["error"]))
            else:
                self._on_event(payload)

    def call(self, name: str, *args):
        if self._errors:
            raise self._errors.pop(0)
        try:
            result = getattr(self._script.exports_sync, name)(*args)
        except Exception as error:
            if running_pid() != self.pid:
                raise GameNotRunning() from error
            raise GameError("TRANSPORT_FAILED", detail=str(error)) from error
        if isinstance(result, dict) and isinstance(result.get("error"), dict):
            raise self._failure(result["error"])
        return result

    def close(self) -> None:
        if self.alive:
            try:
                if script := getattr(self, "_script", None):
                    script.exports_sync.dispose()
            except Exception:
                log.debug(
                    "Game runtime was already unavailable during cleanup", exc_info=True
                )
            finally:
                session, self._session = self._session, None
                session.detach()
