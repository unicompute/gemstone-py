"""Low-level GCI shim.

The pure-ctypes implementation is always available. When an optional
``gemstone_py_native._gci`` module is installed and exports the same symbols,
this shim uses it instead.
"""

from __future__ import annotations

import os

_REQUESTED_BACKEND = os.environ.get("GEMSTONE_PY_GCI_BACKEND", "auto").strip().lower()

if _REQUESTED_BACKEND not in {"auto", "ctypes", "native"}:
    raise RuntimeError(
        "GEMSTONE_PY_GCI_BACKEND must be one of: auto, ctypes, native"
    )

if _REQUESTED_BACKEND == "ctypes":
    from ._gci_ctypes import *  # noqa: F403
    from ._gci_ctypes import __all__ as __all__

    IMPLEMENTATION = "ctypes"
else:
    try:
        from gemstone_py_native._gci import *  # type: ignore[import-not-found,wildcard-import] # noqa: F403,E501
        from gemstone_py_native._gci import __all__ as __all__

        IMPLEMENTATION = "native"
    except ImportError:
        if _REQUESTED_BACKEND == "native":
            raise
        from ._gci_ctypes import *  # noqa: F403
        from ._gci_ctypes import __all__ as __all__

        IMPLEMENTATION = "ctypes"

__all__ = [*list(__all__), "IMPLEMENTATION"]
