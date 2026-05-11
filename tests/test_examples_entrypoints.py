import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_grand_tour_help_does_not_start_live_session():
    result = subprocess.run(
        [sys.executable, "-m", "examples.example", "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "Demonstrates the full gemstone-py API" in result.stdout
    assert "python -m examples.example" in result.stdout
    assert "gci login" not in result.stdout
    assert "gci login" not in result.stderr
