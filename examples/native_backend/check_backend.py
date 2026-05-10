"""Show which GCI backend gemstone-py selected.

Install the optional native fast path with:

    python -m pip install "gemstone-py[fast]"

Then run:

    python -m examples.native_backend.check_backend

Set GEMSTONE_PY_GCI_BACKEND=ctypes or GEMSTONE_PY_GCI_BACKEND=native before
starting Python when you need to force a backend for comparison.
"""

from __future__ import annotations

from gemstone_py import _gci
from gemstone_py.native import native_fast_path_available


def main() -> None:
    print(f"selected backend: {_gci.IMPLEMENTATION}")
    print(f"native extension importable: {native_fast_path_available()}")


if __name__ == "__main__":
    main()
