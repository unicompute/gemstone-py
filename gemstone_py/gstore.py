"""
GStore — a GemStone-backed key/value store.

This module provides a small persistent store interface backed directly by
GemStone UserGlobals via GCI calls — no eval-string construction and no
Ruby VM/runtime dependency.

Each GStore "file" is a StringKeyValueDictionary stored under:
    UserGlobals[#GStoreRoot][filename][key] = JSON-serialised value

Usage:
    from gemstone_py.gstore import GStore

    db = GStore('myapp.db')

    with db.transaction() as t:
        t['user:1'] = {'name': 'Tariq', 'score': 42}
        t['counter'] = t.get('counter', 0) + 1

    with db.transaction(read_only=True) as t:
        print(t['user:1'])
        print(t.get('missing', 'default'))

    GStore.rm('myapp.db')      # delete the named store
    GStore.rm_all()            # wipe every GStore from the repository

Values must be JSON-serialisable (str, int, float, bool, None, list, dict).
For arbitrary Python objects, serialise manually before storing.

Commit conflicts are retried automatically (up to 10 attempts), so
concurrent writers don't produce spurious errors.

To abort a transaction without committing, raise GStoreAbortTransaction:

    with db.transaction() as t:
        t['key'] = 'value'
        if some_condition:
            raise GStoreAbortTransaction   # nothing committed
"""

PORTING_STATUS = "plain_gemstone_port"
RUNTIME_REQUIREMENT = "Works on plain GemStone images over GCI"

import ctypes
import json
from contextlib import contextmanager
from typing import Any, Iterator

import gemstone_py as gemstone
from gemstone_py.persistent_root import PersistentRoot, GsDict, GsObject, _from_oop
from gemstone_py.concurrency import commit as _concurrency_commit, CommitConflictError

# Root symbol in UserGlobals that holds all GStore "files"
_GSTORE_ROOT = 'GStoreRoot'

# Maximum commit attempts before giving up.
_MAX_RETRIES = 10


def _session(
    config: gemstone.GemStoneConfig | None = None,
    *,
    transaction_policy: gemstone.TransactionPolicy | str = gemstone.TransactionPolicy.MANUAL,
) -> gemstone.GemStoneSession:
    """Open a GemStoneSession using explicit config or environment settings."""
    resolved_config = config or gemstone.GemStoneConfig.from_env()
    return gemstone.GemStoneSession(
        config=resolved_config,
        transaction_policy=transaction_policy,
    )


class GStoreError(Exception):
    pass


class GStoreAbortTransaction(Exception):
    """
    Raise inside a GStore.transaction() block to abort cleanly without
    committing, leaving GemStone state unchanged.

    Python uses a dedicated exception for clean aborts:

        with db.transaction() as t:
            t['key'] = 'value'
            if some_condition:
                raise GStoreAbortTransaction   # nothing committed
    """
    pass


# ---------------------------------------------------------------------------
# GCI helpers — direct dict access without eval strings
# ---------------------------------------------------------------------------

def _map_contains(gs_map: GsDict | GsObject, key: str) -> bool:
    if isinstance(gs_map, GsDict):
        return key in gs_map
    return bool(gs_map._call('includesKey:', key))


def _map_get(gs_map: GsDict | GsObject, key: str) -> Any:
    if isinstance(gs_map, GsDict):
        return gs_map[key]
    if not _map_contains(gs_map, key):
        raise KeyError(key)
    s = object.__getattribute__(gs_map, '_session')
    value_oop = gs_map._call_oop('at:', key)
    return _from_oop(s, value_oop)


def _map_set(gs_map: GsDict | GsObject, key: str, value: Any) -> None:
    if isinstance(gs_map, GsDict):
        gs_map[key] = value
        return
    gs_map._call('at:put:', key, value)


def _map_remove(gs_map: GsDict | GsObject, key: str) -> None:
    gs_map._call('removeKey:ifAbsent:', key, None)


def _map_keys(gs_map: GsDict | GsObject) -> list[str]:
    if isinstance(gs_map, GsDict):
        return gs_map.keys()
    s = object.__getattribute__(gs_map, '_session')
    assoc_arr_oop = gs_map._call_oop('associations')
    size = s.perform(assoc_arr_oop, 'size')
    result = []
    for i in range(1, size + 1):
        assoc_oop = s.perform_oop(assoc_arr_oop, 'at:', gemstone._python_to_smallint(i))
        key_oop = s.perform_oop(assoc_oop, 'key')
        result.append(s.perform(key_oop, 'asString'))
    return result


def _ensure_root(s: gemstone.GemStoneSession) -> GsDict | GsObject:
    """
    Return the GStoreRoot mapping from UserGlobals, creating it if absent.

    Older repositories may already contain a legacy Dictionary/Hash at
    this slot; newer gemstone-py repositories use StringKeyValueDictionary.
    Support both so translated code can run against real existing stones.
    """
    root = PersistentRoot(s)
    if _GSTORE_ROOT not in root:
        root[_GSTORE_ROOT] = {}          # GsDict backed by StringKeyValueDictionary
    return root[_GSTORE_ROOT]            # returns GsDict proxy


def _ensure_file(gs_root: GsDict | GsObject, filename: str) -> GsDict | GsObject:
    """
    Return the per-file mapping for `filename` inside gs_root, creating it if
    absent. Supports both StringKeyValueDictionary and legacy Dictionary.
    """
    if not _map_contains(gs_root, filename):
        _map_set(gs_root, filename, {})
    return _map_get(gs_root, filename)


def _read_file(s: gemstone.GemStoneSession, filename: str) -> dict:
    """
    Read all key/value pairs for `filename` from GemStone into a plain
    Python dict.  Values are JSON-deserialised.  Uses GciStrKeyValueDictAt
    internally (via GsDict.__getitem__).
    """
    gs_root = _ensure_root(s)
    gs_file = _ensure_file(gs_root, filename)
    data = {}
    for key in _map_keys(gs_file):
        raw = _map_get(gs_file, key)
        try:
            data[key] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            data[key] = raw
    return data


def _write_file(s: gemstone.GemStoneSession, filename: str,
                dirty: dict, deletes: set) -> None:
    """
    Flush `dirty` writes and `deletes` to GemStone for `filename`.
    Uses GciStrKeyValueDictAtPut internally (via GsDict.__setitem__).
    """
    gs_root = _ensure_root(s)
    gs_file = _ensure_file(gs_root, filename)
    for key, value in dirty.items():
        _map_set(gs_file, key, json.dumps(value))
    for key in deletes:
        _map_remove(gs_file, key)


def _commit_with_retry(s: gemstone.GemStoneSession, filename: str,
                       dirty: dict, deletes: set) -> None:
    """
    Write dirty/deletes to GemStone and commit, retrying up to _MAX_RETRIES
    times on conflict.

    Uses concurrency.commit() so that genuine hard errors raise GemStoneError
    and commit conflicts raise CommitConflictError (rather than being silently
    swallowed).  Conflict errors trigger an abort-and-retry; hard errors and
    exhausted retries are re-raised immediately.
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        _write_file(s, filename, dirty, deletes)
        try:
            _concurrency_commit(s)
            return
        except CommitConflictError:
            # Conflict — abort to get a fresh view, then retry
            s.abort()
        # Hard GemStoneError propagates immediately (not caught here)
    raise GStoreError(
        f"GStore: unable to commit '{filename}' after {_MAX_RETRIES} attempts"
    )


# ---------------------------------------------------------------------------
# Transaction handle
# ---------------------------------------------------------------------------

class GStoreTransaction:
    """
    A live transaction handle yielded by GStore.transaction().

    Mirrors the PStore/GStore block argument in Ruby:
        db.transaction { |t| t['key'] = value }
    →
        with db.transaction() as t:
            t['key'] = value

    Reads come from an in-memory snapshot taken at transaction open.
    Writes are buffered and flushed to GemStone (via GCI dict calls) on
    clean exit, with automatic commit-conflict retry.
    """

    def __init__(self, store: 'GStore', read_only: bool):
        self._store     = store
        self._read_only = read_only
        self._data: dict  = {}   # snapshot from GemStone at open time
        self._dirty: dict = {}   # pending writes
        self._deletes: set = set()
        self._open = False

    # ------------------------------------------------------------------
    # Dict-like interface
    # ------------------------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        self._require_open()
        k = str(key)
        if k in self._dirty:
            return self._dirty[k]
        if k in self._deletes:
            raise KeyError(key)
        if k in self._data:
            return self._data[k]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self._require_open()
        if self._read_only:
            raise GStoreError("Transaction is read-only")
        k = str(key)
        self._dirty[k] = value
        self._deletes.discard(k)

    def __delitem__(self, key: str) -> None:
        self._require_open()
        if self._read_only:
            raise GStoreError("Transaction is read-only")
        k = str(key)
        self._deletes.add(k)
        self._dirty.pop(k, None)

    def __contains__(self, key: str) -> bool:
        k = str(key)
        if k in self._deletes:
            return False
        if k in self._dirty:
            return True
        return k in self._data

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self) -> list:
        return list((set(self._data) | set(self._dirty)) - self._deletes)

    def items(self) -> list:
        return [(k, self[k]) for k in self.keys()]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_open(self) -> None:
        if not self._open:
            raise GStoreError("Transaction is not open")


# ---------------------------------------------------------------------------
# GStore
# ---------------------------------------------------------------------------

class GStore:
    """
    A GemStone-backed key/value store, analogous to Ruby's PStore.

    Each instance manages one named "file" (a StringKeyValueDictionary)
    inside a shared GStoreRoot dictionary in UserGlobals.  Multiple GStore
    instances with different names are fully independent.

    All dict I/O uses direct GCI calls (GciStrKeyValueDictAtPut /
    GciStrKeyValueDictAt) — no Smalltalk eval strings, no quote-escaping.

    Commit conflicts are retried automatically (up to 10 times).

    Parameters
    ----------
    filename : str
        Name of this store.  Analogous to the PStore filename.
    """

    def __init__(self, filename: str = '', *, config: gemstone.GemStoneConfig | None = None):
        self._filename = filename
        self._config = config or gemstone.GemStoneConfig.from_env()
        self._in_transaction = False   # nested transaction guard
        with _session(
            self._config,
            transaction_policy=gemstone.TransactionPolicy.COMMIT_ON_SUCCESS,
        ) as s:
            _ensure_file(_ensure_root(s), filename)

    @contextmanager
    def transaction(self, read_only: bool = False) -> Iterator[GStoreTransaction]:
        """
        Open a transaction.  Use as a context manager:

            with db.transaction() as t:
                t['key'] = 'value'      # buffered in memory
            # flushed to GemStone and committed on clean exit;
            # commit conflicts retried up to 10 times automatically.

            with db.transaction(read_only=True) as t:
                v = t['key']            # reads from snapshot; no commit

        Raises GStoreError if called while another transaction on this
        GStore instance is already open.
        """
        if self._in_transaction:
            raise GStoreError(
                f"GStore '{self._filename}': nested transaction not allowed"
            )
        txn = GStoreTransaction(self, read_only)
        # Manage the session lifecycle manually so the retry loop (not
        # GemStoneSession.__exit__) owns the commit.
        s = _session(self._config, transaction_policy=gemstone.TransactionPolicy.MANUAL)
        s.login()
        self._in_transaction = True
        try:
            # Abort before reading the snapshot so we always see the most
            # recently committed state, even if this session was previously
            # used.
            s.abort()
            txn._data = _read_file(s, self._filename)
            txn._open = True
            user_raised = False
            aborted = False
            try:
                yield txn
            except GStoreAbortTransaction:
                # Caller raised GStoreAbortTransaction to break out cleanly.
                aborted = True
            except Exception:
                user_raised = True
                raise
            finally:
                txn._open = False
                if not user_raised and not read_only and not aborted:
                    # Flush dirty writes and commit with conflict retry.
                    _commit_with_retry(s, self._filename, txn._dirty, txn._deletes)
                else:
                    s.abort()
        finally:
            self._in_transaction = False
            s.logout()

    # ------------------------------------------------------------------
    # Class-level helpers
    # ------------------------------------------------------------------

    @classmethod
    def rm(cls, filename: str, *, config: gemstone.GemStoneConfig | None = None) -> None:
        """Delete a named GStore from the repository."""
        with _session(
            config,
            transaction_policy=gemstone.TransactionPolicy.COMMIT_ON_SUCCESS,
        ) as s:
            gs_root = _ensure_root(s)
            _map_remove(gs_root, filename)

    @classmethod
    def rm_all(cls, *, config: gemstone.GemStoneConfig | None = None) -> None:
        """Remove the entire GStoreRoot from UserGlobals."""
        with _session(
            config,
            transaction_policy=gemstone.TransactionPolicy.COMMIT_ON_SUCCESS,
        ) as s:
            root = PersistentRoot(s)
            if _GSTORE_ROOT in root:
                ug_oop  = object.__getattribute__(root, '_ug')
                sym_oop = s.new_symbol(_GSTORE_ROOT)
                s.perform_oop(ug_oop, 'removeKey:ifAbsent:',
                              sym_oop, gemstone.OOP_NIL)

    @classmethod
    def list(cls, *, config: gemstone.GemStoneConfig | None = None) -> list[str]:
        """Return the names of all GStore files in the repository."""
        with _session(config) as s:
            root = PersistentRoot(s)
            if _GSTORE_ROOT not in root:
                return []
            return _map_keys(root[_GSTORE_ROOT])
