"""Framework adapter entry points for gemstone-py."""

from __future__ import annotations

from importlib import import_module

_LAZY_EXPORTS = {
    "django": "gemstone_py.frameworks.django",
    "flask": "gemstone_py.frameworks.flask",
}


def __getattr__(name: str) -> object:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(target)
    globals()[name] = module
    return module


__all__ = ["django", "flask"]
