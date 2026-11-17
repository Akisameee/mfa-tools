"""Native annotation identity restoration and rollback; Node is optional."""

import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(
    shutil.which("node"), "Node is needed for JavaScript commit checks"
)
class NoteRuntimeTests(unittest.TestCase):
    def test_off_page_commit_rollback_and_focus_preservation(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                shutil.which("node"),
                str(root / "tests/note_fixture.js"),
                str(root / "src/aliens_mcp/game/scripts/annotations.js"),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
