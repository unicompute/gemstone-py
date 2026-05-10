import io
import sys
import types
import unittest
from contextlib import redirect_stderr
from unittest import mock

from gemstone_py import fastapi_example


class FastApiExampleRunnerTests(unittest.TestCase):
    def test_main_reports_missing_optional_dependencies(self):
        stream = io.StringIO()

        with mock.patch(
            "gemstone_py.fastapi_example.missing_dependencies",
            return_value=["fastapi", "uvicorn"],
        ):
            with mock.patch("gemstone_py.fastapi_example.repo_venv_python", return_value=None):
                with redirect_stderr(stream):
                    result = fastapi_example.main([])

        self.assertEqual(result, 2)
        output = stream.getvalue()
        self.assertIn("Missing optional FastAPI dependencies: fastapi, uvicorn", output)
        self.assertIn(f"You are running:\n  {sys.executable}", output)
        self.assertIn("python3 -m venv .venv", output)
        self.assertIn("source .venv/bin/activate", output)
        self.assertIn('python -m pip install -e ".[examples]"', output)
        self.assertIn(f'{sys.executable} -m pip install "gemstone-py[fastapi]"', output)

    def test_main_reexecs_with_repo_venv_when_current_python_is_missing_deps(self):
        with mock.patch(
            "gemstone_py.fastapi_example.missing_dependencies",
            return_value=["fastapi", "uvicorn"],
        ):
            with mock.patch(
                "gemstone_py.fastapi_example.repo_venv_python",
                return_value=fastapi_example.Path("/repo/.venv/bin/python"),
            ):
                with mock.patch("gemstone_py.fastapi_example.os.execv") as execv:
                    result = fastapi_example.main(
                        ["--reload"],
                        module_name="examples.fastapi.run",
                    )

        self.assertEqual(result, 0)
        execv.assert_called_once_with(
            "/repo/.venv/bin/python",
            [
                "/repo/.venv/bin/python",
                "-m",
                "examples.fastapi.run",
                "--reload",
            ],
        )

    def test_main_runs_uvicorn_with_requested_options(self):
        fake_uvicorn = types.SimpleNamespace(run=mock.Mock())

        with mock.patch(
            "gemstone_py.fastapi_example.missing_dependencies",
            return_value=[],
        ):
            with mock.patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
                result = fastapi_example.main(
                    ["--host", "0.0.0.0", "--port", "9000", "--reload"]
                )

        self.assertEqual(result, 0)
        fake_uvicorn.run.assert_called_once_with(
            "gemstone_py.fastapi_example:create_app",
            factory=True,
            host="0.0.0.0",
            port=9000,
            reload=True,
        )


if __name__ == "__main__":
    unittest.main()
