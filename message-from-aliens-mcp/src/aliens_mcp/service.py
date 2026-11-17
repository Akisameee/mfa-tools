"""Tool operations: session state, opaque hashes, validation, and public receipts."""

from __future__ import annotations

import builtins
import threading
from typing import Literal

from .errors import ValidationError
from .game import GameClient
from .hashes import GlyphIds
from .messages import closed_click, unchanged
from .models import CellStyle, ClickResult
from .recording import observe_table
from .rendering.table import build, render
from .validation import validate_click, validate_hash, validate_note, validate_seconds


class GameService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._client: GameClient | None = None
        self._look_cache: dict[str, tuple] = {}
        self.recording_connection = 0
        self._reset_hashes()

    def _reset_hashes(self) -> None:
        self._glyph_ids = GlyphIds()
        self._catalogue_loaded = False

    def reset_session(self) -> None:
        with self._lock:
            self.recording_connection += 1
            self._look_cache.clear()
            self._reset_hashes()
            current, self._client = self._client, None
            if current is not None:
                current.close()

    def client(self) -> GameClient:
        if self._client is None or not self._client.alive:
            self.reset_session()
            self._client = GameClient()
        return self._client

    def _load_catalogue(self) -> None:
        if not self._catalogue_loaded:
            self._glyph_ids.register(self.client().vocabulary())
            self._catalogue_loaded = True

    def _snapshot(self) -> dict:
        client = self.client()
        self._load_catalogue()
        data = client.snapshot()
        self._glyph_ids.register(cell["word"] for cell in data.get("cells", []))
        return {
            **data,
            "ids": {
                cell["word"]: self._glyph_ids.by_word[cell["word"]]
                for cell in data.get("cells", [])
            },
        }

    def _word_for_hash(self, token: str) -> str:
        self._snapshot()  # Includes generated characters on the current page.
        word = self._glyph_ids.by_id.get(token)
        if word is None:
            raise ValidationError("UNKNOWN_HASH", hash=token)
        return word

    def recording_snapshot(self) -> tuple[dict | None, int]:
        """Read without connecting, touching look caches, or assigning new public hashes."""
        with self._lock:
            client = self._client
            if client is None or not client.alive:
                return None, self.recording_connection
            data = client.snapshot()
            ids = {
                cell["word"]: self._glyph_ids.by_word[cell["word"]]
                for cell in data.get("cells", [])
                if cell["word"] in self._glyph_ids.by_word
            }
            return {**data, "ids": ids}, self.recording_connection

    def recording_character(self, token) -> dict | None:
        with self._lock:
            if isinstance(token, str) and token in self._glyph_ids.by_id:
                return {"hash": token, "key": self._glyph_ids.by_id[token]}
            return None

    def _public_target(self, raw: dict | None) -> dict | None:
        if not isinstance(raw, dict):
            return None
        style = CellStyle.from_native(raw)
        if raw.get("empty") is True:
            return {
                "empty": True,
                "boxed": style.boxed,
                **({"frame": style.frame} if style.frame else {}),
            }
        word = raw.get("word")
        if not isinstance(word, str) or not word:
            return None
        self._glyph_ids.register([word])
        return {
            "id": self._glyph_ids.by_word[word],
            "note": raw.get("note") or None,
            **style.target_fields(),
        }

    def look_json(self, raw: bool = False) -> dict:
        with self._lock:
            data = self._snapshot()
            observe_table(data, self.recording_connection)
            return build(data, raw=raw)

    def look(
        self,
        type: Literal["table", "screenshot"] = "table",
        *,
        raw: bool = False,
        force: bool = False,
    ):
        if type not in ("table", "screenshot"):
            raise ValidationError("INVALID_LOOK_TYPE")
        if builtins.type(force) is not bool:
            raise ValidationError("INVALID_FORCE")
        with self._lock:
            # Read before comparing, so cache hits cannot conceal game failures.
            if type == "screenshot":
                result = self.client().screenshot()
                key = result.comparison_key()
            else:
                snapshot = self.look_json(raw=raw)
                result = render(snapshot)
                key = (snapshot.get("page"), result)
            identical = self._look_cache.get(type) == key
            self._look_cache[type] = key
            return unchanged(type) if identical and not force else result

    def click(
        self, row: int, col: int, type: Literal["left", "right"] = "left"
    ) -> dict:
        validate_click(row, col, type)
        with self._lock:
            client = self.client()
            self._load_catalogue()
            native = client.click(row, col, type)
            target = self._public_target(native.get("target"))
            receipt = ClickResult(
                row=row,
                col=col,
                button=type,
                ok=native["ok"],
                game_running=native.get("game_running", True),
                target=target,
                event=native.get("event"),
                click_status=native.get("click_status"),
                urls=native.get("urls"),
                opened=native.get("opened"),
            ).as_dict()
            if receipt["game_running"] is False:
                receipt["message"] = closed_click(
                    receipt.get("click_status") == "quit_requested"
                )
                receipt["next_tool"] = "launch_game"
                self.reset_session()
            return receipt

    def launch_game(self) -> dict:
        with self._lock:
            previous = self._client
            try:
                current, receipt = GameClient.launch(previous)
            except Exception:
                self.reset_session()
                raise
            if current is not previous:
                self.recording_connection += 1
                self._look_cache.clear()
                self._reset_hashes()
            self._client = current
            return receipt

    def status(self) -> dict:
        with self._lock:
            return self.client().status()

    def note(self, hash: str, text: str) -> dict:
        validate_note(hash, text)
        with self._lock:
            result = self.client().note(self._word_for_hash(hash), text)
            return {"ok": result["ok"], "hash": hash, "text": result["text"]}

    def wait(self, seconds: float) -> dict:
        validate_seconds(seconds)
        with self._lock:
            result = self.client().wait(seconds)
            return {"ok": result["ok"], "seconds": result["seconds"]}

    def glyph(self, hash: str, format: Literal["ascii", "paths", "image"] = "image"):
        from .rendering.glyph import coordinates, image, rasterize

        validate_hash(hash)
        if format not in ("ascii", "paths", "image"):
            raise ValidationError("INVALID_GLYPH_FORMAT")
        with self._lock:
            paths = self.client().glyph(self._word_for_hash(hash))
        if format == "paths":
            return coordinates(paths, hash)
        return image(paths) if format == "image" else rasterize(paths)
