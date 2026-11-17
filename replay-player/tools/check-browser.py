"""Compatibility launcher for current data-driven browser checks."""
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parent.parent
subprocess.run(["node",str(root/"tests"/"browser.mjs")],cwd=root.parent,check=True)
