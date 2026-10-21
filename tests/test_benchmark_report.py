"""The committed C5 benchmark report is regenerable byte for byte (issue #22)."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "benchmark" / "REPORT.md"


def test_the_committed_report_is_current() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "benchmark.py"), "--check"],
        cwd=ROOT, capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_number_is_stated_with_its_denominators_and_authority() -> None:
    text = REPORT.read_text(encoding="utf-8")
    assert "1/15 (owner)" in text
    assert "14 refuted" in text
    assert "3 cases" in text
