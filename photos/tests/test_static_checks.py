"""Catches the mistakes tests miss: a name used but never defined or imported fails only when that line runs on the user's Mac."""

import compileall
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).parent.parent / "src"


def test_every_module_compiles():
    assert compileall.compile_dir(str(SRC), quiet=1, force=True)


def test_no_undefined_names_anywhere():
    exe = shutil.which("ruff")
    if exe is None:
        pytest.skip("ruff is not installed")
    done = subprocess.run(
        [exe, "check", str(SRC), "--select", "F821,F822,F823,F811,E9", "--no-cache", "--output-format", "concise"],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stdout + done.stderr
