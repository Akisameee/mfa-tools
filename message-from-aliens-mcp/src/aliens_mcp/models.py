"""Data exchanged between game interaction, service, and rendering layers."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO


@dataclass(frozen=True)
class CellStyle:
    underlined: bool = False
    dim: bool = False
    highlight: bool = False
    boxed: bool = False
    frame: dict[str, bool] | None = None

    @classmethod
    def from_native(cls, cell: dict) -> CellStyle:
        frame = cell.get("frame")
        return cls(
            underlined=bool(cell.get("underlined")),
            dim=bool(cell.get("dim")),
            highlight=bool(cell.get("highlight")),
            boxed=bool(cell.get("boxed")),
            frame={
                key: bool(frame.get(key)) for key in ("top", "bottom", "left", "right")
            }
            if frame
            else None,
        )

    def decorations(self) -> dict:
        return {key: getattr(self, key) for key in ("underlined", "dim", "highlight")}

    def target_fields(self) -> dict:
        return {
            **self.decorations(),
            "boxed": self.boxed,
            **({"frame": self.frame} if self.frame else {}),
        }


@dataclass(frozen=True)
class ClickResult:
    row: int
    col: int
    button: str
    ok: bool
    game_running: bool
    target: dict | None
    event: str | None = None
    click_status: str | None = None
    urls: list[str] | None = None
    opened: bool | None = None

    def as_dict(self) -> dict:
        result = {
            "ok": self.ok,
            "row": self.row,
            "col": self.col,
            "type": self.button,
            "game_running": self.game_running,
            "target": self.target,
        }
        for key in ("event", "click_status", "urls", "opened"):
            if (value := getattr(self, key)) is not None:
                result[key] = value
        return result


@dataclass(frozen=True)
class Screenshot:
    data: bytes
    width: int
    height: int
    client_width: int
    client_height: int
    bordered: bool

    def comparison_key(self) -> tuple:
        """Exact displayed pixels and metadata, independent of PNG encoding."""
        from PIL import Image

        with Image.open(BytesIO(self.data)) as picture:
            return (
                self.width,
                self.height,
                self.client_width,
                self.client_height,
                self.bordered,
                picture.size,
                picture.convert("RGB").tobytes(),
            )
