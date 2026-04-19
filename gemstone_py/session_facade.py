"""
Session-bound GemStone facade helpers.

This module groups the most common persistent-root and transaction helpers
behind one session-bound object for callers that prefer a compact API:

    from gemstone_py.session_facade import GemStoneSessionFacade

    with gemstone.GemStoneSession() as session:
        facade = GemStoneSessionFacade(session)
        facade["answer"] = 42
        facade.commit_transaction()

The same low-level helpers remain available directly through `PersistentRoot`,
`concurrency.commit()`, and `GemStoneSession.abort()`.
"""

from __future__ import annotations

from typing import Any, cast

import gemstone_py as _gs
from gemstone_py.concurrency import (
    CommitConflictError,
)
from gemstone_py.concurrency import (
    commit as _commit,
)
from gemstone_py.concurrency import (
    commit_and_release_locks as _commit_and_release_locks,
)
from gemstone_py.concurrency import (
    session_id as _session_id,
)
from gemstone_py.concurrency import (
    transaction_level as _transaction_level,
)
from gemstone_py.persistent_root import PersistentRoot

PORTING_STATUS = "plain_gemstone_port"
RUNTIME_REQUIREMENT = "Works on plain GemStone images over GCI"


def persistent_root(session: _gs.GemStoneSession) -> PersistentRoot:
    """Return the persistent root wrapper for `session`."""
    return PersistentRoot(session)


def globals_dictionary(session: _gs.GemStoneSession) -> PersistentRoot:
    """Return the Globals SymbolDictionary wrapper for `session`."""
    return PersistentRoot.globals(session)


def published_dictionary(session: _gs.GemStoneSession) -> PersistentRoot:
    """Return the Published SymbolDictionary wrapper for `session`."""
    return PersistentRoot.published(session)


def session_methods_dictionary(session: _gs.GemStoneSession) -> PersistentRoot:
    """Return the SessionMethods SymbolDictionary wrapper for `session`."""
    return PersistentRoot.session_methods(session)


def commit_transaction(session: _gs.GemStoneSession) -> bool:
    """Commit the current transaction."""
    _commit(session)
    return True


def commit(session: _gs.GemStoneSession) -> bool:
    """Alias for commit_transaction()."""
    return commit_transaction(session)


def abort_transaction(session: _gs.GemStoneSession) -> bool:
    """Abort the current transaction and refresh the session view."""
    session.abort()
    return True


def abort(session: _gs.GemStoneSession) -> bool:
    """Alias for abort_transaction()."""
    return abort_transaction(session)


def refresh_view(session: _gs.GemStoneSession) -> bool:
    """Discard local changes and refresh the session view."""
    return abort_transaction(session)


def commit_and_release_locks(session: _gs.GemStoneSession) -> bool:
    """Commit and release all session locks."""
    return bool(_commit_and_release_locks(session))


def current_transaction_level(session: _gs.GemStoneSession) -> int:
    """Return the current transaction nesting level."""
    return int(_transaction_level(session))


class GemStoneSessionFacade:
    """
    Session-bound facade for persistent-root and transaction helpers.

    Exposes `persistent_root` plus the commit / abort helpers as one object.
    """

    def __init__(self, session: _gs.GemStoneSession):
        object.__setattr__(self, "_session", session)
        object.__setattr__(self, "persistent_root", PersistentRoot(session))

    @property
    def session(self) -> _gs.GemStoneSession:
        return cast(_gs.GemStoneSession, object.__getattribute__(self, "_session"))

    def root(self) -> PersistentRoot:
        return cast(PersistentRoot, object.__getattribute__(self, "persistent_root"))

    def __getitem__(self, key: str) -> Any:
        return self.root()[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.root()[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self.root()

    def commit_transaction(self) -> bool:
        return commit_transaction(self.session)

    def commit(self) -> bool:
        return self.commit_transaction()

    def abort_transaction(self) -> bool:
        return abort_transaction(self.session)

    def abort(self) -> bool:
        return self.abort_transaction()

    def refresh_view(self) -> bool:
        return refresh_view(self.session)

    def commit_and_release_locks(self) -> bool:
        return commit_and_release_locks(self.session)

    def current_transaction_level(self) -> int:
        return current_transaction_level(self.session)

    def transaction_level(self) -> int:
        return self.current_transaction_level()

    def globals_dictionary(self) -> PersistentRoot:
        return globals_dictionary(self.session)

    def published_dictionary(self) -> PersistentRoot:
        return published_dictionary(self.session)

    def session_methods_dictionary(self) -> PersistentRoot:
        return session_methods_dictionary(self.session)

    def __repr__(self) -> str:
        try:
            sid_text = str(_session_id(self.session))
        except Exception:
            sid_text = "unlogged"
        return f"<GemStoneSessionFacade session={sid_text}>"


__all__ = [
    "CommitConflictError",
    "GemStoneSessionFacade",
    "abort",
    "abort_transaction",
    "commit",
    "commit_and_release_locks",
    "commit_transaction",
    "current_transaction_level",
    "globals_dictionary",
    "persistent_root",
    "published_dictionary",
    "refresh_view",
    "session_methods_dictionary",
]
