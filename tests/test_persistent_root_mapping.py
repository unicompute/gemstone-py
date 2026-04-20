import unittest
from unittest import mock

import gemstone_py.persistent_root as mod


def _make_gs_dict():
    obj = object.__new__(mod.GsDict)
    session = mock.Mock()
    object.__setattr__(obj, "_session", session)
    object.__setattr__(obj, "_oop", 123)
    return obj, session


def _make_gs_object():
    session = mock.Mock()
    obj = object.__new__(mod.GsObject)
    object.__setattr__(obj, "_session", session)
    object.__setattr__(obj, "_oop", 321)
    return obj, session


def _make_persistent_root():
    session = mock.Mock()
    obj = object.__new__(mod.PersistentRoot)
    object.__setattr__(obj, "_session", session)
    object.__setattr__(obj, "_name", "UserGlobals")
    object.__setattr__(obj, "_ug", 456)
    return obj, session


class GsDictMappingTests(unittest.TestCase):
    def test_delitem_removes_existing_key_via_smalltalk_message(self):
        gs_dict, _session = _make_gs_dict()

        with mock.patch.object(mod.GsDict, "__contains__", autospec=True, return_value=True) as contains:
            with mock.patch.object(mod.GsDict, "_call", autospec=True) as call:
                del gs_dict["alpha"]

        contains.assert_called_once_with(gs_dict, "alpha")
        call.assert_called_once_with(gs_dict, "removeKey:ifAbsent:", "alpha", None)

    def test_delitem_raises_key_error_for_missing_key(self):
        gs_dict, _session = _make_gs_dict()

        with mock.patch.object(mod.GsDict, "__contains__", autospec=True, return_value=False):
            with self.assertRaises(KeyError):
                del gs_dict["alpha"]

    def test_pop_returns_existing_value_and_deletes_key(self):
        gs_dict, _session = _make_gs_dict()

        with mock.patch.object(mod.GsDict, "__contains__", autospec=True, return_value=True) as contains:
            with mock.patch.object(mod.GsDict, "__getitem__", autospec=True, return_value=42) as getitem:
                with mock.patch.object(mod.GsDict, "__delitem__", autospec=True) as delitem:
                    value = gs_dict.pop("alpha")

        self.assertEqual(value, 42)
        contains.assert_called_once_with(gs_dict, "alpha")
        getitem.assert_called_once_with(gs_dict, "alpha")
        delitem.assert_called_once_with(gs_dict, "alpha")

    def test_setdefault_stores_default_for_missing_key(self):
        gs_dict, _session = _make_gs_dict()

        with mock.patch.object(mod.GsDict, "__contains__", autospec=True, return_value=False) as contains:
            with mock.patch.object(mod.GsDict, "__setitem__", autospec=True) as setitem:
                value = gs_dict.setdefault("alpha", 42)

        self.assertEqual(value, 42)
        contains.assert_called_once_with(gs_dict, "alpha")
        setitem.assert_called_once_with(gs_dict, "alpha", 42)

    def test_update_applies_mapping_iterable_and_kwargs(self):
        gs_dict, _session = _make_gs_dict()

        with mock.patch.object(mod.GsDict, "__setitem__", autospec=True) as setitem:
            gs_dict.update({"alpha": 1}, beta=2)

        self.assertEqual(
            setitem.call_args_list,
            [
                mock.call(gs_dict, "alpha", 1),
                mock.call(gs_dict, "beta", 2),
            ],
        )

    def test_clear_calls_remove_all(self):
        gs_dict, _session = _make_gs_dict()

        with mock.patch.object(mod.GsDict, "_call", autospec=True) as call:
            gs_dict.clear()

        call.assert_called_once_with(gs_dict, "removeAll")

    def test_keys_use_batched_eval_and_decode_escaped_rows(self):
        gs_dict, session = _make_gs_dict()
        session.eval.return_value = "alpha\nbeta\\ppipe\n"

        result = gs_dict.keys()

        self.assertEqual(result, ["alpha", "beta|pipe"])
        session.eval.assert_called_once()

    def test_items_use_batched_eval_and_wrap_oops(self):
        gs_dict, session = _make_gs_dict()
        session.eval.return_value = "alpha|101\nbeta\\ppipe|202\n"

        with mock.patch.object(
            mod,
            "_from_oop",
            side_effect=lambda current_session, oop: f"{current_session is session}:{oop}",
        ) as from_oop:
            result = gs_dict.items()

        self.assertEqual(result, [("alpha", "True:101"), ("beta|pipe", "True:202")])
        self.assertEqual(
            from_oop.call_args_list,
            [mock.call(session, 101), mock.call(session, 202)],
        )
        session.eval.assert_called_once()

    def test_values_use_batched_eval_and_wrap_oops(self):
        gs_dict, session = _make_gs_dict()
        session.eval.return_value = "alpha|101\nbeta|202\n"

        with mock.patch.object(mod, "_from_oop", side_effect=["first", "second"]) as from_oop:
            result = gs_dict.values()

        self.assertEqual(result, ["first", "second"])
        self.assertEqual(
            from_oop.call_args_list,
            [mock.call(session, 101), mock.call(session, 202)],
        )
        session.eval.assert_called_once()

    def test_len_uses_size_directly(self):
        gs_dict, session = _make_gs_dict()
        session.perform.return_value = 7

        self.assertEqual(len(gs_dict), 7)
        session.perform.assert_called_once_with(123, "size")

    def test_gs_dict_send_dispatches_and_wraps_result(self):
        gs_dict, session = _make_gs_dict()
        session.perform_oop.return_value = 999

        with mock.patch.object(mod, "_from_oop", return_value="wrapped") as from_oop:
            result = gs_dict.send("size")

        self.assertEqual(result, "wrapped")
        session.perform_oop.assert_called_once_with(123, "size")
        from_oop.assert_called_once_with(session, 999)
        self.assertEqual(gs_dict.oop, 123)

    def test_gs_dict_dynamic_selector_mapping_uses_smalltalk_keywords(self):
        gs_dict, _session = _make_gs_dict()

        with mock.patch.object(mod.GsDict, "send", autospec=True, return_value="wrapped") as send:
            result = gs_dict.at_put_("alpha", 1)

        self.assertEqual(result, "wrapped")
        send.assert_called_once_with(gs_dict, "at:put:", "alpha", 1)


class GsObjectBridgeTests(unittest.TestCase):
    def test_gs_object_send_dispatches_and_wraps_result(self):
        obj, session = _make_gs_object()
        session.perform_oop.return_value = 654

        with mock.patch.object(mod, "_from_oop", return_value="wrapped") as from_oop:
            result = obj.send("name")

        self.assertEqual(result, "wrapped")
        session.perform_oop.assert_called_once_with(321, "name")
        from_oop.assert_called_once_with(session, 654)
        self.assertEqual(obj.oop, 321)

    def test_gs_object_dynamic_selector_mapping_supports_chained_smalltalk_names(self):
        obj, _session = _make_gs_object()

        with mock.patch.object(mod.GsObject, "send", autospec=True, return_value="wrapped") as send:
            result = obj.at_ifAbsent_("Foo", 1)

        self.assertEqual(result, "wrapped")
        send.assert_called_once_with(obj, "at:ifAbsent:", "Foo", 1)


class PersistentRootMappingTests(unittest.TestCase):
    def test_delitem_removes_existing_symbol_key(self):
        root, session = _make_persistent_root()
        session.new_symbol.return_value = 789

        with mock.patch.object(mod.PersistentRoot, "__contains__", autospec=True, return_value=True) as contains:
            del root["Alpha"]

        contains.assert_called_once_with(root, "Alpha")
        session.new_symbol.assert_called_once_with("Alpha")
        session.perform_oop.assert_called_once_with(
            456,
            "removeKey:ifAbsent:",
            789,
            mod._gs.OOP_NIL,
        )

    def test_delitem_raises_key_error_for_missing_key(self):
        root, _session = _make_persistent_root()

        with mock.patch.object(mod.PersistentRoot, "__contains__", autospec=True, return_value=False):
            with self.assertRaises(KeyError):
                del root["Alpha"]

    def test_pop_returns_existing_value_and_deletes_key(self):
        root, _session = _make_persistent_root()

        with mock.patch.object(mod.PersistentRoot, "__contains__", autospec=True, return_value=True) as contains:
            with mock.patch.object(mod.PersistentRoot, "__getitem__", autospec=True, return_value="value") as getitem:
                with mock.patch.object(mod.PersistentRoot, "__delitem__", autospec=True) as delitem:
                    value = root.pop("Alpha")

        self.assertEqual(value, "value")
        contains.assert_called_once_with(root, "Alpha")
        getitem.assert_called_once_with(root, "Alpha")
        delitem.assert_called_once_with(root, "Alpha")

    def test_setdefault_stores_default_for_missing_key(self):
        root, _session = _make_persistent_root()

        with mock.patch.object(mod.PersistentRoot, "__contains__", autospec=True, return_value=False) as contains:
            with mock.patch.object(mod.PersistentRoot, "__setitem__", autospec=True) as setitem:
                value = root.setdefault("Alpha", 42)

        self.assertEqual(value, 42)
        contains.assert_called_once_with(root, "Alpha")
        setitem.assert_called_once_with(root, "Alpha", 42)

    def test_update_applies_mapping_iterable_and_kwargs(self):
        root, _session = _make_persistent_root()

        with mock.patch.object(mod.PersistentRoot, "__setitem__", autospec=True) as setitem:
            root.update({"Alpha": 1}, Beta=2)

        self.assertEqual(
            setitem.call_args_list,
            [
                mock.call(root, "Alpha", 1),
                mock.call(root, "Beta", 2),
            ],
        )

    def test_keys_use_batched_eval_and_decode_escaped_rows(self):
        root, session = _make_persistent_root()
        session.eval.return_value = "Alpha\nBeta\\pPipe\n"

        result = root.keys()

        self.assertEqual(result, ["Alpha", "Beta|Pipe"])
        session.eval.assert_called_once()

    def test_items_use_batched_eval_and_wrap_oops(self):
        root, session = _make_persistent_root()
        session.eval.return_value = "Alpha|301\nBeta\\pPipe|302\n"

        with mock.patch.object(mod, "_from_oop", side_effect=["value-a", "value-b"]) as from_oop:
            result = root.items()

        self.assertEqual(result, [("Alpha", "value-a"), ("Beta|Pipe", "value-b")])
        self.assertEqual(
            from_oop.call_args_list,
            [mock.call(session, 301), mock.call(session, 302)],
        )
        session.eval.assert_called_once()

    def test_values_use_batched_eval_and_wrap_oops(self):
        root, session = _make_persistent_root()
        session.eval.return_value = "Alpha|401\nBeta|402\n"

        with mock.patch.object(mod, "_from_oop", side_effect=["first", "second"]) as from_oop:
            result = root.values()

        self.assertEqual(result, ["first", "second"])
        self.assertEqual(
            from_oop.call_args_list,
            [mock.call(session, 401), mock.call(session, 402)],
        )
        session.eval.assert_called_once()

    def test_len_uses_size_directly(self):
        root, session = _make_persistent_root()
        session.perform.return_value = 4

        self.assertEqual(len(root), 4)
        session.perform.assert_called_once_with(456, "size")


if __name__ == "__main__":
    unittest.main()
