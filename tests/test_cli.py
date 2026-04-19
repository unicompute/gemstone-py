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

    def test_main_dispatches_smalltalk_demo(self):
        with mock.patch("gemstone_py.cli.run_smalltalk_demo") as run_demo:
            result = cli.main(["smalltalk-demo"])

        self.assertEqual(result, 0)
        run_demo.assert_called_once_with()

    def test_smalltalk_demo_main_rejects_extra_args(self):
        with self.assertRaises(SystemExit):
            cli.smalltalk_demo_main(["unexpected"])


if __name__ == "__main__":
    unittest.main()
