import unittest
from unittest import mock

import gemstone_py as gemstone
from gemstone_py import web as gemstone_web


class _FakeApp:
    def __init__(self):
        self.extensions = {}
        self.session_interface = type("SessionInterface", (), {})()
        self.after_request_funcs = []
        self.after_serving_funcs = []
        self.before_serving_funcs = []
        self.teardown_request_funcs = []

    def after_request(self, func):
        self.after_request_funcs.append(func)
        return func

    def after_serving(self, func):
        self.after_serving_funcs.append(func)
        return func

    def before_serving(self, func):
        self.before_serving_funcs.append(func)
        return func

    def teardown_request(self, func):
        self.teardown_request_funcs.append(func)
        return func


class _FakePool:
    def __init__(self, session=None):
        self.session = session if session is not None else object()
        self.acquire_calls = 0
        self.close_calls = 0
        self.warm_calls = []
        self.release_calls = []

    def acquire(self):
        self.acquire_calls += 1
        return self.session

    def release(self, session, *, discard=False, clean=False):
        self.release_calls.append((session, discard, clean))

    def close(self):
        self.close_calls += 1

    def warm(self, count=None):
        self.warm_calls.append(count)
        return 1 if count not in (None, 0) else 0


class _PoolSession:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.abort_calls = 0
        self.login_calls = 0
        self.logout_calls = 0

    def abort(self):
        self.abort_calls += 1

    def login(self):
        self.login_calls += 1

    def logout(self):
        self.logout_calls += 1


class _ValidationSession(_PoolSession):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.eval_calls = []

    def eval(self, source):
        self.eval_calls.append(source)
        return 2


class _ThreadAwarePoolSession(_PoolSession):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.claim_thread_calls = 0
        self.release_thread_calls = []

    def _claim_thread_ownership(self):
        self.claim_thread_calls += 1

    def _release_thread_ownership(self, *, force=False):
        self.release_thread_calls.append(force)


class _RecordingSpan:
    def __init__(self):
        self.attributes = {}

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def record_exception(self, exc):
        del exc


class _RecordingSpanContext:
    def __init__(self, span):
        self.span = span

    def __enter__(self):
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        del exc_type, exc_val, exc_tb
        return False


class _RecordingTracer:
    def __init__(self):
        self.started = []

    def start_span(self, name, attrs=None):
        span = _RecordingSpan()
        context = _RecordingSpanContext(span)
        self.started.append((name, dict(attrs or {}), span))
        return context


class _RecordingMetrics:
    def __init__(self):
        self.increments = []
        self.durations = []

    def increment(self, name, labels=None, value=1):
        self.increments.append((name, dict(labels or {}), value))

    def record_duration(self, name, labels, duration_ms):
        self.durations.append((name, dict(labels or {}), duration_ms))


class GemStoneRequestSessionTests(unittest.TestCase):
    def test_session_scope_reuses_request_scoped_session(self):
        marker = object()

        with mock.patch.object(
            gemstone_web,
            "_get_or_create_flask_request_session",
            return_value=marker,
        ) as get_request_session:
            with mock.patch.object(gemstone_web, "GemStoneSession") as session_cls:
                with gemstone.session_scope() as session:
                    self.assertIs(session, marker)

        get_request_session.assert_called_once_with()
        session_cls.assert_not_called()

    def test_session_scope_falls_back_to_new_session_when_no_request_session(self):
        marker = object()
        session_cm = mock.MagicMock()
        session_cm.__enter__.return_value = marker
        session_cm.__exit__.return_value = False

        with mock.patch.object(
            gemstone_web,
            "_get_or_create_flask_request_session",
            return_value=None,
        ):
            with mock.patch.object(gemstone_web, "GemStoneSession", return_value=session_cm) as session_cls:
                with gemstone.session_scope(stone="demo") as session:
                    self.assertIs(session, marker)

        session_cls.assert_called_once_with(
            stone="demo",
            transaction_policy=gemstone.TransactionPolicy.COMMIT_ON_SUCCESS,
        )

    def test_finalize_request_session_commits_and_clears_on_success(self):
        flask_g = type("FlaskG", (), {})()
        session = mock.Mock()
        setattr(flask_g, gemstone_web._FLASK_REQUEST_SESSION_ATTR, session)

        with mock.patch.object(gemstone_web, "_flask_request_state", return_value=(object(), flask_g)):
            gemstone.finalize_flask_request_session()

        session.commit.assert_called_once_with()
        session.logout.assert_called_once_with()
        self.assertFalse(hasattr(flask_g, gemstone_web._FLASK_REQUEST_SESSION_ATTR))

    def test_finalize_request_session_aborts_and_clears_on_failure(self):
        flask_g = type("FlaskG", (), {})()
        session = mock.Mock()
        setattr(flask_g, gemstone_web._FLASK_REQUEST_SESSION_ATTR, session)
        exc = RuntimeError("boom")

        with mock.patch.object(gemstone_web, "_flask_request_state", return_value=(object(), flask_g)):
            gemstone.finalize_flask_request_session(exc)

        session.abort.assert_called_once_with()
        session.logout.assert_called_once_with()
        self.assertFalse(hasattr(flask_g, gemstone_web._FLASK_REQUEST_SESSION_ATTR))

    def test_install_flask_request_session_registers_commit_and_abort_hooks(self):
        app = _FakeApp()
        flask_g = type("FlaskG", (), {})()
        response = type("Response", (), {"status_code": 200})()

        with mock.patch.object(gemstone_web, "finalize_flask_request_session") as finalize:
            with mock.patch.object(
                gemstone_web,
                "_flask_request_state",
                return_value=(object(), flask_g),
            ):
                returned = gemstone.install_flask_request_session(app, stone="demo")
                result = app.after_request_funcs[0](response)
                app.teardown_request_funcs[0](None)

        self.assertIs(returned, app)
        self.assertEqual(
            app.extensions[gemstone_web._FLASK_REQUEST_SESSION_EXTENSION]["kwargs"],
            {"stone": "demo"},
        )
        self.assertIsNone(
            app.extensions[gemstone_web._FLASK_REQUEST_SESSION_EXTENSION]["session_provider"]
        )
        self.assertIs(result, response)
        self.assertEqual(
            getattr(flask_g, gemstone_web._FLASK_REQUEST_SESSION_RESPONSE_STATUS_ATTR),
            200,
        )
        finalize.assert_called_once_with()

    def test_install_flask_request_session_aborts_server_error_response(self):
        app = _FakeApp()
        flask_g = type("FlaskG", (), {})()
        response = type("Response", (), {"status_code": 500})()

        with mock.patch.object(gemstone_web, "finalize_flask_request_session") as finalize:
            with mock.patch.object(
                gemstone_web,
                "_flask_request_state",
                return_value=(object(), flask_g),
            ):
                gemstone.install_flask_request_session(app, stone="demo")
                result = app.after_request_funcs[0](response)
                app.teardown_request_funcs[0](None)

        self.assertIs(result, response)
        self.assertEqual(
            getattr(flask_g, gemstone_web._FLASK_REQUEST_SESSION_RESPONSE_STATUS_ATTR),
            500,
        )
        finalize.assert_called_once()
        self.assertIsInstance(finalize.call_args.args[0], RuntimeError)
        self.assertIn("500", str(finalize.call_args.args[0]))

    def test_install_flask_request_session_prefers_exception_abort_over_response_status(self):
        app = _FakeApp()
        flask_g = type("FlaskG", (), {})()
        response = type("Response", (), {"status_code": 200})()
        exc = RuntimeError("boom")

        with mock.patch.object(gemstone_web, "finalize_flask_request_session") as finalize:
            returned = gemstone.install_flask_request_session(app, stone="demo")
            with mock.patch.object(
                gemstone_web,
                "_flask_request_state",
                return_value=(object(), flask_g),
            ):
                result = app.after_request_funcs[0](response)
                app.teardown_request_funcs[0](exc)

        self.assertIs(returned, app)
        self.assertIs(result, response)
        finalize.assert_called_once_with(exc)

    def test_install_flask_request_session_skips_after_request_finalize_for_custom_session_interface(self):
        app = _FakeApp()
        app.session_interface._gemstone_request_session_finalizes = True

        with mock.patch.object(gemstone_web, "finalize_flask_request_session") as finalize:
            gemstone.install_flask_request_session(app)
            response = object()

            result = app.after_request_funcs[0](response)

        self.assertIs(result, response)
        finalize.assert_not_called()

    def test_install_flask_request_session_accepts_explicit_provider(self):
        app = _FakeApp()
        provider = _FakePool()

        gemstone.install_flask_request_session(app, session_provider=provider, stone="demo")

        self.assertIs(
            app.extensions[gemstone_web._FLASK_REQUEST_SESSION_EXTENSION]["session_provider"],
            provider,
        )

    def test_install_flask_request_session_can_register_provider_shutdown(self):
        app = _FakeApp()
        provider = _FakePool()

        with mock.patch.object(gemstone_web.atexit, "register") as register:
            gemstone.install_flask_request_session(
                app,
                session_provider=provider,
                close_at_exit=True,
            )

        register.assert_called_once_with(gemstone.close_flask_request_session_provider, app)

    def test_install_flask_request_session_registers_serving_lifecycle_hooks(self):
        app = _FakeApp()
        provider = _FakePool()

        gemstone.install_flask_request_session(
            app,
            session_provider=provider,
            warmup_sessions=2,
            close_on_after_serving=True,
        )

        app.before_serving_funcs[0]()
        app.after_serving_funcs[0]()

        self.assertEqual(provider.warm_calls, [2])
        self.assertEqual(provider.close_calls, 1)

    def test_session_scope_uses_explicit_pool_and_releases_clean_session(self):
        session = mock.Mock()
        pool = _FakePool(session)

        with gemstone.session_scope(session_pool=pool) as actual:
            self.assertIs(actual, session)

        session.commit.assert_called_once_with()
        self.assertEqual(pool.release_calls, [(session, False, True)])

    def test_get_or_create_request_session_uses_pool_and_caches_session(self):
        app = _FakeApp()
        session = mock.Mock()
        pool = _FakePool(session)
        app.extensions[gemstone_web._FLASK_REQUEST_SESSION_EXTENSION] = {
            "kwargs": {},
            "session_pool": pool,
        }
        flask_g = type("FlaskG", (), {})()

        with mock.patch.object(gemstone_web, "_flask_request_state", return_value=(app, flask_g)):
            first = gemstone_web._get_or_create_flask_request_session()
            second = gemstone_web._get_or_create_flask_request_session()

        self.assertIs(first, session)
        self.assertIs(second, session)
        self.assertEqual(pool.acquire_calls, 1)
        self.assertIs(getattr(flask_g, gemstone_web._FLASK_REQUEST_SESSION_ATTR), session)
        self.assertIs(getattr(flask_g, gemstone_web._FLASK_REQUEST_SESSION_POOL_ATTR), pool)

    def test_finalize_request_session_releases_pooled_session(self):
        flask_g = type("FlaskG", (), {})()
        session = mock.Mock()
        pool = mock.Mock()
        setattr(flask_g, gemstone_web._FLASK_REQUEST_SESSION_ATTR, session)
        setattr(flask_g, gemstone_web._FLASK_REQUEST_SESSION_POOL_ATTR, pool)

        with mock.patch.object(gemstone_web, "_flask_request_state", return_value=(object(), flask_g)):
            gemstone.finalize_flask_request_session()

        session.commit.assert_called_once_with()
        session.logout.assert_not_called()
        pool.release.assert_called_once_with(session, discard=False, clean=True)
        self.assertFalse(hasattr(flask_g, gemstone_web._FLASK_REQUEST_SESSION_ATTR))
        self.assertFalse(hasattr(flask_g, gemstone_web._FLASK_REQUEST_SESSION_POOL_ATTR))

    def test_session_scope_uses_explicit_provider_alias(self):
        session = mock.Mock()
        provider = _FakePool(session)

        with gemstone.session_scope(session_provider=provider) as actual:
            self.assertIs(actual, session)

        session.commit.assert_called_once_with()
        self.assertEqual(provider.release_calls, [(session, False, True)])

    def test_flask_provider_helpers_report_and_close_provider(self):
        app = _FakeApp()
        provider = gemstone.GemStoneSessionPool(
            maxsize=1,
            session_factory=_PoolSession,
            name="web-pool",
            stone="demo",
            username="alice",
            password="secret",
        )
        gemstone.install_flask_request_session(app, session_provider=provider)

        resolved = gemstone.flask_request_session_provider(app)
        snapshot = gemstone.flask_request_session_provider_snapshot(app)

        self.assertIs(resolved, provider)
        self.assertEqual(snapshot.name, "web-pool")
        self.assertEqual(snapshot.provider_type, "GemStoneSessionPool")

        gemstone.close_flask_request_session_provider(app)

        self.assertIsNone(gemstone.flask_request_session_provider(app))
        self.assertEqual(provider.snapshot().close_calls, 1)

    def test_flask_provider_metrics_helper_returns_dict(self):
        app = _FakeApp()
        provider = gemstone.GemStoneSessionPool(
            maxsize=1,
            session_factory=_PoolSession,
            name="web-pool",
            stone="demo",
            username="alice",
            password="secret",
        )
        gemstone.install_flask_request_session(app, session_provider=provider)

        metrics = gemstone.flask_request_session_provider_metrics(app)

        self.assertEqual(metrics["name"], "web-pool")
        self.assertEqual(metrics["provider_type"], "GemStoneSessionPool")


class GemStoneSessionPoolTests(unittest.TestCase):
    def test_pool_creates_manual_sessions_and_reuses_clean_session(self):
        created = []

        def factory(**kwargs):
            session = _PoolSession(**kwargs)
            created.append(session)
            return session

        pool = gemstone.GemStoneSessionPool(
            maxsize=1,
            session_factory=factory,
            stone="demo",
            username="alice",
            password="secret",
        )

        first = pool.acquire()
        pool.release(first)
        second = pool.acquire()
        pool.release(second, clean=True)
        pool.close()

        self.assertIs(first, second)
        self.assertEqual(first.login_calls, 1)
        self.assertEqual(first.abort_calls, 1)
        self.assertEqual(first.logout_calls, 1)
        self.assertEqual(first.kwargs["stone"], "demo")
        self.assertIs(first.kwargs["transaction_policy"], gemstone.TransactionPolicy.MANUAL)

    def test_pool_unbinds_idle_sessions_and_reclaims_on_checkout(self):
        pool = gemstone.GemStoneSessionPool(
            maxsize=1,
            session_factory=_ThreadAwarePoolSession,
            stone="demo",
            username="alice",
            password="secret",
        )

        pool.warm(1)
        session = pool.acquire()
        pool.release(session, clean=True)
        pool.close()

        self.assertEqual(session.claim_thread_calls, 1)
        self.assertEqual(session.release_thread_calls, [False, False])
        self.assertEqual(session.logout_calls, 1)

    def test_pool_snapshot_tracks_capacity_and_operations(self):
        pool = gemstone.GemStoneSessionPool(
            maxsize=1,
            session_factory=_PoolSession,
            name="metrics-pool",
            stone="demo",
            username="alice",
            password="secret",
        )

        session = pool.acquire()
        during = pool.snapshot()
        pool.release(session)
        after_release = pool.snapshot()
        pool.close()
        after_close = pool.snapshot()

        self.assertEqual(during.name, "metrics-pool")
        self.assertEqual(during.maxsize, 1)
        self.assertEqual(during.minsize, 0)
        self.assertEqual(during.in_use, 1)
        self.assertEqual(after_release.available, 1)
        self.assertEqual(after_release.created_total, 1)
        self.assertEqual(after_release.acquire_calls, 1)
        self.assertEqual(after_release.release_calls, 1)
        self.assertTrue(after_close.closed)

    def test_pool_stats_exposes_capacity_contract(self):
        pool = gemstone.GemStoneSessionPool(
            maxsize=1,
            session_factory=_PoolSession,
            stone="demo",
            username="alice",
            password="secret",
        )

        session = pool.acquire()
        pool.release(session, clean=True)
        stats = pool.stats()
        pool.close()

        self.assertIsInstance(stats, gemstone.GemStoneSessionPoolStats)
        self.assertEqual(stats.in_use, 0)
        self.assertEqual(stats.idle, 1)
        self.assertEqual(stats.current_capacity, 1)
        self.assertEqual(stats.created_total, 1)
        self.assertEqual(stats.evicted_total, 0)
        self.assertEqual(stats.validation_failures, 0)
        self.assertEqual(stats.acquire_waits_total, 1)

    def test_pool_validation_query_runs_after_interval(self):
        pool = gemstone.GemStoneSessionPool(
            maxsize=1,
            session_factory=_ValidationSession,
            validation_query="1 + 1",
            validation_interval_seconds=999,
            stone="demo",
            username="alice",
            password="secret",
        )

        first = pool.acquire()
        pool.release(first, clean=True)
        setattr(first, "_gemstone_provider_validated_at", 0.0)
        second = pool.acquire()
        pool.release(second, discard=True)
        pool.close()

        self.assertIs(first, second)
        self.assertEqual(first.eval_calls, ["1 + 1", "1 + 1"])

    def test_pool_discards_idle_sessions_on_checkout(self):
        created = []

        def factory(**kwargs):
            session = _PoolSession(**kwargs)
            created.append(session)
            return session

        pool = gemstone.GemStoneSessionPool(
            maxsize=1,
            session_factory=factory,
            idle_timeout_seconds=999,
            stone="demo",
            username="alice",
            password="secret",
        )

        first = pool.acquire()
        pool.release(first, clean=True)
        setattr(first, "_gemstone_provider_last_used_at", 0.0)
        second = pool.acquire()
        pool.release(second, discard=True)
        pool.close()

        self.assertIsNot(first, second)
        self.assertEqual(created, [first, second])
        self.assertEqual(pool.snapshot().idle_timeout_discards, 1)

    def test_pool_sweep_idle_discards_available_sessions(self):
        created = []

        def factory(**kwargs):
            session = _PoolSession(**kwargs)
            created.append(session)
            return session

        pool = gemstone.GemStoneSessionPool(
            maxsize=2,
            session_factory=factory,
            idle_timeout_seconds=999,
            stone="demo",
            username="alice",
            password="secret",
        )

        pool.warm(2)
        for session in created:
            setattr(session, "_gemstone_provider_last_used_at", 0.0)
        swept = pool.sweep_idle()
        snapshot = pool.snapshot()
        pool.close()

        self.assertEqual(swept, 2)
        self.assertEqual(snapshot.created, 0)
        self.assertEqual(snapshot.available, 0)
        self.assertEqual(snapshot.idle_timeout_discards, 2)
        self.assertTrue(all(session.logout_calls == 1 for session in created))

    def test_pool_sweep_idle_respects_minsize(self):
        created = []

        def factory(**kwargs):
            session = _PoolSession(**kwargs)
            created.append(session)
            return session

        pool = gemstone.GemStoneSessionPool(
            maxsize=2,
            minsize=1,
            session_factory=factory,
            idle_timeout_seconds=999,
            stone="demo",
            username="alice",
            password="secret",
        )

        pool.warm(2)
        for session in created:
            setattr(session, "_gemstone_provider_last_used_at", 0.0)
        swept = pool.sweep_idle()
        snapshot = pool.snapshot()
        pool.close()

        self.assertEqual(swept, 1)
        self.assertEqual(snapshot.minsize, 1)
        self.assertEqual(snapshot.created, 1)
        self.assertEqual(snapshot.available, 1)
        self.assertEqual(snapshot.idle_timeout_discards, 1)

    def test_pool_sweeper_thread_starts_when_idle_timeout_is_configured(self):
        pool = gemstone.GemStoneSessionPool(
            maxsize=1,
            session_factory=_PoolSession,
            idle_timeout_seconds=999,
            idle_sweep_interval_seconds=999,
            stone="demo",
            username="alice",
            password="secret",
        )

        thread = pool._idle_sweeper_thread
        pool.close()

        self.assertIsNotNone(thread)
        self.assertFalse(thread.is_alive())

    def test_pool_timeout_raises_timeout_error(self):
        pool = gemstone.GemStoneSessionPool(
            maxsize=1,
            session_factory=_PoolSession,
            acquire_timeout=0,
            stone="demo",
            username="alice",
            password="secret",
        )

        session = pool.acquire()
        with self.assertRaises(TimeoutError):
            pool.acquire()
        pool.release(session, discard=True)
        pool.close()

        self.assertEqual(pool.snapshot().timeout_calls, 1)

    def test_pool_discards_unhealthy_reused_sessions(self):
        sessions = []

        def factory(**kwargs):
            session = _PoolSession(**kwargs)
            sessions.append(session)
            return session

        health = mock.Mock(side_effect=[True, False, True])
        pool = gemstone.GemStoneSessionPool(
            maxsize=1,
            session_factory=factory,
            session_healthcheck=health,
            stone="demo",
            username="alice",
            password="secret",
        )

        first = pool.acquire()
        pool.release(first, clean=True)
        second = pool.acquire()
        pool.release(second, discard=True)
        pool.close()

        self.assertIsNot(first, second)
        snapshot = pool.snapshot()
        self.assertEqual(snapshot.healthcheck_failures, 1)
        self.assertGreaterEqual(snapshot.discard_calls, 2)

    def test_pool_recycles_session_after_max_session_uses(self):
        created = []

        def factory(**kwargs):
            session = _PoolSession(**kwargs)
            created.append(session)
            return session

        pool = gemstone.GemStoneSessionPool(
            maxsize=1,
            max_session_uses=1,
            session_factory=factory,
            stone="demo",
            username="alice",
            password="secret",
        )

        first = pool.acquire()
        pool.release(first, clean=True)
        second = pool.acquire()
        pool.release(second, discard=True)
        pool.close()

        self.assertIsNot(first, second)
        self.assertEqual(pool.snapshot().recycle_use_discards, 1)

    def test_pool_metrics_exporter_and_event_listener_receive_observations(self):
        snapshots = []
        events = []
        pool = gemstone.GemStoneSessionPool(
            maxsize=1,
            session_factory=_PoolSession,
            metrics_exporter=snapshots.append,
            event_listener=events.append,
            stone="demo",
            username="alice",
            password="secret",
        )

        session = pool.acquire()
        pool.release(session, clean=True)
        pool.close()

        self.assertTrue(any(s.provider_type == "GemStoneSessionPool" for s in snapshots))
        self.assertIn("session_acquired", [event.name for event in events])
        self.assertIn("session_released", [event.name for event in events])
        self.assertIn("provider_closed", [event.name for event in events])

    def test_pool_emits_standard_observability_metrics_and_spans(self):
        metrics = _RecordingMetrics()
        tracer = _RecordingTracer()
        pool = gemstone.GemStoneSessionPool(
            maxsize=1,
            session_factory=_PoolSession,
            metrics=metrics,
            tracer=tracer,
            name="observed-pool",
            stone="demo",
            username="alice",
            password="secret",
        )

        session = pool.acquire()
        pool.release(session, clean=True)
        pool.close()

        event_labels = [labels for name, labels, _value in metrics.increments if name == "gemstone_py_pool_events"]
        self.assertIn(
            {
                "event": "session_acquired",
                "provider": "observed-pool",
                "provider_type": "GemStoneSessionPool",
            },
            event_labels,
        )
        self.assertTrue(
            any(name == "gemstone_py_pool_acquire_wait_ms" for name, _labels, _duration in metrics.durations)
        )
        span_names = [name for name, _attrs, _span in tracer.started]
        self.assertIn("gemstone.pool.session_acquired", span_names)
        acquired_attrs = next(
            attrs for name, attrs, _span in tracer.started if name == "gemstone.pool.session_acquired"
        )
        self.assertEqual(acquired_attrs["provider"], "observed-pool")
        self.assertIn("wait_ms", acquired_attrs)


class GemStoneThreadLocalProviderTests(unittest.TestCase):
    def test_thread_local_provider_reuses_current_thread_session(self):
        created = []

        def factory(**kwargs):
            session = _PoolSession(**kwargs)
            created.append(session)
            return session

        provider = gemstone.GemStoneThreadLocalSessionProvider(
            session_factory=factory,
            stone="demo",
            username="alice",
            password="secret",
        )

        first = provider.acquire()
        provider.release(first, clean=True)
        second = provider.acquire()
        provider.release(second)
        provider.close()

        self.assertIs(first, second)
        self.assertEqual(first.login_calls, 1)
        self.assertEqual(first.abort_calls, 1)
        self.assertEqual(first.logout_calls, 1)
        self.assertEqual(first.kwargs["stone"], "demo")
        self.assertIs(first.kwargs["transaction_policy"], gemstone.TransactionPolicy.MANUAL)

    def test_thread_local_snapshot_reports_close(self):
        provider = gemstone.GemStoneThreadLocalSessionProvider(
            session_factory=_PoolSession,
            name="thread-provider",
            stone="demo",
            username="alice",
            password="secret",
        )

        session = provider.acquire()
        provider.release(session, clean=True)
        before_close = provider.snapshot()
        provider.close()
        after_close = provider.snapshot()

        self.assertEqual(before_close.name, "thread-provider")
        self.assertEqual(before_close.acquire_calls, 1)
        self.assertEqual(before_close.created, 1)
        self.assertTrue(after_close.closed)

    def test_thread_local_provider_discards_unhealthy_created_session(self):
        provider = gemstone.GemStoneThreadLocalSessionProvider(
            session_factory=_PoolSession,
            session_healthcheck=lambda _session: False,
            stone="demo",
            username="alice",
            password="secret",
        )

        with self.assertRaises(RuntimeError):
            provider.acquire()

        snapshot = provider.snapshot()
        self.assertEqual(snapshot.created, 0)
        self.assertEqual(snapshot.discard_calls, 1)
        self.assertEqual(snapshot.healthcheck_failures, 1)

    def test_thread_local_provider_recycles_session_after_max_session_uses(self):
        created = []

        def factory(**kwargs):
            session = _PoolSession(**kwargs)
            created.append(session)
            return session

        provider = gemstone.GemStoneThreadLocalSessionProvider(
            session_factory=factory,
            max_session_uses=1,
            stone="demo",
            username="alice",
            password="secret",
        )

        first = provider.acquire()
        provider.release(first, clean=True)
        second = provider.acquire()
        provider.release(second, discard=True)
        provider.close()

        self.assertIsNot(first, second)
        self.assertEqual(provider.snapshot().recycle_use_discards, 1)


if __name__ == "__main__":
    unittest.main()
