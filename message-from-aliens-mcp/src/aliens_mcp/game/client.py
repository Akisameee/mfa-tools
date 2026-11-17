"""Single entry point for game operations; no public hashes or output wording."""

from __future__ import annotations

import threading
import time
from typing import Literal

from ..errors import GameAccessDenied, GameError
from . import windows
from .capture import capture
from .transport import FridaTransport


class GameClient:
    def __init__(self) -> None:
        self._click_id = 0
        self._click_target = None
        self._quit_requested = threading.Event()
        self._transport = FridaTransport(self._on_event)

    @property
    def pid(self) -> int:
        return self._transport.pid

    @property
    def alive(self) -> bool:
        return self._transport.alive

    def _call(self, name: str, *args):
        return self._transport.call(name, *args)

    @classmethod
    def launch(cls, current: GameClient | None = None) -> tuple[GameClient, dict]:
        started = windows.running_pid() is None
        if started:
            if current:
                current.close()
            current = None
            windows.request_launch()
        deadline = time.monotonic() + 45
        last_error = GameError("PAGE_NOT_READY")
        while time.monotonic() < deadline:
            try:
                pid = windows.running_pid()
                if pid is None:
                    time.sleep(0.25)
                    continue
                windows.game_window(pid)
                if current is None or not current.alive or current.pid != pid:
                    if current:
                        current.close()
                    current = cls()
                current._call("ping")
                windows.game_window(current.pid)
                if current.snapshot().get("cells"):
                    return current, {
                        "ok": True,
                        "game_running": True,
                        "ready": True,
                        "started": started,
                        "pid": current.pid,
                    }
                last_error = GameError("PAGE_NOT_READY")
            except GameAccessDenied:
                if current:
                    current.close()
                raise
            except GameError as error:
                last_error = error
                if current:
                    current.close()
                current = None
            time.sleep(0.25)
        if current:
            current.close()
        raise GameError("LAUNCH_TIMEOUT", detail=str(last_error))

    def snapshot(self) -> dict:
        return self._call("snapshot")

    def screenshot(self):
        return capture(self.pid)

    def vocabulary(self) -> list[str]:
        return self._call("glyphWords")

    def glyph(self, character: str) -> list:
        return self._call("glyphPaths", character)

    def status(self) -> dict:
        self._call("ping")
        return {"pid": self.pid, "backend": "frida", "runtime": self._call("runtime")}

    def _on_event(self, payload: dict) -> None:
        if payload.get("request_id") != self._click_id:
            return
        if payload.get("event") == "game_quit_requested":
            self._quit_requested.set()
        elif payload.get("event") == "click_target":
            self._click_target = payload.get("target")

    def _with_click_target(self, result: dict) -> dict:
        return {**result, "target": result.get("target") or self._click_target}

    def _wait_for_exit(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while windows.running_pid() == self.pid:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)
        return True

    def _closed_click(self) -> dict:
        confirmed = self._quit_requested.is_set()
        return self._with_click_target(
            {
                "ok": confirmed,
                "event": "game_closed",
                "game_running": False,
                "click_status": "quit_requested" if confirmed else "unconfirmed",
            }
        )

    def click(
        self, row: int, col: int, button: Literal["left", "right"] = "left"
    ) -> dict:
        window, thread = windows.game_window(self.pid)
        self._click_id += 1
        self._click_target = None
        self._quit_requested.clear()
        try:
            result = self._call(
                "click", row, col, button, thread, hex(window), self._click_id
            )
        except GameError:
            if self._quit_requested.is_set() or not self.alive:
                if self._quit_requested.is_set():
                    # Release the attached managed worker before Unity shutdown.
                    self.close()
                if self._wait_for_exit(15 if self._quit_requested.is_set() else 5):
                    return self._closed_click()
            if windows.running_pid() != self.pid:
                return self._closed_click()
            raise
        if self._quit_requested.is_set():
            self.close()
            if self._wait_for_exit(15):
                return self._closed_click()
            raise GameError("QUIT_UNCONFIRMED")
        if self._wait_for_exit(0.15):
            return self._closed_click()
        return self._with_click_target({**result, "game_running": True})

    def note(self, character: str, text: str) -> dict:
        window, thread = windows.game_window(self.pid)
        return self._call("note", character, text, thread, hex(window))

    def wait(self, seconds: float) -> dict:
        window, thread = windows.game_window(self.pid)
        return self._call("wait", seconds, thread, hex(window))

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> GameClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
