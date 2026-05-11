"""Protocol definitions consumed by ``gemstone-codegen``."""

from __future__ import annotations

from typing import Protocol

from gemstone_py import gemstone_class, gemstone_selector


@gemstone_class("OkzBooking", async_=True)
class OkzBookingProto(Protocol):
    """Python-side type contract for a GemStone ``OkzBooking`` object."""

    status: str

    @classmethod
    @gemstone_selector("findById:")
    def find_by_id(cls, booking_id: str) -> "OkzBookingProto":
        ...

    def mark_paid(self, at_posix_seconds: int) -> None:
        ...

    @gemstone_selector("transferTo:byUserId:")
    def transfer(self, user_id: int, by_user_id: int) -> None:
        ...
