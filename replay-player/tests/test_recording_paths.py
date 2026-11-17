import _paths  # noqa: F401
"""Direct recording paths and compatibility with existing replay bundles."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.data import prepare
from grading import evaluate


class RecordingPathTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.player = self.workspace / "replay-player"
        self.root = self.workspace / "recordings"
        self.legacy = self.root / "old-run"
        self.legacy.mkdir(parents=True)
        (self.legacy / "events.jsonl").write_text("{}\n")
        self.bundle = self.player / "data" / "replay.json"
        self.bundle.parent.mkdir(parents=True)
        self.enterContext(patch.object(prepare, "WORKSPACE", self.workspace))
        self.enterContext(patch.object(evaluate, "ROOT", self.player))

    def test_direct_log_is_preferred_when_no_bundle_exists(self):
        (self.root / "events.jsonl").write_text("{}\n")
        self.assertEqual(prepare.latest_recording(), self.root)
        self.assertEqual(evaluate.default_recording(), self.root)

    def test_legacy_log_remains_available_before_direct_recording_starts(self):
        (self.root / "events.jsonl").write_text("")
        self.assertEqual(prepare.latest_recording(), self.legacy)
        self.assertEqual(evaluate.default_recording(), self.legacy)

    def test_grading_resolves_direct_bundle_to_root(self):
        self.bundle.write_text(json.dumps({"recording": "recordings"}))
        self.assertEqual(evaluate.default_recording(), self.root)

    def test_grading_preserves_current_legacy_bundle_selection(self):
        (self.root / "events.jsonl").write_text("{}\n")
        self.bundle.write_text(json.dumps({"recording": "old-run"}))
        self.assertEqual(evaluate.default_recording(), self.legacy)


if __name__ == "__main__":
    unittest.main()
