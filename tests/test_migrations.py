import unittest
from unittest import mock

from gemstone_py.migrations import Migration


class _DemoMigration(Migration):
    def up(self, session):
        return None


class MigrationChunkingTests(unittest.TestCase):
    def test_each_in_chunks_uses_raw_oops_by_default(self):
        migration = _DemoMigration()
        session = mock.Mock()
        seen = []

        with mock.patch(
            "gemstone_py.concurrency.list_instances",
            return_value=[101, 102, 103],
        ) as list_instances:
            with mock.patch.object(Migration, "_commit_with_retry", autospec=True) as commit:
                total = migration.each_in_chunks(
                    session,
                    "RcCounter",
                    lambda current_session, item: seen.append((current_session, item)),
                    chunk_size=2,
                )

        self.assertEqual(total, 3)
        self.assertEqual(seen, [(session, 101), (session, 102), (session, 103)])
        list_instances.assert_called_once_with(session, "RcCounter", wrap=False)
        self.assertEqual(commit.call_args_list, [
            mock.call(migration, session),
            mock.call(migration, session),
        ])

    def test_each_in_chunks_can_yield_wrapped_instances(self):
        migration = _DemoMigration()
        session = mock.Mock()
        wrapped = [mock.Mock(oop=201), mock.Mock(oop=202)]
        seen = []

        with mock.patch(
            "gemstone_py.concurrency.list_instances",
            return_value=wrapped,
        ) as list_instances:
            with mock.patch.object(Migration, "_commit_with_retry", autospec=True) as commit:
                total = migration.each_in_chunks(
                    session,
                    "RcCounter",
                    lambda current_session, item: seen.append((current_session, item)),
                    chunk_size=10,
                    wrap=True,
                )

        self.assertEqual(total, 2)
        self.assertEqual(seen, [(session, wrapped[0]), (session, wrapped[1])])
        list_instances.assert_called_once_with(session, "RcCounter", wrap=True)
        commit.assert_called_once_with(migration, session)


if __name__ == "__main__":
    unittest.main()
