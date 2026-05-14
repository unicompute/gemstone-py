"""Explicit transaction retry helpers for GemStone sessions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from .client import GemStoneConfig, GemStoneSession, TransactionPolicy
from .concurrency import CommitConflictError, ConflictDiagnostics
from .concurrency import commit as _commit

T = TypeVar("T")


@dataclass(frozen=True)
class TransactionRetry:
    """Details for one retryable commit conflict."""

    attempt: int
    attempts: int
    conflict: CommitConflictError

    @property
    def remaining(self) -> int:
        """Return the number of attempts left after this conflict."""
        return max(self.attempts - self.attempt, 0)

    @property
    def will_retry(self) -> bool:
        """Return true when the retry helper will attempt the work again."""
        return self.attempt < self.attempts

    @property
    def exhausted(self) -> bool:
        """Return true when this conflict used the final configured attempt."""
        return not self.will_retry

    def diagnostics(
        self,
        session: GemStoneSession | None = None,
        *,
        include_summaries: bool = True,
    ) -> ConflictDiagnostics:
        """Return structured diagnostics for this retry's commit conflict."""
        return self.conflict.diagnostics(
            session=session,
            include_summaries=include_summaries,
        )

    def format(
        self,
        session: GemStoneSession | None = None,
        *,
        include_summaries: bool = True,
    ) -> str:
        """Return a readable retry report for logging or CLI output."""
        state = "will retry" if self.will_retry else "no attempts remaining"
        lines = [f"Commit conflict on attempt {self.attempt}/{self.attempts} ({state})"]
        lines.extend(
            f"  {line}"
            for line in self.conflict.format(
                session=session,
                include_summaries=include_summaries,
            ).splitlines()
        )
        return "\n".join(lines)

    def to_dict(
        self,
        session: GemStoneSession | None = None,
        *,
        include_summaries: bool = True,
    ) -> dict[str, Any]:
        """Return a JSON-friendly retry report."""
        return {
            "attempt": self.attempt,
            "attempts": self.attempts,
            "remaining": self.remaining,
            "will_retry": self.will_retry,
            "exhausted": self.exhausted,
            "conflict": self.diagnostics(
                session=session,
                include_summaries=include_summaries,
            ).to_dict(),
        }


ConflictListener = Callable[[TransactionRetry], None]
TransactionWork = Callable[[GemStoneSession], T]


def run_transaction_with_retry(
    work: TransactionWork[T],
    *,
    attempts: int = 3,
    session: GemStoneSession | None = None,
    config: GemStoneConfig | None = None,
    session_factory: Callable[..., GemStoneSession] = GemStoneSession,
    on_conflict: ConflictListener | None = None,
    **session_kwargs: Any,
) -> T:
    """
    Run ``work(session)`` in a manual transaction and retry commit conflicts.

    Unlike a context manager, this helper can safely replay the whole work
    function after a conflict. That matters because a retry must reload state
    from a fresh transaction view before reapplying changes.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if session is not None and (config is not None or session_kwargs):
        raise ValueError("Pass either an existing session or session creation options, not both.")

    if session is not None:
        return _run_on_existing_session(
            work,
            session=session,
            attempts=attempts,
            on_conflict=on_conflict,
        )
    return _run_on_owned_sessions(
        work,
        attempts=attempts,
        config=config,
        session_factory=session_factory,
        on_conflict=on_conflict,
        session_kwargs=session_kwargs,
    )


def retrying_transaction(
    work: TransactionWork[T],
    *,
    attempts: int = 3,
    session: GemStoneSession | None = None,
    config: GemStoneConfig | None = None,
    session_factory: Callable[..., GemStoneSession] = GemStoneSession,
    on_conflict: ConflictListener | None = None,
    **session_kwargs: Any,
) -> T:
    """Alias for ``run_transaction_with_retry``."""
    return run_transaction_with_retry(
        work,
        attempts=attempts,
        session=session,
        config=config,
        session_factory=session_factory,
        on_conflict=on_conflict,
        **session_kwargs,
    )


def _run_on_existing_session(
    work: TransactionWork[T],
    *,
    session: GemStoneSession,
    attempts: int,
    on_conflict: ConflictListener | None,
) -> T:
    for attempt in range(1, attempts + 1):
        try:
            result = work(session)
            _commit(session)
            return result
        except CommitConflictError as exc:
            _notify_conflict(on_conflict, attempt, attempts, exc)
            session.abort()
            if attempt == attempts:
                raise
        except Exception:
            session.abort()
            raise
    raise RuntimeError("unreachable transaction retry state")


def _run_on_owned_sessions(
    work: TransactionWork[T],
    *,
    attempts: int,
    config: GemStoneConfig | None,
    session_factory: Callable[..., GemStoneSession],
    on_conflict: ConflictListener | None,
    session_kwargs: dict[str, Any],
) -> T:
    options = dict(session_kwargs)
    if config is not None:
        options["config"] = config
    options["transaction_policy"] = TransactionPolicy.MANUAL
    for attempt in range(1, attempts + 1):
        with session_factory(**options) as session:
            try:
                result = work(session)
                _commit(session)
                return result
            except CommitConflictError as exc:
                _notify_conflict(on_conflict, attempt, attempts, exc)
                session.abort()
                if attempt == attempts:
                    raise
            except Exception:
                session.abort()
                raise
    raise RuntimeError("unreachable transaction retry state")


def _notify_conflict(
    listener: ConflictListener | None,
    attempt: int,
    attempts: int,
    conflict: CommitConflictError,
) -> None:
    if listener is not None:
        listener(TransactionRetry(attempt=attempt, attempts=attempts, conflict=conflict))


__all__ = [
    "ConflictListener",
    "TransactionRetry",
    "TransactionWork",
    "retrying_transaction",
    "run_transaction_with_retry",
]
