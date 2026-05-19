"""Optional native fast path for gemstone-py."""

from . import _gci


def rust_core_available() -> bool:
    """Return whether the native extension exposes the gemstone-rs core bridge."""

    return hasattr(_gci, "RustCoreSession")


__all__ = ["_gci", "rust_core_available"]
