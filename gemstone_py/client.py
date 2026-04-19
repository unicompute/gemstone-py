"""GemStone session/config client built on the low-level GCI helpers."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from enum import Enum
from types import TracebackType
from typing import Any, Literal, Optional

from ._gci import (
    GCI_ENCRYPT_BUF_SIZE,
    GCI_INVALID_SESSION,
    GciErrSType,
    OOP_FALSE,
    OOP_ILLEGAL,
    OOP_NIL,
    OOP_TRUE,
    _bind,
    _char_to_python,
    _is_char,
    _is_smallint,
    _load_library,
    _python_to_smallint,
    _smallint_to_python,
)

__all__ = [
    "GemStoneError",
    "GemStoneConfigurationError",
    "TransactionPolicy",
    "GemStoneConfig",
    "GemStoneSession",
    "OopRef",
    "connect",
]


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
        return cls(full or f"GemStone error #{err.number}", number=err.number, fatal=bool(err.fatal))


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
            raise ValueError(f"Unknown transaction policy {value!r}. Expected one of: {options}") from exc


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
            stone=os.environ.get("GS_STONE", "gs64stone"),
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
        self._lib = _load_library(self._lib_path)
        _bind(self._lib)
        self._lib.GciInit()

    def login(self) -> None:
        self.config.require_credentials()
        self._ensure_lib()
        lib = self._lib

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
            self.username.encode("utf-8"),
            self.password.encode("utf-8"),
            0,
            0,
        )

        if not ok:
            err = GciErrSType()
            lib.GciErr(ctypes.byref(err))
            raise GemStoneError.from_err_struct(err)

        self._session_id = lib.GciGetSessionId()
        self._logged_in = True

    def logout(self) -> None:
        if not self._logged_in or self._lib is None:
            return
        self._activate_session()
        self._lib.GciLogout()
        self._logged_in = False
        self._session_id = GCI_INVALID_SESSION

    def commit(self) -> None:
        self._require_login()
        err = GciErrSType()
        ok = self._lib.GciCommit(ctypes.byref(err))
        if not ok:
            raise GemStoneError.from_err_struct(err)

    def abort(self) -> None:
        self._require_login()
        err = GciErrSType()
        ok = self._lib.GciAbort(ctypes.byref(err))
        if ok:
            return
        if err.number != 0:
            raise GemStoneError.from_err_struct(err)
        oop = self._lib.GciExecuteStr(
            b"System abortTransaction",
            ctypes.c_uint64(OOP_NIL),
        )
        self._check_result(oop)

    def needs_commit(self) -> bool:
        self._require_login()
        return bool(self._lib.GciNeedsCommit())

    def in_transaction(self) -> bool:
        self._require_login()
        return bool(self._lib.GciInTransaction())

    def eval(self, source: str) -> Any:
        self._require_login()
        oop = self._lib.GciExecuteStr(source.encode("utf-8"), ctypes.c_uint64(OOP_NIL))
        self._check_result(oop)
        return self._marshal(oop)

    def eval_oop(self, source: str) -> int:
        self._require_login()
        oop = self._lib.GciExecuteStr(source.encode("utf-8"), ctypes.c_uint64(OOP_NIL))
        self._check_result(oop)
        return oop

    def perform(self, receiver: int, selector: str, *args: int) -> Any:
        self._require_login()
        arg_arr = (ctypes.c_uint64 * len(args))(*args)
        oop = self._lib.GciPerform(
            ctypes.c_uint64(receiver),
            selector.encode("utf-8"),
            arg_arr,
            ctypes.c_int(len(args)),
        )
        self._check_result(oop)
        return self._marshal(oop)

    def perform_oop(self, receiver: int, selector: str, *args: int) -> int:
        self._require_login()
        arg_arr = (ctypes.c_uint64 * len(args))(*args)
        oop = self._lib.GciPerform(
            ctypes.c_uint64(receiver),
            selector.encode("utf-8"),
            arg_arr,
            ctypes.c_int(len(args)),
        )
        self._check_result(oop)
        return oop

    def new_string(self, value: str) -> int:
        self._require_login()
        return self._lib.GciNewString(value.encode("utf-8"))

    def new_symbol(self, value: str) -> int:
        self._require_login()
        return self._lib.GciNewSymbol(value.encode("utf-8"))

    def new_object(self, class_oop: int) -> int:
        self._require_login()
        return self._lib.GciNewOop(ctypes.c_uint64(class_oop))

    def resolve(self, name: str) -> int:
        self._require_login()
        oop = self._lib.GciResolveSymbol(name.encode("utf-8"), ctypes.c_uint64(OOP_NIL))
        if oop == OOP_ILLEGAL:
            raise GemStoneError(f"Cannot resolve global: {name!r}")
        return oop

    def int_oop(self, value: int) -> int:
        return _python_to_smallint(value)

    def float_oop(self, value: float) -> int:
        self._require_login()
        oop = self._lib.GciFltToOop(ctypes.c_double(value))
        if oop in (OOP_ILLEGAL, OOP_NIL):
            raise GemStoneError(f"Cannot convert Python float {value!r} to GemStone OOP")
        return oop

    def try_oop_to_float(self, oop: int) -> Optional[float]:
        self._require_login()
        value = ctypes.c_double()
        ok = self._lib.GciOopToFlt_(ctypes.c_uint64(oop), ctypes.byref(value))
        if ok:
            return value.value
        return None

    def dict_to_gs(self, d: dict[str, object]) -> int:
        dict_oop = self.new_object(self.resolve("StringKeyValueDictionary"))
        for k, v in d.items():
            v_oop = self._python_value_to_oop(v)
            self._lib.GciStrKeyValueDictAtPut(
                ctypes.c_uint64(dict_oop),
                str(k).encode("utf-8"),
                ctypes.c_uint64(v_oop),
            )
        return dict_oop

    def dict_put_global(self, symbol_name: str, d: dict[str, object]) -> None:
        dict_oop = self.dict_to_gs(d)
        user_globals = self.resolve("UserGlobals")
        sym_oop = self.new_symbol(symbol_name)
        self._lib.GciSymDictAtObjPut(
            ctypes.c_uint64(user_globals),
            ctypes.c_uint64(sym_oop),
            ctypes.c_uint64(dict_oop),
        )

    def global_get(self, symbol_name: str) -> int:
        user_globals = self.resolve("UserGlobals")
        value = ctypes.c_uint64(OOP_ILLEGAL)
        assoc = ctypes.c_uint64(OOP_ILLEGAL)
        self._lib.GciSymDictAt(
            ctypes.c_uint64(user_globals),
            symbol_name.encode("utf-8"),
            ctypes.byref(value),
            ctypes.byref(assoc),
        )
        return value.value

    def str_dict_get(self, dict_oop: int, key: str) -> Any:
        value = ctypes.c_uint64(OOP_ILLEGAL)
        self._lib.GciStrKeyValueDictAt(
            ctypes.c_uint64(dict_oop),
            key.encode("utf-8"),
            ctypes.byref(value),
        )
        return self._marshal(value.value)

    def _python_value_to_oop(self, value) -> int:
        if value is None:
            return OOP_NIL
        if isinstance(value, bool):
            return OOP_TRUE if value else OOP_FALSE
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
        self._require_login()
        size = self._lib.GciFetchSize_(ctypes.c_uint64(oop))
        if size <= 0:
            return ""
        buf = ctypes.create_string_buffer(size + 1)
        fetched = self._lib.GciFetchBytes_(
            ctypes.c_uint64(oop),
            ctypes.c_int64(1),
            buf,
            ctypes.c_int64(size),
        )
        return buf.raw[:fetched].decode("utf-8", errors="replace")

    def fetch_class(self, oop: int) -> int:
        self._require_login()
        return self._lib.GciFetchClass(ctypes.c_uint64(oop))

    def _require_login(self) -> None:
        if not self._logged_in:
            raise GemStoneError("Not logged in. Call login() first.")
        self._activate_session()

    def _activate_session(self) -> None:
        if self._lib is None or self._session_id == GCI_INVALID_SESSION:
            raise GemStoneError("Not logged in. Call login() first.")
        self._lib.GciSetSessionId(self._session_id)

    def _check_result(self, oop: int) -> None:
        if oop == OOP_ILLEGAL:
            err = GciErrSType()
            self._lib.GciErr(ctypes.byref(err))
            if err.number != 0:
                raise GemStoneError.from_err_struct(err)
            raise GemStoneError("GCI call returned OOP_ILLEGAL")

    def _string_class_oops(self) -> frozenset[int]:
        if self.__string_class_oops_cache is not None:
            return self.__string_class_oops_cache
        string_oop = self._lib.GciResolveSymbol(b"String", ctypes.c_uint64(OOP_NIL))
        symbol_oop = self._lib.GciResolveSymbol(b"Symbol", ctypes.c_uint64(OOP_NIL))
        cache: set[int] = set()
        if string_oop not in (OOP_ILLEGAL, 0):
            cache.add(string_oop)
        if symbol_oop not in (OOP_ILLEGAL, 0):
            cache.add(symbol_oop)
        self.__string_class_oops_cache = frozenset(cache)
        return self.__string_class_oops_cache

    def _is_string_oop(self, oop: int) -> bool:
        try:
            cls_oop = self._lib.GciFetchClass(ctypes.c_uint64(oop))
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

    def send(self, selector: str, *args) -> Any:
        raw = []
        for arg in args:
            if isinstance(arg, OopRef):
                raw.append(arg.oop)
            elif isinstance(arg, int) and not _is_smallint(arg):
                raw.append(_python_to_smallint(arg))
            else:
                raw.append(arg)
        return self._session.perform(self.oop, selector, *raw)

    def gs_class(self) -> int:
        return self._session.fetch_class(self.oop)

    def print_string(self) -> str:
        return self._session.perform(self.oop, "printString")


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
    **kwargs,
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
