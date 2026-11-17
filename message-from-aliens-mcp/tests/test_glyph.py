"""Geometry, adaptive resolution, token lookup, and actual MCP image encoding."""

import asyncio
import base64
import json
import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image
from support import ServiceTestCase, mock_game, service

from aliens_mcp import tools
from aliens_mcp.rendering.glyph import coordinates, image, rasterize

SAMPLE = [
    [[0.5, 0.5], [-0.5, 0.5], [-0.5, -0.5], [0.5, -0.5]],
    [[0, 0.125], [-0.25, -0.125], [0.25, -0.125], [0, 0.125]],
    [[-0.25, 0.125], [0.25, 0.125]],
]


class GlyphTests(ServiceTestCase):
    def test_normalization_preserves_aspect_direction_and_path_boundaries(self):
        result = coordinates(SAMPLE, "qrag")
        self.assertEqual(
            result["paths"],
            [
                [[100, 0], [0, 0], [0, 100], [100, 100]],
                [[50, 37.5], [25, 62.5], [75, 62.5], [50, 37.5]],
                [[25, 37.5], [75, 37.5]],
            ],
        )
        self.assertEqual(
            coordinates([[[2, 0], [2, 4], [4, 4]]], "qrag")["paths"],
            [[[25, 100], [25, 0], [75, 0]]],
        )

    def test_ascii_grows_for_close_strokes_and_keeps_a_blank_gap(self):
        simple = rasterize([[[0, 0], [0, 10]], [[10, 0], [10, 10]]]).splitlines()
        dense = rasterize(
            [[[0, 0], [0, 10]], [[1, 0], [1, 10]], [[10, 0], [10, 10]]]
        ).splitlines()
        self.assertGreater(len(dense), len(simple))
        self.assertGreater(len(dense[0]), len(simple[0]))
        # Three distinct vertical runs, including the nearby pair.
        self.assertEqual(len(dense[len(dense) // 2].split()), 3)
        self.assertLessEqual(len(dense), 121)
        self.assertLessEqual(len(dense[0]), 241)
        self.assertEqual(set("\n".join(dense)), {" ", "#", "\n"})

    def test_ascii_does_not_close_open_frame(self):
        lines = rasterize(SAMPLE[:1]).splitlines()
        self.assertEqual(lines[len(lines) // 2].count("#"), 2)
        middle = lines[len(lines) // 2]
        self.assertGreater(len(middle) - len(middle.rstrip()), len(middle) // 2)

    def test_degenerate_and_blank_glyphs_are_supported(self):
        for paths in ([], [[]], [[[3, 8]]], [[[3, 8], [3, 8]]]):
            with self.subTest(paths=paths):
                text = rasterize(paths)
                self.assertEqual(len(text.splitlines()), 10)
                self.assertEqual({len(row) for row in text.splitlines()}, {10})
                if paths and paths[0]:
                    self.assertIn("#", text)
                png = Image.open(BytesIO(image(paths)))
                self.assertEqual(png.size, (64, 64))
                self.assertEqual(
                    png.getpixel((32, 32)), 0 if paths and paths[0] else 255
                )

    def test_png_keeps_frame_open_and_preserves_vertical_orientation(self):
        png = Image.open(BytesIO(image([[[1, 1], [-1, 1], [-1, -1]]])))
        self.assertEqual(png.format, "PNG")
        self.assertLess(png.getpixel((4, 32)), 32)  # left edge
        self.assertLess(png.getpixel((32, 4)), 32)  # top edge
        self.assertEqual(png.getpixel((60, 32)), 255)  # no closing diagonal
        self.assertEqual(png.getpixel((32, 60)), 255)  # no bottom edge
        self.assertEqual(png.getpixel((0, 0)), 255)

    def test_png_is_always_small_and_has_two_pixel_strokes_without_dpi_metadata(self):
        for paths in (
            SAMPLE,
            [[[0, 0], [0, 100]], [[0.01, 0], [0.01, 100]], [[100, 0], [100, 100]]],
        ):
            png = Image.open(BytesIO(image(paths)))
            self.assertEqual(png.size, (64, 64))
            self.assertNotIn("dpi", png.info)
        png = Image.open(BytesIO(image([[[0, -1], [0, 1]]])))
        self.assertGreaterEqual(sum(png.getpixel((x, 32)) < 96 for x in range(64)), 2)

    def test_nonfinite_geometry_is_rejected(self):
        for paths in ([[[float("nan"), 0]]], [[[0, float("inf")]]], [[[1]]]):
            for renderer in (rasterize, image):
                with (
                    self.subTest(paths=paths, renderer=renderer),
                    self.assertRaises(ValueError),
                ):
                    renderer(paths)

    def test_invalid_public_requests_do_not_attach(self):
        with patch.object(service, "client") as attach:
            for token in (None, "", "AB12", "123", "12345", "ab/1", "科学", "slqrag"):
                with self.subTest(token=token), self.assertRaises(ValueError):
                    tools.glyph(token)
            for format in (None, "svg", [], "IMAGE"):
                with self.subTest(format=format), self.assertRaises(ValueError):
                    tools.glyph("qrag", format)
            attach.assert_not_called()

    def test_token_lookup_registers_generated_words_and_rejects_unknown_ids(self):
        from aliens_mcp.hashes import word_id

        runtime = mock_game()
        runtime.vocabulary.return_value = ["private-word"]
        runtime.snapshot.return_value = {"cells": [{"word": "generated-word"}]}
        runtime.glyph.return_value = SAMPLE
        with patch.object(service, "client", return_value=runtime):
            self.assertEqual(
                service.glyph(word_id("generated-word"), "paths")["hash"],
                word_id("generated-word"),
            )
            with self.assertRaisesRegex(ValueError, "Unknown glyph hash"):
                service.glyph("0000")
        runtime.glyph.assert_called_once_with("generated-word")
        self.assertEqual(runtime.vocabulary.call_count, 1)

    def test_look_and_glyph_share_catalogue_ids_for_colliding_words(self):
        runtime = mock_game()
        runtime.vocabulary.return_value = ["sweet", "hide"]
        runtime.snapshot.return_value = {
            "cells": [{"word": "sweet", "row": 1, "col": 0, "block": "left_text"}]
        }
        runtime.glyph.return_value = SAMPLE
        with patch.object(service, "client", return_value=runtime):
            token = service.look_json()["cells"][0]["id"]
            self.assertEqual(len(token), 4)
            self.assertNotEqual(token, service._glyph_ids.by_word["hide"])
            self.assertEqual(
                service.glyph(token, "paths")["paths"],
                coordinates(SAMPLE, token)["paths"],
            )
        runtime.glyph.assert_called_once_with("sweet")

    def test_mcp_returns_one_image_or_text_block_and_advertises_formats(self):
        from aliens_mcp.server import mcp

        async def check():
            advertised = next(t for t in await mcp.list_tools() if t.name == "glyph")
            schema = advertised.model_dump(by_alias=True)["inputSchema"]
            self.assertEqual(schema["properties"]["format"]["default"], "image")
            self.assertEqual(
                schema["properties"]["format"]["enum"], ["ascii", "paths", "image"]
            )
            for format in ("image", "paths", "ascii"):
                result = await mcp.call_tool(
                    "glyph", {"hash": "qrag", "format": format}
                )
                # SDK versions return CallToolResult, a list, or (list, structured).
                blocks = (
                    result.content
                    if hasattr(result, "content")
                    else result[0]
                    if isinstance(result, tuple)
                    else result
                )
                self.assertEqual(len(blocks), 1)
                block = blocks[0]
                if format == "image":
                    self.assertEqual(block.type, "image")
                    png = Image.open(BytesIO(base64.b64decode(block.data)))
                    self.assertEqual(png.format, "PNG")
                elif format == "paths":
                    data = json.loads(block.text)
                    self.assertEqual(
                        set(data),
                        {
                            "hash",
                            "canvas",
                            "origin",
                            "x_direction",
                            "y_direction",
                            "paths",
                        },
                    )
                else:
                    self.assertEqual(set(block.text), {"#", " ", "\n"})

        runtime = mock_game()
        runtime.glyph.return_value = SAMPLE
        with patch.object(service, "client", return_value=runtime):
            asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
