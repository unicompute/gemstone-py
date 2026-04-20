"""
ObjectLog — Python wrapper for GemStone's ObjectLogEntry.

GemStone's ObjectLog is a persistent, distributed queue of ObjectLogEntry
objects held by the repository.  Each entry records:
    priority    int  (6=trace, 5=debug, 4=info, 3=warn, 2=error, 1=fatal)
    label       str  (the message you pass in)
    object      str  (a Smalltalk printString of the attached object, if any)
    pid         int  (Gem process ID at log time)
    timestamp   str  (DateAndTime printString from GemStone)

Usage
-----
    from gemstone_py.objectlog import ObjectLog

    log = ObjectLog()

    # Add entries (each call opens its own session and commits)
    log.info("payment processed")
    log.warn("retry attempt", label="retry #3")
    log.error("charge failed")

    # Read entries
    for e in log.entries():
        print(e)                    # ObjectLogEntry(priority=4, label=...)

    for e in log.errors():          # priority == 2
        print(e.label, e.timestamp)

    log.clear()                     # remove all entries

    # Or use a single session for a batch of writes
    from gemstone_py.objectlog import ObjectLog
    import gemstone_py as gemstone

    log = ObjectLog()
    with gemstone.GemStoneSession(lib_path=...) as s:
        log.info("step 1", session=s)
        log.info("step 2", session=s)
        # session commits on __exit__

Priority levels (matching GemStone ObjectLogEntry class side):
    trace = 6
    debug = 5
    info  = 4
    warn  = 3
    error = 2
    fatal = 1
"""

PORTING_STATUS = "plain_gemstone_port"
RUNTIME_REQUIREMENT = "Works on plain GemStone images over GCI"

from dataclasses import dataclass
from typing import Optional

import gemstone_py as gemstone
from ._smalltalk_batch import decode_escaped_field, escaped_field_encoder_source, object_for_oop_expr

# Priority constants — match GemStone ObjectLogEntry class
TRACE = 6
DEBUG = 5
INFO  = 4
WARN  = 3
ERROR = 2
FATAL = 1

_LEVEL_NAMES = {
    TRACE: 'trace',
    DEBUG: 'debug',
    INFO:  'info',
    WARN:  'warn',
    ERROR: 'error',
    FATAL: 'fatal',
}

_SELECTOR_FOR_LEVEL = {
    TRACE: 'trace:object:',
    DEBUG: 'debug:object:',
    INFO:  'info:object:',
    WARN:  'warn:object:',
    ERROR: 'error:object:',
    FATAL: 'fatal:object:',
}


def _session(
    config: gemstone.GemStoneConfig | None = None,
    *,
    transaction_policy: gemstone.TransactionPolicy | str = gemstone.TransactionPolicy.MANUAL,
) -> gemstone.GemStoneSession:
    resolved_config = config or gemstone.GemStoneConfig.from_env()
    return gemstone.GemStoneSession(
        config=resolved_config,
        transaction_policy=transaction_policy,
    )


def _escape(s: str) -> str:
    return s.replace("'", "''")


def _decode_log_field(value: str) -> str:
    return decode_escaped_field(value)


@dataclass
class ObjectLogEntry:
    """
    A single entry read back from GemStone's ObjectLog.

    Fields are fetched by evaluating Smalltalk accessors on the live OOP
    and returned as Python values.
    """
    priority:    int
    label:       str
    object_repr: str          # printString of the attached Smalltalk object
    pid:         int
    timestamp:   str
    index:       int          # position in the log collection (0-based)
    tag:         str = ''     # optional tag string
    tagged:      bool = False # whether the entry has a tag

    @property
    def level_name(self) -> str:
        return _LEVEL_NAMES.get(self.priority, str(self.priority))

    def __str__(self) -> str:
        parts = (
            f"[{self.level_name.upper():5s}] {self.timestamp}  pid={self.pid}"
            f"  {self.label!r}"
        )
        if self.object_repr and self.object_repr != 'nil':
            parts += f"  obj={self.object_repr}"
        if self.tagged and self.tag:
            parts += f"  tag={self.tag!r}"
        return parts

    def __repr__(self) -> str:
        return (
            f"ObjectLogEntry(priority={self.priority}, label={self.label!r},"
            f" pid={self.pid}, timestamp={self.timestamp!r},"
            f" tag={self.tag!r}, tagged={self.tagged})"
        )


def _fetch_log_entries(s: gemstone.GemStoneSession) -> list[ObjectLogEntry]:
    """
    Pull all ObjectLogEntry records from GemStone in a single Smalltalk eval.

    We serialise each entry as a pipe-delimited string to avoid multiple
    round-trips:
        priority|label|objectPrintString|pid|timestamp
    Rows are separated by newlines.
    """
    raw = s.eval(
        "| encode stream log |\n"
        f"{escaped_field_encoder_source('encode')}"
        "log := ObjectLogEntry objectLog.\n"
        "stream := ''.\n"
        "0 to: log size - 1 do: [:i |\n"
        "  | e obj tagStr hasTag |\n"
        "  e := log at: i + 1.\n"
        "  obj    := [ e object printString ] on: Error do: ['nil'].\n"
        "  hasTag := [ e hasTag ] on: Error do: [false].\n"
        "  tagStr := (hasTag and: [e tag notNil])\n"
        "              ifTrue:  [[ e tag printString ] on: Error do: ['']]\n"
        "              ifFalse: [''].\n"
        "  stream := stream,\n"
        "    (encode value: e priority printString), '|',\n"
        "    (encode value: (e label isNil ifTrue: [''] ifFalse: [e label])), '|',\n"
        "    (encode value: obj), '|',\n"
        "    (encode value: e pid printString), '|',\n"
        "    (encode value: e stamp printString), '|',\n"
        "    (hasTag ifTrue: ['1'] ifFalse: ['0']), '|',\n"
        "    (encode value: tagStr), '\\q'\n"
        "].\n"
        "stream"
    )
    entries = []
    for i, line in enumerate(raw.split("\\q")):
        if not line.strip():
            continue
        parts = line.split('|', 6)
        if len(parts) < 5:
            continue
        priority_str = _decode_log_field(parts[0])
        label = _decode_log_field(parts[1])
        obj_repr = _decode_log_field(parts[2])
        pid_str = _decode_log_field(parts[3])
        timestamp = _decode_log_field(parts[4])
        tagged       = len(parts) > 5 and parts[5] == '1'
        tag = _decode_log_field(parts[6]) if len(parts) > 6 else ''
        # Strip surrounding quotes added by printString on Symbol/String
        if tag.startswith("'") and tag.endswith("'"):
            tag = tag[1:-1]
        try:
            priority = int(priority_str)
        except ValueError:
            priority = 0
        try:
            pid = int(pid_str)
        except ValueError:
            pid = 0
        entries.append(ObjectLogEntry(
            priority=priority,
            label=label,
            object_repr=obj_repr,
            pid=pid,
            timestamp=timestamp,
            index=i,
            tag=tag,
            tagged=tagged,
        ))
    return entries


class ObjectLog:
    """
    Python interface to GemStone's ObjectLog.

    All write methods (trace/debug/info/warn/error/fatal) open a session,
    add the entry, and commit, unless you pass an explicit `session=` keyword
    argument — in which case the caller is responsible for committing.

    All read methods (entries/traces/debugs/infos/warns/errors/fatals) open
    a fresh session (read-only abort) so they always see the current state of
    the repository.
    """

    def __init__(self, *, config: gemstone.GemStoneConfig | None = None):
        self._config = config

    # ------------------------------------------------------------------
    # Write methods
    # ------------------------------------------------------------------

    def _add(
        self,
        level: int,
        label: str,
        object_oop: int | None = None,
        session: Optional[gemstone.GemStoneSession] = None,
    ) -> None:
        """
        Add a log entry at `level` with `label`.

        Parameters
        ----------
        label : str
            The message string.
        object_oop : int, optional
            OOP of a GemStone object to attach to the entry. If None, the
            entry's object field is nil.
        session : GemStoneSession, optional
            Use an existing session instead of opening a new one.
        """
        selector = _SELECTOR_FOR_LEVEL[level]
        kw1 = selector.split(':object:')[0]
        escaped_label = _escape(label)

        if object_oop is not None:
            # Attach a live GemStone object: look it up by OOP then pass it
            smalltalk = (
                f"(ObjectLogEntry {kw1}: '{escaped_label}'"
                f"  object: ({object_for_oop_expr(object_oop)})) addToLog."
            )
        else:
            smalltalk = (
                f"(ObjectLogEntry {kw1}: '{escaped_label}' object: nil) addToLog."
            )

        if session is not None:
            session.eval(smalltalk)
        else:
            with _session(
                self._config,
                transaction_policy=gemstone.TransactionPolicy.COMMIT_ON_SUCCESS,
            ) as s:
                s.eval(smalltalk)

    def trace(
        self,
        label: str,
        *,
        object_oop: int | None = None,
        session: Optional[gemstone.GemStoneSession] = None,
    ) -> None:
        self._add(TRACE, label, object_oop, session)

    def debug(
        self,
        label: str,
        *,
        object_oop: int | None = None,
        session: Optional[gemstone.GemStoneSession] = None,
    ) -> None:
        self._add(DEBUG, label, object_oop, session)

    def info(
        self,
        label: str,
        *,
        object_oop: int | None = None,
        session: Optional[gemstone.GemStoneSession] = None,
    ) -> None:
        self._add(INFO, label, object_oop, session)

    def warn(
        self,
        label: str,
        *,
        object_oop: int | None = None,
        session: Optional[gemstone.GemStoneSession] = None,
    ) -> None:
        self._add(WARN, label, object_oop, session)

    def error(
        self,
        label: str,
        *,
        object_oop: int | None = None,
        session: Optional[gemstone.GemStoneSession] = None,
    ) -> None:
        self._add(ERROR, label, object_oop, session)

    def fatal(
        self,
        label: str,
        *,
        object_oop: int | None = None,
        session: Optional[gemstone.GemStoneSession] = None,
    ) -> None:
        self._add(FATAL, label, object_oop, session)

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    def entries(self) -> list[ObjectLogEntry]:
        """Return all ObjectLogEntry records from the repository."""
        with _session(self._config) as s:
            return _fetch_log_entries(s)

    def traces(self)  -> list[ObjectLogEntry]: return [e for e in self.entries() if e.priority == TRACE]
    def debugs(self)  -> list[ObjectLogEntry]: return [e for e in self.entries() if e.priority == DEBUG]
    def infos(self)   -> list[ObjectLogEntry]: return [e for e in self.entries() if e.priority == INFO]
    def warns(self)   -> list[ObjectLogEntry]: return [e for e in self.entries() if e.priority == WARN]
    def errors(self)  -> list[ObjectLogEntry]: return [e for e in self.entries() if e.priority == ERROR]
    def fatals(self)  -> list[ObjectLogEntry]: return [e for e in self.entries() if e.priority == FATAL]

    def to_a(self) -> list[ObjectLogEntry]:
        """
        Return all entries as a list.  Alias for entries().

        Here we always return a fetched snapshot.
        """
        return self.entries()

    def to_ary(self) -> list[ObjectLogEntry]:
        """Alias for to_a()."""
        return self.entries()

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def delete(self, entry: 'ObjectLogEntry', commit: bool = True) -> None:
        """
        Remove a single entry from the ObjectLog by its index.

        Parameters
        ----------
        entry : ObjectLogEntry
            The entry to remove (uses entry.index to locate it).
        commit : bool, optional
            When True (the default), abort before removing and commit
            after. Pass False when
            you are batching multiple deletes inside your own session.

            entries = log.errors()
            log.delete(entries[0])         # remove + commit
            log.delete(entries[1], commit=False)  # caller commits

        GemStone OrderedCollection responds to removeAtIndex: (no
        ifAbsent: variant) — guard with a size check instead.
        """
        with _session(
            self._config,
            transaction_policy=gemstone.TransactionPolicy.COMMIT_ON_SUCCESS,
        ) as s:
            if commit:
                s.abort()
            s.eval(
                f"| log |\n"
                f"log := ObjectLogEntry objectLog.\n"
                f"({entry.index + 1} <= log size) ifTrue: [\n"
                f"  log removeAtIndex: {entry.index + 1} ]."
            )
            # When commit=False the caller's session commits; when True we let
            # GemStoneSession.__exit__ commit on clean exit (default behaviour).

    def clear(self) -> None:
        """Remove all entries from the GemStone ObjectLog and commit."""
        with _session(
            self._config,
            transaction_policy=gemstone.TransactionPolicy.COMMIT_ON_SUCCESS,
        ) as s:
            s.eval("ObjectLogEntry objectLog removeAllSuchThat: [:e | true].")

    def size(self) -> int:
        """Return the number of entries currently in the ObjectLog."""
        with _session(self._config) as s:
            raw = s.eval("ObjectLogEntry objectLog size printString")
            try:
                return int(raw.strip())
            except ValueError:
                return 0

    # ------------------------------------------------------------------
    # Pretty print
    # ------------------------------------------------------------------

    def print_all(self) -> None:
        """Print every log entry to stdout, newest last."""
        for e in self.entries():
            print(e)
