import os
import pathlib
import unittest


class ReleaseAllScriptTests(unittest.TestCase):
    def test_release_all_script_covers_release_lanes(self):
        script = pathlib.Path("scripts/release_all.sh")
        content = script.read_text(encoding="utf-8")

        self.assertTrue(os.access(script, os.X_OK))
        self.assertIn("scripts/run_ci_checks.sh", content)
        self.assertIn("scripts/run_native_checks.sh", content)
        self.assertIn("gemstone_py.publish_verify", content)
        self.assertIn("npm run test:integration", content)
        self.assertIn("npx vsce package --no-dependencies", content)
        self.assertIn("npx vsce show unicompute.gemstone-py-workbench --json", content)
        self.assertIn("gh release view \"v${gemstone_version}\"", content)
        self.assertIn("gh release view \"vscode-workbench-v${vscode_version}\"", content)
        self.assertIn("SHA256SUMS", content)
        self.assertIn("*.vsix.sha256", pathlib.Path("vscode-gemstone-py-workbench/.gitignore").read_text(encoding="utf-8"))

    def test_makefile_has_release_target(self):
        content = pathlib.Path("Makefile").read_text(encoding="utf-8")

        self.assertIn(".PHONY: release", content)
        self.assertIn("./scripts/release_all.sh", content)


if __name__ == "__main__":
    unittest.main()
