import ctypes
import unittest
from typing import Any
from unittest import mock

import gemstone_py as gemstone


def _populate_error(
    err_ptr: Any,
    *,
    number: int,
    message: str,
    reason: str | None = None,
    fatal: bool = False,
    exception_oop: int = 0,
    category: int = 0,
    arg_oops: tuple[int, ...] = (),
) -> None:
    err = ctypes.cast(err_ptr, ctypes.POINTER(gemstone.GciErrSType)).contents
    err.number = number
    err.fatal = int(fatal)
    err.message = message.encode("utf-8")
    err.reason = (reason or message).encode("utf-8")
    err.exceptionObj = exception_oop
    err.category = category
    err.argCount = len(arg_oops)
    for i, oop in enumerate(arg_oops):
        err.args[i] = oop


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

    def test_check_result_is_noop_when_result_is_nil_without_gci_error(self) -> None:
        session = gemstone.GemStoneSession(username="alice", password="secret")
        lib = mock.Mock()
        session._lib = lib

        # OOP_NIL with no GciErr error is a legitimate nil result, not a failure.
        session._check_result(gemstone.OOP_NIL)

        lib.GciErr.assert_called_once_with(mock.ANY)

    def test_check_result_raises_structured_error_when_gci_err_is_present(self) -> None:
        session = gemstone.GemStoneSession(username="alice", password="secret")
        lib = mock.Mock()
        session._lib = lib

        def fill_error(err_ptr: object) -> None:
            _populate_error(
                err_ptr,
                number=19,
                message="Fetch failed",
                reason="Repository error",
                fatal=True,
            )

        lib.GciErr.side_effect = fill_error

        with self.assertRaises(gemstone.GemStoneError) as ctx:
            session._check_result(gemstone.OOP_NIL)

        self.assertIn("Fetch failed", str(ctx.exception))
        self.assertEqual(ctx.exception.number, 19)
        self.assertTrue(ctx.exception.fatal)

    def test_check_result_carries_exception_data_and_exposes_proxy(self) -> None:
        from gemstone_py.persistent_root import GsObject

        session, lib = self._logged_in_session()

        def fill_error(err_ptr: object) -> None:
            _populate_error(
                err_ptr,
                number=2026,
                message="divide by zero",
                exception_oop=0x12345,
                category=7,
                arg_oops=(0xAA, 0xBB),
            )

        lib.GciErr.side_effect = fill_error

        with self.assertRaises(gemstone.GemStoneError) as ctx:
            session._check_result(gemstone.OOP_NIL)

        err = ctx.exception
        self.assertEqual(err.exception_oop, 0x12345)
        self.assertEqual(err.category, 7)
        self.assertEqual(err.arg_oops, (0xAA, 0xBB))

        proxy = err.exception
        self.assertIsInstance(proxy, GsObject)
        self.assertEqual(proxy.oop, 0x12345)

    def test_exception_is_none_without_session(self) -> None:
        err = gemstone.GemStoneError("boom", number=1, exception_oop=0x99)
        self.assertIsNone(err.exception)

    def test_exception_is_none_without_exception_oop(self) -> None:
        session, _ = self._logged_in_session()
        err = gemstone.GemStoneError("boom", number=1, session=session)
        self.assertIsNone(err.exception)

    def test_activate_session_raises_when_session_id_is_invalid(self) -> None:
        session = gemstone.GemStoneSession(username="alice", password="secret")
        session._lib = mock.Mock()
        session._logged_in = True
        session._session_id = gemstone.GCI_INVALID_SESSION

        with self.assertRaises(gemstone.GemStoneError) as ctx:
            session._activate_session()

        self.assertIn("Not logged in", str(ctx.exception))

    def test_activate_session_rejects_cross_thread_use(self) -> None:
        session, lib = self._logged_in_session()
        session._owner_thread_id = 999999

        with self.assertRaises(gemstone.GemStoneError) as ctx:
            session._activate_session()

        self.assertIn("bound to a different Python thread", str(ctx.exception))
        lib.GciSetSessionId.assert_not_called()

    def test_thread_ownership_can_be_released_and_reclaimed(self) -> None:
        session, lib = self._logged_in_session()
        session._owner_thread_id = None

        session._activate_session()
        first_owner = session.owner_thread_id
        session._release_thread_ownership()
        session._activate_session()

        self.assertIsNotNone(first_owner)
        self.assertEqual(session.owner_thread_id, first_owner)
        self.assertEqual(lib.GciSetSessionId.call_count, 2)

    def test_resolve_raises_when_symbol_cannot_be_resolved(self) -> None:
        session, lib = self._logged_in_session()
        lib.GciResolveSymbol.return_value = gemstone.OOP_ILLEGAL

        with self.assertRaises(gemstone.GemStoneError) as ctx:
            session.resolve("MissingGlobal")

        self.assertIn("Cannot resolve global", str(ctx.exception))

    def test_fetch_string_returns_empty_for_non_positive_size(self) -> None:
        session, lib = self._logged_in_session()
        lib.GciFetchSize_.return_value = 0

        self.assertEqual(session.fetch_string(123), "")
        lib.GciFetchBytes_.assert_not_called()

    def test_fetch_string_decodes_fetched_bytes(self) -> None:
        session, lib = self._logged_in_session()
        lib.GciFetchSize_.return_value = 5

        def fetch_bytes(_oop: object, _start: object, buf: Any, _size: object) -> int:
            buf.value = b"hello"
            return 5

        lib.GciFetchBytes_.side_effect = fetch_bytes

        self.assertEqual(session.fetch_string(123), "hello")

    def test_logout_is_noop_when_not_logged_in(self) -> None:
        session = gemstone.GemStoneSession(username="alice", password="secret")
        lib = mock.Mock()
        session._lib = lib
        session._logged_in = False

        session.logout()

        lib.GciLogout.assert_not_called()


if __name__ == "__main__":
    unittest.main()
