import importlib.util
import os
import threading
import unittest
import uuid

from gemstone_py import (
    GemStoneConfig,
    GemStoneSession,
    GemStoneSessionPool,
    GemStoneThreadLocalSessionProvider,
    TransactionPolicy,
    close_flask_request_session_provider,
    flask_request_session_provider_metrics,
    flask_request_session_provider_snapshot,
    install_flask_request_session,
    session_scope,
    warm_flask_request_session_provider,
)
from gemstone_py.concurrency import (
    RCCounter,
    RCHash,
    list_instances,
    lock,
    nested_transaction,
    session_count,
    session_id,
    shared_counter_count,
    shared_counter_get,
    shared_counter_increment,
    shared_counter_set,
)
from gemstone_py.gsquery import GSCollection
from gemstone_py.gstore import GStore
from gemstone_py.objectlog import ObjectLog
from gemstone_py.ordered_collection import OrderedCollection
from gemstone_py.persistent_root import PersistentRoot

RUN_LIVE = os.environ.get("GS_RUN_LIVE") == "1"
RUN_DESTRUCTIVE_LIVE = os.environ.get("GS_RUN_DESTRUCTIVE_LIVE") == "1"
HAS_FLASK = importlib.util.find_spec("flask") is not None


@unittest.skipUnless(RUN_LIVE, "set GS_RUN_LIVE=1 to run live GemStone integration tests")
class LiveIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = GemStoneConfig.from_env()

    def _root_cleanup(self, *keys: str) -> None:
        with GemStoneSession(
            config=self.config,
            transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
        ) as session:
            root = PersistentRoot(session)
            for key in keys:
                if key in root:
                    del root[key]

    def test_persistent_root_round_trip_across_sessions(self):
        key = f"LivePersistentRoot_{uuid.uuid4().hex}"
        payload = {"name": "Live Root", "count": 3}
        self._root_cleanup(key)
        try:
            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
            ) as session:
                root = PersistentRoot(session)
                root[key] = payload

            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.ABORT_ON_EXIT,
            ) as session:
                root = PersistentRoot(session)
                self.assertIn(key, root)
                stored = root[key]
                self.assertEqual(stored["name"], payload["name"])
                self.assertEqual(stored["count"], payload["count"])
        finally:
            self._root_cleanup(key)

    def test_persistent_root_and_gsdict_items_values_round_trip(self):
        dict_key = f"LivePersistentRootDict_{uuid.uuid4().hex}"
        scalar_key = f"LivePersistentRootScalar_{uuid.uuid4().hex}"
        payload = {
            "name": f"Live Root {uuid.uuid4().hex}",
            "count": 7,
            "enabled": True,
        }
        scalar_value = f"scalar-{uuid.uuid4().hex}"
        self._root_cleanup(dict_key, scalar_key)
        try:
            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
            ) as session:
                root = PersistentRoot(session)
                root[dict_key] = payload
                root[scalar_key] = scalar_value

            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.ABORT_ON_EXIT,
            ) as session:
                root = PersistentRoot(session)
                items = {
                    key: value
                    for key, value in root.items()
                    if key in {dict_key, scalar_key}
                }
                self.assertEqual(items[scalar_key], scalar_value)
                self.assertEqual(dict(items[dict_key].items()), payload)
                self.assertCountEqual(items[dict_key].values(), list(payload.values()))

                root_values = root.values()
                self.assertIn(scalar_value, root_values)
        finally:
            self._root_cleanup(dict_key, scalar_key)

    def test_gstore_round_trip(self):
        filename = f"live-gstore-{uuid.uuid4().hex}.db"
        store = GStore(filename, config=self.config)
        try:
            with store.transaction() as txn:
                txn["alpha"] = {"name": "Tariq", "count": 2}
                txn["beta"] = ["a", "b"]

            with store.transaction(read_only=True) as txn:
                self.assertEqual(txn["alpha"]["name"], "Tariq")
                self.assertEqual(txn["alpha"]["count"], 2)
                self.assertEqual(txn["beta"], ["a", "b"])
        finally:
            GStore.rm(filename, config=self.config)

    def test_gscollection_indexed_search(self):
        name = f"LiveGSCollection_{uuid.uuid4().hex}"
        col = GSCollection(name, config=self.config)
        try:
            col.insert({"@name": "Alice", "@age": 30})
            col.insert({"@name": "Bob", "@age": 24})
            col.add_index("@age")

            results = col.search("@age", "lt", 25)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["@name"], "Bob")
            self.assertEqual(results[0]["@age"], 24)
        finally:
            GSCollection.drop(name, config=self.config)

    def test_rchash_round_trip_uses_items_fetch(self):
        key = f"LiveRCHash_{uuid.uuid4().hex}"
        self._root_cleanup(key)
        try:
            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
            ) as session:
                root = PersistentRoot(session)
                root[key] = RCHash(session)
                cache = root[key]
                cache["alpha"] = 1
                cache["enabled"] = True
                cache["missing"] = None

            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.ABORT_ON_EXIT,
            ) as session:
                root = PersistentRoot(session)
                cache = root[key]
                self.assertEqual(
                    dict(cache.items()),
                    {"alpha": 1, "enabled": True, "missing": None},
                )
        finally:
            self._root_cleanup(key)

    def test_rchash_round_trip_uses_batched_non_scalar_fallback(self):
        key = f"LiveRCHashNonScalar_{uuid.uuid4().hex}"
        self._root_cleanup(key)
        try:
            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
            ) as session:
                root = PersistentRoot(session)
                root[key] = RCHash(session)
                cache = root[key]
                counter = RCCounter(session)
                cache["counter"] = counter
                cache["label"] = "alpha"
                counter.increment_by(3)

            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.ABORT_ON_EXIT,
            ) as session:
                root = PersistentRoot(session)
                cache = root[key]
                items = dict(cache.items())
                self.assertEqual(items["label"], "alpha")
                self.assertEqual(items["counter"].send("value"), 3)
        finally:
            self._root_cleanup(key)

    def test_ordered_collection_clear_round_trip(self):
        key = f"LiveOrderedCollection_{uuid.uuid4().hex}"
        self._root_cleanup(key)
        try:
            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
            ) as session:
                root = PersistentRoot(session)
                root[key] = OrderedCollection(session)
                col = root[key]
                col.append("alpha")
                col.append("beta")
                self.assertEqual(list(col), ["alpha", "beta"])
                col.clear()
                self.assertEqual(list(col), [])

            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.ABORT_ON_EXIT,
            ) as session:
                root = PersistentRoot(session)
                col = root[key]
                self.assertEqual(len(col), 0)
        finally:
            self._root_cleanup(key)

    def test_objectlog_read_snapshot(self):
        log = ObjectLog(config=self.config)
        entries = log.entries()
        if not entries:
            self.skipTest("ObjectLog is empty on this stone")

        warns = log.warns()
        errors = log.errors()
        infos = log.infos()
        size_before = log.size()

        self.assertEqual(size_before, len(entries))
        self.assertIsInstance(warns, list)
        self.assertIsInstance(errors, list)
        self.assertIsInstance(infos, list)

    def test_objectlog_add_with_object_oop(self):
        key = f"LiveObjectLog_{uuid.uuid4().hex}"
        root_key = f"LiveObjectLogObj_{uuid.uuid4().hex}"
        log = ObjectLog(config=self.config)
        self._root_cleanup(root_key)
        created_entry = None
        try:
            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
            ) as session:
                root = PersistentRoot(session)
                root[root_key] = {"name": "attached"}
                attached = root[root_key]
                log.info(key, object_oop=attached.oop, session=session)

            matches = [entry for entry in log.entries() if entry.label == key]
            self.assertTrue(matches)
            created_entry = matches[-1]
            self.assertNotEqual(created_entry.object_repr, "nil")
            self.assertNotEqual(created_entry.object_repr, "")
        finally:
            if created_entry is not None:
                log.delete(created_entry)
            self._root_cleanup(root_key)

    @unittest.skipUnless(
        RUN_DESTRUCTIVE_LIVE,
        "set GS_RUN_DESTRUCTIVE_LIVE=1 to run destructive live ObjectLog tests",
    )
    def test_objectlog_delete_and_clear(self):
        log = ObjectLog(config=self.config)
        entries = log.entries()
        if not entries:
            self.skipTest("ObjectLog is empty on this stone")

        size_before = log.size()

        log.delete(entries[-1])
        self.assertEqual(log.size(), size_before - 1)

        log.clear()
        self.assertEqual(log.size(), 0)
        self.assertEqual(log.entries(), [])

    def test_session_pool_warm_recycle_and_close(self):
        provider = GemStoneSessionPool(
            maxsize=2,
            config=self.config,
            max_session_uses=1,
            acquire_timeout=0.1,
        )
        try:
            warmed = provider.warm(1)
            self.assertEqual(warmed, 1)
            warm_snapshot = provider.snapshot()
            self.assertEqual(warm_snapshot.warmup_calls, 1)
            self.assertEqual(warm_snapshot.warmed_sessions, 1)
            self.assertEqual(warm_snapshot.available, 1)

            session = provider.acquire()
            provider.release(session, clean=False)

            recycle_snapshot = provider.snapshot()
            self.assertGreaterEqual(recycle_snapshot.recycle_use_discards, 1)
            self.assertGreaterEqual(recycle_snapshot.discard_calls, 1)

            session2 = provider.acquire()
            second_identity = id(session2)
            provider.release(session2, clean=False)

            self.assertNotEqual(id(session), second_identity)
        finally:
            provider.close()

        closed_snapshot = provider.snapshot()
        self.assertTrue(closed_snapshot.closed)
        self.assertGreaterEqual(closed_snapshot.close_calls, 1)

    def test_session_pool_timeout_and_closed_provider_failures(self):
        provider = GemStoneSessionPool(
            maxsize=1,
            config=self.config,
            acquire_timeout=0.01,
        )
        session = provider.acquire()
        try:
            with self.assertRaises(TimeoutError):
                provider.acquire()

            timeout_snapshot = provider.snapshot()
            self.assertGreaterEqual(timeout_snapshot.timeout_calls, 1)
        finally:
            provider.release(session, clean=True)
            provider.close()

        closed_snapshot = provider.snapshot()
        self.assertTrue(closed_snapshot.closed)
        self.assertGreaterEqual(closed_snapshot.close_calls, 1)
        with self.assertRaises(RuntimeError):
            provider.acquire()

    def test_thread_local_provider_recycles_and_closes(self):
        provider = GemStoneThreadLocalSessionProvider(
            config=self.config,
            max_session_uses=1,
        )
        thread_results: list[tuple[int, int]] = []
        thread_errors: list[BaseException] = []

        def worker() -> None:
            try:
                session = provider.acquire()
                thread_results.append((threading.get_ident(), id(session)))
                provider.release(session, clean=True)
            except BaseException as exc:  # pragma: no cover - live thread failure path
                thread_errors.append(exc)

        try:
            first = provider.acquire()
            first_identity = id(first)
            provider.release(first, clean=True)

            worker_thread = threading.Thread(target=worker)
            worker_thread.start()
            worker_thread.join()

            second = provider.acquire()
            second_identity = id(second)
            provider.release(second, clean=True)

            self.assertEqual(thread_errors, [])
            self.assertEqual(len(thread_results), 1)
            self.assertNotEqual(thread_results[0][1], first_identity)
            self.assertNotEqual(second_identity, first_identity)
            snapshot = provider.snapshot()
            self.assertGreaterEqual(snapshot.recycle_use_discards, 1)
        finally:
            provider.close()

        closed_snapshot = provider.snapshot()
        self.assertTrue(closed_snapshot.closed)
        with self.assertRaises(RuntimeError):
            provider.acquire()

    def test_concurrency_helpers_cross_session(self):
        key = f"LiveConcurrency_{uuid.uuid4().hex}"
        counter_index = 1
        self._root_cleanup(key)
        try:
            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
            ) as writer:
                root = PersistentRoot(writer)
                root[key] = RCCounter(writer)
                obj = root[key]
                obj.increment()
                writer.commit()
                self.assertGreaterEqual(shared_counter_count(writer), counter_index)
                shared_counter_set(writer, counter_index, 0)
                shared_counter_increment(writer, counter_index, by=2)
                self.assertEqual(shared_counter_get(writer, counter_index), 2)
                instance_ids = list_instances(writer, "RcCounter", wrap=False)
                self.assertIn(obj.oop, instance_ids)

                with lock(writer, obj):
                    with GemStoneSession(
                        config=self.config,
                        transaction_policy=TransactionPolicy.ABORT_ON_EXIT,
                    ) as reader:
                        reader_root = PersistentRoot(reader)
                        self.assertEqual(reader_root[key].value, 1)
                        self.assertGreaterEqual(session_count(reader), 2)
                        self.assertNotEqual(session_id(writer), session_id(reader))
                        self.assertEqual(shared_counter_get(reader, counter_index), 2)
        finally:
            self._root_cleanup(key)

    def test_nested_transaction_aborts_inner_scope_on_exception(self):
        key = f"LiveNestedAbort_{uuid.uuid4().hex}"
        self._root_cleanup(key)
        try:
            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
            ) as setup:
                root = PersistentRoot(setup)
                root[key] = {"state": "outer"}

            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
            ) as session:
                root = PersistentRoot(session)
                with self.assertRaises(RuntimeError):
                    with nested_transaction(session):
                        root[key]["state"] = "inner"
                        raise RuntimeError("boom")
                self.assertEqual(root[key]["state"], "outer")

            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.ABORT_ON_EXIT,
            ) as verify:
                root = PersistentRoot(verify)
                self.assertEqual(root[key]["state"], "outer")
        finally:
            self._root_cleanup(key)

    @unittest.skipUnless(HAS_FLASK, "Flask is not installed in python3")
    def test_flask_request_session_commits_and_aborts(self):
        from flask import Flask

        commit_key = f"LiveFlaskCommit_{uuid.uuid4().hex}"
        abort_key = f"LiveFlaskAbort_{uuid.uuid4().hex}"
        self._root_cleanup(commit_key, abort_key)

        app = Flask(__name__)
        app.config["PROPAGATE_EXCEPTIONS"] = False
        app.secret_key = "gemstone-live-test"
        events = []
        install_flask_request_session(
            app,
            config=self.config,
            pool_size=1,
            warmup_sessions=1,
            close_on_after_serving=True,
            event_listener=lambda event: events.append(event.name),
        )

        @app.get("/commit")
        def commit_route():
            with session_scope() as session:
                root = PersistentRoot(session)
                root[commit_key] = {"state": "committed"}
            return "ok"

        @app.get("/abort")
        def abort_route():
            with session_scope() as session:
                root = PersistentRoot(session)
                root[abort_key] = {"state": "aborted"}
            raise RuntimeError("boom")

        try:
            warmed = warm_flask_request_session_provider(app, 1)
            self.assertEqual(warmed, 1)
            client = app.test_client()

            commit_response = client.get("/commit")
            self.assertEqual(commit_response.status_code, 200)

            abort_response = client.get("/abort")
            self.assertEqual(abort_response.status_code, 500)

            snapshot = flask_request_session_provider_snapshot(app)
            self.assertIsNotNone(snapshot)
            self.assertGreaterEqual(snapshot.acquire_calls, 2)
            self.assertGreaterEqual(snapshot.release_calls, 2)
            self.assertGreaterEqual(snapshot.created, 1)
            self.assertGreaterEqual(snapshot.warmup_calls, 1)
            self.assertGreaterEqual(snapshot.warmed_sessions, 1)

            metrics = flask_request_session_provider_metrics(app)
            self.assertIsNotNone(metrics)
            self.assertGreaterEqual(metrics["acquire_calls"], 2)
            self.assertIn("session_warmed", events)
            self.assertIn("session_acquired", events)
            self.assertIn("session_released", events)

            with GemStoneSession(
                config=self.config,
                transaction_policy=TransactionPolicy.ABORT_ON_EXIT,
            ) as session:
                root = PersistentRoot(session)
                self.assertIn(commit_key, root)
                self.assertEqual(root[commit_key]["state"], "committed")
                self.assertNotIn(abort_key, root)
        finally:
            close_flask_request_session_provider(app)
            self._root_cleanup(commit_key, abort_key)


if __name__ == "__main__":
    unittest.main()
