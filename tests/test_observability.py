import unittest
from unittest import mock

import gemstone_py as gemstone
from gemstone_py.observability import NULL_SPAN, NULL_TRACER


class RecordingSpan:
    def __init__(self):
        self.attributes = {}
        self.exceptions = []

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def record_exception(self, exc):
        self.exceptions.append(type(exc).__name__)


class RecordingSpanContext:
    def __init__(self, span):
        self.span = span
        self.exit_exc_type = None

    def __enter__(self):
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        del exc_val, exc_tb
        self.exit_exc_type = exc_type
        return False


class RecordingTracer:
    def __init__(self):
        self.started = []

    def start_span(self, name, attrs=None):
        span = RecordingSpan()
        context = RecordingSpanContext(span)
        self.started.append((name, dict(attrs or {}), span, context))
        return context


class RecordingMetrics:
    def __init__(self):
        self.increments = []
        self.durations = []

    def increment(self, name, labels=None, value=1):
        self.increments.append((name, dict(labels or {}), value))

    def record_duration(self, name, labels, duration_ms):
        self.durations.append((name, dict(labels or {}), duration_ms))


def _observed_session():
    tracer = RecordingTracer()
    metrics = RecordingMetrics()
    session = gemstone.GemStoneSession(
        username="alice",
        password="secret",
        tracer=tracer,
        metrics=metrics,
    )
    session._logged_in = True
    session._session_id = 41
    session._lib = mock.Mock()
    return session, tracer, metrics


class ObservabilityTests(unittest.TestCase):
    def test_null_tracer_reuses_singleton_span(self):
        self.assertIs(NULL_TRACER.start_span("anything"), NULL_SPAN)

    def test_execute_records_tracing_and_metrics(self):
        session, tracer, metrics = _observed_session()
        session._lib.GciExecuteStr.return_value = gemstone._python_to_smallint(7)

        result = session.execute("1 + 6")

        self.assertEqual(result, gemstone._python_to_smallint(7))
        self.assertEqual(tracer.started[0][0], "gemstone.session.execute_oop")
        self.assertEqual(tracer.started[0][1]["source_length"], 5)
        span = tracer.started[0][2]
        self.assertEqual(span.attributes["status"], "ok")
        self.assertIn("duration_ms", span.attributes)
        self.assertEqual(
            metrics.increments,
            [
                (
                    "gemstone_py_session_operations",
                    {"operation": "execute_oop", "status": "ok"},
                    1,
                )
            ],
        )
        self.assertEqual(metrics.durations[0][0], "gemstone_py_session_duration_ms")
        self.assertEqual(metrics.durations[0][1], {"operation": "execute_oop", "status": "ok"})

    def test_operation_errors_are_recorded(self):
        session, tracer, metrics = _observed_session()
        session._lib.GciPerform.return_value = gemstone.OOP_ILLEGAL

        with self.assertRaises(gemstone.GemStoneError):
            session.perform_oop(123, "missing")

        span = tracer.started[0][2]
        self.assertEqual(span.attributes["status"], "error")
        self.assertEqual(span.attributes["error"], "GemStoneError")
        self.assertEqual(span.exceptions, ["GemStoneError"])
        self.assertEqual(
            metrics.increments,
            [
                (
                    "gemstone_py_session_operations",
                    {"operation": "perform_oop", "status": "error"},
                    1,
                )
            ],
        )

    def test_slow_operation_logger_uses_threshold(self):
        session, _tracer, _metrics = _observed_session()
        session.slow_query_threshold_ms = 0.0
        session._lib.GciCommit.return_value = True

        with self.assertLogs("gemstone_py.slow_queries", level="WARNING") as logs:
            session.commit()

        self.assertIn("slow GemStone operation commit", logs.output[0])


if __name__ == "__main__":
    unittest.main()
