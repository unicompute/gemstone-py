"""GemStone session/config client built on the low-level GCI helpers."""

from __future__ import annotations

import ctypes
import logging
import os
import threading
import time
from collections import Counter
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from types import TracebackType
from typing import Any, Iterator, Literal, Optional, Sequence, TypeVar, cast

from ._gci import (
    GCI_ENCRYPT_BUF_SIZE,
    GCI_INVALID_SESSION,
    OOP_FALSE,
    OOP_ILLEGAL,
    OOP_NIL,
    OOP_TRUE,
    GciErrSType,
    _bind,
    _char_to_python,
    _is_char,
    _is_smallint,
    _load_library,
    _python_to_smallint,
    _smallint_to_python,
)
from .observability import (
    NULL_METRICS,
    NULL_SPAN,
    NULL_TRACER,
    MetricsCollector,
    Span,
    Tracer,
)
from .oop import ManagedOop, Oop, OopHandle, TypedOop

__all__ = [
    "GemStoneError",
    "GemStoneConfigurationError",
    "TransactionPolicy",
    "GemStoneConfig",
    "GemStoneSession",
    "ManagedOop",
    "OopRef",
    "OopHandle",
    "TypedOop",
    "connect",
]

T = TypeVar("T")


class GemStoneError(RuntimeError):
    """Raised when a GCI call returns an error."""

    def __init__(self, message: str, number: int = 0, fatal: bool = False):
        super().__init__(message)
        self.number = number
        self.fatal = fatal

    @classmethod
    def from_err_struct(cls, err: GciErrSType) -> "GemStoneError":
        msg = err.message.decode("utf-8", errors="replace").rstrip("\x00")
        reason = err.reason.decode("utf-8", errors="replace").rstrip("\x00")
        full = msg if not reason or reason == msg else f"{msg} [{reason}]"
        return cls(
            full or f"GemStone error #{err.number}",
            number=err.number,
            fatal=bool(err.fatal),
        )


class GemStoneConfigurationError(ValueError):
    """Raised when a session is missing required connection configuration."""


class TransactionPolicy(str, Enum):
    """How a GemStoneSession context manager should end its transaction."""

    MANUAL = "manual"
    COMMIT_ON_SUCCESS = "commit_on_success"
    ABORT_ON_EXIT = "abort_on_exit"

    @classmethod
    def coerce(cls, value: "TransactionPolicy | str") -> "TransactionPolicy":
        if isinstance(value, cls):
            return value
        try:
            return cls(value)
        except ValueError as exc:
            options = ", ".join(policy.value for policy in cls)
            raise ValueError(
                f"Unknown transaction policy {value!r}. Expected one of: {options}"
            ) from exc


@dataclass(frozen=True)
class GemStoneConfig:
    """
    Explicit GemStone connection settings.

    Credentials are intentionally not defaulted here. Callers should pass
    them directly or rely on `from_env()`.
    """

    stone: str = "gs64stone"
    netldi: str = "netldi"
    host: str = "localhost"
    username: Optional[str] = None
    password: Optional[str] = None
    host_username: str = ""
    host_password: str = ""
    gem_service: str = "gemnetobject"
    lib_path: Optional[str] = None

    @classmethod
    def from_env(cls, *, require_credentials: bool = True) -> "GemStoneConfig":
        config = cls(
            stone=os.environ.get("GS_STONE") or os.environ.get("GS_STONE_NAME", "gs64stone"),
            netldi=os.environ.get("GS_NETLDI", "netldi"),
            host=os.environ.get("GS_HOST", "localhost"),
            username=os.environ.get("GS_USERNAME"),
            password=os.environ.get("GS_PASSWORD"),
            host_username=os.environ.get("GS_HOST_USERNAME", ""),
            host_password=os.environ.get("GS_HOST_PASSWORD", ""),
            gem_service=os.environ.get("GS_GEM_SERVICE", "gemnetobject"),
            lib_path=os.environ.get("GS_LIB_PATH"),
        )
        if require_credentials:
            config.require_credentials()
        return config

    def require_credentials(self) -> "GemStoneConfig":
        missing = []
        if not self.username:
            missing.append("GS_USERNAME")
        if not self.password:
            missing.append("GS_PASSWORD")
        if missing:
            missing_vars = " and ".join(missing)
            raise GemStoneConfigurationError(
                "GemStone credentials are required. Pass username/password explicitly "
                f"or set {missing_vars}."
            )
        return self

    def as_session_kwargs(self) -> dict[str, Any]:
        return {
            "stone": self.stone,
            "netldi": self.netldi,
            "host": self.host,
            "username": self.username,
            "password": self.password,
            "host_username": self.host_username,
            "host_password": self.host_password,
            "gem_service": self.gem_service,
            "lib_path": self.lib_path,
        }


def _safe_set_attribute(span: Span, key: str, value: str | int | float | bool | None) -> None:
    try:
        span.set_attribute(key, value)
    except Exception:
        pass


def _safe_record_exception(span: Span, exc: BaseException) -> None:
    try:
        span.record_exception(exc)
    except Exception:
        pass


def _smalltalk_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _bulk_perform_source(receivers: Sequence[int], selector: str, args: Sequence[int]) -> str:
    receiver_puts = "".join(
        f"receivers at: {index} put: (Object _objectForOop: {receiver}).\n"
        for index, receiver in enumerate(receivers, 1)
    )
    arg_puts = "".join(
        f"args at: {index} put: (Object _objectForOop: {arg}).\n"
        for index, arg in enumerate(args, 1)
    )
    selector_literal = _smalltalk_string_literal(selector)
    return (
        "| receivers args selector stream |\n"
        f"receivers := Array new: {len(receivers)}.\n"
        f"{receiver_puts}"
        f"args := Array new: {len(args)}.\n"
        f"{arg_puts}"
        f"selector := {selector_literal} asSymbol.\n"
        "stream := ''.\n"
        "1 to: receivers size do: [:index | | result |\n"
        "  result := (receivers at: index) perform: selector withArguments: args.\n"
        "  stream := stream, result asOop asString, String lf asString\n"
        "].\n"
        "stream"
    )


class GemStoneSession:
    """A GemStone GCI session."""

    def __init__(
        self,
        stone: Optional[str] = None,
        netldi: Optional[str] = None,
        host: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        host_username: Optional[str] = None,
        host_password: Optional[str] = None,
        gem_service: Optional[str] = None,
        lib_path: Optional[str] = None,
        *,
        config: Optional[GemStoneConfig] = None,
        transaction_policy: TransactionPolicy | str = TransactionPolicy.MANUAL,
        tracer: Tracer | None = None,
        metrics: MetricsCollector | None = None,
        slow_query_threshold_ms: float | None = None,
    ):
        base = config or GemStoneConfig()
        self.config = GemStoneConfig(
            stone=stone if stone is not None else base.stone,
            netldi=netldi if netldi is not None else base.netldi,
            host=host if host is not None else base.host,
            username=username if username is not None else base.username,
            password=password if password is not None else base.password,
            host_username=host_username if host_username is not None else base.host_username,
            host_password=host_password if host_password is not None else base.host_password,
            gem_service=gem_service if gem_service is not None else base.gem_service,
            lib_path=lib_path if lib_path is not None else base.lib_path,
        )
        self.transaction_policy = TransactionPolicy.coerce(transaction_policy)
        self.tracer = tracer or NULL_TRACER
        self.metrics = metrics or NULL_METRICS
        self.slow_query_threshold_ms = slow_query_threshold_ms
        self.stone = self.config.stone
        self.netldi = self.config.netldi
        self.host = self.config.host
        self.username = self.config.username
        self.password = self.config.password
        self.host_username = self.config.host_username
        self.host_password = self.config.host_password
        self.gem_service = self.config.gem_service
        self._lib_path = self.config.lib_path
        self._lib: Optional[ctypes.CDLL] = None
        self._session_id: int = GCI_INVALID_SESSION
        self._logged_in: bool = False
        self.__string_class_oops_cache: frozenset[int] | None = None
        self._managed_oop_counts: Counter[int] = Counter()
        self._managed_oop_pending_removals: Counter[int] = Counter()
        self._managed_oop_lock = threading.RLock()
        self._managed_oop_draining = False
        self._owner_thread_id: int | None = None

    @property
    def owner_thread_id(self) -> int | None:
        """Return the Python thread currently allowed to use this session."""
        return self._owner_thread_id

    def __enter__(self) -> "GemStoneSession":
        self.login()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        try:
            if exc_type is None:
                if self.transaction_policy is TransactionPolicy.COMMIT_ON_SUCCESS:
                    self.commit()
                elif self.transaction_policy is TransactionPolicy.ABORT_ON_EXIT:
                    try:
                        self.abort()
                    except Exception:
                        pass
            else:
                try:
                    self.abort()
                except Exception:
                    pass
        finally:
            self.logout()
        return False

    def _ensure_lib(self) -> None:
        if self._lib is not None:
            return
        lib = _load_library(self._lib_path)
        self._lib = lib
        _bind(lib)
        lib.GciInit()

    def _require_lib(self) -> ctypes.CDLL:
        lib = self._lib
        if lib is None:
            raise GemStoneError("GCI library is not loaded. Call login() first.")
        return lib

    @contextmanager
    def _observe_operation(
        self,
        operation: str,
        attrs: dict[str, str | int | float | bool | None] | None = None,
    ) -> Iterator[Span]:
        tracer = self.tracer
        metrics = self.metrics
        threshold = self.slow_query_threshold_ms
        if tracer is NULL_TRACER and metrics is NULL_METRICS and threshold is None:
            yield NULL_SPAN
            return

        attributes: dict[str, str | int | float | bool | None] = {
            "operation": operation,
            "stone": self.stone,
            "host": self.host,
        }
        if attrs:
            attributes.update(attrs)

        started_at = time.perf_counter()
        span_context = tracer.start_span(f"gemstone.session.{operation}", attributes)
        span = span_context.__enter__()
        status = "ok"
        error_type: str | None = None
        exc_info: tuple[type[BaseException] | None, BaseException | None, TracebackType | None] = (
            None,
            None,
            None,
        )
        try:
            yield span
        except BaseException as exc:
            status = "error"
            error_type = type(exc).__name__
            exc_info = (type(exc), exc, exc.__traceback__)
            _safe_record_exception(span, exc)
            _safe_set_attribute(span, "error", error_type)
            raise
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1000.0
            _safe_set_attribute(span, "status", status)
            _safe_set_attribute(span, "duration_ms", duration_ms)
            span_context.__exit__(*exc_info)
            labels = {"operation": operation, "status": status}
            metrics.increment("gemstone_py_session_operations", labels)
            metrics.record_duration("gemstone_py_session_duration_ms", labels, duration_ms)
            if threshold is not None and duration_ms >= threshold:
                logger = logging.getLogger("gemstone_py.slow_queries")
                message = f"slow GemStone operation {operation} took {duration_ms:.3f}ms"
                extra: dict[str, object] = {
                    "gemstone_operation": operation,
                    "duration_ms": duration_ms,
                    "stone": self.stone,
                    "host": self.host,
                    "session_id": self._session_id,
                    "status": status,
                }
                if error_type is not None:
                    extra["error"] = error_type
                logger.warning(message, extra=extra)

    def login(self) -> None:
        self.config.require_credentials()
        with self._observe_operation("login"):
            self._ensure_lib()
            lib = self._require_lib()
            username = self.username
            password = self.password
            assert username is not None
            assert password is not None

            host = self.host or ""
            if host and host not in ("localhost", "127.0.0.1"):
                stone_nrs = f"!@{host}!{self.netldi}!{self.stone}"
            else:
                stone_nrs = self.stone

            gem_service = self.gem_service or "gemnetobject"

            enc_buf = ctypes.create_string_buffer(GCI_ENCRYPT_BUF_SIZE)
            host_pw = (self.host_password or "").encode("latin-1")
            lib.GciEncrypt(host_pw if host_pw else b"", enc_buf, GCI_ENCRYPT_BUF_SIZE)

            lib.GciSetNet(
                stone_nrs.encode("utf-8"),
                (self.host_username or "").encode("latin-1"),
                enc_buf,
                gem_service.encode("utf-8"),
            )

            ok = lib.GciLoginEx(
                username.encode("utf-8"),
                password.encode("utf-8"),
                0,
                0,
            )

            if not ok:
                err = GciErrSType()
                lib.GciErr(ctypes.byref(err))
                raise GemStoneError.from_err_struct(err)

            self._session_id = lib.GciGetSessionId()
            self._logged_in = True
            self._owner_thread_id = threading.get_ident()

    def logout(self) -> None:
        if not self._logged_in or self._lib is None:
            return
        with self._observe_operation("logout"):
            lib = self._activate_session()
            try:
                lib.GciLogout()
            finally:
                self._logged_in = False
                self._session_id = GCI_INVALID_SESSION
                self._owner_thread_id = None
                with self._managed_oop_lock:
                    self._managed_oop_counts.clear()
                    self._managed_oop_pending_removals.clear()

    def commit(self) -> None:
        with self._observe_operation("commit"):
            lib = self._require_login()
            err = GciErrSType()
            ok = lib.GciCommit(ctypes.byref(err))
            if not ok:
                raise GemStoneError.from_err_struct(err)

    def abort(self) -> None:
        with self._observe_operation("abort"):
            lib = self._require_login()
            err = GciErrSType()
            ok = lib.GciAbort(ctypes.byref(err))
            if ok:
                return
            if err.number != 0:
                raise GemStoneError.from_err_struct(err)
            oop = int(
                lib.GciExecuteStr(
                    b"System abortTransaction",
                    ctypes.c_uint64(OOP_NIL),
                )
            )
            self._check_result(oop)

    def needs_commit(self) -> bool:
        with self._observe_operation("needs_commit"):
            lib = self._require_login()
            return bool(lib.GciNeedsCommit())

    def in_transaction(self) -> bool:
        with self._observe_operation("in_transaction"):
            lib = self._require_login()
            return bool(lib.GciInTransaction())

    def eval(self, source: str) -> Any:
        with self._observe_operation("eval", {"source_length": len(source)}):
            oop = self._execute_str_oop(source)
            return self._marshal(oop)

    def eval_oop(self, source: str) -> int:
        with self._observe_operation("eval_oop", {"source_length": len(source)}):
            return self._execute_str_oop(source)

    def _execute_str_oop(self, source: str) -> int:
        lib = self._require_login()
        oop = int(lib.GciExecuteStr(source.encode("utf-8"), ctypes.c_uint64(OOP_NIL)))
        self._check_result(oop)
        return oop

    def execute(self, source: str) -> int:
        """Evaluate Smalltalk source and return the raw result OOP."""
        return self.execute_oop(source)

    def execute_oop(self, source: str) -> int:
        """Evaluate Smalltalk source and return the raw result OOP."""
        with self._observe_operation("execute_oop", {"source_length": len(source)}):
            return self._execute_str_oop(source)

    def execute_typed(self, source: str, cls: type[T]) -> TypedOop[T]:
        """Evaluate source and return a phantom-typed OOP."""
        return TypedOop(self.eval_oop(source), self, cls)

    def execute_managed(self, source: str) -> ManagedOop:
        """Evaluate source and retain the raw result OOP in the export set."""
        return self.eval_managed(source)

    def eval_managed(self, source: str) -> ManagedOop:
        """Evaluate source and retain the raw result OOP in the export set."""
        return self.managed_oop(self.eval_oop(source))

    def perform_value(self, receiver: int, selector: str, *args: int) -> Any:
        """Perform a selector and marshal the result to a Python value."""
        with self._observe_operation("perform_value", {"selector": selector, "argc": len(args)}):
            oop = self._perform_oop_raw(receiver, selector, *args)
            return self._marshal(oop)

    def perform(self, receiver: int, selector: str, *args: int) -> int:
        """Perform a selector and return the raw result OOP."""
        return self.perform_oop(receiver, selector, *args)

    def perform_oop(self, receiver: int, selector: str, *args: int) -> int:
        with self._observe_operation("perform_oop", {"selector": selector, "argc": len(args)}):
            return self._perform_oop_raw(receiver, selector, *args)

    def bulk_perform_oop(
        self,
        receivers: Iterable[int],
        selector: str,
        *args: int,
    ) -> list[int]:
        """Perform one selector across several receiver OOPs in one eval."""
        receiver_oops = [int(receiver) for receiver in receivers]
        if not receiver_oops:
            return []
        with self._observe_operation(
            "bulk_perform_oop",
            {"selector": selector, "argc": len(args), "receiver_count": len(receiver_oops)},
        ):
            raw = self.eval(_bulk_perform_source(receiver_oops, selector, args))
        if raw is None:
            return []
        return [int(line) for line in str(raw).splitlines() if line]

    def bulk_perform_value(
        self,
        receivers: Iterable[int],
        selector: str,
        *args: int,
    ) -> list[Any]:
        """Perform one selector across several receiver OOPs and marshal results."""
        return [self._marshal(oop) for oop in self.bulk_perform_oop(receivers, selector, *args)]

    def perform_many_oop(self, receivers: Iterable[int], selector: str, *args: int) -> list[int]:
        """Alias for ``bulk_perform_oop``."""
        return self.bulk_perform_oop(receivers, selector, *args)

    def perform_many_value(
        self,
        receivers: Iterable[int],
        selector: str,
        *args: int,
    ) -> list[Any]:
        """Alias for ``bulk_perform_value``."""
        return self.bulk_perform_value(receivers, selector, *args)

    def _perform_oop_raw(self, receiver: int, selector: str, *args: int) -> int:
        lib = self._require_login()
        arg_arr = (ctypes.c_uint64 * len(args))(*args)
        oop = int(
            lib.GciPerform(
                ctypes.c_uint64(receiver),
                selector.encode("utf-8"),
                arg_arr,
                ctypes.c_int(len(args)),
            )
        )
        self._check_result(oop)
        return oop

    def perform_typed(
        self,
        receiver: int,
        selector: str,
        cls: type[T],
        *args: int,
    ) -> TypedOop[T]:
        """Perform a selector and return a phantom-typed OOP."""
        return TypedOop(self.perform_oop(receiver, selector, *args), self, cls)

    def perform_managed(self, receiver: int, selector: str, *args: int) -> ManagedOop:
        """Perform a selector and retain the raw result OOP in the export set."""
        return self.managed_oop(self.perform_oop(receiver, selector, *args))

    def new_string(self, value: str) -> int:
        with self._observe_operation("new_string", {"value_length": len(value)}):
            lib = self._require_login()
            return int(lib.GciNewString(value.encode("utf-8")))

    def new_symbol(self, value: str) -> int:
        with self._observe_operation("new_symbol", {"value_length": len(value)}):
            lib = self._require_login()
            return int(lib.GciNewSymbol(value.encode("utf-8")))

    def new_object(self, class_oop: int) -> int:
        with self._observe_operation("new_object"):
            lib = self._require_login()
            return int(lib.GciNewOop(ctypes.c_uint64(class_oop)))

    def resolve(self, name: str) -> int:
        with self._observe_operation("resolve", {"symbol": name}):
            lib = self._require_login()
            oop = int(lib.GciResolveSymbol(name.encode("utf-8"), ctypes.c_uint64(OOP_NIL)))
            if oop == OOP_ILLEGAL:
                raise GemStoneError(f"Cannot resolve global: {name!r}")
            return oop

    def resolve_symbol(self, name: str) -> int:
        """Resolve a GemStone global symbol and return its raw OOP."""
        return self.resolve(name)

    def int_oop(self, value: int) -> int:
        return cast(int, _python_to_smallint(value))

    def float_oop(self, value: float) -> int:
        with self._observe_operation("float_oop"):
            lib = self._require_login()
            oop = int(lib.GciFltToOop(ctypes.c_double(value)))
            if oop in (OOP_ILLEGAL, OOP_NIL):
                raise GemStoneError(f"Cannot convert Python float {value!r} to GemStone OOP")
            return oop

    def try_oop_to_float(self, oop: int) -> Optional[float]:
        with self._observe_operation("try_oop_to_float"):
            lib = self._require_login()
            value = ctypes.c_double()
            ok = lib.GciOopToFlt_(ctypes.c_uint64(oop), ctypes.byref(value))
            if ok:
                return value.value
            return None

    def dict_to_gs(self, d: dict[str, object]) -> int:
        with self._observe_operation("dict_to_gs", {"entries": len(d)}):
            dict_oop = self.new_object(self.resolve("StringKeyValueDictionary"))
            lib = self._require_login()
            for k, v in d.items():
                v_oop = self._python_value_to_oop(v)
                lib.GciStrKeyValueDictAtPut(
                    ctypes.c_uint64(dict_oop),
                    str(k).encode("utf-8"),
                    ctypes.c_uint64(v_oop),
                )
            return dict_oop

    def dict_put_global(self, symbol_name: str, d: dict[str, object]) -> None:
        with self._observe_operation("dict_put_global", {"symbol": symbol_name}):
            dict_oop = self.dict_to_gs(d)
            user_globals = self.resolve("UserGlobals")
            sym_oop = self.new_symbol(symbol_name)
            lib = self._require_login()
            lib.GciSymDictAtObjPut(
                ctypes.c_uint64(user_globals),
                ctypes.c_uint64(sym_oop),
                ctypes.c_uint64(dict_oop),
            )

    def global_get(self, symbol_name: str) -> int:
        with self._observe_operation("global_get", {"symbol": symbol_name}):
            user_globals = self.resolve("UserGlobals")
            value = ctypes.c_uint64(OOP_ILLEGAL)
            assoc = ctypes.c_uint64(OOP_ILLEGAL)
            lib = self._require_login()
            lib.GciSymDictAt(
                ctypes.c_uint64(user_globals),
                symbol_name.encode("utf-8"),
                ctypes.byref(value),
                ctypes.byref(assoc),
            )
            return value.value

    def str_dict_get(self, dict_oop: int, key: str) -> Any:
        with self._observe_operation("str_dict_get", {"key": key}):
            value = ctypes.c_uint64(OOP_ILLEGAL)
            lib = self._require_login()
            lib.GciStrKeyValueDictAt(
                ctypes.c_uint64(dict_oop),
                key.encode("utf-8"),
                ctypes.byref(value),
            )
            return self._marshal(value.value)

    def managed_oop(self, oop: int) -> ManagedOop:
        """Return an automatically released export-set handle for ``oop``."""
        return ManagedOop(oop, self)

    def handle(self, oop: int) -> OopHandle:
        """Return an explicitly scoped export-set handle for ``oop``."""
        return OopHandle(oop, self)

    def _retain_managed_oop(self, oop: int) -> None:
        with self._managed_oop_lock:
            previous = self._managed_oop_counts[oop]
            if previous == 0:
                self._add_to_export_set(oop)
            self._managed_oop_counts[oop] = previous + 1

    def _release_managed_oop(self, oop: int) -> None:
        remove_now = False
        with self._managed_oop_lock:
            current = self._managed_oop_counts.get(oop, 0)
            if current <= 0:
                return
            if current == 1:
                del self._managed_oop_counts[oop]
                if self._can_call_gci_on_current_thread():
                    remove_now = True
                elif self._logged_in:
                    self._managed_oop_pending_removals[oop] += 1
            else:
                self._managed_oop_counts[oop] = current - 1
        if remove_now:
            self._remove_from_export_set(oop)

    def _can_call_gci_on_current_thread(self) -> bool:
        owner = self._owner_thread_id
        return self._logged_in and owner == threading.get_ident()

    def _drain_pending_managed_oop_removals(self) -> None:
        if self._managed_oop_draining or not self._can_call_gci_on_current_thread():
            return
        self._managed_oop_draining = True
        try:
            while True:
                with self._managed_oop_lock:
                    if not self._managed_oop_pending_removals:
                        return
                    oop, count = self._managed_oop_pending_removals.popitem()
                for _ in range(count):
                    self._remove_from_export_set(oop)
        finally:
            self._managed_oop_draining = False

    def _add_to_export_set(self, oop: int) -> None:
        self._call_optional_oop_export_function(
            ("GciAddOopToExportSet", "GciAddObjToExportSet"),
            oop,
        )

    def _remove_from_export_set(self, oop: int) -> None:
        self._call_optional_oop_export_function(
            ("GciRemoveOopFromExportSet", "GciRemoveObjFromExportSet"),
            oop,
        )

    def _call_optional_oop_export_function(self, names: tuple[str, ...], oop: int) -> None:
        if not self._logged_in or self._lib is None:
            return
        lib = self._activate_session(drain_pending=False)
        for name in names:
            try:
                fn = getattr(lib, name)
            except AttributeError:
                continue
            fn(ctypes.c_uint64(oop))
            return

    def _python_value_to_oop(self, value: object) -> int:
        if value is None:
            return int(OOP_NIL)
        if isinstance(value, bool):
            return int(OOP_TRUE if value else OOP_FALSE)
        if isinstance(value, (ManagedOop, Oop, OopHandle)):
            return int(value.oop)
        if hasattr(value, "oop"):
            return int(getattr(value, "oop"))
        if isinstance(value, int):
            return self.int_oop(value)
        if isinstance(value, float):
            return self.float_oop(value)
        if isinstance(value, str):
            return self.new_string(value)
        if isinstance(value, dict):
            return self.dict_to_gs(value)
        raise TypeError(f"Cannot convert {type(value).__name__!r} to GemStone OOP")

    def fetch_string(self, oop: int) -> str:
        with self._observe_operation("fetch_string"):
            lib = self._require_login()
            size = int(lib.GciFetchSize_(ctypes.c_uint64(oop)))
            if size <= 0:
                return ""
            buf = ctypes.create_string_buffer(size + 1)
            fetched = int(
                lib.GciFetchBytes_(
                    ctypes.c_uint64(oop),
                    ctypes.c_int64(1),
                    buf,
                    ctypes.c_int64(size),
                )
            )
            return buf.raw[:fetched].decode("utf-8", errors="replace")

    def fetch_class(self, oop: int) -> int:
        with self._observe_operation("fetch_class"):
            lib = self._require_login()
            return int(lib.GciFetchClass(ctypes.c_uint64(oop)))

    def inspect(self, oop: int, *, slots: Sequence[str] | None = None) -> Any:
        """Return a one-level inspection result for a GemStone OOP."""
        from gemstone_py.inspection import inspect_oop

        if slots is None:
            return inspect_oop(self, oop)
        return inspect_oop(self, oop, slots=slots)

    def dump(
        self,
        oop: int,
        *,
        depth: int = 2,
        slots: Sequence[str] | None = None,
        classes: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Return a recursive JSON-serialisable structure dump for a GemStone OOP."""
        from gemstone_py.inspection import dump_oop

        kwargs: dict[str, Any] = {"depth": depth}
        if slots is not None:
            kwargs["slots"] = slots
        if classes is not None:
            kwargs["classes"] = classes
        payload: dict[str, Any] = dump_oop(self, oop, **kwargs)
        return payload

    def describe_class(self, name: str) -> Any:
        """Return superclass and instance-variable details for a GemStone class."""
        from gemstone_py.inspection import describe_class

        return describe_class(self, name)

    def _require_login(self) -> ctypes.CDLL:
        if not self._logged_in:
            raise GemStoneError("Not logged in. Call login() first.")
        return self._activate_session()

    def _claim_thread_ownership(self) -> None:
        """Bind this logged-in session to the current thread."""
        if not self._logged_in:
            return
        current_thread_id = threading.get_ident()
        owner_thread_id = self._owner_thread_id
        if owner_thread_id is None:
            self._owner_thread_id = current_thread_id
            return
        if owner_thread_id != current_thread_id:
            raise GemStoneError(
                "GemStoneSession is bound to a different Python thread "
                f"(owner={owner_thread_id}, current={current_thread_id}). "
                "Sessions are not safe to share across threads; acquire a "
                "session per thread or use GemStoneSessionPool."
            )

    def _release_thread_ownership(self, *, force: bool = False) -> None:
        """Unbind this session so a provider can safely hand it to another thread."""
        owner_thread_id = self._owner_thread_id
        if owner_thread_id is None:
            return
        current_thread_id = threading.get_ident()
        if not force and owner_thread_id != current_thread_id:
            raise GemStoneError(
                "Cannot release GemStoneSession thread ownership from a "
                f"different Python thread (owner={owner_thread_id}, "
                f"current={current_thread_id})."
            )
        self._owner_thread_id = None

    def _activate_session(self, *, drain_pending: bool = True) -> ctypes.CDLL:
        lib = self._require_lib()
        if self._session_id == GCI_INVALID_SESSION:
            raise GemStoneError("Not logged in. Call login() first.")
        self._claim_thread_ownership()
        lib.GciSetSessionId(self._session_id)
        if drain_pending:
            self._drain_pending_managed_oop_removals()
        return lib

    def _check_result(self, oop: int) -> None:
        if oop == OOP_ILLEGAL:
            err = GciErrSType()
            lib = self._require_lib()
            lib.GciErr(ctypes.byref(err))
            if err.number != 0:
                raise GemStoneError.from_err_struct(err)
            raise GemStoneError("GCI call returned OOP_ILLEGAL")

    def _string_class_oops(self) -> frozenset[int]:
        if self.__string_class_oops_cache is not None:
            return self.__string_class_oops_cache
        lib = self._require_login()
        string_oop = int(lib.GciResolveSymbol(b"String", ctypes.c_uint64(OOP_NIL)))
        symbol_oop = int(lib.GciResolveSymbol(b"Symbol", ctypes.c_uint64(OOP_NIL)))
        cache: set[int] = set()
        if string_oop not in (OOP_ILLEGAL, 0):
            cache.add(string_oop)
        if symbol_oop not in (OOP_ILLEGAL, 0):
            cache.add(symbol_oop)
        self.__string_class_oops_cache = frozenset(cache)
        return self.__string_class_oops_cache

    def _is_string_oop(self, oop: int) -> bool:
        try:
            lib = self._require_login()
            cls_oop = int(lib.GciFetchClass(ctypes.c_uint64(oop)))
            return cls_oop in self._string_class_oops()
        except Exception:
            return False

    def _marshal(self, oop: int) -> Any:
        if oop == OOP_NIL:
            return None
        if oop == OOP_TRUE:
            return True
        if oop == OOP_FALSE:
            return False
        if oop == OOP_ILLEGAL:
            raise GemStoneError("OOP_ILLEGAL")

        if _is_smallint(oop):
            return _smallint_to_python(oop)

        if _is_char(oop):
            return _char_to_python(oop)

        float_value = self.try_oop_to_float(oop)
        if float_value is not None:
            return float_value

        if self._is_string_oop(oop):
            return self.fetch_string(oop)

        return OopRef(oop, self)


class OopRef:
    """Wraps a GemStone OOP for objects that cannot be auto-converted."""

    def __init__(self, oop: int, session: GemStoneSession):
        self.oop = oop
        self._session = session

    def __repr__(self) -> str:
        return f"<OopRef 0x{self.oop:016X}>"

    def send(self, selector: str, *args: object) -> Any:
        raw: list[int] = []
        for arg in args:
            if isinstance(arg, OopRef):
                raw.append(arg.oop)
            elif isinstance(arg, int) and not _is_smallint(arg):
                raw.append(cast(int, _python_to_smallint(arg)))
            else:
                raw.append(cast(int, arg))
        return self._session.perform_value(self.oop, selector, *raw)

    def gs_class(self) -> int:
        return self._session.fetch_class(self.oop)

    def print_string(self) -> str:
        return cast(str, self._session.perform_value(self.oop, "printString"))


def connect(
    stone: Optional[str] = None,
    netldi: Optional[str] = None,
    host: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    lib_path: Optional[str] = None,
    *,
    config: Optional[GemStoneConfig] = None,
    transaction_policy: TransactionPolicy | str = TransactionPolicy.MANUAL,
    **kwargs: Any,
) -> GemStoneSession:
    """Open and return a logged-in GemStoneSession."""

    session = GemStoneSession(
        stone=stone,
        netldi=netldi,
        host=host,
        username=username,
        password=password,
        lib_path=lib_path,
        config=config,
        transaction_policy=transaction_policy,
        **kwargs,
    )
    session.login()
    return session
