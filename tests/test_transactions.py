import unittest
from unittest import mock

import gemstone_py as gemstone
from gemstone_py.concurrency import CommitConflictError
from gemstone_py.transactions import retrying_transaction, run_transaction_with_retry


class FakeSession:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls: list[str] = []

    def __enter__(self):
        self.calls.append("enter")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.calls.append("exit")
        return False

    def abort(self):
        self.calls.append("abort")


class TransactionRetryTests(unittest.TestCase):
    def test_existing_session_replays_work_after_commit_conflict(self):
        session = mock.Mock()
        conflict = CommitConflictError("conflict", [], [])
        attempts: list[int] = []
        seen_conflicts = []

        def work(current_session):
            self.assertIs(current_session, session)
            attempts.append(len(attempts) + 1)
            return "done"

        with mock.patch("gemstone_py.transactions._commit", side_effect=[conflict, None]):
            result = run_transaction_with_retry(
                work,
                session=session,
                attempts=2,
                on_conflict=seen_conflicts.append,
            )

        self.assertEqual(result, "done")
        self.assertEqual(attempts, [1, 2])
        session.abort.assert_called_once_with()
        self.assertEqual(seen_conflicts[0].attempt, 1)
        self.assertEqual(seen_conflicts[0].attempts, 2)
        self.assertIs(seen_conflicts[0].conflict, conflict)

    def test_existing_session_raises_last_conflict_after_exhaustion(self):
        session = mock.Mock()
        conflict = CommitConflictError("conflict", [], [])

        with mock.patch("gemstone_py.transactions._commit", side_effect=[conflict, conflict]):
            with self.assertRaises(CommitConflictError):
                run_transaction_with_retry(lambda _session: None, session=session, attempts=2)

        self.assertEqual(session.abort.call_count, 2)

    def test_existing_session_aborts_on_user_error(self):
        session = mock.Mock()

        with self.assertRaisesRegex(RuntimeError, "boom"):
            run_transaction_with_retry(
                lambda _session: (_ for _ in ()).throw(RuntimeError("boom")),
                session=session,
            )

        session.abort.assert_called_once_with()

    def test_owned_sessions_are_manual_and_recreated_per_attempt(self):
        created: list[FakeSession] = []
        conflict = CommitConflictError("conflict", [], [])

        def factory(**kwargs):
            session = FakeSession(**kwargs)
            created.append(session)
            return session

        with mock.patch("gemstone_py.transactions._commit", side_effect=[conflict, None]):
            result = retrying_transaction(
                lambda session: session.kwargs["stone"],
                attempts=2,
                session_factory=factory,
                stone="demo",
            )

        self.assertEqual(result, "demo")
        self.assertEqual(len(created), 2)
        self.assertIs(created[0].kwargs["transaction_policy"], gemstone.TransactionPolicy.MANUAL)
        self.assertEqual(created[0].calls, ["enter", "abort", "exit"])
        self.assertEqual(created[1].calls, ["enter", "exit"])

    def test_attempts_must_be_positive(self):
        with self.assertRaises(ValueError):
            run_transaction_with_retry(lambda _session: None, attempts=0)

    def test_rejects_existing_session_with_creation_options(self):
        with self.assertRaises(ValueError):
            run_transaction_with_retry(lambda _session: None, session=mock.Mock(), stone="demo")


if __name__ == "__main__":
    unittest.main()
