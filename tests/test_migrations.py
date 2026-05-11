import io
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from gemstone_py import gemstone_class
from gemstone_py.inspection import ClassDescription
from gemstone_py.migrations import (
    DEFAULT_VERSION_ROOT,
    Migration,
    MigrationError,
    MigrationStep,
    current_version,
    diff_class,
    downgrade,
    load_manifest,
    main,
    migration_from_module,
    migration_status,
    plan_downgrade,
    plan_upgrade,
    scaffold,
    upgrade,
    validate_migration_state,
)


class _DemoMigration(Migration):
    def up(self, session):
        return None


class MigrationChunkingTests(unittest.TestCase):
    def test_each_in_chunks_uses_raw_oops_by_default(self):
        migration = _DemoMigration()
        session = mock.Mock()
        seen = []

        with mock.patch(
            "gemstone_py.concurrency.list_instances",
            return_value=[101, 102, 103],
        ) as list_instances:
            with mock.patch.object(Migration, "_commit_with_retry", autospec=True) as commit:
                total = migration.each_in_chunks(
                    session,
                    "RcCounter",
                    lambda current_session, item: seen.append((current_session, item)),
                    chunk_size=2,
                )

        self.assertEqual(total, 3)
        self.assertEqual(seen, [(session, 101), (session, 102), (session, 103)])
        list_instances.assert_called_once_with(session, "RcCounter", wrap=False)
        self.assertEqual(commit.call_args_list, [
            mock.call(migration, session),
            mock.call(migration, session),
        ])

    def test_each_in_chunks_can_yield_wrapped_instances(self):
        migration = _DemoMigration()
        session = mock.Mock()
        wrapped = [mock.Mock(oop=201), mock.Mock(oop=202)]
        seen = []

        with mock.patch(
            "gemstone_py.concurrency.list_instances",
            return_value=wrapped,
        ) as list_instances:
            with mock.patch.object(Migration, "_commit_with_retry", autospec=True) as commit:
                total = migration.each_in_chunks(
                    session,
                    "RcCounter",
                    lambda current_session, item: seen.append((current_session, item)),
                    chunk_size=10,
                    wrap=True,
                )

        self.assertEqual(total, 2)
        self.assertEqual(seen, [(session, wrapped[0]), (session, wrapped[1])])
        list_instances.assert_called_once_with(session, "RcCounter", wrap=True)
        commit.assert_called_once_with(migration, session)


class ModuleMigrationTests(unittest.TestCase):
    def test_migration_from_module_reads_metadata(self):
        module = types.ModuleType("app.migrations.001_initial")
        module.__doc__ = "Create the first shape."
        module.dependencies = ("000_base",)

        def upgrade_callback(session):
            session.touched = True

        def downgrade_callback(session):
            session.touched = False

        module.upgrade = upgrade_callback
        module.downgrade = downgrade_callback

        step = migration_from_module(module)

        self.assertEqual(step.id, "001_initial")
        self.assertEqual(step.description, "Create the first shape.")
        self.assertEqual(step.dependencies, ("000_base",))
        self.assertIs(step.upgrade, upgrade_callback)
        self.assertIs(step.downgrade, downgrade_callback)

    def test_load_manifest_accepts_module_entries(self):
        migration_module = types.ModuleType("app.migrations.001_initial")
        migration_module.upgrade = lambda session: None
        manifest_module = types.ModuleType("app.migrations.manifest")
        manifest_module.migrations = [migration_module]

        steps = load_manifest(manifest_module)

        self.assertEqual([step.id for step in steps], ["001_initial"])

    def test_plan_upgrade_orders_dependencies_and_skips_applied(self):
        calls = []
        first = MigrationStep("001_initial", lambda session: calls.append("first"))
        second = MigrationStep(
            "002_add_total",
            lambda session: calls.append("second"),
            dependencies=("001_initial",),
        )

        pending = plan_upgrade([second, first], {"001_initial": {}})

        self.assertEqual([step.id for step in pending], ["002_add_total"])

    def test_plan_downgrade_keeps_target_applied(self):
        first = MigrationStep("001_initial", lambda session: None, lambda session: None)
        second = MigrationStep(
            "002_add_total",
            lambda session: None,
            lambda session: None,
            dependencies=("001_initial",),
        )

        pending = plan_downgrade(
            [first, second],
            {"001_initial": {}, "002_add_total": {}},
            target="001_initial",
        )

        self.assertEqual([step.id for step in pending], ["002_add_total"])

    def test_upgrade_records_versions_and_commits_each_step(self):
        root = {}
        session = mock.Mock()
        calls = []
        first = MigrationStep("001_initial", lambda current: calls.append(("up", current)))
        second = MigrationStep(
            "002_add_total",
            lambda current: calls.append(("up2", current)),
            dependencies=("001_initial",),
            checksum="abc",
            description="Add total.",
        )

        with mock.patch("gemstone_py.persistent_root.PersistentRoot", return_value=root):
            result = upgrade(session, [second, first])

        self.assertEqual(result.steps, ("001_initial", "002_add_total"))
        self.assertEqual(calls, [("up", session), ("up2", session)])
        self.assertEqual(session.commit.call_count, 2)
        self.assertIn("001_initial", root[DEFAULT_VERSION_ROOT])
        self.assertEqual(root[DEFAULT_VERSION_ROOT]["002_add_total"]["checksum"], "abc")

    def test_upgrade_dry_run_does_not_touch_session(self):
        root = {}
        session = mock.Mock()
        step = MigrationStep("001_initial", lambda current: current.commit())

        with mock.patch("gemstone_py.persistent_root.PersistentRoot", return_value=root):
            result = upgrade(session, [step], dry_run=True)

        self.assertEqual(result.steps, ("001_initial",))
        self.assertTrue(result.dry_run)
        session.commit.assert_not_called()
        self.assertNotIn(DEFAULT_VERSION_ROOT, root)

    def test_downgrade_removes_records_and_commits_each_step(self):
        root = {
            DEFAULT_VERSION_ROOT: {
                "001_initial": {"id": "001_initial", "applied_at": "2026-01-01T00:00:00Z"},
                "002_add_total": {"id": "002_add_total", "applied_at": "2026-01-02T00:00:00Z"},
            }
        }
        session = mock.Mock()
        calls = []
        first = MigrationStep("001_initial", lambda current: None, lambda current: None)
        second = MigrationStep(
            "002_add_total",
            lambda current: None,
            lambda current: calls.append(("down", current)),
            dependencies=("001_initial",),
        )

        with mock.patch("gemstone_py.persistent_root.PersistentRoot", return_value=root):
            result = downgrade(session, [first, second], target="001_initial")

        self.assertEqual(result.steps, ("002_add_total",))
        self.assertEqual(calls, [("down", session)])
        session.commit.assert_called_once_with()
        self.assertIn("001_initial", root[DEFAULT_VERSION_ROOT])
        self.assertNotIn("002_add_total", root[DEFAULT_VERSION_ROOT])

    def test_downgrade_requires_callback(self):
        root = {
            DEFAULT_VERSION_ROOT: {
                "001_initial": {"id": "001_initial", "applied_at": "2026-01-01T00:00:00Z"}
            }
        }
        session = mock.Mock()
        step = MigrationStep("001_initial", lambda current: None)

        with mock.patch("gemstone_py.persistent_root.PersistentRoot", return_value=root):
            with self.assertRaises(MigrationError):
                downgrade(session, [step], target="base")

        session.commit.assert_not_called()

    def test_current_version_returns_latest_applied_id(self):
        root = {
            DEFAULT_VERSION_ROOT: {
                "001_initial": {"id": "001_initial", "applied_at": "2026-01-01T00:00:00Z"},
                "002_add_total": {"id": "002_add_total", "applied_at": "2026-01-02T00:00:00Z"},
            }
        }

        with mock.patch("gemstone_py.persistent_root.PersistentRoot", return_value=root):
            self.assertEqual(current_version(mock.Mock()), "002_add_total")

    def test_diff_class_compares_local_annotations_to_gemstone_instvars(self):
        @gemstone_class("MigrationDiffBooking")
        class BookingProto:
            status: str
            amount: int

            @property
            def customer(self):
                return None

        session = mock.Mock()
        session.describe_class.return_value = ClassDescription(
            name="MigrationDiffBooking",
            superclasses=["Object"],
            instvars=["status", "legacyField"],
            class_instvars=[],
            instance_count=1,
        )

        class_diff = diff_class(session, local_class=BookingProto)

        self.assertFalse(class_diff.is_current)
        self.assertEqual(class_diff.remote_instvars, ("status", "legacyField"))
        self.assertEqual(class_diff.local_instvars, ("status", "amount", "customer"))
        self.assertEqual(class_diff.missing_instvars, ("amount", "customer"))
        self.assertEqual(class_diff.extra_instvars, ("legacyField",))
        self.assertIn("addInstVarName", class_diff.suggested_upgrade[0])
        self.assertIn("removeInstVarName", class_diff.suggested_downgrade[0])
        session.describe_class.assert_called_once_with("MigrationDiffBooking")

    def test_migration_status_reports_applied_and_pending(self):
        root = {
            DEFAULT_VERSION_ROOT: {
                "001_initial": {"id": "001_initial", "applied_at": "2026-01-01T00:00:00Z"}
            }
        }
        first = MigrationStep("001_initial", lambda current: None)
        second = MigrationStep(
            "002_add_total",
            lambda current: None,
            dependencies=("001_initial",),
        )

        with mock.patch("gemstone_py.persistent_root.PersistentRoot", return_value=root):
            status = migration_status(mock.Mock(), [first, second])

        self.assertEqual(status.current, "001_initial")
        self.assertEqual(status.applied, ("001_initial",))
        self.assertEqual(status.pending, ("002_add_total",))

    def test_validate_migration_state_rejects_unknown_applied_version(self):
        step = MigrationStep("001_initial", lambda current: None)

        with self.assertRaisesRegex(MigrationError, "not present in the local manifest"):
            validate_migration_state([step], {"999_missing": {}})

    def test_validate_migration_state_rejects_checksum_drift(self):
        step = MigrationStep("001_initial", lambda current: None, checksum="local")

        with self.assertRaisesRegex(MigrationError, "checksum mismatch"):
            validate_migration_state([step], {"001_initial": {"checksum": "stored"}})

    def test_scaffold_creates_next_numbered_file(self):
        with TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            (directory / "001_initial.py").write_text("", encoding="utf-8")

            path = scaffold("Add Amount To Booking", directory, dependencies=("001_initial",))

            source = path.read_text(encoding="utf-8")

        self.assertEqual(path.name, "002_add_amount_to_booking.py")
        self.assertIn('id = "002_add_amount_to_booking"', source)
        self.assertIn("dependencies = ('001_initial',)", source)

    def test_scaffold_cli_prints_created_path(self):
        with TemporaryDirectory() as temp_dir:
            with mock.patch("sys.stdout") as stdout:
                result = main(["scaffold", "add status", "--directory", temp_dir])

        self.assertEqual(result, 0)
        stdout.write.assert_any_call(str(Path(temp_dir) / "001_add_status.py"))

    def test_plan_cli_prints_pending_steps(self):
        stream = io.StringIO()
        step = MigrationStep("001_initial", lambda current: None, description="Create shape.")
        session = mock.Mock()
        session_cm = mock.Mock()
        session_cm.__enter__ = mock.Mock(return_value=session)
        session_cm.__exit__ = mock.Mock(return_value=False)

        with mock.patch("gemstone_py.migrations.load_manifest", return_value=(step,)):
            with mock.patch("gemstone_py.migrations._session_from_env", return_value=session_cm):
                with mock.patch("gemstone_py.migrations.applied_migrations", return_value={}):
                    with redirect_stdout(stream):
                        result = main(["plan", "--manifest", "app.migrations.manifest"])

        self.assertEqual(result, 0)
        self.assertIn("upgrade: 1 step(s)", stream.getvalue())
        self.assertIn("001_initial - Create shape.", stream.getvalue())

    def test_status_cli_prints_applied_and_pending_steps(self):
        stream = io.StringIO()
        first = MigrationStep("001_initial", lambda current: None)
        second = MigrationStep(
            "002_add_total",
            lambda current: None,
            dependencies=("001_initial",),
        )
        root = {
            DEFAULT_VERSION_ROOT: {
                "001_initial": {"id": "001_initial", "applied_at": "2026-01-01T00:00:00Z"}
            }
        }
        session = mock.Mock()
        session_cm = mock.Mock()
        session_cm.__enter__ = mock.Mock(return_value=session)
        session_cm.__exit__ = mock.Mock(return_value=False)

        with mock.patch("gemstone_py.migrations.load_manifest", return_value=(first, second)):
            with mock.patch("gemstone_py.migrations._session_from_env", return_value=session_cm):
                with mock.patch("gemstone_py.persistent_root.PersistentRoot", return_value=root):
                    with redirect_stdout(stream):
                        result = main(["status", "--manifest", "app.migrations.manifest"])

        self.assertEqual(result, 0)
        output = stream.getvalue()
        self.assertIn("current: 001_initial", output)
        self.assertIn("applied: 1", output)
        self.assertIn("pending: 1", output)
        self.assertIn("002_add_total", output)

    def test_upgrade_cli_supports_dry_run(self):
        stream = io.StringIO()
        step = MigrationStep("001_initial", lambda current: None)
        session = mock.Mock()
        session_cm = mock.Mock()
        session_cm.__enter__ = mock.Mock(return_value=session)
        session_cm.__exit__ = mock.Mock(return_value=False)

        with mock.patch("gemstone_py.migrations.load_manifest", return_value=(step,)):
            with mock.patch("gemstone_py.migrations._session_from_env", return_value=session_cm):
                with mock.patch("gemstone_py.persistent_root.PersistentRoot", return_value={}):
                    with redirect_stdout(stream):
                        result = main(
                            ["upgrade", "--manifest", "app.migrations.manifest", "--dry-run"]
                        )

        self.assertEqual(result, 0)
        self.assertIn("upgrade dry-run: 1 step(s)", stream.getvalue())
        self.assertIn("001_initial", stream.getvalue())
        session.commit.assert_not_called()

    def test_current_cli_prints_base_for_empty_version_table(self):
        stream = io.StringIO()
        session = mock.Mock()
        session_cm = mock.Mock()
        session_cm.__enter__ = mock.Mock(return_value=session)
        session_cm.__exit__ = mock.Mock(return_value=False)

        with mock.patch("gemstone_py.migrations._session_from_env", return_value=session_cm):
            with mock.patch("gemstone_py.persistent_root.PersistentRoot", return_value={}):
                with redirect_stdout(stream):
                    result = main(["current"])

        self.assertEqual(result, 0)
        self.assertEqual(stream.getvalue(), "base\n")

    def test_diff_class_cli_prints_suggestions(self):
        class BookingProto:
            status: str
            amount: int

        module = types.ModuleType("temp_local_model")
        module.BookingProto = BookingProto
        sys.modules["temp_local_model"] = module
        stream = io.StringIO()
        session = mock.Mock()
        session.describe_class.return_value = ClassDescription(
            name="OkzBooking",
            superclasses=["Object"],
            instvars=["status"],
            class_instvars=[],
            instance_count=1,
        )
        session_cm = mock.Mock()
        session_cm.__enter__ = mock.Mock(return_value=session)
        session_cm.__exit__ = mock.Mock(return_value=False)
        try:
            with mock.patch("gemstone_py.migrations._session_from_env", return_value=session_cm):
                with redirect_stdout(stream):
                    result = main(
                        [
                            "diff-class",
                            "OkzBooking",
                            "--local-class",
                            "temp_local_model:BookingProto",
                        ]
                    )
        finally:
            sys.modules.pop("temp_local_model", None)

        self.assertEqual(result, 0)
        output = stream.getvalue()
        self.assertIn("class: OkzBooking", output)
        self.assertIn("missing instvars: amount", output)
        self.assertIn("suggested upgrade:", output)

    def test_manifest_can_import_migration_module_by_name(self):
        migration_module = types.ModuleType("temp_migration_001")
        migration_module.upgrade = lambda session: None
        manifest_module = types.ModuleType("temp_manifest")
        manifest_module.migrations = ["temp_migration_001"]
        sys.modules["temp_migration_001"] = migration_module
        try:
            steps = load_manifest(manifest_module)
        finally:
            sys.modules.pop("temp_migration_001", None)

        self.assertEqual([step.id for step in steps], ["temp_migration_001"])


if __name__ == "__main__":
    unittest.main()
