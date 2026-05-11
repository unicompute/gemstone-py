import io
import json
import pathlib
import tempfile
import types
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

    def test_measure_with_peak_memory_records_peak_bytes(self):
        result, value = benchmarks._measure_with_peak_memory(
            "gscollection",
            "iter_stream_count",
            3,
            lambda: [index for index in range(3)],
        )

        self.assertEqual(value, [0, 1, 2])
        self.assertEqual(result.count, 3)
        self.assertIn("peak_bytes=", result.note or "")


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
        self.assertIn(payload["gci_backend"], {"ctypes", "native"})
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

    def test_gci_suite_does_not_require_credentials(self):
        stream = io.StringIO()
        config = mock.Mock(stone="gs64stone", host="localhost")
        results = [
            benchmarks.BenchmarkResult(
                suite="gci",
                operation="ctypes_smallint_roundtrip",
                count=10,
                elapsed_seconds=0.1,
                ops_per_second=100.0,
            )
        ]

        with mock.patch(
            "gemstone_py.benchmarks.GemStoneConfig.from_env",
            return_value=config,
        ) as from_env:
            with mock.patch(
                "gemstone_py.benchmarks.run_benchmark_suite",
                return_value=results,
            ):
                with redirect_stdout(stream):
                    benchmarks.main(["--suite", "gci"])

        from_env.assert_called_once_with(require_credentials=False)
        self.assertIn("ctypes_smallint_roundtrip", stream.getvalue())

    def test_gci_benchmark_compares_ctypes_and_native_modules(self):
        def fake_module() -> types.ModuleType:
            module = types.ModuleType("fake_gci")
            module._python_to_smallint = lambda value: (value << 3) | 0x2
            module._smallint_to_python = lambda oop: oop >> 3
            return module

        def import_side_effect(name):
            if name in {"gemstone_py._gci_ctypes", "gemstone_py_native._gci"}:
                return fake_module()
            raise ImportError(name=name)

        with mock.patch(
            "gemstone_py.benchmarks.import_module",
            side_effect=import_side_effect,
        ):
            results = benchmarks.benchmark_gci(mock.Mock(), entries=5)

        self.assertEqual(
            [result.operation for result in results],
            ["ctypes_smallint_roundtrip", "native_smallint_roundtrip"],
        )
        self.assertTrue(all(result.count == 5 for result in results))
        self.assertTrue(all(result.note == "checksum=-499990" for result in results))


if __name__ == "__main__":
    unittest.main()
