"""Optional native fast-path discovery for gemstone-py."""

from __future__ import annotations

from importlib import import_module
from types import ModuleType


def native_module() -> ModuleType | None:
    """Return the optional ``gemstone_py_native._gci`` module when installed."""
    try:
        return import_module("gemstone_py_native._gci")
    except ImportError:
        return None


def native_fast_path_available() -> bool:
    """Return whether the optional native GCI extension can be imported."""
    return native_module() is not None


def rust_core_available() -> bool:
    """Return whether the optional native extension exposes the gemstone-rs core."""
    module = native_module()
    return module is not None and hasattr(module, "RustCoreSession")


__all__ = ["native_fast_path_available", "native_module", "rust_core_available"]
