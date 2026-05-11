import unittest

from gemstone_py.web_core import (
    AsyncRequestScope,
    AsyncTransactionScope,
    RequestScope,
    TransactionScope,
    request_failed,
)


class _Session:
    def __init__(self, fail_commit=False, fail_abort=False, **kwargs):
        self.calls = []
        self.kwargs = kwargs
        self.fail_commit = fail_commit
        self.fail_abort = fail_abort

    def login(self):
        self.calls.append("login")

    def logout(self):
        self.calls.append("logout")

    def commit(self):
        self.calls.append("commit")
        if self.fail_commit:
            raise RuntimeError("commit failed")

    def abort(self):
        self.calls.append("abort")
        if self.fail_abort:
            raise RuntimeError("abort failed")


class _Provider:
    def __init__(self, session):
        self.session = session
        self.acquire_calls = 0
        self.release_calls = []

    def acquire(self):
        self.acquire_calls += 1
        return self.session

    def release(self, session, *, discard=False, clean=False):
        self.release_calls.append((session, discard, clean))


class _AsyncSession:
    def __init__(self, **kwargs):
        self.calls = []
        self.kwargs = kwargs

    async def login(self):
        self.calls.append("login")

    async def aclose(self):
        self.calls.append("aclose")

    async def commit(self):
        self.calls.append("commit")

    async def abort(self):
        self.calls.append("abort")


class _AsyncProvider:
    def __init__(self, session):
        self.session = session
        self.acquire_calls = 0
        self.release_calls = []

    async def acquire(self):
        self.acquire_calls += 1
        return self.session

    async def release(self, session, *, discard=False, clean=False):
        self.release_calls.append((session, discard, clean))


class WebCoreTests(unittest.TestCase):
    def test_request_failed_uses_exception_or_server_status(self):
        self.assertFalse(request_failed(response_status=204))
        self.assertTrue(request_failed(response_status=500))
        self.assertTrue(request_failed(exc=RuntimeError("boom"), response_status=200))

    def test_transaction_scope_commits_on_success(self):
        session = _Session()

        outcome = TransactionScope(session).finalize()

        self.assertEqual(outcome.action, "commit")
        self.assertTrue(outcome.clean)
        self.assertEqual(session.calls, ["commit"])

    def test_transaction_scope_aborts_on_failure_without_raising_abort_error(self):
        session = _Session(fail_abort=True)

        outcome = TransactionScope(session).finalize(RuntimeError("boom"))

        self.assertEqual(outcome.action, "abort_failed")
        self.assertFalse(outcome.clean)
        self.assertTrue(outcome.discard)
        self.assertEqual(session.calls, ["abort"])

    def test_request_scope_creates_logs_in_commits_and_logs_out(self):
        scope = RequestScope(
            session_factory=_Session,
            session_kwargs={"stone": "demo"},
        )

        session = scope.session()
        outcome = scope.finalize()

        self.assertEqual(session.kwargs, {"stone": "demo"})
        self.assertEqual(outcome.action, "commit")
        self.assertEqual(session.calls, ["login", "commit", "logout"])

    def test_request_scope_releases_provider_session_with_clean_flag(self):
        session = _Session()
        provider = _Provider(session)
        scope = RequestScope(session_provider=provider)

        self.assertIs(scope.session(), session)
        outcome = scope.finalize(response_status=200)

        self.assertEqual(outcome.action, "commit")
        self.assertEqual(provider.acquire_calls, 1)
        self.assertEqual(provider.release_calls, [(session, False, True)])

    def test_request_scope_releases_provider_session_with_discard_flag(self):
        session = _Session(fail_abort=True)
        provider = _Provider(session)
        scope = RequestScope(session_provider=provider)

        self.assertIs(scope.session(), session)
        outcome = scope.finalize(response_status=503)

        self.assertEqual(outcome.action, "abort_failed")
        self.assertEqual(provider.release_calls, [(session, True, False)])


class AsyncWebCoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_transaction_scope_commits_on_success(self):
        session = _AsyncSession()

        outcome = await AsyncTransactionScope(session).finalize()

        self.assertEqual(outcome.action, "commit")
        self.assertTrue(outcome.clean)
        self.assertEqual(session.calls, ["commit"])

    async def test_async_request_scope_creates_logs_in_commits_and_closes(self):
        scope = AsyncRequestScope(
            session_factory=_AsyncSession,
            session_kwargs={"stone": "demo"},
        )

        session = await scope.session()
        outcome = await scope.finalize()

        self.assertEqual(session.kwargs, {"stone": "demo"})
        self.assertEqual(outcome.action, "commit")
        self.assertEqual(session.calls, ["login", "commit", "aclose"])

    async def test_async_request_scope_releases_provider_session(self):
        session = _AsyncSession()
        provider = _AsyncProvider(session)
        scope = AsyncRequestScope(session_provider=provider)

        self.assertIs(await scope.session(), session)
        outcome = await scope.finalize(response_status=503)

        self.assertEqual(outcome.action, "abort")
        self.assertEqual(provider.acquire_calls, 1)
        self.assertEqual(provider.release_calls, [(session, False, True)])


if __name__ == "__main__":
    unittest.main()
