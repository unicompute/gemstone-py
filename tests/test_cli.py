import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from gemstone_py import cli


class HelloCliTests(unittest.TestCase):
    def test_hello_main_prints_runtime_details(self):
        stream = io.StringIO()

        with redirect_stdout(stream):
            result = cli.hello_main([])

        self.assertEqual(result, 0)
        output = stream.getvalue()
        self.assertIn("Hello from:", output)
        self.assertIn("Python version:", output)
        self.assertIn("Python engine:", output)

    def test_hello_main_rejects_extra_args(self):
        with self.assertRaises(SystemExit):
            cli.hello_main(["unexpected"])


class AggregateCliTests(unittest.TestCase):
    def test_main_dispatches_hello(self):
        stream = io.StringIO()

        with redirect_stdout(stream):
            result = cli.main(["hello"])

        self.assertEqual(result, 0)
        self.assertIn("Hello from:", stream.getvalue())

    def test_main_lists_curated_examples(self):
        stream = io.StringIO()

        with redirect_stdout(stream):
            result = cli.main(["list"])

        output = stream.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("gemstone-py examples", output)
        self.assertIn("Installed package: gemstone-examples quickstart", output)
        self.assertIn("Source checkout:", output)
        self.assertIn("examples/quickstart.py", output)
        self.assertIn("examples/cookbook/", output)

    def test_main_lists_plan3_feature_map(self):
        stream = io.StringIO()

        with redirect_stdout(stream):
            result = cli.main(["plan3-map"])

        output = stream.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("gemstone-py plan3 feature map", output)
        self.assertIn("Stream 1: Pool + health", output)
        self.assertIn("Stream 11: Bootstrap", output)
        self.assertIn("docs/plan3-feature-map.md", output)

    def test_main_dispatches_smalltalk_demo(self):
        with mock.patch("gemstone_py.cli.run_smalltalk_demo") as run_demo:
            result = cli.main(["smalltalk-demo"])

        self.assertEqual(result, 0)
        run_demo.assert_called_once_with()

    def test_main_dispatches_quickstart(self):
        with mock.patch("gemstone_py.cli.run_quickstart") as run_demo:
            result = cli.main(["quickstart"])

        self.assertEqual(result, 0)
        run_demo.assert_called_once_with()

    def test_main_dispatches_fastapi_example(self):
        with mock.patch("gemstone_py.cli.run_fastapi_example", return_value=0) as run_demo:
            result = cli.main(["fastapi", "--host", "0.0.0.0", "--port", "9001", "--reload"])

        self.assertEqual(result, 0)
        run_demo.assert_called_once_with(
            ["--host", "0.0.0.0", "--port", "9001", "--reload"]
        )

    def test_main_dispatches_litestar_example(self):
        with mock.patch("gemstone_py.cli.run_litestar_example", return_value=0) as run_demo:
            result = cli.main(["litestar", "--host", "0.0.0.0", "--port", "9002", "--reload"])

        self.assertEqual(result, 0)
        run_demo.assert_called_once_with(
            ["--host", "0.0.0.0", "--port", "9002", "--reload"]
        )

    def test_smalltalk_demo_main_rejects_extra_args(self):
        with self.assertRaises(SystemExit):
            cli.smalltalk_demo_main(["unexpected"])


if __name__ == "__main__":
    unittest.main()
