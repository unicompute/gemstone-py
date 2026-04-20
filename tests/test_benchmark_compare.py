import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout

from gemstone_py import benchmark_compare


def _report_payload(
    *,
    ops_per_second: float = 10.0,
    suite: str = "persistent_root",
    operation: str = "mapping_keys",
    schema_version: int = 1,
    stone: str = "gs64stone",
    platform: str = "macOS-14-arm64",
    python_version: str = "3.11.9",
    python_implementation: str = "CPython",
    entries: int = 200,
    search_runs: int = 10,
    suites: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "generated_at": "2026-04-20T12:00:00Z",
        "stone": stone,
        "platform": platform,
        "python_version": python_version,
        "python_implementation": python_implementation,
        "entries": entries,
        "search_runs": search_runs,
        "suites": suites or [suite],
        "results": [
            {
                "suite": suite,
                "operation": operation,
                "count": 10,
                "elapsed_seconds": 1.0,
                "ops_per_second": ops_per_second,
                "note": None,
            }
        ],
    }


class BenchmarkCompareTests(unittest.TestCase):
    def test_compare_reports_marks_improvement(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_path = pathlib.Path(temp_dir) / "baseline.json"
            candidate_path = pathlib.Path(temp_dir) / "candidate.json"
            baseline_path.write_text(
                json.dumps(_report_payload(ops_per_second=10.0)),
                encoding="utf-8",
            )
            candidate_path.write_text(
                json.dumps(_report_payload(ops_per_second=12.5)),
                encoding="utf-8",
            )

            report = benchmark_compare.compare_reports(
                baseline_path=str(baseline_path),
                candidate_path=str(candidate_path),
            )

        self.assertEqual(
            report.schema_version,
            benchmark_compare.BENCHMARK_COMPARISON_SCHEMA_VERSION,
        )
        self.assertTrue(report.comparable)
        self.assertEqual(report.compatibility_issues, [])
        self.assertEqual(len(report.rows), 1)
        row = report.rows[0]
        self.assertEqual(row.status, "improved")
        self.assertEqual(row.delta_ops_per_second, 2.5)
        self.assertEqual(row.delta_percent, 25.0)

    def test_compare_reports_marks_metadata_mismatch_non_comparable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_path = pathlib.Path(temp_dir) / "baseline.json"
            candidate_path = pathlib.Path(temp_dir) / "candidate.json"
            baseline_path.write_text(
                json.dumps(_report_payload(platform="macOS-14-arm64")),
                encoding="utf-8",
            )
            candidate_path.write_text(
                json.dumps(_report_payload(platform="Linux-x86_64")),
                encoding="utf-8",
            )

            report = benchmark_compare.compare_reports(
                baseline_path=str(baseline_path),
                candidate_path=str(candidate_path),
                max_regression_pct=10.0,
            )

        self.assertFalse(report.comparable)
        self.assertIn("platform differs", report.compatibility_issues[0])
        self.assertFalse(report.threshold_exceeded)
        self.assertEqual(report.threshold_exceeded_operations, [])

    def test_compare_reports_normalises_suite_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_path = pathlib.Path(temp_dir) / "baseline.json"
            candidate_path = pathlib.Path(temp_dir) / "candidate.json"
            baseline_path.write_text(
                json.dumps(_report_payload(suites=["persistent_root", "gstore"])),
                encoding="utf-8",
            )
            candidate_path.write_text(
                json.dumps(_report_payload(suites=["gstore", "persistent_root"])),
                encoding="utf-8",
            )

            report = benchmark_compare.compare_reports(
                baseline_path=str(baseline_path),
                candidate_path=str(candidate_path),
            )

        self.assertTrue(report.comparable)

    def test_format_comparison_renders_table(self):
        report = benchmark_compare.BenchmarkComparisonReport(
            schema_version=benchmark_compare.BENCHMARK_COMPARISON_SCHEMA_VERSION,
            baseline_path="baseline.json",
            candidate_path="candidate.json",
            comparable=True,
            compatibility_issues=[],
            max_regression_pct=10.0,
            suite_regression_pcts={},
            operation_regression_pcts={},
            threshold_exceeded=True,
            threshold_exceeded_operations=["gstore/snapshot_read"],
            baseline_metadata={"stone": "gs64stone"},
            candidate_metadata={"stone": "gs64stone"},
            baseline_generated_at="2026-04-20T12:00:00Z",
            candidate_generated_at="2026-04-20T12:05:00Z",
            baseline_stone="gs64stone",
            candidate_stone="gs64stone",
            rows=[
                benchmark_compare.BenchmarkComparisonRow(
                    suite="gstore",
                    operation="snapshot_read",
                    status="regressed",
                    baseline_ops_per_second=100.0,
                    candidate_ops_per_second=80.0,
                    delta_ops_per_second=-20.0,
                    delta_percent=-20.0,
                    baseline_count=10,
                    candidate_count=10,
                )
            ],
        )

        output = benchmark_compare.format_comparison(report)

        self.assertIn("Baseline: baseline.json", output)
        self.assertIn("Candidate: candidate.json", output)
        self.assertIn("Comparable: yes", output)
        self.assertIn("Regression Threshold: 10.0% (exceeded)", output)
        self.assertIn("snapshot_read", output)
        self.assertIn("regressed", output)

    def test_compare_reports_honours_suite_threshold_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_path = pathlib.Path(temp_dir) / "baseline.json"
            candidate_path = pathlib.Path(temp_dir) / "candidate.json"
            baseline_path.write_text(
                json.dumps(_report_payload(ops_per_second=10.0)),
                encoding="utf-8",
            )
            candidate_path.write_text(
                json.dumps(_report_payload(ops_per_second=9.0)),
                encoding="utf-8",
            )

            report = benchmark_compare.compare_reports(
                baseline_path=str(baseline_path),
                candidate_path=str(candidate_path),
                max_regression_pct=5.0,
                suite_regression_pcts={"persistent_root": 15.0},
            )

        self.assertTrue(report.comparable)
        self.assertFalse(report.threshold_exceeded)
        self.assertEqual(report.rows[0].applied_regression_pct, 15.0)
        self.assertEqual(report.rows[0].threshold_scope, "suite")

    def test_compare_reports_honours_operation_threshold_precedence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_path = pathlib.Path(temp_dir) / "baseline.json"
            candidate_path = pathlib.Path(temp_dir) / "candidate.json"
            baseline_path.write_text(
                json.dumps(_report_payload(ops_per_second=10.0)),
                encoding="utf-8",
            )
            candidate_path.write_text(
                json.dumps(_report_payload(ops_per_second=9.0)),
                encoding="utf-8",
            )

            report = benchmark_compare.compare_reports(
                baseline_path=str(baseline_path),
                candidate_path=str(candidate_path),
                max_regression_pct=15.0,
                suite_regression_pcts={"persistent_root": 12.0},
                operation_regression_pcts={"persistent_root/mapping_keys": 5.0},
            )

        self.assertTrue(report.comparable)
        self.assertTrue(report.threshold_exceeded)
        self.assertEqual(
            report.threshold_exceeded_operations,
            ["persistent_root/mapping_keys"],
        )
        self.assertEqual(report.rows[0].applied_regression_pct, 5.0)
        self.assertEqual(report.rows[0].threshold_scope, "operation")

    def test_main_emits_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_path = pathlib.Path(temp_dir) / "baseline.json"
            candidate_path = pathlib.Path(temp_dir) / "candidate.json"
            baseline_path.write_text(
                json.dumps(_report_payload(ops_per_second=10.0)),
                encoding="utf-8",
            )
            candidate_path.write_text(
                json.dumps(_report_payload(ops_per_second=9.0)),
                encoding="utf-8",
            )

            stream = io.StringIO()
            with redirect_stdout(stream):
                exit_code = benchmark_compare.main(
                    [str(baseline_path), str(candidate_path), "--json"]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stream.getvalue())
        self.assertEqual(
            payload["schema_version"],
            benchmark_compare.BENCHMARK_COMPARISON_SCHEMA_VERSION,
        )
        self.assertTrue(payload["comparable"])
        self.assertEqual(payload["rows"][0]["status"], "regressed")

    def test_main_writes_output_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_path = pathlib.Path(temp_dir) / "baseline.json"
            candidate_path = pathlib.Path(temp_dir) / "candidate.json"
            output_path = pathlib.Path(temp_dir) / "compare.json"
            baseline_path.write_text(
                json.dumps(_report_payload(ops_per_second=10.0)),
                encoding="utf-8",
            )
            candidate_path.write_text(
                json.dumps(_report_payload(ops_per_second=11.0)),
                encoding="utf-8",
            )

            exit_code = benchmark_compare.main(
                [
                    str(baseline_path),
                    str(candidate_path),
                    "--json",
                    "--output",
                    str(output_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["rows"][0]["status"], "improved")

    def test_main_returns_threshold_exit_code_for_comparable_regression(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_path = pathlib.Path(temp_dir) / "baseline.json"
            candidate_path = pathlib.Path(temp_dir) / "candidate.json"
            baseline_path.write_text(
                json.dumps(_report_payload(ops_per_second=10.0)),
                encoding="utf-8",
            )
            candidate_path.write_text(
                json.dumps(_report_payload(ops_per_second=8.0)),
                encoding="utf-8",
            )

            exit_code = benchmark_compare.main(
                [
                    str(baseline_path),
                    str(candidate_path),
                    "--max-regression-pct",
                    "10",
                ]
            )

        self.assertEqual(exit_code, 2)

    def test_main_accepts_threshold_overrides(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_path = pathlib.Path(temp_dir) / "baseline.json"
            candidate_path = pathlib.Path(temp_dir) / "candidate.json"
            baseline_path.write_text(
                json.dumps(_report_payload(ops_per_second=10.0)),
                encoding="utf-8",
            )
            candidate_path.write_text(
                json.dumps(_report_payload(ops_per_second=9.0)),
                encoding="utf-8",
            )

            exit_code = benchmark_compare.main(
                [
                    str(baseline_path),
                    str(candidate_path),
                    "--max-regression-pct",
                    "20",
                    "--suite-threshold",
                    "persistent_root=15",
                    "--operation-threshold",
                    "persistent_root/mapping_keys=5",
                ]
            )

        self.assertEqual(exit_code, 2)

    def test_main_skips_threshold_on_metadata_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_path = pathlib.Path(temp_dir) / "baseline.json"
            candidate_path = pathlib.Path(temp_dir) / "candidate.json"
            baseline_path.write_text(
                json.dumps(_report_payload(platform="macOS-14-arm64")),
                encoding="utf-8",
            )
            candidate_path.write_text(
                json.dumps(_report_payload(platform="Linux-x86_64", ops_per_second=8.0)),
                encoding="utf-8",
            )

            exit_code = benchmark_compare.main(
                [
                    str(baseline_path),
                    str(candidate_path),
                    "--max-regression-pct",
                    "10",
                ]
            )

        self.assertEqual(exit_code, 0)

    def test_main_rejects_unknown_schema_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            baseline_path = pathlib.Path(temp_dir) / "baseline.json"
            candidate_path = pathlib.Path(temp_dir) / "candidate.json"
            baseline_path.write_text(
                json.dumps(_report_payload(schema_version=99)),
                encoding="utf-8",
            )
            candidate_path.write_text(
                json.dumps(_report_payload()),
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit):
                benchmark_compare.main([str(baseline_path), str(candidate_path)])


if __name__ == "__main__":
    unittest.main()
