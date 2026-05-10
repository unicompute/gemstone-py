"""Run the repository FastAPI example with dependency checks."""

from __future__ import annotations

from gemstone_py.fastapi_example import main


def main_entry() -> int:
    """Run ``examples.fastapi.app:app`` through the shared FastAPI runner."""
    return main(app_path="examples.fastapi.app:app", factory=False)


if __name__ == "__main__":
    raise SystemExit(main_entry())
