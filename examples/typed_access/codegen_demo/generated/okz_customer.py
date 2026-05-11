"""Generated GemStone wrappers.

Source Protocol: examples.typed_access.codegen_demo.models.OkzCustomerProto
Regenerate with `gemstone-codegen`; do not edit by hand.
"""

from __future__ import annotations

from typing import Any

from gemstone_py import TypedOop


def _smalltalk_literal(value: Any) -> str:
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, int | float):
        return repr(value)
    custom = getattr(value, "__smalltalk_source__", None)
    if callable(custom):
        return str(custom())
    raise TypeError(f"cannot convert {type(value).__name__} to a Smalltalk literal")


def _argument_to_oop(value: Any) -> int:
    if hasattr(value, "oop"):
        return int(getattr(value, "oop"))
    return int(value)


def _build_smalltalk_source(receiver: str, selector: str, args: tuple[Any, ...]) -> str:
    keywords = tuple(part for part in selector.split(":")[:-1] if part)
    if not keywords:
        if args:
            raise TypeError(f"selector {selector!r} does not accept arguments")
        return f"{receiver} {selector}"
    if len(keywords) != len(args):
        raise TypeError(f"selector {selector!r} expects {len(keywords)} argument(s)")
    pieces = [receiver]
    for keyword, arg in zip(keywords, args):
        pieces.append(f"{keyword}:")
        pieces.append(_smalltalk_literal(arg))
    return " ".join(pieces)


class OkzCustomer(TypedOop[Any]):
    __gemstone_class_name__ = 'OkzCustomer'

    @property
    def name(self) -> str:
        return self.send('name')

    def yourself(self) -> OkzCustomer:
        oop = self.send_oop('yourself')
        return type(self)(
            oop,
            session=self.session,
            wrapper_type=type(self),
            gemstone_class_name=type(self).__gemstone_class_name__,
        )


class AsyncOkzCustomer(TypedOop[Any]):
    __gemstone_class_name__ = 'OkzCustomer'

    async def name(self) -> str:
        session = self.session
        if session is None:
            raise RuntimeError("TypedOop has no associated GemStoneSession")
        return await session.perform_value(int(self), 'name')

    async def yourself(self) -> AsyncOkzCustomer:
        session = self.session
        if session is None:
            raise RuntimeError("TypedOop has no associated GemStoneSession")
        oop = await session.perform_oop(int(self), 'yourself')
        return type(self)(
            oop,
            session=session,
            wrapper_type=type(self),
            gemstone_class_name=type(self).__gemstone_class_name__,
        )


__all__ = ['OkzCustomer', 'AsyncOkzCustomer']
