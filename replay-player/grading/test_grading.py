"""Offline regressions, including a real local HTTP Chat Completions stub."""

from contextlib import redirect_stdout
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from grading.evaluate import FatalAPIError, grade_batch, run, validate_response
from grading.reference import numeric_value
from grading.store import annotation_versions, append_jsonl, atomic_json, read_jsonl


class GradingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.recording = self.root / "recording"
        (self.recording / "states").mkdir(parents=True)
        self.assets = self.root / "resources.assets"
        self.assets.write_bytes(b"test resources")
        self.fingerprint = hashlib.sha256(self.assets.read_bytes()).hexdigest()
        self.calls = []
        self.mode = "ok"
        test = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                test.calls.append((self.path, self.headers.get("Authorization"), body))
                if test.mode == "unauthorized":
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b"dummy-secret rejected")
                    return
                if test.mode == "retry" and len(test.calls) == 1:
                    self.send_response(503)
                    self.end_headers()
                    return
                items = json.loads(body["messages"][1]["content"])["items"]
                results = [
                    {
                        "id": i["id"],
                        "grade": "wrong" if i["annotation"] == "旧" else "correct",
                        "reason": "依据字典定义判断",
                    }
                    for i in items
                ]
                response = {
                    "choices": [
                        {
                            "finish_reason": "length"
                            if test.mode == "length"
                            else "stop",
                            "message": {"content": json.dumps({"results": results})},
                        }
                    ],
                    "usage": {"total_tokens": 10},
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.config = self.root / "config.toml"
        self.config.write_text(
            f'base_url = "http://127.0.0.1:{self.server.server_port}/v1"\n'
            'model = "test-model"\napi_key_env = "UNUSED_GRADING_TEST_KEY"\n'
            'api_key = "dummy-secret"\nbatch_size = 1\nconcurrency = 1\nretry_attempts = 1\n',
            encoding="utf-8",
        )
        snapshot = {
            "snapshot": {"page": "test", "cells": [{"word": "a", "note": "旧"}]}
        }
        atomic_json(self.recording / "states" / "first.json", snapshot)
        events = [
            {
                "kind": "call.begin",
                "call_id": "old",
                "tool": "note",
                "arguments": {"text": "旧"},
            },
            {
                "kind": "call.end",
                "call_id": "old",
                "tool": "note",
                "status": "ok",
                "character": {"key": "a"},
            },
            {
                "kind": "call.end",
                "call_id": "look",
                "tool": "look",
                "state_ref": "states/first.json",
                "state_observed": True,
            },
            {
                "kind": "call.begin",
                "call_id": "note",
                "tool": "note",
                "arguments": {"text": "新"},
            },
            {
                "kind": "call.end",
                "call_id": "note",
                "tool": "note",
                "status": "ok",
                "character": {"key": "a"},
            },
            {
                "kind": "call.begin",
                "call_id": "bad",
                "tool": "note",
                "arguments": {"text": "未写入"},
            },
            {
                "kind": "call.end",
                "call_id": "bad",
                "tool": "note",
                "status": "error",
                "character": {"key": "a"},
            },
        ]
        for event in events:
            append_jsonl(self.recording / "events.jsonl", event)
        self.original = (self.recording / "events.jsonl").read_bytes()
        atomic_json(
            self.recording / "grading" / "reference.json",
            {
                "version": 1,
                "assets_fingerprint": self.fingerprint,
                "notation": "test",
                "entries": {
                    "a": {
                        "key": "a",
                        "english": "a",
                        "dictionary_text": "author definition",
                    }
                },
            },
        )
        self.bundle = self.root / "replay.json"
        atomic_json(
            self.bundle,
            {
                "recording": self.recording.name,
                "glyphs": {"fingerprint": self.fingerprint},
            },
        )

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temporary.cleanup()

    def args(self, **changes):
        values = dict(
            recording=self.recording,
            config=self.config,
            bundle=self.bundle,
            assets=self.assets,
            prepare_only=False,
            attach_only=False,
            limit=0,
            retry_unresolved=False,
        )
        values.update(changes)
        return SimpleNamespace(**values)

    def test_versions_use_only_successful_note_inputs(self):
        # Snapshot contents are intentionally unreadable: they are not inputs
        # to this pipeline, even when an observed look references the file.
        (self.recording / "states" / "first.json").write_text(
            "not JSON", encoding="utf-8"
        )
        self.assertEqual(
            annotation_versions(self.recording),
            [
                {"key": "a", "annotation": "旧"},
                {"key": "a", "annotation": "新"},
            ],
        )

    def test_resume_history_and_no_source_mutation(self):
        original_bundle = self.bundle.read_bytes()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(run(self.args(limit=1)), 0)
            self.assertEqual(len(self.calls), 1)
            self.assertEqual(run(self.args()), 0)
            self.assertEqual(len(self.calls), 2)
            self.assertEqual(run(self.args()), 0)
        self.assertEqual(len(self.calls), 2)
        lookup = json.loads((self.root / "grading.json").read_text(encoding="utf-8"))["grading"][
            "lookup"
        ]
        self.assertEqual(lookup["a"]["旧"]["grade"], "wrong")
        self.assertEqual(lookup["a"]["新"]["grade"], "correct")
        self.assertEqual(self.bundle.read_bytes(), original_bundle)
        exported = json.loads((self.root / "grading.json").read_text(encoding="utf-8"))
        self.assertEqual(exported["recording"], self.recording.name)
        self.assertEqual(exported["grading"]["references"]["a"]["dictionary_text"], "author definition")
        self.assertEqual((self.recording / "events.jsonl").read_bytes(), self.original)
        self.assertEqual(self.calls[0][0], "/v1/chat/completions")
        self.assertEqual(self.calls[0][1], "Bearer dummy-secret")
        self.assertEqual(self.calls[0][2]["response_format"], {"type": "json_object"})
        for path in (self.recording / "grading").glob("*.json*"):
            self.assertNotIn("dummy-secret", path.read_text(encoding="utf-8"))

    def test_prepare_only_makes_no_requests_or_metadata_change(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(run(self.args(prepare_only=True)), 0)
        self.assertEqual(self.calls, [])
        self.assertFalse((self.recording / "grading" / "metadata.json").exists())

    def test_snapshots_are_ignored_and_player_parentheses_survive(self):
        with redirect_stdout(io.StringIO()):
            run(self.args())
        calls = len(self.calls)
        atomic_json(
            self.recording / "states" / "hint.json",
            {
                "snapshot": {"cells": [{"word": "a", "note": "新 (106)"}]},
            },
        )
        append_jsonl(
            self.recording / "events.jsonl",
            {
                "kind": "call.end",
                "tool": "look",
                "call_id": "hint",
                "state_observed": True,
                "state_ref": "states/hint.json",
            },
        )
        with redirect_stdout(io.StringIO()):
            run(self.args())
        self.assertEqual(len(self.calls), calls)
        lookup = json.loads((self.root / "grading.json").read_text(encoding="utf-8"))["grading"][
            "lookup"
        ]
        self.assertNotIn("新 (106)", lookup["a"])
        # Parentheses explicitly written by the player remain a new version,
        # including when they first appear in this same call's snapshot.
        atomic_json(
            self.recording / "states" / "written.json",
            {
                "snapshot": {"cells": [{"word": "a", "note": "新 (另一种含义)"}]},
            },
        )
        append_jsonl(
            self.recording / "events.jsonl",
            {
                "kind": "call.begin",
                "call_id": "parentheses",
                "tool": "note",
                "arguments": {"text": "新 (另一种含义)"},
            },
        )
        append_jsonl(
            self.recording / "events.jsonl",
            {
                "kind": "call.end",
                "call_id": "parentheses",
                "tool": "note",
                "status": "ok",
                "character": {"key": "a"},
                "state_observed": True,
                "state_ref": "states/written.json",
            },
        )
        self.assertIn(
            "新 (另一种含义)",
            [i["annotation"] for i in annotation_versions(self.recording)],
        )

    def test_api_retry_and_fatal_error_redaction(self):
        from grading.evaluate import load_config

        config = load_config(self.config)
        config["retry_attempts"] = 2
        item = {"id": "item", "annotation": "新", "reference": {}}
        self.mode = "retry"
        with patch("grading.evaluate.time.sleep"):
            rows, _ = grade_batch(config, "Return JSON", "", [item])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(rows[0]["grade"], "correct")
        self.mode = "unauthorized"
        with self.assertRaises(FatalAPIError) as raised:
            grade_batch(config, "Return JSON", "", [item])
        self.assertNotIn("dummy-secret", str(raised.exception))
        self.mode = "length"
        config["retry_attempts"] = 1
        with self.assertRaisesRegex(RuntimeError, "truncated"):
            grade_batch(config, "Return JSON", "", [item])

    def test_bad_or_missing_response_ids_are_rejected(self):
        items = [{"id": "a"}, {"id": "b"}]
        for results in [
            [],
            [{"id": "other", "grade": "correct", "reason": "x"}],
            [{"id": "a", "grade": "green", "reason": "x"}],
        ]:
            with self.assertRaises(ValueError):
                validate_response(json.dumps({"results": results}), items)

    def test_partial_append_is_repaired_on_resume(self):
        path = self.root / "partial.jsonl"
        path.write_bytes(b'{"id":"saved"}\n{"id":"interrupted')
        self.assertEqual(list(read_jsonl(path)), [{"id": "saved"}])
        append_jsonl(path, {"id": "next"})
        self.assertEqual(list(read_jsonl(path)), [{"id": "saved"}, {"id": "next"}])

    def test_base_seven_numeric_reference(self):
        self.assertEqual(numeric_value("4e1"), "28")
        self.assertEqual(numeric_value("3e-2"), "3/49")
        self.assertIsNone(numeric_value("4D1"))

    def test_atomic_json_replaces_complete_output_without_leaving_temporary_file(self):
        path = self.root / "bundle.json"
        atomic_json(path, {"old": True})
        atomic_json(path, {"new": True})
        self.assertEqual(json.loads(path.read_text()), {"new": True})
        self.assertFalse(list(self.root.glob("bundle.json.*.tmp")))

    def test_atomic_json_permanent_denial_preserves_both_output_and_old_file(self):
        path = self.root / "bundle.json"
        atomic_json(path, {"old": True})
        with patch.object(Path, "replace", side_effect=PermissionError(5, "Access denied")) as replace:
            with self.assertRaises(PermissionError):
                atomic_json(path, {"new": True})
        self.assertEqual(replace.call_count, 1)
        self.assertEqual(json.loads(path.read_text()), {"old": True})
        pending = list(self.root.glob("bundle.json.*.tmp"))
        self.assertEqual(len(pending), 1)
        self.assertEqual(json.loads(pending[0].read_text()), {"new": True})


if __name__ == "__main__":
    unittest.main()
