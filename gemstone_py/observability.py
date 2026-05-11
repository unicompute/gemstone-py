"""Tracing, metrics, and slow-operation hooks for gemstone-py."""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping
from types import TracebackType
from typing import Any, Literal, Protocol, cast, runtime_checkable

MetricLabels = Mapping[str, str | int | float | bool | None]
SpanAttributes = Mapping[str, str | int | float | bool | None]


@runtime_checkable
class Span(Protocol):
    """Minimal span surface used by gemstone-py instrumentation."""

    def set_attribute(self, key: str, value: str | int | float | bool | None) -> None:
        """Attach one attribute to the active span."""

    def record_exception(self, exc: BaseException) -> None:
        """Record an exception on the active span."""


@runtime_checkable
class SpanContext(Protocol):
    """Context manager returned by ``Tracer.start_span``."""

    def __enter__(self) -> Span:
        """Enter the span and return a span object."""

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        """Leave the span."""


@runtime_checkable
class Tracer(Protocol):
    """Protocol implemented by tracing adapters."""

    def start_span(
        self,
        name: str,
        attrs: SpanAttributes | None = None,
    ) -> SpanContext:
        """Start a named span with optional attributes."""


@runtime_checkable
class MetricsCollector(Protocol):
    """Protocol implemented by metrics adapters."""

    def increment(
        self,
        name: str,
        labels: MetricLabels | None = None,
        value: int | float = 1,
    ) -> None:
        """Increment a counter."""

    def record_duration(
        self,
        name: str,
        labels: MetricLabels | None,
        duration_ms: float,
    ) -> None:
        """Record one duration sample in milliseconds."""


class NullSpan:
    """Reusable no-op span and context manager."""

    def __enter__(self) -> "NullSpan":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        del exc_type, exc_val, exc_tb
        return False

    def set_attribute(self, key: str, value: str | int | float | bool | None) -> None:
        del key, value

    def record_exception(self, exc: BaseException) -> None:
        del exc


NULL_SPAN = NullSpan()


class NullTracer:
    """No-op tracer used when tracing is not configured."""

    def start_span(
        self,
        name: str,
        attrs: SpanAttributes | None = None,
    ) -> NullSpan:
        del name, attrs
        return NULL_SPAN


class NullMetrics:
    """No-op metrics collector used when metrics are not configured."""

    def increment(
        self,
        name: str,
        labels: MetricLabels | None = None,
        value: int | float = 1,
    ) -> None:
        del name, labels, value

    def record_duration(
        self,
        name: str,
        labels: MetricLabels | None,
        duration_ms: float,
    ) -> None:
        del name, labels, duration_ms


NULL_TRACER = NullTracer()
NULL_METRICS = NullMetrics()


class OpenTelemetryTracer:
    """Adapter for an ``opentelemetry.trace.Tracer`` instance."""

    def __init__(self, tracer: Any):
        self._tracer = tracer

    def start_span(
        self,
        name: str,
        attrs: SpanAttributes | None = None,
    ) -> SpanContext:
        return cast(
            SpanContext,
            self._tracer.start_as_current_span(
                name,
                attributes=dict(attrs or {}),
            ),
        )


class PrometheusMetrics:
    """
    Metrics adapter backed by ``prometheus_client``.

    Metrics are created lazily. A given metric name must always use the same
    label keys, which matches Prometheus' data model and keeps misconfigured
    instrumentation visible.
    """

    def __init__(self, registry: Any | None = None):
        try:
            from prometheus_client import Counter, Histogram
        except ImportError as exc:
            raise RuntimeError(
                "PrometheusMetrics requires the optional prometheus_client package."
            ) from exc
        self._counter_cls = Counter
        self._histogram_cls = Histogram
        self._registry = registry
        self._lock = threading.Lock()
        self._counters: dict[str, Any] = {}
        self._histograms: dict[str, Any] = {}
        self._labelnames: dict[tuple[str, str], tuple[str, ...]] = {}

    def increment(
        self,
        name: str,
        labels: MetricLabels | None = None,
        value: int | float = 1,
    ) -> None:
        label_values = _normalize_labels(labels)
        counter = self._metric(
            "counter",
            name,
            label_values,
            self._counters,
            self._counter_cls,
            "gemstone-py operation counter.",
        )
        if label_values:
            counter.labels(**label_values).inc(value)
        else:
            counter.inc(value)

    def record_duration(
        self,
        name: str,
        labels: MetricLabels | None,
        duration_ms: float,
    ) -> None:
        label_values = _normalize_labels(labels)
        histogram = self._metric(
            "histogram",
            name,
            label_values,
            self._histograms,
            self._histogram_cls,
            "gemstone-py operation duration in milliseconds.",
        )
        if label_values:
            histogram.labels(**label_values).observe(duration_ms)
        else:
            histogram.observe(duration_ms)

    def _metric(
        self,
        kind: str,
        name: str,
        labels: dict[str, str],
        cache: dict[str, Any],
        factory: Any,
        documentation: str,
    ) -> Any:
        metric_name = _metric_name(name)
        labelnames = tuple(labels)
        key = (kind, metric_name)
        with self._lock:
            previous = self._labelnames.get(key)
            if previous is not None and previous != labelnames:
                raise ValueError(
                    f"Prometheus metric {metric_name!r} was already created with "
                    f"labels {previous!r}, not {labelnames!r}."
                )
            self._labelnames[key] = labelnames
            metric = cache.get(metric_name)
            if metric is None:
                kwargs = {"registry": self._registry} if self._registry is not None else {}
                metric = factory(metric_name, documentation, labelnames, **kwargs)
                cache[metric_name] = metric
            return metric


def _normalize_labels(labels: MetricLabels | None) -> dict[str, str]:
    return {str(key): "" if value is None else str(value) for key, value in (labels or {}).items()}


def _metric_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_:]", "_", name)
    if not cleaned or not re.match(r"[a-zA-Z_:]", cleaned):
        cleaned = f"gemstone_py_{cleaned}"
    return cleaned


__all__ = [
    "MetricLabels",
    "MetricsCollector",
    "NULL_METRICS",
    "NULL_SPAN",
    "NULL_TRACER",
    "NullMetrics",
    "NullSpan",
    "NullTracer",
    "OpenTelemetryTracer",
    "PrometheusMetrics",
    "Span",
    "SpanAttributes",
    "SpanContext",
    "Tracer",
]
