import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout

from gemstone_py import benchmark_baselines


def _report_payload(
    *,
    stone: str = "gs64stone",
    platform: str = "macOS-26-arm64",
    python_version: str = "3.14.3",
    python_implementation: str = "CPython",
    entries: int = 200,
    search_runs: int = 10,
    suites: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at": "2026-04-20T12:00:00Z",
        "stone": stone,
        "host": "localhost",
        "platform": platform,
        "python_version": python_version,
        "python_implementation": python_implementation,
        "entries": entries,
        "search_runs": search_runs,
        "suites": suites or ["persistent_root", "gscollection"],
        "results": [],
    }


def _write_manifest(path: pathlib.Path, baselines: list[str | dict[str, str]]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": benchmark_baselines.BASELINE_MANIFEST_SCHEMA_VERSION,
                "baselines": baselines,
            }
        ),
        encoding="utf-8",
    )


class BenchmarkBaselineSelectionTests(unittest.TestCase):
    def test_select_baseline_returns_exact_metadata_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            candidate_path = temp_path / "candidate.json"
            baseline_path = temp_path / "baseline.json"
            manifest_path = temp_path / "index.json"
            candidate_path.write_text(json.dumps(_report_payload()), encoding="utf-8")
            baseline_path.write_text(json.dumps(_report_payload()), encoding="utf-8")
            _write_manifest(manifest_path, ["baseline.json"])

            report = benchmark_baselines.select_baseline(
                candidate_report_path=str(candidate_path),
                manifest_path=str(manifest_path),
            )

        self.assertTrue(report.comparable)
        self.assertEqual(report.selected_path, str(baseline_path))
        self.assertEqual(report.selected_metadata, report.candidate_metadata)

    def test_select_baseline_returns_none_when_no_environment_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            candidate_path = temp_path / "candidate.json"
            baseline_path = temp_path / "baseline.json"
            manifest_path = temp_path / "index.json"
            candidate_path.write_text(json.dumps(_report_payload()), encoding="utf-8")
            baseline_path.write_text(
                json.dumps(_report_payload(python_version="3.11.9")),
                encoding="utf-8",
            )
            _write_manifest(manifest_path, ["baseline.json"])

            report = benchmark_baselines.select_baseline(
                candidate_report_path=str(candidate_path),
                manifest_path=str(manifest_path),
            )

        self.assertFalse(report.comparable)
        self.assertIsNone(report.selected_path)
        self.assertIn("No committed benchmark baseline matches", report.message)

    def test_select_baseline_normalises_suite_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            candidate_path = temp_path / "candidate.json"
            baseline_path = temp_path / "baseline.json"
            manifest_path = temp_path / "index.json"
            candidate_path.write_text(
                json.dumps(_report_payload(suites=["gstore", "persistent_root"])),
                encoding="utf-8",
            )
            baseline_path.write_text(
                json.dumps(_report_payload(suites=["persistent_root", "gstore"])),
                encoding="utf-8",
            )
            _write_manifest(manifest_path, ["baseline.json"])

            report = benchmark_baselines.select_baseline(
                candidate_report_path=str(candidate_path),
                manifest_path=str(manifest_path),
            )

        self.assertTrue(report.comparable)

    def test_select_baseline_rejects_multiple_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            candidate_path = temp_path / "candidate.json"
            baseline_one_path = temp_path / "baseline-a.json"
            baseline_two_path = temp_path / "baseline-b.json"
            manifest_path = temp_path / "index.json"
            payload = json.dumps(_report_payload())
            candidate_path.write_text(payload, encoding="utf-8")
            baseline_one_path.write_text(payload, encoding="utf-8")
            baseline_two_path.write_text(payload, encoding="utf-8")
            _write_manifest(manifest_path, ["baseline-a.json", "baseline-b.json"])

            with self.assertRaises(SystemExit):
                benchmark_baselines.select_baseline(
                    candidate_report_path=str(candidate_path),
                    manifest_path=str(manifest_path),
                )

    def test_main_emits_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            candidate_path = temp_path / "candidate.json"
            baseline_path = temp_path / "baseline.json"
            manifest_path = temp_path / "index.json"
            candidate_path.write_text(json.dumps(_report_payload()), encoding="utf-8")
            baseline_path.write_text(json.dumps(_report_payload()), encoding="utf-8")
            _write_manifest(manifest_path, ["baseline.json"])

            stream = io.StringIO()
            with redirect_stdout(stream):
                exit_code = benchmark_baselines.main(
                    [
                        str(candidate_path),
                        "--manifest",
                        str(manifest_path),
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stream.getvalue())
        self.assertEqual(
            payload["schema_version"],
            benchmark_baselines.BASELINE_SELECTION_SCHEMA_VERSION,
        )
        self.assertEqual(payload["selected_path"], str(baseline_path))


if __name__ == "__main__":
    unittest.main()
