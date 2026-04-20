"""Public API contract checks for installed gemstone-py artifacts."""

from __future__ import annotations

import argparse
import io
import json
import os
from contextlib import redirect_stdout
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Sequence

CORE_EXPORTS: dict[str, tuple[str, str]] = {
    "GemStoneConfig": ("gemstone_py.client", "GemStoneConfig"),
    "GemStoneConfigurationError": ("gemstone_py.client", "GemStoneConfigurationError"),
    "GemStoneError": ("gemstone_py.client", "GemStoneError"),
    "GemStoneSession": ("gemstone_py.client", "GemStoneSession"),
    "OopRef": ("gemstone_py.client", "OopRef"),
    "TransactionPolicy": ("gemstone_py.client", "TransactionPolicy"),
    "connect": ("gemstone_py.client", "connect"),
    "GemStoneSessionPool": ("gemstone_py.web", "GemStoneSessionPool"),
    "GemStoneSessionProvider": ("gemstone_py.web", "GemStoneSessionProvider"),
    "GemStoneSessionProviderEvent": ("gemstone_py.web", "GemStoneSessionProviderEvent"),
    "GemStoneSessionProviderSnapshot": (
        "gemstone_py.web",
        "GemStoneSessionProviderSnapshot",
    ),
    "GemStoneThreadLocalSessionProvider": (
        "gemstone_py.web",
        "GemStoneThreadLocalSessionProvider",
    ),
    "close_flask_request_session_provider": (
        "gemstone_py.web",
        "close_flask_request_session_provider",
    ),
    "current_flask_request_session": ("gemstone_py.web", "current_flask_request_session"),
    "finalize_flask_request_session": ("gemstone_py.web", "finalize_flask_request_session"),
    "flask_request_session_provider": ("gemstone_py.web", "flask_request_session_provider"),
    "flask_request_session_provider_metrics": (
        "gemstone_py.web",
        "flask_request_session_provider_metrics",
    ),
    "flask_request_session_provider_snapshot": (
        "gemstone_py.web",
        "flask_request_session_provider_snapshot",
    ),
    "install_flask_request_session": ("gemstone_py.web", "install_flask_request_session"),
    "session_scope": ("gemstone_py.web", "session_scope"),
    "warm_flask_request_session_provider": (
        "gemstone_py.web",
        "warm_flask_request_session_provider",
    ),
    "GemStoneSessionFacade": ("gemstone_py.session_facade", "GemStoneSessionFacade"),
    "PersistentRoot": ("gemstone_py.persistent_root", "PersistentRoot"),
}

MODULE_EXPORTS: dict[str, str] = {
    "benchmark_baseline_register": "gemstone_py.benchmark_baseline_register",
    "benchmark_baselines": "gemstone_py.benchmark_baselines",
    "benchmark_compare": "gemstone_py.benchmark_compare",
    "release_metadata": "gemstone_py.release_metadata",
    "session_facade": "gemstone_py.session_facade",
}


def validate_public_api() -> list[str]:
    """Validate the documented gemstone_py package export surface."""
    pkg = import_module("gemstone_py")
    validated: list[str] = []

    for name, (module_name, attr_name) in CORE_EXPORTS.items():
        expected = getattr(import_module(module_name), attr_name)
        actual = getattr(pkg, name)
        if actual is not expected:
            raise AssertionError(
                f"gemstone_py.{name} does not resolve to {module_name}.{attr_name}"
            )
        validated.append(name)

    for name, module_name in MODULE_EXPORTS.items():
        expected_module = import_module(module_name)
        actual_module = getattr(pkg, name)
        if actual_module is not expected_module:
            raise AssertionError(f"gemstone_py.{name} does not resolve to {module_name}")
        validated.append(name)

    package_all = getattr(pkg, "__all__")
    for name in CORE_EXPORTS:
        if name not in package_all:
            raise AssertionError(f"gemstone_py.__all__ is missing {name}")
    for name in MODULE_EXPORTS:
        if name not in package_all:
            raise AssertionError(f"gemstone_py.__all__ is missing {name}")

    return sorted(validated)


def validate_public_api_behaviors() -> list[str]:
    """Validate documented non-live behaviors for the installed package."""
    validated: list[str] = []

    gemstone_py = import_module("gemstone_py")
    client = import_module("gemstone_py.client")
    benchmark_compare = import_module("gemstone_py.benchmark_compare")
    benchmark_baselines = import_module("gemstone_py.benchmark_baselines")
    release_metadata = import_module("gemstone_py.release_metadata")
    baseline_register = import_module("gemstone_py.benchmark_baseline_register")

    transaction_policy = gemstone_py.TransactionPolicy.coerce("manual")
    if transaction_policy is not gemstone_py.TransactionPolicy.MANUAL:
        raise AssertionError("TransactionPolicy.coerce('manual') did not return MANUAL")
    validated.append("transaction_policy_coerce")

    original_env = {
        key: os.environ.get(key)
        for key in ("GS_STONE", "GS_HOST", "GS_USERNAME", "GS_PASSWORD")
    }
    try:
        os.environ["GS_STONE"] = "artifactStone"
        os.environ["GS_HOST"] = "artifact.example"
        os.environ.pop("GS_USERNAME", None)
        os.environ.pop("GS_PASSWORD", None)
        config = gemstone_py.GemStoneConfig.from_env(require_credentials=False)
        if config.stone != "artifactStone" or config.host != "artifact.example":
            raise AssertionError("GemStoneConfig.from_env did not read the environment")
        try:
            gemstone_py.GemStoneConfig().require_credentials()
        except gemstone_py.GemStoneConfigurationError:
            pass
        else:
            raise AssertionError("GemStoneConfig.require_credentials should fail without creds")
    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    validated.append("gemstone_config_env")

    class _StubSession:
        def __init__(self) -> None:
            self.calls: list[tuple[int, str, tuple[object, ...]]] = []

        def perform(self, receiver: int, selector: str, *args: object) -> str:
            self.calls.append((receiver, selector, args))
            return "printStringResult"

    stub_session = _StubSession()
    oop_ref = client.OopRef(0xABC, stub_session)
    if oop_ref.print_string() != "printStringResult":
        raise AssertionError("OopRef.print_string did not delegate to session.perform")
    if stub_session.calls != [(0xABC, "printString", ())]:
        raise AssertionError("OopRef.print_string called session.perform incorrectly")
    validated.append("oopref_print_string")

    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        report_path = temp_path / "candidate.json"
        manifest_path = temp_path / "benchmarks" / "index.json"
        report_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "generated_at": "2026-04-20T12:00:00Z",
                    "stone": "gs64stone",
                    "host": "localhost",
                    "platform": "macOS-26-arm64",
                    "python_version": "3.14.3",
                    "python_implementation": "CPython",
                    "entries": 200,
                    "search_runs": 10,
                    "suites": ["persistent_root"],
                    "results": [],
                }
            ),
            encoding="utf-8",
        )
        registration = baseline_register.register_baseline(
            report_path=str(report_path),
            manifest_path=str(manifest_path),
            copy_to="accepted.json",
        )
        if registration.registered_path != "accepted.json":
            raise AssertionError("benchmark baseline registration used an unexpected path")
        maintenance = baseline_register.prune_manifest(
            manifest_path=str(manifest_path),
            drop_paths=["accepted.json"],
        )
        if maintenance.remaining_paths:
            raise AssertionError("benchmark baseline prune/drop did not update the manifest")
    validated.append("benchmark_baseline_lifecycle")

    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        report_path = temp_path / "candidate.json"
        manifest_path = temp_path / "benchmarks" / "index.json"
        report_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "generated_at": "2026-04-20T12:00:00Z",
                    "stone": "gs64stone",
                    "host": "localhost",
                    "platform": "macOS-26-arm64",
                    "python_version": "3.14.3",
                    "python_implementation": "CPython",
                    "entries": 200,
                    "search_runs": 10,
                    "suites": ["persistent_root"],
                    "results": [],
                }
            ),
            encoding="utf-8",
        )
        stream = io.StringIO()
        with redirect_stdout(stream):
            exit_code = baseline_register.main(
                [
                    str(report_path),
                    "--manifest",
                    str(manifest_path),
                    "--copy-to",
                    "accepted.json",
                    "--drop-path",
                    "accepted.json",
                    "--json",
                ]
            )
        if exit_code != 0:
            raise AssertionError("benchmark baseline register CLI returned a non-zero exit code")
        payload = json.loads(stream.getvalue())
        if sorted(payload.keys()) != ["maintenance", "registration"]:
            raise AssertionError(
                "benchmark baseline register CLI did not emit the combined JSON shape"
            )
    validated.append("benchmark_baseline_register_cli_json")

    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        baseline_path = temp_path / "baseline.json"
        candidate_path = temp_path / "candidate.json"
        manifest_path = temp_path / "benchmarks" / "index.json"
        baseline_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "generated_at": "2026-04-20T12:00:00Z",
                    "stone": "gs64stone",
                    "platform": "macOS-26-arm64",
                    "python_version": "3.14.3",
                    "python_implementation": "CPython",
                    "entries": 200,
                    "search_runs": 10,
                    "suites": ["persistent_root"],
                    "results": [
                        {
                            "suite": "persistent_root",
                            "operation": "mapping_keys",
                            "count": 10,
                            "elapsed_seconds": 1.0,
                            "ops_per_second": 10.0,
                            "note": None,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        candidate_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "generated_at": "2026-04-20T12:05:00Z",
                    "stone": "gs64stone",
                    "platform": "macOS-26-arm64",
                    "python_version": "3.14.3",
                    "python_implementation": "CPython",
                    "entries": 200,
                    "search_runs": 10,
                    "suites": ["persistent_root"],
                    "results": [
                        {
                            "suite": "persistent_root",
                            "operation": "mapping_keys",
                            "count": 10,
                            "elapsed_seconds": 1.0,
                            "ops_per_second": 9.0,
                            "note": None,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        baseline_register.register_baseline(
            report_path=str(baseline_path),
            manifest_path=str(manifest_path),
            copy_to="accepted.json",
        )
        selection = benchmark_baselines.select_baseline(
            candidate_report_path=str(candidate_path),
            manifest_path=str(manifest_path),
        )
        if not selection.comparable or not selection.selected_path:
            raise AssertionError("benchmark baseline selection did not find the accepted report")
        comparison = benchmark_compare.compare_reports(
            baseline_path=str(baseline_path),
            candidate_path=str(candidate_path),
            max_regression_pct=20.0,
            suite_regression_pcts={"persistent_root": 15.0},
            operation_regression_pcts={"persistent_root/mapping_keys": 5.0},
        )
        if not comparison.threshold_exceeded:
            raise AssertionError(
                "benchmark compare thresholds did not flag the override regression"
            )
        if comparison.rows[0].threshold_scope != "operation":
            raise AssertionError("operation threshold did not override suite/global thresholds")
    validated.append("benchmark_compare_thresholds")
    validated.append("benchmark_baseline_selection")

    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        baseline_path = temp_path / "baseline.json"
        candidate_path = temp_path / "candidate.json"
        manifest_path = temp_path / "benchmarks" / "index.json"
        baseline_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "generated_at": "2026-04-20T12:00:00Z",
                    "stone": "gs64stone",
                    "platform": "macOS-26-arm64",
                    "python_version": "3.14.3",
                    "python_implementation": "CPython",
                    "entries": 200,
                    "search_runs": 10,
                    "suites": ["persistent_root"],
                    "results": [
                        {
                            "suite": "persistent_root",
                            "operation": "mapping_keys",
                            "count": 10,
                            "elapsed_seconds": 1.0,
                            "ops_per_second": 10.0,
                            "note": None,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        candidate_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "generated_at": "2026-04-20T12:05:00Z",
                    "stone": "otherStone",
                    "platform": "Linux-x86_64",
                    "python_version": "3.14.3",
                    "python_implementation": "CPython",
                    "entries": 200,
                    "search_runs": 10,
                    "suites": ["persistent_root"],
                    "results": [
                        {
                            "suite": "persistent_root",
                            "operation": "mapping_keys",
                            "count": 10,
                            "elapsed_seconds": 1.0,
                            "ops_per_second": 9.0,
                            "note": None,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        baseline_register.register_baseline(
            report_path=str(baseline_path),
            manifest_path=str(manifest_path),
            copy_to="accepted.json",
        )
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
        if exit_code != 0:
            raise AssertionError("benchmark baseline selection CLI returned a non-zero exit code")
        payload = json.loads(stream.getvalue())
        if payload["selected_path"] is not None or payload["comparable"]:
            raise AssertionError(
                "benchmark baseline selection CLI did not report a metadata mismatch"
            )
    validated.append("benchmark_baseline_selection_cli_json")

    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        baseline_path = temp_path / "baseline.json"
        candidate_path = temp_path / "candidate.json"
        baseline_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "generated_at": "2026-04-20T12:00:00Z",
                    "stone": "gs64stone",
                    "platform": "macOS-26-arm64",
                    "python_version": "3.14.3",
                    "python_implementation": "CPython",
                    "entries": 200,
                    "search_runs": 10,
                    "suites": ["persistent_root"],
                    "results": [
                        {
                            "suite": "persistent_root",
                            "operation": "mapping_keys",
                            "count": 10,
                            "elapsed_seconds": 1.0,
                            "ops_per_second": 10.0,
                            "note": None,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        candidate_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "generated_at": "2026-04-20T12:05:00Z",
                    "stone": "gs64stone",
                    "platform": "macOS-26-arm64",
                    "python_version": "3.14.3",
                    "python_implementation": "CPython",
                    "entries": 200,
                    "search_runs": 10,
                    "suites": ["persistent_root"],
                    "results": [
                        {
                            "suite": "persistent_root",
                            "operation": "mapping_keys",
                            "count": 10,
                            "elapsed_seconds": 1.0,
                            "ops_per_second": 9.0,
                            "note": None,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        stream = io.StringIO()
        with redirect_stdout(stream):
            exit_code = benchmark_compare.main(
                [
                    str(baseline_path),
                    str(candidate_path),
                    "--json",
                    "--max-regression-pct",
                    "20",
                    "--suite-threshold",
                    "persistent_root=15",
                    "--operation-threshold",
                    "persistent_root/mapping_keys=5",
                ]
            )
        payload = json.loads(stream.getvalue())
        if exit_code != 2 or not payload["threshold_exceeded"]:
            raise AssertionError("benchmark compare CLI did not surface the thresholded regression")
        if payload["rows"][0]["threshold_scope"] != "operation":
            raise AssertionError("benchmark compare CLI JSON omitted the operation threshold scope")
    validated.append("benchmark_compare_cli_json")

    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        pyproject_path = temp_path / "pyproject.toml"
        changelog_path = temp_path / "CHANGELOG.md"
        pyproject_path.write_text(
            '[project]\nname = "gemstone-py"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        changelog_path.write_text(
            "# Changelog\n\n## 0.1.0 - 2026-04-20\n\n- Released.\n",
            encoding="utf-8",
        )
        report = release_metadata.validate_release_metadata(
            pyproject_path=pyproject_path,
            changelog_path=changelog_path,
            tag="v0.1.0",
        )
        if report.version != "0.1.0" or report.normalized_tag != "0.1.0":
            raise AssertionError("release metadata validation returned unexpected values")
    validated.append("release_metadata")

    return validated


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for installed-package API contract validation."""
    parser = argparse.ArgumentParser(
        prog="python -m gemstone_py.api_contract",
        description="Validate the installed gemstone_py public API contract.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a short text summary.",
    )
    parser.add_argument(
        "--output",
        help="Write the rendered output to this file instead of stdout.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the installed-package API contract validation CLI."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    validated_exports = validate_public_api()
    validated_behaviors = validate_public_api_behaviors()
    if args.json:
        output = json.dumps(
            {
                "validated_exports": validated_exports,
                "validated_behaviors": validated_behaviors,
                "count": len(validated_exports) + len(validated_behaviors),
            },
            indent=2,
        )
    else:
        output = (
            "Validated "
            f"{len(validated_exports)} gemstone_py exports and "
            f"{len(validated_behaviors)} non-live behaviors."
        )
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


def main_entry() -> None:
    """Console-script wrapper for API contract validation."""
    raise SystemExit(main())


if __name__ == "__main__":
    main_entry()
