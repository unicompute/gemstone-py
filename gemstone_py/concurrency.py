"""
concurrency.py — Multi-session GemStone primitives for Python.

All classes wrap live GemStone objects via GCI perform calls. Every mutation
is immediately visible to GemStone; call session.commit() to make it durable.

────────────────────────────────────────────────────────────────
 1. RCCounter  — reduced-conflict counter (GemStone RcCounter)
 2. RCHash     — reduced-conflict key/value store (RcKeyValueDictionary)
 3. RCQueue    — reduced-conflict FIFO queue (RcQueue)
 4. CommitConflictError — raised when GciCommit returns FALSE
 5. nested_transaction() — context manager for nested transactions
 6. gs_now() / gs_datetime() / datetime_to_gs() — DateAndTime ↔ datetime
 7. lock() / read_lock() / unlock() — object locking across sessions
 8. shared_counter_*() — persistent shared counters (System sharedCounter:…)
 9. needs_commit / commit_and_release_locks / transaction_level / session_id
10. Repository — full_backup_to / restore_from_backup / list_instances
11. list_instances() — convenience function (single class, flat proxy/OOP list)
────────────────────────────────────────────────────────────────

Usage
-----
    import gemstone_py as gemstone
    from gemstone_py.concurrency import (
        RCCounter, RCHash, RCQueue,
        nested_transaction,
        gs_now, gs_datetime, datetime_to_gs,
        lock, read_lock, unlock,
        shared_counter_get, shared_counter_increment, shared_counter_set,
        list_instances,
    )
    from gemstone_py.persistent_root import PersistentRoot

    with gemstone.GemStoneSession(...) as s:
        root = PersistentRoot(s)

        # RCCounter — safe for concurrent increment from many sessions
        root['hits'] = RCCounter(s)
        root['hits'].increment()
        print(root['hits'].value)      # 1

        # RCHash — concurrent writes to different keys never conflict
        root['cache'] = RCHash(s)
        root['cache']['session:1'] = 'data'

        # RCQueue — many producers, one consumer
        root['jobs'] = RCQueue(s)
        root['jobs'].push('job-1')
        job = root['jobs'].pop()

        # Nested transaction
        with nested_transaction(s):
            root['draft'] = {'status': 'pending'}
            # commits the nested level on clean exit; outer txn still open

        # DateAndTime
        ts = gs_now(s)                          # GemStone timestamp as datetime
        gs_ts = datetime_to_gs(s, datetime.now())

        # Object locking
        with lock(s, obj_oop):
            ...                                 # exclusive write lock, auto-released

        # Shared counters (1..128, survive without a transaction)
        shared_counter_set(s, 1, 0)
        shared_counter_increment(s, 1)
        print(shared_counter_get(s, 1))         # 1

        # List all instances of a GemStone class
        instances = list_instances(s, 'RcCounter', wrap=True)
"""

import ctypes
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator, cast

import gemstone_py as _gs

from ._smalltalk_batch import (
    fetch_collection_oops,
    fetch_mapping_oop_pairs,
    fetch_mapping_string_oop_lists,
    json_string_encoder_source,
    object_for_oop_expr,
)

PORTING_STATUS = "plain_gemstone_port"
RUNTIME_REQUIREMENT = "Works on plain GemStone images over GCI"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _python_name_to_selector(name: str) -> str:
    """Convert a Python-friendly method name to a Smalltalk selector."""
    if not name or name.startswith('__'):
        raise AttributeError(name)
    if '_' not in name:
        return name
    return name.replace('_', ':')

def _oop(s: _gs.GemStoneSession, v: Any) -> int:
    """Convert a Python value to a GemStone OOP for use as a perform argument."""
    if isinstance(v, bool):
        return cast(int, _gs.OOP_TRUE if v else _gs.OOP_FALSE)
    if v is None:
        return cast(int, _gs.OOP_NIL)
    if isinstance(v, int):
        return cast(int, _gs._python_to_smallint(v))
    if isinstance(v, str):
        return s.new_string(v)
    if isinstance(v, _GsProxy):
        return cast(int, object.__getattribute__(v, '_oop'))
    raise TypeError(f"Cannot pass {type(v).__name__!r} as a GemStone argument")


def _py(s: _gs.GemStoneSession, oop: int) -> Any:
    """Marshal a GemStone OOP to a Python value."""
    return cast(Any, s._marshal(oop))


def _wrap_oop(s: _gs.GemStoneSession, oop: int) -> Any:
    """Convert a GemStone OOP to the richer proxy/value model used by persistent_root."""
    from gemstone_py.persistent_root import _from_oop

    return _from_oop(s, oop)


def _coerce_oop(value: Any) -> int:
    """Return a raw GemStone OOP from an int or a proxy exposing `.oop`."""
    if isinstance(value, int):
        return value
    oop = getattr(value, 'oop', None)
    if oop is not None:
        return cast(int, oop)
    try:
        return cast(int, object.__getattribute__(value, '_oop'))
    except AttributeError as exc:
        raise TypeError(
            f"Expected a GemStone OOP or proxy object, got {type(value).__name__!r}"
        ) from exc


class _GsProxy:
    """Base for Python proxies that wrap a live GemStone OOP."""

    def __init__(self, session: _gs.GemStoneSession, oop: int):
        object.__setattr__(self, '_session', session)
        object.__setattr__(self, '_oop',     oop)

    def _s(self) -> _gs.GemStoneSession:
        return cast(_gs.GemStoneSession, object.__getattribute__(self, '_session'))

    def _o(self) -> int:
        return cast(int, object.__getattribute__(self, '_oop'))

    def _call(self, selector: str, *args: Any) -> Any:
        raw = [_oop(self._s(), a) for a in args]
        return self._s().perform(self._o(), selector, *raw)

    def _call_oop(self, selector: str, *args: Any) -> int:
        raw = [_oop(self._s(), a) for a in args]
        return self._s().perform_oop(self._o(), selector, *raw)

    def send(self, selector: str, *args: Any) -> Any:
        return _py(self._s(), self._call_oop(selector, *args))

    def send_oop(self, selector: str, *args: Any) -> int:
        return self._call_oop(selector, *args)

    def __getattr__(self, name: str) -> Callable[..., Any]:
        selector = _python_name_to_selector(name)

        def dispatcher(*args: Any) -> Any:
            return self.send(selector, *args)

        dispatcher.__name__ = name
        dispatcher.__doc__ = f"Dispatches to Smalltalk selector `{selector}`."
        return dispatcher

    @property
    def oop(self) -> int:
        return self._o()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} oop=0x{self._o():X}>"


# ---------------------------------------------------------------------------
# 1. RCCounter — GemStone RcCounter
# ---------------------------------------------------------------------------

class RCCounter(_GsProxy):
    """
    Reduced-conflict counter.  Multiple sessions can increment the same
    instance without conflicting with each other at commit time.

        c = RCCounter(session)
        c.increment()
        c.increment_by(5)
        print(c.value)          # 6
        c.decrement()
        c.decrement_by(2)
    """

    def __init__(self, session: _gs.GemStoneSession, oop: int = 0):
        if not oop:
            oop = session.eval_oop('RcCounter new')
        super().__init__(session, oop)

    @property
    def value(self) -> int:
        return cast(int, self._call('value'))

    def increment(self) -> 'RCCounter':
        self._call('increment')
        return self

    def increment_by(self, n: int) -> 'RCCounter':
        self._call('incrementBy:', n)
        return self

    def decrement(self) -> 'RCCounter':
        self._call('decrement')
        return self

    def decrement_by(
        self,
        n: int,
        guard: int | None = None,
        callback: Callable[[], Any] | None = None,
    ) -> 'RCCounter':
        """
        Decrement by `n`.

        If `guard` and `callback` are supplied, this is the guarded form:
        GemStone's decrementBy:ifLessThan:thenExecute: atomically decrements
        by `n`; if the result is less than `guard` the Smalltalk block fires.
        Since GCI cannot call back into Python from a Smalltalk block, we use
        a sentinel approach: the Smalltalk block stores a flag in a temp
        variable and we return that flag to Python to decide whether to invoke
        the Python callback.

            c.decrement_by(5)                       # plain decrement
            c.decrement_by(5, 0) { puts 'fired!' }  # guarded; block called if result < 0
        """
        if guard is not None and callback is not None:
            s   = self._s()
            oop = self._o()
            # The Smalltalk block sets a flag variable to true when it executes.
            # We return that flag so Python knows whether to call the callback.
            fired = s.eval(
                f"| counter fired |\n"
                f"fired := false.\n"
                f"counter := {object_for_oop_expr(oop)}.\n"
                f"counter\n"
                f"  decrementBy: {n}\n"
                f"  ifLessThan: {guard}\n"
                f"  thenExecute: [fired := true].\n"
                f"fired"
            )
            if fired:
                callback()
        else:
            self._call('decrementBy:', n)
        return self

    def decrement_if_negative(self, n: int) -> 'RCCounter':
        """
        Decrement by `n` only if the result would remain >= 0.

        GemStone returns self unchanged if decrement would go negative.
        """
        self._call('decrementIfNegative:', n)
        return self

    def __int__(self) -> int:
        return self.value

    def __repr__(self) -> str:
        return f"<RCCounter value={self.value}>"


# ---------------------------------------------------------------------------
# 2. RCHash — GemStone RcKeyValueDictionary
# ---------------------------------------------------------------------------

class RCHash(_GsProxy):
    """
    Reduced-conflict key/value store.  Concurrent writes to different keys
    from different sessions rarely conflict at commit time.

    Keys and values must be str, int, bool, or None.

        h = RCHash(session)
        h['session:1'] = 'active'
        print(h['session:1'])   # 'active'
        del h['session:1']
        print(h.size)           # 0
    """

    def __init__(self, session: _gs.GemStoneSession, oop: int = 0):
        if not oop:
            oop = session.eval_oop('RcKeyValueDictionary new')
        super().__init__(session, oop)

    def __setitem__(self, key: Any, value: Any) -> None:
        self._call('at:put:', key, value)

    def __getitem__(self, key: Any) -> Any:
        result = self._call('at:otherwise:', key, None)
        if result is None and not self.__contains__(key):
            raise KeyError(key)
        return result

    def get(self, key: Any, default: Any = None) -> Any:
        return self._call('at:otherwise:', key, default)

    def __delitem__(self, key: Any) -> None:
        self._call('removeKey:ifAbsent:', key, None)

    def __contains__(self, key: Any) -> bool:
        return bool(self._call('includesKey:', key))

    @property
    def size(self) -> int:
        return cast(int, self._call('size'))

    def __len__(self) -> int:
        return self.size

    def _fetch_all(self) -> list[tuple[Any, Any]]:
        """
        Fetch all key/value pairs.

        Fast-paths the common scalar-key/scalar-value case through one
        serialized Smalltalk eval. Falls back to batched OOP fetches for
        non-scalar objects so semantics stay intact without per-entry RPCs.
        """
        fast_pairs = self._fetch_scalar_pairs_fast()
        if fast_pairs is not None:
            return fast_pairs

        return self._fetch_oop_pairs_fallback()

    def _fetch_scalar_pairs_fast(self) -> list[tuple[Any, Any]] | None:
        """
        Return all pairs in one eval when every key/value is JSON-scalar-safe.

        RcKeyValueDictionary is commonly used for str/int/bool/None values.
        If any key or value falls outside that subset we return None and let
        the slower association traversal preserve the full object semantics.
        """
        s = self._s()
        oop = self._o()
        raw = s.eval(
            f"| mapping encodeString encodeScalar stream supported |\n"
            f"mapping := {object_for_oop_expr(oop)}.\n"
            f"{json_string_encoder_source('encodeString')}"
            "encodeScalar := [:value |\n"
            "  value isNil ifTrue: [ 'null' ] ifFalse: [\n"
            "    value == true ifTrue: [ 'true' ] ifFalse: [\n"
            "      value == false ifTrue: [ 'false' ] ifFalse: [\n"
            "        (value isInteger) ifTrue: [ value printString ] ifFalse: [\n"
            "          ((value isKindOf: String) or: [ value class == Symbol ])\n"
            "            ifTrue: [ '\"', (encodeString value: value), '\"' ]\n"
            "            ifFalse: [ nil ]\n"
            "        ]\n"
            "      ]\n"
            "    ]\n"
            "  ]\n"
            "].\n"
            "stream := ''.\n"
            "supported := true.\n"
            "mapping associationsDo: [:assoc |\n"
            "  | keyJson valueJson |\n"
            "  supported ifTrue: [\n"
            "    keyJson := encodeScalar value: assoc key.\n"
            "    valueJson := encodeScalar value: assoc value.\n"
            "    (keyJson isNil or: [ valueJson isNil ])\n"
            "      ifTrue: [ supported := false ]\n"
            "      ifFalse: [\n"
            "        stream := stream, '[', keyJson, ',', valueJson, ']', String lf asString\n"
            "      ]\n"
            "  ]\n"
            "].\n"
            "supported ifTrue: [ stream ] ifFalse: [ nil ]"
        )
        if raw is None:
            return None
        return [
            tuple(json.loads(line))
            for line in raw.splitlines()
            if line.strip()
        ]

    def _fetch_oop_pairs_fallback(self) -> list[tuple[Any, Any]]:
        """Fetch all pairs in one eval as raw OOPs, then marshal in Python."""
        s = self._s()
        oop = self._o()
        return [
            (_py(s, key_oop), _py(s, value_oop))
            for key_oop, value_oop in fetch_mapping_oop_pairs(s, oop)
        ]

    def keys(self) -> list[Any]:
        """Return all keys in a single round-trip via keysAndValuesDo:."""
        return [k for k, _ in self._fetch_all()]

    def values(self) -> list[Any]:
        """Return all values in a single round-trip via keysAndValuesDo:."""
        return [v for _, v in self._fetch_all()]

    def items(self) -> list[tuple[Any, Any]]:
        """Return all (key, value) pairs in a single round-trip."""
        return self._fetch_all()

    def __iter__(self) -> Iterator[Any]:
        return iter(self.keys())

    @property
    def empty(self) -> bool:
        """Return True if the hash contains no entries (GS: isEmpty)."""
        return bool(self._call('isEmpty'))

    def rebuild_table(self, size: int) -> None:
        """
        Rebuild the internal hash table with a new target capacity.

        Use when you have inserted many items and want to improve lookup
        performance by reducing hash collisions.

            h.rebuild_table(1024)
        """
        self._call('rebuildTable:', size)

    def __repr__(self) -> str:
        return f"<RCHash size={self.size}>"


# ---------------------------------------------------------------------------
# 3. RCQueue — GemStone RcQueue
# ---------------------------------------------------------------------------

class RCQueue(_GsProxy):
    """
    Reduced-conflict FIFO queue.  Many producers can push concurrently
    without conflicting.  Single-consumer pop is also conflict-free.

        q = RCQueue(session)
        q.push('job-1')
        q.push('job-2')
        print(q.first)          # 'job-1'
        print(q.pop())          # 'job-1'
        print(q.size)           # 1
    """

    def __init__(self, session: _gs.GemStoneSession, oop: int = 0):
        if not oop:
            oop = session.eval_oop('RcQueue new')
        super().__init__(session, oop)

    def push(self, value: Any) -> 'RCQueue':
        """Add an item to the back of the queue."""
        self._call('add:', value)
        return self

    # aliases
    def add(self, value: Any) -> 'RCQueue': return self.push(value)
    def enq(self, value: Any) -> 'RCQueue': return self.push(value)
    def __lshift__(self, value: Any) -> 'RCQueue': return self.push(value)

    def pop(self) -> Any:
        """Remove and return the front item."""
        return self._call('remove')

    def shift(self) -> Any: return self.pop()
    def deq(self) -> Any: return self.pop()

    @property
    def first(self) -> Any:
        """Peek at the front item without removing it."""
        return self._call('peek')

    @property
    def size(self) -> int:
        return cast(int, self._call('size'))

    def __len__(self) -> int:
        return self.size

    @property
    def empty(self) -> bool:
        return bool(self._call('isEmpty'))

    def clear(self) -> 'RCQueue':
        """
        Remove all items from the queue.

            q.clear()
            assert q.size == 0
        """
        self._call('removeAll')
        return self

    def __iter__(self) -> Iterator[Any]:
        """
        Iterate over all items without removing them.

        Fetches size then reads each element by index (1-based in GemStone).
        """
        size = self._call('size')
        for i in range(1, size + 1):
            v_oop = self._s().perform_oop(self._o(), 'at:', _gs._python_to_smallint(i))
            yield _py(self._s(), v_oop)

    def __repr__(self) -> str:
        return f"<RCQueue size={self.size}>"


# ---------------------------------------------------------------------------
# 4. CommitConflictError + patched commit
# ---------------------------------------------------------------------------

class CommitConflictError(Exception):
    """
    Raised when GciCommit returns FALSE due to a concurrency conflict.

    Attributes
    ----------
    ww_conflicts : list[int]
        OOPs of objects with write/write conflicts.
    wd_conflicts : list[int]
        OOPs of objects with write/dependency conflicts.
    report : str
        Human-readable conflict report from System conflictReportString.
    """
    def __init__(self, report: str, ww: list[int], wd: list[int]):
        super().__init__(report)
        self.report       = report
        self.ww_conflicts = ww
        self.wd_conflicts = wd


def commit(session: _gs.GemStoneSession) -> None:
    """
    Commit the current transaction, raising CommitConflictError on conflict.

    Replaces the bare session.commit() for code that needs conflict detail.

        try:
            commit(s)
        except CommitConflictError as e:
            print(e.report)
            s.abort()
    """
    session._require_login()
    lib = session._lib
    assert lib is not None
    err = _gs.GciErrSType()
    ok = lib.GciCommit(ctypes.byref(err))
    if ok:
        return
    # GciCommit returned FALSE — either conflict or hard error
    if err.number != 0:
        raise _gs.GemStoneError.from_err_struct(err)
    # Conflict — collect details before aborting
    report = session.eval('System conflictReportString') or ''
    ww = _collect_conflict_oops(session, 'currentTransactionWWConflicts')
    wd = _collect_conflict_oops(session, 'currentTransactionWDConflicts')
    raise CommitConflictError(report or 'Commit conflict', ww, wd)


def _collect_conflict_oops(session: _gs.GemStoneSession, selector: str) -> list[int]:
    try:
        conflicts_oop = session.eval_oop(f"System {selector}")
        return fetch_collection_oops(session, conflicts_oop)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 5. Nested transactions
# ---------------------------------------------------------------------------

@contextmanager
def nested_transaction(session: _gs.GemStoneSession) -> Iterator[_gs.GemStoneSession]:
    """
    Context manager for a GemStone nested transaction (up to 16 levels).

    On clean exit: commits the nested level (System commitTransaction).
    On exception: aborts the nested level (System abortTransaction).

        with nested_transaction(s):
            root['draft'] = {'status': 'pending'}
        # nested level committed; outer transaction still open
    """
    session.eval('System beginNestedTransaction')
    try:
        yield session
    except Exception:
        session.eval('System abortTransaction')
        raise
    else:
        ok = session.eval('System commitTransaction')
        if not ok:
            report = session.eval('System conflictReportString') or 'Nested commit conflict'
            raise CommitConflictError(report, [], [])


# ---------------------------------------------------------------------------
# 6. DateAndTime ↔ Python datetime
# ---------------------------------------------------------------------------

# GemStone epoch: 1 Jan 1901 00:00:00 UTC
# POSIX epoch:    1 Jan 1970 00:00:00 UTC
# Difference in seconds: 2208988800
_POSIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def gs_now(session: _gs.GemStoneSession) -> datetime:
    """Return the current GemStone server time as a Python datetime (UTC)."""
    return gs_datetime(session, session.eval_oop('DateAndTime now'))


def gs_datetime(session: _gs.GemStoneSession, dt_oop: int) -> datetime:
    """
    Convert a GemStone DateAndTime OOP to a Python datetime (UTC).

    """
    # asPosixSeconds returns a GemStone Float — fetch its printString via perform
    posix_oop = session.perform_oop(dt_oop, 'asPosixSeconds')
    ps_oop    = session.perform_oop(posix_oop, 'printString')
    posix_str = session.fetch_string(ps_oop)
    posix = float(posix_str)
    return _POSIX_EPOCH + timedelta(seconds=posix)


def datetime_to_gs(session: _gs.GemStoneSession, dt: datetime) -> int:
    """
    Convert a Python datetime to a GemStone DateAndTime OOP.

    Returns the OOP of the new DateAndTime object.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    posix = dt.timestamp()
    return session.eval_oop(f'DateAndTime posixSeconds: {posix} offsetSeconds: 0')


# ---------------------------------------------------------------------------
# 7. Object locking
# ---------------------------------------------------------------------------

@contextmanager
def lock(session: _gs.GemStoneSession, obj: Any) -> Iterator[None]:
    """
    Acquire an exclusive write lock on a GemStone object, release on exit.

    `obj` may be either a raw OOP integer or any gemstone-py proxy object
    that exposes `.oop`.

        with lock(s, my_object):
            ...   # other sessions cannot write-lock this object
    """
    obj_oop = _coerce_oop(obj)
    session.eval(f'System writeLock: ({object_for_oop_expr(obj_oop)})')
    try:
        yield
    finally:
        session.eval(f'System removeLock: ({object_for_oop_expr(obj_oop)})')


@contextmanager
def read_lock(session: _gs.GemStoneSession, obj: Any) -> Iterator[None]:
    """
    Acquire a shared read lock on a GemStone object, release on exit.

    `obj` may be either a raw OOP integer or any gemstone-py proxy object
    that exposes `.oop`.

        with read_lock(s, my_object):
            ...   # other sessions can also read-lock but not write-lock
    """
    obj_oop = _coerce_oop(obj)
    session.eval(f'System readLock: ({object_for_oop_expr(obj_oop)})')
    try:
        yield
    finally:
        session.eval(f'System removeLock: ({object_for_oop_expr(obj_oop)})')


def unlock(session: _gs.GemStoneSession, obj: Any) -> None:
    """Release any lock held on `obj` by this session."""
    obj_oop = _coerce_oop(obj)
    session.eval(f'System removeLock: ({object_for_oop_expr(obj_oop)})')


# ---------------------------------------------------------------------------
# 8. Persistent shared counters
# ---------------------------------------------------------------------------

def shared_counter_get(session: _gs.GemStoneSession, index: int) -> int:
    """
    Read shared counter number `index` (1-based, 1..numSharedCounters).

    Shared counters persist without a transaction — visible to all sessions
    immediately.  Used for metrics, rate limiting, coordination.

        v = shared_counter_get(s, 1)
    """
    return cast(int, session.eval(f'System sharedCounter: {index}'))


def shared_counter_set(session: _gs.GemStoneSession, index: int, value: int) -> None:
    """Set shared counter `index` to `value`."""
    session.eval(f'System sharedCounter: {index} setValue: {value}')


def shared_counter_increment(session: _gs.GemStoneSession, index: int, by: int = 1) -> None:
    """Increment shared counter `index` by `by` (default 1)."""
    session.eval(f'System sharedCounter: {index} incrementBy: {by}')


def shared_counter_decrement(session: _gs.GemStoneSession, index: int, by: int = 1) -> None:
    """Decrement shared counter `index` by `by` (default 1)."""
    session.eval(f'System sharedCounter: {index} decrementBy: {by}')


def shared_counter_count(session: _gs.GemStoneSession) -> int:
    """Return the total number of shared counters available."""
    return cast(int, session.eval('System numSharedCounters'))


# ---------------------------------------------------------------------------
# 9. Session utilities
# ---------------------------------------------------------------------------

def needs_commit(session: _gs.GemStoneSession) -> bool:
    """
    Return True if the current transaction has uncommitted changes.

    Checks whether any objects have been modified since the last commit or
    abort.

        if needs_commit(s):
            commit(s)
    """
    return bool(session.eval('System needsCommit'))


def commit_and_release_locks(session: _gs.GemStoneSession) -> bool:
    """
    Commit the transaction and release all locks held by this session.

    Same as commit() but also clears the session's lock set on success.
    Returns True on success; raises CommitConflictError on conflict.

        commit_and_release_locks(s)
    """
    commit(session)                        # raises CommitConflictError on conflict
    session.eval('System releaseAllLocks')
    return True


def transaction_level(session: _gs.GemStoneSession) -> int:
    """
    Return the current transaction nesting level.

    0 = outside any transaction, 1 = top-level, >1 = inside nested_transaction.

        with nested_transaction(s):
            assert transaction_level(s) == 2
    """
    return cast(int, session.eval('System transactionLevel'))


def session_id(session: _gs.GemStoneSession) -> int:
    """
    Return the GemStone session ID for this connection.

    Each logged-in GCI session gets a unique integer ID from the stone.
    Useful for logging and multi-session coordination.

        print(f"Connected as session {session_id(s)}")
    """
    return cast(int, session.eval('System session'))


def session_count(session: _gs.GemStoneSession) -> int:
    """
    Return the number of sessions currently logged in to the stone.

        print(f"{session_count(s)} sessions active")
    """
    return cast(int, session.eval('System currentSessionCount'))


# ---------------------------------------------------------------------------
# 10. Repository — backup/restore and instance enumeration
# ---------------------------------------------------------------------------

class Repository:
    """
    Wrapper around GemStone's SystemRepository object.

    Exposes backup, restore, and instance-listing operations.

    Usage
    -----
        import gemstone_py as gemstone
        from gemstone_py.concurrency import Repository

        with gemstone.GemStoneSession(...) as s:
            repo = Repository(s)
            repo.full_backup_to('/tmp/backup.gz')      # requires FileControl privilege
            instances = repo.list_instances(['RcCounter'], wrap=True)
            print(instances['RcCounter'])               # [<RCCounter ...>, ...]
    """

    def __init__(self, session: _gs.GemStoneSession):
        object.__setattr__(self, '_session', session)
        # SystemRepository is the live repository object in GemStone
        object.__setattr__(self, '_oop', session.resolve('SystemRepository'))

    def _s(self) -> _gs.GemStoneSession:
        return cast(_gs.GemStoneSession, object.__getattribute__(self, '_session'))

    def _o(self) -> int:
        return cast(int, object.__getattribute__(self, '_oop'))

    def full_backup_to(self, path: str) -> bool:
        """
        Write a compressed full backup of the repository to `path`.

        GemStone selector: fullBackupCompressedTo:

        Requires the FileControl privilege (run as DataCurator or SystemUser).
        Appends '.gz' if path does not already end with it.
        Aborts the current transaction before running — uncommitted changes
        will be lost.

        Returns True on success.
        """
        s   = self._s()
        oop = self._o()
        p   = path if path.endswith('.gz') else path + '.gz'
        path_oop = s.new_string(p)
        result   = s.perform_oop(oop, 'fullBackupCompressedTo:', path_oop)
        false_oop = int(_gs.OOP_FALSE)
        nil_oop = int(_gs.OOP_NIL)
        return result not in {false_oop, nil_oop}

    def restore_from_backup(self, path: str) -> None:
        """
        Restore the repository from a backup file.

        GemStone selector: restoreFromBackup:

        Disables logins, restores all objects, then logs the session out.
        Requires the FileControl privilege.

        WARNING: this is destructive.  The current repository content is
        replaced with the backup.  The session is automatically logged out
        when the restore completes.
        """
        s        = self._s()
        oop      = self._o()
        path_oop = s.new_string(path)
        s.perform_oop(oop, 'restoreFromBackup:', path_oop)

    def list_instances(self, class_names: list[str], wrap: bool = False) -> dict[str, list[Any]]:
        """
        Return a mapping of class_name → list of persistent instances of each
        named GemStone class.

        Scans the entire repository — may be slow for large stores.  As
        documented for SystemRepository, GemStone scans the repository once
        per 2000 unique classes (or fraction thereof). This wrapper sends at
        most 2000 classes per call to avoid triggering multiple full scans in
        a single Smalltalk eval.

            instances = repo.list_instances(['RcCounter', 'RcQueue'], wrap=True)
            print(instances['RcCounter'])   # [<RCCounter ...>, ...]

        Parameters
        ----------
        class_names : list[str]
            GemStone class names to search for.
        wrap : bool, default False
            When True, convert each OOP into the same natural Python value or
            sendable proxy used by `PersistentRoot`. When False, return raw
            OOP integers for compatibility.
        """
        _BATCH = 2000
        s      = self._s()
        result: dict[str, list[Any]] = {name: [] for name in class_names}

        # De-duplicate while preserving order, then chunk into ≤2000-class batches.
        unique = list(dict.fromkeys(class_names))
        for batch_start in range(0, len(unique), _BATCH):
            batch = unique[batch_start: batch_start + _BATCH]

            adds = ''.join(f" add: (Smalltalk at: #{n});" for n in batch)
            batch_map_oop = s.eval_oop(
                f"| clsArray arr byName |\n"
                f"clsArray := (OrderedCollection new{adds} yourself) asArray.\n"
                f"arr := SystemRepository listInstances: clsArray.\n"
                f"byName := Dictionary new.\n"
                f"1 to: clsArray size do: [:i |\n"
                f"  byName at: (clsArray at: i) name put: (arr at: i)\n"
                f"].\n"
                f"byName"
            )
            for cls_name, oops in fetch_mapping_string_oop_lists(s, batch_map_oop):
                if cls_name not in result:
                    continue
                if wrap:
                    result[cls_name].extend(_wrap_oop(s, oop) for oop in oops)
                else:
                    result[cls_name].extend(oops)
        return result

    def __repr__(self) -> str:
        oop = self._o()
        return f"<Repository oop=0x{oop:X}>"


# ---------------------------------------------------------------------------
# 11. listInstances — convenience function (kept for backward compatibility)
# ---------------------------------------------------------------------------

def list_instances(session: _gs.GemStoneSession, class_name: str, wrap: bool = False) -> list[Any]:
    """
    Return persistent objects of the named GemStone class.

    Scans the entire repository — may be slow for large collections.
    Use indexes (gsquery.GSCollection) for repeated queries.

        counters = list_instances(s, 'RcCounter', wrap=True)
        for counter in counters:
            print(counter.value)

    Parameters
    ----------
    wrap : bool, default False
        When True, convert each OOP into the same natural Python value or
        sendable proxy used by `PersistentRoot`. When False, return raw
        OOP integers for compatibility.
    """
    result_collection_oop = session.eval_oop(
        f"| cls result |"
        f"cls := Smalltalk at: #{class_name}."
        f"result := SystemRepository listInstances: (Array with: cls)."
        f"result first"
    )
    oops = fetch_collection_oops(session, result_collection_oop)
    if not oops:
        return []
    if wrap:
        return [_wrap_oop(session, oop) for oop in oops]
    return cast(list[Any], oops)
