import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout

from gemstone_py import benchmark_baseline_register


def _report_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at": "2026-04-20T12:00:00Z",
        "stone": "gs64stone",
        "host": "localhost",
        "platform": "macOS-26-arm64",
        "python_version": "3.14.3",
        "python_implementation": "CPython",
        "entries": 200,
        "search_runs": 10,
        "suites": ["persistent_root", "gscollection"],
        "results": [],
    }


class BenchmarkBaselineRegisterTests(unittest.TestCase):
    def test_register_baseline_copies_external_report_into_manifest_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            report_path = temp_path / "candidate.json"
            manifest_path = temp_path / "benchmarks" / "index.json"
            report_path.write_text(json.dumps(_report_payload()), encoding="utf-8")

            result = benchmark_baseline_register.register_baseline(
                report_path=str(report_path),
                manifest_path=str(manifest_path),
            )

            copied_report = manifest_path.parent / report_path.name
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(copied_report.exists())

            self.assertTrue(result.copied)
            self.assertTrue(result.added_to_manifest)
            self.assertEqual(result.registered_path, report_path.name)
            self.assertEqual(manifest_payload["baselines"], [report_path.name])

    def test_register_baseline_keeps_manifest_entry_stable_when_already_registered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            manifest_path = temp_path / "benchmarks" / "index.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            report_path = manifest_path.parent / "baseline.json"
            report_path.write_text(json.dumps(_report_payload()), encoding="utf-8")
            manifest_path.write_text(
                json.dumps({"schema_version": 1, "baselines": ["baseline.json"]}),
                encoding="utf-8",
            )

            result = benchmark_baseline_register.register_baseline(
                report_path=str(report_path),
                manifest_path=str(manifest_path),
            )
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertFalse(result.copied)
        self.assertFalse(result.added_to_manifest)
        self.assertEqual(manifest_payload["baselines"], ["baseline.json"])

    def test_main_emits_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            report_path = temp_path / "candidate.json"
            manifest_path = temp_path / "benchmarks" / "index.json"
            report_path.write_text(json.dumps(_report_payload()), encoding="utf-8")

            stream = io.StringIO()
            with redirect_stdout(stream):
                exit_code = benchmark_baseline_register.main(
                    [
                        str(report_path),
                        "--manifest",
                        str(manifest_path),
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stream.getvalue())
        self.assertEqual(
            payload["schema_version"],
            benchmark_baseline_register.BASELINE_REGISTRATION_SCHEMA_VERSION,
        )
        self.assertEqual(payload["registered_path"], report_path.name)

    def test_prune_manifest_removes_missing_and_explicit_drop_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            manifest_path = temp_path / "benchmarks" / "index.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            keep_path = manifest_path.parent / "keep.json"
            drop_path = manifest_path.parent / "drop.json"
            keep_path.write_text(json.dumps(_report_payload()), encoding="utf-8")
            drop_path.write_text(json.dumps(_report_payload()), encoding="utf-8")
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "baselines": ["keep.json", "drop.json", "missing.json"],
                    }
                ),
                encoding="utf-8",
            )

            report = benchmark_baseline_register.prune_manifest(
                manifest_path=str(manifest_path),
                drop_paths=["drop.json"],
            )
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(sorted(report.removed_paths), ["drop.json", "missing.json"])
        self.assertEqual(report.remaining_paths, ["keep.json"])
        self.assertEqual(manifest_payload["baselines"], ["keep.json"])

    def test_main_supports_manifest_maintenance_without_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = pathlib.Path(temp_dir)
            manifest_path = temp_path / "benchmarks" / "index.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            drop_path = manifest_path.parent / "drop.json"
            drop_path.write_text(json.dumps(_report_payload()), encoding="utf-8")
            manifest_path.write_text(
                json.dumps({"schema_version": 1, "baselines": ["drop.json"]}),
                encoding="utf-8",
            )

            stream = io.StringIO()
            with redirect_stdout(stream):
                exit_code = benchmark_baseline_register.main(
                    [
                        "--manifest",
                        str(manifest_path),
                        "--drop-path",
                        "drop.json",
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["removed_paths"], ["drop.json"])


if __name__ == "__main__":
    unittest.main()
