"""Typed failures with stable codes; wording belongs to messages.py."""

from __future__ import annotations


class GameError(RuntimeError):
    def __init__(self, code: str, **details) -> None:
        self.code, self.details = code, details
        super().__init__(code)

    def __str__(self) -> str:
        from .messages import error_text

        return error_text(self.code, **self.details)


class GameAccessDenied(GameError):
    def __init__(self) -> None:
        super().__init__("ACCESS_DENIED")


class GameNotRunning(GameError):
    def __init__(self) -> None:
        super().__init__("GAME_NOT_RUNNING")


class ValidationError(ValueError):
    def __init__(self, code: str, **details) -> None:
        self.code, self.details = code, details
        super().__init__(code)

    def __str__(self) -> str:
        from .messages import error_text

        return error_text(self.code, **self.details)
