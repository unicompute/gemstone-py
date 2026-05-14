from __future__ import annotations

from typing import Any

from gemstone_py import TypedOop

class OkzCustomer(TypedOop[Any]):
    __gemstone_class_name__: str
    __gemstone_protocol__: str
    __gemstone_selectors__: dict[str, str]
    @property
    def name(self) -> str: ...
    def yourself(self) -> OkzCustomer: ...


class AsyncOkzCustomer(TypedOop[Any]):
    __gemstone_class_name__: str
    __gemstone_protocol__: str
    __gemstone_selectors__: dict[str, str]
    async def name(self) -> str: ...
    async def yourself(self) -> AsyncOkzCustomer: ...
