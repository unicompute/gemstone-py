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
            with redirect_stderr(stream):
                result = fastapi_example.main([])

        self.assertEqual(result, 2)
        output = stream.getvalue()
        self.assertIn("Missing optional FastAPI dependencies: fastapi, uvicorn", output)
        self.assertIn(f'{sys.executable} -m pip install "gemstone-py[fastapi]"', output)
        self.assertIn(f'{sys.executable} -m pip install -e ".[examples]"', output)

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
