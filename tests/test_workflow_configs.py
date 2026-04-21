import pathlib
import re
import unittest


class WorkflowConfigTests(unittest.TestCase):
    def test_workflows_use_sha_pinned_external_actions(self) -> None:
        uses_pattern = re.compile(
            r"^\s*-\s+uses:\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([^\s#]+)",
            re.MULTILINE,
        )
        for path in pathlib.Path(".github/workflows").glob("*.yml"):
            content = path.read_text(encoding="utf-8")
            for action, ref in uses_pattern.findall(content):
                self.assertRegex(
                    ref,
                    r"^[0-9a-f]{40}$",
                    msg=f"{path} uses unpinned action {action}@{ref}",
                )

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

    def test_post_release_verify_workflow_exists(self) -> None:
        content = pathlib.Path(".github/workflows/post-release-verify.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("release-version:", content)
        self.assertIn("pypi-release.json", content)
        self.assertIn("gemstone-py-post-release-verify", content)


if __name__ == "__main__":
    unittest.main()
