from __future__ import annotations

import os
import unittest
from typing import Any, Protocol

import gemstone_py as gemstone
from gemstone_py.codegen import generate_wrapper

RUN_LIVE = os.environ.get("GS_RUN_LIVE") == "1"


@gemstone.gemstone_class("Date")
class LiveDateProto(Protocol):
    @classmethod
    @gemstone.gemstone_selector("today")
    def today(cls) -> "LiveDateProto":
        ...

    @property
    def printString(self) -> str:
        ...

    def yourself(self) -> "LiveDateProto":
        ...


@unittest.skipUnless(RUN_LIVE, "set GS_RUN_LIVE=1 to run live GemStone codegen tests")
class LiveCodegenTests(unittest.TestCase):
    def test_generated_wrapper_round_trips_against_date(self) -> None:
        namespace: dict[str, Any] = {}
        exec(generate_wrapper(LiveDateProto), namespace)
        date_cls = namespace["LiveDate"]

        config = gemstone.GemStoneConfig.from_env()
        with gemstone.GemStoneSession(config=config) as session:
            today = date_cls.today(session)
            self.assertEqual(today.gemstone_class_name, "Date")
            self.assertIs(today.wrapper_type, date_cls)
            self.assertIsInstance(today.printString, str)

            same_day = today.yourself()
            self.assertIsInstance(same_day, date_cls)
            self.assertEqual(same_day.gemstone_class_name, "Date")


if __name__ == "__main__":
    unittest.main()
