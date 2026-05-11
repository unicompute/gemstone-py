"""
gsquery — GemStone IdentitySet query helper.

GemStone IdentitySet supports indexed search patterns such as:
    people search: '@age' comparing: #< with: 25
    people createEqualityIndexOn: '@age' withLastElementClass: SmallInt
    people removeEqualityIndexOn: '@age'

This module provides a thin Python wrapper that:
  1. Manages a named IdentitySet stored in GemStone UserGlobals.
  2. Creates / removes equality indexes on instance-variable paths.
  3. Runs search queries and returns results as Python dicts.

GemStone operator mapping
-------------------------
    Python string  →  Smalltalk selector (GemStone search:comparing:with:)
    'lt'           →  #<
    'lte'          →  #<=
    'gt'           →  #>
    'gte'          →  #>=
    'eql'          →  #=
    'neq'          →  #~=

Usage
-----
    from gemstone_py.gsquery import GSCollection

    # Open (or create) a persistent IdentitySet in GemStone UserGlobals
    col = GSCollection('People')

    # Add an index on the @age ivar of elements
    col.add_index('@age')          # equality index, GemStone class SmallInt

    # Insert objects (stored as Dictionary with JSON-serialised ivars)
    col.insert({'@name': 'Alice', '@age': 30})
    col.insert({'@name': 'Bob',   '@age': 24})

    # Bulk-load many objects with one session / collection lookup
    col.bulk_insert(
        {'@name': f'Person {i}', '@age': i % 100}
        for i in range(10_000)
    )

    # Batch keyed rewrites
    col.bulk_upsert_unique('@name', [
        {'@name': 'Alice', '@age': 31},
        {'@name': 'Bob', '@age': 25},
    ])

    # Query
    youngsters = col.search('@age', 'lt', 25)
    print(youngsters)   # [{'@name': 'Bob', '@age': 24}]

    # Multi-level path
    col.add_index('@address.@zip')
    results = col.search('@address.@zip', 'eql', 45678)

    # Intersection (logical AND of two queries)
    old   = col.search('@age', 'gte', 75)
    hermits = col.search('@status', 'eql', 'hermit')
    old_hermits = col.intersect(old, hermits)

    # Remove index
    col.remove_index('@age')

    # Delete the collection from GemStone
    GSCollection.drop('People')

Implementation notes
--------------------
GemStone stores each element as a Dictionary (not a real typed object),
since we are talking to GemStone via Smalltalk eval and cannot instantiate
arbitrary Python classes there.  The Dictionary keys are the ivar path
strings (e.g. '@age', '@address.@zip').  Values are stored with their
natural GemStone types so indexed comparisons behave correctly.  The
equality index is created on the appropriate key using:

    aCollection createEqualityIndexOn: '@age' withLastElementClass: SmallInt.

This is the standard GemStone equality-index operation.
"""

import json
from collections.abc import Callable, Iterator
from contextlib import nullcontext
from dataclasses import dataclass
from types import TracebackType
from typing import Any, ContextManager, Generic, Iterable, List, Literal, TypeVar, cast, overload

import gemstone_py as gemstone
from gemstone_py.persistent_root import _from_oop, _to_oop

from ._smalltalk_batch import (
    fetch_mapping_string_keys,
    fetch_mapping_string_oop_pairs,
    json_string_encoder_source,
    object_for_oop_expr,
)

PORTING_STATUS = "plain_gemstone_port"
RUNTIME_REQUIREMENT = "Works on plain GemStone images over GCI"

# GemStone search operator map
_OPS = {
    'lt':  '#<',
    'lte': '#<=',
    'gt':  '#>',
    'gte': '#>=',
    'eql': '#=',
    'neq': '#~=',
}

# Root key in UserGlobals that holds all named GSCollections
_ROOT = 'GSQueryRoot'
Record = dict[str, Any]
RecordT = TypeVar("RecordT")


@dataclass(frozen=True)
class QueryPredicate:
    """One typed query predicate against a GemStone record ivar path."""

    ivar_path: str
    op: str
    value: Any


class _FieldPath:
    """Runtime field recorder used by ``Query.where(lambda row: ...)``."""

    def __init__(self, parts: tuple[str, ...]):
        self._parts = parts

    @property
    def ivar_path(self) -> str:
        return ".".join(f"@{part}" for part in self._parts)

    def __getattr__(self, name: str) -> "_FieldPath":
        if name.startswith("__"):
            raise AttributeError(name)
        return _FieldPath((*self._parts, name))

    def _predicate(self, op: str, value: Any) -> QueryPredicate:
        return QueryPredicate(self.ivar_path, op, value)

    def eq(self, value: Any) -> QueryPredicate:
        return self._predicate("eql", value)

    def ne(self, value: Any) -> QueryPredicate:
        return self._predicate("neq", value)

    def lt(self, value: Any) -> QueryPredicate:
        return self._predicate("lt", value)

    def lte(self, value: Any) -> QueryPredicate:
        return self._predicate("lte", value)

    def gt(self, value: Any) -> QueryPredicate:
        return self._predicate("gt", value)

    def gte(self, value: Any) -> QueryPredicate:
        return self._predicate("gte", value)

    def __eq__(self, value: object) -> Any:
        return self.eq(value)

    def __ne__(self, value: object) -> Any:
        return self.ne(value)

    def __lt__(self, value: Any) -> QueryPredicate:
        return self.lt(value)

    def __le__(self, value: Any) -> QueryPredicate:
        return self.lte(value)

    def __gt__(self, value: Any) -> QueryPredicate:
        return self.gt(value)

    def __ge__(self, value: Any) -> QueryPredicate:
        return self.gte(value)


class _QueryRow:
    """Root field recorder for typed query lambdas."""

    def __getattr__(self, name: str) -> _FieldPath:
        if name.startswith("__"):
            raise AttributeError(name)
        return _FieldPath((name,))


class _RecordProxy:
    """Attribute facade over a materialized GemStone record dictionary."""

    def __init__(self, data: Record):
        self._data = data

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        for key in (name, f"@{name}"):
            if key in self._data:
                return _wrap_record_value(self._data[key])
        raise AttributeError(name)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self) -> Iterable[str]:
        return self._data.keys()

    def items(self) -> Iterable[tuple[str, Any]]:
        for key, value in self._data.items():
            yield key, _wrap_record_value(value)

    def to_dict(self) -> Record:
        return dict(self._data)

    def __repr__(self) -> str:
        return f"<GSCollectionRecord {self._data!r}>"


def _wrap_record_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _RecordProxy(value)
    if isinstance(value, list):
        return [_wrap_record_value(item) for item in value]
    return value


_MISSING = object()


def _session(
    session: gemstone.GemStoneSession | None = None,
    config: gemstone.GemStoneConfig | None = None,
) -> ContextManager[gemstone.GemStoneSession]:
    if session is not None:
        return cast(
            ContextManager[gemstone.GemStoneSession],
            gemstone.session_scope(
                session,
                transaction_policy=gemstone.TransactionPolicy.COMMIT_ON_SUCCESS,
            ),
        )
    resolved_config = config or gemstone.GemStoneConfig.from_env()
    return cast(
        ContextManager[gemstone.GemStoneSession],
        gemstone.session_scope(
            session,
            config=resolved_config,
            transaction_policy=gemstone.TransactionPolicy.COMMIT_ON_SUCCESS,
        ),
    )


def _escape(s: str) -> str:
    return s.replace("'", "''")


def _smalltalk_value(v: Any) -> str:
    """Render a Python value as a Smalltalk literal for use in eval."""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if v is None:
        return 'nil'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(v)
    if isinstance(v, str):
        return f"'{_escape(v)}'"
    raise ValueError(f"Cannot convert {v!r} to a Smalltalk literal for indexed search")


def _close_iterator(iterator: object) -> None:
    close = getattr(iterator, "close", None)
    if callable(close):
        close()


def _observe_session_operation(
    session: object,
    operation: str,
    attrs: dict[str, str | int | float | bool | None],
) -> ContextManager[object]:
    if not isinstance(session, gemstone.GemStoneSession):
        return nullcontext()
    observer = getattr(session, "_observe_operation", None)
    if callable(observer):
        return cast(ContextManager[object], observer(operation, attrs))
    return nullcontext()


class GSCollection:
    """
    A named, persistent IdentitySet in GemStone UserGlobals.

    Elements are stored as Dictionaries (ivar-path → value).  This lets us
    create equality indexes on ivar paths and run range queries without
    defining typed Smalltalk classes.
    """

    def __init__(self, name: str, *, config: gemstone.GemStoneConfig | None = None):
        self._name = name
        self._config = config

    def query(
        self,
        record_type: type[RecordT] | None = None,
        *,
        session: gemstone.GemStoneSession | None = None,
    ) -> "Query[RecordT]":
        """Return a typed query facade for this collection."""
        return Query(self, record_type=record_type, session=session)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_root(self, s: gemstone.GemStoneSession) -> None:
        root = _escape(_ROOT)
        name = _escape(self._name)
        s.eval(
            f"(UserGlobals includesKey: #{root}) ifFalse: ["
            f"  UserGlobals at: #{root} put: Dictionary new ]."
        )
        s.eval(
            f"((UserGlobals at: #{root}) includesKey: '{name}') ifFalse: ["
            f"  (UserGlobals at: #{root}) at: '{name}' put: IdentitySet new ]."
        )

    def _set_expr(self) -> str:
        root = _escape(_ROOT)
        name = _escape(self._name)
        return f"((UserGlobals at: #{root}) at: '{name}')"

    def _set_oop(self, s: gemstone.GemStoneSession) -> int:
        self._ensure_root(s)
        return s.eval_oop(self._set_expr())

    @staticmethod
    def _collection_member_oops(
        s: gemstone.GemStoneSession,
        collection_oop: int,
    ) -> List[int]:
        array_oop = s.perform_oop(collection_oop, 'asArray')
        size = s.perform_value(array_oop, 'size')
        result = []
        for i in range(1, size + 1):
            idx_oop = gemstone._python_to_smallint(i)
            result.append(s.perform_oop(array_oop, 'at:', idx_oop))
        return result

    @staticmethod
    def _path_array_oop(s: gemstone.GemStoneSession, ivar_path: str) -> int:
        segments = ivar_path.split('.')
        array_class_oop = s.resolve('Array')
        size_oop = cast(int, gemstone._python_to_smallint(len(segments)))
        array_oop = s.perform_oop(array_class_oop, 'new:', size_oop)
        for i, segment in enumerate(segments, 1):
            idx_oop = cast(int, gemstone._python_to_smallint(i))
            segment_oop = s.new_string(segment)
            s.perform_oop(array_oop, 'at:put:', idx_oop, segment_oop)
        return array_oop

    @staticmethod
    def _keys_from_dict_oop(s: gemstone.GemStoneSession, dict_oop: int) -> List[str]:
        return fetch_mapping_string_keys(
            s,
            dict_oop,
            iterate_header="mapping keysAndValuesDo: [:key :value |",
            key_expr="key asString",
        )

    @staticmethod
    def _plain_value(value: Any) -> Any:
        if isinstance(value, list):
            return [GSCollection._plain_value(item) for item in value]
        if isinstance(value, dict):
            return {str(k): GSCollection._plain_value(v) for k, v in value.items()}
        items = getattr(value, 'items', None)
        if callable(items):
            return {
                str(k): GSCollection._plain_value(v)
                for k, v in items()
            }
        keys = getattr(value, 'keys', None)
        if callable(keys) and hasattr(value, '__getitem__'):
            return {str(k): GSCollection._plain_value(value[k]) for k in value.keys()}
        return value

    @staticmethod
    def _dict_from_oop(s: gemstone.GemStoneSession, dict_oop: int) -> Record:
        return {
            key: GSCollection._plain_value(_from_oop(s, value_oop))
            for key, value_oop in fetch_mapping_string_oop_pairs(
                s,
                dict_oop,
                iterate_header="mapping keysAndValuesDo: [:key :value |",
                key_expr="key asString",
                value_expr="value asOop asString",
            )
        }

    def _all_records(self, s: gemstone.GemStoneSession) -> List[Record]:
        return self._records_from_collection_oop(s, self._set_oop(s))

    @staticmethod
    def _records_from_collection_oop(
        s: gemstone.GemStoneSession,
        collection_oop: int,
    ) -> List[Record]:
        """
        Materialize a collection of record dictionaries in one eval/fetch.

        Elements inserted through GSCollection are limited to JSON-friendly
        scalars, arrays, and dictionaries, so we serialize them to one JSON
        line per record on the GemStone side and decode them in Python.
        """
        raw = s.eval(
            f"| collection encodeString encodeValue encodeMap encodeSequence stream |\n"
            f"collection := {object_for_oop_expr(collection_oop)}.\n"
            f"{json_string_encoder_source('encodeString')}"
            "encodeValue := nil.\n"
            "encodeMap := nil.\n"
            "encodeSequence := nil.\n"
            "encodeSequence := [:seq | | out first |\n"
            "  out := '['.\n"
            "  first := true.\n"
            "  seq do: [:each |\n"
            "    first ifFalse: [ out := out, ',' ].\n"
            "    out := out, (encodeValue value: each).\n"
            "    first := false\n"
            "  ].\n"
            "  out, ']'\n"
            "].\n"
            "encodeMap := [:map | | out first |\n"
            "  out := '{'.\n"
            "  first := true.\n"
            "  map keysAndValuesDo: [:key :value |\n"
            "    first ifFalse: [ out := out, ',' ].\n"
            "    out := out,\n"
            "      '\"', (encodeString value: key), '\":', (encodeValue value: value).\n"
            "    first := false\n"
            "  ].\n"
            "  out, '}'\n"
            "].\n"
            "encodeValue := [:value |\n"
            "  value isNil ifTrue: [ 'null' ] ifFalse: [\n"
            "    value == true ifTrue: [ 'true' ] ifFalse: [\n"
            "      value == false ifTrue: [ 'false' ] ifFalse: [\n"
            "        ((value isKindOf: String) or: [ value class == Symbol ]) ifTrue: [\n"
            "          '\"', (encodeString value: value), '\"'\n"
            "        ] ifFalse: [\n"
            "          (value respondsTo: #keysAndValuesDo:) ifTrue: [\n"
            "            encodeMap value: value\n"
            "          ] ifFalse: [\n"
            "            ((value isKindOf: SequenceableCollection)\n"
            "              and: [(value isKindOf: String) not])\n"
            "              ifTrue: [ encodeSequence value: value ]\n"
            "              ifFalse: [ value printString ]\n"
            "          ]\n"
            "        ]\n"
            "      ]\n"
            "    ]\n"
            "  ]\n"
            "].\n"
            "stream := ''.\n"
            "collection do: [:record |\n"
            "  stream := stream, (encodeMap value: record), String lf asString\n"
            "].\n"
            "stream"
        )
        return [cast(Record, json.loads(line)) for line in raw.splitlines() if line.strip()]

    @staticmethod
    def _records_from_array_range_oop(
        s: gemstone.GemStoneSession,
        array_oop: int,
        start: int,
        stop: int,
    ) -> List[Record]:
        """
        Materialize one 1-based inclusive slice from a GemStone Array of records.

        This keeps large result iteration bounded by ``chunk_size`` on the
        Python side while reusing the same JSON representation as ``search()``.
        """
        raw = s.eval(
            f"| array encodeString encodeValue encodeMap encodeSequence stream |\n"
            f"array := {object_for_oop_expr(array_oop)}.\n"
            f"{json_string_encoder_source('encodeString')}"
            "encodeValue := nil.\n"
            "encodeMap := nil.\n"
            "encodeSequence := nil.\n"
            "encodeSequence := [:seq | | out first |\n"
            "  out := '['.\n"
            "  first := true.\n"
            "  seq do: [:each |\n"
            "    first ifFalse: [ out := out, ',' ].\n"
            "    out := out, (encodeValue value: each).\n"
            "    first := false\n"
            "  ].\n"
            "  out, ']'\n"
            "].\n"
            "encodeMap := [:map | | out first |\n"
            "  out := '{'.\n"
            "  first := true.\n"
            "  map keysAndValuesDo: [:key :value |\n"
            "    first ifFalse: [ out := out, ',' ].\n"
            "    out := out,\n"
            "      '\"', (encodeString value: key), '\":', (encodeValue value: value).\n"
            "    first := false\n"
            "  ].\n"
            "  out, '}'\n"
            "].\n"
            "encodeValue := [:value |\n"
            "  value isNil ifTrue: [ 'null' ] ifFalse: [\n"
            "    value == true ifTrue: [ 'true' ] ifFalse: [\n"
            "      value == false ifTrue: [ 'false' ] ifFalse: [\n"
            "        ((value isKindOf: String) or: [ value class == Symbol ]) ifTrue: [\n"
            "          '\"', (encodeString value: value), '\"'\n"
            "        ] ifFalse: [\n"
            "          (value respondsTo: #keysAndValuesDo:) ifTrue: [\n"
            "            encodeMap value: value\n"
            "          ] ifFalse: [\n"
            "            ((value isKindOf: SequenceableCollection)\n"
            "              and: [(value isKindOf: String) not])\n"
            "              ifTrue: [ encodeSequence value: value ]\n"
            "              ifFalse: [ value printString ]\n"
            "          ]\n"
            "        ]\n"
            "      ]\n"
            "    ]\n"
            "  ]\n"
            "].\n"
            "stream := ''.\n"
            f"{start} to: {stop} do: [:index | | record |\n"
            "  record := array at: index.\n"
            "  stream := stream, (encodeMap value: record), String lf asString\n"
            "].\n"
            "stream"
        )
        return [cast(Record, json.loads(line)) for line in raw.splitlines() if line.strip()]

    def _record_oop(self, s: gemstone.GemStoneSession, element: Record) -> int:
        dict_oop = s.perform_oop(s.resolve('Dictionary'), 'new')
        for k, v in element.items():
            key_oop = s.new_string(str(k))
            val_oop = _to_oop(s, v)
            s.perform_oop(dict_oop, 'at:put:', key_oop, val_oop)
        return dict_oop

    def _insert_into_set_oop(
        self,
        s: gemstone.GemStoneSession,
        set_oop: int,
        element: Record,
    ) -> None:
        s.perform_oop(set_oop, 'add:', self._record_oop(s, element))

    def _remove_member_oops(
        self,
        s: gemstone.GemStoneSession,
        set_oop: int,
        member_oops: List[int],
    ) -> int:
        for member_oop in member_oops:
            s.perform_oop(set_oop, 'remove:', member_oop)
        return len(member_oops)

    def _insert_with_session(self, s: gemstone.GemStoneSession, element: Record) -> None:
        self._insert_into_set_oop(s, self._set_oop(s), element)

    def _search_result_oop(
        self,
        s: gemstone.GemStoneSession,
        ivar_path: str,
        op: str,
        value: Any,
    ) -> int:
        if op not in _OPS:
            raise ValueError(f"Unknown operator {op!r}. Use one of: {list(_OPS)}")

        gs_op  = _OPS[op]
        gs_val = _smalltalk_value(value)
        path   = _escape(ivar_path)

        self._ensure_root(s)
        try:
            result_oop = s.perform_oop(
                self._set_oop(s),
                'search:comparing:with:',
                self._path_array_oop(s, ivar_path),
                s.new_symbol(gs_op[1:]),
                _to_oop(s, value),
            )
            if result_oop == gemstone.OOP_NIL:
                raise gemstone.GemStoneError("GSCollection indexed search returned nil")
        except Exception:
            result_oop = s.eval_oop(
                f"| col result valueOrNil |\n"
                f"col := {self._set_expr()}.\n"
                f"result := col select: [:e |\n"
                f"  valueOrNil := e at: '{path}' ifAbsent: [nil].\n"
                f"  valueOrNil notNil and: [ valueOrNil {gs_op[1:]} {gs_val} ]\n"
                f"].\n"
                f"result"
            )

        return result_oop

    def _search_oops(
        self,
        s: gemstone.GemStoneSession,
        ivar_path: str,
        op: str,
        value: Any,
    ) -> List[int]:
        result_oop = self._search_result_oop(s, ivar_path, op, value)
        if result_oop == gemstone.OOP_NIL:
            return []
        return self._collection_member_oops(s, result_oop)

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def add_index(
        self,
        ivar_path: str,
        session: gemstone.GemStoneSession | None = None,
    ) -> None:
        """
        Create an equality index on `ivar_path` (e.g. '@age', '@address.@zip').

        Infers the GemStone element class from the first element already in the
        collection.  The collection must be non-empty when this is called;
        if it is empty use add_index_for_class() and supply the class explicitly.

        The value class is determined automatically by inspecting existing
        elements.
        """
        with _session(session, self._config) as s:
            self._ensure_root(s)
            path = _escape(ivar_path)
            # Ask GemStone to infer the class of the value at `path` from the
            # first element already stored, then create the index.
            # If no elements exist yet this returns nil and GemStone will raise;
            # callers should insert at least one element first or use
            # add_index_for_class() with an explicit class name.
            s.eval(
                f"| col cls |\n"
                f"col := {self._set_expr()}.\n"
                f"cls := col isEmpty\n"
                f"  ifTrue:  [ String ]\n"
                f"  ifFalse: [\n"
                f"    | sample val |\n"
                f"    sample := col anElement.\n"
                f"    val := sample at: '{path}' ifAbsent: [nil].\n"
                f"    val isNil ifTrue: [String] ifFalse: [val class]\n"
                f"  ].\n"
                f"col createEqualityIndexOn: '{path}' withLastElementClass: cls."
            )

    def add_index_for_class(
        self,
        ivar_path: str,
        gs_class: str = 'SmallInt',
        session: gemstone.GemStoneSession | None = None,
    ) -> None:
        """
        Create an equality index with an explicit GemStone element class.

        Parameters
        ----------
        ivar_path : str
            Dot-separated ivar path, e.g. '@age' or '@address.@zip'.
        gs_class : str
            GemStone class name for the last element, e.g. 'SmallInt',
            'String', 'Float', 'LargePositiveInteger'.
        """
        with _session(session, self._config) as s:
            self._ensure_root(s)
            path = _escape(ivar_path)
            s.eval(
                f"{self._set_expr()}"
                f" createEqualityIndexOn: '{path}'"
                f" withLastElementClass: {gs_class}."
            )

    def remove_index(
        self,
        ivar_path: str,
        session: gemstone.GemStoneSession | None = None,
    ) -> None:
        """Remove a single equality index."""
        with _session(session, self._config) as s:
            path = _escape(ivar_path)
            s.eval(f"{self._set_expr()} removeEqualityIndexOn: '{path}'.")

    def remove_all_indexes(self, session: gemstone.GemStoneSession | None = None) -> None:
        """Remove every index on this collection."""
        with _session(session, self._config) as s:
            s.eval(f"{self._set_expr()} removeAllIndexes.")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def insert(
        self,
        element: Record,
        session: gemstone.GemStoneSession | None = None,
    ) -> None:
        """
        Insert a dict into the IdentitySet.

        Keys should be ivar-path strings (e.g. '@name', '@age').
        Values are stored with their natural GemStone types so that indexed
        comparisons behave correctly.
        """
        with _session(session, self._config) as s:
            self._insert_with_session(s, element)

    def bulk_insert(
        self,
        elements: Iterable[Record],
        session: gemstone.GemStoneSession | None = None,
    ) -> int:
        """
        Insert many dicts using one session and one collection lookup.

        `elements` may be any iterable of dicts. This is the preferred path
        for loading large collections because it avoids reopening GemStone and
        re-resolving the backing IdentitySet for each row.

        Returns the number of inserted elements.
        """
        with _session(session, self._config) as s:
            set_oop = self._set_oop(s)
            total = 0
            for element in elements:
                self._insert_into_set_oop(s, set_oop, element)
                total += 1
            return total

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def search(
        self,
        ivar_path: str,
        op: str,
        value: Any,
        session: gemstone.GemStoneSession | None = None,
    ) -> List[Record]:
        """
        Search the collection on an indexed (or non-indexed) ivar path.

        Uses GemStone's indexed search:comparing:with: when an equality index
        exists on the path and otherwise falls back to a full select: scan.

        Parameters
        ----------
        ivar_path : str
            e.g. '@age' or '@address.@zip'
        op : str
            One of: 'lt', 'lte', 'gt', 'gte', 'eql', 'neq'
        value : Any
            A JSON-serialisable Python value.

        Returns
        -------
        list[dict]
            Matching elements as Python dicts (same structure as insert()).
        """
        with self.search_iter(ivar_path, op, value, session=session) as iterator:
            return list(iterator)

    def search_iter(
        self,
        ivar_path: str,
        op: str,
        value: Any,
        *,
        chunk_size: int = 256,
        session: gemstone.GemStoneSession | None = None,
    ) -> "GSCollectionIterator":
        """
        Iterate over matching records in chunks.

        Use this for large result sets when materialising the full list returned
        by ``search()`` would be wasteful. If no session is supplied, the
        iterator owns a session until exhausted or closed.
        """
        return GSCollectionIterator(
            self,
            lambda s: self._search_result_oop(s, ivar_path, op, value),
            chunk_size=chunk_size,
            session=session,
        )

    def all(self, session: gemstone.GemStoneSession | None = None) -> List[Record]:
        """Return every element in the collection."""
        with self.iter(session=session) as iterator:
            return list(iterator)

    def iter(
        self,
        *,
        chunk_size: int = 256,
        session: gemstone.GemStoneSession | None = None,
    ) -> "GSCollectionIterator":
        """
        Iterate over all records in chunks.

        The iterator is also a context manager. Prefer ``with`` when you may
        break early so any owned GemStone session is closed promptly.
        """
        return GSCollectionIterator(
            self,
            lambda s: self._set_oop(s),
            chunk_size=chunk_size,
            session=session,
        )

    def size(self, session: gemstone.GemStoneSession | None = None) -> int:
        """Return the number of elements in the collection."""
        with _session(session, self._config) as s:
            return cast(int, s.perform_value(self._set_oop(s), 'size'))

    def replace_all(
        self,
        elements: List[Record],
        session: gemstone.GemStoneSession | None = None,
    ) -> None:
        """
        Replace the collection contents with `elements`.

        This recreates the underlying IdentitySet.  Callers that rely on
        equality indexes should add them again afterwards.
        """
        with _session(session, self._config) as s:
            self._ensure_root(s)
            root = _escape(_ROOT)
            name = _escape(self._name)
            s.eval(f"(UserGlobals at: #{root}) at: '{name}' put: IdentitySet new.")
            set_oop = self._set_oop(s)
            for element in elements:
                self._insert_into_set_oop(s, set_oop, element)

    def delete_where(
        self,
        ivar_path: str,
        value: Any,
        session: gemstone.GemStoneSession | None = None,
    ) -> int:
        """
        Remove every element whose `ivar_path` equals `value`.

        Returns the number of removed elements.
        """
        return self.bulk_delete_where(ivar_path, [value], session=session)

    def bulk_delete_where(
        self,
        ivar_path: str,
        values: Iterable[Any],
        session: gemstone.GemStoneSession | None = None,
    ) -> int:
        """
        Remove every element whose `ivar_path` equals any of `values`.

        Uses one session and one collection lookup for the whole batch.
        Returns the total number of removed elements.
        """
        with _session(session, self._config) as s:
            set_oop = self._set_oop(s)
            total = 0
            seen: set[Any] = set()
            for value in values:
                if value in seen:
                    continue
                seen.add(value)
                total += self._remove_member_oops(
                    s,
                    set_oop,
                    self._search_oops(s, ivar_path, 'eql', value),
                )
            return total

    def upsert_unique(
        self,
        ivar_path: str,
        element: Record,
        session: gemstone.GemStoneSession | None = None,
    ) -> None:
        """
        Replace any existing elements matching `element[ivar_path]`, then insert
        `element` as the unique current record for that key.
        """
        self.bulk_upsert_unique(ivar_path, [element], session=session)

    def bulk_upsert_unique(
        self,
        ivar_path: str,
        elements: Iterable[Record],
        session: gemstone.GemStoneSession | None = None,
    ) -> int:
        """
        Replace any existing elements matching each element's `ivar_path`, then
        insert one current record per unique key.

        Uses one session and one collection lookup for the whole batch.
        If multiple input elements have the same key, the last one wins.
        Returns the number of inserted records.
        """
        keyed: dict[Any, Record] = {}
        order: list[Any] = []
        for element in elements:
            if ivar_path not in element:
                raise KeyError(ivar_path)
            key = element[ivar_path]
            if key not in keyed:
                order.append(key)
            keyed[key] = element

        with _session(session, self._config) as s:
            set_oop = self._set_oop(s)
            for key in order:
                self._remove_member_oops(
                    s,
                    set_oop,
                    self._search_oops(s, ivar_path, 'eql', key),
                )
                self._insert_into_set_oop(s, set_oop, keyed[key])
            return len(order)

    # ------------------------------------------------------------------
    # Set operations (Python-side, post-fetch)
    # ------------------------------------------------------------------

    @staticmethod
    def intersect(a: List[Record], b: List[Record]) -> List[Record]:
        """
        Return elements in both `a` and `b`.

        Uses dict identity comparison (same dict == same element is not
        possible post-fetch; instead we compare all key/value pairs).
        """
        b_set = [json.dumps(d, sort_keys=True) for d in b]
        return [d for d in a if json.dumps(d, sort_keys=True) in b_set]

    # ------------------------------------------------------------------
    # Class-level helpers
    # ------------------------------------------------------------------

    @classmethod
    def drop(
        cls,
        name: str,
        session: gemstone.GemStoneSession | None = None,
        *,
        config: gemstone.GemStoneConfig | None = None,
    ) -> None:
        """Delete a named collection from UserGlobals."""
        with _session(session, config) as s:
            root = _escape(_ROOT)
            n    = _escape(name)
            s.eval(
                f"(UserGlobals includesKey: #{root}) ifTrue: ["
                f"  (UserGlobals at: #{root}) removeKey: '{n}' ifAbsent: [] ]."
            )

    @classmethod
    def list(
        cls,
        session: gemstone.GemStoneSession | None = None,
        *,
        config: gemstone.GemStoneConfig | None = None,
    ) -> List[str]:
        """Return the names of all GSCollections in the repository."""
        with _session(session, config) as s:
            root = _escape(_ROOT)
            exists = s.eval(f"UserGlobals includesKey: #{root}")
            if not exists:
                return []
            root_oop = s.eval_oop(f"UserGlobals at: #{root}")
            return cls._keys_from_dict_oop(s, root_oop)


class GSCollectionIterator(Iterator[Record]):
    """Chunked iterator over a GemStone collection of record dictionaries."""

    def __init__(
        self,
        collection: GSCollection,
        collection_oop_factory: Callable[[gemstone.GemStoneSession], int],
        *,
        chunk_size: int = 256,
        session: gemstone.GemStoneSession | None = None,
    ):
        if chunk_size < 1:
            raise ValueError("chunk_size must be at least 1")
        self._collection = collection
        self._collection_oop_factory = collection_oop_factory
        self._chunk_size = chunk_size
        self._provided_session = session
        self._session_cm: ContextManager[gemstone.GemStoneSession] | None = None
        self._session: gemstone.GemStoneSession | None = None
        self._array_oop: int | None = None
        self._size = 0
        self._next_index = 1
        self._buffer: list[Record] = []
        self._closed = False
        self._chunks_fetched = 0
        self._yielded = 0

    def __iter__(self) -> "GSCollectionIterator":
        return self

    def __next__(self) -> Record:
        if not self._buffer:
            self._fill_buffer()
        if not self._buffer:
            self.close()
            raise StopIteration
        self._yielded += 1
        return self._buffer.pop(0)

    def __enter__(self) -> "GSCollectionIterator":
        self._open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        del exc_type, exc_val, exc_tb
        self.close()
        return False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        session_cm = self._session_cm
        session = self._session
        self._session_cm = None
        self._session = None
        if session is not None:
            with _observe_session_operation(
                session,
                "query_iter",
                {
                    "collection": self._collection._name,
                    "chunk_size": self._chunk_size,
                    "total_yielded": self._yielded,
                    "chunks_fetched": self._chunks_fetched,
                },
            ):
                pass
        if session_cm is not None:
            session_cm.__exit__(None, None, None)

    def _open(self) -> None:
        if self._closed:
            raise RuntimeError("GSCollectionIterator is closed")
        if self._session is not None:
            return
        if self._provided_session is not None:
            session = self._provided_session
        else:
            self._session_cm = _session(None, self._collection._config)
            session = self._session_cm.__enter__()
        collection_oop = self._collection_oop_factory(session)
        self._session = session
        if collection_oop == gemstone.OOP_NIL:
            self._size = 0
            return
        self._array_oop = session.perform_oop(collection_oop, 'asArray')
        self._size = cast(int, session.perform_value(self._array_oop, 'size'))

    def _fill_buffer(self) -> None:
        self._open()
        if self._next_index > self._size:
            return
        session = self._session
        array_oop = self._array_oop
        if session is None or array_oop is None:
            raise RuntimeError("GSCollectionIterator is not open")
        stop = min(self._next_index + self._chunk_size - 1, self._size)
        with _observe_session_operation(
            session,
            "query_iter_chunk",
            {
                "collection": self._collection._name,
                "chunk_size": self._chunk_size,
                "start": self._next_index,
                "stop": stop,
            },
        ):
            self._buffer = self._collection._records_from_array_range_oop(
                session,
                array_oop,
                self._next_index,
                stop,
            )
        self._chunks_fetched += 1
        self._next_index = stop + 1

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


class Query(Generic[RecordT]):
    """Typed query facade for ``GSCollection`` records."""

    def __init__(
        self,
        collection: GSCollection,
        *,
        record_type: type[RecordT] | None = None,
        session: gemstone.GemStoneSession | None = None,
        filters: list[QueryPredicate] | None = None,
    ):
        self._collection = collection
        self._record_type = record_type
        self._session = session
        self._filters = list(filters or [])

    @overload
    def where(self, ivar_path: str, op: str, value: Any) -> "Query[RecordT]":
        ...

    @overload
    def where(self, ivar_path: Callable[[RecordT], object]) -> "Query[RecordT]":
        ...

    def where(
        self,
        ivar_path: str | Callable[[Any], object],
        op: str | None = None,
        value: Any = _MISSING,
    ) -> "Query[RecordT]":
        """
        Return a new query with one additional GemStone indexed-search predicate.

        The classic form is ``where("@age", "lt", 25)``. The typed form accepts
        a lambda over a field recorder, such as ``where(lambda row: row.age < 25)``.
        Attribute paths map to GemStone ivar paths, so ``row.address.zip`` becomes
        ``@address.@zip``.
        """
        if callable(ivar_path):
            if op is not None or value is not _MISSING:
                raise TypeError("lambda query predicates do not accept op/value arguments")
            predicate = ivar_path(_QueryRow())
            if not isinstance(predicate, QueryPredicate):
                raise TypeError(
                    "query lambda must return one field comparison, "
                    "for example: lambda row: row.status == 'booked'"
                )
        else:
            if op is None or value is _MISSING:
                raise TypeError("string query predicates require ivar_path, op, and value")
            predicate = QueryPredicate(ivar_path, op, value)

        return Query(
            self._collection,
            record_type=self._record_type,
            session=self._session,
            filters=[*self._filters, predicate],
        )

    def all(self) -> list[RecordT]:
        """Materialize all records matching this query by exhausting ``iter()``."""
        return list(self.iter())

    def iter(self, *, chunk_size: int = 256) -> Iterator[RecordT]:
        """
        Iterate over matching records in chunks.

        With zero or one predicate this streams directly from GemStone in
        ``chunk_size`` batches. Additional predicates are applied Python-side to
        the streamed first-predicate result to avoid materialising every match.
        """
        remaining: list[QueryPredicate] = []
        if not self._filters:
            records: Iterator[Record] = self._collection.iter(
                chunk_size=chunk_size,
                session=self._session,
            )
        else:
            first, *remaining = self._filters
            records = self._collection.search_iter(
                first.ivar_path,
                first.op,
                first.value,
                chunk_size=chunk_size,
                session=self._session,
            )
        try:
            for record in records:
                if remaining and not all(
                    _record_matches_predicate(record, predicate) for predicate in remaining
                ):
                    continue
                yield self._coerce_record(record)
        finally:
            _close_iterator(records)

    def first(self, default: RecordT | None = None) -> RecordT | None:
        """Return the first matching record, or ``default`` when empty."""
        iterator = self.iter(chunk_size=1)
        try:
            return next(iterator, default)
        finally:
            _close_iterator(iterator)

    def _coerce_records(self, records: list[Record]) -> list[RecordT]:
        return [self._coerce_record(record) for record in records]

    def _coerce_record(self, record: Record) -> RecordT:
        if self._record_type is None or self._record_type is dict:
            return cast(RecordT, record)
        return cast(RecordT, _RecordProxy(record))


# ------------------------------------------------------------------
# Row parsing helpers
# ------------------------------------------------------------------

def _parse_rows(raw: str) -> list[Record]:
    """Parse the serialised row format produced by our Smalltalk queries."""
    results: list[Record] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        row: Record = {}
        for pair in line.split(';'):
            pair = pair.strip()
            if not pair or '=' not in pair:
                continue
            k, _, v_raw = pair.partition('=')
            try:
                row[k] = json.loads(v_raw)
            except (json.JSONDecodeError, TypeError):
                row[k] = v_raw
        if row:
            results.append(row)
    return results


def _record_matches_predicate(record: Record, predicate: QueryPredicate) -> bool:
    value = _record_path_value(record, predicate.ivar_path)
    if value is _MISSING:
        return False
    target = predicate.value
    if predicate.op == "lt":
        return bool(value < target)
    if predicate.op == "lte":
        return bool(value <= target)
    if predicate.op == "gt":
        return bool(value > target)
    if predicate.op == "gte":
        return bool(value >= target)
    if predicate.op == "eql":
        return bool(value == target)
    if predicate.op == "neq":
        return bool(value != target)
    raise ValueError(f"Unknown operator {predicate.op!r}. Use one of: {list(_OPS)}")


def _record_path_value(record: Record, ivar_path: str) -> Any:
    if ivar_path in record:
        return record[ivar_path]
    current: Any = record
    for segment in ivar_path.split("."):
        if isinstance(current, dict):
            if segment in current:
                current = current[segment]
                continue
            plain_segment = segment[1:] if segment.startswith("@") else segment
            if plain_segment in current:
                current = current[plain_segment]
                continue
        return _MISSING
    return current
