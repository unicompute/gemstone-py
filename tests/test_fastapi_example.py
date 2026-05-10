import asyncio
import importlib.util
import io
import os
import sys
import types
import unittest
from contextlib import redirect_stderr
from unittest import mock

from gemstone_py import fastapi_example


class FastApiExampleRunnerTests(unittest.TestCase):
    def test_startup_instructions_include_curl_browser_and_expected_output(self):
        output = fastapi_example.startup_instructions("http://127.0.0.1:9000")

        self.assertIn("• With that server running, test it from a second terminal.", output)
        self.assertIn("curl -i http://127.0.0.1:9000/", output)
        self.assertIn("HTTP/1.1 200 OK", output)
        self.assertIn(fastapi_example.INDEX_BODY_EXAMPLE, output)
        self.assertIn("curl -i http://127.0.0.1:9000/health/gemstone", output)
        self.assertIn('{"result":7}', output)
        self.assertIn("http://127.0.0.1:9000/docs", output)

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
        self.assertEqual(
            os.environ[fastapi_example.STARTUP_INSTRUCTIONS_ENV],
            "http://127.0.0.1:9000",
        )
        fake_uvicorn.run.assert_called_once_with(
            "gemstone_py.fastapi_example:create_app",
            factory=True,
            host="0.0.0.0",
            port=9000,
            reload=True,
        )


@unittest.skipIf(
    importlib.util.find_spec("fastapi") is None,
    "FastAPI is not installed",
)
class FastApiExampleAppTests(unittest.TestCase):
    def test_root_endpoint_points_to_available_routes(self):
        app = fastapi_example.create_app()
        route = next(route for route in app.routes if route.path == "/")

        self.assertEqual(
            asyncio.run(route.endpoint()),
            {
                "name": "gemstone-py FastAPI example",
                "endpoints": {
                    "health": "/health/gemstone",
                    "docs": "/docs",
                    "openapi": "/openapi.json",
                },
            },
        )

    @unittest.skipIf(
        importlib.util.find_spec("httpx") is None,
        "FastAPI TestClient dependencies are not installed",
    )
    def test_http_smoke_routes_include_docs_and_gemstone_health(self):
        from fastapi.testclient import TestClient

        class FakeSession:
            async def eval(self, expression):
                self.expression = expression
                return 7

        def fake_session_dependency(*, config):
            async def dependency():
                yield FakeSession()

            return dependency

        with mock.patch(
            "gemstone_py.aio.fastapi.session_dependency",
            side_effect=fake_session_dependency,
        ):
            app = fastapi_example.create_app()

        with TestClient(app) as client:
            index = client.get("/")
            docs = client.get("/docs")
            health = client.get("/health/gemstone")

        self.assertEqual(index.status_code, 200)
        self.assertEqual(
            index.json(),
            {
                "name": "gemstone-py FastAPI example",
                "endpoints": {
                    "health": "/health/gemstone",
                    "docs": "/docs",
                    "openapi": "/openapi.json",
                },
            },
        )
        self.assertEqual(docs.status_code, 200)
        self.assertIn("text/html", docs.headers["content-type"])
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {"result": 7})


if __name__ == "__main__":
    unittest.main()
