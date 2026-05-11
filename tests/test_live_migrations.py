from __future__ import annotations

import os
import unittest

import gemstone_py as gemstone
from gemstone_py.migrations import MigrationStep, current_version, downgrade, upgrade

RUN_LIVE = os.environ.get("GS_RUN_LIVE") == "1"


@unittest.skipUnless(RUN_LIVE, "set GS_RUN_LIVE=1 to run live GemStone migration tests")
class LiveMigrationTests(unittest.TestCase):
    def test_module_migration_upgrade_and_downgrade_round_trip(self) -> None:
        suffix = str(os.getpid())
        probe_key = f"GemstonePyLiveMigrationProbe{suffix}"
        root_key = f"GemstonePyLiveMigrationVersions{suffix}"
        lock_key = f"GemstonePyLiveMigrationLock{suffix}"

        def apply(session: gemstone.GemStoneSession) -> None:
            session.eval(f"UserGlobals at: #{probe_key} put: 7")

        def rollback(session: gemstone.GemStoneSession) -> None:
            session.eval(f"UserGlobals removeKey: #{probe_key} ifAbsent: []")

        step = MigrationStep(
            "001_live_probe",
            apply,
            rollback,
            checksum="live-test",
            description="Live migration probe.",
        )

        config = gemstone.GemStoneConfig.from_env()
        with gemstone.GemStoneSession(config=config) as session:
            try:
                self._cleanup(session, probe_key, root_key, lock_key)
                upgraded = upgrade(
                    session,
                    [step],
                    root_key=root_key,
                    lock_key=lock_key,
                    lock_owner="live-migration-test",
                )
                self.assertEqual(upgraded.steps, ("001_live_probe",))
                self.assertEqual(current_version(session, root_key=root_key), "001_live_probe")
                self.assertEqual(
                    session.eval(f"UserGlobals at: #{probe_key} ifAbsent: [0]"),
                    7,
                )

                rolled_back = downgrade(
                    session,
                    [step],
                    target="base",
                    root_key=root_key,
                    lock_key=lock_key,
                    lock_owner="live-migration-test",
                )
                self.assertEqual(rolled_back.steps, ("001_live_probe",))
                self.assertIsNone(current_version(session, root_key=root_key))
                self.assertEqual(
                    session.eval(f"UserGlobals at: #{probe_key} ifAbsent: [0]"),
                    0,
                )
            finally:
                self._cleanup(session, probe_key, root_key, lock_key)

    @staticmethod
    def _cleanup(
        session: gemstone.GemStoneSession,
        probe_key: str,
        root_key: str,
        lock_key: str,
    ) -> None:
        for key in (probe_key, root_key, lock_key):
            session.eval(f"UserGlobals removeKey: #{key} ifAbsent: []")
        session.commit()


if __name__ == "__main__":
    unittest.main()
