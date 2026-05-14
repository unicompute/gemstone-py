"""Preview explicit value converters without requiring a live GemStone stone.

Run from the repository root:

    python -m examples.cookbook.value_converters

From an installed package:

    gemstone-examples value-converters
"""

from __future__ import annotations

from gemstone_py.cli import run_value_converters_preview


def main() -> int:
    """Print the offline converter preview."""
    run_value_converters_preview()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
