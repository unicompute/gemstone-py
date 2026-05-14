import asyncio
import threading
import unittest
from unittest import mock

import gemstone_py as gemstone
from gemstone_py.aio import (
    AsyncGSCollection,
    AsyncManagedOop,
    AsyncPersistentRoot,
    AsyncSession,
    AsyncSessionPool,
)
from gemstone_py.aio.fastapi import pool_session_dependency, session_dependency


class RecordingSpan:
    def __init__(self):
        self.attributes = {}

    def set_attribute(self, key, value):
        self.attributes[key] = value

    def record_exception(self, exc):
        del exc


class RecordingSpanContext:
    def __init__(self, span):
        self.span = span

    def __enter__(self):
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        del exc_type, exc_val, exc_tb
        return False


class RecordingTracer:
    def __init__(self):
        self.started = []

    def start_span(self, name, attrs=None):
        span = RecordingSpan()
        context = RecordingSpanContext(span)
        self.started.append((name, dict(attrs or {}), span))
        return context


class RecordingMetrics:
    def __init__(self):
        self.increments = []
        self.durations = []

    def increment(self, name, labels=None, value=1):
        self.increments.append((name, dict(labels or {}), value))

    def record_duration(self, name, labels, duration_ms):
        self.durations.append((name, dict(labels or {}), duration_ms))


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

    def bulk_perform_oop(self, receivers, selector, *args):
        receiver_list = list(receivers)
        self._record(f"bulk_perform_oop:{receiver_list}:{selector}:{args}")
        return [700 + index for index, _receiver in enumerate(receiver_list, 1)]

    def bulk_perform_value(self, receivers, selector, *args):
        receiver_list = list(receivers)
        self._record(f"bulk_perform_value:{receiver_list}:{selector}:{args}")
        return [f"value-{index}" for index, _receiver in enumerate(receiver_list, 1)]

    def bulk_perform_calls_oop(self, calls):
        call_list = list(calls)
        self._record(f"bulk_perform_calls_oop:{call_list}")
        return [800 + index for index, _call in enumerate(call_list, 1)]

    def bulk_perform_calls_value(self, calls):
        call_list = list(calls)
        self._record(f"bulk_perform_calls_value:{call_list}")
        return [f"call-value-{index}" for index, _call in enumerate(call_list, 1)]

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

    async def test_async_session_delegates_bulk_perform(self):
        created = []

        def factory(**kwargs):
            session = FakeGemStoneSession(**kwargs)
            created.append(session)
            return session

        session = AsyncSession(session_factory=factory)

        oops = await session.bulk_perform_oop([101, 202], "size")
        values = await session.perform_many_value([101, 202], "name")
        call_oops = await session.perform_calls_oop([(101, "size"), (202, "name")])
        call_values = await session.bulk_perform_calls_value([(101, "size"), (202, "name")])
        session.close()

        self.assertEqual(oops, [701, 702])
        self.assertEqual(values, ["value-1", "value-2"])
        self.assertEqual(call_oops, [801, 802])
        self.assertEqual(call_values, ["call-value-1", "call-value-2"])
        self.assertEqual(
            created[0].calls,
            [
                "bulk_perform_oop:[101, 202]:size:()",
                "bulk_perform_value:[101, 202]:name:()",
                "bulk_perform_calls_oop:[(101, 'size'), (202, 'name')]",
                "bulk_perform_calls_value:[(101, 'size'), (202, 'name')]",
            ],
        )

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

    async def test_async_persistent_root_delegates_batch_helpers(self):
        class FakeRoot:
            instances = []

            def __init__(self, sync_session, name):
                self.sync_session = sync_session
                self.name = name
                self.calls = []
                self.instances.append(self)

            def get_many(self, keys, default=None):
                key_list = list(keys)
                self.calls.append(("get_many", key_list, default))
                return {key: default for key in key_list}

            def update_many(self, other=None, /, **kwargs):
                self.calls.append(("update_many", other, kwargs))

        sync_session = FakeGemStoneSession()
        session = AsyncSession(session=sync_session)

        with mock.patch("gemstone_py.aio.persistent_root.PersistentRoot", FakeRoot):
            root = AsyncPersistentRoot(session, "UserGlobals")
            result = await root.get_many((key for key in ["Alpha", "Beta"]), default="missing")
            await root.update_many({"Alpha": 1}, Beta=2)

        session.close()

        self.assertEqual(result, {"Alpha": "missing", "Beta": "missing"})
        fake_root = FakeRoot.instances[0]
        self.assertIs(fake_root.sync_session, sync_session)
        self.assertEqual(fake_root.name, "UserGlobals")
        self.assertEqual(
            fake_root.calls,
            [
                ("get_many", ["Alpha", "Beta"], "missing"),
                ("update_many", {"Alpha": 1}, {"Beta": 2}),
            ],
        )


class AsyncSessionPoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_pool_reuses_clean_sessions(self):
        created = []

        def factory(**kwargs):
            session = FakeGemStoneSession(**kwargs)
            created.append(session)
            return session

        pool = AsyncSessionPool(maxsize=1, session_factory=factory, stone="demo")

        first = await pool.acquire()
        await pool.release(first, clean=True)
        second = await pool.acquire()
        await pool.release(second, discard=True)
        await pool.close()

        self.assertIs(first, second)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].calls, ["login", "logout"])
        self.assertEqual(created[0].kwargs["transaction_policy"], gemstone.TransactionPolicy.MANUAL)

    async def test_pool_context_manager_aborts_before_release(self):
        created = []

        def factory(**kwargs):
            session = FakeGemStoneSession(**kwargs)
            created.append(session)
            return session

        pool = AsyncSessionPool(maxsize=1, session_factory=factory)

        async with pool.acquire() as session:
            self.assertIsInstance(session, AsyncSession)

        stats = pool.stats()
        await pool.close()

        self.assertEqual(stats.idle, 1)
        self.assertEqual(created[0].calls, ["login", "abort", "logout"])

    async def test_pool_timeout_raises_timeout_error(self):
        pool = AsyncSessionPool(maxsize=1, session_factory=FakeGemStoneSession, acquire_timeout=0)

        session = await pool.acquire()
        with self.assertRaises(TimeoutError):
            await pool.acquire()
        await pool.release(session, discard=True)
        await pool.close()

    async def test_pool_validation_query_runs_after_interval(self):
        created = []

        def factory(**kwargs):
            session = FakeGemStoneSession(**kwargs)
            created.append(session)
            return session

        pool = AsyncSessionPool(
            maxsize=1,
            session_factory=factory,
            validation_query="1 + 1",
            validation_interval_seconds=999,
        )

        first = await pool.acquire()
        await pool.release(first, clean=True)
        setattr(first, "_gemstone_pool_validated_at", 0.0)
        second = await pool.acquire()
        await pool.release(second, discard=True)
        await pool.close()

        self.assertIs(first, second)
        self.assertEqual(created[0].calls, ["login", "eval:1 + 1", "eval:1 + 1", "logout"])

    async def test_pool_sweep_idle_respects_minsize(self):
        pool = AsyncSessionPool(
            maxsize=2,
            minsize=1,
            session_factory=FakeGemStoneSession,
            idle_timeout_seconds=999,
        )

        await pool.warm(2)
        drained = []
        while True:
            try:
                session = pool._available.get_nowait()
            except asyncio.QueueEmpty:
                break
            setattr(session, "_gemstone_pool_last_used_at", 0.0)
            drained.append(session)
        for session in drained:
            pool._available.put_nowait(session)

        swept = await pool.sweep_idle()
        stats = pool.stats()
        await pool.close()

        self.assertEqual(swept, 1)
        self.assertEqual(stats.current_capacity, 1)
        self.assertEqual(stats.idle, 1)
        self.assertEqual(stats.evicted_total, 1)

    async def test_pool_session_dependency_commits_and_releases_clean_session(self):
        created = []

        def factory(**kwargs):
            session = FakeGemStoneSession(**kwargs)
            created.append(session)
            return session

        pool = AsyncSessionPool(maxsize=1, session_factory=factory)
        dependency = pool_session_dependency(pool)
        generator = dependency()

        session = await generator.__anext__()
        self.assertIsInstance(session, AsyncSession)
        with self.assertRaises(StopAsyncIteration):
            await generator.__anext__()

        stats = pool.stats()
        await pool.close()

        self.assertEqual(stats.idle, 1)
        self.assertEqual(created[0].calls, ["login", "commit", "logout"])

    async def test_pool_emits_standard_observability_metrics_and_spans(self):
        metrics = RecordingMetrics()
        tracer = RecordingTracer()
        pool = AsyncSessionPool(
            maxsize=1,
            session_factory=FakeGemStoneSession,
            metrics=metrics,
            tracer=tracer,
        )

        session = await pool.acquire()
        await pool.release(session, clean=True)
        await pool.close()

        event_labels = [labels for name, labels, _value in metrics.increments if name == "gemstone_py_pool_events"]
        self.assertIn(
            {
                "event": "session_acquired",
                "provider": "AsyncSessionPool",
                "provider_type": "AsyncSessionPool",
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
        self.assertIn("wait_ms", acquired_attrs)


class AsyncCollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_collection_delegates_to_sync_collection(self):
        collection = mock.Mock()
        collection.search.return_value = [{"@name": "Alice"}]
        async_collection = AsyncGSCollection("People", collection=collection)

        result = await async_collection.search("@name", "eql", "Alice")

        async_collection.close()
        self.assertEqual(result, [{"@name": "Alice"}])
        collection.search.assert_called_once_with("@name", "eql", "Alice")

    async def test_async_collection_iter_yields_sync_chunks(self):
        collection = mock.Mock()
        collection.iter.return_value = iter([{"@name": "Alice"}, {"@name": "Bob"}])
        async_collection = AsyncGSCollection("People", collection=collection)

        result = [record async for record in async_collection.iter(chunk_size=2)]

        async_collection.close()
        self.assertEqual(result, [{"@name": "Alice"}, {"@name": "Bob"}])
        collection.iter.assert_called_once_with(chunk_size=2)


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

        self.assertEqual(created[0].calls, ["login", "commit", "logout"])

    async def test_session_dependency_aborts_after_handler_error(self):
        created = []

        def factory(**kwargs):
            session = FakeGemStoneSession(**kwargs)
            created.append(session)
            return session

        dependency = session_dependency(session_factory=factory)
        generator = dependency()
        session = await generator.__anext__()
        self.assertIsInstance(session, AsyncSession)

        with self.assertRaises(RuntimeError):
            await generator.athrow(RuntimeError("boom"))

        self.assertEqual(created[0].calls, ["login", "abort", "logout"])


if __name__ == "__main__":
    unittest.main()
