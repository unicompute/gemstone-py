"""Generated GemStone wrappers.

Source Protocol: examples.typed_access.codegen_demo.models.OkzBookingProto
Regenerate with `gemstone-codegen`; do not edit by hand.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gemstone_py import TypedOop

if TYPE_CHECKING:
    from .okz_customer import AsyncOkzCustomer, OkzCustomer


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


class OkzBooking(TypedOop[Any]):
    __gemstone_class_name__ = 'OkzBooking'

    @property
    def status(self) -> str:
        return self.send('status')

    @classmethod
    def find_by_id(cls, session: Any, booking_id: str) -> OkzBooking:
        source = _build_smalltalk_source(
            cls.__gemstone_class_name__,
            'findById:',
            (booking_id,),
        )
        oop = session.execute_oop(source)
        return cls(
            oop,
            session=session,
            wrapper_type=cls,
            gemstone_class_name=cls.__gemstone_class_name__,
        )

    def yourself(self) -> OkzBooking:
        oop = self.send_oop('yourself')
        return type(self)(
            oop,
            session=self.session,
            wrapper_type=type(self),
            gemstone_class_name=type(self).__gemstone_class_name__,
        )

    def customer(self) -> OkzCustomer:
        from .okz_customer import OkzCustomer
        oop = self.send_oop('customer')
        return OkzCustomer(
            oop,
            session=self.session,
            wrapper_type=OkzCustomer,
            gemstone_class_name=OkzCustomer.__gemstone_class_name__,
        )

    def mark_paid(self, at_posix_seconds: int) -> None:
        self.send('markPaid:', at_posix_seconds)

    def transfer(self, user_id: int, by_user_id: int) -> None:
        self.send('transferTo:byUserId:', user_id, by_user_id)


class AsyncOkzBooking(TypedOop[Any]):
    __gemstone_class_name__ = 'OkzBooking'

    async def status(self) -> str:
        session = self.session
        if session is None:
            raise RuntimeError("TypedOop has no associated GemStoneSession")
        return await session.perform_value(int(self), 'status')

    @classmethod
    async def find_by_id(cls, session: Any, booking_id: str) -> AsyncOkzBooking:
        source = _build_smalltalk_source(
            cls.__gemstone_class_name__,
            'findById:',
            (booking_id,),
        )
        oop = await session.execute_oop(source)
        return cls(
            oop,
            session=session,
            wrapper_type=cls,
            gemstone_class_name=cls.__gemstone_class_name__,
        )

    async def yourself(self) -> AsyncOkzBooking:
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

    async def customer(self) -> AsyncOkzCustomer:
        session = self.session
        if session is None:
            raise RuntimeError("TypedOop has no associated GemStoneSession")
        from .okz_customer import AsyncOkzCustomer
        oop = await session.perform_oop(int(self), 'customer')
        return AsyncOkzCustomer(
            oop,
            session=session,
            wrapper_type=AsyncOkzCustomer,
            gemstone_class_name=AsyncOkzCustomer.__gemstone_class_name__,
        )

    async def mark_paid(self, at_posix_seconds: int) -> None:
        session = self.session
        if session is None:
            raise RuntimeError("TypedOop has no associated GemStoneSession")
        raw_args = (_argument_to_oop(at_posix_seconds),)
        await session.perform_value(int(self), 'markPaid:', *raw_args)

    async def transfer(self, user_id: int, by_user_id: int) -> None:
        session = self.session
        if session is None:
            raise RuntimeError("TypedOop has no associated GemStoneSession")
        raw_args = (_argument_to_oop(user_id), _argument_to_oop(by_user_id))
        await session.perform_value(int(self), 'transferTo:byUserId:', *raw_args)


__all__ = ['OkzBooking', 'AsyncOkzBooking']
