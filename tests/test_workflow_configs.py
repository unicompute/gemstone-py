import pathlib
import unittest


class WorkflowConfigTests(unittest.TestCase):
    def test_benchmarks_workflow_supports_named_profiles(self) -> None:
        content = pathlib.Path(".github/workflows/benchmarks.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("profile:", content)
        self.assertIn("smoke", content)
        self.assertIn("regression", content)
        self.assertIn(r"Profile: \`${BENCH_PROFILE}\`", content)

    def test_live_workflow_supports_soak_runs(self) -> None:
        content = pathlib.Path(".github/workflows/live.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("run-soak:", content)
        self.assertIn("GS_RUN_LIVE_SOAK", content)

    def test_runner_health_workflow_exists(self) -> None:
        content = pathlib.Path(".github/workflows/runner-health.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("schedule:", content)
        self.assertIn("./scripts/bootstrap_self_hosted_runner.sh --latest-version", content)
        self.assertIn("actions/runners", content)


if __name__ == "__main__":
    unittest.main()
