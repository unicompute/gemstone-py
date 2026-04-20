"""
PersistentRoot — a GemStone SymbolDictionary root for Python.

Python talks to GemStone as an external GCI client, so persistent objects
must be created explicitly in the repository. PersistentRoot wraps a live
GemStone SymbolDictionary and mirrors Python writes into GemStone
immediately through direct GCI calls.

GsDict mirrors a Python dict as a live GemStone StringKeyValueDictionary.
Every __setitem__ on a GsDict calls GciStrKeyValueDictAtPut immediately.
Nested dicts produce nested GsDicts.

Usage
-----
    import gemstone_py as gemstone
    from gemstone_py.persistent_root import PersistentRoot

    with gemstone.GemStoneSession(...) as s:
        root = PersistentRoot(s)

        root['MyDict'] = {'name': 'Tariq', 'amount': 100, 'currency': 'GBP'}

        root['Config'] = {'debug': False, 'retries': 3}

        # Nested
        root['Order'] = {
            'id': 42,
            'customer': {'name': 'Alice', 'city': 'London'},
        }

        # Commit makes the mirrored changes durable in GemStone.
        # — or just exit the `with` block cleanly.

    # Read back in a later session:
    with gemstone.GemStoneSession(...) as s:
        root = PersistentRoot(s)
        d = root['MyDict']          # GsDict proxy
        print(d['name'])            # 'Tariq'
        print(dict(d))              # {'name': 'Tariq', 'amount': 100, ...}
"""

import ctypes
from typing import Any, Iterator, cast

import gemstone_py as _gs

from ._smalltalk_batch import (
    fetch_mapping_string_keys as _fetch_mapping_string_keys,
)
from ._smalltalk_batch import (
    fetch_mapping_string_oop_pairs as _fetch_mapping_string_oop_pairs,
)

PORTING_STATUS = "plain_gemstone_port"
RUNTIME_REQUIREMENT = "Works on plain GemStone images over GCI"


def _python_name_to_selector(name: str) -> str:
    """Convert a Python-friendly method name to a Smalltalk selector."""
    if not name or name.startswith('__'):
        raise AttributeError(name)
    if '_' not in name:
        return name
    return name.replace('_', ':')


class GsDict:
    """
    A Python proxy for a live GemStone StringKeyValueDictionary.

    Every write is immediately sent to GemStone via GciStrKeyValueDictAtPut.
    Every read fetches from GemStone via GciStrKeyValueDictAt.
    Nested Python dicts are automatically converted to nested GsDicts.

    Behaves like a live GemStone dictionary proxy.
    """

    def __init__(self, session: _gs.GemStoneSession, oop: int):
        # Use object.__setattr__ to avoid triggering our own __setattr__
        object.__setattr__(self, '_session', session)
        object.__setattr__(self, '_oop', oop)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def __setitem__(self, key: str, value: Any) -> None:
        s   = object.__getattribute__(self, '_session')
        oop = object.__getattribute__(self, '_oop')
        v_oop = _to_oop(s, value)
        s._lib.GciStrKeyValueDictAtPut(
            ctypes.c_uint64(oop),
            str(key).encode('utf-8'),
            ctypes.c_uint64(v_oop),
        )

    def __delitem__(self, key: str) -> None:
        if key not in self:
            raise KeyError(key)
        self._call('removeKey:ifAbsent:', key, None)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        s   = object.__getattribute__(self, '_session')
        oop = object.__getattribute__(self, '_oop')
        value = ctypes.c_uint64(_gs.OOP_ILLEGAL)
        s._lib.GciStrKeyValueDictAt(
            ctypes.c_uint64(oop),
            str(key).encode('utf-8'),
            ctypes.byref(value),
        )
        v = value.value
        if v == _gs.OOP_ILLEGAL:
            raise KeyError(key)
        return _from_oop(s, v)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        try:
            self[key]
            return True
        except KeyError:
            return False

    def keys(self) -> list[str]:
        """
        Return string keys for StringKeyValueDictionary objects.
        Batch them into one Smalltalk eval instead of per-entry RPCs.
        """
        s = object.__getattribute__(self, '_session')
        oop = object.__getattribute__(self, '_oop')
        return _fetch_mapping_string_keys(s, oop)

    def items(self) -> list[tuple[str, Any]]:
        s = object.__getattribute__(self, '_session')
        oop = object.__getattribute__(self, '_oop')
        return _batched_mapping_items(s, oop)

    def values(self) -> list[Any]:
        s = object.__getattribute__(self, '_session')
        oop = object.__getattribute__(self, '_oop')
        return _batched_mapping_values(s, oop)

    def pop(self, key: str, default: Any = ...) -> Any:
        if key in self:
            value = self[key]
            del self[key]
            return value
        if default is ...:
            raise KeyError(key)
        return default

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key in self:
            return self[key]
        self[key] = default
        return default

    def update(self, other: Any = None, /, **kwargs: Any) -> None:
        if other is not None:
            if hasattr(other, 'items'):
                iterable = other.items()
            else:
                iterable = other
            for key, value in iterable:
                self[key] = value
        for key, value in kwargs.items():
            self[key] = value

    def clear(self) -> None:
        self._call('removeAll')

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    def __len__(self) -> int:
        s = object.__getattribute__(self, '_session')
        oop = object.__getattribute__(self, '_oop')
        return cast(int, s.perform(oop, 'size'))

    def _call(self, selector: str, *args: Any) -> Any:
        """Send an arbitrary Smalltalk message to this dict's OOP."""
        s   = object.__getattribute__(self, '_session')
        oop = object.__getattribute__(self, '_oop')
        raw = [_to_oop(s, a) for a in args]
        return s.perform(oop, selector, *raw)

    def _call_oop(self, selector: str, *args: Any) -> int:
        s   = object.__getattribute__(self, '_session')
        oop = object.__getattribute__(self, '_oop')
        raw = [_to_oop(s, a) for a in args]
        return cast(int, s.perform_oop(oop, selector, *raw))

    def send(self, selector: str, *args: Any) -> Any:
        return _from_oop(
            object.__getattribute__(self, '_session'),
            self._call_oop(selector, *args),
        )

    def send_oop(self, selector: str, *args: Any) -> int:
        return self._call_oop(selector, *args)

    def __getattr__(self, name: str) -> Any:
        selector = _python_name_to_selector(name)

        def dispatcher(*args: Any) -> Any:
            return self.send(selector, *args)

        dispatcher.__name__ = name
        dispatcher.__doc__ = f"Dispatches to Smalltalk selector `{selector}`."
        return dispatcher

    @property
    def oop(self) -> int:
        return cast(int, object.__getattribute__(self, '_oop'))

    def __repr__(self) -> str:
        oop = object.__getattribute__(self, '_oop')
        return f"<GsDict oop=0x{oop:X}>"

    def __str__(self) -> str:
        oop = object.__getattribute__(self, '_oop')
        return f"<GsDict oop=0x{oop:X}>"


class GsObject:
    """
    Generic proxy for a live GemStone object when no richer Python wrapper
    exists for its class.

    Provides the same low-level message-send helpers as GsDict without
    assuming dictionary semantics.
    """

    def __init__(self, session: _gs.GemStoneSession, oop: int):
        object.__setattr__(self, '_session', session)
        object.__setattr__(self, '_oop', oop)

    def _call(self, selector: str, *args: Any) -> Any:
        s   = object.__getattribute__(self, '_session')
        oop = object.__getattribute__(self, '_oop')
        raw = [_to_oop(s, a) for a in args]
        return s.perform(oop, selector, *raw)

    def _call_oop(self, selector: str, *args: Any) -> int:
        s   = object.__getattribute__(self, '_session')
        oop = object.__getattribute__(self, '_oop')
        raw = [_to_oop(s, a) for a in args]
        return cast(int, s.perform_oop(oop, selector, *raw))

    def send(self, selector: str, *args: Any) -> Any:
        return _from_oop(
            object.__getattribute__(self, '_session'),
            self._call_oop(selector, *args),
        )

    def send_oop(self, selector: str, *args: Any) -> int:
        return self._call_oop(selector, *args)

    def __getattr__(self, name: str) -> Any:
        selector = _python_name_to_selector(name)

        def dispatcher(*args: Any) -> Any:
            return self.send(selector, *args)

        dispatcher.__name__ = name
        dispatcher.__doc__ = f"Dispatches to Smalltalk selector `{selector}`."
        return dispatcher

    @property
    def oop(self) -> int:
        return cast(int, object.__getattribute__(self, '_oop'))

    def __repr__(self) -> str:
        oop = object.__getattribute__(self, '_oop')
        return f"<GsObject oop=0x{oop:X}>"

    def __str__(self) -> str:
        return repr(self)


class PersistentRoot:
    """
    Wrap a GemStone SymbolDictionary as a dict-like object.

    Every assignment mirrors the value into GemStone immediately via GCI
    calls. Reading fetches from GemStone. Call session.commit() (or exit the
    `with` block) to make changes durable.

    The four SymbolDictionaries in a DataCurator session's symbol list:

        PersistentRoot(s)                   # UserGlobals — user data (writable)
        PersistentRoot.globals(s)           # Globals     — all system classes (read-only)
        PersistentRoot.published(s)         # Published   — shared published objects
        PersistentRoot.session_methods(s)   # SessionMethods — per-session transient

    GciResolveSymbol searches all four in symbol-list order, so names like
    'Dictionary' or 'Array' resolve from Globals without specifying which
    dictionary.  UserGlobals is searched first, so user-defined names there
    shadow system names.

        root = PersistentRoot(s)
        root['MyDict'] = {'name': 'Tariq', 'amount': 100}
        session.commit()
    """

    def __init__(self, session: _gs.GemStoneSession, _name: str = 'UserGlobals'):
        object.__setattr__(self, '_session', session)
        object.__setattr__(self, '_name', _name)
        object.__setattr__(self, '_ug', session.resolve(_name))

    @classmethod
    def globals(cls, session: _gs.GemStoneSession) -> 'PersistentRoot':
        """Wrap the Globals SymbolDictionary (all GemStone system classes)."""
        return cls(session, 'Globals')

    @classmethod
    def published(cls, session: _gs.GemStoneSession) -> 'PersistentRoot':
        """Wrap the Published SymbolDictionary."""
        return cls(session, 'Published')

    @classmethod
    def session_methods(cls, session: _gs.GemStoneSession) -> 'PersistentRoot':
        """Wrap the SessionMethods SymbolDictionary (transient, per-session)."""
        return cls(session, 'SessionMethods')

    # ------------------------------------------------------------------
    # Write — mirrors to GemStone immediately
    # ------------------------------------------------------------------

    def __setitem__(self, key: str, value: Any) -> None:
        s  = object.__getattribute__(self, '_session')
        ug = object.__getattribute__(self, '_ug')
        v_oop  = _to_oop(s, value)
        sym    = s.new_symbol(str(key))
        s._lib.GciSymDictAtObjPut(
            ctypes.c_uint64(ug),
            ctypes.c_uint64(sym),
            ctypes.c_uint64(v_oop),
        )

    def __delitem__(self, key: str) -> None:
        if key not in self:
            raise KeyError(key)
        s  = object.__getattribute__(self, '_session')
        ug = object.__getattribute__(self, '_ug')
        sym = s.new_symbol(str(key))
        s.perform_oop(ug, 'removeKey:ifAbsent:', sym, _gs.OOP_NIL)

    # ------------------------------------------------------------------
    # Read — fetches from GemStone
    # ------------------------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        s  = object.__getattribute__(self, '_session')
        ug = object.__getattribute__(self, '_ug')
        value = ctypes.c_uint64(_gs.OOP_ILLEGAL)
        assoc = ctypes.c_uint64(_gs.OOP_ILLEGAL)
        s._lib.GciSymDictAt(
            ctypes.c_uint64(ug),
            str(key).encode('utf-8'),
            ctypes.byref(value),
            ctypes.byref(assoc),
        )
        v = value.value
        if v == _gs.OOP_ILLEGAL:
            raise KeyError(key)
        return _from_oop(s, v)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        try:
            self[key]
            return True
        except KeyError:
            return False

    def keys(self) -> list[str]:
        """
        Return all symbol-dictionary keys as plain Python strings.

        The batch serializer keeps quoting isolated to one fixed helper while
        avoiding a per-entry GCI call sequence.
        """
        s = object.__getattribute__(self, '_session')
        ug = object.__getattribute__(self, '_ug')
        return _fetch_mapping_string_keys(s, ug)

    def items(self) -> list[tuple[str, Any]]:
        s = object.__getattribute__(self, '_session')
        ug = object.__getattribute__(self, '_ug')
        return _batched_mapping_items(s, ug)

    def values(self) -> list[Any]:
        s = object.__getattribute__(self, '_session')
        ug = object.__getattribute__(self, '_ug')
        return _batched_mapping_values(s, ug)

    def pop(self, key: str, default: Any = ...) -> Any:
        if key in self:
            value = self[key]
            del self[key]
            return value
        if default is ...:
            raise KeyError(key)
        return default

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key in self:
            return self[key]
        self[key] = default
        return default

    def update(self, other: Any = None, /, **kwargs: Any) -> None:
        if other is not None:
            if hasattr(other, 'items'):
                iterable = other.items()
            else:
                iterable = other
            for key, value in iterable:
                self[key] = value
        for key, value in kwargs.items():
            self[key] = value

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    def __len__(self) -> int:
        s = object.__getattribute__(self, '_session')
        ug = object.__getattribute__(self, '_ug')
        return cast(int, s.perform(ug, 'size'))

    def __repr__(self) -> str:
        name = object.__getattribute__(self, '_name')
        ug   = object.__getattribute__(self, '_ug')
        return f'<PersistentRoot {name} oop=0x{ug:X}>'


# ---------------------------------------------------------------------------
# Internal helpers — Python ↔ GemStone OOP conversion
# ---------------------------------------------------------------------------


def _batched_mapping_items(s: _gs.GemStoneSession, oop: int) -> list[tuple[str, Any]]:
    """Fetch mapping items in one eval and materialise values via OOP lookup."""
    return [
        (key, _from_oop(s, value_oop))
        for key, value_oop in _fetch_mapping_string_oop_pairs(s, oop)
    ]


def _batched_mapping_values(s: _gs.GemStoneSession, oop: int) -> list[Any]:
    """Fetch mapping values in one eval and materialise them via OOP lookup."""
    return [
        _from_oop(s, value_oop)
        for _, value_oop in _fetch_mapping_string_oop_pairs(s, oop)
    ]


def _to_oop(s: _gs.GemStoneSession, value: Any) -> int:
    """Convert any supported Python value to a GemStone OOP."""
    if value is None:
        return cast(int, _gs.OOP_NIL)
    if isinstance(value, bool):
        return cast(int, _gs.OOP_TRUE if value else _gs.OOP_FALSE)
    if isinstance(value, int):
        return cast(int, _gs._python_to_smallint(value))
    if isinstance(value, float):
        return s.float_oop(value)
    if isinstance(value, str):
        return s.new_string(value)
    if isinstance(value, (dict, GsDict)):
        return _dict_to_gs(s, value)
    if isinstance(value, (list, tuple)):
        return _list_to_gs(s, value)
    # Any object that already wraps a GemStone OOP (RCCounter, RCHash, GsDict, …)
    if hasattr(value, '_oop'):
        return cast(int, object.__getattribute__(value, '_oop'))
    raise TypeError(f"Cannot persist {type(value).__name__!r} to GemStone")


def _from_oop(s: _gs.GemStoneSession, oop: int) -> Any:
    """Convert a GemStone OOP to the most natural Python value."""
    if oop == _gs.OOP_NIL:
        return None
    if oop == _gs.OOP_TRUE:
        return True
    if oop == _gs.OOP_FALSE:
        return False
    if _gs._is_smallint(oop):
        return _gs._smallint_to_python(oop)
    if s._is_string_oop(oop):
        return s.fetch_string(oop)

    float_value = s.try_oop_to_float(oop)
    if float_value is not None:
        return float_value

    cls_oop = s.fetch_class(oop)

    if cls_oop == _class_oop(s, 'StringKeyValueDictionary'):
        return GsDict(s, oop)

    if cls_oop == _class_oop(s, 'Array'):
        return _array_from_gs(s, oop)

    if cls_oop == _class_oop(s, 'OrderedCollection'):
        from gemstone_py.ordered_collection import OrderedCollection
        return OrderedCollection(s, oop)

    if cls_oop == _class_oop(s, 'RcCounter'):
        from gemstone_py.concurrency import RCCounter
        return RCCounter(s, oop)

    if cls_oop == _class_oop(s, 'RcKeyValueDictionary'):
        from gemstone_py.concurrency import RCHash
        return RCHash(s, oop)

    if cls_oop == _class_oop(s, 'RcQueue'):
        from gemstone_py.concurrency import RCQueue
        return RCQueue(s, oop)

    return GsObject(s, oop)


def _class_oop(s: _gs.GemStoneSession, name: str) -> int | None:
    """Resolve and cache a GemStone class OOP per session."""
    cache = cast(dict[str, int | None] | None, getattr(s, '_persistent_root_class_oops', None))
    if cache is None:
        cache = {}
        setattr(s, '_persistent_root_class_oops', cache)
    if name not in cache:
        try:
            cache[name] = s.resolve(name)
        except Exception:
            cache[name] = None
    return cache[name]


def _array_from_gs(s: _gs.GemStoneSession, oop: int) -> list[Any]:
    """Convert a GemStone Array into a plain Python list."""
    size = s.perform(oop, 'size')
    result: list[Any] = []
    for i in range(1, size + 1):
        idx_oop = _gs._python_to_smallint(i)
        item_oop = s.perform_oop(oop, 'at:', idx_oop)
        result.append(_from_oop(s, item_oop))
    return result


def _dict_to_gs(s: _gs.GemStoneSession, d: Any) -> int:
    """Build a GemStone StringKeyValueDictionary from a Python dict or GsDict."""
    s._ensure_lib()
    lib = s._lib
    assert lib is not None
    oop = s.new_object(s.resolve('StringKeyValueDictionary'))
    items = d.items() if isinstance(d, (dict, GsDict)) else d
    for k, v in items:
        v_oop = _to_oop(s, v)
        lib.GciStrKeyValueDictAtPut(
            ctypes.c_uint64(oop),
            str(k).encode('utf-8'),
            ctypes.c_uint64(v_oop),
        )
    return oop


def _list_to_gs(s: _gs.GemStoneSession, lst: list[Any] | tuple[Any, ...]) -> int:
    """Build a GemStone Array from a Python list or tuple."""
    arr_class = s.resolve('Array')
    size_oop  = _gs._python_to_smallint(len(lst))
    arr_oop   = s.perform_oop(arr_class, 'new:', size_oop)
    for i, v in enumerate(lst, start=1):
        v_oop   = _to_oop(s, v)
        idx_oop = _gs._python_to_smallint(i)
        s.perform_oop(arr_oop, 'at:put:', idx_oop, v_oop)
    return arr_oop
