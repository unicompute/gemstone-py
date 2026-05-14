import unittest
from unittest import mock

import gemstone_py as gemstone


class BulkPerformTests(unittest.TestCase):
    def test_bulk_perform_oop_sends_one_eval_and_preserves_order(self):
        session = gemstone.GemStoneSession(username="alice", password="secret")

        with mock.patch.object(session, "eval", return_value="301\n302\n") as eval_source:
            result = session.bulk_perform_oop([101, 202], "at:", gemstone._python_to_smallint(1))

        self.assertEqual(result, [301, 302])
        source = eval_source.call_args.args[0]
        self.assertIn("receivers at: 1 put: (Object _objectForOop: 101).", source)
        self.assertIn("receivers at: 2 put: (Object _objectForOop: 202).", source)
        self.assertIn("args at: 1 put: (Object _objectForOop:", source)
        self.assertIn("selector := 'at:' asSymbol.", source)
        self.assertIn("perform: selector withArguments: args", source)

    def test_bulk_perform_oop_escapes_selector_literal(self):
        session = gemstone.GemStoneSession(username="alice", password="secret")

        with mock.patch.object(session, "eval", return_value="301\n") as eval_source:
            session.bulk_perform_oop([101], "selector'withQuote")

        self.assertIn("selector := 'selector''withQuote' asSymbol.", eval_source.call_args.args[0])

    def test_bulk_perform_oop_empty_receivers_does_not_eval(self):
        session = gemstone.GemStoneSession(username="alice", password="secret")

        with mock.patch.object(session, "eval") as eval_source:
            result = session.bulk_perform_oop([], "size")

        self.assertEqual(result, [])
        eval_source.assert_not_called()

    def test_bulk_perform_value_marshals_each_result(self):
        session = gemstone.GemStoneSession(username="alice", password="secret")

        with mock.patch.object(session, "bulk_perform_oop", return_value=[101, 202]):
            with mock.patch.object(session, "_marshal", side_effect=["Alice", "Bob"]) as marshal:
                result = session.bulk_perform_value([1, 2], "name")

        self.assertEqual(result, ["Alice", "Bob"])
        self.assertEqual(marshal.call_args_list, [mock.call(101), mock.call(202)])

    def test_perform_many_aliases_bulk_perform(self):
        session = gemstone.GemStoneSession(username="alice", password="secret")

        with mock.patch.object(session, "bulk_perform_oop", return_value=[101]) as bulk_oop:
            self.assertEqual(session.perform_many_oop([1], "size"), [101])
        bulk_oop.assert_called_once_with([1], "size")

        with mock.patch.object(session, "bulk_perform_value", return_value=[3]) as bulk_value:
            self.assertEqual(session.perform_many_value([1], "size"), [3])
        bulk_value.assert_called_once_with([1], "size")


if __name__ == "__main__":
    unittest.main()
