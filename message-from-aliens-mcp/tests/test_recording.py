"""Private native-grid capture without extra read-only calls or model-visible changes."""

import asyncio
import json
import os
import tempfile
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from unittest.mock import patch

from support import ServiceTestCase, mock_game, service

from aliens_mcp import tools
from aliens_mcp.descriptions import INSTRUCTIONS
from aliens_mcp.errors import GameError
from aliens_mcp.recording import Recorder, bind_call, unbind_call
from aliens_mcp.server import RecordingServer


def page(note="旧标注"):
    return {
        "page": "page",
        "rows": 9,
        "cols": 24,
        "cells": [
            {
                "row": 1,
                "col": 2,
                "block": "right_text_down",
                "word": "test-character",
                "note": note,
                "underlined": True,
                "highlight": False,
                "dim": False,
            }
        ],
        "boxes": [],
        "frames": [],
        "geometry": {"center_line": 12},
    }


class RecordingTests(ServiceTestCase):
    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.recorder = Recorder(self.root / "run")
        self.addCleanup(self.recorder.close)
        self.client = mock_game(alive=True)
        self.client.snapshot.side_effect = lambda: page()
        service._client = self.client

    def events(self):
        return [
            json.loads(line)
            for line in (self.recorder.directory / "events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]

    def recorded(self, name, arguments, function):
        call = self.recorder.begin(name, arguments, "req-1")
        token = bind_call(call)
        try:
            result = function()
        except Exception as error:
            self.recorder.finish(call, service, error=error)
            raise
        else:
            self.recorder.finish(call, service, result=result)
            return result
        finally:
            unbind_call(token)

    def state(self, end):
        return json.loads(
            (self.recorder.directory / end["state_ref"]).read_text(encoding="utf-8")
        )

    def test_environment_off_creates_no_directory(self):
        target = self.root / "disabled"
        for value in ("0", "", "false"):
            with patch.dict(
                os.environ,
                {"ALIENS_MCP_RECORD": value, "ALIENS_MCP_RECORD_DIR": str(target)},
            ):
                self.assertIsNone(Recorder.from_environment())
        self.assertFalse(target.exists())

    def test_enabled_environment_uses_directory_directly_and_resumes(self):
        with patch.dict(
            os.environ,
            {"ALIENS_MCP_RECORD": "1", "ALIENS_MCP_RECORD_DIR": str(self.root)},
        ):
            first = Recorder.from_environment()
            self.assertEqual(first.directory, self.root)
            first.begin("glyph", {"hash": "qrag"})
            original_manifest = (self.root / "manifest.json").read_bytes()
            first.close()
            second = Recorder.from_environment()
        self.addCleanup(second.close)
        self.assertEqual(second.directory, self.root)
        self.assertEqual(second.begin("look", {}).id, "2")
        self.assertEqual((self.root / "manifest.json").read_bytes(), original_manifest)
        self.assertEqual(
            json.loads((first.directory / "manifest.json").read_text())[
                "schema_version"
            ],
            1,
        )

    def test_restart_preserves_history_and_assigns_new_connection(self):
        self.recorded("look", {}, lambda: tools.look())
        before = self.events()
        original_events = (self.recorder.directory / "events.jsonl").read_bytes()
        original_state = self.state(before[-1])
        self.recorder.close()
        self.recorder = Recorder(self.root / "run")
        self.addCleanup(self.recorder.close)
        # Model hashes can restart, even if the game remains running.
        self.recorded("look", {}, lambda: tools.look())
        after = self.events()
        self.assertEqual([e["seq"] for e in after], [1, 2, 3, 4])
        self.assertEqual([e["call_id"] for e in after], ["1", "1", "2", "2"])
        self.assertEqual(after[:2], before)
        self.assertTrue(
            (self.recorder.directory / "events.jsonl").read_bytes().startswith(original_events)
        )
        self.assertGreater(after[-1]["connection"], before[-1]["connection"])
        self.assertGreaterEqual(after[2]["elapsed_ns"], before[-1]["elapsed_ns"])
        self.assertGreaterEqual(after[-1]["completed_elapsed_ns"], after[2]["elapsed_ns"])
        self.assertIsNone(after[2]["state_ref"])
        self.assertNotEqual(after[-1]["state_ref"], before[-1]["state_ref"])
        self.assertEqual(self.state(before[-1]), original_state)

    def test_restart_repairs_partial_tail_without_replaying_incomplete_call(self):
        self.recorder.begin("note", {"hash": "qrag", "text": "unfinished"})
        self.recorder.close()
        with (self.recorder.directory / "events.jsonl").open("ab") as stream:
            stream.write(b'{"seq":2,"text":"\xe4')
        self.recorder = Recorder(self.root / "run")
        self.addCleanup(self.recorder.close)
        self.recorded("look", {}, lambda: tools.look())
        events = self.events()
        self.assertEqual([e["seq"] for e in events], [1, 2, 3])
        self.assertEqual([e["call_id"] for e in events], ["1", "2", "2"])
        self.client.note.assert_not_called()

    def test_restart_preserves_valid_final_event_without_newline(self):
        self.recorder.begin("look", {})
        self.recorder.close()
        path = self.recorder.directory / "events.jsonl"
        path.write_bytes(path.read_bytes().rstrip(b"\n"))
        self.recorder = Recorder(self.root / "run")
        self.addCleanup(self.recorder.close)
        self.recorder.begin("glyph", {})
        self.assertEqual([e["seq"] for e in self.events()], [1, 2])

    def test_another_recorder_can_open_the_same_directory_without_a_lock(self):
        self.recorder.begin("look", {})
        path = self.recorder.directory / "events.jsonl"
        original = path.read_bytes()
        other = Recorder(self.recorder.directory)
        self.addCleanup(other.close)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.recorder.directory / ".recording.lock").exists())

    def test_multiple_stdio_servers_share_log_and_idle_servers_do_not_lock(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        directory = self.root / "shared"
        fixture = Path(__file__).with_name("recording_stdio_fixture.py")
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(fixture)],
            env={
                **os.environ,
                "ALIENS_MCP_RECORD": "1",
                "ALIENS_MCP_RECORD_DIR": str(directory),
                "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
            },
        )

        async def connect(stack):
            streams = await stack.enter_async_context(stdio_client(parameters))
            session = await stack.enter_async_context(ClientSession(*streams))
            await session.initialize()
            return session

        async def run():
            async with AsyncExitStack() as first_stack:
                first = await connect(first_stack)
                self.assertFalse(directory.exists())
                async with AsyncExitStack() as second_stack:
                    second = await connect(second_stack)
                    await second.call_tool("look", {})
                    # First started earlier, but has been idle until now.
                    await first.call_tool("look", {})
                    await first.call_tool("note", {"hash": "qrag", "text": "first"})
                    await second.call_tool("note", {"hash": "qrag", "text": "second"})
                    await first.call_tool("look", {})
                    await second.call_tool("look", {})
                async with AsyncExitStack() as restarted_stack:
                    restarted = await connect(restarted_stack)
                    await restarted.call_tool("look", {})

        asyncio.run(run())
        self.assertFalse((directory / ".recording.lock").exists())
        rows = [json.loads(s) for s in (directory / "events.jsonl").read_text().splitlines()]
        self.assertEqual([e["seq"] for e in rows], list(range(1, 15)))
        self.assertEqual([e["call_id"] for e in rows[::2]], [str(i) for i in range(1, 8)])
        self.assertTrue(all(e["kind"] == "call.begin" for e in rows[::2]))
        ends = rows[1::2]
        self.assertTrue(all(e["status"] == "ok" for e in ends))
        self.assertTrue(all(e["state_observed"] for e in ends))
        for end in ends:
            state = json.loads((directory / end["state_ref"]).read_text())
            self.assertEqual(state["connection"], end["connection"])
        # Alternation preserves each live process's connection identity.
        self.assertEqual(ends[0]["connection"], ends[5]["connection"])
        self.assertEqual(ends[1]["connection"], ends[4]["connection"])
        self.assertNotIn(ends[6]["connection"], [ends[0]["connection"], ends[1]["connection"]])

    def test_recording_retries_after_initialization_failure(self):
        with patch.dict(os.environ, {"ALIENS_MCP_RECORD": "1"}):
            server = RecordingServer("retry-test")
            server.tool()(tools.look)

            async def run():
                with patch(
                    "aliens_mcp.server.Recorder.from_environment",
                    side_effect=[None, self.recorder],
                ):
                    await server.call_tool("look", {})
                    self.assertIsNone(server.recorder)
                    await server.call_tool("look", {})

            asyncio.run(run())
        self.assertEqual(len(self.events()), 2)
        self.assertTrue(self.recorder.enabled)

    def test_corrupt_complete_line_is_not_removed(self):
        self.recorder.close()
        path = self.recorder.directory / "events.jsonl"
        path.write_bytes(b"invalid event\n")
        with self.assertRaises(json.JSONDecodeError):
            Recorder(self.recorder.directory)
        self.assertEqual(path.read_bytes(), b"invalid event\n")

    def test_capture_is_native_and_does_not_seed_hashes_or_touch_cache(self):
        service._look_cache["table"] = ("previous", "value")
        self.client.snapshot.side_effect = lambda: {
            **page(),
            "cells": [dict(page()["cells"][0], word="new-key")],
        }
        self.recorded("click", {"row": 0, "col": 0}, lambda: {"ok": True})
        native = self.state(self.events()[-1])["snapshot"]
        self.assertEqual(native["cells"][0]["word"], "new-key")
        self.assertIn("geometry", native)
        self.assertEqual(native["ids"], {})
        self.assertNotIn("new-key", service._glyph_ids.by_word)
        self.assertEqual(service._look_cache["table"], ("previous", "value"))

    def test_launch_game_saves_initial_state_without_a_look_call(self):
        service._client = None
        receipt = {"ok": True, "game_running": True, "ready": True, "started": True}
        with patch(
            "aliens_mcp.service.GameClient.launch",
            return_value=(self.client, receipt),
        ):
            result = self.recorded("launch_game", {}, tools.launch_game)
        self.assertEqual(result, receipt)
        end = self.events()[-1]
        self.assertEqual(end["tool"], "launch_game")
        self.assertEqual(end["status"], "ok")
        self.assertEqual(end["capture"], "captured")
        self.assertTrue(end["state_observed"])
        initial = self.state(end)["snapshot"]
        self.assertEqual(initial["page"], "page")
        self.assertEqual(initial["cells"][0]["note"], "旧标注")
        self.assertEqual(initial["ids"], {})
        self.assertFalse(service._look_cache)
        self.client.snapshot.assert_called_once()

    def test_look_uses_its_existing_read_even_when_response_is_unchanged(self):
        self.recorded("look", {}, lambda: tools.look())
        second = self.recorded("look", {}, lambda: tools.look())
        self.assertTrue(second.startswith("Unchanged"))
        self.assertEqual(self.client.snapshot.call_count, 2)
        ends = [e for e in self.events() if e["kind"] == "call.end"]
        self.assertEqual(ends[0]["state_ref"], ends[1]["state_ref"])
        self.assertEqual(ends[1]["capture"], "reused")
        self.assertEqual(len(list((self.recorder.directory / "states").iterdir())), 1)

    def test_changed_annotations_are_saved_as_historical_values(self):
        self.recorded("look", {}, lambda: tools.look())
        self.client.snapshot.side_effect = lambda: page("新标注")
        self.recorded("note", {"hash": "qrag", "text": "新标注"}, lambda: {"ok": True})
        ends = [e for e in self.events() if e["kind"] == "call.end"]
        self.assertEqual(self.state(ends[0])["snapshot"]["cells"][0]["note"], "旧标注")
        self.assertEqual(self.state(ends[1])["snapshot"]["cells"][0]["note"], "新标注")
        self.assertEqual(
            ends[1]["character"], {"hash": "qrag", "key": "test-character"}
        )

    def test_glyph_records_location_but_no_grid_or_resource_payload(self):
        self.recorded("look", {}, lambda: tools.look())
        self.client.snapshot.reset_mock()
        self.recorded(
            "glyph", {"hash": "qrag", "format": "paths"}, lambda: {"paths": [[12345]]}
        )
        end = self.events()[-1]
        self.client.snapshot.assert_not_called()
        self.assertEqual(end["capture"], "not_requested")
        self.assertFalse(end["state_observed"])
        self.assertIsNotNone(end["state_ref"])
        self.assertNotIn(
            "12345", (self.recorder.directory / "events.jsonl").read_text()
        )

    def test_hidden_hash_resolution_during_glyph_does_not_create_frame(self):
        self.client.glyph.return_value = [[[0, 0], [1, 1]]]
        self.recorded("glyph", {"hash": "qrag"}, lambda: tools.glyph("qrag"))
        self.assertEqual(self.client.snapshot.call_count, 1)
        self.assertIsNone(self.events()[-1]["state_ref"])
        self.assertFalse(list((self.recorder.directory / "states").iterdir()))

    def test_screenshot_look_omits_image_without_reading_grid(self):
        image = {
            "content": [
                {"type": "image", "mimeType": "image/png", "data": "secret-image-data"}
            ]
        }
        result = self.recorded("look", {"type": "screenshot"}, lambda: image)
        self.assertIs(result, image)
        self.client.snapshot.assert_not_called()
        text = (self.recorder.directory / "events.jsonl").read_text()
        self.assertNotIn("secret-image-data", text)
        self.assertIn('"omitted":true', text)

    def test_exit_does_not_reconnect_or_reuse_old_state_as_current(self):
        self.recorded("look", {}, lambda: tools.look())
        service.reset_session()
        with patch("aliens_mcp.service.GameClient") as factory:
            self.recorded(
                "click", {"row": 0, "col": 23}, lambda: {"game_running": False}
            )
        factory.assert_not_called()
        end = self.events()[-1]
        self.assertEqual(end["capture"], "unavailable")
        self.assertIsNone(end["state_ref"])

    def test_failed_capture_preserves_successful_operation(self):
        self.client.snapshot.side_effect = GameError("PAGE_CHANGED")
        original = {"ok": True, "seconds": 60}
        self.assertIs(
            self.recorded("wait", {"seconds": 60}, lambda: original), original
        )
        end = self.events()[-1]
        self.assertEqual(end["status"], "ok")
        self.assertEqual(end["capture_error"]["code"], "PAGE_CHANGED")

    def test_operation_error_keeps_partial_effect_information(self):
        def fail():
            raise GameError(
                "TIME_SAVE_FAILED", advanced=True, seconds=60, cause="UNITY_REJECTED"
            )

        with self.assertRaises(GameError):
            self.recorded("wait", {"seconds": 60}, fail)
        end = self.events()[-1]
        self.assertEqual(end["status"], "error")
        self.assertTrue(end["error"]["details"]["advanced"])
        self.assertEqual(end["capture"], "captured")

    def test_disk_failure_disables_recorder_without_changing_result(self):
        self.recorded("look", {}, lambda: tools.look())
        call = self.recorder.begin("wait", {"seconds": 1})
        with (
            patch.object(self.recorder, "_append", side_effect=OSError("disk full")),
            self.assertLogs("aliens_mcp.recording"),
        ):
            self.recorder.finish(call, service, result={"ok": True})
        self.assertFalse(self.recorder.enabled)

    def test_mcp_boundary_captures_validation_errors_and_context_thread_handoff(self):
        with patch.dict(os.environ, {"ALIENS_MCP_RECORD": "0"}):
            server = RecordingServer("probe-test", instructions=INSTRUCTIONS)
        server.recorder = self.recorder
        import anyio

        server._record_lock = anyio.Lock()
        server.tool()(tools.look)

        async def run():
            await server.call_tool("look", {})
            try:
                await server.call_tool("look", {"force": "not-a-boolean"})
            except Exception:
                pass

        asyncio.run(run())
        ends = [e for e in self.events() if e["kind"] == "call.end"]
        self.assertEqual(ends[0]["capture"], "reused")
        self.assertEqual(ends[1]["status"], "error")
        seqs = [e["seq"] for e in self.events()]
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))

    def test_concurrent_mcp_calls_finish_capture_before_the_next_operation(self):
        with patch.dict(os.environ, {"ALIENS_MCP_RECORD": "0"}):
            server = RecordingServer("concurrent-test")
        server.recorder = self.recorder
        import anyio

        server._record_lock = anyio.Lock()
        visible = {"note": "initial"}
        self.client.snapshot.side_effect = lambda: page(visible["note"])

        @server.tool()
        async def note(hash: str, text: str) -> dict:
            visible["note"] = text
            await asyncio.sleep(0.01)
            return {"ok": True}

        async def run():
            await asyncio.gather(
                server.call_tool("note", {"hash": "qrag", "text": "first"}),
                server.call_tool("note", {"hash": "qrag", "text": "second"}),
            )

        asyncio.run(run())
        events = self.events()
        self.assertEqual(
            [e["kind"] for e in events],
            ["call.begin", "call.end", "call.begin", "call.end"],
        )
        self.assertEqual(
            [
                self.state(e)["snapshot"]["cells"][0]["note"]
                for e in events
                if e["kind"] == "call.end"
            ],
            ["first", "second"],
        )
