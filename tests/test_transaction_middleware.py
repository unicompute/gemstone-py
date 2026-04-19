import contextlib
import io
import unittest

import gemstone_py as gemstone
from examples.flask.transaction_middleware import (
    GemStoneTransactionMiddleware,
    ManagedGemStoneTransactionMiddleware,
    PooledGemStoneTransactionMiddleware,
    ThreadLocalGemStoneTransactionMiddleware,
)


class FakeSession:
    def __init__(self, commit_error=None, abort_error=None):
        self.abort_calls = 0
        self.commit_calls = 0
        self.commit_error = commit_error
        self.abort_error = abort_error

    def abort(self):
        self.abort_calls += 1
        if self.abort_error is not None:
            raise self.abort_error

    def commit(self):
        self.commit_calls += 1
        if self.commit_error is not None:
            raise self.commit_error


class ClosableIterable:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.closed = False

    def __iter__(self):
        return iter(self._chunks)

    def close(self):
        self.closed = True


class FakePool:
    def __init__(self, session):
        self.session = session
        self.acquire_calls = 0
        self.release_calls = 0

    def acquire(self):
        self.acquire_calls += 1
        return self.session

    def release(self, session):
        self.release_calls += 1
        self.session = session


class TransactionMiddlewareTests(unittest.TestCase):
    def _invoke(self, app, session, environ=None):
        captured = {}

        def start_response(status, headers, exc_info=None):
            captured["status"] = status
            captured["headers"] = headers
            captured["exc_info"] = exc_info
            return lambda _chunk: None

        middleware = GemStoneTransactionMiddleware(app, session)
        with contextlib.redirect_stderr(io.StringIO()):
            body = middleware(environ or {"PATH_INFO": "/demo"}, start_response)
        return captured, body

    def test_commits_successful_response(self):
        def app(_environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"ok"]

        session = FakeSession()
        captured, body = self._invoke(app, session)

        self.assertEqual(captured["status"], "200 OK")
        self.assertEqual(body, [b"ok"])
        self.assertEqual(session.abort_calls, 1)
        self.assertEqual(session.commit_calls, 1)

    def test_uncommittable_response_aborts_instead(self):
        def app(_environ, start_response):
            start_response("500 Internal Server Error", [("Content-Type", "text/plain")])
            return [b"bad"]

        session = FakeSession()
        captured, body = self._invoke(app, session)

        self.assertEqual(captured["status"], "500 Internal Server Error")
        self.assertEqual(body, [b"bad"])
        self.assertEqual(session.abort_calls, 2)
        self.assertEqual(session.commit_calls, 0)

    def test_app_exception_returns_500(self):
        def app(_environ, _start_response):
            raise RuntimeError("boom")

        session = FakeSession()
        captured, body = self._invoke(app, session)

        self.assertEqual(captured["status"], "500 Internal Server Error")
        self.assertEqual(body, [b"Internal server error"])
        self.assertEqual(session.abort_calls, 2)
        self.assertEqual(session.commit_calls, 0)

    def test_commit_failure_returns_500_and_closes_body(self):
        result = ClosableIterable([b"payload"])

        def app(_environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return result

        session = FakeSession(commit_error=gemstone.GemStoneError("commit failed"))
        captured, body = self._invoke(app, session)

        self.assertEqual(captured["status"], "500 Internal Server Error")
        self.assertEqual(body, [b"GemStone commit failed: commit failed"])
        self.assertTrue(result.closed)
        self.assertEqual(session.abort_calls, 2)
        self.assertEqual(session.commit_calls, 1)

    def test_missing_start_response_is_treated_as_error(self):
        def app(_environ, _start_response):
            return [b"orphaned"]

        session = FakeSession()
        captured, body = self._invoke(app, session)

        self.assertEqual(captured["status"], "500 Internal Server Error")
        self.assertEqual(body, [b"WSGI app failed to call start_response"])
        self.assertEqual(session.abort_calls, 2)
        self.assertEqual(session.commit_calls, 0)

    def test_pooled_middleware_borrows_and_releases_one_session(self):
        def app(_environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"ok"]

        session = FakeSession()
        pool = FakePool(session)
        captured = {}

        def start_response(status, headers, exc_info=None):
            captured["status"] = status
            captured["headers"] = headers
            captured["exc_info"] = exc_info
            return lambda _chunk: None

        middleware = PooledGemStoneTransactionMiddleware(app, pool)
        with contextlib.redirect_stderr(io.StringIO()):
            body = middleware({"PATH_INFO": "/pooled"}, start_response)

        self.assertEqual(captured["status"], "200 OK")
        self.assertEqual(body, [b"ok"])
        self.assertEqual(session.abort_calls, 1)
        self.assertEqual(session.commit_calls, 1)
        self.assertEqual(pool.acquire_calls, 1)
        self.assertEqual(pool.release_calls, 1)

    def test_managed_middleware_uses_generic_provider_interface(self):
        def app(_environ, start_response):
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"ok"]

        session = FakeSession()
        provider = FakePool(session)
        captured = {}

        def start_response(status, headers, exc_info=None):
            captured["status"] = status
            return lambda _chunk: None

        middleware = ManagedGemStoneTransactionMiddleware(app, provider)
        with contextlib.redirect_stderr(io.StringIO()):
            body = middleware({"PATH_INFO": "/managed"}, start_response)

        self.assertEqual(captured["status"], "200 OK")
        self.assertEqual(body, [b"ok"])
        self.assertEqual(provider.acquire_calls, 1)
        self.assertEqual(provider.release_calls, 1)

    def test_thread_local_middleware_is_named_managed_variant(self):
        provider = FakePool(FakeSession())
        middleware = ThreadLocalGemStoneTransactionMiddleware(lambda _e, _s: [b"ok"], provider)

        self.assertIsInstance(middleware, ManagedGemStoneTransactionMiddleware)


if __name__ == "__main__":
    unittest.main()
