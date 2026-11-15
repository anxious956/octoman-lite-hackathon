"""Runs the dashboard's JavaScript unit tests (tests/js) with Node's built-in test runner."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
def test_derive_js_unit_tests():
    result = subprocess.run([NODE, "--test", str(ROOT / "tests" / "js" / "derive.test.mjs")],
                            cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
@pytest.mark.parametrize("name", ["app.js", "derive.js"])
def test_dashboard_modules_parse(name):
    result = subprocess.run([NODE, "--check", str(ROOT / "dashboard" / "assets" / name)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
