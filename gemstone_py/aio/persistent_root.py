"""Async wrappers for ``gemstone_py.persistent_root``."""

from __future__ import annotations

from collections.abc import Awaitable, Iterable
from typing import Any, cast

from gemstone_py.aio import AsyncSession
from gemstone_py.ordered_collection import OrderedCollection
from gemstone_py.persistent_root import GsDict, PersistentRoot


class AsyncPersistentRoot:
    """Lazy async facade for ``PersistentRoot`` bound to an ``AsyncSession``."""

    def __init__(self, session: AsyncSession, name: str = "UserGlobals"):
        self._session = session
        self._name = name
        self._root: PersistentRoot | None = None

    @classmethod
    def globals(cls, session: AsyncSession) -> "AsyncPersistentRoot":
        return cls(session, "Globals")

    @classmethod
    def published(cls, session: AsyncSession) -> "AsyncPersistentRoot":
        return cls(session, "Published")

    @classmethod
    def session_methods(cls, session: AsyncSession) -> "AsyncPersistentRoot":
        return cls(session, "SessionMethods")

    def __getitem__(self, key: str) -> Awaitable[Any]:
        return self.get(key)

    async def set(self, key: str, value: Any) -> None:
        await self._session.run_sync(
            lambda sync_session: self._for_session(sync_session).__setitem__(key, value)
        )

    async def delete(self, key: str) -> None:
        await self._session.run_sync(
            lambda sync_session: self._for_session(sync_session).__delitem__(key)
        )

    async def get(self, key: str, default: Any = ...) -> Any:
        if default is ...:
            return await self._session.run_sync(
                lambda sync_session: _materialize_async_value(
                    self._for_session(sync_session).__getitem__(key)
                )
            )
        return await self._session.run_sync(
            lambda sync_session: _materialize_async_value(
                self._for_session(sync_session).get(key, default)
            )
        )

    async def contains(self, key: str) -> bool:
        return cast(
            bool,
            await self._session.run_sync(
                lambda sync_session: key in self._for_session(sync_session)
            ),
        )

    async def keys(self) -> list[str]:
        return cast(
            list[str],
            await self._session.run_sync(
                lambda sync_session: self._for_session(sync_session).keys()
            ),
        )

    async def items(self) -> list[tuple[str, Any]]:
        return cast(
            list[tuple[str, Any]],
            await self._session.run_sync(
                lambda sync_session: [
                    (key, _materialize_async_value(value))
                    for key, value in self._for_session(sync_session).items()
                ]
            ),
        )

    async def values(self) -> list[Any]:
        return cast(
            list[Any],
            await self._session.run_sync(
                lambda sync_session: [
                    _materialize_async_value(value)
                    for value in self._for_session(sync_session).values()
                ]
            ),
        )

    async def get_many(
        self,
        keys: Iterable[str],
        default: Any = None,
    ) -> dict[str, Any]:
        key_list = [str(key) for key in keys]
        return cast(
            dict[str, Any],
            await self._session.run_sync(
                lambda sync_session: {
                    key: _materialize_async_value(value)
                    for key, value in self._for_session(sync_session)
                    .get_many(key_list, default=default)
                    .items()
                }
            ),
        )

    async def pop(self, key: str, default: Any = ...) -> Any:
        if default is ...:
            return await self._session.run_sync(
                lambda sync_session: _materialize_async_value(
                    self._for_session(sync_session).pop(key)
                )
            )
        return await self._session.run_sync(
            lambda sync_session: _materialize_async_value(
                self._for_session(sync_session).pop(key, default)
            )
        )

    async def setdefault(self, key: str, default: Any = None) -> Any:
        return await self._session.run_sync(
            lambda sync_session: _materialize_async_value(
                self._for_session(sync_session).setdefault(key, default)
            )
        )

    async def update(self, other: Any = None, /, **kwargs: Any) -> None:
        await self._session.run_sync(
            lambda sync_session: self._for_session(sync_session).update(other, **kwargs)
        )

    async def update_many(self, other: Any = None, /, **kwargs: Any) -> None:
        await self._session.run_sync(
            lambda sync_session: self._for_session(sync_session).update_many(
                other,
                **kwargs,
            )
        )

    async def length(self) -> int:
        return cast(
            int,
            await self._session.run_sync(
                lambda sync_session: len(self._for_session(sync_session))
            ),
        )

    def _for_session(self, sync_session: Any) -> PersistentRoot:
        if self._root is None:
            self._root = PersistentRoot(sync_session, self._name)
        return self._root


def _materialize_async_value(value: Any) -> Any:
    """Return values that can be used safely outside the sync session thread."""
    if isinstance(value, GsDict):
        return {
            key: _materialize_async_value(value[key])
            for key in value.keys()
        }
    if isinstance(value, OrderedCollection):
        return [_materialize_async_value(item) for item in value.to_list()]
    if isinstance(value, list):
        return [_materialize_async_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_materialize_async_value(item) for item in value)
    if isinstance(value, dict):
        return {
            key: _materialize_async_value(item)
            for key, item in value.items()
        }
    return value


__all__ = ["AsyncPersistentRoot"]
