"""Generated GemStone wrappers.

Source Protocol: examples.typed_access.codegen_demo.models.OkzCustomerProto
Regenerate with `gemstone-codegen`; do not edit by hand.
"""

from __future__ import annotations

from typing import Any

from gemstone_py import OOP_FALSE, OOP_NIL, OOP_TRUE, TypedOop


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


def _argument_to_oop(session: Any, value: Any) -> int:
    if hasattr(value, "oop"):
        return int(getattr(value, "oop"))
    if value is None:
        return int(OOP_NIL)
    if value is True:
        return int(OOP_TRUE)
    if value is False:
        return int(OOP_FALSE)
    if isinstance(value, int):
        return int(session.int_oop(value))
    if isinstance(value, float):
        return int(session.float_oop(value))
    if isinstance(value, str):
        return int(session.new_string(value))
    return int(value)


async def _argument_to_oop_async(session: Any, value: Any) -> int:
    if hasattr(value, "oop"):
        return int(getattr(value, "oop"))
    if value is None:
        return int(OOP_NIL)
    if value is True:
        return int(OOP_TRUE)
    if value is False:
        return int(OOP_FALSE)
    if isinstance(value, int):
        return int(session.int_oop(value))
    if isinstance(value, float):
        return int(await session.float_oop(value))
    if isinstance(value, str):
        return int(await session.new_string(value))
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
    """Typed wrapper for the GemStone class 'OkzCustomer'."""

    __gemstone_class_name__ = 'OkzCustomer'

    @property
    def name(self) -> str:
        """Send the 'name' selector to this GemStone object."""
        return self.send('name')

    def yourself(self) -> OkzCustomer:
        """Send the 'yourself' selector to this GemStone object."""
        session = self.session
        if session is None:
            raise RuntimeError("TypedOop has no associated GemStoneSession")
        oop = session.perform_oop(int(self), 'yourself')
        return type(self)(
            oop,
            session=session,
            wrapper_type=type(self),
            gemstone_class_name=type(self).__gemstone_class_name__,
        )


class AsyncOkzCustomer(TypedOop[Any]):
    """Typed wrapper for the GemStone class 'OkzCustomer'."""

    __gemstone_class_name__ = 'OkzCustomer'

    async def name(self) -> str:
        """Send the 'name' selector to this GemStone object."""
        session = self.session
        if session is None:
            raise RuntimeError("TypedOop has no associated GemStoneSession")
        return await session.perform_value(int(self), 'name')

    async def yourself(self) -> AsyncOkzCustomer:
        """Send the 'yourself' selector to this GemStone object."""
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
