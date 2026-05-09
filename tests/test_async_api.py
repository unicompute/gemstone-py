import threading
import unittest
from unittest import mock

import gemstone_py as gemstone
from gemstone_py.aio import AsyncGSCollection, AsyncManagedOop, AsyncSession
from gemstone_py.aio.fastapi import session_dependency


class FakeGemStoneSession:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._logged_in = False
        self.calls = []
        self.thread_ids = []
        self.transaction_policy = kwargs.get(
            "transaction_policy",
            gemstone.TransactionPolicy.MANUAL,
        )

    def _record(self, name):
        self.calls.append(name)
        self.thread_ids.append(threading.get_ident())

    def login(self):
        self._record("login")
        self._logged_in = True

    def logout(self):
        self._record("logout")
        self._logged_in = False

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._record("exit")
        if (
            exc_type is None
            and self.transaction_policy is gemstone.TransactionPolicy.COMMIT_ON_SUCCESS
        ):
            self.commit()
        elif exc_type is not None:
            self.abort()
        self.logout()
        return False

    def eval_oop(self, source):
        self._record(f"eval_oop:{source}")
        return 123

    def eval_managed(self, source):
        self._record(f"eval_managed:{source}")
        return mock.Mock(oop=123)

    def eval(self, source):
        self._record(f"eval:{source}")
        return "value"

    def commit(self):
        self._record("commit")

    def abort(self):
        self._record("abort")


class FailingGemStoneSession(FakeGemStoneSession):
    def eval_oop(self, source):
        self._record(f"eval_oop:{source}")
        raise gemstone.GemStoneError("boom")


class AsyncSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_session_runs_calls_on_one_worker_thread(self):
        created = []

        def factory(**kwargs):
            session = FakeGemStoneSession(**kwargs)
            created.append(session)
            return session

        session = AsyncSession(session_factory=factory)
        await session.login()
        result = await session.execute_managed("3 + 4")
        await session.logout()
        session.close()

        self.assertIsInstance(result, AsyncManagedOop)
        self.assertEqual(result.oop, 123)
        self.assertEqual(created[0].calls, ["login", "eval_managed:3 + 4", "logout"])
        self.assertEqual(len(set(created[0].thread_ids)), 1)
        self.assertNotEqual(created[0].thread_ids[0], threading.get_ident())

    async def test_async_session_propagates_original_gemstone_error(self):
        session = AsyncSession(session_factory=FailingGemStoneSession)
        await session.login()

        with self.assertRaises(gemstone.GemStoneError) as ctx:
            await session.execute_oop("Object error")

        await session.logout()
        session.close()
        self.assertEqual(str(ctx.exception), "boom")

    async def test_transaction_context_commits_or_aborts(self):
        fake = FakeGemStoneSession()
        session = AsyncSession(session=fake)

        async with session.transaction():
            pass

        with self.assertRaises(RuntimeError):
            async with session.transaction():
                raise RuntimeError("fail")

        await session.logout()
        session.close()
        self.assertEqual(fake.calls, ["commit", "abort", "logout"])

    async def test_connect_context_manager_logs_out(self):
        created = []

        def factory(**kwargs):
            session = FakeGemStoneSession(**kwargs)
            created.append(session)
            return session

        async with AsyncSession(session_factory=factory) as session:
            result = await session.execute_managed("1")
            self.assertIsInstance(result, AsyncManagedOop)
            self.assertEqual(result.oop, 123)

        self.assertEqual(created[0].calls, ["login", "eval_managed:1", "exit", "logout"])

    async def test_async_managed_oop_release_is_drained_on_worker_thread(self):
        sync_session = gemstone.GemStoneSession(username="alice", password="secret")
        lib = mock.Mock()
        lib.GciNeedsCommit.return_value = False
        sync_session._lib = lib
        sync_session._logged_in = True
        sync_session._session_id = 41

        session = AsyncSession(session=sync_session)
        managed = await session.managed_oop(0xCAFE)

        self.assertNotEqual(sync_session._owner_thread_id, threading.get_ident())

        managed._managed.close()

        self.assertEqual(sync_session._managed_oop_pending_removals[0xCAFE], 1)
        lib.GciRemoveOopFromExportSet.assert_not_called()

        await session.run_sync(lambda owner_session: owner_session.needs_commit())

        self.assertFalse(sync_session._managed_oop_pending_removals)
        lib.GciRemoveOopFromExportSet.assert_called_once()

        await session.logout()
        session.close()


class AsyncCollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_collection_delegates_to_sync_collection(self):
        collection = mock.Mock()
        collection.search.return_value = [{"@name": "Alice"}]
        async_collection = AsyncGSCollection("People", collection=collection)

        result = await async_collection.search("@name", "eql", "Alice")

        async_collection.close()
        self.assertEqual(result, [{"@name": "Alice"}])
        collection.search.assert_called_once_with("@name", "eql", "Alice")


class FastAPIDependencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_dependency_commits_after_successful_yield(self):
        created = []

        def factory(**kwargs):
            session = FakeGemStoneSession(**kwargs)
            created.append(session)
            return session

        dependency = session_dependency(session_factory=factory)
        generator = dependency()
        session = await generator.__anext__()
        self.assertIsInstance(session, AsyncSession)

        with self.assertRaises(StopAsyncIteration):
            await generator.__anext__()

        self.assertEqual(created[0].calls, ["login", "commit", "exit", "logout"])


if __name__ == "__main__":
    unittest.main()
