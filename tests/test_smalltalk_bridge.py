import unittest
from unittest import mock

from gemstone_py.persistent_root import GsObject
from gemstone_py.smalltalk_bridge import SmalltalkBridge, SmalltalkObject, bridge


class FakeSession:
    def __init__(self):
        self.calls = []

    def resolve(self, name):
        self.calls.append(("resolve", name))
        return f"oop:{name}"

    def perform_oop(self, receiver, selector, *args):
        self.calls.append(("perform_oop", receiver, selector, args))
        return "oop:result"


class SmalltalkBridgeTests(unittest.TestCase):
    def test_bridge_constructor_returns_bridge(self):
        session = FakeSession()

        result = bridge(session)

        self.assertIsInstance(result, SmalltalkBridge)

    def test_getitem_resolves_global_name(self):
        session = FakeSession()
        st = SmalltalkBridge(session)

        obj = st["SystemRepository"]

        self.assertIsInstance(obj, SmalltalkObject)
        self.assertEqual(object.__getattribute__(obj, "_oop"), "oop:SystemRepository")
        self.assertEqual(object.__getattribute__(obj, "_name"), "SystemRepository")
        self.assertEqual(obj.oop, "oop:SystemRepository")
        self.assertEqual(session.calls, [("resolve", "SystemRepository")])

    def test_bridge_send_resolves_and_dispatches(self):
        session = FakeSession()
        st = SmalltalkBridge(session)

        with mock.patch(
            "gemstone_py.smalltalk_bridge._from_oop",
            return_value="wrapped",
        ) as from_oop:
            result = st.send("SystemRepository", "name")

        self.assertEqual(result, "wrapped")
        self.assertEqual(
            session.calls,
            [
                ("resolve", "SystemRepository"),
                ("perform_oop", "oop:SystemRepository", "name", ()),
            ],
        )
        from_oop.assert_called_once_with(session, "oop:result")

    def test_bridge_send_promotes_generic_gsobject_to_smalltalk_object(self):
        session = FakeSession()
        st = SmalltalkBridge(session)
        generic = GsObject(session, "oop:result")

        with mock.patch("gemstone_py.smalltalk_bridge._from_oop", return_value=generic):
            result = st.send("SystemRepository", "name")

        self.assertIsInstance(result, SmalltalkObject)
        self.assertEqual(object.__getattribute__(result, "_oop"), "oop:result")

    def test_python_keyword_name_maps_to_smalltalk_selector(self):
        session = FakeSession()
        obj = SmalltalkObject(session, "oop:UserGlobals", name="UserGlobals")

        with mock.patch(
            "gemstone_py.smalltalk_bridge._to_oop",
            side_effect=lambda _s, value: f"oop:{value}",
        ):
            with mock.patch(
                "gemstone_py.smalltalk_bridge._from_oop",
                return_value="stored",
            ):
                result = obj.at_put_("BridgeDemo", 42)

        self.assertEqual(result, "stored")
        self.assertEqual(
            session.calls,
            [
                ("perform_oop", "oop:UserGlobals", "at:put:", ("oop:BridgeDemo", "oop:42")),
            ],
        )


if __name__ == "__main__":
    unittest.main()
