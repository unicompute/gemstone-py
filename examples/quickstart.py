"""A small first example for a configured GemStone stone.

Run from a source checkout:

    python -m examples.quickstart
"""

from __future__ import annotations

from gemstone_py.cli import run_quickstart


def main() -> int:
    run_quickstart()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
