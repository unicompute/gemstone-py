import asyncio
import os
import unittest
import uuid

import gemstone_py as gemstone
from gemstone_py.aio import AsyncGSCollection, AsyncManagedOop, AsyncPersistentRoot, AsyncSession
from gemstone_py.aio.fastapi import GemStoneSessionMiddleware
from gemstone_py.persistent_root import PersistentRoot
from tests.test_live_integration import LiveIntegrationTests

RUN_LIVE = os.environ.get("GS_RUN_LIVE") == "1"


@unittest.skipUnless(RUN_LIVE, "set GS_RUN_LIVE=1 to run live async GemStone tests")
class AsyncLiveGemStoneTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = gemstone.GemStoneConfig.from_env()

    def _cleanup_root(self, *keys: str) -> None:
        with gemstone.GemStoneSession(
            config=self.config,
            transaction_policy=gemstone.TransactionPolicy.COMMIT_ON_SUCCESS,
        ) as session:
            root = PersistentRoot(session)
            for key in keys:
                if key in root:
                    del root[key]

    async def test_async_session_execute_transaction_and_error_propagation(self) -> None:
        async with AsyncSession.connect(config=self.config) as session:
            self.assertEqual(await session.eval("3 + 4"), 7)
            ref = await session.execute_managed("Object new")
            self.assertIsInstance(ref, AsyncManagedOop)
            self.assertTrue(await ref.print_string())

            async with session.transaction():
                self.assertTrue(await session.eval("System myUserProfile notNil"))

            with self.assertRaises(gemstone.GemStoneError):
                await session.resolve(f"MissingAsyncGlobal_{uuid.uuid4().hex}")

    async def test_async_persistent_root_round_trip(self) -> None:
        key = f"AsyncLiveRoot_{uuid.uuid4().hex}"
        payload = {"name": "Async Root", "count": 9}
        self._cleanup_root(key)
        try:
            async with AsyncSession.connect(config=self.config) as session:
                root = AsyncPersistentRoot(session)
                await root.set(key, payload)
                await session.commit()

            async with AsyncSession.connect(config=self.config) as session:
                root = AsyncPersistentRoot(session)
                self.assertTrue(await root.contains(key))
                stored = await root.get(key)
                self.assertEqual(stored["name"], payload["name"])
                self.assertEqual(stored["count"], payload["count"])
        finally:
            self._cleanup_root(key)

    async def test_async_gscollection_indexed_search(self) -> None:
        name = f"AsyncLiveGSCollection_{uuid.uuid4().hex}"
        col = AsyncGSCollection(name, config=self.config)
        try:
            await col.insert({"@name": "Alice", "@age": 30})
            await col.insert({"@name": "Bob", "@age": 24})
            await col.add_index("@age")

            results = await col.search("@age", "lt", 25)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["@name"], "Bob")
            self.assertEqual(results[0]["@age"], 24)
        finally:
            await AsyncGSCollection.drop(name, config=self.config)
            col.close()

    async def test_async_lifetime_handle_survives_gemstone_gc(self) -> None:
        async with AsyncSession.connect(config=self.config) as session:
            ref = await session.execute_managed("Object new")
            self.assertTrue(await ref.print_string())
            await session.eval("System startGcAndCommit")
            self.assertTrue(await ref.print_string())

            async with session.handle(ref.oop) as handle:
                await session.eval("System startGcAndCommit")
                self.assertTrue(await handle.send("printString"))

            await ref.close()

    async def test_fastapi_middleware_request_transaction_commits(self) -> None:
        key = f"AsyncFastAPILive_{uuid.uuid4().hex}"
        self._cleanup_root(key)

        async def app(scope, receive, send):
            del receive
            session = scope["state"]["gemstone_session"]
            root = AsyncPersistentRoot(session)
            await root.set(key, {"status": "committed"})
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b"ok"})

        sent = []

        async def send(message):
            sent.append(message)

        middleware = GemStoneSessionMiddleware(app, config=self.config)
        try:
            await middleware(
                {"type": "http", "state": {}},
                lambda: {"type": "http.request", "body": b"", "more_body": False},
                send,
            )

            with gemstone.GemStoneSession(
                config=self.config,
                transaction_policy=gemstone.TransactionPolicy.ABORT_ON_EXIT,
            ) as session:
                root = PersistentRoot(session)
                self.assertEqual(root[key]["status"], "committed")
        finally:
            self._cleanup_root(key)


@unittest.skipUnless(RUN_LIVE, "set GS_RUN_LIVE=1 to run async live parity tests")
class AsyncLiveIntegrationParityTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        LiveIntegrationTests.setUpClass()

    @classmethod
    def tearDownClass(cls) -> None:
        tear_down = getattr(LiveIntegrationTests, "tearDownClass", None)
        if tear_down is not None:
            tear_down()

    @staticmethod
    def _run_sync_live_test(method_name: str) -> None:
        case = LiveIntegrationTests(methodName=method_name)
        case.setUp()
        try:
            getattr(case, method_name)()
        finally:
            case.tearDown()


def _make_async_parity_test(method_name: str):
    async def test(self: AsyncLiveIntegrationParityTests) -> None:
        await asyncio.to_thread(self._run_sync_live_test, method_name)

    test.__name__ = f"test_async_parity_{method_name}"
    return test


for _name in sorted(name for name in dir(LiveIntegrationTests) if name.startswith("test_")):
    setattr(
        AsyncLiveIntegrationParityTests,
        f"test_async_parity_{_name}",
        _make_async_parity_test(_name),
    )


if __name__ == "__main__":
    unittest.main()
