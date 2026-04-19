import unittest
from contextlib import contextmanager
from unittest import mock

from tests._support import load_module


def _load_magtag_models_module():
    return load_module(
        "magtag_models_batching",
        "examples",
        "flask",
        "magtag",
        "models.py",
    )


class MagTagSessionBatchingTests(unittest.TestCase):
    def test_rewrite_records_reuses_one_scoped_session(self):
        mod = _load_magtag_models_module()
        marker = object()
        fake_col = mock.Mock()

        @contextmanager
        def fake_scope(session=None, **_kwargs):
            self.assertIsNone(session)
            yield marker

        with mock.patch.object(mod.gemstone, "session_scope", fake_scope):
            with mock.patch.object(mod.User, "_col", return_value=fake_col) as col:
                records = [{"@id": "1", "@name": "alice"}]
                mod.User._rewrite_records(records)

        col.assert_called_once_with(session=marker)
        fake_col.replace_all.assert_called_once_with(records, session=marker)
        self.assertEqual(
            fake_col.add_index_for_class.call_args_list,
            [
                mock.call("@name", "String", session=marker),
                mock.call("@id", "String", session=marker),
            ],
        )

    def test_signup_uses_one_scoped_session_for_lookup_and_save(self):
        mod = _load_magtag_models_module()
        marker = object()

        @contextmanager
        def fake_scope(session=None, **_kwargs):
            self.assertIsNone(session)
            yield marker

        def fake_save(self, session=None):
            self._saved_session = session
            return self

        with mock.patch.object(mod.gemstone, "session_scope", fake_scope):
            with mock.patch.object(mod.User, "find_by_name", return_value=None) as find:
                with mock.patch.object(mod.User, "save", autospec=True, side_effect=fake_save):
                    user = mod.User.signup("alice", "secret")

        find.assert_called_once_with("alice", session=marker)
        self.assertEqual(user.name, "alice")
        self.assertIs(user._saved_session, marker)

    def test_tweet_reuses_one_scoped_session_for_follower_updates(self):
        mod = _load_magtag_models_module()
        marker = object()
        user = mod.User("alice", "secret")
        user._followers = ["bob"]
        follower = mod.User("bob", "secret")
        fake_col = mock.Mock()

        @contextmanager
        def fake_scope(session=None, **_kwargs):
            self.assertIsNone(session)
            yield marker

        with mock.patch.object(mod.gemstone, "session_scope", fake_scope):
            with mock.patch.object(mod.User, "find_by_name", return_value=follower) as find:
                with mock.patch.object(mod.User, "_col", return_value=fake_col) as col:
                    tweet = user.tweet("hello")

        find.assert_called_once_with("bob", session=marker)
        col.assert_called_once_with(session=marker)
        self.assertEqual(tweet.author, "alice")
        self.assertEqual(follower.timeline[0].text, "hello")
        fake_col.bulk_upsert_unique.assert_called_once()
        args = fake_col.bulk_upsert_unique.call_args
        self.assertEqual(args.args[0], "@id")
        self.assertEqual(len(args.args[1]), 2)
        self.assertEqual(args.kwargs, {"session": marker})

    def test_follow_uses_one_bulk_upsert_for_both_users(self):
        mod = _load_magtag_models_module()
        marker = object()
        alice = mod.User("alice", "secret")
        bob = mod.User("bob", "secret")
        fake_col = mock.Mock()

        @contextmanager
        def fake_scope(session=None, **_kwargs):
            self.assertIsNone(session)
            yield marker

        with mock.patch.object(mod.gemstone, "session_scope", fake_scope):
            with mock.patch.object(mod.User, "_col", return_value=fake_col) as col:
                alice.follow(bob)

        col.assert_called_once_with(session=marker)
        fake_col.bulk_upsert_unique.assert_called_once()
        args = fake_col.bulk_upsert_unique.call_args
        self.assertEqual(args.args[0], "@id")
        self.assertEqual(len(args.args[1]), 2)
        self.assertEqual(args.kwargs, {"session": marker})


if __name__ == "__main__":
    unittest.main()
