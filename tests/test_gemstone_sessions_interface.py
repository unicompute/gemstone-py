import importlib.util
import unittest

from tests._support import load_module

HAS_FLASK = importlib.util.find_spec("flask") is not None


def _load_gemstone_sessions_module():
    return load_module(
        "gemstone_sessions_test",
        "examples",
        "flask",
        "sessions",
        "gemstone_sessions.py",
    )


@unittest.skipUnless(HAS_FLASK, "Flask is not installed in python3")
class GemStoneSessionInterfaceTests(unittest.TestCase):
    def test_store_can_skip_creation_for_read_only_paths(self):
        mod = _load_gemstone_sessions_module()
        interface = mod.GemStoneSessionInterface()
        root = {}

        store = interface._store(root, create=False)

        self.assertIsNone(store)
        self.assertEqual(root, {})

    def test_store_creates_backing_dictionary_when_requested(self):
        mod = _load_gemstone_sessions_module()
        interface = mod.GemStoneSessionInterface()
        root = {}

        store = interface._store(root, create=True)

        self.assertEqual(store, {})
        self.assertEqual(root, {mod.GS_SESSIONS_KEY: {}})


if __name__ == "__main__":
    unittest.main()
