import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from gemstone_py import benchmarks


class BenchmarkFormattingTests(unittest.TestCase):
    def test_format_results_renders_table(self):
        results = [
            benchmarks.BenchmarkResult(
                suite="persistent_root",
                operation="mapping_keys",
                count=200,
                elapsed_seconds=0.5,
                ops_per_second=400.0,
                note="ok",
            )
        ]

        output = benchmarks.format_results(results)

        self.assertIn("Suite", output)
        self.assertIn("persistent_root", output)
        self.assertIn("mapping_keys", output)
        self.assertIn("400.0", output)


class BenchmarkCliTests(unittest.TestCase):
    def test_main_emits_json(self):
        stream = io.StringIO()
        config = mock.Mock(stone="gs64stone", host="localhost")
        results = [
            benchmarks.BenchmarkResult(
                suite="gstore",
                operation="snapshot_read",
                count=10,
                elapsed_seconds=0.25,
                ops_per_second=40.0,
            )
        ]

        with mock.patch(
            "gemstone_py.benchmarks._benchmark_config",
            return_value=config,
        ):
            with mock.patch(
                "gemstone_py.benchmarks.run_benchmark_suite",
                return_value=results,
            ) as run_suite:
                with redirect_stdout(stream):
                    exit_code = benchmarks.main(["--json", "--suite", "gstore"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stream.getvalue())
        self.assertEqual(
            payload["schema_version"],
            benchmarks.BENCHMARK_REPORT_SCHEMA_VERSION,
        )
        self.assertEqual(payload["stone"], "gs64stone")
        self.assertEqual(payload["results"][0]["suite"], "gstore")
        self.assertEqual(payload["results"][0]["operation"], "snapshot_read")
        run_suite.assert_called_once()

    def test_main_rejects_invalid_entries(self):
        with self.assertRaises(SystemExit):
            benchmarks.main(["--entries", "0"])

    def test_main_defaults_to_all_suites(self):
        config = mock.Mock(stone="gs64stone", host="localhost")
        with mock.patch(
            "gemstone_py.benchmarks._benchmark_config",
            return_value=config,
        ):
            with mock.patch(
                "gemstone_py.benchmarks.run_benchmark_suite",
                return_value=[],
            ) as run_suite:
                with redirect_stdout(io.StringIO()):
                    benchmarks.main([])

        kwargs = run_suite.call_args.kwargs
        self.assertEqual(kwargs["suites"], benchmarks.DEFAULT_SUITES)

    def test_main_writes_json_output_file(self):
        config = mock.Mock(stone="gs64stone", host="localhost")
        results = [
            benchmarks.BenchmarkResult(
                suite="persistent_root",
                operation="mapping_keys",
                count=5,
                elapsed_seconds=0.1,
                ops_per_second=50.0,
            )
        ]

        with mock.patch(
            "gemstone_py.benchmarks._benchmark_config",
            return_value=config,
        ):
            with mock.patch(
                "gemstone_py.benchmarks.run_benchmark_suite",
                return_value=results,
            ):
                with tempfile.TemporaryDirectory() as temp_dir:
                    output_path = pathlib.Path(temp_dir) / "bench.json"
                    exit_code = benchmarks.main(
                        ["--json", "--output", str(output_path)]
                    )

                    self.assertEqual(exit_code, 0)
                    payload = json.loads(output_path.read_text(encoding="utf-8"))
                    self.assertEqual(
                        payload["schema_version"],
                        benchmarks.BENCHMARK_REPORT_SCHEMA_VERSION,
                    )
                    self.assertEqual(payload["results"][0]["operation"], "mapping_keys")


if __name__ == "__main__":
    unittest.main()
