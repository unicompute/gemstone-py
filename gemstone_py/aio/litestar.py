"""Litestar helpers for async GemStone request sessions.

The functions avoid importing Litestar at module import time. They return plain
async callables/generators that can be wrapped with Litestar's dependency and
middleware APIs by the application.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Callable, cast

from gemstone_py.aio import AsyncSession
from gemstone_py.aio.pool import AsyncSessionPool
from gemstone_py.client import TransactionPolicy
from gemstone_py.web_core import AsyncRequestScope, AsyncSessionProvider


def session_dependency(
    *,
    commit_on_success: bool = True,
    **session_kwargs: Any,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Build a Litestar-compatible async generator dependency."""

    async def provide_session() -> AsyncIterator[AsyncSession]:
        scope = AsyncRequestScope(
            session_factory=AsyncSession.connect,
            session_kwargs={
                **session_kwargs,
                "transaction_policy": TransactionPolicy.MANUAL,
            },
            transaction_policy=(
                TransactionPolicy.COMMIT_ON_SUCCESS
                if commit_on_success
                else TransactionPolicy.MANUAL
            ),
        )
        try:
            session = await scope.session()
            yield session
        except Exception as exc:
            await scope.finalize(exc)
            raise
        else:
            await scope.finalize()

    return provide_session


def pool_session_dependency(
    pool: AsyncSessionPool,
    *,
    commit_on_success: bool = True,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Build a Litestar-compatible dependency backed by ``AsyncSessionPool``."""

    async def provide_pooled_session() -> AsyncIterator[AsyncSession]:
        scope = AsyncRequestScope(
            session_provider=cast(AsyncSessionProvider[AsyncSession], pool),
            transaction_policy=(
                TransactionPolicy.COMMIT_ON_SUCCESS
                if commit_on_success
                else TransactionPolicy.MANUAL
            ),
        )
        try:
            session = await scope.session()
            yield session
        except Exception as exc:
            await scope.finalize(exc)
            raise
        else:
            await scope.finalize()

    return provide_pooled_session


class GemStoneSessionMiddleware:
    """ASGI middleware suitable for Litestar applications."""

    def __init__(
        self,
        app: Callable[..., Any],
        *,
        state_key: str = "gemstone_session",
        commit_on_success: bool = True,
        **session_kwargs: Any,
    ) -> None:
        self.app = app
        self.state_key = state_key
        self.commit_on_success = commit_on_success
        self.session_kwargs = dict(session_kwargs)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        response_status: int | None = None

        async def tracking_send(message: dict[str, Any]) -> None:
            nonlocal response_status
            if message.get("type") == "http.response.start":
                response_status = int(message.get("status", 500))
            await send(message)

        request_scope = AsyncRequestScope(
            session_factory=AsyncSession.connect,
            session_kwargs={
                **self.session_kwargs,
                "transaction_policy": TransactionPolicy.MANUAL,
            },
            transaction_policy=(
                TransactionPolicy.COMMIT_ON_SUCCESS
                if self.commit_on_success
                else TransactionPolicy.ABORT_ON_EXIT
            ),
        )
        state = scope.setdefault("state", {})
        state[self.state_key] = await request_scope.session()
        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            await request_scope.finalize(exc)
            raise
        else:
            await request_scope.finalize(response_status=response_status)
        finally:
            state.pop(self.state_key, None)


def request_session(connection: Any, *, state_key: str = "gemstone_session") -> AsyncSession:
    """Return the current Litestar connection's attached GemStone session."""
    state = getattr(connection, "state", None)
    if state is None and isinstance(connection, dict):
        state = connection.get("state")
    if isinstance(state, dict) and state_key in state:
        return cast(AsyncSession, state[state_key])
    try:
        return cast(AsyncSession, getattr(state, state_key))
    except AttributeError as exc:
        raise RuntimeError("No GemStone AsyncSession is attached to this connection") from exc


__all__ = [
    "GemStoneSessionMiddleware",
    "pool_session_dependency",
    "request_session",
    "session_dependency",
]
