import pathlib
import unittest


class ReleaseTestPyPIWorkflowTests(unittest.TestCase):
    def test_release_testpypi_workflow_exists(self) -> None:
        workflow_path = pathlib.Path(".github/workflows/release-testpypi.yml")
        self.assertTrue(workflow_path.exists())
        content = workflow_path.read_text(encoding="utf-8")
        self.assertIn("Publish to TestPyPI with trusted publishing", content)
        self.assertIn("repository-url: https://test.pypi.org/legacy/", content)
        self.assertIn("verify-testpypi-install", content)
        self.assertIn("Install published package from TestPyPI", content)
        self.assertIn("python -m gemstone_py.api_contract --json", content)


if __name__ == "__main__":
    unittest.main()
