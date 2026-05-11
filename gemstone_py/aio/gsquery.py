"""Async wrappers for ``gemstone_py.gsquery``."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterable

from gemstone_py import GemStoneConfig
from gemstone_py.aio import AsyncSession
from gemstone_py.gsquery import GSCollection, Record


class AsyncGSCollection:
    """Async facade for ``GSCollection`` query and mutation operations."""

    def __init__(
        self,
        name: str,
        *,
        config: GemStoneConfig | None = None,
        collection: GSCollection | None = None,
        executor: ThreadPoolExecutor | None = None,
    ):
        self._collection = collection or GSCollection(name, config=config)
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="gemstone-async-gsquery",
        )
        self._owns_executor = executor is None
        self._closed = False

    async def __aenter__(self) -> "AsyncGSCollection":
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> bool:
        del exc_type, exc_val, exc_tb
        self.close()
        return False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_executor:
            self._executor.shutdown(wait=True)

    async def _run(
        self,
        method_name: str,
        *args: Any,
        session: AsyncSession | None = None,
        **kwargs: Any,
    ) -> Any:
        if self._closed:
            raise RuntimeError("AsyncGSCollection is closed")
        if session is not None:
            return await session.run_sync(
                lambda sync_session: getattr(self._collection, method_name)(
                    *args,
                    session=sync_session,
                    **kwargs,
                )
            )

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: getattr(self._collection, method_name)(*args, **kwargs),
        )

    async def add_index(self, ivar_path: str, session: AsyncSession | None = None) -> None:
        await self._run("add_index", ivar_path, session=session)

    async def add_index_for_class(
        self,
        ivar_path: str,
        gs_class: str = "SmallInt",
        session: AsyncSession | None = None,
    ) -> None:
        await self._run("add_index_for_class", ivar_path, gs_class, session=session)

    async def remove_index(self, ivar_path: str, session: AsyncSession | None = None) -> None:
        await self._run("remove_index", ivar_path, session=session)

    async def remove_all_indexes(self, session: AsyncSession | None = None) -> None:
        await self._run("remove_all_indexes", session=session)

    async def insert(self, element: Record, session: AsyncSession | None = None) -> None:
        await self._run("insert", element, session=session)

    async def bulk_insert(
        self,
        elements: Iterable[Record],
        session: AsyncSession | None = None,
    ) -> int:
        return int(await self._run("bulk_insert", elements, session=session))

    async def search(
        self,
        ivar_path: str,
        op: str,
        value: Any,
        session: AsyncSession | None = None,
    ) -> list[Record]:
        return list(await self._run("search", ivar_path, op, value, session=session))

    async def search_iter(
        self,
        ivar_path: str,
        op: str,
        value: Any,
        *,
        chunk_size: int = 256,
        session: AsyncSession | None = None,
    ) -> AsyncIterator[Record]:
        if self._closed:
            raise RuntimeError("AsyncGSCollection is closed")
        if session is not None:
            iterator = await session.run_sync(
                lambda sync_session: self._collection.search_iter(
                    ivar_path,
                    op,
                    value,
                    chunk_size=chunk_size,
                    session=sync_session,
                )
            )
            try:
                while True:
                    done, item = await session.run_sync(
                        lambda _sync_session: _next_or_end(iterator)
                    )
                    if done:
                        break
                    assert item is not None
                    yield item
            finally:
                await session.run_sync(lambda _sync_session: _close_iterator(iterator))
            return

        loop = asyncio.get_running_loop()
        iterator = await loop.run_in_executor(
            self._executor,
            lambda: self._collection.search_iter(
                ivar_path,
                op,
                value,
                chunk_size=chunk_size,
            ),
        )
        try:
            while True:
                done, item = await loop.run_in_executor(
                    self._executor,
                    lambda: _next_or_end(iterator),
                )
                if done:
                    break
                assert item is not None
                yield item
        finally:
            await loop.run_in_executor(self._executor, lambda: _close_iterator(iterator))

    async def all(self, session: AsyncSession | None = None) -> list[Record]:
        return list(await self._run("all", session=session))

    async def iter(
        self,
        *,
        chunk_size: int = 256,
        session: AsyncSession | None = None,
    ) -> AsyncIterator[Record]:
        if self._closed:
            raise RuntimeError("AsyncGSCollection is closed")
        if session is not None:
            iterator = await session.run_sync(
                lambda sync_session: self._collection.iter(
                    chunk_size=chunk_size,
                    session=sync_session,
                )
            )
            try:
                while True:
                    done, item = await session.run_sync(
                        lambda _sync_session: _next_or_end(iterator)
                    )
                    if done:
                        break
                    assert item is not None
                    yield item
            finally:
                await session.run_sync(lambda _sync_session: _close_iterator(iterator))
            return

        loop = asyncio.get_running_loop()
        iterator = await loop.run_in_executor(
            self._executor,
            lambda: self._collection.iter(chunk_size=chunk_size),
        )
        try:
            while True:
                done, item = await loop.run_in_executor(
                    self._executor,
                    lambda: _next_or_end(iterator),
                )
                if done:
                    break
                assert item is not None
                yield item
        finally:
            await loop.run_in_executor(self._executor, lambda: _close_iterator(iterator))

    async def size(self, session: AsyncSession | None = None) -> int:
        return int(await self._run("size", session=session))

    async def replace_all(
        self,
        elements: list[Record],
        session: AsyncSession | None = None,
    ) -> None:
        await self._run("replace_all", elements, session=session)

    async def delete_where(
        self,
        ivar_path: str,
        value: Any,
        session: AsyncSession | None = None,
    ) -> int:
        return int(await self._run("delete_where", ivar_path, value, session=session))

    async def bulk_delete_where(
        self,
        ivar_path: str,
        values: Iterable[Any],
        session: AsyncSession | None = None,
    ) -> int:
        return int(await self._run("bulk_delete_where", ivar_path, values, session=session))

    async def upsert_unique(
        self,
        ivar_path: str,
        element: Record,
        session: AsyncSession | None = None,
    ) -> None:
        await self._run("upsert_unique", ivar_path, element, session=session)

    async def bulk_upsert_unique(
        self,
        ivar_path: str,
        elements: Iterable[Record],
        session: AsyncSession | None = None,
    ) -> int:
        return int(await self._run("bulk_upsert_unique", ivar_path, elements, session=session))

    @staticmethod
    def intersect(a: list[Record], b: list[Record]) -> list[Record]:
        return GSCollection.intersect(a, b)

    @classmethod
    async def drop(
        cls,
        name: str,
        *,
        config: GemStoneConfig | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        if session is not None:
            await session.run_sync(lambda sync_session: GSCollection.drop(name, sync_session))
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: GSCollection.drop(name, config=config))

    @classmethod
    async def list(
        cls,
        *,
        config: GemStoneConfig | None = None,
        session: AsyncSession | None = None,
    ) -> list[str]:
        if session is not None:
            return await session.run_sync(lambda sync_session: GSCollection.list(sync_session))
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: GSCollection.list(config=config))


def _next_or_end(iterator: Iterator[Record]) -> tuple[bool, Record | None]:
    try:
        return False, next(iterator)
    except StopIteration:
        return True, None


def _close_iterator(iterator: Iterator[Record]) -> None:
    close = getattr(iterator, "close", None)
    if callable(close):
        close()


__all__ = ["AsyncGSCollection"]
