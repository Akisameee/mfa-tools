"""Annotation validation and public receipts; no running game required."""

import asyncio
import unittest
from unittest.mock import patch

from support import ServiceTestCase, mock_game, service

from aliens_mcp import tools


class NoteTests(ServiceTestCase):
    def test_invalid_requests_do_not_attach(self):
        invalid = [
            (token, "标注")
            for token in (None, "", "AB12", "123", "12345", "ab/1", "科学", True)
        ]
        invalid += [
            ("qrag", value)
            for value in (
                None,
                "第一行\n第二行",
                "\r",
                "\0",
                "字" * 50,
                "😀" * 25,
                "\ud800",
            )
        ]
        with patch.object(service, "client") as attach:
            for args in invalid:
                with self.subTest(args=repr(args)), self.assertRaises(ValueError):
                    tools.note(*args)
            attach.assert_not_called()

    def test_chinese_and_supplementary_unicode_are_forwarded_intact(self):
        for text in ("科学", "科学🛰️", "字" * 49, "😀" * 24 + "字"):
            runtime = mock_game()
            runtime.note.return_value = {"ok": True, "text": text}
            with (
                self.subTest(text=text),
                patch.object(service, "client", return_value=runtime),
            ):
                self.assertEqual(tools.note("qrag", text)["text"], text)
            runtime.note.assert_called_once_with("test-character", text)

    def test_empty_string_clears_an_annotation(self):
        runtime = mock_game()
        runtime.note.return_value = {"ok": True, "text": ""}
        with patch.object(service, "client", return_value=runtime):
            self.assertEqual(
                tools.note("qrag", ""), {"ok": True, "hash": "qrag", "text": ""}
            )

    def test_receipt_does_not_expose_internal_word_keys(self):
        runtime = mock_game()
        runtime.note.return_value = {
            "ok": True,
            "text": "玩家标注",
            "word": "private-word",
        }
        with patch.object(service, "client", return_value=runtime):
            receipt = tools.note("qrag", "玩家标注")
        self.assertEqual(receipt, {"ok": True, "hash": "qrag", "text": "玩家标注"})

    def test_game_failure_is_not_reported_as_success(self):
        runtime = mock_game()
        runtime.note.side_effect = RuntimeError("Native annotation failed")
        with patch.object(service, "client", return_value=runtime):
            with self.assertRaisesRegex(RuntimeError, "Native annotation failed"):
                tools.note("qrag", "标注")

    def test_service_resolves_off_page_hash_and_rejects_unknown_before_native_edit(
        self,
    ):
        from aliens_mcp.hashes import word_id

        runtime = mock_game()
        runtime.vocabulary.return_value = ["private-off-page", "sweet", "hide"]
        runtime.note.return_value = {"ok": True, "text": "标注"}
        with patch.object(service, "client", return_value=runtime):
            self.assertTrue(service.note(word_id("private-off-page"), "标注")["ok"])
            self.assertEqual(runtime.note.call_args.args, ("private-off-page", "标注"))
            service.note(service._glyph_ids.by_word["sweet"], "标注")
            self.assertEqual(runtime.note.call_args.args[0], "sweet")
            with self.assertRaisesRegex(ValueError, "Unknown glyph hash"):
                service.note("0000", "标注")
        self.assertEqual(runtime.note.call_count, 2)

    def test_mcp_schema_accepts_hash_and_text_without_coordinates(self):
        from aliens_mcp.server import mcp

        async def check():
            tool = next(t for t in await mcp.list_tools() if t.name == "note")
            schema = tool.model_dump(by_alias=True)["inputSchema"]
            self.assertEqual(set(schema["properties"]), {"hash", "text"})
            self.assertEqual(set(schema["required"]), {"hash", "text"})
            await mcp.call_tool("note", {"hash": "qrag", "text": "标注"})

        runtime = mock_game()
        runtime.note.return_value = {"ok": True, "text": "标注"}
        with patch.object(service, "client", return_value=runtime):
            asyncio.run(check())
        runtime.note.assert_called_once_with("test-character", "标注")


if __name__ == "__main__":
    unittest.main()
