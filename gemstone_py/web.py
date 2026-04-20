"""Flask integration and production-grade session helpers for gemstone-py."""

from __future__ import annotations

import atexit
import queue
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterator, Optional

from .client import GemStoneSession, TransactionPolicy

__all__ = [
    "GemStoneSessionProviderEvent",
    "GemStoneSessionProviderSnapshot",
    "GemStoneSessionProvider",
    "GemStoneSessionPool",
    "GemStoneThreadLocalSessionProvider",
    "close_flask_request_session_provider",
    "current_flask_request_session",
    "flask_request_session_provider",
    "flask_request_session_provider_metrics",
    "flask_request_session_provider_snapshot",
    "finalize_flask_request_session",
    "install_flask_request_session",
    "session_scope",
    "warm_flask_request_session_provider",
]


_FLASK_REQUEST_SESSION_EXTENSION = "gemstone_request_session"
_FLASK_REQUEST_SESSION_ATTR = "_gemstone_request_session"
_FLASK_REQUEST_SESSION_PROVIDER_ATTR = "_gemstone_request_session_provider"
_FLASK_REQUEST_SESSION_POOL_ATTR = _FLASK_REQUEST_SESSION_PROVIDER_ATTR


@dataclass(frozen=True)
class GemStoneSessionProviderSnapshot:
    """Operational counters and capacity information for a session provider."""

    name: str
    provider_type: str
    maxsize: Optional[int]
    max_session_age: Optional[float]
    max_session_uses: Optional[int]
    created: int
    available: int
    in_use: int
    acquire_calls: int
    release_calls: int
    discard_calls: int
    timeout_calls: int
    reset_failures: int
    healthcheck_failures: int
    create_failures: int
    recycle_age_discards: int
    recycle_use_discards: int
    warmup_calls: int
    warmed_sessions: int
    acquire_wait_seconds: float
    close_calls: int
    closed: bool

    def metrics(self) -> dict[str, Any]:
        """Return a JSON-/metrics-friendly dict view of the snapshot."""
        return asdict(self)


@dataclass(frozen=True)
class GemStoneSessionProviderEvent:
    """Structured event emitted by GemStone session providers."""

    name: str
    provider_name: str
    provider_type: str
    session_id: Optional[int]
    reason: Optional[str]
    occurred_at: float
    snapshot: GemStoneSessionProviderSnapshot


class GemStoneSessionProvider:
    """
    Interface for components that vend GemStone sessions to callers.

    Providers may implement pooling, thread-local reuse, or simple
    create-and-destroy behavior as long as they honour `acquire()`,
    `release()`, and `close()`.
    """

    def acquire(self, timeout: Optional[float] = None) -> GemStoneSession:
        raise NotImplementedError

    def release(
        self,
        session: Optional[GemStoneSession],
        *,
        discard: bool = False,
        clean: bool = False,
    ) -> None:
        raise NotImplementedError

    def close(self) -> None:
        return None

    def snapshot(self) -> GemStoneSessionProviderSnapshot:
        raise NotImplementedError

    def warm(self, count: Optional[int] = None) -> int:
        del count
        return 0

    def _initialize_provider(
        self,
        *,
        name: Optional[str] = None,
        session_factory: Callable[..., GemStoneSession] = GemStoneSession,
        session_healthcheck: Optional[Callable[[GemStoneSession], bool]] = None,
        acquire_timeout: Optional[float] = None,
        max_session_age: Optional[float] = None,
        max_session_uses: Optional[int] = None,
        metrics_exporter: Optional[Callable[[GemStoneSessionProviderSnapshot], None]] = None,
        event_listener: Optional[Callable[[GemStoneSessionProviderEvent], None]] = None,
        logger: Any = None,
        **session_kwargs: Any,
    ) -> None:
        if max_session_age is not None and max_session_age <= 0:
            raise ValueError("GemStone session max_session_age must be > 0.")
        if max_session_uses is not None and max_session_uses < 1:
            raise ValueError("GemStone session max_session_uses must be >= 1.")
        self._name = name or type(self).__name__
        self._session_factory: Callable[..., GemStoneSession] = session_factory
        self._session_kwargs = dict(session_kwargs)
        self._session_healthcheck = session_healthcheck
        self._acquire_timeout = acquire_timeout
        self._max_session_age = max_session_age
        self._max_session_uses = max_session_uses
        self._metrics_exporter = metrics_exporter
        self._event_listener = event_listener
        self._logger = logger
        self._stats_lock = threading.Lock()
        self._acquire_calls = 0
        self._release_calls = 0
        self._discard_calls = 0
        self._timeout_calls = 0
        self._reset_failures = 0
        self._healthcheck_failures = 0
        self._create_failures = 0
        self._recycle_age_discards = 0
        self._recycle_use_discards = 0
        self._warmup_calls = 0
        self._warmed_sessions = 0
        self._acquire_wait_seconds = 0.0
        self._close_calls = 0

    def _record_stat(self, attr_name: str, delta: int = 1) -> None:
        with self._stats_lock:
            setattr(self, attr_name, getattr(self, attr_name) + delta)

    def _record_float_stat(self, attr_name: str, delta: float) -> None:
        with self._stats_lock:
            setattr(self, attr_name, getattr(self, attr_name) + float(delta))

    def _record_acquire_wait(self, started_at: float) -> None:
        self._record_float_stat("_acquire_wait_seconds", max(time.monotonic() - started_at, 0.0))

    @staticmethod
    def _session_created_at(session: GemStoneSession) -> float:
        return float(getattr(session, "_gemstone_provider_created_at", time.monotonic()))

    @staticmethod
    def _session_use_count(session: GemStoneSession) -> int:
        return int(getattr(session, "_gemstone_provider_use_count", 0))

    def _mark_session_created(self, session: GemStoneSession) -> None:
        setattr(session, "_gemstone_provider_created_at", time.monotonic())
        setattr(session, "_gemstone_provider_use_count", 0)

    def _mark_session_checked_out(self, session: GemStoneSession) -> None:
        setattr(session, "_gemstone_provider_use_count", self._session_use_count(session) + 1)

    def _session_recycle_reason(self, session: GemStoneSession) -> Optional[str]:
        if self._max_session_age is not None:
            if time.monotonic() - self._session_created_at(session) >= self._max_session_age:
                return "max_age"
        if self._max_session_uses is not None:
            if self._session_use_count(session) >= self._max_session_uses:
                return "max_uses"
        return None

    def _emit_observation(
        self,
        event_name: str,
        *,
        session: Optional[GemStoneSession] = None,
        reason: Optional[str] = None,
    ) -> None:
        snapshot = self.snapshot()
        if self._metrics_exporter is not None:
            try:
                self._metrics_exporter(snapshot)
            except Exception:
                pass
        if self._event_listener is not None:
            event = GemStoneSessionProviderEvent(
                name=event_name,
                provider_name=snapshot.name,
                provider_type=snapshot.provider_type,
                session_id=id(session) if session is not None else None,
                reason=reason,
                occurred_at=time.time(),
                snapshot=snapshot,
            )
            try:
                self._event_listener(event)
            except Exception:
                pass
        if self._logger is not None:
            try:
                self._logger.info(
                    "GemStone session provider event",
                    extra={
                        "gemstone_provider_event": event_name,
                        "gemstone_provider_name": snapshot.name,
                        "gemstone_provider_type": snapshot.provider_type,
                        "gemstone_provider_reason": reason,
                        "gemstone_provider_session_id": (
                            id(session) if session is not None else None
                        ),
                    },
                )
            except Exception:
                pass

    def _create_session(self) -> GemStoneSession:
        options = dict(self._session_kwargs)
        options["transaction_policy"] = TransactionPolicy.MANUAL
        try:
            session = self._session_factory(**options)
            session.login()
            self._mark_session_created(session)
            return session
        except Exception:
            self._record_stat("_create_failures")
            raise

    def _reset_session(self, session: GemStoneSession) -> bool:
        try:
            session.abort()
            return True
        except Exception:
            self._record_stat("_reset_failures")
            self._record_stat("_healthcheck_failures")
            return False

    def _session_is_healthy(self, session: GemStoneSession) -> bool:
        if getattr(session, "_logged_in", True) is False:
            self._record_stat("_healthcheck_failures")
            return False
        if self._session_healthcheck is None:
            return True
        try:
            healthy = bool(self._session_healthcheck(session))
        except Exception:
            healthy = False
        if not healthy:
            self._record_stat("_healthcheck_failures")
        return healthy

    def _prepare_session_for_checkout(
        self,
        session: GemStoneSession,
    ) -> tuple[bool, Optional[str]]:
        if not self._session_is_healthy(session):
            return False, "unhealthy"
        recycle_reason = self._session_recycle_reason(session)
        if recycle_reason is not None:
            return False, recycle_reason
        self._mark_session_checked_out(session)
        return True, None

    def _provider_snapshot(
        self,
        *,
        maxsize: Optional[int],
        created: int,
        available: int,
        closed: bool,
    ) -> GemStoneSessionProviderSnapshot:
        with self._stats_lock:
            return GemStoneSessionProviderSnapshot(
                name=self._name,
                provider_type=type(self).__name__,
                maxsize=maxsize,
                max_session_age=self._max_session_age,
                max_session_uses=self._max_session_uses,
                created=created,
                available=available,
                in_use=max(created - available, 0),
                acquire_calls=self._acquire_calls,
                release_calls=self._release_calls,
                discard_calls=self._discard_calls,
                timeout_calls=self._timeout_calls,
                reset_failures=self._reset_failures,
                healthcheck_failures=self._healthcheck_failures,
                create_failures=self._create_failures,
                recycle_age_discards=self._recycle_age_discards,
                recycle_use_discards=self._recycle_use_discards,
                warmup_calls=self._warmup_calls,
                warmed_sessions=self._warmed_sessions,
                acquire_wait_seconds=self._acquire_wait_seconds,
                close_calls=self._close_calls,
                closed=closed,
            )


class GemStoneSessionPool(GemStoneSessionProvider):
    """
    Thread-safe pool of logged-in GemStone sessions for web-style workloads.

    Sessions are created lazily up to `maxsize`. Returned sessions are reset
    before being reused unless the caller tells the pool the session is already
    in a clean post-commit/post-abort state.
    """

    def __init__(
        self,
        *,
        maxsize: int = 4,
        session_factory: Callable[..., GemStoneSession] = GemStoneSession,
        session_healthcheck: Optional[Callable[[GemStoneSession], bool]] = None,
        acquire_timeout: Optional[float] = None,
        max_session_age: Optional[float] = None,
        max_session_uses: Optional[int] = None,
        metrics_exporter: Optional[Callable[[GemStoneSessionProviderSnapshot], None]] = None,
        event_listener: Optional[Callable[[GemStoneSessionProviderEvent], None]] = None,
        logger: Any = None,
        name: Optional[str] = None,
        **session_kwargs: Any,
    ) -> None:
        if maxsize < 1:
            raise ValueError("GemStoneSessionPool maxsize must be at least 1.")
        self._maxsize = maxsize
        self._initialize_provider(
            name=name,
            session_factory=session_factory,
            session_healthcheck=session_healthcheck,
            acquire_timeout=acquire_timeout,
            max_session_age=max_session_age,
            max_session_uses=max_session_uses,
            metrics_exporter=metrics_exporter,
            event_listener=event_listener,
            logger=logger,
            **session_kwargs,
        )
        self._available: queue.LifoQueue[GemStoneSession] = queue.LifoQueue(maxsize)
        self._lock = threading.Lock()
        self._created = 0
        self._closed = False

    @property
    def maxsize(self) -> int:
        return self._maxsize

    @property
    def created(self) -> int:
        with self._lock:
            return self._created

    @property
    def available(self) -> int:
        return self._available.qsize()

    def acquire(self, timeout: Optional[float] = None) -> GemStoneSession:
        started_at = time.monotonic()
        self._record_stat("_acquire_calls")
        effective_timeout = self._acquire_timeout if timeout is None else timeout
        deadline = None if effective_timeout is None else time.monotonic() + effective_timeout

        with self._lock:
            if self._closed:
                raise RuntimeError("GemStoneSessionPool is closed.")

        while True:
            try:
                session = self._available.get_nowait()
                ready, reason = self._prepare_session_for_checkout(session)
                if ready:
                    self._record_acquire_wait(started_at)
                    self._emit_observation("session_acquired", session=session)
                    return session
                self._discard_session(session, reason=reason)
                continue
            except queue.Empty:
                pass

            with self._lock:
                if self._closed:
                    raise RuntimeError("GemStoneSessionPool is closed.")
                if self._created < self._maxsize:
                    self._created += 1
                    should_create = True
                else:
                    should_create = False

            if should_create:
                try:
                    session = self._create_session()
                except Exception:
                    with self._lock:
                        self._created -= 1
                    raise
                ready, reason = self._prepare_session_for_checkout(session)
                if ready:
                    self._record_acquire_wait(started_at)
                    self._emit_observation("session_acquired", session=session)
                    return session
                self._discard_session(session, reason=reason)
                continue

            remaining = None
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._record_stat("_timeout_calls")
                    self._emit_observation("acquire_timeout", reason="timeout")
                    raise TimeoutError("Timed out waiting for a GemStone session from the pool.")
            try:
                session = self._available.get(timeout=remaining)
            except queue.Empty as exc:
                self._record_stat("_timeout_calls")
                self._emit_observation("acquire_timeout", reason="timeout")
                raise TimeoutError(
                    "Timed out waiting for a GemStone session from the pool."
                ) from exc
            ready, reason = self._prepare_session_for_checkout(session)
            if ready:
                self._record_acquire_wait(started_at)
                self._emit_observation("session_acquired", session=session)
                return session
            self._discard_session(session, reason=reason)

    def release(
        self,
        session: Optional[GemStoneSession],
        *,
        discard: bool = False,
        clean: bool = False,
    ) -> None:
        if session is None:
            return
        self._record_stat("_release_calls")
        if discard or self._closed:
            self._discard_session(
                session,
                reason="discard_requested" if discard else "provider_closed",
            )
            return
        if not clean and not self._reset_session(session):
            self._discard_session(session, reason="reset_failed")
            return
        if not self._session_is_healthy(session):
            self._discard_session(session, reason="unhealthy")
            return
        recycle_reason = self._session_recycle_reason(session)
        if recycle_reason is not None:
            self._discard_session(session, reason=recycle_reason)
            return
        try:
            self._available.put_nowait(session)
            self._emit_observation("session_released", session=session)
        except queue.Full:
            self._discard_session(session, reason="queue_full")

    def close(self) -> None:
        self._record_stat("_close_calls")
        with self._lock:
            self._closed = True
        drained = []
        while True:
            try:
                drained.append(self._available.get_nowait())
            except queue.Empty:
                break
        for session in drained:
            self._discard_session(session, reason="provider_closed")
        self._emit_observation("provider_closed")

    def warm(self, count: Optional[int] = None) -> int:
        self._record_stat("_warmup_calls")
        target = self._maxsize if count is None else min(max(int(count), 0), self._maxsize)
        warmed = 0
        while warmed < target:
            with self._lock:
                if self._closed:
                    raise RuntimeError("GemStoneSessionPool is closed.")
                if self._created >= self._maxsize:
                    break
                self._created += 1
            try:
                session = self._create_session()
            except Exception:
                with self._lock:
                    self._created -= 1
                raise
            if not self._session_is_healthy(session):
                self._discard_session(session, reason="unhealthy")
                continue
            try:
                self._available.put_nowait(session)
            except queue.Full:
                self._discard_session(session, reason="queue_full")
                break
            warmed += 1
            self._record_stat("_warmed_sessions")
            self._emit_observation("session_warmed", session=session)
        return warmed

    @contextmanager
    def lease(self) -> Iterator[GemStoneSession]:
        session = self.acquire()
        discard = False
        clean = False
        try:
            yield session
        except Exception:
            try:
                session.abort()
                clean = True
            except Exception:
                discard = True
            raise
        finally:
            self.release(session, discard=discard, clean=clean)

    def _create_session(self) -> GemStoneSession:
        return super()._create_session()

    def _discard_session(self, session: GemStoneSession, reason: Optional[str] = None) -> None:
        self._record_stat("_discard_calls")
        if reason == "max_age":
            self._record_stat("_recycle_age_discards")
        elif reason == "max_uses":
            self._record_stat("_recycle_use_discards")
        try:
            session.logout()
        except Exception:
            pass
        finally:
            with self._lock:
                if self._created > 0:
                    self._created -= 1
        self._emit_observation("session_discarded", session=session, reason=reason)

    def snapshot(self) -> GemStoneSessionProviderSnapshot:
        with self._lock:
            created = self._created
            closed = self._closed
        return self._provider_snapshot(
            maxsize=self._maxsize,
            created=created,
            available=self._available.qsize(),
            closed=closed,
        )


class GemStoneThreadLocalSessionProvider(GemStoneSessionProvider):
    """
    Reuse one logged-in GemStone session per thread.

    This is useful for threaded workers that do not want a central pool but do
    want to avoid repeatedly logging in for each request or task.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[..., GemStoneSession] = GemStoneSession,
        session_healthcheck: Optional[Callable[[GemStoneSession], bool]] = None,
        max_session_age: Optional[float] = None,
        max_session_uses: Optional[int] = None,
        metrics_exporter: Optional[Callable[[GemStoneSessionProviderSnapshot], None]] = None,
        event_listener: Optional[Callable[[GemStoneSessionProviderEvent], None]] = None,
        logger: Any = None,
        name: Optional[str] = None,
        **session_kwargs: Any,
    ) -> None:
        self._initialize_provider(
            name=name,
            session_factory=session_factory,
            session_healthcheck=session_healthcheck,
            max_session_age=max_session_age,
            max_session_uses=max_session_uses,
            metrics_exporter=metrics_exporter,
            event_listener=event_listener,
            logger=logger,
            **session_kwargs,
        )
        self._local = threading.local()
        self._lock = threading.Lock()
        self._sessions_by_thread: dict[int, GemStoneSession] = {}
        self._closed = False

    def acquire(self, timeout: Optional[float] = None) -> GemStoneSession:
        del timeout
        self._record_stat("_acquire_calls")
        with self._lock:
            if self._closed:
                raise RuntimeError("GemStoneThreadLocalSessionProvider is closed.")
        session: Optional[GemStoneSession] = getattr(self._local, "session", None)
        if session is not None:
            ready, reason = self._prepare_session_for_checkout(session)
            if ready:
                self._emit_observation("session_acquired", session=session)
                return session
            self._discard_current_session(session, reason=reason)
            session = None
        if session is not None:
            return session
        session = self._create_session()
        ready, reason = self._prepare_session_for_checkout(session)
        if not ready:
            self._discard_current_session(session, reason=reason)
            raise RuntimeError("GemStoneThreadLocalSessionProvider created an unhealthy session.")
        ident = threading.get_ident()
        with self._lock:
            if self._closed:
                try:
                    session.logout()
                finally:
                    raise RuntimeError("GemStoneThreadLocalSessionProvider is closed.")
            self._sessions_by_thread[ident] = session
        self._local.session = session
        self._emit_observation("session_acquired", session=session)
        return session

    def release(
        self,
        session: Optional[GemStoneSession],
        *,
        discard: bool = False,
        clean: bool = False,
    ) -> None:
        if session is None:
            return
        self._record_stat("_release_calls")
        if discard or self._closed:
            self._discard_current_session(
                session,
                reason="discard_requested" if discard else "provider_closed",
            )
            return
        if not clean and not self._reset_session(session):
            self._discard_current_session(session, reason="reset_failed")
            return
        if not self._session_is_healthy(session):
            self._discard_current_session(session, reason="unhealthy")
            return
        recycle_reason = self._session_recycle_reason(session)
        if recycle_reason is not None:
            self._discard_current_session(session, reason=recycle_reason)
            return
        self._emit_observation("session_released", session=session)

    def close(self) -> None:
        self._record_stat("_close_calls")
        with self._lock:
            self._closed = True
            sessions = list(self._sessions_by_thread.values())
            self._sessions_by_thread.clear()
        for session in sessions:
            try:
                session.logout()
            except Exception:
                pass
        self._emit_observation("provider_closed")

    def _discard_current_session(
        self,
        session: GemStoneSession,
        reason: Optional[str] = None,
    ) -> None:
        ident = threading.get_ident()
        self._record_stat("_discard_calls")
        if reason == "max_age":
            self._record_stat("_recycle_age_discards")
        elif reason == "max_uses":
            self._record_stat("_recycle_use_discards")
        try:
            session.logout()
        except Exception:
            pass
        finally:
            with self._lock:
                self._sessions_by_thread.pop(ident, None)
            if getattr(self._local, "session", None) is session:
                self._local.session = None
        self._emit_observation("session_discarded", session=session, reason=reason)

    def warm(self, count: Optional[int] = None) -> int:
        del count
        self._record_stat("_warmup_calls")
        return 0

    def snapshot(self) -> GemStoneSessionProviderSnapshot:
        with self._lock:
            created = len(self._sessions_by_thread)
            closed = self._closed
        return self._provider_snapshot(
            maxsize=None,
            created=created,
            available=0,
            closed=closed,
        )


def _flask_request_state() -> tuple[Any | None, Any | None]:
    try:
        from flask import current_app, g, has_request_context
    except ImportError:
        return None, None
    if not has_request_context():
        return None, None
    return current_app._get_current_object(), g


def current_flask_request_session() -> Optional[GemStoneSession]:
    """Return the current Flask request's shared GemStone session, if any."""
    _app, flask_g = _flask_request_state()
    if flask_g is None:
        return None
    return getattr(flask_g, _FLASK_REQUEST_SESSION_ATTR, None)


def flask_request_session_provider(app: Any | None = None) -> Optional[GemStoneSessionProvider]:
    """Return the configured Flask request-session provider, if any."""
    if app is None:
        app, _flask_g = _flask_request_state()
    extension = (
        getattr(app, "extensions", {}).get(_FLASK_REQUEST_SESSION_EXTENSION, {})
        if app
        else {}
    )
    return extension.get("session_provider") or extension.get("session_pool")


def flask_request_session_provider_snapshot(
    app: Any | None = None,
) -> Optional[GemStoneSessionProviderSnapshot]:
    """Return an operational snapshot for the configured Flask provider."""
    provider = flask_request_session_provider(app)
    if provider is None:
        return None
    return provider.snapshot()


def flask_request_session_provider_metrics(app: Any | None = None) -> Optional[dict[str, Any]]:
    """Return a metrics-friendly dict for the configured Flask provider."""
    snapshot = flask_request_session_provider_snapshot(app)
    if snapshot is None:
        return None
    return snapshot.metrics()


def warm_flask_request_session_provider(app: Any | None = None, count: Optional[int] = None) -> int:
    """Warm the configured Flask provider, returning the number of sessions prepared."""
    provider = flask_request_session_provider(app)
    if provider is None:
        return 0
    return provider.warm(count)


def close_flask_request_session_provider(app: Any | None = None) -> None:
    """Close and detach the configured Flask request-session provider."""
    provider = flask_request_session_provider(app)
    if provider is None:
        return
    provider.close()
    if app is None:
        app, _flask_g = _flask_request_state()
    if app is None:
        return
    extension = app.extensions.get(_FLASK_REQUEST_SESSION_EXTENSION)
    if extension is None:
        return
    extension["session_provider"] = None
    extension["session_pool"] = None


def _resolve_session_provider(
    *,
    session_provider: Optional[GemStoneSessionProvider] = None,
    session_pool: Optional[GemStoneSessionProvider] = None,
    pool_size: Optional[int] = None,
    thread_local: bool = False,
    provider_name: Optional[str] = None,
    acquire_timeout: Optional[float] = None,
    session_healthcheck: Optional[Callable[[GemStoneSession], bool]] = None,
    max_session_age: Optional[float] = None,
    max_session_uses: Optional[int] = None,
    metrics_exporter: Optional[Callable[[GemStoneSessionProviderSnapshot], None]] = None,
    event_listener: Optional[Callable[[GemStoneSessionProviderEvent], None]] = None,
    logger: Any = None,
    **kwargs: Any,
) -> Optional[GemStoneSessionProvider]:
    if session_provider is not None and session_pool is not None:
        raise ValueError("Pass either session_provider or session_pool, not both.")
    provider = session_provider or session_pool
    if provider is not None and (pool_size is not None or thread_local):
        raise ValueError(
            "Do not combine an explicit session provider with pool_size or thread_local."
        )
    if pool_size is not None and thread_local:
        raise ValueError("Pass either pool_size or thread_local, not both.")
    if provider is not None:
        return provider
    if pool_size is not None:
        return GemStoneSessionPool(
            maxsize=pool_size,
            name=provider_name,
            acquire_timeout=acquire_timeout,
            session_healthcheck=session_healthcheck,
            max_session_age=max_session_age,
            max_session_uses=max_session_uses,
            metrics_exporter=metrics_exporter,
            event_listener=event_listener,
            logger=logger,
            **kwargs,
        )
    if thread_local:
        return GemStoneThreadLocalSessionProvider(
            name=provider_name,
            session_healthcheck=session_healthcheck,
            max_session_age=max_session_age,
            max_session_uses=max_session_uses,
            metrics_exporter=metrics_exporter,
            event_listener=event_listener,
            logger=logger,
            **kwargs,
        )
    return None


def _get_or_create_flask_request_session(**kwargs: Any) -> Optional[GemStoneSession]:
    app, flask_g = _flask_request_state()
    if app is None or flask_g is None:
        return None
    config = app.extensions.get(_FLASK_REQUEST_SESSION_EXTENSION)
    if config is None:
        return None
    session: Optional[GemStoneSession] = getattr(
        flask_g,
        _FLASK_REQUEST_SESSION_ATTR,
        None,
    )
    if session is not None:
        return session

    session_provider = config.get("session_provider") or config.get("session_pool")
    if session_provider is not None:
        session = session_provider.acquire()
        setattr(flask_g, _FLASK_REQUEST_SESSION_PROVIDER_ATTR, session_provider)
    else:
        options = dict(config.get("kwargs", {}))
        options.update(kwargs)
        options["transaction_policy"] = TransactionPolicy.MANUAL
        session = GemStoneSession(**options)
        session.login()
    setattr(flask_g, _FLASK_REQUEST_SESSION_ATTR, session)
    return session


def finalize_flask_request_session(exc: Optional[BaseException] = None) -> None:
    """
    Commit or abort the current Flask request's shared GemStone session.

    Successful requests commit; failing requests abort. Sessions created from a
    pool are returned to it. Ad-hoc request sessions are logged out.
    """
    _app, flask_g = _flask_request_state()
    if flask_g is None:
        return
    session = getattr(flask_g, _FLASK_REQUEST_SESSION_ATTR, None)
    if session is None:
        return

    session_provider = (
        getattr(flask_g, _FLASK_REQUEST_SESSION_PROVIDER_ATTR, None)
        or getattr(flask_g, _FLASK_REQUEST_SESSION_POOL_ATTR, None)
    )
    discard = False
    clean = False
    try:
        if exc is None:
            try:
                session.commit()
                clean = True
            except Exception:
                try:
                    session.abort()
                    clean = True
                except Exception:
                    discard = True
                raise
        else:
            try:
                session.abort()
                clean = True
            except Exception:
                discard = True
    finally:
        try:
            if session_provider is not None:
                session_provider.release(session, discard=discard, clean=clean)
            else:
                session.logout()
        finally:
            for attr_name in (
                _FLASK_REQUEST_SESSION_ATTR,
                _FLASK_REQUEST_SESSION_PROVIDER_ATTR,
                _FLASK_REQUEST_SESSION_POOL_ATTR,
            ):
                try:
                    delattr(flask_g, attr_name)
                except AttributeError:
                    pass


def install_flask_request_session(
    app: Any,
    *,
    session_provider: Optional[GemStoneSessionProvider] = None,
    session_pool: Optional[GemStoneSessionProvider] = None,
    pool_size: Optional[int] = None,
    thread_local: bool = False,
    provider_name: Optional[str] = None,
    acquire_timeout: Optional[float] = None,
    session_healthcheck: Optional[Callable[[GemStoneSession], bool]] = None,
    max_session_age: Optional[float] = None,
    max_session_uses: Optional[int] = None,
    metrics_exporter: Optional[Callable[[GemStoneSessionProviderSnapshot], None]] = None,
    event_listener: Optional[Callable[[GemStoneSessionProviderEvent], None]] = None,
    logger: Any = None,
    warmup_sessions: int = 0,
    close_at_exit: bool = False,
    close_on_after_serving: bool = False,
    **kwargs: Any,
) -> Any:
    """
    Register lazy request-scoped GemStone session handling for a Flask app.

    By default each request creates and tears down its own session lazily. Pass
    a `session_provider=` explicitly, `pool_size=` for pooled sessions, or
    `thread_local=True` for one session per worker thread.
    """
    provider = _resolve_session_provider(
        session_provider=session_provider,
        session_pool=session_pool,
        pool_size=pool_size,
        thread_local=thread_local,
        provider_name=provider_name,
        acquire_timeout=acquire_timeout,
        session_healthcheck=session_healthcheck,
        max_session_age=max_session_age,
        max_session_uses=max_session_uses,
        metrics_exporter=metrics_exporter,
        event_listener=event_listener,
        logger=logger,
        **kwargs,
    )

    config = app.extensions.setdefault(_FLASK_REQUEST_SESSION_EXTENSION, {})
    config["kwargs"] = dict(kwargs)
    config["session_provider"] = provider
    config["session_pool"] = provider
    config["close_at_exit"] = close_at_exit
    config["close_on_after_serving"] = close_on_after_serving
    config["warmup_sessions"] = warmup_sessions
    if config.get("installed"):
        return app
    config["installed"] = True
    if provider is not None and close_at_exit:
        atexit.register(close_flask_request_session_provider, app)
    if provider is not None and warmup_sessions and hasattr(app, "before_serving"):
        @app.before_serving
        def _warm_request_session_provider() -> None:
            warm_flask_request_session_provider(app, warmup_sessions)
    if provider is not None and close_on_after_serving and hasattr(app, "after_serving"):
        @app.after_serving
        def _close_request_session_provider() -> None:
            close_flask_request_session_provider(app)

    @app.after_request
    def _commit_request_session(response: Any) -> Any:
        if not getattr(app.session_interface, "_gemstone_request_session_finalizes", False):
            finalize_flask_request_session()
        return response

    @app.teardown_request
    def _cleanup_request_session(exc: BaseException | None) -> None:
        if exc is not None:
            finalize_flask_request_session(exc)

    return app


@contextmanager
def session_scope(
    session: Optional[GemStoneSession] = None,
    *,
    session_provider: Optional[GemStoneSessionProvider] = None,
    session_pool: Optional[GemStoneSessionPool] = None,
    transaction_policy: TransactionPolicy | str = TransactionPolicy.COMMIT_ON_SUCCESS,
    provider_name: Optional[str] = None,
    acquire_timeout: Optional[float] = None,
    session_healthcheck: Optional[Callable[[GemStoneSession], bool]] = None,
    max_session_age: Optional[float] = None,
    max_session_uses: Optional[int] = None,
    metrics_exporter: Optional[Callable[[GemStoneSessionProviderSnapshot], None]] = None,
    event_listener: Optional[Callable[[GemStoneSessionProviderEvent], None]] = None,
    logger: Any = None,
    **kwargs: Any,
) -> Iterator[GemStoneSession]:
    """
    Yield a usable GemStone session.

    Explicit sessions are reused as-is. Request-scoped Flask sessions take
    precedence. Pooled sessions are finalized and returned to the pool when the
    context exits.
    """
    if session is not None:
        yield session
        return

    request_session = _get_or_create_flask_request_session(**kwargs)
    if request_session is not None:
        yield request_session
        return

    policy = TransactionPolicy.coerce(transaction_policy)
    provider = _resolve_session_provider(
        session_provider=session_provider,
        session_pool=session_pool,
        provider_name=provider_name,
        acquire_timeout=acquire_timeout,
        session_healthcheck=session_healthcheck,
        max_session_age=max_session_age,
        max_session_uses=max_session_uses,
        metrics_exporter=metrics_exporter,
        event_listener=event_listener,
        logger=logger,
        **kwargs,
    )
    if provider is not None:
        pooled_session = provider.acquire()
        discard = False
        clean = False
        try:
            yield pooled_session
            if policy is TransactionPolicy.COMMIT_ON_SUCCESS:
                pooled_session.commit()
                clean = True
            elif policy is TransactionPolicy.ABORT_ON_EXIT:
                pooled_session.abort()
                clean = True
        except Exception:
            try:
                pooled_session.abort()
                clean = True
            except Exception:
                discard = True
            raise
        finally:
            provider.release(pooled_session, discard=discard, clean=clean)
        return

    with GemStoneSession(transaction_policy=policy, **kwargs) as new_session:
        yield new_session
