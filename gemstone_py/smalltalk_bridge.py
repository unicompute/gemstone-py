"""
Smalltalk bridge for gemstone-py.

Python already has explicit object references, so the useful bridge here is
a small helper that:

1. resolves Smalltalk globals lazily from a GemStone session, and
2. forwards Python calls to Smalltalk selectors with automatic marshalling.

Usage
-----
    import gemstone_py as gemstone
    from gemstone_py.smalltalk_bridge import SmalltalkBridge

    with gemstone.GemStoneSession() as s:
        st = SmalltalkBridge(s)

        repo_name = st.SystemRepository.name()
        repo_name = st['SystemRepository'].name()
        numbers   = st.Array.new_(3)          # selector: new:
        now       = st.DateAndTime.now()
        status    = st.send('SystemRepository', 'name')

        root = st.UserGlobals
        root.at_put_('BridgeDemo', 42)        # selector: at:put:

Selector naming
---------------
Python attribute names are mapped to Smalltalk selectors:

    size          -> 'size'
    new_          -> 'new:'
    at_put_       -> 'at:put:'
    removeKey_ifAbsent_ -> 'removeKey:ifAbsent:'

Underscores become keyword colons. A trailing underscore adds the final colon.
If you need an exact selector string, use `send('selector', *args)`.
"""

from __future__ import annotations

from typing import Any

import gemstone_py as _gs
from gemstone_py.persistent_root import GsObject, _to_oop, _from_oop

PORTING_STATUS = "plain_gemstone_port"
RUNTIME_REQUIREMENT = "Works on plain GemStone images over GCI"


def _python_name_to_selector(name: str) -> str:
    """
    Convert a Python-friendly method name to a Smalltalk selector.

    Examples:
        new_           -> new:
        at_put_        -> at:put:
        removeAll      -> removeAll
    """
    if not name or name.startswith('__'):
        raise AttributeError(name)
    if '_' not in name:
        return name
    return name.replace('_', ':')


class SmalltalkObject:
    """Proxy for a resolved Smalltalk object or class."""

    def __init__(self, session: _gs.GemStoneSession, oop: int, name: str | None = None):
        object.__setattr__(self, '_session', session)
        object.__setattr__(self, '_oop', oop)
        object.__setattr__(self, '_name', name)

    def send(self, selector: str, *args: Any) -> Any:
        """Send `selector` to the wrapped Smalltalk object."""
        s = object.__getattribute__(self, '_session')
        oop = object.__getattribute__(self, '_oop')
        raw = [_to_oop(s, arg) for arg in args]
        result_oop = s.perform_oop(oop, selector, *raw)
        return _wrap_smalltalk_result(s, result_oop)

    def send_oop(self, selector: str, *args: Any) -> int:
        """Like send(), but return the raw OOP."""
        s = object.__getattribute__(self, '_session')
        oop = object.__getattribute__(self, '_oop')
        raw = [_to_oop(s, arg) for arg in args]
        return s.perform_oop(oop, selector, *raw)

    def __getattr__(self, name: str):
        selector = _python_name_to_selector(name)

        def dispatcher(*args: Any) -> Any:
            return self.send(selector, *args)

        dispatcher.__name__ = name
        dispatcher.__doc__ = f"Dispatches to Smalltalk selector `{selector}`."
        return dispatcher

    @property
    def oop(self) -> int:
        return object.__getattribute__(self, '_oop')

    def __repr__(self) -> str:
        name = object.__getattribute__(self, '_name')
        oop = object.__getattribute__(self, '_oop')
        label = f" {name}" if name else ''
        return f"<SmalltalkObject{label} oop=0x{oop:X}>"


class SmalltalkBridge:
    """Resolve Smalltalk globals lazily from a GemStone session."""

    def __init__(self, session: _gs.GemStoneSession):
        object.__setattr__(self, '_session', session)

    def resolve(self, name: str) -> SmalltalkObject:
        """Resolve a Smalltalk global name and return a proxy."""
        s = object.__getattribute__(self, '_session')
        return SmalltalkObject(s, s.resolve(name), name=name)

    def send(self, global_name: str, selector: str, *args: Any) -> Any:
        """Resolve `global_name` and send `selector` to it in one step."""
        return self.resolve(global_name).send(selector, *args)

    def __getitem__(self, name: str) -> SmalltalkObject:
        """Allow `bridge['SystemRepository']` for names not suited to dot syntax."""
        return self.resolve(name)

    def __getattr__(self, name: str) -> SmalltalkObject:
        if name.startswith('_'):
            raise AttributeError(name)
        return self.resolve(name)


def bridge(session: _gs.GemStoneSession) -> SmalltalkBridge:
    """Convenience constructor."""
    return SmalltalkBridge(session)


def _wrap_smalltalk_result(session: _gs.GemStoneSession, oop: int) -> Any:
    """
    Return the most useful Python view of a Smalltalk send result.

    Keep native Python values and richer GemStone proxies as-is, but promote
    the generic `GsObject` fallback to `SmalltalkObject` so callers can keep
    chaining Smalltalk sends naturally.
    """
    value = _from_oop(session, oop)
    if isinstance(value, GsObject):
        return SmalltalkObject(session, oop)
    return value
