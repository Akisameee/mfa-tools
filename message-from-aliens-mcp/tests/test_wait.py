import asyncio
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from support import ServiceTestCase, mock_game, service

from aliens_mcp import tools


class WaitTests(ServiceTestCase):
    def test_invalid_intervals_do_not_attach(self):
        with patch.object(service, "client") as attach:
            for value in (
                None,
                True,
                False,
                "60",
                -1,
                0,
                0.0001,
                86401,
                float("nan"),
                float("inf"),
            ):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    tools.wait(value)
            attach.assert_not_called()

    def test_receipt_contains_only_requested_time_and_success(self):
        runtime = mock_game()
        runtime.wait.return_value = {"ok": True, "seconds": 1.25, "word": "private"}
        with patch.object(service, "client", return_value=runtime):
            self.assertEqual(tools.wait(1.25), {"ok": True, "seconds": 1.25})
        runtime.wait.assert_called_once_with(1.25)

    def test_client_queues_on_window_thread_without_sleeping(self):
        from aliens_mcp.game.client import GameClient

        runtime = GameClient.__new__(GameClient)
        runtime._transport = Mock(pid=123)
        runtime._transport.call.return_value = {"ok": True, "seconds": 60}
        with (
            patch("aliens_mcp.game.windows.game_window", return_value=(456, 789)),
            patch("aliens_mcp.game.client.time.sleep") as sleep,
        ):
            self.assertTrue(runtime.wait(60)["ok"])
        runtime._transport.call.assert_called_once_with("wait", 60, 789, "0x1c8")
        sleep.assert_not_called()

    def test_mcp_advertises_seconds_and_returns_english_receipt(self):
        from aliens_mcp.server import INSTRUCTIONS, mcp

        async def check():
            advertised = next(t for t in await mcp.list_tools() if t.name == "wait")
            schema = advertised.model_dump(by_alias=True)["inputSchema"]
            self.assertEqual(set(schema["properties"]), {"seconds"})
            self.assertIn("pages that support time advancement", advertised.description)
            for text in (INSTRUCTIONS, advertised.description):
                self.assertNotIn("incremental", text.lower())
                self.assertNotIn("minigame", text.lower())
            result = await mcp.call_tool("wait", {"seconds": 60})
            blocks = (
                result.content
                if hasattr(result, "content")
                else result[0]
                if isinstance(result, tuple)
                else result
            )
            self.assertEqual(blocks[0].text, "Advanced game time by 60 seconds.")

        with patch.object(tools, "wait", return_value={"ok": True, "seconds": 60}):
            asyncio.run(check())

    @unittest.skipUnless(
        shutil.which("node"), "Node is needed for JavaScript timer checks"
    )
    def test_native_settlement_guards_and_rollback(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                shutil.which("node"),
                str(root / "tests/idle_fixture.js"),
                str(root / "src/aliens_mcp/game/scripts/time.js"),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
