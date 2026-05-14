"""Explicit, opt-in Python value converters for GemStone objects."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Generic, TypeVar
from uuid import UUID

from gemstone_py.client import GemStoneSession
from gemstone_py.oop import Oop

T = TypeVar("T")


@dataclass(frozen=True)
class ValueConverter(Generic[T]):
    """One explicit Python-value to GemStone-OOP converter."""

    name: str
    python_type: type[T]
    to_oop_fn: Callable[[GemStoneSession, T], int]
    from_oop_fn: Callable[[GemStoneSession, int], T] | None = None
    exact_type: bool = False

    def matches(self, value: object) -> bool:
        """Return true when this converter should handle ``value``."""
        if self.exact_type:
            return type(value) is self.python_type
        return isinstance(value, self.python_type)

    def to_oop(self, session: GemStoneSession, value: T) -> int:
        """Convert a Python value to a raw GemStone OOP."""
        if not self.matches(value):
            raise TypeError(
                f"{self.name} cannot convert {type(value).__name__!r}; "
                f"expected {self.python_type.__name__!r}"
            )
        return int(self.to_oop_fn(session, value))

    def wrap_oop(self, session: GemStoneSession, value: T) -> Oop:
        """Convert a Python value to an ``Oop`` marker safe to pass to gemstone-py APIs."""
        return Oop(self.to_oop(session, value))

    def from_oop(self, session: GemStoneSession, oop: int) -> T:
        """Convert a raw GemStone OOP back to Python using this converter."""
        if self.from_oop_fn is None:
            raise TypeError(f"{self.name} does not define from_oop conversion")
        return self.from_oop_fn(session, int(oop))


class ValueConverterRegistry:
    """Ordered registry for explicit value conversion."""

    def __init__(self, converters: Iterable[ValueConverter[Any]] = ()):
        self._converters = list(converters)

    def register(self, converter: ValueConverter[Any]) -> None:
        """Append a converter after the existing converters."""
        self._converters.append(converter)

    def extend(self, converters: Iterable[ValueConverter[Any]]) -> None:
        """Append converters after the existing converters."""
        self._converters.extend(converters)

    def copy(self) -> "ValueConverterRegistry":
        """Return an independent registry with the same converters in the same order."""
        return ValueConverterRegistry(self._converters)

    def converter_for(self, value: object) -> ValueConverter[Any] | None:
        """Return the first converter registered for ``value``."""
        for converter in self._converters:
            if converter.matches(value):
                return converter
        return None

    def to_oop(self, session: GemStoneSession, value: object) -> Oop:
        """Convert ``value`` to an ``Oop`` marker using a registered converter."""
        converter = self.converter_for(value)
        if converter is None:
            raise TypeError(f"No value converter registered for {type(value).__name__!r}")
        return Oop(converter.to_oop(session, value))

    def to_oops(self, session: GemStoneSession, values: Iterable[object]) -> list[Oop]:
        """Convert ``values`` to ``Oop`` markers using registered converters."""
        return [self.to_oop(session, value) for value in values]

    def from_oop(self, name: str, session: GemStoneSession, oop: int) -> object:
        """Convert ``oop`` through a registered converter selected by name."""
        for converter in self._converters:
            if converter.name == name:
                return converter.from_oop(session, oop)
        raise KeyError(name)

    def from_oops(self, name: str, session: GemStoneSession, oops: Iterable[int]) -> list[object]:
        """Convert ``oops`` through a registered converter selected by name."""
        return [self.from_oop(name, session, oop) for oop in oops]

    def names(self) -> tuple[str, ...]:
        """Return registered converter names in matching order."""
        return tuple(converter.name for converter in self._converters)


def datetime_converter() -> ValueConverter[datetime]:
    """Convert ``datetime`` to GemStone ``DateAndTime`` via existing helpers."""
    from gemstone_py.concurrency import datetime_to_gs, gs_datetime

    return ValueConverter(
        name="datetime",
        python_type=datetime,
        to_oop_fn=datetime_to_gs,
        from_oop_fn=gs_datetime,
    )


def date_as_iso_string_converter() -> ValueConverter[date]:
    """Convert exact ``date`` values to ISO-8601 GemStone strings."""
    return ValueConverter(
        name="date_iso_string",
        python_type=date,
        exact_type=True,
        to_oop_fn=lambda session, value: session.new_string(value.isoformat()),
        from_oop_fn=lambda session, oop: date.fromisoformat(session.fetch_string(oop)),
    )


def decimal_as_string_converter() -> ValueConverter[Decimal]:
    """Convert ``Decimal`` values to exact decimal text in GemStone strings."""
    return ValueConverter(
        name="decimal_string",
        python_type=Decimal,
        to_oop_fn=lambda session, value: session.new_string(str(value)),
        from_oop_fn=lambda session, oop: Decimal(session.fetch_string(oop)),
    )


def uuid_as_string_converter() -> ValueConverter[UUID]:
    """Convert ``UUID`` values to canonical GemStone strings."""
    return ValueConverter(
        name="uuid_string",
        python_type=UUID,
        to_oop_fn=lambda session, value: session.new_string(str(value)),
        from_oop_fn=lambda session, oop: UUID(session.fetch_string(oop)),
    )


def scalar_value_converter_registry() -> ValueConverterRegistry:
    """Return a registry with the built-in scalar-ish converters."""
    return ValueConverterRegistry(
        [
            datetime_converter(),
            date_as_iso_string_converter(),
            decimal_as_string_converter(),
            uuid_as_string_converter(),
        ]
    )


def dataclass_to_dict(value: object, *, recurse: bool = True) -> dict[str, Any]:
    """Convert a dataclass instance to a plain dict before explicit persistence."""
    if not is_dataclass(value) or isinstance(value, type):
        raise TypeError(f"Expected a dataclass instance, got {type(value).__name__!r}")
    if recurse:
        return asdict(value)
    return {field.name: getattr(value, field.name) for field in fields(value)}


__all__ = [
    "ValueConverter",
    "ValueConverterRegistry",
    "dataclass_to_dict",
    "date_as_iso_string_converter",
    "datetime_converter",
    "decimal_as_string_converter",
    "scalar_value_converter_registry",
    "uuid_as_string_converter",
]
