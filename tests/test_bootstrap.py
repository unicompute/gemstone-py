import io
import unittest
from contextlib import redirect_stdout

from gemstone_py import bootstrap


class FakeSession:
    def __init__(self, present_keys=None):
        self.present_keys = set(present_keys or [])
        self.evals = []

    def eval(self, source):
        self.evals.append(source)
        if source.startswith("UserGlobals includesKey: #"):
            key = source.rsplit("#", 1)[1]
            return key in self.present_keys
        if source == "ObjectLogEntry objectLog notNil":
            return True
        if source == bootstrap.bootstrap_source():
            self.present_keys.update(
                {
                    bootstrap.BOOTSTRAP_MARKER_KEY,
                    "GStoreRoot",
                    "GSQueryRoot",
                }
            )
            return (
                "gemstone-py bootstrap 1 created: "
                "#('GStoreRoot' 'GSQueryRoot' 'GemstonePyBootstrapVersion')"
            )
        raise AssertionError(f"Unexpected eval source: {source!r}")


class BootstrapSourceTests(unittest.TestCase):
    def test_bootstrap_source_contains_current_artifact_keys(self):
        source = bootstrap.bootstrap_source()

        self.assertIn("UserGlobals at: #GStoreRoot", source)
        self.assertIn("StringKeyValueDictionary new", source)
        self.assertIn("UserGlobals at: #GSQueryRoot", source)
        self.assertIn("Dictionary new", source)
        self.assertIn("GemstonePyBootstrapVersion", source)


class BootstrapTests(unittest.TestCase):
    def test_audit_reports_user_global_and_builtin_artifacts(self):
        session = FakeSession({"GStoreRoot"})

        statuses = bootstrap.audit(session)

        by_name = {status.artifact.name: status.present for status in statuses}
        self.assertFalse(by_name[bootstrap.BOOTSTRAP_MARKER_KEY])
        self.assertTrue(by_name["GStoreRoot"])
        self.assertFalse(by_name["GSQueryRoot"])
        self.assertTrue(by_name["ObjectLogEntry objectLog"])

    def test_bootstrap_applies_packaged_source_and_reports_created_keys(self):
        session = FakeSession()

        result = bootstrap.bootstrap(session)

        self.assertTrue(result.applied)
        self.assertEqual(
            result.created_keys,
            (bootstrap.BOOTSTRAP_MARKER_KEY, "GStoreRoot", "GSQueryRoot"),
        )
        self.assertIn(bootstrap.bootstrap_source(), session.evals)
        after = {status.artifact.name: status.present for status in result.after}
        self.assertTrue(after[bootstrap.BOOTSTRAP_MARKER_KEY])
        self.assertTrue(after["GStoreRoot"])
        self.assertTrue(after["GSQueryRoot"])

    def test_bootstrap_dry_run_audits_without_evaluating_packaged_source(self):
        session = FakeSession({"GStoreRoot"})

        result = bootstrap.bootstrap(session, dry_run=True)

        self.assertFalse(result.applied)
        self.assertEqual(result.created_keys, ())
        self.assertNotIn(bootstrap.bootstrap_source(), session.evals)
        self.assertEqual(result.before, result.after)


class BootstrapCliTests(unittest.TestCase):
    def test_print_source_does_not_require_environment(self):
        stream = io.StringIO()

        with redirect_stdout(stream):
            exit_code = bootstrap.main(["--print-source"])

        self.assertEqual(exit_code, 0)
        self.assertIn("GStoreRoot", stream.getvalue())

    def test_dry_run_prints_plan_and_source_without_environment(self):
        stream = io.StringIO()

        with redirect_stdout(stream):
            exit_code = bootstrap.main(["--dry-run"])

        self.assertEqual(exit_code, 0)
        output = stream.getvalue()
        self.assertIn("bootstrap dry run", output)
        self.assertIn("UserGlobals at: #GStoreRoot", output)
        self.assertIn("ObjectLogEntry objectLog", output)


if __name__ == "__main__":
    unittest.main()
