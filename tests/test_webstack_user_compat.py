import importlib.util
import unittest
from unittest import mock

from tests._support import load_module

HAS_FLASK = importlib.util.find_spec("flask") is not None


def _load_webstack_user_module():
    return load_module("webstack_user_compat", "examples", "webstack", "lib", "user.py")


def _load_webstack_app_module():
    return load_module("webstack_magtag_app_test", "examples", "webstack", "magtag_app.py")


class WebstackUserCompatTests(unittest.TestCase):
    def test_num_properties_match_template_expectations(self):
        mod = _load_webstack_user_module()
        user = mod.User.__new__(mod.User)
        user._followers = ["a", "b"]
        user._following = ["c"]
        user._tweets = [object(), object(), object()]

        self.assertEqual(user.num_followers, 2)
        self.assertEqual(user.num_following, 1)
        self.assertEqual(user.num_tweets, 3)

    @unittest.skipUnless(HAS_FLASK, "Flask is not installed in python3")
    def test_root_without_session_skips_repository_lookup(self):
        mod = _load_webstack_app_module()

        with mock.patch.object(
            mod.User,
            "find_by_name",
            side_effect=AssertionError("unexpected repository lookup"),
        ):
            response = mod.app.test_client().get("/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/login"))

    @unittest.skipUnless(HAS_FLASK, "Flask is not installed in python3")
    def test_stale_session_is_cleared_on_open_page(self):
        mod = _load_webstack_app_module()
        client = mod.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["logged_in_user"] = "ghost"

        with mock.patch.object(mod.User, "find_by_name", return_value=None):
            response = client.get("/info")

        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as flask_session:
            self.assertNotIn("logged_in_user", flask_session)


if __name__ == "__main__":
    unittest.main()
