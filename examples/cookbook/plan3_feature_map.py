"""Print the plan3 feature map without requiring a live GemStone stone."""

from __future__ import annotations

from gemstone_py.cli import run_plan3_map


def main() -> int:
    """Print the plan3 feature map."""
    run_plan3_map()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
