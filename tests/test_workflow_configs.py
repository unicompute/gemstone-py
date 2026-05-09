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

    def test_native_wheels_workflow_exists(self) -> None:
        content = pathlib.Path(".github/workflows/native-wheels.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("gemstone-py-native/**", content)
        for platform in [
            "linux-x86_64",
            "linux-aarch64",
            "macos-x86_64",
            "macos-aarch64",
            "windows-x86_64",
            "windows-aarch64",
        ]:
            self.assertIn(platform, content)
        self.assertIn("release-tag:", content)
        self.assertIn("normalize_native_tag", content)
        self.assertIn("gemstone-py-native-", content)
        self.assertIn("Manual native PyPI publish requires the release-tag input.", content)
        self.assertIn("does not match project.version", content)
        self.assertIn("publish-to-testpypi", content)
        self.assertIn("publish-to-pypi", content)
        self.assertIn("wheel-markers:", content)
        self.assertIn("manylinux,x86_64", content)
        self.assertIn("manylinux,aarch64", content)
        self.assertIn("macosx,x86_64", content)
        self.assertIn("macosx,arm64", content)
        self.assertIn("win_amd64", content)
        self.assertIn("win_arm64", content)
        self.assertIn("windows-11-arm", content)
        self.assertIn("Verify ${{ matrix.platform }} wheel artifact", content)
        self.assertIn("EXPECTED_WHEEL_MARKERS", content)
        self.assertIn("Verify ${{ matrix.platform }} wheel import", content)
        self.assertIn("native-wheel-smoke", content)
        self.assertIn("gemstone-py-native-sdist", content)
        self.assertIn("Verify native TestPyPI publish artifacts", content)
        self.assertIn("Verify native PyPI publish artifacts", content)
        self.assertIn("--native-artifacts-dir", content)
        self.assertIn("native-publish-artifacts.json", content)
        self.assertIn("maturin sdist", content)
        self.assertIn("Verify native sdist builds a wheel", content)
        self.assertIn("tarfile.open", content)
        self.assertIn('"maturin"', content)
        self.assertIn("sdist-src", content)
        self.assertIn("native-sdist-build-smoke", content)
        self.assertIn("Publish native wheels to TestPyPI with trusted publishing", content)
        self.assertIn("Publish native wheels to PyPI with trusted publishing", content)
        self.assertIn("verify-testpypi-install", content)
        self.assertIn("verify-pypi-install", content)
        self.assertIn("Verify TestPyPI native files and metadata", content)
        self.assertIn("Verify PyPI native files and metadata", content)
        self.assertIn("https://test.pypi.org/pypi/gemstone-py-native/json", content)
        self.assertIn("https://pypi.org/pypi/gemstone-py-native/json", content)
        self.assertIn("python -m gemstone_py.release_metadata", content)
        self.assertIn("--native-pypi-json-url", content)
        self.assertIn("--native-version", content)
        self.assertIn("native-pypi-release.json", content)
        self.assertIn("gemstone-py-native-testpypi-verify", content)
        self.assertIn("gemstone-py-native-pypi-verify", content)
        self.assertIn("gemstone-py-native==${NATIVE_VERSION}", content)
        self.assertIn("gci.IMPLEMENTATION != \"native\"", content)
        self.assertIn("maturin[zig]", content)
        self.assertIn("--zig", content)
        self.assertIn("--compatibility pypi", content)
        self.assertIn("maturin build", content)
        self.assertIn("upload-artifact", content)


if __name__ == "__main__":
    unittest.main()
