"""Framework-neutral web session lifecycle helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, Protocol, TypeVar

from .client import TransactionPolicy

SessionT = TypeVar("SessionT")
AsyncSessionT = TypeVar("AsyncSessionT")


class SessionProvider(Protocol[SessionT]):
    """Synchronous provider protocol used by framework adapters."""

    def acquire(self, timeout: float | None = None) -> SessionT:
        """Return one usable session."""

    def release(
        self,
        session: SessionT | None,
        *,
        discard: bool = False,
        clean: bool = False,
    ) -> None:
        """Return or discard a previously acquired session."""


class AsyncSessionProvider(Protocol[AsyncSessionT]):
    """Async provider protocol used by framework adapters."""

    def acquire(self, timeout: float | None = None) -> Awaitable[AsyncSessionT]:
        """Return an awaitable that resolves to one usable async session."""

    async def release(
        self,
        session: AsyncSessionT | None,
        *,
        discard: bool = False,
        clean: bool = False,
    ) -> None:
        """Return or discard a previously acquired async session."""


@dataclass(frozen=True)
class TransactionFinalization:
    """Result of a framework-neutral transaction finalization."""

    action: str
    clean: bool
    discard: bool = False


def request_failed(
    *,
    exc: BaseException | None = None,
    response_status: int | None = None,
    server_error_status: int = 500,
) -> bool:
    """Return true when a request outcome should abort the transaction."""
    if exc is not None:
        return True
    return response_status is not None and int(response_status) >= server_error_status


class TransactionScope(Generic[SessionT]):
    """
    Finalize one synchronous request or handler transaction.

    The scope is independent of Flask, Django, or any specific WSGI framework.
    It only assumes the session exposes `commit()` and `abort()`.
    """

    def __init__(
        self,
        session: SessionT,
        *,
        transaction_policy: TransactionPolicy | str = TransactionPolicy.COMMIT_ON_SUCCESS,
        server_error_status: int = 500,
    ) -> None:
        self.session = session
        self.transaction_policy = TransactionPolicy.coerce(transaction_policy)
        self.server_error_status = server_error_status
        self.last_outcome = TransactionFinalization("none", clean=False)

    def finalize(
        self,
        exc: BaseException | None = None,
        *,
        response_status: int | None = None,
    ) -> TransactionFinalization:
        """Commit, abort, or leave the session alone for the request outcome."""
        if request_failed(
            exc=exc,
            response_status=response_status,
            server_error_status=self.server_error_status,
        ):
            self.last_outcome = self._abort(raise_errors=False)
            return self.last_outcome
        if self.transaction_policy is TransactionPolicy.COMMIT_ON_SUCCESS:
            self.last_outcome = self._commit()
            return self.last_outcome
        if self.transaction_policy is TransactionPolicy.ABORT_ON_EXIT:
            self.last_outcome = self._abort(raise_errors=True)
            return self.last_outcome
        self.last_outcome = TransactionFinalization("none", clean=False)
        return self.last_outcome

    def _commit(self) -> TransactionFinalization:
        try:
            getattr(self.session, "commit")()
            return TransactionFinalization("commit", clean=True)
        except Exception:
            try:
                getattr(self.session, "abort")()
            except Exception:
                self.last_outcome = TransactionFinalization(
                    "abort_after_commit_failed",
                    clean=False,
                    discard=True,
                )
                raise
            self.last_outcome = TransactionFinalization(
                "abort_after_commit_failed",
                clean=True,
            )
            raise

    def _abort(self, *, raise_errors: bool) -> TransactionFinalization:
        try:
            getattr(self.session, "abort")()
            return TransactionFinalization("abort", clean=True)
        except Exception:
            if raise_errors:
                raise
            return TransactionFinalization("abort_failed", clean=False, discard=True)


class RequestScope(Generic[SessionT]):
    """
    Lazy synchronous request/session lifecycle.

    Framework adapters can keep one instance in their request-local storage,
    call `session()` from handlers, and call `finalize()` during teardown.
    """

    def __init__(
        self,
        *,
        session_provider: SessionProvider[SessionT] | None = None,
        session_factory: Callable[..., SessionT] | None = None,
        session_kwargs: dict[str, Any] | None = None,
        transaction_policy: TransactionPolicy | str = TransactionPolicy.COMMIT_ON_SUCCESS,
        server_error_status: int = 500,
    ) -> None:
        self.session_provider = session_provider
        self.session_factory = session_factory
        self.session_kwargs = dict(session_kwargs or {})
        self.transaction_policy = TransactionPolicy.coerce(transaction_policy)
        self.server_error_status = server_error_status
        self._session: SessionT | None = None
        self._finalized = False
        self._provider_owned = False

    @property
    def active_session(self) -> SessionT | None:
        """Return the acquired session, if any."""
        return self._session

    def session(self) -> SessionT:
        """Return the request session, acquiring or creating it lazily."""
        if self._session is not None:
            return self._session
        if self.session_provider is not None:
            self._session = self.session_provider.acquire()
            self._provider_owned = True
            return self._session
        if self.session_factory is None:
            raise RuntimeError("RequestScope needs a session_provider or session_factory.")
        session = self.session_factory(**self.session_kwargs)
        login = getattr(session, "login", None)
        if login is not None:
            login()
        self._session = session
        return session

    def finalize(
        self,
        exc: BaseException | None = None,
        *,
        response_status: int | None = None,
    ) -> TransactionFinalization:
        """Finalize the transaction and release/log out the session."""
        if self._finalized:
            return TransactionFinalization("already_finalized", clean=True)
        session = self._session
        self._finalized = True
        if session is None:
            return TransactionFinalization("none", clean=True)

        transaction = TransactionScope(
            session,
            transaction_policy=self.transaction_policy,
            server_error_status=self.server_error_status,
        )
        outcome = TransactionFinalization("none", clean=False)
        try:
            outcome = transaction.finalize(exc, response_status=response_status)
            return outcome
        except Exception:
            outcome = transaction.last_outcome
            raise
        finally:
            if self._provider_owned and self.session_provider is not None:
                self.session_provider.release(
                    session,
                    discard=outcome.discard,
                    clean=outcome.clean,
                )
            else:
                logout = getattr(session, "logout", None)
                if logout is not None:
                    logout()
            self._session = None


class AsyncTransactionScope(Generic[AsyncSessionT]):
    """Async variant of `TransactionScope`."""

    def __init__(
        self,
        session: AsyncSessionT,
        *,
        transaction_policy: TransactionPolicy | str = TransactionPolicy.COMMIT_ON_SUCCESS,
        server_error_status: int = 500,
    ) -> None:
        self.session = session
        self.transaction_policy = TransactionPolicy.coerce(transaction_policy)
        self.server_error_status = server_error_status
        self.last_outcome = TransactionFinalization("none", clean=False)

    async def finalize(
        self,
        exc: BaseException | None = None,
        *,
        response_status: int | None = None,
    ) -> TransactionFinalization:
        """Commit, abort, or leave the async session alone for the request outcome."""
        if request_failed(
            exc=exc,
            response_status=response_status,
            server_error_status=self.server_error_status,
        ):
            self.last_outcome = await self._abort(raise_errors=False)
            return self.last_outcome
        if self.transaction_policy is TransactionPolicy.COMMIT_ON_SUCCESS:
            self.last_outcome = await self._commit()
            return self.last_outcome
        if self.transaction_policy is TransactionPolicy.ABORT_ON_EXIT:
            self.last_outcome = await self._abort(raise_errors=True)
            return self.last_outcome
        self.last_outcome = TransactionFinalization("none", clean=False)
        return self.last_outcome

    async def _commit(self) -> TransactionFinalization:
        try:
            await getattr(self.session, "commit")()
            return TransactionFinalization("commit", clean=True)
        except Exception:
            try:
                await getattr(self.session, "abort")()
            except Exception:
                self.last_outcome = TransactionFinalization(
                    "abort_after_commit_failed",
                    clean=False,
                    discard=True,
                )
                raise
            self.last_outcome = TransactionFinalization(
                "abort_after_commit_failed",
                clean=True,
            )
            raise

    async def _abort(self, *, raise_errors: bool) -> TransactionFinalization:
        try:
            await getattr(self.session, "abort")()
            return TransactionFinalization("abort", clean=True)
        except Exception:
            if raise_errors:
                raise
            return TransactionFinalization("abort_failed", clean=False, discard=True)


class AsyncRequestScope(Generic[AsyncSessionT]):
    """Lazy async request/session lifecycle for ASGI-style adapters."""

    def __init__(
        self,
        *,
        session_provider: AsyncSessionProvider[AsyncSessionT] | None = None,
        session_factory: Callable[..., AsyncSessionT] | None = None,
        session_kwargs: dict[str, Any] | None = None,
        transaction_policy: TransactionPolicy | str = TransactionPolicy.COMMIT_ON_SUCCESS,
        server_error_status: int = 500,
    ) -> None:
        self.session_provider = session_provider
        self.session_factory = session_factory
        self.session_kwargs = dict(session_kwargs or {})
        self.transaction_policy = TransactionPolicy.coerce(transaction_policy)
        self.server_error_status = server_error_status
        self._session: AsyncSessionT | None = None
        self._finalized = False
        self._provider_owned = False

    @property
    def active_session(self) -> AsyncSessionT | None:
        """Return the acquired async session, if any."""
        return self._session

    async def session(self) -> AsyncSessionT:
        """Return the request session, acquiring or creating it lazily."""
        if self._session is not None:
            return self._session
        if self.session_provider is not None:
            self._session = await self.session_provider.acquire()
            self._provider_owned = True
            return self._session
        if self.session_factory is None:
            raise RuntimeError("AsyncRequestScope needs a session_provider or session_factory.")
        session = self.session_factory(**self.session_kwargs)
        login = getattr(session, "login", None)
        if login is not None:
            await login()
        self._session = session
        return session

    async def finalize(
        self,
        exc: BaseException | None = None,
        *,
        response_status: int | None = None,
    ) -> TransactionFinalization:
        """Finalize the transaction and release/log out the async session."""
        if self._finalized:
            return TransactionFinalization("already_finalized", clean=True)
        session = self._session
        self._finalized = True
        if session is None:
            return TransactionFinalization("none", clean=True)

        transaction = AsyncTransactionScope(
            session,
            transaction_policy=self.transaction_policy,
            server_error_status=self.server_error_status,
        )
        outcome = TransactionFinalization("none", clean=False)
        try:
            outcome = await transaction.finalize(exc, response_status=response_status)
            return outcome
        except Exception:
            outcome = transaction.last_outcome
            raise
        finally:
            if self._provider_owned and self.session_provider is not None:
                await self.session_provider.release(
                    session,
                    discard=outcome.discard,
                    clean=outcome.clean,
                )
            else:
                aclose = getattr(session, "aclose", None)
                if aclose is not None:
                    await aclose()
                else:
                    logout = getattr(session, "logout", None)
                    if logout is not None:
                        await logout()
            self._session = None


__all__ = [
    "AsyncRequestScope",
    "AsyncSessionProvider",
    "AsyncTransactionScope",
    "RequestScope",
    "SessionProvider",
    "TransactionFinalization",
    "TransactionScope",
    "request_failed",
]
