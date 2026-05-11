"""Asyncio wrappers for the synchronous GemStone client API."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from types import TracebackType
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from gemstone_py.client import GemStoneConfig, GemStoneSession, TransactionPolicy
from gemstone_py.oop import ManagedOop, OopHandle, TypedOop

T = TypeVar("T")

if TYPE_CHECKING:
    from gemstone_py.aio.gsquery import AsyncGSCollection
    from gemstone_py.aio.persistent_root import AsyncPersistentRoot


def _argument_to_oop(arg: Any) -> int:
    if isinstance(arg, AsyncManagedOop):
        return arg.oop
    if isinstance(arg, AsyncOopHandle):
        return arg.oop
    if isinstance(arg, ManagedOop):
        return arg.oop
    if isinstance(arg, OopHandle):
        return arg.oop
    if hasattr(arg, "oop"):
        return int(getattr(arg, "oop"))
    return int(arg)


class AsyncManagedOop:
    """Async-safe managed OOP handle bound to an ``AsyncSession``."""

    def __init__(self, session: "AsyncSession", managed: ManagedOop):
        self._session = session
        self._managed = managed

    @property
    def oop(self) -> int:
        return self._managed.oop

    async def close(self) -> None:
        await self._session.run_sync(lambda _session: self._managed.close())

    async def detach(self) -> int:
        return await self._session.run_sync(lambda _session: self._managed.detach())

    async def send(self, selector: str, *args: Any) -> Any:
        raw = [_argument_to_oop(arg) for arg in args]
        return await self._session.run_sync(
            lambda sync_session: sync_session.perform_value(self.oop, selector, *raw)
        )

    async def send_oop(self, selector: str, *args: Any) -> int:
        raw = [_argument_to_oop(arg) for arg in args]
        return await self._session.run_sync(
            lambda sync_session: sync_session.perform_oop(self.oop, selector, *raw)
        )

    async def print_string(self) -> str:
        return str(await self.send("printString"))

    def __int__(self) -> int:
        return self.oop

    def __index__(self) -> int:
        return self.oop

    def __repr__(self) -> str:
        return f"<AsyncManagedOop 0x{self.oop:016X}>"


class AsyncOopHandle:
    """Async context-managed export-set handle for a raw OOP."""

    def __init__(self, session: "AsyncSession", oop: int):
        self._session = session
        self._oop = int(oop)
        self._handle: OopHandle | None = None

    @property
    def oop(self) -> int:
        return self._oop

    async def __aenter__(self) -> "AsyncOopHandle":
        def enter(sync_session: GemStoneSession) -> OopHandle:
            handle = sync_session.handle(self._oop)
            handle.__enter__()
            return handle

        self._handle = await self._session.run_sync(enter)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        del exc_type, exc_val, exc_tb
        handle = self._handle
        if handle is not None:
            await self._session.run_sync(lambda _session: handle.__exit__(None, None, None))
            self._handle = None
        return False

    async def send(self, selector: str, *args: Any) -> Any:
        raw = [_argument_to_oop(arg) for arg in args]
        return await self._session.run_sync(
            lambda sync_session: sync_session.perform_value(self.oop, selector, *raw)
        )

    async def send_oop(self, selector: str, *args: Any) -> int:
        raw = [_argument_to_oop(arg) for arg in args]
        return await self._session.run_sync(
            lambda sync_session: sync_session.perform_oop(self.oop, selector, *raw)
        )

    def __int__(self) -> int:
        return self.oop

    def __index__(self) -> int:
        return self.oop


class AsyncSession:
    """
    Async facade over ``GemStoneSession``.

    The underlying synchronous session is created and used from one dedicated
    executor thread, which keeps GemStone GCI calls on a single owning thread.
    """

    def __init__(
        self,
        session: GemStoneSession | None = None,
        *,
        session_factory: Callable[..., GemStoneSession] = GemStoneSession,
        executor: ThreadPoolExecutor | None = None,
        **session_kwargs: Any,
    ):
        self._session = session
        self._session_factory = session_factory
        self._session_kwargs = dict(session_kwargs)
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="gemstone-async-session",
        )
        self._owns_executor = executor is None
        self._closed = False

    @classmethod
    def connect(
        cls,
        stone: str | None = None,
        netldi: str | None = None,
        host: str | None = None,
        username: str | None = None,
        password: str | None = None,
        lib_path: str | None = None,
        *,
        config: GemStoneConfig | None = None,
        transaction_policy: TransactionPolicy | str = TransactionPolicy.MANUAL,
        **kwargs: Any,
    ) -> "AsyncSession":
        """Return an awaitable async session/context manager."""
        options = dict(kwargs)
        options.update(
            {
                "stone": stone,
                "netldi": netldi,
                "host": host,
                "username": username,
                "password": password,
                "lib_path": lib_path,
                "config": config,
                "transaction_policy": transaction_policy,
            }
        )
        return cls(**{key: value for key, value in options.items() if value is not None})

    def __await__(self) -> Generator[Any, None, "AsyncSession"]:
        async def _login_and_return() -> "AsyncSession":
            await self.login()
            return self

        return _login_and_return().__await__()

    async def __aenter__(self) -> "AsyncSession":
        await self.login()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        try:
            return await self.run_sync(lambda session: session.__exit__(exc_type, exc_val, exc_tb))
        finally:
            self.close()

    @property
    def closed(self) -> bool:
        return self._closed

    async def run_sync(self, fn: Callable[[GemStoneSession], T]) -> T:
        """Run ``fn`` against the underlying sync session on its owner thread."""
        if self._closed:
            raise RuntimeError("AsyncSession is closed")

        def invoke() -> T:
            session = self._ensure_session()
            return fn(session)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, invoke)

    def close(self) -> None:
        """Shut down the owned executor after the session has been logged out."""
        if self._closed:
            return
        self._closed = True
        if self._owns_executor:
            self._executor.shutdown(wait=True)

    async def aclose(self) -> None:
        """Log out the underlying session, then close the executor."""
        if self._closed:
            return
        try:
            if self._session is not None:
                await self.logout()
        finally:
            self.close()

    def _ensure_session(self) -> GemStoneSession:
        if self._session is None:
            self._session = self._session_factory(**self._session_kwargs)
        return self._session

    async def login(self) -> None:
        await self.run_sync(
            lambda session: None if getattr(session, "_logged_in", False) else session.login()
        )

    async def logout(self) -> None:
        await self.run_sync(lambda session: session.logout())

    async def commit(self) -> None:
        await self.run_sync(lambda session: session.commit())

    async def abort(self) -> None:
        await self.run_sync(lambda session: session.abort())

    async def needs_commit(self) -> bool:
        return await self.run_sync(lambda session: session.needs_commit())

    async def in_transaction(self) -> bool:
        return await self.run_sync(lambda session: session.in_transaction())

    async def eval(self, source: str) -> Any:
        return await self.run_sync(lambda session: session.eval(source))

    async def eval_oop(self, source: str) -> int:
        return await self.run_sync(lambda session: session.eval_oop(source))

    async def execute(self, source: str) -> int:
        return await self.execute_oop(source)

    async def execute_oop(self, source: str) -> int:
        return await self.eval_oop(source)

    async def execute_typed(self, source: str, cls: type[T]) -> TypedOop[T]:
        return await self.run_sync(lambda session: session.execute_typed(source, cls))

    async def execute_managed(self, source: str) -> AsyncManagedOop:
        return await self.eval_managed(source)

    async def eval_managed(self, source: str) -> AsyncManagedOop:
        managed = await self.run_sync(lambda session: session.eval_managed(source))
        return AsyncManagedOop(self, managed)

    async def perform_value(self, receiver: int, selector: str, *args: int) -> Any:
        return await self.run_sync(lambda session: session.perform_value(receiver, selector, *args))

    async def perform(self, receiver: int, selector: str, *args: int) -> int:
        return await self.perform_oop(receiver, selector, *args)

    async def perform_oop(self, receiver: int, selector: str, *args: int) -> int:
        return await self.run_sync(lambda session: session.perform_oop(receiver, selector, *args))

    async def perform_typed(
        self,
        receiver: int,
        selector: str,
        cls: type[T],
        *args: int,
    ) -> TypedOop[T]:
        return await self.run_sync(
            lambda session: session.perform_typed(receiver, selector, cls, *args)
        )

    async def perform_managed(self, receiver: int, selector: str, *args: int) -> AsyncManagedOop:
        managed = await self.run_sync(
            lambda session: session.perform_managed(receiver, selector, *args)
        )
        return AsyncManagedOop(self, managed)

    async def new_string(self, value: str) -> int:
        return await self.run_sync(lambda session: session.new_string(value))

    async def new_symbol(self, value: str) -> int:
        return await self.run_sync(lambda session: session.new_symbol(value))

    async def new_object(self, class_oop: int) -> int:
        return await self.run_sync(lambda session: session.new_object(class_oop))

    async def resolve(self, name: str) -> int:
        return await self.run_sync(lambda session: session.resolve(name))

    async def resolve_symbol(self, name: str) -> int:
        return await self.resolve(name)

    def int_oop(self, value: int) -> int:
        session = self._session
        if session is not None:
            return session.int_oop(value)
        return GemStoneSession().int_oop(value)

    async def float_oop(self, value: float) -> int:
        return await self.run_sync(lambda session: session.float_oop(value))

    async def try_oop_to_float(self, oop: int) -> float | None:
        return await self.run_sync(lambda session: session.try_oop_to_float(oop))

    async def dict_to_gs(self, value: dict[str, object]) -> int:
        return await self.run_sync(lambda session: session.dict_to_gs(value))

    async def dict_put_global(self, symbol_name: str, value: dict[str, object]) -> None:
        await self.run_sync(lambda session: session.dict_put_global(symbol_name, value))

    async def global_get(self, symbol_name: str) -> int:
        return await self.run_sync(lambda session: session.global_get(symbol_name))

    async def str_dict_get(self, dict_oop: int, key: str) -> Any:
        return await self.run_sync(lambda session: session.str_dict_get(dict_oop, key))

    async def fetch_string(self, oop: int) -> str:
        return await self.run_sync(lambda session: session.fetch_string(oop))

    async def fetch_class(self, oop: int) -> int:
        return await self.run_sync(lambda session: session.fetch_class(oop))

    async def managed_oop(self, oop: int) -> AsyncManagedOop:
        managed = await self.run_sync(lambda session: session.managed_oop(oop))
        return AsyncManagedOop(self, managed)

    def handle(self, oop: int) -> AsyncOopHandle:
        return AsyncOopHandle(self, oop)

    def transaction(self) -> "_AsyncTransaction":
        """Return an async transaction context manager."""
        return _AsyncTransaction(self)

    def root(self, name: str = "UserGlobals") -> "AsyncPersistentRoot":
        """Return a lazy async PersistentRoot wrapper bound to this session."""
        from gemstone_py.aio.persistent_root import AsyncPersistentRoot

        return AsyncPersistentRoot(self, name)


class _AsyncTransaction:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        del exc_val, exc_tb
        if exc_type is None:
            await self._session.commit()
        else:
            await self._session.abort()
        return False


def __getattr__(name: str) -> object:
    if name == "AsyncGSCollection":
        from gemstone_py.aio.gsquery import AsyncGSCollection

        return AsyncGSCollection
    if name == "AsyncPersistentRoot":
        from gemstone_py.aio.persistent_root import AsyncPersistentRoot

        return AsyncPersistentRoot
    if name == "AsyncSessionPool":
        from gemstone_py.aio.pool import AsyncSessionPool

        return AsyncSessionPool
    if name == "AsyncSessionPoolLease":
        from gemstone_py.aio.pool import AsyncSessionPoolLease

        return AsyncSessionPoolLease
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AsyncGSCollection",
    "AsyncManagedOop",
    "AsyncOopHandle",
    "AsyncPersistentRoot",
    "AsyncSession",
    "AsyncSessionPool",
    "AsyncSessionPoolLease",
]
