"""Flask integration and production-grade session helpers for gemstone-py."""

from __future__ import annotations

import atexit
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional

from .client import GemStoneSession, TransactionPolicy
from .observability import MetricsCollector, Tracer
from .session_providers import (
    GemStoneSessionPool,
    GemStoneSessionPoolStats,
    GemStoneSessionProvider,
    GemStoneSessionProviderEvent,
    GemStoneSessionProviderSnapshot,
    GemStoneThreadLocalSessionProvider,
)
from .web_core import RequestScope, TransactionScope

__all__ = [
    "GemStoneSessionProviderEvent",
    "GemStoneSessionProviderSnapshot",
    "GemStoneSessionPoolStats",
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
_FLASK_REQUEST_SESSION_RESPONSE_STATUS_ATTR = "_gemstone_request_session_response_status"
_FLASK_REQUEST_SESSION_SCOPE_ATTR = "_gemstone_request_session_scope"


def _flask_request_state() -> tuple[Any | None, Any | None]:
    try:
        from flask import current_app, g, has_request_context
    except ImportError:
        return None, None
    if not has_request_context():
        return None, None
    return current_app._get_current_object(), g


def _clear_flask_request_session_state(flask_g: Any) -> None:
    for attr_name in (
        _FLASK_REQUEST_SESSION_ATTR,
        _FLASK_REQUEST_SESSION_PROVIDER_ATTR,
        _FLASK_REQUEST_SESSION_POOL_ATTR,
        _FLASK_REQUEST_SESSION_RESPONSE_STATUS_ATTR,
        _FLASK_REQUEST_SESSION_SCOPE_ATTR,
    ):
        try:
            delattr(flask_g, attr_name)
        except AttributeError:
            pass


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
    pool_minsize: int = 0,
    thread_local: bool = False,
    provider_name: Optional[str] = None,
    acquire_timeout: Optional[float] = None,
    session_healthcheck: Optional[Callable[[GemStoneSession], bool]] = None,
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
    **kwargs: Any,
) -> Optional[GemStoneSessionProvider]:
    if session_provider is not None and session_pool is not None:
        raise ValueError("Pass either session_provider or session_pool, not both.")
    provider = session_provider or session_pool
    if provider is not None and (pool_size is not None or pool_minsize != 0 or thread_local):
        raise ValueError(
            "Do not combine an explicit session provider with pool_size, "
            "pool_minsize, or thread_local."
        )
    if pool_size is not None and thread_local:
        raise ValueError("Pass either pool_size or thread_local, not both.")
    if provider is not None:
        return provider
    if pool_size is not None:
        return GemStoneSessionPool(
            maxsize=pool_size,
            minsize=pool_minsize,
            name=provider_name,
            acquire_timeout=acquire_timeout,
            session_healthcheck=session_healthcheck,
            max_session_age=max_session_age,
            max_session_uses=max_session_uses,
            idle_timeout_seconds=idle_timeout_seconds,
            idle_sweep_interval_seconds=idle_sweep_interval_seconds,
            validation_query=validation_query,
            validation_interval_seconds=validation_interval_seconds,
            metrics_exporter=metrics_exporter,
            event_listener=event_listener,
            metrics=metrics,
            tracer=tracer,
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
            metrics=metrics,
            tracer=tracer,
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
    scope: RequestScope[GemStoneSession] | None = getattr(
        flask_g,
        _FLASK_REQUEST_SESSION_SCOPE_ATTR,
        None,
    )
    if scope is not None:
        session = scope.session()
        setattr(flask_g, _FLASK_REQUEST_SESSION_ATTR, session)
        return session

    session_provider = config.get("session_provider") or config.get("session_pool")
    if session_provider is not None:
        scope = RequestScope(
            session_provider=session_provider,
            transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
        )
        session = scope.session()
        setattr(flask_g, _FLASK_REQUEST_SESSION_PROVIDER_ATTR, session_provider)
    else:
        options = dict(config.get("kwargs", {}))
        options.update(kwargs)
        options["transaction_policy"] = TransactionPolicy.MANUAL
        scope = RequestScope(
            session_factory=GemStoneSession,
            session_kwargs=options,
            transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
        )
        session = scope.session()
    setattr(flask_g, _FLASK_REQUEST_SESSION_SCOPE_ATTR, scope)
    setattr(flask_g, _FLASK_REQUEST_SESSION_ATTR, session)
    return session


def finalize_flask_request_session(exc: Optional[BaseException] = None) -> None:
    """
    Commit or abort the current Flask request's shared GemStone session.

    Requests that finish without an exception or server-error response commit;
    failing requests abort. Sessions created from a pool are returned to it.
    Ad-hoc request sessions are logged out.
    """
    _app, flask_g = _flask_request_state()
    if flask_g is None:
        return
    session = getattr(flask_g, _FLASK_REQUEST_SESSION_ATTR, None)
    if session is None:
        _clear_flask_request_session_state(flask_g)
        return

    session_provider = (
        getattr(flask_g, _FLASK_REQUEST_SESSION_PROVIDER_ATTR, None)
        or getattr(flask_g, _FLASK_REQUEST_SESSION_POOL_ATTR, None)
    )
    scope: RequestScope[GemStoneSession] | None = getattr(
        flask_g,
        _FLASK_REQUEST_SESSION_SCOPE_ATTR,
        None,
    )
    try:
        if scope is not None:
            scope.finalize(exc)
        else:
            transaction = TransactionScope(
                session,
                transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
            )
            outcome = transaction.last_outcome
            try:
                outcome = transaction.finalize(exc)
            finally:
                outcome = transaction.last_outcome if outcome.action == "none" else outcome
                if session_provider is not None:
                    session_provider.release(
                        session,
                        discard=outcome.discard,
                        clean=outcome.clean,
                    )
                else:
                    session.logout()
    finally:
        _clear_flask_request_session_state(flask_g)


def install_flask_request_session(
    app: Any,
    *,
    session_provider: Optional[GemStoneSessionProvider] = None,
    session_pool: Optional[GemStoneSessionProvider] = None,
    pool_size: Optional[int] = None,
    pool_minsize: int = 0,
    thread_local: bool = False,
    provider_name: Optional[str] = None,
    acquire_timeout: Optional[float] = None,
    session_healthcheck: Optional[Callable[[GemStoneSession], bool]] = None,
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
        pool_minsize=pool_minsize,
        thread_local=thread_local,
        provider_name=provider_name,
        acquire_timeout=acquire_timeout,
        session_healthcheck=session_healthcheck,
        max_session_age=max_session_age,
        max_session_uses=max_session_uses,
        idle_timeout_seconds=idle_timeout_seconds,
        idle_sweep_interval_seconds=idle_sweep_interval_seconds,
        validation_query=validation_query,
        validation_interval_seconds=validation_interval_seconds,
        metrics_exporter=metrics_exporter,
        event_listener=event_listener,
        metrics=metrics,
        tracer=tracer,
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

    def _warm_request_session_provider() -> None:
        warm_flask_request_session_provider(app, warmup_sessions)

    if provider is not None and warmup_sessions and hasattr(app, "before_serving"):
        app.before_serving(_warm_request_session_provider)

    def _close_request_session_provider() -> None:
        close_flask_request_session_provider(app)

    if provider is not None and close_on_after_serving and hasattr(app, "after_serving"):
        app.after_serving(_close_request_session_provider)

    def _record_request_session_outcome(response: Any) -> Any:
        if not getattr(app.session_interface, "_gemstone_request_session_finalizes", False):
            _app, flask_g = _flask_request_state()
            if flask_g is not None:
                setattr(
                    flask_g,
                    _FLASK_REQUEST_SESSION_RESPONSE_STATUS_ATTR,
                    getattr(response, "status_code", None),
                )
        return response

    app.after_request(_record_request_session_outcome)

    def _cleanup_request_session(exc: BaseException | None) -> None:
        if getattr(app.session_interface, "_gemstone_request_session_finalizes", False):
            if exc is not None:
                finalize_flask_request_session(exc)
            return
        _app, flask_g = _flask_request_state()
        response_status = (
            getattr(flask_g, _FLASK_REQUEST_SESSION_RESPONSE_STATUS_ATTR, None)
            if flask_g is not None
            else None
        )
        if exc is not None:
            finalize_flask_request_session(exc)
        elif response_status is not None and int(response_status) >= 500:
            finalize_flask_request_session(
                RuntimeError(f"request failed with status {response_status}")
            )
        else:
            finalize_flask_request_session()

    app.teardown_request(_cleanup_request_session)

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
    metrics: MetricsCollector | None = None,
    tracer: Tracer | None = None,
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
        metrics=metrics,
        tracer=tracer,
        logger=logger,
        **kwargs,
    )
    if provider is not None:
        scope = RequestScope(
            session_provider=provider,
            transaction_policy=policy,
        )
        try:
            pooled_session = scope.session()
            yield pooled_session
        except Exception as exc:
            scope.finalize(exc)
            raise
        else:
            scope.finalize()
        return

    with GemStoneSession(transaction_policy=policy, **kwargs) as new_session:
        yield new_session
