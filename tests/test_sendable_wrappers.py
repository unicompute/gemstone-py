import unittest
from unittest import mock

import gemstone_py.concurrency as concurrency_mod
import gemstone_py.ordered_collection as ordered_collection_mod


def _make_ordered_collection():
    session = mock.Mock()
    obj = object.__new__(ordered_collection_mod.OrderedCollection)
    object.__setattr__(obj, "_session", session)
    object.__setattr__(obj, "_oop", 111)
    return obj, session


class _FakeProxy(concurrency_mod._GsProxy):
    pass


def _make_proxy():
    session = mock.Mock()
    obj = _FakeProxy(session, 222)
    return obj, session


class OrderedCollectionBridgeTests(unittest.TestCase):
    def test_send_dispatches_and_wraps_result(self):
        col, session = _make_ordered_collection()
        session.perform_oop.return_value = 999

        with mock.patch.object(ordered_collection_mod, "_from_oop", return_value="wrapped") as from_oop:
            result = col.send("last")

        self.assertEqual(result, "wrapped")
        session.perform_oop.assert_called_once_with(111, "last")
        from_oop.assert_called_once_with(session, 999)
        self.assertEqual(col.oop, 111)

    def test_dynamic_selector_mapping_uses_smalltalk_keywords(self):
        col, _session = _make_ordered_collection()

        with mock.patch.object(ordered_collection_mod.OrderedCollection, "send", autospec=True, return_value="wrapped") as send:
            result = col.at_put_(1, "alpha")

        self.assertEqual(result, "wrapped")
        send.assert_called_once_with(col, "at:put:", 1, "alpha")

    def test_reverse_iter_uses_array_snapshot_without_eval_string_oops(self):
        col, session = _make_ordered_collection()
        session.perform_oop.side_effect = [500, 703, 702, 701]
        session.perform.return_value = 3

        with mock.patch.object(ordered_collection_mod, "_from_oop", side_effect=lambda _s, oop: f"wrapped:{oop}") as from_oop:
            result = list(col.reverse_iter())

        self.assertEqual(result, ["wrapped:703", "wrapped:702", "wrapped:701"])
        self.assertEqual(session.perform_oop.call_args_list, [
            mock.call(111, "asArray"),
            mock.call(500, "at:", ordered_collection_mod._gs._python_to_smallint(3)),
            mock.call(500, "at:", ordered_collection_mod._gs._python_to_smallint(2)),
            mock.call(500, "at:", ordered_collection_mod._gs._python_to_smallint(1)),
        ])
        session.perform.assert_called_once_with(500, "size")
        session.eval.assert_not_called()
        self.assertEqual(from_oop.call_count, 3)

    def test_clear_uses_plain_gemstone_object_for_oop(self):
        col, session = _make_ordered_collection()

        result = col.clear()

        self.assertIs(result, col)
        session.eval.assert_called_once_with(
            "(Object _objectForOop: 111) removeAllSuchThat: [:e | true]."
        )


class ProxyBridgeTests(unittest.TestCase):
    def test_send_dispatches_and_wraps_result(self):
        proxy, session = _make_proxy()
        session.perform_oop.return_value = 654

        with mock.patch.object(concurrency_mod, "_py", return_value="wrapped") as py:
            result = proxy.send("value")

        self.assertEqual(result, "wrapped")
        session.perform_oop.assert_called_once_with(222, "value")
        py.assert_called_once_with(session, 654)
        self.assertEqual(proxy.oop, 222)

    def test_dynamic_selector_mapping_uses_smalltalk_keywords(self):
        proxy, _session = _make_proxy()

        with mock.patch.object(_FakeProxy, "send", autospec=True, return_value="wrapped") as send:
            result = proxy.decrementBy_ifLessThan_thenExecute_(5, 0, "ignored")

        self.assertEqual(result, "wrapped")
        send.assert_called_once_with(proxy, "decrementBy:ifLessThan:thenExecute:", 5, 0, "ignored")


if __name__ == "__main__":
    unittest.main()
