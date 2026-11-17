"""Public contract preservation and structured native failure handling."""

import asyncio
import inspect
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock

from aliens_mcp.descriptions import INSTRUCTIONS
from aliens_mcp.errors import GameError
from aliens_mcp.game.transport import FridaTransport
from aliens_mcp.messages import ERRORS


class BoundaryTests(unittest.TestCase):
    def test_mcp_contract_matches_the_pre_refactor_tools(self):
        from aliens_mcp.server import mcp

        async def check():
            expected = json.loads(
                Path(__file__)
                .with_name("mcp_contract.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(INSTRUCTIONS, expected["instructions"])
            actual = {
                t.name: t.model_dump(by_alias=True) for t in await mcp.list_tools()
            }
            self.assertEqual(set(actual), {t["name"] for t in expected["tools"]})
            for tool in expected["tools"]:
                with self.subTest(tool=tool["name"]):
                    current = actual[tool["name"]]
                    self.assertEqual(current["inputSchema"], tool["inputSchema"])
                    self.assertEqual(
                        inspect.cleandoc(current["description"]),
                        inspect.cleandoc(tool["description"]),
                    )

        asyncio.run(check())

    def test_rpc_failure_keeps_already_applied_time_and_does_not_retry(self):
        transport = FridaTransport.__new__(FridaTransport)
        transport._errors = []
        transport._script = Mock()
        transport._script.exports_sync.wait.return_value = {
            "error": {
                "code": "TIME_SAVE_FAILED",
                "details": {"advanced": True, "seconds": 60, "cause": "UNITY_REJECTED"},
            }
        }
        with self.assertRaises(GameError) as caught:
            transport.call("wait", 60)
        self.assertEqual(caught.exception.code, "TIME_SAVE_FAILED")
        self.assertTrue(caught.exception.details["advanced"])
        self.assertEqual(caught.exception.details["seconds"], 60)
        self.assertIn("Game time advanced, but saving failed", str(caught.exception))
        transport._script.exports_sync.wait.assert_called_once_with(60)

    def test_unexpected_native_diagnostics_stay_out_of_public_errors(self):
        with self.assertLogs("aliens_mcp.game.transport", level="ERROR") as logs:
            error = FridaTransport._failure(
                {"code": "INTERNAL_ERROR", "diagnostic": "private source details"}
            )
        self.assertIn("private source details", logs.output[0])
        self.assertNotIn("private", str(error))

    def test_native_codes_all_have_centralized_messages(self):
        import re

        root = Path(__file__).resolve().parents[1] / "src/aliens_mcp/game/scripts"
        for source in root.glob("*.js"):
            for code in re.findall(
                r"gameError\('([A-Z_]+)'", source.read_text(encoding="utf-8")
            ):
                self.assertIn(code, ERRORS, (source.name, code))

    @unittest.skipUnless(
        shutil.which("node"), "Node is needed for the RPC protocol checks"
    )
    def test_javascript_protocol_handles_sync_async_and_partial_failure(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                shutil.which("node"),
                str(root / "tests/protocol_fixture.js"),
                str(root / "src/aliens_mcp/game/scripts"),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
