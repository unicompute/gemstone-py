import unittest

import gemstone_py as gemstone
from gemstone_py import web as gemstone_web
from gemstone_py.aio import AsyncSession
from gemstone_py.aio import litestar as litestar_adapter
from gemstone_py.aio.pool import AsyncSessionPool
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
