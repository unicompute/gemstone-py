import unittest

from gemstone_py.concurrency import session_count, session_id


class _FakeSession:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def eval(self, source):
        self.calls.append(source)
        return self.values[source]


class SessionUtilityTests(unittest.TestCase):
    def test_session_utilities_use_gemstone_selectors(self):
        session = _FakeSession(
            {
                "System session": 11,
                "System currentSessionCount": 7,
            }
        )

        self.assertEqual(session_id(session), 11)
        self.assertEqual(session_count(session), 7)
        self.assertEqual(
            session.calls,
            [
                "System session",
                "System currentSessionCount",
            ],
        )


if __name__ == "__main__":
    unittest.main()
