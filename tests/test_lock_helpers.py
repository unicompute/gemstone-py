import unittest

from gemstone_py.concurrency import lock, read_lock, unlock


class _FakeSession:
    def __init__(self):
        self.calls = []

    def eval(self, source):
        self.calls.append(source)
        return True


class _FakeProxy:
    def __init__(self, oop):
        self.oop = oop


class LockHelpersTests(unittest.TestCase):
    def test_lock_accepts_proxy_with_oop(self):
        session = _FakeSession()
        obj = _FakeProxy(123)

        with lock(session, obj):
            session.calls.append("inside")

        self.assertEqual(
            session.calls,
            [
                "System writeLock: (ObjectMemory objectForOop: 123)",
                "inside",
                "System removeLock: (ObjectMemory objectForOop: 123)",
            ],
        )

    def test_read_lock_accepts_raw_oop(self):
        session = _FakeSession()

        with read_lock(session, 456):
            session.calls.append("inside")

        self.assertEqual(
            session.calls,
            [
                "System readLock: (ObjectMemory objectForOop: 456)",
                "inside",
                "System removeLock: (ObjectMemory objectForOop: 456)",
            ],
        )

    def test_unlock_accepts_proxy_with_oop(self):
        session = _FakeSession()
        obj = _FakeProxy(789)

        unlock(session, obj)

        self.assertEqual(
            session.calls,
            ["System removeLock: (ObjectMemory objectForOop: 789)"],
        )

    def test_lock_rejects_non_proxy_non_oop_values(self):
        session = _FakeSession()

        with self.assertRaises(TypeError):
            with lock(session, object()):
                pass


if __name__ == "__main__":
    unittest.main()
