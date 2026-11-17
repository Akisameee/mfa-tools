"""Native runtime dispatch checks; Node is optional for Python-only development."""

import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(
    shutil.which("node"), "Node is needed for the JavaScript adapter checks"
)
class RuntimeBindingTests(unittest.TestCase):
    def check_adapter(self, scenario):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                shutil.which("node"),
                str(root / "tests/runtime_fixture.js"),
                str(root / "src/aliens_mcp/game/scripts/runtime.js"),
                scenario,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_mono_uses_inherited_members_public_array_api_and_cached_jit_addresses(
        self,
    ):
        self.check_adapter("mono")

    def test_il2cpp_keeps_its_method_and_array_conventions(self):
        self.check_adapter("il2cpp")

    def test_unknown_runtime_is_rejected_explicitly(self):
        self.check_adapter("unsupported")
