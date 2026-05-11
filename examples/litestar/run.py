"""Run the repository Litestar example with dependency checks."""

from __future__ import annotations

from gemstone_py.litestar_example import main


def main_entry() -> int:
    """Run ``examples.litestar.app:app`` through the shared Litestar runner."""
    return main(
        app_path="examples.litestar.app:app",
        factory=False,
        module_name="examples.litestar.run",
    )


if __name__ == "__main__":
    raise SystemExit(main_entry())
