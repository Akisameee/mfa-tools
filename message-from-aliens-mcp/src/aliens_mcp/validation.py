"""Public request validation, before attaching to the game."""

from __future__ import annotations

import math

from .errors import ValidationError
from .hashes import TOKEN_WIDTH


def validate_click(row: int, col: int, button: str) -> None:
    if type(row) is not int or not 0 <= row < 9:
        raise ValidationError("INVALID_ROW")
    if type(col) is not int or not 0 <= col < 24:
        raise ValidationError("INVALID_COL")
    if button not in ("left", "right"):
        raise ValidationError("INVALID_BUTTON")


def validate_hash(token: str) -> None:
    if (
        not isinstance(token, str)
        or len(token) != TOKEN_WIDTH
        or any(c not in "0123456789abcdefghijklmnopqrstuvwxyz" for c in token)
    ):
        raise ValidationError("INVALID_HASH")


def validate_note(token: str, text: str) -> None:
    validate_hash(token)
    if not isinstance(text, str):
        raise ValidationError("INVALID_TEXT_TYPE")
    if any(char in text for char in "\r\n\0"):
        raise ValidationError("INVALID_TEXT_LINE")
    try:
        length = len(text.encode("utf-16-le")) // 2
    except UnicodeEncodeError as error:
        raise ValidationError("INVALID_TEXT_LINE") from error
    if length > 49:
        raise ValidationError("INVALID_TEXT_LENGTH")


def validate_seconds(seconds: float) -> None:
    if (
        type(seconds) not in (int, float)
        or not math.isfinite(seconds)
        or not 0.001 <= seconds <= 86400
    ):
        raise ValidationError("INVALID_SECONDS")
