"""Canonical package imports for gemstone-py."""

from importlib import import_module

from ._gci import (
    GCI_INVALID_SESSION,
    OOP_FALSE,
    OOP_ILLEGAL,
    OOP_NIL,
    OOP_TRUE,
    GciErrSType,
    _is_smallint,
    _python_to_smallint,
    _smallint_to_python,
)
from .client import (
    GemStoneConfig,
    GemStoneConfigurationError,
    GemStoneError,
    GemStoneSession,
    ManagedOop,
    OopHandle,
    OopRef,
    TransactionPolicy,
    TypedOop,
    connect,
)
from .oop import (
    GemStoneClassWrapper,
    GemStoneObjectProxy,
    Oop,
    gemstone_class,
    gemstone_class_name,
    registered_gemstone_classes,
    typed_oop,
)
from .web import (
    GemStoneSessionPool,
    GemStoneSessionProvider,
    GemStoneSessionProviderEvent,
    GemStoneSessionProviderSnapshot,
    GemStoneThreadLocalSessionProvider,
    close_flask_request_session_provider,
    current_flask_request_session,
    finalize_flask_request_session,
    flask_request_session_provider,
    flask_request_session_provider_metrics,
    flask_request_session_provider_snapshot,
    install_flask_request_session,
    session_scope,
    warm_flask_request_session_provider,
)

_LAZY_EXPORTS = {
    "aio": "gemstone_py.aio",
    "benchmark_baseline_register": "gemstone_py.benchmark_baseline_register",
    "benchmark_baselines": "gemstone_py.benchmark_baselines",
    "benchmark_compare": "gemstone_py.benchmark_compare",
    "GemStoneSessionFacade": "gemstone_py.session_facade",
    "PersistentRoot": "gemstone_py.persistent_root",
    "concurrency": "gemstone_py.concurrency",
    "gsquery": "gemstone_py.gsquery",
    "gstore": "gemstone_py.gstore",
    "migrations": "gemstone_py.migrations",
    "native": "gemstone_py.native",
    "objectlog": "gemstone_py.objectlog",
    "ordered_collection": "gemstone_py.ordered_collection",
    "persistent_root": "gemstone_py.persistent_root",
    "release_metadata": "gemstone_py.release_metadata",
    "session_facade": "gemstone_py.session_facade",
    "smalltalk_bridge": "gemstone_py.smalltalk_bridge",
}


def __getattr__(name: str) -> object:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(target)
    if name in {"GemStoneSessionFacade", "PersistentRoot"}:
        value = getattr(module, name)
    else:
        value = module
    globals()[name] = value
    return value


__all__ = [
    "GCI_INVALID_SESSION",
    "GciErrSType",
    "GemStoneConfig",
    "GemStoneConfigurationError",
    "GemStoneError",
    "GemStoneSession",
    "GemStoneSessionFacade",
    "GemStoneSessionPool",
    "GemStoneSessionProviderEvent",
    "GemStoneSessionProvider",
    "GemStoneSessionProviderSnapshot",
    "GemStoneThreadLocalSessionProvider",
    "GemStoneClassWrapper",
    "GemStoneObjectProxy",
    "ManagedOop",
    "OOP_FALSE",
    "OOP_ILLEGAL",
    "OOP_NIL",
    "OOP_TRUE",
    "Oop",
    "OopRef",
    "OopHandle",
    "TypedOop",
    "PersistentRoot",
    "TransactionPolicy",
    "_is_smallint",
    "_python_to_smallint",
    "_smallint_to_python",
    "aio",
    "benchmark_baselines",
    "benchmark_baseline_register",
    "benchmark_compare",
    "close_flask_request_session_provider",
    "connect",
    "current_flask_request_session",
    "flask_request_session_provider",
    "flask_request_session_provider_metrics",
    "flask_request_session_provider_snapshot",
    "finalize_flask_request_session",
    "gemstone_class",
    "gemstone_class_name",
    "install_flask_request_session",
    "native",
    "release_metadata",
    "registered_gemstone_classes",
    "session_facade",
    "session_scope",
    "typed_oop",
    "warm_flask_request_session_provider",
]
