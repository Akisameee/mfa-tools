import unittest

from support import ServiceTestCase, mock_game, service

from aliens_mcp.hashes import GlyphIds, word_id
from aliens_mcp.rendering.table import build, render


class LookTests(ServiceTestCase):
    def test_short_hash_collision_is_resolved_independently_of_catalogue_order(self):
        self.assertEqual(word_id("hide"), word_id("sweet"))
        first, second = GlyphIds(), GlyphIds()
        first.register(["hide", "sweet"])
        second.register(["sweet", "hide"])
        self.assertEqual(first.by_word, second.by_word)
        self.assertEqual(len(set(first.by_word.values())), 2)
        self.assertTrue(all(len(token) == 4 for token in first.by_word.values()))
        previous = dict(first.by_word)
        first.register([f"generated-{i}" for i in range(5000)])
        self.assertEqual({w: first.by_word[w] for w in previous}, previous)
        self.assertEqual(len(set(first.by_word.values())), 5002)

    def test_pure_snapshot_builder_also_handles_short_hash_collisions(self):
        data = self.snapshot()
        data["cells"] = [
            dict(data["cells"][0], word=w, col=i)
            for i, w in enumerate(["hide", "sweet"])
        ]
        self.assertEqual(len({c["id"] for c in build(data)["cells"]}), 2)

    def test_full_short_id_space_reports_error_instead_of_reusing_a_token(self):
        from unittest.mock import patch

        with patch("aliens_mcp.hashes.TOKEN_SPACE", 2):
            index = GlyphIds()
            index.register(["first", "second"])
            with self.assertRaisesRegex(ValueError, "exhausted"):
                index.register(["third"])

    def snapshot(self):
        return {
            "page": "test-page",
            "rows": 9,
            "cols": 24,
            "marked": "private-word",
            "sources": [],
            "menu": "(win) [test-target] private-word",
            "geometry": {"center_line": 12, "right_title": [12, 8]},
            "cells": [
                {
                    "row": 1,
                    "col": 12,
                    "block": "right_text_down",
                    "word": "private-word",
                    "note": "玩家注释",
                    "line": 0,
                    "line_str": "private-word",
                    "highlight": True,
                    "underlined": True,
                    "dim": True,
                }
            ],
            "boxes": [[2, 13]],
        }

    def test_live_notes_and_tokens_survive_the_snapshot_boundary(self):
        result = build(self.snapshot())
        cell = result["cells"][0]
        self.assertEqual(cell["note"], "玩家注释")
        self.assertEqual(cell["id"], word_id("private-word"))
        self.assertNotIn("private-word", repr(result))
        self.assertNotIn("word", cell)

    def test_live_note_changes_are_visible_on_the_next_read(self):
        data = self.snapshot()
        first = build(data)
        data["cells"][0]["note"] = "新的注释"
        second = build(data)
        self.assertEqual(first["cells"][0]["id"], second["cells"][0]["id"])
        self.assertEqual(second["cells"][0]["note"], "新的注释")

    def test_layout_and_decorations_survive_rendering(self):
        snapshot = build(self.snapshot())
        self.assertEqual(snapshot["underlines"], [[1, 12]])
        self.assertEqual(snapshot["frame"]["vertical"], 12)
        self.assertEqual(snapshot["frame"]["horizontal"], [[0, 0, 23]])
        markdown = render(snapshot)
        self.assertIn("\\dim{\\hl{\\underline{", markdown)
        self.assertIn("[ ]", markdown)
        self.assertIn("│", markdown)
        self.assertIn("玩家注释", render(snapshot, "text"))

    def test_raw_word_keys_require_explicit_development_mode(self):
        self.assertEqual(
            build(self.snapshot(), raw=True)["cells"][0]["id"], "private-word"
        )

    def test_vertical_card_preserves_grouping_and_empty_slot_outlines(self):
        data = self.snapshot()
        data["boxes"] = []
        data["frames"] = [[1, 12, 2, 12], [1, 14, 2, 14]]
        data["cells"][0].update(underlined=False, highlight=False, dim=False)
        data["cells"].append(dict(data["cells"][0], row=2, word="other", note="下半张"))
        snapshot = build(data)
        self.assertEqual(snapshot["frames"], data["frames"])
        for style in ("markdown", "text"):
            output = render(snapshot, style)
            self.assertIn(f"┌{word_id('private-word')}:玩家注释┐", output)
            self.assertIn(f"└{word_id('other')}:下半张┘", output)
            self.assertIn("┌ ┐", output)
            self.assertIn("└ ┘", output)

    def test_three_row_card_keeps_middle_sides_and_single_cell_frames_use_brackets(
        self,
    ):
        data = self.snapshot()
        data["boxes"] = []
        data["frames"] = [[1, 12, 3, 12], [1, 12, 1, 12], [2, 14, 2, 14]]
        snapshot = build(data)
        self.assertEqual(snapshot["boxes"], [[1, 12], [2, 14]])
        output = render(snapshot)
        self.assertIn("┌[\\dim{\\hl{\\underline{", output)
        self.assertIn("│ │", output)
        self.assertIn("└ ┘", output)
        self.assertIn("[ ]", output)

    def test_wide_rectangles_keep_corner_and_side_positions(self):
        data = self.snapshot()
        data["cells"] = []
        data["boxes"] = []
        data["frames"] = [[1, 12, 3, 14]]
        output = render(build(data))
        self.assertIn("┌ ─ | ─ ─ | ─ ┐", output)
        self.assertIn("│  |   |  │", output)
        self.assertIn("└ ─ | ─ ─ | ─ ┘", output)

    def test_unavailable_page_is_an_error(self):
        with self.assertRaisesRegex(RuntimeError, "could not complete"):
            build({"error": "page unavailable"})

    def test_identical_labels_keep_their_own_rendered_styles(self):
        data = self.snapshot()
        data["menu"] = (
            "shared entry newline (win) [done] shared entry newline [open] shared entry"
        )
        data["cells"] = [
            {
                "word": "shared",
                "row": line + 1,
                "col": 12,
                "block": "right_text_down",
                "line": line,
                "line_str": "shared entry",
                "underlined": line != 0,
                "dim": line == 1,
            }
            for line in range(3)
        ]
        result = build(data)
        self.assertEqual(result["underlines"], [[2, 12], [3, 12]])
        self.assertEqual([c["dim"] for c in result["cells"]], [False, True, False])

    def test_hidden_menu_lines_do_not_shift_rendered_styles(self):
        data = self.snapshot()
        data["menu"] = " newline [target] private-word"
        data["cells"][0]["line"] = 1
        self.assertEqual(build(data)["underlines"], [[1, 12]])

    def test_legacy_menu_markers_cannot_override_rendered_false_flags(self):
        data = self.snapshot()
        data["cells"][0].update(underlined=False, dim=False)
        result = build(data)
        self.assertEqual(result["underlines"], [])
        self.assertFalse(result["cells"][0]["dim"])

    def test_underlines_and_dim_can_appear_outside_right_menu(self):
        data = self.snapshot()
        data["cells"][0]["block"] = "left_text"
        result = build(data)
        self.assertEqual(result["underlines"], [[1, 12]])
        self.assertTrue(result["cells"][0]["dim"])

    def test_highlights_follow_each_cells_visible_background(self):
        data = self.snapshot()
        data["cells"].append(dict(data["cells"][0], row=2, highlight=False))
        self.assertEqual([c["highlight"] for c in build(data)["cells"]], [True, False])

    def test_player_punctuation_does_not_break_table_or_forge_decorations(self):
        data = self.snapshot()
        note = "甲|乙}\\hl{假高亮}\n**标注**<tag>&"
        data["cells"][0]["note"] = note
        snapshot = build(data)
        self.assertEqual(snapshot["cells"][0]["note"], note)
        markdown = render(snapshot)
        lines = markdown.splitlines()
        self.assertEqual({line.count("|") for line in lines}, {lines[0].count("|")})
        self.assertIn("&#124;", markdown)
        self.assertIn("&#10;", markdown)
        self.assertNotIn("\\hl{假高亮}", markdown)
        self.assertNotIn("<tag>", markdown)

    def test_all_table_rows_have_the_same_number_of_columns(self):
        data = self.snapshot()
        data["geometry"]["right_message_u"] = [12, 6]
        data["geometry"]["right_message_d"] = [12, 3]
        lines = render(build(data)).splitlines()
        self.assertEqual(len({line.count("|") for line in lines}), 1)

    def test_game_number_translations_are_preserved_without_parsing_word_keys(self):
        data = self.snapshot()
        data["cells"] = [dict(data["cells"][0], word="1e1", note="7 (7)")]
        snapshot = build(data)
        self.assertEqual(snapshot["cells"][0]["id"], word_id("1e1"))
        self.assertEqual(snapshot["cells"][0]["note"], "7 (7)")
        self.assertIn("7 (7)", render(snapshot))


class ScreenshotTests(ServiceTestCase):
    def test_invalid_look_type_is_rejected_before_attaching(self):
        from unittest.mock import patch

        from aliens_mcp import tools

        with patch.object(service, "client") as attach:
            for type in ("image", "json", "", None, True):
                with self.subTest(type=type), self.assertRaises(ValueError):
                    tools.look(type)
            attach.assert_not_called()

    def test_screenshot_mode_does_not_read_or_render_the_grid(self):
        from io import BytesIO
        from unittest.mock import patch

        from PIL import Image

        from aliens_mcp import tools
        from aliens_mcp.models import Screenshot

        runtime = mock_game(pid=123)
        buffer = BytesIO()
        Image.new("RGB", (4, 3)).save(buffer, format="PNG")
        screenshot = Screenshot(buffer.getvalue(), 4, 3, 4, 3, True)
        with (
            patch.object(service, "client", return_value=runtime),
            patch.object(runtime, "screenshot", return_value=screenshot) as capture,
        ):
            self.assertIs(tools.look("screenshot"), screenshot)
        capture.assert_called_once_with()
        runtime.snapshot.assert_not_called()

    def test_mcp_screenshot_contains_pixel_metadata_and_actual_color_image(self):
        import asyncio
        import base64
        from io import BytesIO
        from unittest.mock import patch

        from PIL import Image

        from aliens_mcp import tools
        from aliens_mcp.models import Screenshot
        from aliens_mcp.server import mcp

        buffer = BytesIO()
        Image.new("RGB", (4, 3), (238, 101, 20)).save(buffer, format="PNG")
        screenshot = Screenshot(buffer.getvalue(), 4, 3, 4, 3, False)

        async def check():
            tool = next(t for t in await mcp.list_tools() if t.name == "look")
            schema = tool.model_dump(by_alias=True)["inputSchema"]
            self.assertEqual(schema["properties"]["type"]["default"], "table")
            self.assertEqual(
                schema["properties"]["type"]["enum"], ["table", "screenshot"]
            )
            result = await mcp.call_tool("look", {"type": "screenshot"})
            blocks = (
                result.content
                if hasattr(result, "content")
                else result[0]
                if isinstance(result, tuple)
                else result
            )
            self.assertEqual([b.type for b in blocks], ["text", "image"])
            self.assertIn("4x3 pixels", blocks[0].text)
            self.assertIn("borderless", blocks[0].text)
            self.assertNotIn("Click coordinates", blocks[0].text)
            self.assertNotIn("look(", blocks[0].text)
            picture = Image.open(BytesIO(base64.b64decode(blocks[1].data)))
            self.assertEqual(picture.size, (4, 3))
            self.assertEqual(picture.getpixel((0, 0)), (238, 101, 20))

        with patch.object(tools, "look", return_value=screenshot):
            asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
