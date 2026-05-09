"""FastAPI/Starlette helpers for async GemStone sessions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Callable, cast

from gemstone_py.aio import AsyncSession
from gemstone_py.client import GemStoneConfig, TransactionPolicy


def session_dependency(
    *,
    commit_on_success: bool = True,
    **session_kwargs: Any,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """
    Build a FastAPI dependency that yields one ``AsyncSession`` per request.

    The dependency commits after a successful handler by default and aborts
    when the handler raises.
    """

    async def get_session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession.connect(
            transaction_policy=TransactionPolicy.MANUAL,
            **session_kwargs,
        ) as session:
            yield session
            if commit_on_success:
                await session.commit()

    return get_session


def get_session(**session_kwargs: Any) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Alias for ``session_dependency`` matching FastAPI naming conventions."""
    return session_dependency(**session_kwargs)


class GemStoneSessionMiddleware:
    """
    ASGI middleware that stores an ``AsyncSession`` in ``scope['state']``.

    HTTP responses below 500 commit by default; exceptions and 5xx responses
    abort. The state key defaults to ``gemstone_session``.
    """

    def __init__(
        self,
        app: Callable[..., Any],
        *,
        state_key: str = "gemstone_session",
        commit_on_success: bool = True,
        **session_kwargs: Any,
    ):
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

        async with AsyncSession.connect(
            transaction_policy=TransactionPolicy.MANUAL,
            **self.session_kwargs,
        ) as session:
            state = scope.setdefault("state", {})
            state[self.state_key] = session
            try:
                await self.app(scope, receive, tracking_send)
                if self.commit_on_success and (response_status is None or response_status < 500):
                    await session.commit()
                else:
                    await session.abort()
            finally:
                state.pop(self.state_key, None)


def install_fastapi_session(
    app: Any,
    *,
    config: GemStoneConfig | None = None,
    state_key: str = "gemstone_session",
    commit_on_success: bool = True,
    **session_kwargs: Any,
) -> None:
    """Install ``GemStoneSessionMiddleware`` on a FastAPI/Starlette app."""
    options = dict(session_kwargs)
    if config is not None:
        options["config"] = config
    app.add_middleware(
        GemStoneSessionMiddleware,
        state_key=state_key,
        commit_on_success=commit_on_success,
        **options,
    )


def request_session(request: Any, *, state_key: str = "gemstone_session") -> AsyncSession:
    """Return the current request's AsyncSession from Starlette request state."""
    try:
        return cast(AsyncSession, getattr(request.state, state_key))
    except AttributeError as exc:
        raise RuntimeError("No GemStone AsyncSession is attached to this request") from exc


__all__ = [
    "GemStoneSessionMiddleware",
    "get_session",
    "install_fastapi_session",
    "request_session",
    "session_dependency",
]
