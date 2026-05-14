"""Production session provider implementations for gemstone-py."""

from __future__ import annotations

import queue
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterator, Optional

from .client import GemStoneSession, TransactionPolicy
from .observability import NULL_METRICS, NULL_TRACER, MetricsCollector, Tracer

__all__ = [
    "GemStoneSessionProviderEvent",
    "GemStoneSessionProviderSnapshot",
    "GemStoneSessionPoolStats",
    "GemStoneSessionProvider",
    "GemStoneSessionPool",
    "GemStoneThreadLocalSessionProvider",
]


@dataclass(frozen=True)
class GemStoneSessionProviderSnapshot:
    """Operational counters and capacity information for a session provider."""

    name: str
    provider_type: str
    maxsize: Optional[int]
    minsize: Optional[int]
    max_session_age: Optional[float]
    max_session_uses: Optional[int]
    created: int
    created_total: int
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
    idle_timeout_discards: int
    warmup_calls: int
    warmed_sessions: int
    acquire_wait_seconds: float
    close_calls: int
    closed: bool

    def metrics(self) -> dict[str, Any]:
        """Return a JSON-/metrics-friendly dict view of the snapshot."""
        return asdict(self)


@dataclass(frozen=True)
class GemStoneSessionPoolStats:
    """
    Stable pool statistics for capacity planning and metrics export.

    `created_total` and `evicted_total` are monotonic counters. `current_capacity`
    is the current number of live sessions owned by the pool.
    """

    in_use: int
    idle: int
    created_total: int
    evicted_total: int
    validation_failures: int
    acquire_waits_total: int
    acquire_wait_seconds_total: float
    current_capacity: int


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
        idle_timeout_seconds: Optional[float] = None,
        validation_query: Optional[str] = None,
        validation_interval_seconds: Optional[float] = None,
        metrics_exporter: Optional[Callable[[GemStoneSessionProviderSnapshot], None]] = None,
        event_listener: Optional[Callable[[GemStoneSessionProviderEvent], None]] = None,
        metrics: MetricsCollector | None = None,
        tracer: Tracer | None = None,
        logger: Any = None,
        **session_kwargs: Any,
    ) -> None:
        if max_session_age is not None and max_session_age <= 0:
            raise ValueError("GemStone session max_session_age must be > 0.")
        if max_session_uses is not None and max_session_uses < 1:
            raise ValueError("GemStone session max_session_uses must be >= 1.")
        if idle_timeout_seconds is not None and idle_timeout_seconds <= 0:
            raise ValueError("GemStone session idle_timeout_seconds must be > 0.")
        if validation_interval_seconds is not None and validation_interval_seconds <= 0:
            raise ValueError("GemStone validation_interval_seconds must be > 0.")
        self._name = name or type(self).__name__
        self._session_factory: Callable[..., GemStoneSession] = session_factory
        self._session_kwargs = dict(session_kwargs)
        self._session_healthcheck = session_healthcheck
        self._acquire_timeout = acquire_timeout
        self._max_session_age = max_session_age
        self._max_session_uses = max_session_uses
        self._idle_timeout_seconds = idle_timeout_seconds
        self._validation_query = (
            validation_query
            if validation_query is not None
            else ("1 + 1" if validation_interval_seconds is not None else None)
        )
        self._validation_interval_seconds = validation_interval_seconds
        self._metrics_exporter = metrics_exporter
        self._event_listener = event_listener
        self._metrics = metrics or NULL_METRICS
        self._tracer = tracer or NULL_TRACER
        self._logger = logger
        self._stats_lock = threading.Lock()
        self._created_total = 0
        self._acquire_calls = 0
        self._release_calls = 0
        self._discard_calls = 0
        self._timeout_calls = 0
        self._reset_failures = 0
        self._healthcheck_failures = 0
        self._create_failures = 0
        self._recycle_age_discards = 0
        self._recycle_use_discards = 0
        self._idle_timeout_discards = 0
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

    def _record_acquire_wait(self, started_at: float) -> float:
        wait_seconds = max(time.monotonic() - started_at, 0.0)
        self._record_float_stat("_acquire_wait_seconds", wait_seconds)
        return wait_seconds

    @staticmethod
    def _session_created_at(session: GemStoneSession) -> float:
        return float(getattr(session, "_gemstone_provider_created_at", time.monotonic()))

    @staticmethod
    def _session_use_count(session: GemStoneSession) -> int:
        return int(getattr(session, "_gemstone_provider_use_count", 0))

    def _mark_session_created(self, session: GemStoneSession) -> None:
        now = time.monotonic()
        setattr(session, "_gemstone_provider_created_at", now)
        setattr(session, "_gemstone_provider_use_count", 0)
        setattr(session, "_gemstone_provider_last_used_at", now)
        setattr(session, "_gemstone_provider_validated_at", 0.0)

    def _mark_session_checked_out(self, session: GemStoneSession) -> None:
        setattr(session, "_gemstone_provider_use_count", self._session_use_count(session) + 1)

    @staticmethod
    def _mark_session_released(session: GemStoneSession) -> None:
        setattr(session, "_gemstone_provider_last_used_at", time.monotonic())

    def _session_recycle_reason(self, session: GemStoneSession) -> Optional[str]:
        if self._max_session_age is not None:
            if time.monotonic() - self._session_created_at(session) >= self._max_session_age:
                return "max_age"
        if self._max_session_uses is not None:
            if self._session_use_count(session) >= self._max_session_uses:
                return "max_uses"
        return None

    def _session_idle_timeout_reason(self, session: GemStoneSession) -> Optional[str]:
        if self._idle_timeout_seconds is None:
            return None
        last_used_at = float(
            getattr(
                session,
                "_gemstone_provider_last_used_at",
                self._session_created_at(session),
            )
        )
        if last_used_at <= 0:
            return "idle_timeout"
        if time.monotonic() - last_used_at >= self._idle_timeout_seconds:
            return "idle_timeout"
        return None

    def _emit_observation(
        self,
        event_name: str,
        *,
        session: Optional[GemStoneSession] = None,
        reason: Optional[str] = None,
        attrs: Optional[dict[str, str | int | float | bool | None]] = None,
    ) -> None:
        snapshot = self.snapshot()
        self._emit_standard_observability(event_name, snapshot, reason=reason, attrs=attrs)
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

    def _emit_standard_observability(
        self,
        event_name: str,
        snapshot: GemStoneSessionProviderSnapshot,
        *,
        reason: Optional[str] = None,
        attrs: Optional[dict[str, str | int | float | bool | None]] = None,
    ) -> None:
        labels: dict[str, str] = {
            "event": event_name,
            "provider": snapshot.name,
            "provider_type": snapshot.provider_type,
        }
        if reason is not None:
            labels["reason"] = reason
        try:
            self._metrics.increment("gemstone_py_pool_events", labels)
        except Exception:
            pass

        attributes: dict[str, str | int | float | bool | None] = {
            "event": event_name,
            "provider": snapshot.name,
            "provider_type": snapshot.provider_type,
            "pool_in_use": snapshot.in_use,
            "pool_idle": snapshot.available,
            "pool_capacity": snapshot.created,
            "reason": reason,
        }
        if attrs:
            attributes.update(attrs)
        try:
            with self._tracer.start_span(f"gemstone.pool.{event_name}", attributes) as span:
                try:
                    span.set_attribute("status", "ok")
                except Exception:
                    pass
        except Exception:
            pass

    def _record_acquire_wait_metric(self, wait_seconds: float, snapshot: Any | None = None) -> None:
        del snapshot
        try:
            self._metrics.record_duration(
                "gemstone_py_pool_acquire_wait_ms",
                {
                    "provider": self._name,
                    "provider_type": type(self).__name__,
                },
                wait_seconds * 1000.0,
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
            self._record_stat("_created_total")
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

    def _session_needs_validation(self, session: GemStoneSession) -> bool:
        if self._session_healthcheck is None and self._validation_query is None:
            return False
        interval = self._validation_interval_seconds
        if interval is None:
            return True
        validated_at = float(getattr(session, "_gemstone_provider_validated_at", 0.0))
        if validated_at <= 0:
            return True
        return time.monotonic() - validated_at >= interval

    def _run_validation_query(self, session: GemStoneSession) -> bool:
        query = self._validation_query
        if query is None:
            return True
        session.eval(query)
        return True

    def _session_is_healthy(self, session: GemStoneSession) -> bool:
        if getattr(session, "_logged_in", True) is False:
            self._record_stat("_healthcheck_failures")
            return False
        if not self._session_needs_validation(session):
            return True
        try:
            if self._session_healthcheck is not None:
                healthy = bool(self._session_healthcheck(session))
            else:
                healthy = self._run_validation_query(session)
        except Exception:
            healthy = False
        if not healthy:
            self._record_stat("_healthcheck_failures")
        else:
            setattr(session, "_gemstone_provider_validated_at", time.monotonic())
        return healthy

    @staticmethod
    def _claim_session_thread_ownership(session: GemStoneSession) -> None:
        claim = getattr(session, "_claim_thread_ownership", None)
        if callable(claim):
            claim()

    @staticmethod
    def _release_session_thread_ownership(
        session: GemStoneSession,
        *,
        force: bool = False,
    ) -> None:
        release = getattr(session, "_release_thread_ownership", None)
        if callable(release):
            release(force=force)

    def _prepare_session_for_checkout(
        self,
        session: GemStoneSession,
    ) -> tuple[bool, Optional[str]]:
        self._claim_session_thread_ownership(session)
        idle_timeout_reason = self._session_idle_timeout_reason(session)
        if idle_timeout_reason is not None:
            return False, idle_timeout_reason
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
        minsize: Optional[int] = None,
    ) -> GemStoneSessionProviderSnapshot:
        with self._stats_lock:
            return GemStoneSessionProviderSnapshot(
                name=self._name,
                provider_type=type(self).__name__,
                maxsize=maxsize,
                minsize=minsize,
                max_session_age=self._max_session_age,
                max_session_uses=self._max_session_uses,
                created=created,
                created_total=self._created_total,
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
                idle_timeout_discards=self._idle_timeout_discards,
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
        minsize: int = 0,
        session_factory: Callable[..., GemStoneSession] = GemStoneSession,
        session_healthcheck: Optional[Callable[[GemStoneSession], bool]] = None,
        acquire_timeout: Optional[float] = None,
        max_session_age: Optional[float] = None,
        max_session_uses: Optional[int] = None,
        idle_timeout_seconds: Optional[float] = None,
        idle_sweep_interval_seconds: Optional[float] = None,
        validation_query: Optional[str] = None,
        validation_interval_seconds: Optional[float] = None,
        metrics_exporter: Optional[Callable[[GemStoneSessionProviderSnapshot], None]] = None,
        event_listener: Optional[Callable[[GemStoneSessionProviderEvent], None]] = None,
        metrics: MetricsCollector | None = None,
        tracer: Tracer | None = None,
        logger: Any = None,
        name: Optional[str] = None,
        **session_kwargs: Any,
    ) -> None:
        if maxsize < 1:
            raise ValueError("GemStoneSessionPool maxsize must be at least 1.")
        if minsize < 0:
            raise ValueError("GemStoneSessionPool minsize must be at least 0.")
        if minsize > maxsize:
            raise ValueError("GemStoneSessionPool minsize cannot exceed maxsize.")
        if idle_sweep_interval_seconds is not None and idle_sweep_interval_seconds <= 0:
            raise ValueError("GemStone idle_sweep_interval_seconds must be > 0.")
        self._maxsize = maxsize
        self._minsize = minsize
        self._idle_sweep_interval_seconds = idle_sweep_interval_seconds
        self._initialize_provider(
            name=name,
            session_factory=session_factory,
            session_healthcheck=session_healthcheck,
            acquire_timeout=acquire_timeout,
            max_session_age=max_session_age,
            max_session_uses=max_session_uses,
            idle_timeout_seconds=idle_timeout_seconds,
            validation_query=validation_query,
            validation_interval_seconds=validation_interval_seconds,
            metrics_exporter=metrics_exporter,
            event_listener=event_listener,
            metrics=metrics,
            tracer=tracer,
            logger=logger,
            **session_kwargs,
        )
        self._available: queue.LifoQueue[GemStoneSession] = queue.LifoQueue(maxsize)
        self._lock = threading.Lock()
        self._created = 0
        self._closed = False
        self._idle_sweeper_stop = threading.Event()
        self._idle_sweeper_thread: Optional[threading.Thread] = None
        self._start_idle_sweeper_if_configured()

    @property
    def maxsize(self) -> int:
        return self._maxsize

    @property
    def minsize(self) -> int:
        return self._minsize

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
                    wait_seconds = self._record_acquire_wait(started_at)
                    self._record_acquire_wait_metric(wait_seconds)
                    self._emit_observation(
                        "session_acquired",
                        session=session,
                        attrs={"wait_ms": wait_seconds * 1000.0},
                    )
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
                    wait_seconds = self._record_acquire_wait(started_at)
                    self._record_acquire_wait_metric(wait_seconds)
                    self._emit_observation(
                        "session_acquired",
                        session=session,
                        attrs={"wait_ms": wait_seconds * 1000.0},
                    )
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
                wait_seconds = self._record_acquire_wait(started_at)
                self._record_acquire_wait_metric(wait_seconds)
                self._emit_observation(
                    "session_acquired",
                    session=session,
                    attrs={"wait_ms": wait_seconds * 1000.0},
                )
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
            self._mark_session_released(session)
            self._release_session_thread_ownership(session)
            self._available.put_nowait(session)
            self._emit_observation("session_released", session=session)
        except queue.Full:
            self._discard_session(session, reason="queue_full")

    def close(self) -> None:
        self._record_stat("_close_calls")
        with self._lock:
            self._closed = True
        self._idle_sweeper_stop.set()
        sweeper_thread = self._idle_sweeper_thread
        if sweeper_thread is not None and sweeper_thread is not threading.current_thread():
            sweeper_thread.join(timeout=1.0)
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
            self._release_session_thread_ownership(session)
            try:
                self._available.put_nowait(session)
            except queue.Full:
                self._discard_session(session, reason="queue_full")
                break
            warmed += 1
            self._record_stat("_warmed_sessions")
            self._emit_observation("session_warmed", session=session)
        return warmed

    def sweep_idle(self) -> int:
        """
        Evict idle available sessions without touching checked-out sessions.

        The pool never sweeps below `minsize`; use `minsize=0` when every idle
        session may be discarded after `idle_timeout_seconds`.
        """
        if self._idle_timeout_seconds is None:
            return 0

        drained: list[GemStoneSession] = []
        while True:
            try:
                drained.append(self._available.get_nowait())
            except queue.Empty:
                break

        swept = 0
        keep: list[GemStoneSession] = []
        for session in drained:
            with self._lock:
                closed = self._closed
                can_evict = self._created > self._minsize
            if closed:
                self._discard_session(session, reason="provider_closed")
                swept += 1
            elif can_evict and self._session_idle_timeout_reason(session) == "idle_timeout":
                self._discard_session(session, reason="idle_timeout")
                swept += 1
            else:
                keep.append(session)

        for session in keep:
            try:
                self._available.put_nowait(session)
            except queue.Full:
                self._discard_session(session, reason="queue_full")
                swept += 1
        if swept:
            self._emit_observation("idle_sweep", reason="idle_timeout")
        return swept

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
        elif reason == "idle_timeout":
            self._record_stat("_idle_timeout_discards")
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
            minsize=self._minsize,
            created=created,
            available=self._available.qsize(),
            closed=closed,
        )

    def stats(self) -> GemStoneSessionPoolStats:
        """Return the stable production pool statistics contract."""
        snapshot = self.snapshot()
        return GemStoneSessionPoolStats(
            in_use=snapshot.in_use,
            idle=snapshot.available,
            created_total=snapshot.created_total,
            evicted_total=snapshot.discard_calls,
            validation_failures=snapshot.healthcheck_failures,
            acquire_waits_total=snapshot.acquire_calls,
            acquire_wait_seconds_total=snapshot.acquire_wait_seconds,
            current_capacity=snapshot.created,
        )

    def _start_idle_sweeper_if_configured(self) -> None:
        if self._idle_timeout_seconds is None:
            return
        interval = self._idle_sweep_interval_seconds
        if interval is None:
            interval = min(max(self._idle_timeout_seconds / 2.0, 1.0), 60.0)
        thread = threading.Thread(
            target=self._idle_sweeper_loop,
            name=f"{self._name}-idle-sweeper",
            args=(interval,),
            daemon=True,
        )
        self._idle_sweeper_thread = thread
        thread.start()

    def _idle_sweeper_loop(self, interval: float) -> None:
        while not self._idle_sweeper_stop.wait(interval):
            try:
                self.sweep_idle()
            except Exception:
                pass


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
        metrics: MetricsCollector | None = None,
        tracer: Tracer | None = None,
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
            metrics=metrics,
            tracer=tracer,
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
                self._release_session_thread_ownership(session, force=True)
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
