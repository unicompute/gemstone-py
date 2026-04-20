import ctypes
import unittest
from unittest import mock

import gemstone_py as gemstone


def _populate_error(
    err_ptr: object,
    *,
    number: int,
    message: str,
    reason: str | None = None,
    fatal: bool = False,
) -> None:
    err = ctypes.cast(err_ptr, ctypes.POINTER(gemstone.GciErrSType)).contents
    err.number = number
    err.fatal = int(fatal)
    err.message = message.encode("utf-8")
    err.reason = (reason or message).encode("utf-8")


class GemStoneClientFailureTests(unittest.TestCase):
    def _logged_in_session(self) -> tuple[gemstone.GemStoneSession, mock.Mock]:
        session = gemstone.GemStoneSession(username="alice", password="secret")
        lib = mock.Mock()
        session._lib = lib
        session._logged_in = True
        session._session_id = 41
        return session, lib

    def test_login_raises_error_when_gci_login_fails(self) -> None:
        lib = mock.Mock()

        def fill_login_error(err_ptr: object) -> None:
            _populate_error(
                err_ptr,
                number=23,
                message="Login failed",
                reason="Bad credentials",
            )

        lib.GciLoginEx.return_value = 0
        lib.GciErr.side_effect = fill_login_error

        session = gemstone.GemStoneSession(username="alice", password="secret")
        with mock.patch("gemstone_py.client._load_library", return_value=lib):
            with mock.patch("gemstone_py.client._bind"):
                with self.assertRaises(gemstone.GemStoneError) as ctx:
                    session.login()

        self.assertIn("Login failed", str(ctx.exception))
        self.assertEqual(ctx.exception.number, 23)
        self.assertFalse(session._logged_in)

    def test_commit_raises_error_when_gci_commit_fails(self) -> None:
        session, lib = self._logged_in_session()

        def fail_commit(err_ptr: object) -> int:
            _populate_error(
                err_ptr,
                number=77,
                message="Commit failed",
                reason="Write conflict",
            )
            return 0

        lib.GciCommit.side_effect = fail_commit

        with self.assertRaises(gemstone.GemStoneError) as ctx:
            session.commit()

        self.assertIn("Commit failed", str(ctx.exception))
        self.assertEqual(ctx.exception.number, 77)
        self.assertEqual(
            lib.mock_calls[:2],
            [
                mock.call.GciSetSessionId(41),
                mock.call.GciCommit(mock.ANY),
            ],
        )

    def test_abort_falls_back_to_system_abort_transaction(self) -> None:
        session, lib = self._logged_in_session()
        lib.GciAbort.return_value = 0
        lib.GciExecuteStr.return_value = gemstone.OOP_TRUE

        session.abort()

        self.assertEqual(
            lib.mock_calls[:3],
            [
                mock.call.GciSetSessionId(41),
                mock.call.GciAbort(mock.ANY),
                mock.call.GciExecuteStr(b"System abortTransaction", mock.ANY),
            ],
        )

    def test_abort_raises_error_when_gci_abort_sets_error(self) -> None:
        session, lib = self._logged_in_session()

        def fail_abort(err_ptr: object) -> int:
            _populate_error(err_ptr, number=88, message="Abort failed")
            return 0

        lib.GciAbort.side_effect = fail_abort

        with self.assertRaises(gemstone.GemStoneError) as ctx:
            session.abort()

        self.assertIn("Abort failed", str(ctx.exception))
        self.assertEqual(ctx.exception.number, 88)
        lib.GciExecuteStr.assert_not_called()

    def test_check_result_raises_generic_error_when_gci_err_is_empty(self) -> None:
        session = gemstone.GemStoneSession(username="alice", password="secret")
        lib = mock.Mock()
        session._lib = lib

        with self.assertRaises(gemstone.GemStoneError) as ctx:
            session._check_result(gemstone.OOP_ILLEGAL)

        self.assertEqual(str(ctx.exception), "GCI call returned OOP_ILLEGAL")
        lib.GciErr.assert_called_once_with(mock.ANY)

    def test_activate_session_raises_when_session_id_is_invalid(self) -> None:
        session = gemstone.GemStoneSession(username="alice", password="secret")
        session._lib = mock.Mock()
        session._logged_in = True
        session._session_id = gemstone.GCI_INVALID_SESSION

        with self.assertRaises(gemstone.GemStoneError) as ctx:
            session._activate_session()

        self.assertIn("Not logged in", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
