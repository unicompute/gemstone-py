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

    def test_vscode_workbench_live_workflow_verifies_setup_command(self) -> None:
        content = pathlib.Path(".github/workflows/vscode-workbench-live.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("live-verify-workbench-setup:", content)
        self.assertIn("GEMSTONE_PY_LIVE_SETUP_VERIFY: \"1\"", content)
        self.assertIn("GS_STONE_NAME", content)
        self.assertIn("npm run test:integration:live", content)
        self.assertIn("actions/cache@27d5ce7f107fe9357f9df03efb73ab90386fccae", content)
        self.assertIn("vscode-gemstone-py-workbench/.vscode-test", content)

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
        self.assertIn("Verify fast extra native backend from PyPI", content)
        self.assertIn("${PACKAGE_NAME}[fast]==${RELEASE_VERSION}", content)
        self.assertIn("fast-backend.json", content)
        self.assertIn("gci.IMPLEMENTATION", content)
        self.assertIn("native_fast_path_available", content)
        self.assertIn("gemstone-py-post-release-verify", content)

    def test_vscode_extension_workflow_publishes_and_verifies_marketplace_version(self) -> None:
        content = pathlib.Path(".github/workflows/vscode-extension.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("publish-to-marketplace", content)
        self.assertIn("require-domain-verified", content)
        self.assertIn("VSCE_PAT", content)
        self.assertIn("--pat \"${VSCE_PAT}\"", content)
        self.assertIn("Check Marketplace version before publish", content)
        self.assertIn("steps.marketplace-precheck.outputs.visible != 'true'", content)
        self.assertIn("already (exists|published)|version.*(exists|published)", content)
        self.assertIn("Integration-test extension in VS Code", content)
        self.assertIn("xvfb-run -a npm run test:integration", content)
        self.assertIn("Cache VS Code test host", content)
        self.assertIn("actions/cache@27d5ce7f107fe9357f9df03efb73ab90386fccae", content)
        self.assertIn("vscode-gemstone-py-workbench/.vscode-test", content)
        self.assertIn("vscode-test-${{ runner.os }}-${{ runner.arch }}-", content)
        self.assertIn("Generate VSIX checksum", content)
        self.assertIn("*.vsix.sha256", content)
        self.assertIn("CHECKSUM_PATH", content)
        self.assertIn("Verify Marketplace version", content)
        self.assertIn("npx vsce show unicompute.gemstone-py-workbench --json", content)
        self.assertIn("EXPECTED_VERSION", content)
        self.assertIn("REQUIRE_DOMAIN_VERIFIED", content)
        self.assertIn("publisher.isDomainVerified", content)
        self.assertIn("https://unicompute.com", content)
        self.assertIn("versions[0]", content)
        self.assertIn("seq 1 20", content)
        self.assertIn("sleep 60", content)
        self.assertIn(
            "https://marketplace.visualstudio.com/items?itemName=unicompute.gemstone-py-workbench",
            content,
        )
        self.assertIn("gemstone-py Workbench", content)
        self.assertIn("## Changelog", content)
        self.assertIn("vscode-gemstone-py-workbench/CHANGELOG.md", content)

    def test_ci_workflow_smoke_tests_release_wrapper(self) -> None:
        content = pathlib.Path(".github/workflows/ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("release-wrapper-smoke:", content)
        self.assertIn(
            "scripts/release_all.sh --skip-ci --skip-native --skip-public-verify",
            content,
        )
        self.assertIn("actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e", content)
        self.assertIn("node-version: \"24\"", content)
        self.assertIn("SKIP_VSCODE_INTEGRATION: \"1\"", content)

    def test_full_release_verify_workflow_runs_complete_wrapper(self) -> None:
        content = pathlib.Path(".github/workflows/full-release-verify.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("schedule:", content)
        self.assertIn("workflow_dispatch:", content)
        self.assertIn("require-marketplace-domain-verified", content)
        self.assertIn("REQUIRE_VSCODE_DOMAIN_VERIFIED", content)
        self.assertIn("python -m pip install -e .[dev] maturin", content)
        self.assertIn("scripts/release_all.sh", content)
        self.assertNotIn("--skip-ci", content)
        self.assertNotIn("--skip-native", content)
        self.assertNotIn("--skip-public-verify", content)

    def test_release_workflows_use_trusted_publishing(self) -> None:
        testpypi_content = pathlib.Path(
            ".github/workflows/release-testpypi.yml"
        ).read_text(encoding="utf-8")
        pypi_content = pathlib.Path(".github/workflows/release.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("Publish to TestPyPI with trusted publishing", testpypi_content)
        self.assertIn("id-token: write", testpypi_content)
        self.assertIn("repository-url: https://test.pypi.org/legacy/", testpypi_content)
        self.assertNotIn("TEST_PYPI_API_TOKEN", testpypi_content)
        self.assertNotIn("Publish to TestPyPI with API token", testpypi_content)

        self.assertNotIn("PYPI_API_TOKEN", pypi_content)
        self.assertNotIn("Publish to PyPI with API token", pypi_content)
        self.assertIn("Publish to PyPI with trusted publishing", pypi_content)
        self.assertIn("id-token: write", pypi_content)
        self.assertNotIn("password:", pypi_content)
        self.assertNotIn("attestations: false", pypi_content)
        self.assertIn("Generate release checksums", pypi_content)
        self.assertIn("checksums/SHA256SUMS", pypi_content)
        self.assertIn("gemstone-py-release-checksums", pypi_content)

    def test_native_wheels_workflow_exists(self) -> None:
        content = pathlib.Path(".github/workflows/native-wheels.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("branches:", content)
        self.assertIn('"**"', content)
        self.assertIn("gemstone-py-native/**", content)
        self.assertIn("crates/**", content)
        for platform in [
            "linux-x86_64",
            "linux-aarch64",
            "linux-armv7l",
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
        self.assertIn("manylinux,armv7l", content)
        self.assertIn("armv7-unknown-linux-gnueabihf", content)
        self.assertIn("Verify ${{ matrix.platform }} cross-compiled wheel binary", content)
        self.assertIn("EXPECTED_BINARY_MARKERS", content)
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
        self.assertNotIn("TEST_PYPI_API_TOKEN", content)
        self.assertNotIn("PYPI_API_TOKEN", content)
        self.assertNotIn("Publish native wheels to TestPyPI with API token", content)
        self.assertIn("Publish native wheels to TestPyPI with trusted publishing", content)
        self.assertNotIn("Publish native wheels to PyPI with API token", content)
        self.assertIn("Publish native wheels to PyPI with trusted publishing", content)
        self.assertNotIn("attestations: false", content)
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
