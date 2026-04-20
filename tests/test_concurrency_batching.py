import unittest
from unittest import mock

from gemstone_py.concurrency import RCHash


class RCHashBatchingTests(unittest.TestCase):
    def test_fetch_all_uses_batched_scalar_eval_when_available(self):
        session = mock.Mock()
        session.eval.return_value = '["alpha",1]\n[true,null]\n'
        rc_hash = RCHash(session, oop=123)

        result = rc_hash._fetch_all()

        self.assertEqual(result, [("alpha", 1), (True, None)])
        session.eval.assert_called_once()
        session.perform_oop.assert_not_called()

    def test_fetch_all_falls_back_to_association_traversal_for_non_scalars(self):
        session = mock.Mock()
        session.eval.side_effect = [None, "701|801\n702|802\n"]
        session._marshal.side_effect = ["alpha", "wrapped:801", "beta", "wrapped:802"]
        rc_hash = RCHash(session, oop=123)

        result = rc_hash._fetch_all()

        self.assertEqual(result, [("alpha", "wrapped:801"), ("beta", "wrapped:802")])
        self.assertEqual(session.eval.call_count, 2)
        session.perform_oop.assert_not_called()
        session.perform.assert_not_called()


if __name__ == "__main__":
    unittest.main()
