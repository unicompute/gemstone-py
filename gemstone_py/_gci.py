"""Low-level GCI constants, ctypes bindings, and OOP helpers."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
from typing import Optional

__all__ = [
    "OOP_ILLEGAL",
    "OOP_NIL",
    "OOP_FALSE",
    "OOP_TRUE",
    "OOP_ASCII_NUL",
    "GCI_ERR_STR_SIZE",
    "GCI_MAX_ERR_ARGS",
    "GCI_INVALID_SESSION",
    "GCI_ENCRYPT_BUF_SIZE",
    "GCI_LOGIN_PW_ENCRYPTED",
    "GCI_LOGIN_IS_GCSTS",
    "GciErrSType",
    "_is_smallint",
    "_is_smalldouble",
    "_smallint_to_python",
    "_python_to_smallint",
    "_is_char",
    "_char_to_python",
    "_load_library",
    "_bind",
]


# ---------------------------------------------------------------------------
# OOP constants  (from gcioop.ht)
# ---------------------------------------------------------------------------

OOP_ILLEGAL = 0x01
OOP_NIL = 0x14
OOP_FALSE = 0x0C
OOP_TRUE = 0x10C
OOP_ASCII_NUL = 0x1C

# Tag bits (bottom 3 bits of OOP)
_TAG_SMALLINT = 0x2
_TAG_SMALLDOUBLE = 0x6
_TAG_SPECIAL = 0x4
_TAG_POM = 0x1

# SmallInteger: value occupies top 61 bits (arithmetic right-shift by 3)
_SMALLINT_SHIFT = 3

# Character OOP: low byte is 0x1C, unicode code point in bits 8+
_CHAR_TAG_BYTE = 0x1C

# GCI constants
GCI_ERR_STR_SIZE = 1024
GCI_MAX_ERR_ARGS = 10
GCI_INVALID_SESSION = 0
GCI_ENCRYPT_BUF_SIZE = 1024

# Login flags
GCI_LOGIN_PW_ENCRYPTED = 0x1
GCI_LOGIN_IS_GCSTS = 0x2


class GciErrSType(ctypes.Structure):
    """
    Maps to GciErrSType in gci.ht.

    Order of fields matches the C++ class layout exactly.
    """

    _fields_ = [
        ("category", ctypes.c_uint64),
        ("context", ctypes.c_uint64),
        ("exceptionObj", ctypes.c_uint64),
        ("args", ctypes.c_uint64 * GCI_MAX_ERR_ARGS),
        ("number", ctypes.c_int),
        ("argCount", ctypes.c_int),
        ("fatal", ctypes.c_ubyte),
        ("message", ctypes.c_char * (GCI_ERR_STR_SIZE + 1)),
        ("reason", ctypes.c_char * (GCI_ERR_STR_SIZE + 1)),
    ]


def _is_smallint(oop: int) -> bool:
    return (oop & 0x7) == _TAG_SMALLINT


def _is_smalldouble(oop: int) -> bool:
    return (oop & 0x7) == _TAG_SMALLDOUBLE


def _smallint_to_python(oop: int) -> int:
    """Signed 64-bit arithmetic right-shift by 3."""
    return ctypes.c_int64(oop).value >> _SMALLINT_SHIFT


def _python_to_smallint(value: int) -> int:
    return ctypes.c_uint64((value << _SMALLINT_SHIFT) | _TAG_SMALLINT).value


def _is_char(oop: int) -> bool:
    return (oop & 0xFF) == _CHAR_TAG_BYTE and (oop & 0x6) == _TAG_SPECIAL


def _char_to_python(oop: int) -> str:
    return chr((oop >> 8) & 0x1FFFFF)


def _load_library(lib_path: Optional[str] = None) -> ctypes.CDLL:
    if lib_path:
        return ctypes.CDLL(lib_path)

    gs_lib = os.environ.get("GS_LIB") or os.path.join(os.environ.get("GEMSTONE", ""), "lib")
    if gs_lib and os.path.isdir(gs_lib):
        for name in sorted(os.listdir(gs_lib), reverse=True):
            if name.startswith("libgcirpc") and (name.endswith(".dylib") or name.endswith(".so")):
                return ctypes.CDLL(os.path.join(gs_lib, name))

    found = ctypes.util.find_library("gcirpc")
    if found:
        return ctypes.CDLL(found)

    raise OSError(
        "Cannot find libgcirpc. Pass lib_path= or set GS_LIB to the "
        "GemStone lib directory."
    )


def _bind(lib: ctypes.CDLL) -> None:
    """Attach argtypes/restype to the GCI functions we use."""

    def bind(name, restype, *argtypes):
        if hasattr(lib, name):
            fn = getattr(lib, name)
            fn.restype = restype
            fn.argtypes = list(argtypes)

    p_err = ctypes.POINTER(GciErrSType)
    u64 = ctypes.c_uint64
    i64 = ctypes.c_int64
    c_int = ctypes.c_int
    c_str = ctypes.c_char_p
    c_uint = ctypes.c_uint

    bind("GciInit", c_int)
    bind("GciSetNet", None, c_str, c_str, c_str, c_str)
    bind("GciEncrypt", c_str, c_str, ctypes.c_char_p, c_uint)
    bind("GciLoginEx", c_int, c_str, c_str, c_uint, c_int)
    bind("GciLogout", c_int)
    bind("GciCommit", c_int, p_err)
    bind("GciAbort", c_int, p_err)
    bind("GciErr", c_int, p_err)
    bind("GciExecuteStr", u64, c_str, u64)
    bind("GciNewString", u64, c_str)
    bind("GciNewSymbol", u64, c_str)
    bind("GciFltToOop", u64, ctypes.c_double)
    bind("GciOopToFlt_", c_int, u64, ctypes.POINTER(ctypes.c_double))
    bind("GciFetchSize_", i64, u64)
    bind("GciFetchBytes_", i64, u64, i64, ctypes.c_char_p, i64)
    bind("GciFetchClass", u64, u64)
    bind("GciPerform", u64, u64, c_str, ctypes.POINTER(u64), c_int)
    bind("GciNewOop", u64, u64)
    bind("GciResolveSymbol", u64, c_str, u64)
    bind("GciSymDictAtPut", None, u64, c_str, u64)
    bind("GciSymDictAtObjPut", None, u64, u64, u64)
    bind("GciStrKeyValueDictAtPut", None, u64, c_str, u64)
    bind("GciStrKeyValueDictAt", None, u64, c_str, ctypes.POINTER(u64))
    bind("GciSymDictAt", None, u64, c_str, ctypes.POINTER(u64), ctypes.POINTER(u64))
    bind("GciGetSessionId", c_int)
    bind("GciSetSessionId", None, c_int)
    bind("GciNeedsCommit", c_int)
    bind("GciInTransaction", c_int)
