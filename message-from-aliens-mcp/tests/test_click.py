"""Public click contract; no running game or process injection required."""

import asyncio
import unittest
from unittest.mock import patch

from support import ServiceTestCase, mock_game, service

from aliens_mcp import tools
from aliens_mcp.validation import validate_click


class ClickTests(ServiceTestCase):
    def test_rejects_invalid_requests_before_attaching(self):
        invalid = [
            (-1, 0, "left"),
            (9, 0, "left"),
            (0, -1, "left"),
            (0, 24, "right"),
            (True, 0, "left"),
            (0, False, "left"),
            (1.5, 0, "left"),
            (0, "1", "left"),
            (0, 0, "middle"),
        ]
        with patch.object(service, "client") as attach:
            for args in invalid:
                with self.subTest(args=args), self.assertRaises(ValueError):
                    tools.click(*args)
            attach.assert_not_called()

    def test_grid_corners_accept_both_buttons(self):
        for row, col in [(0, 0), (0, 23), (8, 0), (8, 23)]:
            for button in ("left", "right"):
                validate_click(row, col, button)

    def test_receipt_does_not_expose_runtime_fields(self):
        runtime = mock_game()
        runtime.click.return_value = {"ok": True, "word": "private game data"}
        with patch.object(service, "client", return_value=runtime):
            result = tools.click(8, 23, "right")
        runtime.click.assert_called_once_with(8, 23, "right")
        self.assertEqual(
            result,
            {
                "ok": True,
                "row": 8,
                "col": 23,
                "type": "right",
                "game_running": True,
                "target": None,
            },
        )

    def test_target_receipt_keeps_only_public_label_and_decoration_fields(self):
        runtime = mock_game()
        runtime.click.return_value = {
            "ok": True,
            "target": {
                "note": "玩家标注",
                "highlight": True,
                "boxed": True,
                "word": "test-character",
                "meaning": "private-meaning",
                "menu": "private-menu",
            },
        }
        with patch.object(service, "client", return_value=runtime):
            result = tools.click(1, 2)
        self.assertEqual(
            result["target"],
            {
                "id": "qrag",
                "note": "玩家标注",
                "underlined": False,
                "highlight": True,
                "dim": False,
                "boxed": True,
            },
        )
        self.assertNotIn("private", repr(result))

    def test_default_button_is_left(self):
        runtime = mock_game()
        runtime.click.return_value = {"ok": True}
        with patch.object(service, "client", return_value=runtime):
            tools.click(0, 0)
        runtime.click.assert_called_once_with(0, 0, "left")

    def test_blank_cell_receipt_preserves_frame_without_inventing_a_hash(self):
        runtime = mock_game()
        runtime.click.return_value = {
            "ok": True,
            "target": {"empty": True, "boxed": True, "word": "stale-private-word"},
        }
        with patch.object(service, "client", return_value=runtime):
            result = tools.click(3, 13)
        self.assertEqual(result["target"], {"empty": True, "boxed": True})
        self.assertNotIn("stale", repr(result))

    def test_game_failure_is_not_reported_as_success(self):
        runtime = mock_game()
        runtime.click.side_effect = RuntimeError("There is no character at this cell")
        with patch.object(service, "client", return_value=runtime):
            with self.assertRaisesRegex(RuntimeError, "no character"):
                tools.click(8, 23)

    def test_external_links_are_returned_without_exposing_internal_fields(self):
        runtime = mock_game()
        runtime.click.return_value = {
            "ok": True,
            "event": "external_url",
            "urls": ["https://example.com/community"],
            "opened": False,
            "game_running": True,
            "word": "private-word",
        }
        with patch.object(service, "client", return_value=runtime):
            result = tools.click(8, 12)
        self.assertEqual(result["event"], "external_url")
        self.assertEqual(result["urls"], ["https://example.com/community"])
        self.assertFalse(result["opened"])
        self.assertNotIn("word", result)


class MCPClickOutputTests(ServiceTestCase):
    def test_blank_click_results_distinguish_empty_from_unknown_targets(self):
        from aliens_mcp.server import _describe_click, mcp

        async def check():
            for boxed, label in [(False, "blank"), (True, "[blank]")]:
                receipt = {
                    "ok": True,
                    "game_running": True,
                    "row": 3,
                    "col": 13,
                    "type": "left",
                    "target": {"empty": True, "boxed": boxed},
                }
                expected = f"Clicked {label} at (3, 13) with the left mouse button."
                self.assertEqual(_describe_click(receipt), expected)
                with patch.object(tools, "click", return_value=receipt):
                    result = await mcp.call_tool("click", {"row": 3, "col": 13})
                blocks = (
                    result.content
                    if hasattr(result, "content")
                    else result[0]
                    if isinstance(result, tuple)
                    else result
                )
                self.assertEqual(blocks[0].text, expected)

        asyncio.run(check())

    def test_plain_text_preserves_click_state_and_urls_without_json_wrapping(self):
        from aliens_mcp.server import mcp

        cases = [
            (
                {"ok": True, "game_running": True},
                "left",
                ["left mouse button", "(1, 2)"],
            ),
            (
                {"ok": True, "game_running": True},
                "right",
                ["right mouse button", "(1, 2)"],
            ),
            (
                {
                    "ok": True,
                    "game_running": False,
                    "event": "game_closed",
                    "click_status": "quit_requested",
                },
                "left",
                ["The game has closed", "requested exit", "launch_game()"],
            ),
            (
                {
                    "ok": False,
                    "game_running": False,
                    "event": "game_closed",
                    "click_status": "unconfirmed",
                },
                "right",
                ["The game process has exited", "Could not confirm", "launch_game()"],
            ),
            (
                {
                    "ok": True,
                    "game_running": True,
                    "event": "external_url",
                    "opened": False,
                    "urls": ["https://example.com/one", "https://example.com/two"],
                },
                "left",
                [
                    "External navigation blocked",
                    "no webpage was opened",
                    "https://example.com/one",
                    "https://example.com/two",
                ],
            ),
            ({"ok": False, "game_running": True}, "left", ["Could not confirm"]),
        ]

        async def check():
            tool = next(t for t in await mcp.list_tools() if t.name == "click")
            self.assertIsNone(tool.model_dump(by_alias=True).get("outputSchema"))
            self.assertEqual(
                set(tool.model_dump(by_alias=True)["inputSchema"]["properties"]),
                {"row", "col", "type"},
            )
            for receipt, button, expected in cases:
                data = {
                    **receipt,
                    "row": 1,
                    "col": 2,
                    "type": button,
                    "target": {"id": "abcd", "note": "player note"},
                }
                with (
                    self.subTest(receipt=receipt, button=button),
                    patch.object(tools, "click", return_value=data),
                ):
                    result = await mcp.call_tool(
                        "click", {"row": 1, "col": 2, "type": button}
                    )
                    blocks = (
                        result.content
                        if hasattr(result, "content")
                        else result[0]
                        if isinstance(result, tuple)
                        else result
                    )
                    self.assertEqual([b.type for b in blocks], ["text"])
                    text = blocks[0].text
                    self.assertTrue(text.isascii())
                    self.assertFalse(text.startswith("{"))
                    self.assertIn("abcd:player note", text)
                    for snippet in expected:
                        self.assertIn(snippet, text)
                    self.assertNotIn("The game is still running", text)
                    self.assertNotIn("Call look()", text)
                    if receipt["ok"] is False:
                        self.assertNotIn("Clicked", text)

        asyncio.run(check())

    def test_unknown_target_is_not_guessed_and_annotations_use_table_escaping(self):
        from aliens_mcp.server import _describe_click

        receipt = {"ok": True, "game_running": True, "row": 1, "col": 2, "type": "left"}
        self.assertIn("target unknown", _describe_click(receipt))
        receipt["target"] = {"id": "abcd", "note": '中文"注释\n换行'}
        text = _describe_click(receipt)
        self.assertIn('abcd:中文"注释&#10;换行', text)
        self.assertEqual(len(text.splitlines()), 1)

    def test_click_and_look_use_the_same_complete_decoration_format(self):
        from aliens_mcp.rendering.table import render
        from aliens_mcp.server import _describe_click

        cell = {
            "id": "abcd",
            "note": "science",
            "row": 1,
            "col": 2,
            "highlight": True,
            "dim": True,
            "underlined": True,
            "boxed": True,
        }
        expected = "[\\dim{\\hl{\\underline{abcd:science}}}]"
        table = {
            "rows": 9,
            "cols": 24,
            "cells": [cell],
            "boxes": [[1, 2]],
            "underlines": [[1, 2]],
        }
        self.assertIn(expected, render(table))
        text = _describe_click(
            {
                "ok": True,
                "game_running": True,
                "row": 1,
                "col": 2,
                "type": "left",
                "target": cell,
            }
        )
        self.assertEqual(
            text, f"Clicked {expected} at (1, 2) with the left mouse button."
        )

    def test_card_edges_survive_capture_and_match_table_labels(self):
        from aliens_mcp.messages import describe_click
        from aliens_mcp.rendering.table import render_cell

        frame = {"top": True, "bottom": False, "left": True, "right": True}
        runtime = mock_game()
        for raw, label in [
            ({"word": "private", "note": "卡牌"}, None),
            ({"empty": True}, "┌blank┐"),
        ]:
            runtime.click.return_value = {
                "ok": True,
                "game_running": True,
                "target": {**raw, "frame": frame},
            }
            with patch.object(service, "client", return_value=runtime):
                receipt = tools.click(7, 14)
            self.assertEqual(receipt["target"]["frame"], frame)
            expected = label or render_cell(receipt["target"])
            self.assertIn(expected, describe_click(receipt))
            self.assertNotIn("private", describe_click(receipt))


if __name__ == "__main__":
    unittest.main()
