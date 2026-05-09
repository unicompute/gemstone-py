import threading
import unittest
from typing import Protocol
from unittest import mock

import gemstone_py as gemstone


@gemstone.gemstone_class("OkzBooking")
class OkzBooking(Protocol):
    status: str


class TypedOopTests(unittest.TestCase):
    def test_execute_typed_returns_phantom_typed_oop(self):
        session = gemstone.GemStoneSession(username="alice", password="secret")

        with mock.patch.object(session, "eval_oop", return_value=0xABC):
            result = session.execute_typed("OkzBooking findById: 'x'", OkzBooking)

        self.assertIsInstance(result, gemstone.TypedOop)
        self.assertEqual(int(result), 0xABC)
        self.assertIs(result.wrapper_type, OkzBooking)
        self.assertEqual(result.gemstone_class_name, "OkzBooking")

    def test_typed_oop_proxy_sends_attribute_name_as_selector(self):
        session = gemstone.GemStoneSession(username="alice", password="secret")
        result = gemstone.TypedOop(0xABC, session, OkzBooking)

        with mock.patch.object(session, "perform_value", return_value="booked") as perform:
            status = result.proxy().status

        self.assertEqual(status, "booked")
        perform.assert_called_once_with(0xABC, "status")

    def test_gemstone_class_registry_records_wrappers(self):
        self.assertEqual(gemstone.gemstone_class_name(OkzBooking), "OkzBooking")
        self.assertIs(gemstone.registered_gemstone_classes()["OkzBooking"], OkzBooking)


class ManagedOopTests(unittest.TestCase):
    def _logged_in_session(self):
        session = gemstone.GemStoneSession(username="alice", password="secret")
        lib = mock.Mock()
        session._lib = lib
        session._logged_in = True
        session._session_id = 41
        return session, lib

    def test_managed_oop_reference_counts_export_set_entries(self):
        session, lib = self._logged_in_session()

        first = session.managed_oop(0xCAFE)
        second = session.managed_oop(0xCAFE)

        self.assertEqual(session._managed_oop_counts[0xCAFE], 2)
        lib.GciAddOopToExportSet.assert_called_once()

        first.close()
        self.assertEqual(session._managed_oop_counts[0xCAFE], 1)
        lib.GciRemoveOopFromExportSet.assert_not_called()

        second.close()
        self.assertNotIn(0xCAFE, session._managed_oop_counts)
        lib.GciRemoveOopFromExportSet.assert_called_once()

    def test_managed_oop_finalizer_queues_export_removal_from_non_owner_thread(self):
        session, lib = self._logged_in_session()
        session._owner_thread_id = threading.get_ident()
        lib.GciNeedsCommit.return_value = False

        managed = session.managed_oop(0xCAFE)

        worker = threading.Thread(target=managed.close)
        worker.start()
        worker.join()

        self.assertNotIn(0xCAFE, session._managed_oop_counts)
        self.assertEqual(session._managed_oop_pending_removals[0xCAFE], 1)
        lib.GciRemoveOopFromExportSet.assert_not_called()

        self.assertFalse(session.needs_commit())

        self.assertFalse(session._managed_oop_pending_removals)
        lib.GciRemoveOopFromExportSet.assert_called_once()

    def test_logout_drains_queued_managed_oop_removals_before_closing_session(self):
        session, lib = self._logged_in_session()
        session._owner_thread_id = threading.get_ident()

        managed = session.managed_oop(0xBEEF)

        worker = threading.Thread(target=managed.close)
        worker.start()
        worker.join()

        session.logout()

        self.assertFalse(session._managed_oop_counts)
        self.assertFalse(session._managed_oop_pending_removals)
        self.assertEqual([call[0] for call in lib.method_calls[-2:]], [
            "GciRemoveOopFromExportSet",
            "GciLogout",
        ])

    def test_execute_and_perform_keep_raw_oop_compatibility(self):
        session, lib = self._logged_in_session()
        lib.GciExecuteStr.return_value = 0xCAFE
        lib.GciPerform.return_value = 0xBEEF

        executed = session.execute("Object new")
        performed = session.perform(0xCAFE, "yourself")
        managed = session.execute_managed("Object new")

        self.assertEqual(executed, 0xCAFE)
        self.assertEqual(performed, 0xBEEF)
        self.assertIsInstance(managed, gemstone.ManagedOop)
        self.assertEqual(managed.oop, 0xCAFE)
        self.assertEqual(session.execute_oop("Object new"), 0xCAFE)
        self.assertEqual(session._managed_oop_counts[0xCAFE], 1)
        self.assertNotIn(0xBEEF, session._managed_oop_counts)

        managed.close()

    def test_oop_handle_releases_on_context_exit(self):
        session, lib = self._logged_in_session()

        with session.handle(0xBEEF) as handle:
            self.assertEqual(int(handle), 0xBEEF)
            self.assertEqual(session._managed_oop_counts[0xBEEF], 1)

        self.assertNotIn(0xBEEF, session._managed_oop_counts)
        lib.GciAddOopToExportSet.assert_called_once()
        lib.GciRemoveOopFromExportSet.assert_called_once()


if __name__ == "__main__":
    unittest.main()
