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


if __name__ == "__main__":
    unittest.main()
