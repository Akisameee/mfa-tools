"""Build public grids and render table cells, frames, and styles."""

from __future__ import annotations

import unicodedata

from ..errors import GameError, ValidationError
from ..hashes import TOKEN_WIDTH, GlyphIds
from ..models import CellStyle


def page_frame(geometry: dict | None, rows: int, cols: int) -> dict:
    """Where the dividers sit, from Draw's block rectangles.



    `center_line` is the column boundary the vertical rule stands on; the rule under

    the title row spans the full width, and the second rule starts at that boundary.

    """

    if not geometry:
        return {"vertical": None, "horizontal": []}

    vertical = geometry.get("center_line")

    if not vertical or not (0 < vertical < cols):
        vertical = None

    horizontal = []

    title = geometry.get("right_title")

    if title and 0 <= rows - 1 - title[1] < rows - 1:
        horizontal.append([rows - 1 - title[1], 0, cols - 1])

    upper = geometry.get("right_message_u")

    lower = geometry.get("right_message_d")

    if upper and lower and upper[1] != lower[1]:
        boundary = rows - 1 - upper[1]

        if 0 <= boundary < rows - 1:
            horizontal.append(
                [boundary, vertical if vertical else min(upper[0], cols // 2), cols - 1]
            )

    return {"vertical": vertical, "horizontal": horizontal}


def cell_decorations(cell: dict) -> dict:
    """Preserve the actual per-cell rendered state for look and click targets."""

    return CellStyle.from_native(cell).decorations()


def frame_edges(row: int, col: int, frames: list) -> dict | None:

    matches = [
        f
        for f in frames
        if (f[0] != f[2] or f[1] != f[3])
        and f[0] <= row <= f[2]
        and f[1] <= col <= f[3]
    ]

    if not matches:
        return None

    top, left, bottom, right = min(
        matches, key=lambda f: (f[2] - f[0] + 1) * (f[3] - f[1] + 1)
    )

    return {
        "top": row == top,
        "bottom": row == bottom,
        "left": col == left,
        "right": col == right,
    }


def build(data: dict, raw: bool = False) -> dict:

    if "error" in data:
        raise GameError("INTERNAL_ERROR")

    rows = data.get("rows", 9)

    cols = data.get("cols", 24)

    ids = data.get("ids")

    if ids is None and not raw:
        # Pure-Python callers without an Agent still get unique page-local IDs.

        index = GlyphIds()

        index.register(cell["word"] for cell in data["cells"])

        ids = index.by_word

    cells = []

    underlines = []

    for cell in data["cells"]:
        word = cell["word"]

        decoration = cell_decorations(cell)

        if decoration["underlined"]:
            underlines.append([cell["row"], cell["col"]])

        cells.append(
            {
                "id": word if raw else ids[word],
                "col": cell["col"],
                "row": cell["row"],
                "block": cell["block"],
                "note": cell.get("note") or None,
                "dim": decoration["dim"],
                "highlight": decoration["highlight"],
            }
        )

    frames = [list(frame) for frame in data.get("frames", [])]

    boxes = {tuple(position) for position in data.get("boxes", [])}

    boxes.update(
        (top, left)
        for top, left, bottom, right in frames
        if top == bottom and left == right
    )

    return {
        "page": data.get("page"),
        "rows": rows,
        "cols": cols,
        "cells": cells,
        "frame": page_frame(data.get("geometry"), rows, cols),
        "boxes": [list(position) for position in sorted(boxes)],
        "frames": frames,
        "underlines": underlines,
    }


JUNCTIONS = {
    (True, True, True, True): "┼",
    (True, True, False, True): "├",
    (True, True, True, False): "┤",
    (True, False, True, True): "┬",
    (False, True, True, True): "┴",
    (True, True, False, False): "│",
    (False, False, True, True): "─",
    (True, False, False, True): "└",
    (False, True, True, False): "┐",
    (True, False, True, False): "┘",
    (False, True, False, True): "┌",
    (True, False, False, False): "╵",
    (False, True, False, False): "╷",
    (False, False, True, False): "╴",
    (False, False, False, True): "╶",
}


def junction(up: bool, down: bool, left: bool, right: bool) -> str:

    return JUNCTIONS.get((up, down, left, right), "│")


def render(snapshot: dict, style: str = "markdown") -> str:

    renderer = _Renderer()

    if style == "markdown":
        return renderer._render_markdown(snapshot)

    if style == "text":
        return renderer._render_text(snapshot)

    raise ValidationError("INVALID_TABLE_FORMAT")


def _cell_label(cell: dict) -> str:

    return f"{cell['id']}:{cell['note']}" if cell["note"] else cell["id"]


def _escape_markdown(text: str) -> str:

    # Player text must not introduce table columns or decoration delimiters.

    return "".join(
        f"&#{ord(char)};" if char in "&<>\\|{}[]*_~`" or ord(char) < 32 else char
        for char in text
    )


def render_cell(
    cell: dict | None,
    *,
    boxed: bool = False,
    underlined: bool = False,
    frame: dict | None = None,
    escape: bool = True,
) -> str:
    """Shared look/click spelling, escaping, and decoration nesting order."""

    frame = frame or (cell.get("frame") if cell else None)

    label = _cell_label(cell) if cell else " " if boxed or frame else ""

    if escape:
        label = _escape_markdown(label)

    if underlined and label:
        label = f"\\underline{{{label}}}"

    if cell and cell.get("highlight"):
        label = f"\\hl{{{label}}}"

    if cell and cell.get("dim"):
        label = f"\\dim{{{label}}}"

    if boxed:
        label = f"[{label}]"

    if not frame:
        return label

    if frame["top"] and frame["bottom"]:
        return ("[" if frame["left"] else "") + label + ("]" if frame["right"] else "")

    horizontal = frame["top"] or frame["bottom"]

    left = (
        ("┌" if frame["top"] else "└" if frame["bottom"] else "│")
        if frame["left"]
        else "─"
        if horizontal
        else ""
    )

    right = (
        ("┐" if frame["top"] else "┘" if frame["bottom"] else "│")
        if frame["right"]
        else "─"
        if horizontal
        else ""
    )

    return left + label + right


class _Renderer:
    @staticmethod
    def _grid(snapshot: dict) -> list[list[dict | None]]:

        rows, cols = snapshot["rows"], snapshot["cols"]

        table: list[list[dict | None]] = [[None] * cols for _ in range(rows)]

        for cell in snapshot["cells"]:
            if 0 <= cell["row"] < rows and 0 <= cell["col"] < cols:
                table[cell["row"]][cell["col"]] = cell

        return table

    @staticmethod
    def _display_width(text: str) -> int:
        """Terminal width: East Asian wide characters occupy two columns."""

        return sum(
            2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text
        )

    def _render_text(self, snapshot: dict) -> str:

        table = self._grid(snapshot)

        rows, cols = snapshot["rows"], snapshot["cols"]

        frame = snapshot.get("frame") or {}

        boxes = {tuple(position) for position in snapshot.get("boxes", [])}

        underlines = {tuple(position) for position in snapshot.get("underlines", [])}

        labels = [
            [
                render_cell(
                    cell,
                    boxed=(r, c) in boxes,
                    underlined=(r, c) in underlines,
                    frame=frame_edges(r, c, snapshot.get("frames", [])),
                    escape=False,
                )
                for c, cell in enumerate(row)
            ]
            for r, row in enumerate(table)
        ]

        widths = [
            max(
                [TOKEN_WIDTH] + [self._display_width(labels[r][c]) for r in range(rows)]
            )
            for c in range(cols)
        ]

        def pad(text: str, width: int) -> str:

            return text + " " * (width - self._display_width(text))

        vertical = frame.get("vertical")

        separators = []

        for index in range(cols + 1):
            separators.append("   " if vertical == index else "  ")

        def join(cells: list[str], row_index: int) -> str:

            out = [cells[0]]

            for index in range(1, cols):
                # the divider only exists below the title rule

                if separators[index] == "   " and row_index > 0:
                    out.append(" │ ")

                else:
                    out.append(separators[index])

                out.append(cells[index])

            return "".join(out)

        def rule(filled) -> str:

            cells = [
                "─" * widths[c] if filled(c) else " " * widths[c] for c in range(cols)
            ]

            out = [cells[0]]

            for index in range(1, cols):
                sep = separators[index]

                if filled(index - 1) and filled(index):
                    out.append("─" * len(sep))

                else:
                    out.append(" " * len(sep))

                out.append(cells[index])

            return "".join(out).rstrip()

        header = "    " + join(
            [pad(f"{col:>{TOKEN_WIDTH}}", widths[col]) for col in range(cols)], 0
        )

        lines = [header.rstrip()]

        rules: dict[int, list[tuple[int, int]]] = {}

        for after, start, end in frame.get("horizontal", []):
            rules.setdefault(after, []).append((start, end))

        for row_index, row in enumerate(labels):
            body = join(
                [pad(text, widths[col]) for col, text in enumerate(row)], row_index
            )

            lines.append(f"r{row_index}  " + body.rstrip())

            for start, end in rules.get(row_index, []):
                lines.append("    " + rule(lambda c, s=start, e=end: s <= c <= e))

        return "\n".join(lines)

    def _render_markdown(self, snapshot: dict) -> str:
        """One table, with the game's dividers drawn inside it.



        Not strict Markdown: the vertical divider becomes a narrow `│` column and

        the horizontal ones become `───` rows, so the model sees the table and the

        layout at the same time. Single-cell frames use `[...]`; multirow frames

        retain their corners and sides, including empty slots.

        """

        table = self._grid(snapshot)

        cols = snapshot["cols"]

        frame = snapshot.get("frame") or {}

        boxes = {(row, col) for row, col in snapshot.get("boxes", [])}

        underlined = {(row, col) for row, col in snapshot.get("underlines", [])}

        vertical = frame.get("vertical")

        rules: dict[int, list[tuple[int, int]]] = {}

        for after, start, end in frame.get("horizontal", []):
            rules.setdefault(after, []).append((start, end))

        head = []

        for col in range(cols):
            if vertical == col:
                head.append("│")

            head.append(str(col))

        lines = ["| row/col | " + " | ".join(head) + " |"]

        lines.append("|" + "---|" * (len(head) + 1))

        for row_index, row in enumerate(table):
            cells = []

            for col in range(cols):
                if vertical == col:
                    # the divider runs the whole page height, so its column is a

                    # plain vertical segment wherever no horizontal rule meets it

                    cells.append("│")

                cell = row[col]

                boxed = (row_index, col) in boxes

                underlined_here = (row_index, col) in underlined

                cells.append(
                    render_cell(
                        cell,
                        boxed=boxed,
                        underlined=underlined_here,
                        frame=frame_edges(row_index, col, snapshot.get("frames", [])),
                    )
                )

            lines.append(f"| {row_index} | " + " | ".join(cells) + " |")

            for start, end in rules.get(row_index, []):
                cells = []

                for col in range(cols):
                    inside = start <= col <= end

                    if vertical == col:
                        # the vertical passes through this row, so it always has

                        # both arms; the rule supplies the horizontal ones

                        cells.append(
                            junction(
                                up=True,
                                down=True,
                                left=start <= vertical - 1,
                                right=end >= vertical,
                            )
                        )

                    cells.append("───" if inside else "")

                lines.append("|  | " + " | ".join(cells) + " |")

        return "\n".join(lines)
