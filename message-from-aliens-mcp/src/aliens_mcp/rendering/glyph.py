"""Three views of the game's vector paths; no screenshots or semantic labels."""

from __future__ import annotations

import math
from io import BytesIO

from ..errors import ValidationError

Point = tuple[float, float]
Paths = list[list[Point]]


def normalize(paths: list) -> Paths:
    """Fit into 0..100, preserving aspect ratio, with x right and y down."""
    if any(
        len(point) != 2 or not all(math.isfinite(v) for v in point)
        for path in paths
        for point in path
    ):
        raise ValidationError("INVALID_GLYPH_PATHS")
    points = [point for path in paths for point in path]
    if not points:
        return [[] for path in paths]
    xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
    ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
    span = max(xmax - xmin, ymax - ymin)
    scale = 100 / span if span else 1
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    return [
        [((x - cx) * scale + 50, (cy - y) * scale + 50) for x, y in path]
        for path in paths
    ]


def coordinates(paths: list, hash: str) -> dict:
    return {
        "hash": hash,
        "canvas": [100, 100],
        "origin": "top-left",
        "x_direction": "right",
        "y_direction": "down",
        "paths": [
            [[round(x, 9), round(y, 9)] for x, y in path] for path in normalize(paths)
        ],
    }


def _segments(paths: Paths) -> list[tuple[Point, Point]]:
    # Do not close open paths. A one-point path is a dot.
    return [
        segment
        for path in paths
        for segment in ([(path[0], path[0])] if len(path) == 1 else zip(path, path[1:]))
    ]


def _point_distance(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2 if length2 else 0
    t = max(0, min(1, t))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _cross(a: Point, b: Point, p: Point) -> float:
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def _detail(paths: Paths) -> float:
    """Smallest positive segment length or distance between disjoint segments.

    True crossings/touches stay connected. Ignore float32-sized noise near joins.
    A finite output-size cap handles exceptionally small gaps.
    """
    segments = _segments(paths)
    distances = [math.dist(a, b) for a, b in segments]
    for i, (a, b) in enumerate(segments):
        for c, d in segments[i + 1 :]:
            distance = min(
                _point_distance(a, c, d),
                _point_distance(b, c, d),
                _point_distance(c, a, b),
                _point_distance(d, a, b),
            )
            crossing = (
                _cross(a, b, c) * _cross(a, b, d) < 0
                and _cross(c, d, a) * _cross(c, d, b) < 0
            )
            if not crossing:
                distances.append(distance)
    return min((d for d in distances if d > 1e-4), default=100)


def rasterize(paths: list) -> str:
    """Adaptive spaces/# grid, at least 10x10, at most 241 columns x 121 rows.

    Columns are half a row high visually. Increase resolution to leave space
    between nearby segments; rasterization cannot preserve arbitrarily tiny gaps.
    """
    paths = normalize(paths)
    points = [p for path in paths for p in path]
    if not points:
        return "\n".join(" " * 10 for _ in range(10))
    xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
    ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
    xspan, yspan = xmax - xmin, ymax - ymin
    scale = min(max(0.07, 3 / _detail(paths)), 1.18)
    width = max(10, min(241, math.ceil(xspan * scale * 2) + 5))
    height = max(10, min(121, math.ceil(yspan * scale) + 3))
    ox, oy = (width - 1) * 0.25, (height - 1) * 0.5
    strokes = _segments(
        [
            [((x - 50) * scale + ox, (y - 50) * scale + oy) for x, y in path]
            for path in paths
        ]
    )
    pixels = [[" "] * width for _ in range(height)]
    # Cover even a dot halfway between rows/columns on a 1:2 cell grid.
    radius = 0.56
    for a, b in strokes:
        x0 = max(0, math.floor(2 * (min(a[0], b[0]) - radius)))
        x1 = min(width - 1, math.ceil(2 * (max(a[0], b[0]) + radius)))
        y0 = max(0, math.floor(min(a[1], b[1]) - radius))
        y1 = min(height - 1, math.ceil(max(a[1], b[1]) + radius))
        for row in range(y0, y1 + 1):
            for col in range(x0, x1 + 1):
                if _point_distance((col * 0.5, row), a, b) <= radius:
                    pixels[row][col] = "#"
    return "\n".join("".join(row) for row in pixels)


def image(paths: list) -> bytes:
    """Antialiased black paths on white, fixed 64x64 PNG, two-pixel strokes."""
    from PIL import Image, ImageDraw

    paths = normalize(paths)
    size = 64
    supersampling = 4
    canvas = Image.new("L", (size * supersampling,) * 2, 255)
    draw = ImageDraw.Draw(canvas)
    margin = size / 16
    scale = (size - margin * 2) / 100
    width = 2 * supersampling
    radius = width / 2
    for path in paths:
        points = [
            ((x * scale + margin) * supersampling, (y * scale + margin) * supersampling)
            for x, y in path
        ]
        if len(points) > 1:
            draw.line(points, fill=0, width=width, joint="curve")
        for x, y in points:
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=0)
    canvas = canvas.resize((size, size), Image.Resampling.LANCZOS)
    output = BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()
