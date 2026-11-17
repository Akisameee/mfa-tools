"""Optional, private MCP timeline and native-grid recording. No image resources."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import __version__

log = logging.getLogger(__name__)
_active_call: ContextVar[RecordedCall | None] = ContextVar(
    "recorded_call", default=None
)
MUTATING_TOOLS = frozenset(("click", "note", "wait", "launch_game"))


def _json(value) -> str:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _safe_value(value):
    """Keep protocol text/structured data, omitting image payloads at any depth."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(value, dict):
        if value.get("type") == "image":
            return {"type": "image", "mimeType": value.get("mimeType"), "omitted": True}
        return {str(k): _safe_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_safe_value(v) for v in value]
    if isinstance(value, bytes):
        return {"omitted": True, "byte_length": len(value)}
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": str(value)}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return {"type": type(value).__name__, "omitted": True}


def _error(error: Exception) -> dict:
    result = {"type": type(error).__name__, "message": str(error)}
    seen = set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if hasattr(current, "code"):
            result.update(code=current.code, details=_safe_value(current.details))
            break
        current = current.__cause__
    return result


@dataclass
class RecordedCall:
    name: str
    arguments: dict
    id: str
    snapshot: dict | None = None
    connection: int | None = None


def observe_table(snapshot: dict, connection: int) -> None:
    """Reuse only an explicit table look; hash resolution during glyph/note is not a frame."""
    call = _active_call.get()
    if (
        call is not None
        and call.name == "look"
        and call.arguments.get("type", "table") == "table"
    ):
        call.snapshot, call.connection = snapshot, connection


class Recorder:
    def __init__(self, directory: Path) -> None:
        self.enabled = True
        self.directory = directory
        self._seq = 0
        self._calls = 0
        self._started_ns = time.monotonic_ns()
        self._elapsed_offset = 0
        self._state_ref = None
        self._states = set()
        self._connections = {}
        self._last_connection = 0
        self._read_offset = 0
        directory.mkdir(parents=True, exist_ok=True)
        self.refresh()

    def close(self) -> None:
        """Disable this recorder without affecting the game tools."""
        self.enabled = False

    def refresh(self) -> None:
        """Resume counters from new log entries before the next call."""
        directory = self.directory
        (directory / "states").mkdir(exist_ok=True)
        manifest = directory / "manifest.json"
        if manifest.exists():
            if json.loads(manifest.read_text(encoding="utf-8"))["schema_version"] != 1:
                raise ValueError("Unsupported recording schema")
        else:
            self._write_manifest(manifest)
        events = directory / "events.jsonl"
        if not events.exists():
            return
        last = None
        with events.open("rb+") as stream:
            stream.seek(self._read_offset)
            while True:
                offset = stream.tell()
                line = stream.readline()
                if not line:
                    break
                try:
                    event = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    if line.endswith(b"\n"):
                        raise
                    # Only an interrupted final line may be discarded.
                    stream.truncate(offset)
                    stream.seek(offset)
                    break
                self._seq = max(self._seq, event["seq"])
                self._calls = max(self._calls, int(event["call_id"]))
                self._last_connection = max(
                    self._last_connection, event.get("connection") or 0
                )
                last = event
                if not line.endswith(b"\n"):
                    stream.write(b"\n")
                    break
            self._read_offset = stream.tell()
        if last is not None:
            self._state_ref = None
            downtime = datetime.now(timezone.utc) - datetime.fromisoformat(last["at"])
            self._elapsed_offset = last["elapsed_ns"] + max(
                0, int(downtime.total_seconds() * 1_000_000_000)
            )
            self._started_ns = time.monotonic_ns()

    def _write_manifest(self, path: Path) -> None:
        metadata = {
            "schema_version": 1,
            "mcp_version": __version__,
            "recording_id": self.directory.name,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "time_unit": "nanoseconds",
            "state_format": "native-grid-with-known-ids",
            "images": False,
            "glyph_paths": False,
            "conversation_text": False,
        }
        path.write_text(_json(metadata) + "\n", encoding="utf-8")

    @classmethod
    def from_environment(cls) -> Recorder | None:
        if os.environ.get("ALIENS_MCP_RECORD") != "1":
            return None
        try:
            root = (
                Path(os.environ.get("ALIENS_MCP_RECORD_DIR", "recordings"))
                .expanduser()
                .resolve()
            )
            return cls(root)
        except Exception:
            log.exception("Recording could not start; game tools remain available")
            return None

    def _disable(self) -> None:
        self.close()
        log.exception("Recording failed and was disabled; tool execution is unchanged")

    def _append(self, kind: str, **fields) -> None:
        self._seq += 1
        event = {
            "seq": self._seq,
            "kind": kind,
            "at": datetime.now(timezone.utc).isoformat(),
            "elapsed_ns": self._elapsed_ns(),
            **fields,
        }
        with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(_json(event) + "\n")
            stream.flush()
            self._read_offset = stream.tell()

    def _elapsed_ns(self) -> int:
        return self._elapsed_offset + time.monotonic_ns() - self._started_ns

    def _connection(self, local: int) -> int:
        if local not in self._connections:
            self._last_connection += 1
            self._connections[local] = self._last_connection
        return self._connections[local]

    def begin(self, name: str, arguments: dict, request_id=None) -> RecordedCall:
        self._calls += 1
        call = RecordedCall(name, arguments, str(self._calls))
        try:
            self._append(
                "call.begin",
                call_id=call.id,
                tool=name,
                arguments=_safe_value(arguments),
                request_id=request_id,
                state_ref=self._state_ref,
            )
        except Exception:
            self._disable()
        return call

    def _save_state(self, snapshot: dict, connection: int) -> str:
        encoded = _json({"connection": connection, "snapshot": snapshot})
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        if digest not in self._states:
            path = self.directory / "states" / (digest + ".json")
            if not path.exists():
                temporary = path.with_suffix(".tmp")
                temporary.write_text(encoded + "\n", encoding="utf-8")
                temporary.replace(path)
            self._states.add(digest)
        return "states/" + digest + ".json"

    def finish(
        self, call: RecordedCall, service, result=None, error: Exception | None = None
    ) -> None:
        if not self.enabled:
            return
        try:
            # Mark tool completion separately from the optional extra read.
            completed_at = datetime.now(timezone.utc).isoformat()
            completed_ns = self._elapsed_ns()
            snapshot, connection = call.snapshot, call.connection
            capture = "reused" if snapshot is not None else "not_requested"
            capture_error = None
            if call.name in MUTATING_TOOLS:
                try:
                    snapshot, connection = service.recording_snapshot()
                    capture = "captured" if snapshot is not None else "unavailable"
                except Exception as caught:
                    capture, capture_error = "failed", _error(caught)
            observed = snapshot is not None
            connection = self._connection(
                connection if observed else service.recording_connection
            )
            if observed:
                self._state_ref = self._save_state(snapshot, connection)
            elif call.name in MUTATING_TOOLS:
                # Never present an old frame as a fresh observation after failure/exit.
                self._state_ref = None
            failed = error is not None or bool(
                getattr(result, "is_error", getattr(result, "isError", False))
            )
            character = service.recording_character(call.arguments.get("hash"))
            if error is not None:
                saved_result = None
            elif call.name == "glyph":
                saved_result = {
                    "omitted": True,
                    "format": call.arguments.get("format", "image"),
                }
            else:
                saved_result = _safe_value(result)
            self._append(
                "call.end",
                call_id=call.id,
                tool=call.name,
                status="error" if failed else "ok",
                result=saved_result,
                error=_error(error) if error is not None else None,
                completed_at=completed_at,
                completed_elapsed_ns=completed_ns,
                connection=connection,
                state_ref=self._state_ref,
                state_observed=observed,
                capture=capture,
                capture_error=capture_error,
                character=character,
            )
        except Exception:
            self._disable()


def bind_call(call: RecordedCall):
    return _active_call.set(call)


def unbind_call(token) -> None:
    _active_call.reset(token)
