import os
import unittest

import gemstone_py as gemstone

RUN_LIVE = os.environ.get("GS_RUN_LIVE") == "1"


@unittest.skipUnless(RUN_LIVE, "set GS_RUN_LIVE=1 to run live GemStone smoke tests")
class LiveSmokeTests(unittest.TestCase):
    def test_login_eval_and_print_string(self):
        config = gemstone.GemStoneConfig.from_env()

        with gemstone.GemStoneSession(config=config) as session:
            self.assertEqual(session.eval("3 + 4"), 7)
            ref = session.eval("Object new")
            self.assertIsInstance(ref, gemstone.OopRef)
            self.assertTrue(ref.print_string())

    def test_error_exposes_live_exception_object(self):
        config = gemstone.GemStoneConfig.from_env()

        with gemstone.GemStoneSession(config=config) as session:
            with self.assertRaises(gemstone.GemStoneError) as ctx:
                session.eval("1/0")
            err = ctx.exception
            self.assertEqual(err.number, 2026)
            self.assertIsNotNone(err.exception)
            # session still logged in here -> selectors dispatch as methods
            desc = err.exception.description()  # ZeroDivide#messageText is nil; use #description
            self.assertIn("attempt to divide 1 by zero", desc)


if __name__ == "__main__":
    unittest.main()
