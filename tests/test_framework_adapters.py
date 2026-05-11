import unittest

import gemstone_py as gemstone
from gemstone_py import web as gemstone_web
from gemstone_py.aio import AsyncSession
from gemstone_py.aio import litestar as litestar_adapter
from gemstone_py.aio.pool import AsyncSessionPool
from gemstone_py.frameworks import django as django_adapter
from gemstone_py.frameworks import flask as flask_adapter


class _FakeSyncSession:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._logged_in = False
        self.calls = []

    def login(self):
        self.calls.append("login")
        self._logged_in = True

    def logout(self):
        self.calls.append("logout")
        self._logged_in = False

    def commit(self):
        self.calls.append("commit")

    def abort(self):
        self.calls.append("abort")

    def eval(self, source):
        self.calls.append(f"eval:{source}")
        return 7


class _FakeProvider:
    def __init__(self, session):
        self.session = session
        self.releases = []
        self.timeout = None

    def acquire(self, timeout=None):
        self.timeout = timeout
        return self.session

    def release(self, session, *, discard=False, clean=False):
        self.releases.append((session, discard, clean))


class FrameworkAdapterTests(unittest.TestCase):
    def test_flask_adapter_facade_preserves_existing_objects(self):
        self.assertIs(
            flask_adapter.install_flask_request_session,
            gemstone_web.install_flask_request_session,
        )
        self.assertIs(
            flask_adapter.current_flask_request_session,
            gemstone_web.current_flask_request_session,
        )
        self.assertIs(
            flask_adapter.finalize_flask_request_session,
            gemstone_web.finalize_flask_request_session,
        )

    def test_frameworks_module_is_exported(self):
        self.assertIs(gemstone.frameworks.flask, flask_adapter)
        self.assertIs(gemstone.frameworks.django, django_adapter)


class DjangoAdapterTests(unittest.TestCase):
    def test_middleware_commits_factory_session_and_clears_request_state(self):
        created = []

        def factory(**kwargs):
            session = _FakeSyncSession(**kwargs)
            created.append(session)
            return session

        def view(request):
            session = django_adapter.request_session(request)
            self.assertIs(django_adapter.request_session(request), session)
            return type("Response", (), {"status_code": 200})()

        request = type("Request", (), {})()
        middleware = django_adapter.GemStoneSessionMiddleware(view, session_factory=factory)

        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(created[0].calls, ["login", "commit", "logout"])
        self.assertIs(created[0].kwargs["transaction_policy"], gemstone.TransactionPolicy.MANUAL)
        self.assertFalse(hasattr(request, "gemstone_session"))
        self.assertFalse(hasattr(request, "_gemstone_request_scope"))

    def test_middleware_aborts_on_exception(self):
        created = []

        def factory(**kwargs):
            session = _FakeSyncSession(**kwargs)
            created.append(session)
            return session

        def view(request):
            django_adapter.request_session(request)
            raise RuntimeError("boom")

        middleware = django_adapter.GemStoneSessionMiddleware(view, session_factory=factory)

        with self.assertRaises(RuntimeError):
            middleware(type("Request", (), {})())

        self.assertEqual(created[0].calls, ["login", "abort", "logout"])

    def test_middleware_aborts_on_server_error_response(self):
        created = []

        def factory(**kwargs):
            session = _FakeSyncSession(**kwargs)
            created.append(session)
            return session

        def view(request):
            django_adapter.request_session(request)
            return type("Response", (), {"status_code": 503})()

        middleware = django_adapter.GemStoneSessionMiddleware(view, session_factory=factory)

        response = middleware(type("Request", (), {})())

        self.assertEqual(response.status_code, 503)
        self.assertEqual(created[0].calls, ["login", "abort", "logout"])

    def test_middleware_releases_provider_session(self):
        session = _FakeSyncSession()
        provider = _FakeProvider(session)

        def view(request):
            self.assertIs(django_adapter.request_session(request), session)
            return type("Response", (), {"status_code": 200})()

        middleware = django_adapter.GemStoneSessionMiddleware(view, session_provider=provider)

        middleware(type("Request", (), {})())

        self.assertEqual(session.calls, ["commit"])
        self.assertEqual(provider.releases, [(session, False, True)])

    def test_request_session_requires_middleware_scope(self):
        with self.assertRaisesRegex(RuntimeError, "No GemStone request scope"):
            django_adapter.request_session(type("Request", (), {})())


class LitestarAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_dependency_commits_and_closes(self):
        created = []

        def factory(**kwargs):
            session = _FakeSyncSession(**kwargs)
            created.append(session)
            return session

        dependency = litestar_adapter.session_dependency(session_factory=factory)
        generator = dependency()

        session = await generator.__anext__()
        self.assertIsInstance(session, AsyncSession)
        with self.assertRaises(StopAsyncIteration):
            await generator.__anext__()

        self.assertEqual(created[0].calls, ["login", "commit", "logout"])
        self.assertIs(created[0].kwargs["transaction_policy"], gemstone.TransactionPolicy.MANUAL)

    async def test_session_dependency_aborts_on_handler_error(self):
        created = []

        def factory(**kwargs):
            session = _FakeSyncSession(**kwargs)
            created.append(session)
            return session

        dependency = litestar_adapter.session_dependency(session_factory=factory)
        generator = dependency()

        await generator.__anext__()
        with self.assertRaises(RuntimeError):
            await generator.athrow(RuntimeError("boom"))

        self.assertEqual(created[0].calls, ["login", "abort", "logout"])

    async def test_pool_session_dependency_releases_clean_session(self):
        created = []

        def factory(**kwargs):
            session = _FakeSyncSession(**kwargs)
            created.append(session)
            return session

        pool = AsyncSessionPool(maxsize=1, session_factory=factory)
        dependency = litestar_adapter.pool_session_dependency(pool)
        generator = dependency()

        session = await generator.__anext__()
        self.assertIsInstance(session, AsyncSession)
        with self.assertRaises(StopAsyncIteration):
            await generator.__anext__()

        stats = pool.stats()
        await pool.close()

        self.assertEqual(stats.idle, 1)
        self.assertEqual(created[0].calls, ["login", "commit", "logout"])

    async def test_middleware_attaches_session_and_commits_on_2xx(self):
        created = []
        seen_session = []

        def factory(**kwargs):
            session = _FakeSyncSession(**kwargs)
            created.append(session)
            return session

        async def app(scope, _receive, send):
            seen_session.append(scope["state"]["gemstone_session"])
            await send({"type": "http.response.start", "status": 200})
            await send({"type": "http.response.body", "body": b"ok"})

        sent = []

        async def send(message):
            sent.append(message)

        middleware = litestar_adapter.GemStoneSessionMiddleware(app, session_factory=factory)
        scope = {"type": "http"}

        await middleware(scope, object(), send)

        self.assertIsInstance(seen_session[0], AsyncSession)
        self.assertNotIn("gemstone_session", scope["state"])
        self.assertEqual(created[0].calls, ["login", "commit", "logout"])
        self.assertEqual(sent[0]["status"], 200)

    def test_request_session_reads_mapping_or_object_state(self):
        marker = object()
        self.assertIs(
            litestar_adapter.request_session({"state": {"gemstone_session": marker}}),
            marker,
        )

        state = type("State", (), {"gemstone_session": marker})()
        connection = type("Connection", (), {"state": state})()
        self.assertIs(litestar_adapter.request_session(connection), marker)


if __name__ == "__main__":
    unittest.main()
