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


def test_codegen_preview_example_does_not_start_live_session():
    result = subprocess.run(
        [sys.executable, "-m", "examples.typed_access.codegen_demo.preview"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "gemstone-py Codegen preview" in result.stdout
    assert "okz_booking.py" in result.stdout
    assert "gemstone-codegen \\" in result.stdout
    assert "gci login" not in result.stdout
    assert "gci login" not in result.stderr


def test_codegen_live_probe_help_does_not_start_live_session():
    result = subprocess.run(
        [sys.executable, "-m", "examples.typed_access.codegen_demo.live_probe", "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "Call generated wrappers against a configured GemStone stone." in result.stdout
    assert "--booking-id" in result.stdout
    assert "gci login" not in result.stdout
    assert "gci login" not in result.stderr
