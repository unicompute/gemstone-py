"""Django helpers for synchronous GemStone request sessions.

The adapter intentionally avoids importing Django at module import time. It
uses the standard Django middleware callable shape and stores the request scope
on the request object.
"""

from __future__ import annotations

from typing import Any, Callable, cast

from gemstone_py.client import GemStoneConfig, GemStoneSession, TransactionPolicy
from gemstone_py.web_core import RequestScope, SessionProvider

_DJANGO_REQUEST_SESSION_ATTR = "gemstone_session"
_DJANGO_REQUEST_SCOPE_ATTR = "_gemstone_request_scope"

SessionFactory = Callable[..., GemStoneSession]
GetResponse = Callable[[Any], Any]


class GemStoneSessionMiddleware:
    """
    Django middleware that manages one lazy GemStone session per request.

    Handlers call ``request_session(request)`` to acquire the session. Successful
    responses commit by default; exceptions and 5xx responses abort.
    """

    def __init__(
        self,
        get_response: GetResponse,
        *,
        config: GemStoneConfig | None = None,
        session_provider: SessionProvider[GemStoneSession] | None = None,
        session_pool: SessionProvider[GemStoneSession] | None = None,
        session_factory: SessionFactory = GemStoneSession,
        request_attr: str = _DJANGO_REQUEST_SESSION_ATTR,
        scope_attr: str = _DJANGO_REQUEST_SCOPE_ATTR,
        commit_on_success: bool = True,
        server_error_status: int = 500,
        **session_kwargs: Any,
    ) -> None:
        if session_provider is not None and session_pool is not None:
            raise ValueError("Pass either session_provider or session_pool, not both.")
        self.get_response = get_response
        self.session_provider = session_provider or session_pool
        self.session_factory = session_factory
        self.request_attr = request_attr
        self.scope_attr = scope_attr
        self.transaction_policy = (
            TransactionPolicy.COMMIT_ON_SUCCESS
            if commit_on_success
            else TransactionPolicy.MANUAL
        )
        self.server_error_status = server_error_status
        self.session_kwargs = dict(session_kwargs)
        if config is not None:
            self.session_kwargs["config"] = config
        self.session_kwargs["transaction_policy"] = TransactionPolicy.MANUAL

    def __call__(self, request: Any) -> Any:
        scope = RequestScope(
            session_provider=self.session_provider,
            session_factory=None if self.session_provider is not None else self.session_factory,
            session_kwargs=self.session_kwargs,
            transaction_policy=self.transaction_policy,
            server_error_status=self.server_error_status,
        )
        setattr(request, self.scope_attr, scope)
        try:
            response = self.get_response(request)
        except Exception as exc:
            scope.finalize(exc)
            raise
        else:
            scope.finalize(response_status=getattr(response, "status_code", None))
            return response
        finally:
            _clear_request_state(
                request,
                scope,
                request_attr=self.request_attr,
                scope_attr=self.scope_attr,
            )


def session_middleware(**options: Any) -> Callable[[GetResponse], GemStoneSessionMiddleware]:
    """Return a Django middleware factory configured with gemstone-py options."""

    def build(get_response: GetResponse) -> GemStoneSessionMiddleware:
        return GemStoneSessionMiddleware(get_response, **options)

    return build


def request_session(
    request: Any,
    *,
    request_attr: str = _DJANGO_REQUEST_SESSION_ATTR,
    scope_attr: str = _DJANGO_REQUEST_SCOPE_ATTR,
) -> GemStoneSession:
    """Return the current Django request's shared GemStone session."""
    scope = getattr(request, scope_attr, None)
    if scope is None:
        raise RuntimeError("No GemStone request scope is attached to this Django request")
    request_scope = cast(RequestScope[GemStoneSession], scope)
    existing = getattr(request, request_attr, None)
    if existing is not None and existing is request_scope.active_session:
        return cast(GemStoneSession, existing)
    session = request_scope.session()
    setattr(request, request_attr, session)
    return session


def _clear_request_state(
    request: Any,
    scope: RequestScope[GemStoneSession],
    *,
    request_attr: str,
    scope_attr: str,
) -> None:
    if getattr(request, scope_attr, None) is scope:
        try:
            delattr(request, request_attr)
        except AttributeError:
            pass
        try:
            delattr(request, scope_attr)
        except AttributeError:
            pass


__all__ = [
    "GemStoneSessionMiddleware",
    "request_session",
    "session_middleware",
]
