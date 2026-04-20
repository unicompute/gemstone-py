"""
OrderedCollection — Python proxy for GemStone's OrderedCollection.

This module wraps a live GemStone OrderedCollection OOP via GCI perform
calls.

OrderedCollection is an ordered, resizable sequence.  It differs from a
Python list in that it lives inside GemStone and changes are visible to
other sessions after a commit.  Use it when you need a persistent ordered
sequence and RCQueue's FIFO semantics are too restrictive.

Usage
-----
    import gemstone_py as gemstone
    from gemstone_py.ordered_collection import OrderedCollection
    from gemstone_py.persistent_root import PersistentRoot

    with gemstone.GemStoneSession(...) as s:
        root = PersistentRoot(s)

        col = OrderedCollection(s)
        col.append('first')
        col.append('second')
        col.append('third')
        root['MyList'] = col

        print(col[0])           # 'first'   (0-based, like Python)
        print(col.last)         # 'third'
        print(len(col))         # 3
        col.delete('second')
        print(col.to_list())    # ['first', 'third']

        for item in col:
            print(item)

        col.clear()
        print(len(col))         # 0
"""

PORTING_STATUS = "plain_gemstone_port"
RUNTIME_REQUIREMENT = "Works on plain GemStone images over GCI"

from typing import Any, Iterator

import gemstone_py as _gs
from gemstone_py._smalltalk_batch import object_for_oop_expr
from gemstone_py.persistent_root import _to_oop, _from_oop


def _python_name_to_selector(name: str) -> str:
    """Convert a Python-friendly method name to a Smalltalk selector."""
    if not name or name.startswith('__'):
        raise AttributeError(name)
    if '_' not in name:
        return name
    return name.replace('_', ':')


class OrderedCollection:
    """
    Python proxy for a live GemStone OrderedCollection OOP.

    GemStone's OrderedCollection is 1-indexed; this wrapper presents a
    0-indexed interface consistent with Python lists.

    Every mutation is immediately sent to GemStone via GciPerform.
    Call session.commit() (or exit the `with` block) to persist changes.

    """

    def __init__(self, session: _gs.GemStoneSession, oop: int = 0):
        if not oop:
            oop = session.eval_oop('OrderedCollection new')
        object.__setattr__(self, '_session', session)
        object.__setattr__(self, '_oop',     oop)

    def _s(self) -> _gs.GemStoneSession:
        return object.__getattribute__(self, '_session')

    def _o(self) -> int:
        return object.__getattribute__(self, '_oop')

    def _call(self, selector: str, *args) -> Any:
        raw = [_to_oop(self._s(), a) for a in args]
        return self._s().perform(self._o(), selector, *raw)

    def _call_oop(self, selector: str, *args) -> int:
        raw = [_to_oop(self._s(), a) for a in args]
        return self._s().perform_oop(self._o(), selector, *raw)

    def send(self, selector: str, *args) -> Any:
        return _from_oop(self._s(), self._call_oop(selector, *args))

    def send_oop(self, selector: str, *args) -> int:
        return self._call_oop(selector, *args)

    def __getattr__(self, name: str):
        selector = _python_name_to_selector(name)

        def dispatcher(*args: Any) -> Any:
            return self.send(selector, *args)

        dispatcher.__name__ = name
        dispatcher.__doc__ = f"Dispatches to Smalltalk selector `{selector}`."
        return dispatcher

    @property
    def oop(self) -> int:
        return self._o()

    # ------------------------------------------------------------------
    # Append / delete
    # ------------------------------------------------------------------

    def append(self, value: Any) -> 'OrderedCollection':
        """Add value to the end of the collection (GS: add:)."""
        self._call('add:', value)
        return self

    def __lshift__(self, value: Any) -> 'OrderedCollection':
        """col << value  — same as append."""
        return self.append(value)

    def pop(self) -> Any:
        """
        Remove and return the last element (GS: removeLast).

            last = col.pop()
        """
        v_oop = self._call_oop('removeLast')
        return _from_oop(self._s(), v_oop)

    def shift(self) -> Any:
        """
        Remove and return the first element (GS: removeFirst).

            first = col.shift()
        """
        v_oop = self._call_oop('removeFirst')
        return _from_oop(self._s(), v_oop)

    def delete(self, value: Any) -> Any:
        """
        Remove the first occurrence of value (GS: remove:).
        Raises ValueError if not found.
        """
        result = self._call('remove:ifAbsent:', value, None)
        if result is None and value not in self:
            raise ValueError(f"{value!r} not in OrderedCollection")
        return value

    def discard(self, value: Any) -> None:
        """Remove value if present, silently ignore if absent."""
        self._call('remove:ifAbsent:', value, None)

    def clear(self) -> 'OrderedCollection':
        """
        Remove all elements.

        Uses GemStone's removeAllSuchThat: rather than size: 0.
        OrderedCollection>>size: is not a standard resize-to-zero message
        and raises on some GemStone versions; removeAllSuchThat: [:e | true]
        is the documented way to clear an OrderedCollection.

        """
        s = self._s()
        oop = self._o()
        s.eval(
            f"({object_for_oop_expr(oop)}) removeAllSuchThat: [:e | true]."
        )
        return self

    # ------------------------------------------------------------------
    # Access — 0-based, like Python
    # ------------------------------------------------------------------

    def __getitem__(self, index: int) -> Any:
        """0-based access: col[0] → first element (GS: at: index+1)."""
        size = len(self)
        if index < 0:
            index += size
        if not (0 <= index < size):
            raise IndexError(f"index {index} out of range")
        v_oop = self._call_oop('at:', index + 1)
        return _from_oop(self._s(), v_oop)

    @property
    def last(self) -> Any:
        """Return the last element without removing it (GS: last)."""
        v_oop = self._call_oop('last')
        return _from_oop(self._s(), v_oop)

    @property
    def first(self) -> Any:
        """Return the first element without removing it (GS: first)."""
        v_oop = self._call_oop('first')
        return _from_oop(self._s(), v_oop)

    # ------------------------------------------------------------------
    # Size / membership
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return self._call('size')

    def __contains__(self, value: Any) -> bool:
        return bool(self._call('includes:', value))

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def __iter__(self) -> Iterator:
        """Iterate by fetching elements one at a time via at:."""
        size = len(self)
        for i in range(1, size + 1):
            v_oop = self._call_oop('at:', i)
            yield _from_oop(self._s(), v_oop)

    def reverse_iter(self) -> Iterator:
        """
        Iterate from last to first.

        Builds a GemStone array snapshot, then walks it from the back via
        direct GCI calls. This avoids the previous `asOop printString`
        eval-string path while still keeping iteration stable against a
        single collection snapshot.

        """
        s = self._s()
        array_oop = self._call_oop('asArray')
        size = s.perform(array_oop, 'size')
        for i in range(size, 0, -1):
            v_oop = s.perform_oop(array_oop, 'at:', _gs._python_to_smallint(i))
            yield _from_oop(s, v_oop)

    def reverse_iter_with_index(self) -> Iterator:
        """
        Iterate from last to first, yielding (item, 0-based-index) pairs.

        Uses `reverse_iter()` for the collection walk.

            for item, i in col.reverse_iter_with_index():
                print(i, item)
        """
        items = list(self.reverse_iter())
        size  = len(self)
        for i, item in enumerate(items):
            yield item, size - 1 - i  # 0-based index from the front

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def to_list(self) -> list:
        """Return a plain Python list of all elements."""
        return list(self)

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        oop = self._o()
        return f"<OrderedCollection size={len(self)} oop=0x{oop:X}>"
