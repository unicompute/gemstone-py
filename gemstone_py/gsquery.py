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
from typing import Any, ContextManager, Iterable, List, cast

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
        size = s.perform(array_oop, 'size')
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
        with _session(session, self._config) as s:
            result_oop = self._search_result_oop(s, ivar_path, op, value)
            if result_oop == gemstone.OOP_NIL:
                return []
            return self._records_from_collection_oop(s, result_oop)

    def all(self, session: gemstone.GemStoneSession | None = None) -> List[Record]:
        """Return every element in the collection."""
        with _session(session, self._config) as s:
            return self._all_records(s)

    def size(self, session: gemstone.GemStoneSession | None = None) -> int:
        """Return the number of elements in the collection."""
        with _session(session, self._config) as s:
            return cast(int, s.perform(self._set_oop(s), 'size'))

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
