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
from .inspection import (
    ClassDescription,
    InspectedReference,
    InspectedSlot,
    InspectionResult,
)
from .observability import (
    NULL_METRICS,
    NULL_SPAN,
    NULL_TRACER,
    MetricsCollector,
    NullMetrics,
    NullSpan,
    NullTracer,
    OpenTelemetryTracer,
    PrometheusMetrics,
    Span,
    SpanContext,
    Tracer,
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
    GemStoneSessionPoolStats,
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
    "bootstrap": "gemstone_py.bootstrap",
    "inspection": "gemstone_py.inspection",
    "GemStoneSessionFacade": "gemstone_py.session_facade",
    "PersistentRoot": "gemstone_py.persistent_root",
    "concurrency": "gemstone_py.concurrency",
    "gsquery": "gemstone_py.gsquery",
    "gstore": "gemstone_py.gstore",
    "migrations": "gemstone_py.migrations",
    "native": "gemstone_py.native",
    "observability": "gemstone_py.observability",
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
    "GemStoneSessionPoolStats",
    "GemStoneThreadLocalSessionProvider",
    "ClassDescription",
    "GemStoneClassWrapper",
    "GemStoneObjectProxy",
    "InspectedReference",
    "InspectedSlot",
    "InspectionResult",
    "MetricsCollector",
    "ManagedOop",
    "NULL_METRICS",
    "NULL_SPAN",
    "NULL_TRACER",
    "NullMetrics",
    "NullSpan",
    "NullTracer",
    "OOP_FALSE",
    "OOP_ILLEGAL",
    "OOP_NIL",
    "OOP_TRUE",
    "Oop",
    "OopRef",
    "OopHandle",
    "OpenTelemetryTracer",
    "PrometheusMetrics",
    "Span",
    "SpanContext",
    "Tracer",
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
    "bootstrap",
    "close_flask_request_session_provider",
    "connect",
    "current_flask_request_session",
    "flask_request_session_provider",
    "flask_request_session_provider_metrics",
    "flask_request_session_provider_snapshot",
    "finalize_flask_request_session",
    "gemstone_class",
    "gemstone_class_name",
    "inspection",
    "install_flask_request_session",
    "native",
    "observability",
    "release_metadata",
    "registered_gemstone_classes",
    "session_facade",
    "session_scope",
    "typed_oop",
    "warm_flask_request_session_provider",
]
