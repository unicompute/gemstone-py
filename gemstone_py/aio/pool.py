"""Async GemStone session pool."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any

from gemstone_py.aio import AsyncSession
from gemstone_py.client import GemStoneSession, TransactionPolicy
from gemstone_py.web import GemStoneSessionPoolStats

AsyncSessionHealthcheck = Callable[[AsyncSession], bool | Awaitable[bool]]


class AsyncSessionPool:
    """
    Bounded pool of logged-in ``AsyncSession`` instances.

    Sessions are created lazily up to ``maxsize``. Returned sessions are reset
    before reuse unless the caller marks them clean after an explicit commit or
    abort. Idle maintenance only sweeps sessions sitting in the pool; checked-out
    sessions are never evicted by the background task.
    """

    def __init__(
        self,
        *,
        maxsize: int = 4,
        minsize: int = 0,
        session_factory: Callable[..., GemStoneSession] = GemStoneSession,
        async_session_factory: Callable[..., AsyncSession] = AsyncSession,
        session_healthcheck: AsyncSessionHealthcheck | None = None,
        acquire_timeout: float | None = None,
        max_session_age: float | None = None,
        max_session_uses: int | None = None,
        idle_timeout_seconds: float | None = None,
        idle_sweep_interval_seconds: float | None = None,
        validation_query: str | None = None,
        validation_interval_seconds: float | None = None,
        **session_kwargs: Any,
    ) -> None:
        if maxsize < 1:
            raise ValueError("AsyncSessionPool maxsize must be at least 1.")
        if minsize < 0:
            raise ValueError("AsyncSessionPool minsize must be at least 0.")
        if minsize > maxsize:
            raise ValueError("AsyncSessionPool minsize cannot exceed maxsize.")
        if max_session_age is not None and max_session_age <= 0:
            raise ValueError("AsyncSession max_session_age must be > 0.")
        if max_session_uses is not None and max_session_uses < 1:
            raise ValueError("AsyncSession max_session_uses must be >= 1.")
        if idle_timeout_seconds is not None and idle_timeout_seconds <= 0:
            raise ValueError("AsyncSession idle_timeout_seconds must be > 0.")
        if idle_sweep_interval_seconds is not None and idle_sweep_interval_seconds <= 0:
            raise ValueError("AsyncSession idle_sweep_interval_seconds must be > 0.")
        if validation_interval_seconds is not None and validation_interval_seconds <= 0:
            raise ValueError("AsyncSession validation_interval_seconds must be > 0.")

        self._maxsize = maxsize
        self._minsize = minsize
        self._session_factory = session_factory
        self._async_session_factory = async_session_factory
        self._session_healthcheck = session_healthcheck
        self._acquire_timeout = acquire_timeout
        self._max_session_age = max_session_age
        self._max_session_uses = max_session_uses
        self._idle_timeout_seconds = idle_timeout_seconds
        self._idle_sweep_interval_seconds = idle_sweep_interval_seconds
        self._validation_query = (
            validation_query
            if validation_query is not None
            else ("1 + 1" if validation_interval_seconds is not None else None)
        )
        self._validation_interval_seconds = validation_interval_seconds
        self._session_kwargs = dict(session_kwargs)

        self._available: asyncio.LifoQueue[AsyncSession] = asyncio.LifoQueue(maxsize)
        self._lock = asyncio.Lock()
        self._created = 0
        self._created_total = 0
        self._discard_calls = 0
        self._validation_failures = 0
        self._acquire_calls = 0
        self._acquire_wait_seconds = 0.0
        self._closed = False
        self._sweeper_task: asyncio.Task[None] | None = None

    @property
    def maxsize(self) -> int:
        return self._maxsize

    @property
    def minsize(self) -> int:
        return self._minsize

    @property
    def created(self) -> int:
        return self._created

    @property
    def available(self) -> int:
        return self._available.qsize()

    def acquire(self, timeout: float | None = None) -> "AsyncSessionPoolLease":
        """Return an awaitable async context manager for one pooled session."""
        return AsyncSessionPoolLease(self, timeout=timeout)

    async def release(
        self,
        session: AsyncSession | None,
        *,
        discard: bool = False,
        clean: bool = False,
    ) -> None:
        """Return a session to the pool or discard it."""
        if session is None:
            return
        if discard or self._closed:
            await self._discard_session(session)
            return
        if not clean and not await self._reset_session(session):
            await self._discard_session(session)
            return
        if not await self._session_is_healthy(session):
            await self._discard_session(session)
            return
        recycle_reason = self._session_recycle_reason(session)
        if recycle_reason is not None:
            await self._discard_session(session)
            return
        self._mark_session_released(session)
        try:
            self._available.put_nowait(session)
        except asyncio.QueueFull:
            await self._discard_session(session)

    async def warm(self, count: int | None = None) -> int:
        """Create and log in up to ``count`` idle sessions."""
        self._ensure_sweeper_started()
        target = self._maxsize if count is None else min(max(int(count), 0), self._maxsize)
        warmed = 0
        while warmed < target:
            async with self._lock:
                if self._closed:
                    raise RuntimeError("AsyncSessionPool is closed.")
                if self._created >= self._maxsize:
                    break
                self._created += 1
            try:
                session = await self._create_session()
            except Exception:
                async with self._lock:
                    self._created -= 1
                raise
            if not await self._session_is_healthy(session):
                await self._discard_session(session)
                continue
            try:
                self._available.put_nowait(session)
            except asyncio.QueueFull:
                await self._discard_session(session)
                break
            warmed += 1
        return warmed

    async def sweep_idle(self) -> int:
        """Evict idle available sessions down to ``minsize``."""
        if self._idle_timeout_seconds is None:
            return 0

        drained: list[AsyncSession] = []
        while True:
            try:
                drained.append(self._available.get_nowait())
            except asyncio.QueueEmpty:
                break

        swept = 0
        keep: list[AsyncSession] = []
        for session in drained:
            async with self._lock:
                closed = self._closed
                can_evict = self._created > self._minsize
            if closed:
                await self._discard_session(session)
                swept += 1
            elif can_evict and self._session_idle_timed_out(session):
                await self._discard_session(session)
                swept += 1
            else:
                keep.append(session)

        for session in keep:
            try:
                self._available.put_nowait(session)
            except asyncio.QueueFull:
                await self._discard_session(session)
                swept += 1
        return swept

    def stats(self) -> GemStoneSessionPoolStats:
        """Return stable pool statistics for metrics export."""
        return GemStoneSessionPoolStats(
            in_use=max(self._created - self._available.qsize(), 0),
            idle=self._available.qsize(),
            created_total=self._created_total,
            evicted_total=self._discard_calls,
            validation_failures=self._validation_failures,
            acquire_waits_total=self._acquire_calls,
            acquire_wait_seconds_total=self._acquire_wait_seconds,
            current_capacity=self._created,
        )

    async def close(self) -> None:
        """Close every idle session and stop the background sweeper."""
        if self._closed:
            return
        self._closed = True
        task = self._sweeper_task
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        while True:
            try:
                session = self._available.get_nowait()
            except asyncio.QueueEmpty:
                break
            await self._discard_session(session)

    async def aclose(self) -> None:
        """Alias for ``close()``."""
        await self.close()

    async def __aenter__(self) -> "AsyncSessionPool":
        self._ensure_sweeper_started()
        if self._minsize:
            await self.warm(self._minsize)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        del exc_type, exc_val, exc_tb
        await self.close()
        return False

    async def _acquire(self, timeout: float | None = None) -> AsyncSession:
        self._ensure_sweeper_started()
        started_at = time.monotonic()
        self._acquire_calls += 1
        effective_timeout = self._acquire_timeout if timeout is None else timeout
        deadline = None if effective_timeout is None else time.monotonic() + effective_timeout

        async with self._lock:
            if self._closed:
                raise RuntimeError("AsyncSessionPool is closed.")

        while True:
            try:
                session = self._available.get_nowait()
                if await self._prepare_session_for_checkout(session):
                    self._record_acquire_wait(started_at)
                    return session
                await self._discard_session(session)
                continue
            except asyncio.QueueEmpty:
                pass

            async with self._lock:
                if self._closed:
                    raise RuntimeError("AsyncSessionPool is closed.")
                if self._created < self._maxsize:
                    self._created += 1
                    should_create = True
                else:
                    should_create = False

            if should_create:
                try:
                    session = await self._create_session()
                except Exception:
                    async with self._lock:
                        self._created -= 1
                    raise
                if await self._prepare_session_for_checkout(session):
                    self._record_acquire_wait(started_at)
                    return session
                await self._discard_session(session)
                continue

            remaining = None
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Timed out waiting for an AsyncSession from the pool.")
            try:
                if remaining is None:
                    session = await self._available.get()
                else:
                    session = await asyncio.wait_for(self._available.get(), timeout=remaining)
            except asyncio.TimeoutError as exc:
                raise TimeoutError(
                    "Timed out waiting for an AsyncSession from the pool."
                ) from exc
            if await self._prepare_session_for_checkout(session):
                self._record_acquire_wait(started_at)
                return session
            await self._discard_session(session)

    async def _create_session(self) -> AsyncSession:
        options = dict(self._session_kwargs)
        options["transaction_policy"] = TransactionPolicy.MANUAL
        options["session_factory"] = self._session_factory
        session = self._async_session_factory(**options)
        await session.login()
        self._mark_session_created(session)
        self._created_total += 1
        return session

    async def _discard_session(self, session: AsyncSession) -> None:
        self._discard_calls += 1
        try:
            await session.aclose()
        finally:
            async with self._lock:
                if self._created > 0:
                    self._created -= 1

    async def _reset_session(self, session: AsyncSession) -> bool:
        try:
            await session.abort()
            return True
        except Exception:
            self._validation_failures += 1
            return False

    async def _session_is_healthy(self, session: AsyncSession) -> bool:
        if session.closed:
            self._validation_failures += 1
            return False
        if not self._session_needs_validation(session):
            return True
        try:
            if self._session_healthcheck is not None:
                health = self._session_healthcheck(session)
                healthy = bool(await health) if inspect.isawaitable(health) else bool(health)
            else:
                healthy = await self._run_validation_query(session)
        except Exception:
            healthy = False
        if healthy:
            setattr(session, "_gemstone_pool_validated_at", time.monotonic())
        else:
            self._validation_failures += 1
        return healthy

    async def _run_validation_query(self, session: AsyncSession) -> bool:
        query = self._validation_query
        if query is None:
            return True
        await session.eval(query)
        return True

    async def _prepare_session_for_checkout(self, session: AsyncSession) -> bool:
        if self._session_idle_timed_out(session):
            return False
        if not await self._session_is_healthy(session):
            return False
        if self._session_recycle_reason(session) is not None:
            return False
        self._mark_session_checked_out(session)
        return True

    def _session_recycle_reason(self, session: AsyncSession) -> str | None:
        if self._max_session_age is not None:
            created_at = float(getattr(session, "_gemstone_pool_created_at", time.monotonic()))
            if time.monotonic() - created_at >= self._max_session_age:
                return "max_age"
        if self._max_session_uses is not None:
            use_count = int(getattr(session, "_gemstone_pool_use_count", 0))
            if use_count >= self._max_session_uses:
                return "max_uses"
        return None

    def _session_idle_timed_out(self, session: AsyncSession) -> bool:
        if self._idle_timeout_seconds is None:
            return False
        last_used_at = float(getattr(session, "_gemstone_pool_last_used_at", 0.0))
        if last_used_at <= 0:
            return True
        return time.monotonic() - last_used_at >= self._idle_timeout_seconds

    def _session_needs_validation(self, session: AsyncSession) -> bool:
        if self._session_healthcheck is None and self._validation_query is None:
            return False
        interval = self._validation_interval_seconds
        if interval is None:
            return True
        validated_at = float(getattr(session, "_gemstone_pool_validated_at", 0.0))
        if validated_at <= 0:
            return True
        return time.monotonic() - validated_at >= interval

    @staticmethod
    def _mark_session_created(session: AsyncSession) -> None:
        now = time.monotonic()
        setattr(session, "_gemstone_pool_created_at", now)
        setattr(session, "_gemstone_pool_last_used_at", now)
        setattr(session, "_gemstone_pool_validated_at", 0.0)
        setattr(session, "_gemstone_pool_use_count", 0)

    @staticmethod
    def _mark_session_checked_out(session: AsyncSession) -> None:
        use_count = int(getattr(session, "_gemstone_pool_use_count", 0))
        setattr(session, "_gemstone_pool_use_count", use_count + 1)

    @staticmethod
    def _mark_session_released(session: AsyncSession) -> None:
        setattr(session, "_gemstone_pool_last_used_at", time.monotonic())

    def _record_acquire_wait(self, started_at: float) -> None:
        self._acquire_wait_seconds += max(time.monotonic() - started_at, 0.0)

    def _ensure_sweeper_started(self) -> None:
        if self._idle_timeout_seconds is None or self._sweeper_task is not None:
            return
        interval = self._idle_sweep_interval_seconds
        if interval is None:
            interval = min(max(self._idle_timeout_seconds / 2.0, 1.0), 60.0)
        self._sweeper_task = asyncio.create_task(self._sweeper_loop(interval))

    async def _sweeper_loop(self, interval: float) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(interval)
                await self.sweep_idle()
        except asyncio.CancelledError:
            raise


class AsyncSessionPoolLease(AbstractAsyncContextManager[AsyncSession]):
    """Awaitable/context-manager lease returned by ``AsyncSessionPool.acquire``."""

    def __init__(self, pool: AsyncSessionPool, *, timeout: float | None = None):
        self._pool = pool
        self._timeout = timeout
        self._session: AsyncSession | None = None

    def __await__(self) -> Any:
        return self._pool._acquire(self._timeout).__await__()

    async def __aenter__(self) -> AsyncSession:
        self._session = await self._pool._acquire(self._timeout)
        return self._session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        del exc_val, exc_tb
        session = self._session
        self._session = None
        if session is None:
            return False
        await self._pool.release(session, discard=False, clean=False)
        return False


__all__ = [
    "AsyncSessionHealthcheck",
    "AsyncSessionPool",
    "AsyncSessionPoolLease",
]
