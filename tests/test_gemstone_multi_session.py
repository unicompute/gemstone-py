import unittest
from unittest import mock

import gemstone_py as gemstone


class GemStoneMultiSessionTests(unittest.TestCase):
    def test_resolve_activates_saved_session_before_gci_call(self):
        session = gemstone.GemStoneSession()
        lib = mock.Mock()
        lib.GciResolveSymbol.return_value = 123
        session._lib = lib
        session._logged_in = True
        session._session_id = 17

        resolved = session.resolve("UserGlobals")

        self.assertEqual(resolved, 123)
        self.assertEqual(
            lib.mock_calls[:2],
            [
                mock.call.GciSetSessionId(17),
                mock.call.GciResolveSymbol(b"UserGlobals", mock.ANY),
            ],
        )

    def test_logout_activates_saved_session_before_logout(self):
        session = gemstone.GemStoneSession()
        lib = mock.Mock()
        session._lib = lib
        session._logged_in = True
        session._session_id = 23

        session.logout()

        self.assertEqual(
            lib.mock_calls,
            [
                mock.call.GciSetSessionId(23),
                mock.call.GciLogout(),
            ],
        )
        self.assertFalse(session._logged_in)
        self.assertEqual(session._session_id, gemstone.GCI_INVALID_SESSION)


if __name__ == "__main__":
    unittest.main()
