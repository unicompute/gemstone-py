import importlib.util
import io
import os
import sys
import types
import unittest
from contextlib import redirect_stderr
from unittest import mock

from gemstone_py import litestar_example


class LitestarExampleRunnerTests(unittest.TestCase):
    def test_startup_instructions_include_curl_browser_and_expected_output(self):
        output = litestar_example.startup_instructions("http://127.0.0.1:9000")

        self.assertIn("• With that server running, test it from a second terminal.", output)
        self.assertIn("curl -i http://127.0.0.1:9000/", output)
        self.assertIn("HTTP/1.1 200 OK", output)
        self.assertIn(litestar_example.INDEX_BODY_EXAMPLE, output)
        self.assertIn("curl -i http://127.0.0.1:9000/health/gemstone", output)
        self.assertIn('{"result":7}', output)
        self.assertIn("http://127.0.0.1:9000/schema/swagger", output)

    def test_main_reports_missing_optional_dependencies(self):
        stream = io.StringIO()

        with mock.patch(
            "gemstone_py.litestar_example.missing_dependencies",
            return_value=["litestar", "uvicorn"],
        ):
            with mock.patch("gemstone_py.litestar_example.repo_venv_python", return_value=None):
                with redirect_stderr(stream):
                    result = litestar_example.main([])

        self.assertEqual(result, 2)
        output = stream.getvalue()
        self.assertIn("Missing optional Litestar dependencies: litestar, uvicorn", output)
        self.assertIn(f"You are running:\n  {sys.executable}", output)
        self.assertIn("python3 -m venv .venv", output)
        self.assertIn("source .venv/bin/activate", output)
        self.assertIn('python -m pip install -e ".[examples]"', output)
        self.assertIn(f'{sys.executable} -m pip install "gemstone-py[litestar]"', output)

    def test_main_reexecs_with_repo_venv_when_current_python_is_missing_deps(self):
        with mock.patch(
            "gemstone_py.litestar_example.missing_dependencies",
            return_value=["litestar", "uvicorn"],
        ):
            with mock.patch(
                "gemstone_py.litestar_example.repo_venv_python",
                return_value=litestar_example.Path("/repo/.venv/bin/python"),
            ):
                with mock.patch("gemstone_py.litestar_example.os.execv") as execv:
                    result = litestar_example.main(
                        ["--reload"],
                        module_name="examples.litestar.run",
                    )

        self.assertEqual(result, 0)
        execv.assert_called_once_with(
            "/repo/.venv/bin/python",
            [
                "/repo/.venv/bin/python",
                "-m",
                "examples.litestar.run",
                "--reload",
            ],
        )

    def test_main_runs_uvicorn_with_requested_options(self):
        fake_uvicorn = types.SimpleNamespace(run=mock.Mock())

        with mock.patch(
            "gemstone_py.litestar_example.missing_dependencies",
            return_value=[],
        ):
            with mock.patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
                result = litestar_example.main(
                    ["--host", "0.0.0.0", "--port", "9000", "--reload"]
                )

        self.assertEqual(result, 0)
        self.assertEqual(
            os.environ[litestar_example.STARTUP_INSTRUCTIONS_ENV],
            "http://127.0.0.1:9000",
        )
        fake_uvicorn.run.assert_called_once_with(
            "gemstone_py.litestar_example:create_app",
            factory=True,
            host="0.0.0.0",
            port=9000,
            reload=True,
        )


@unittest.skipIf(
    importlib.util.find_spec("litestar") is None,
    "Litestar is not installed",
)
class LitestarExampleAppTests(unittest.TestCase):
    def test_create_app_exposes_route_handlers(self):
        app = litestar_example.create_app()
        self.assertGreaterEqual(len(app.route_handlers), 2)


if __name__ == "__main__":
    unittest.main()
