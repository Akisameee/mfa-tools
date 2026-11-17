"""Independent views, exact pixel comparisons, and live state/error handling."""

import unittest
from dataclasses import replace
from io import BytesIO
from unittest.mock import patch

from PIL import Image
from support import ServiceTestCase, mock_game, service

from aliens_mcp import tools
from aliens_mcp.errors import GameError, GameNotRunning
from aliens_mcp.models import Screenshot


def picture(color=(12, 34, 56), compression=6):
    buffer = BytesIO()
    Image.new("RGB", (4, 3), color).save(
        buffer, format="PNG", compress_level=compression
    )
    return Screenshot(buffer.getvalue(), 4, 3, 4, 3, True)


def page():
    return {
        "page": "test",
        "rows": 9,
        "cols": 24,
        "cells": [
            {
                "word": "private",
                "note": "标注",
                "row": 1,
                "col": 0,
                "block": "left_text",
                "highlight": False,
            }
        ],
    }


class LookCacheTests(ServiceTestCase):
    def setUp(self):
        super().setUp()
        service._look_cache.clear()
        self.addCleanup(service._look_cache.clear)
        self.runtime = mock_game(pid=123)
        self.runtime.snapshot.side_effect = lambda: page()

    def test_identical_table_is_short_but_state_is_still_read_each_time(self):
        with patch.object(service, "client", return_value=self.runtime):
            first = tools.look()
            self.assertIn("标注", first)
            self.assertIn("Unchanged: table", tools.look())
        self.assertEqual(self.runtime.snapshot.call_count, 2)

    def test_changed_notes_decorations_and_page_context_resend_the_table(self):
        data = page()
        self.runtime.snapshot.side_effect = lambda: data
        with patch.object(service, "client", return_value=self.runtime):
            tools.look()
            data["cells"][0]["note"] = "新的标注"
            self.assertIn("新的标注", tools.look())
            data["cells"][0]["highlight"] = True
            self.assertIn("\\hl{", tools.look())
            data["page"] = "another-page-with-same-visible-labels"
            self.assertIn("row/col", tools.look())
            self.assertIn("Unchanged", tools.look())

    def test_screenshot_and_table_keep_separate_previous_results(self):
        frame = picture()
        with (
            patch.object(service, "client", return_value=self.runtime),
            patch.object(self.runtime, "screenshot", return_value=frame) as capture,
        ):
            self.assertIn("row/col", tools.look())
            self.assertIs(tools.look("screenshot"), frame)
            self.assertIn("Unchanged: table", tools.look())
            self.assertIn("Unchanged: screenshot", tools.look("screenshot"))
        self.assertEqual(capture.call_count, 2)

    def test_pixels_are_exact_even_when_png_compression_differs(self):
        first, same_pixels = picture(compression=0), picture(compression=9)
        changed_pixel = picture(color=(12, 34, 57))
        self.assertNotEqual(first.data, same_pixels.data)
        with (
            patch.object(service, "client", return_value=self.runtime),
            patch.object(
                self.runtime,
                "screenshot",
                side_effect=[first, same_pixels, changed_pixel],
            ),
        ):
            self.assertIs(tools.look("screenshot"), first)
            self.assertIn("Unchanged", tools.look("screenshot"))
            self.assertIs(tools.look("screenshot"), changed_pixel)

    def test_changed_size_or_window_style_resends_image(self):
        frames = [picture()]
        frames.append(replace(frames[0], client_width=3))
        frames.append(replace(frames[1], bordered=False))
        with (
            patch.object(service, "client", return_value=self.runtime),
            patch.object(self.runtime, "screenshot", side_effect=frames),
        ):
            for frame in frames:
                self.assertIs(tools.look("screenshot"), frame)

    def test_force_rereads_and_returns_full_content_in_both_modes(self):
        frame = picture()
        with (
            patch.object(service, "client", return_value=self.runtime),
            patch.object(self.runtime, "screenshot", return_value=frame),
        ):
            first = tools.look()
            tools.look("screenshot")
            self.assertEqual(tools.look(force=True), first)
            self.assertIs(tools.look("screenshot", force=True), frame)
            self.assertIn("Unchanged", tools.look())
            self.assertIn("Unchanged", tools.look("screenshot"))

    def test_stopped_game_or_failed_capture_is_not_hidden_by_cache(self):
        with patch.object(service, "client", return_value=self.runtime):
            tools.look()
        with patch.object(service, "client", side_effect=GameNotRunning()):
            with self.assertRaisesRegex(GameNotRunning, "launch_game"):
                tools.look()
        with (
            patch.object(service, "client", return_value=self.runtime),
            patch.object(
                self.runtime,
                "screenshot",
                side_effect=[
                    picture(),
                    GameError("CAPTURE_FAILED", detail="capture failed"),
                ],
            ),
        ):
            tools.look("screenshot")
            with self.assertRaisesRegex(GameError, "capture failed"):
                tools.look("screenshot")

    def test_reconnect_clears_both_views(self):
        old, new = mock_game(pid=123, alive=True), mock_game(pid=456, alive=True)
        old.snapshot.side_effect = new.snapshot.side_effect = lambda: page()
        frame = picture()
        with (
            patch.object(service, "_client", old),
            patch("aliens_mcp.service.GameClient", return_value=new),
            patch.object(old, "screenshot", return_value=frame),
            patch.object(new, "screenshot", return_value=frame),
        ):
            tools.look()
            tools.look("screenshot")
            old.alive = False
            self.assertIn("row/col", tools.look())
            self.assertIs(tools.look("screenshot"), frame)
            self.assertIn("Unchanged", tools.look())

    def test_invalid_force_is_rejected_before_attaching(self):
        with patch.object(service, "client") as attach:
            with self.assertRaisesRegex(ValueError, "boolean"):
                tools.look(force="yes")
            attach.assert_not_called()


if __name__ == "__main__":
    unittest.main()
