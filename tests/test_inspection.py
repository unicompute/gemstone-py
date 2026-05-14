import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

import gemstone_py as gemstone
from gemstone_py import inspection


class InspectionParsingTests(unittest.TestCase):
    def test_inspect_oop_parses_header_and_slots(self):
        session = mock.Mock()
        session.eval.return_value = (
            "Person|a Person\n"
            "name|101|String|Alice\n"
            "address|202|Address|10 High\\pStreet\n"
        )

        result = inspection.inspect_oop(session, 123)

        self.assertEqual(result.oop, 123)
        self.assertEqual(result.class_name, "Person")
        self.assertEqual(result.summary, "a Person")
        self.assertEqual(result.slots[0].name, "name")
        self.assertEqual(result.slots[0].value.oop, 101)
        self.assertEqual(result.slots[1].value.summary, "10 High|Street")
        self.assertIn("Object _objectForOop: 123", session.eval.call_args.args[0])
        self.assertIn("allInstVarNames", session.eval.call_args.args[0])

    def test_inspect_oop_filters_slots(self):
        session = mock.Mock()
        session.eval.return_value = (
            "Person|a Person\n"
            "name|101|String|Alice\n"
            "address|202|Address|10 High Street\n"
        )

        result = inspection.inspect_oop(session, 123, slots=["address"])

        self.assertEqual([slot.name for slot in result.slots], ["address"])

    def test_dump_oop_recurses_and_marks_cycles(self):
        root = inspection.InspectionResult(
            oop=1,
            class_name="Node",
            summary="root",
            slots=[
                inspection.InspectedSlot(
                    "child",
                    inspection.InspectedReference(2, "Node", "child"),
                )
            ],
        )
        child = inspection.InspectionResult(
            oop=2,
            class_name="Node",
            summary="child",
            slots=[
                inspection.InspectedSlot(
                    "parent",
                    inspection.InspectedReference(1, "Node", "root"),
                )
            ],
        )

        with mock.patch(
            "gemstone_py.inspection.inspect_oop",
            side_effect=[root, child],
        ):
            payload = inspection.dump_oop(mock.Mock(), 1, depth=3)

        self.assertEqual(payload["class_name"], "Node")
        self.assertEqual(payload["slots"]["child"]["slots"]["parent"], {"oop": 1, "cycle": True})

    def test_dump_oop_filters_slots_and_classes(self):
        root = inspection.InspectionResult(
            oop=1,
            class_name="Node",
            summary="root",
            slots=[
                inspection.InspectedSlot(
                    "child",
                    inspection.InspectedReference(2, "Leaf", "child"),
                )
            ],
        )
        child = inspection.InspectionResult(
            oop=2,
            class_name="Leaf",
            summary="child",
            slots=[],
        )

        with mock.patch(
            "gemstone_py.inspection.inspect_oop",
            side_effect=[root, child],
        ) as inspect_oop:
            payload = inspection.dump_oop(
                mock.Mock(),
                1,
                depth=3,
                slots=["child"],
                classes=["Node"],
            )

        self.assertEqual(payload["slots"]["child"]["class_name"], "Leaf")
        self.assertTrue(payload["slots"]["child"]["filtered"])
        self.assertNotIn("slots", payload["slots"]["child"])
        self.assertEqual(inspect_oop.call_args_list[0].kwargs["slots"], ["child"])

    def test_format_inspection_and_dump(self):
        result = inspection.InspectionResult(
            oop=1,
            class_name="Node",
            summary="root",
            slots=[
                inspection.InspectedSlot(
                    "child",
                    inspection.InspectedReference(2, "Node", "child"),
                )
            ],
        )
        self.assertIn("Node  oop=0x1", inspection.format_inspection(result))
        self.assertIn("child: Node oop=0x2 child", inspection.format_inspection(result))

        payload = {
            "oop": 1,
            "class_name": "Node",
            "summary": "root",
            "slots": {
                "child": {
                    "oop": 2,
                    "class_name": "Node",
                    "summary": "child",
                    "slots": {"parent": {"oop": 1, "cycle": True}},
                }
            },
        }
        text = inspection.format_dump(payload)

        self.assertIn("Node oop=0x1 root", text)
        self.assertIn("child: Node oop=0x2 child", text)
        self.assertIn("parent: <cycle oop=0x1>", text)

    def test_describe_class_parses_superclasses_and_instvars(self):
        session = mock.Mock()
        session.resolve.return_value = 999
        session.eval.return_value = (
            "OkzBooking|42\n"
            "superclass|Object\n"
            "instvar|status\n"
            "instvar|amount\n"
            "class_instvar|DefaultStatus\n"
        )

        description = inspection.describe_class(session, "OkzBooking")

        self.assertEqual(description.name, "OkzBooking")
        self.assertEqual(description.instance_count, 42)
        self.assertEqual(description.superclasses, ["Object"])
        self.assertEqual(description.instvars, ["status", "amount"])
        self.assertEqual(description.class_instvars, ["DefaultStatus"])
        session.resolve.assert_called_once_with("OkzBooking")
        self.assertIn("Object _objectForOop: 999", session.eval.call_args.args[0])

    def test_session_methods_delegate_to_inspection_helpers(self):
        session = gemstone.GemStoneSession(username="alice", password="secret")

        with mock.patch("gemstone_py.inspection.inspect_oop", return_value="inspected") as inspect_oop:
            self.assertEqual(session.inspect(123), "inspected")
        inspect_oop.assert_called_once_with(session, 123)

        with mock.patch("gemstone_py.inspection.dump_oop", return_value={"ok": True}) as dump_oop:
            self.assertEqual(session.dump(123, depth=4), {"ok": True})
        dump_oop.assert_called_once_with(session, 123, depth=4)

        with mock.patch(
            "gemstone_py.inspection.describe_class",
            return_value="described",
        ) as describe_class:
            self.assertEqual(session.describe_class("OkzBooking"), "described")
        describe_class.assert_called_once_with(session, "OkzBooking")


class InspectionCliTests(unittest.TestCase):
    def test_main_prints_class_description_json(self):
        description = inspection.ClassDescription(
            name="OkzBooking",
            superclasses=["Object"],
            instvars=["status"],
            class_instvars=[],
            instance_count=2,
        )

        class SessionContext:
            def __init__(self, *args, **kwargs):
                del args, kwargs

            def __enter__(self):
                return mock.Mock()

            def __exit__(self, exc_type, exc_val, exc_tb):
                del exc_type, exc_val, exc_tb
                return False

        stream = io.StringIO()
        with mock.patch("gemstone_py.inspection.GemStoneSession", SessionContext):
            with mock.patch(
                "gemstone_py.inspection.GemStoneConfig.from_env",
                return_value=mock.Mock(),
            ):
                with mock.patch(
                    "gemstone_py.inspection.describe_class",
                    return_value=description,
                ):
                    with redirect_stdout(stream):
                        exit_code = inspection.main(["--class", "OkzBooking", "--json"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["name"], "OkzBooking")
        self.assertEqual(payload["instvars"], ["status"])


if __name__ == "__main__":
    unittest.main()
