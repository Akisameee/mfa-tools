"""Launch readiness, process exit, and errors across interaction boundaries."""

import asyncio
import threading
import unittest
from unittest.mock import Mock, patch

from support import ServiceTestCase, mock_game, service

from aliens_mcp import tools
from aliens_mcp.errors import GameAccessDenied, GameError, GameNotRunning
from aliens_mcp.game.client import GameClient
from aliens_mcp.game.transport import FridaTransport


def click_client():
    current = GameClient.__new__(GameClient)
    current._transport = Mock(pid=123, alive=True)
    current._click_id = 0
    current._click_target = None
    current._quit_requested = threading.Event()
    current._wait_for_exit = Mock(return_value=True)
    return current


class TransportLifecycleTests(unittest.TestCase):
    def test_close_releases_managed_thread_before_frida_detach(self):
        current = FridaTransport.__new__(FridaTransport)
        current._session = Mock(is_detached=False)
        current._script = Mock()
        events = []
        current._script.exports_sync.dispose.side_effect = lambda: events.append(
            "dispose"
        )
        current._session.detach.side_effect = lambda: events.append("detach")
        current.close()
        self.assertEqual(events, ["dispose", "detach"])
        self.assertFalse(current.alive)

    def test_close_still_detaches_when_runtime_is_already_gone(self):
        current = FridaTransport.__new__(FridaTransport)
        current._session = session = Mock(is_detached=False)
        current._script = Mock()
        current._script.exports_sync.dispose.side_effect = RuntimeError(
            "Runtime unloaded"
        )
        current.close()
        session.detach.assert_called_once_with()

    def test_no_process_raises_actionable_error_without_attaching(self):
        with (
            patch("aliens_mcp.game.transport.running_pid", return_value=None),
            patch("aliens_mcp.game.transport.frida.get_local_device") as device,
        ):
            with self.assertRaisesRegex(GameNotRunning, "launch_game"):
                GameClient()
        device.assert_not_called()


class LaunchTests(unittest.TestCase):
    def test_launch_access_denied_does_not_start_steam_or_retry(self):
        with (
            patch("aliens_mcp.game.windows.running_pid", return_value=123),
            patch("aliens_mcp.game.windows.request_launch") as launch,
            patch("aliens_mcp.game.windows.game_window", return_value=(1, 2)),
            patch(
                "aliens_mcp.game.client.FridaTransport", side_effect=GameAccessDenied()
            ) as attach,
        ):
            with self.assertRaises(GameAccessDenied):
                GameClient.launch()
        launch.assert_not_called()
        attach.assert_called_once()

    def test_launch_reuses_readable_game_without_launching_again(self):
        current = mock_game(pid=123, alive=True)
        current.snapshot.return_value = {"cells": [{}]}
        with (
            patch("aliens_mcp.game.windows.running_pid", return_value=123),
            patch("aliens_mcp.game.windows.request_launch") as launch,
            patch("aliens_mcp.game.windows.game_window", return_value=(1, 2)),
        ):
            client, result = GameClient.launch(current)
        launch.assert_not_called()
        self.assertIs(client, current)
        self.assertEqual(
            result,
            {
                "ok": True,
                "game_running": True,
                "ready": True,
                "started": False,
                "pid": 123,
            },
        )

    def test_launch_waits_until_a_page_is_readable(self):
        current = mock_game(pid=456, alive=True)
        current.snapshot.side_effect = [GameError("DRAW_NOT_FOUND"), {"cells": [{}]}]
        with (
            patch("aliens_mcp.game.windows.running_pid", side_effect=[None, 456, 456]),
            patch("aliens_mcp.game.windows.request_launch") as launch,
            patch("aliens_mcp.game.windows.game_window", return_value=(1, 2)),
            patch.object(GameClient, "__new__", return_value=current),
            patch("aliens_mcp.game.client.time.sleep"),
        ):
            _, result = GameClient.launch()
        launch.assert_called_once_with()
        self.assertTrue(result["started"])
        self.assertTrue(result["ready"])
        self.assertEqual(current.snapshot.call_count, 2)

    def test_launch_timeout_is_an_error_not_a_false_ready_receipt(self):
        current = mock_game(pid=456, alive=True)
        with (
            patch("aliens_mcp.game.windows.running_pid", return_value=456),
            patch("aliens_mcp.game.windows.game_window", return_value=(1, 2)),
            patch("aliens_mcp.game.client.time.monotonic", side_effect=[0, 1, 46]),
            patch("aliens_mcp.game.client.time.sleep"),
        ):
            with self.assertRaisesRegex(GameError, "45 seconds"):
                GameClient.launch(current)
        current.close.assert_called_once()


class NativeClickTests(unittest.TestCase):
    def test_quit_during_click_returns_confirmed_closed_event(self):
        current = click_client()

        def quit(*args):
            current._on_event(
                {
                    "event": "click_target",
                    "request_id": args[-1],
                    "target": {"word": "private-end", "note": "End"},
                }
            )
            current._on_event({"event": "game_quit_requested", "request_id": args[-1]})
            raise GameNotRunning()

        current._transport.call.side_effect = quit

        def exited(timeout):
            current._transport.close.assert_called_once_with()
            return True

        current._wait_for_exit.side_effect = exited
        with patch("aliens_mcp.game.windows.game_window", return_value=(1, 2)):
            result = current.click(0, 23)
        self.assertTrue(result["ok"])
        self.assertEqual(result["event"], "game_closed")
        self.assertFalse(result["game_running"])
        self.assertEqual(result["target"]["word"], "private-end")

    def test_click_reports_pre_navigation_target_instead_of_reading_new_page(self):
        current = click_client()
        current._wait_for_exit.return_value = False
        current._transport.call.return_value = {
            "ok": True,
            "target": {"word": "original-cell"},
        }
        with patch("aliens_mcp.game.windows.game_window", return_value=(1, 2)):
            result = current.click(1, 2)
        self.assertEqual(result["target"]["word"], "original-cell")
        self.assertEqual(
            [c.args[0] for c in current._transport.call.call_args_list], ["click"]
        )

    def test_unexpected_process_exit_is_not_confirmed_click_success(self):
        current = click_client()
        current._transport.call.side_effect = GameNotRunning()
        with (
            patch("aliens_mcp.game.windows.game_window", return_value=(1, 2)),
            patch("aliens_mcp.game.windows.running_pid", return_value=None),
        ):
            result = current.click(0, 23)
        self.assertFalse(result["ok"])
        self.assertEqual(result["click_status"], "unconfirmed")

    def test_connection_failure_with_live_process_is_an_error(self):
        current = click_client()
        current._transport.call.side_effect = GameError(
            "TRANSPORT_FAILED", detail="transport lost"
        )
        with (
            patch("aliens_mcp.game.windows.game_window", return_value=(1, 2)),
            patch("aliens_mcp.game.windows.running_pid", return_value=123),
        ):
            with self.assertRaisesRegex(GameError, "transport lost"):
                current.click(0, 23)

    def test_late_quit_message_cannot_confirm_another_click(self):
        current = click_client()
        current._click_id = 2
        current._on_event({"event": "game_quit_requested", "request_id": 1})
        current._on_event(
            {"event": "click_target", "request_id": 1, "target": {"word": "stale-cell"}}
        )
        self.assertFalse(current._quit_requested.is_set())
        self.assertIsNone(current._click_target)


class PublicLifecycleTests(ServiceTestCase):
    def test_native_blank_target_remains_explicit_and_drops_private_fields(self):
        self.assertEqual(
            service._public_target(
                {"empty": True, "boxed": True, "note": "stale", "block": "private"}
            ),
            {"empty": True, "boxed": True},
        )

    def test_target_decorations_use_the_captured_rendered_flags(self):
        target = service._public_target(
            {
                "word": "shared",
                "menu": "private",
                "highlight": True,
                "boxed": True,
                "underlined": True,
                "dim": True,
            }
        )
        self.assertTrue(
            all(target[k] for k in ("underlined", "dim", "highlight", "boxed"))
        )
        self.assertNotIn("word", target)
        self.assertNotIn("menu", target)

    def test_menu_markers_cannot_forge_click_target_styles(self):
        target = service._public_target(
            {"word": "shared", "menu": "(win) [target] shared"}
        )
        self.assertFalse(target["underlined"])
        self.assertFalse(target["dim"])

    def test_public_closed_receipt_clears_session_and_retains_recovery_hint(self):
        current = mock_game()
        current.click.return_value = {
            "ok": True,
            "game_running": False,
            "event": "game_closed",
            "click_status": "quit_requested",
            "word": "private-word",
        }
        with (
            patch.object(service, "client", return_value=current),
            patch.object(service, "reset_session") as reset,
        ):
            result = tools.click(0, 23)
        reset.assert_called_once_with()
        self.assertEqual(result["next_tool"], "launch_game")
        self.assertNotIn("word", result)

    def test_every_mcp_game_tool_preserves_launch_hint(self):
        from aliens_mcp.server import _ToolError, mcp

        async def check():
            for name, args in [
                ("look", {}),
                ("look", {"type": "screenshot"}),
                ("click", {"row": 0, "col": 0}),
                ("note", {"hash": "qrag", "text": "test"}),
                ("glyph", {"hash": "qrag"}),
                ("wait", {"seconds": 60}),
            ]:
                with (
                    self.subTest(name=name),
                    self.assertRaisesRegex(_ToolError, "launch_game"),
                ):
                    await mcp.call_tool(name, args)

        with patch.object(service, "client", side_effect=GameNotRunning()):
            asyncio.run(check())
