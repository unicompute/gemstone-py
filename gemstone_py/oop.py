"""Typed and managed GemStone OOP helper objects."""

from __future__ import annotations

import weakref
from collections.abc import Callable, Mapping
from typing import Any, ClassVar, Generic, Literal, Protocol, TypeVar, cast, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class GemStoneClassWrapper(Protocol):
    """Protocol marker for Python classes that describe a GemStone class."""

    __gemstone_class_name__: ClassVar[str]


class Oop(int):
    """GemStone object pointer value that remains usable as an ``int``."""

    def __new__(cls, value: int) -> "Oop":
        return int.__new__(cls, int(value))

    @property
    def oop(self) -> int:
        """Return the raw GemStone OOP integer."""
        return int(self)

    def __repr__(self) -> str:
        return f"Oop(0x{int(self):016X})"


class GemStoneObjectProxy(Generic[T]):
    """
    Runtime proxy for a typed GemStone OOP.

    Static typing comes from ``TypedOop[T].proxy()`` returning ``T``. At runtime,
    attribute access sends the same-named Smalltalk selector to the OOP.
    """

    def __init__(self, typed_oop: "TypedOop[T]"):
        self._typed_oop = typed_oop

    @property
    def oop(self) -> int:
        return self._typed_oop.oop

    def send(self, selector: str, *args: Any) -> Any:
        return self._typed_oop.send(selector, *args)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        return self.send(name.replace("_", ":"))

    def __repr__(self) -> str:
        typed_oop = object.__getattribute__(self, "_typed_oop")
        return f"<GemStoneObjectProxy {typed_oop!r}>"


class TypedOop(Oop, Generic[T]):
    """GemStone OOP carrying a phantom Python type for static analysis."""

    _session: Any | None
    _wrapper_type: type[T] | None
    _gemstone_class_name: str | None

    def __new__(
        cls,
        value: int,
        session: Any | None = None,
        wrapper_type: type[T] | None = None,
        gemstone_class_name: str | None = None,
    ) -> "TypedOop[T]":
        obj = int.__new__(cls, int(value))
        obj._session = session
        obj._wrapper_type = wrapper_type
        obj._gemstone_class_name = gemstone_class_name or _class_name_for(wrapper_type)
        return obj

    @property
    def session(self) -> Any | None:
        """Session associated with this OOP, if it was created by a session."""
        return getattr(self, "_session", None)

    @property
    def wrapper_type(self) -> type[T] | None:
        """Python wrapper/protocol type used as the phantom type witness."""
        return cast(type[T] | None, getattr(self, "_wrapper_type", None))

    @property
    def gemstone_class_name(self) -> str | None:
        """GemStone-side class name registered for this OOP, if known."""
        return cast(str | None, getattr(self, "_gemstone_class_name", None))

    def send(self, selector: str, *args: Any) -> Any:
        """Send a Smalltalk selector through the associated session."""
        session = self.session
        if session is None:
            raise RuntimeError("TypedOop has no associated GemStoneSession")
        return session.perform_value(int(self), selector, *[_argument_to_oop(arg) for arg in args])

    def send_oop(self, selector: str, *args: Any) -> "TypedOop[Any]":
        """Send a selector and keep the raw result as another typed OOP."""
        session = self.session
        if session is None:
            raise RuntimeError("TypedOop has no associated GemStoneSession")
        oop = session.perform_oop(int(self), selector, *[_argument_to_oop(arg) for arg in args])
        return TypedOop(oop, session)

    def proxy(self) -> T:
        """Return a runtime proxy typed as the registered Python wrapper ``T``."""
        return cast(T, GemStoneObjectProxy(self))

    def __repr__(self) -> str:
        class_name = self.gemstone_class_name
        suffix = f", class={class_name}" if class_name else ""
        return f"TypedOop(0x{int(self):016X}{suffix})"


class ManagedOop:
    """Reference-counted OOP handle retained in the GemStone export set."""

    def __init__(self, oop: int, session: Any):
        self._oop = int(oop)
        self._session = session
        self._finalizer = weakref.finalize(self, session._release_managed_oop, self._oop)
        session._retain_managed_oop(self._oop)

    @property
    def oop(self) -> int:
        return self._oop

    @property
    def session(self) -> Any:
        return self._session

    def close(self) -> None:
        """Release this handle's export-set reference immediately."""
        self._finalizer()

    def detach(self) -> int:
        """Stop automatic cleanup and return the raw OOP."""
        self._finalizer.detach()
        return self._oop

    def send(self, selector: str, *args: Any) -> Any:
        return self._session.perform_value(
            self._oop,
            selector,
            *[_argument_to_oop(arg) for arg in args],
        )

    def send_oop(self, selector: str, *args: Any) -> int:
        oop = self._session.perform_oop(
            self._oop,
            selector,
            *[_argument_to_oop(arg) for arg in args],
        )
        return cast(
            int,
            oop,
        )

    def print_string(self) -> str:
        return cast(str, self.send("printString"))

    def __int__(self) -> int:
        return self._oop

    def __index__(self) -> int:
        return self._oop

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ManagedOop):
            return self._oop == other._oop
        if isinstance(other, int):
            return self._oop == other
        return False

    def __hash__(self) -> int:
        return hash(self._oop)

    def __repr__(self) -> str:
        return f"<ManagedOop 0x{self._oop:016X}>"


class OopHandle:
    """Explicit context-managed export-set handle for a raw OOP."""

    def __init__(self, oop: int, session: Any):
        self._oop = int(oop)
        self._session = session
        self._entered = False

    @property
    def oop(self) -> int:
        return self._oop

    def __enter__(self) -> "OopHandle":
        if not self._entered:
            self._session._retain_managed_oop(self._oop)
            self._entered = True
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> Literal[False]:
        if self._entered:
            self._session._release_managed_oop(self._oop)
            self._entered = False
        return False

    def send(self, selector: str, *args: Any) -> Any:
        return self._session.perform_value(
            self._oop,
            selector,
            *[_argument_to_oop(arg) for arg in args],
        )

    def send_oop(self, selector: str, *args: Any) -> int:
        oop = self._session.perform_oop(
            self._oop,
            selector,
            *[_argument_to_oop(arg) for arg in args],
        )
        return cast(
            int,
            oop,
        )

    def __int__(self) -> int:
        return self._oop

    def __index__(self) -> int:
        return self._oop

    def __repr__(self) -> str:
        return f"<OopHandle 0x{self._oop:016X}>"


_REGISTRY: dict[str, type[Any]] = {}
_CLASS_NAMES: weakref.WeakKeyDictionary[type[Any], str] = weakref.WeakKeyDictionary()


def gemstone_class(name: str) -> Callable[[type[T]], type[T]]:
    """Register a Python class or protocol as describing a GemStone class."""

    def decorator(cls: type[T]) -> type[T]:
        setattr(cls, "__gemstone_class_name__", name)
        _REGISTRY[name] = cls
        _CLASS_NAMES[cls] = name
        return cls

    return decorator


def gemstone_class_name(cls: type[Any]) -> str | None:
    """Return the registered GemStone class name for ``cls`` if present."""
    return _class_name_for(cls)


def registered_gemstone_classes() -> Mapping[str, type[Any]]:
    """Return a snapshot of registered GemStone class wrappers."""
    return dict(_REGISTRY)


def typed_oop(
    oop: int,
    cls: type[T],
    *,
    session: Any | None = None,
    gemstone_class_name: str | None = None,
) -> TypedOop[T]:
    """Build a ``TypedOop[T]`` from a raw OOP and type witness."""
    return TypedOop(oop, session, cls, gemstone_class_name)


def _class_name_for(cls: type[Any] | None) -> str | None:
    if cls is None:
        return None
    explicit = getattr(cls, "__gemstone_class_name__", None)
    if isinstance(explicit, str):
        return explicit
    return _CLASS_NAMES.get(cls)


def _argument_to_oop(arg: Any) -> int:
    if isinstance(arg, ManagedOop):
        return arg.oop
    if isinstance(arg, OopHandle):
        return arg.oop
    if isinstance(arg, Oop):
        return arg.oop
    if hasattr(arg, "oop"):
        return int(getattr(arg, "oop"))
    return cast(int, arg)


__all__ = [
    "GemStoneClassWrapper",
    "GemStoneObjectProxy",
    "ManagedOop",
    "Oop",
    "OopHandle",
    "TypedOop",
    "gemstone_class",
    "gemstone_class_name",
    "registered_gemstone_classes",
    "typed_oop",
]
