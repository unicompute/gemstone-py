"""Select environment-specific benchmark baselines for compare workflows."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence, cast

from .benchmark_compare import COMPARABLE_METADATA_FIELDS
from .benchmarks import BENCHMARK_REPORT_SCHEMA_VERSION

BASELINE_MANIFEST_SCHEMA_VERSION = 1
BASELINE_SELECTION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BaselineSelectionReport:
    """Serializable summary for one candidate-to-manifest baseline lookup."""

    schema_version: int
    candidate_path: str
    manifest_path: str
    selected_path: str | None
    comparable: bool
    message: str
    candidate_metadata: dict[str, Any]
    selected_metadata: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} does not contain a JSON object benchmark report")
    schema_version = payload.get("schema_version")
    if schema_version != BENCHMARK_REPORT_SCHEMA_VERSION:
        raise SystemExit(
            f"{path} uses schema_version={schema_version!r}; "
            f"expected {BENCHMARK_REPORT_SCHEMA_VERSION}"
        )
    results = payload.get("results")
    if not isinstance(results, list):
        raise SystemExit(f"{path} is missing a valid 'results' list")
    return cast(dict[str, Any], payload)


def _normalise_metadata_value(field: str, value: Any) -> Any:
    if field == "suites" and isinstance(value, list):
        suite_names = [suite for suite in value if isinstance(suite, str)]
        if len(suite_names) == len(value):
            return sorted(suite_names)
    return value


def _metadata_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        field: _normalise_metadata_value(field, payload.get(field))
        for field in COMPARABLE_METADATA_FIELDS
    }


def _load_manifest(path: Path) -> list[Path]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} does not contain a JSON object baseline manifest")
    schema_version = payload.get("schema_version")
    if schema_version != BASELINE_MANIFEST_SCHEMA_VERSION:
        raise SystemExit(
            f"{path} uses schema_version={schema_version!r}; "
            f"expected {BASELINE_MANIFEST_SCHEMA_VERSION}"
        )
    entries = payload.get("baselines")
    if not isinstance(entries, list):
        raise SystemExit(f"{path} is missing a valid 'baselines' list")

    resolved: list[Path] = []
    for index, entry in enumerate(entries):
        if isinstance(entry, str):
            baseline_path = Path(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("path"), str):
            baseline_path = Path(entry["path"])
        else:
            raise SystemExit(f"{path} baseline entry #{index} must be a string path or object")
        if not baseline_path.is_absolute():
            baseline_path = path.parent / baseline_path
        if not baseline_path.exists():
            raise SystemExit(f"Baseline report not found: {baseline_path}")
        resolved.append(baseline_path)
    return resolved


def select_baseline(
    *,
    candidate_report_path: str,
    manifest_path: str,
) -> BaselineSelectionReport:
    """Select the exact-metadata baseline report for a candidate benchmark artifact."""
    candidate_path = Path(candidate_report_path)
    manifest = Path(manifest_path)
    candidate_payload = _load_report(candidate_path)
    candidate_metadata = _metadata_snapshot(candidate_payload)

    matches: list[tuple[Path, dict[str, Any]]] = []
    for baseline_path in _load_manifest(manifest):
        baseline_payload = _load_report(baseline_path)
        baseline_metadata = _metadata_snapshot(baseline_payload)
        if baseline_metadata == candidate_metadata:
            matches.append((baseline_path, baseline_metadata))

    if not matches:
        return BaselineSelectionReport(
            schema_version=BASELINE_SELECTION_SCHEMA_VERSION,
            candidate_path=str(candidate_path),
            manifest_path=str(manifest),
            selected_path=None,
            comparable=False,
            message="No committed benchmark baseline matches the candidate metadata.",
            candidate_metadata=candidate_metadata,
            selected_metadata=None,
        )

    if len(matches) > 1:
        paths = ", ".join(str(path) for path, _metadata in matches)
        raise SystemExit(f"Multiple benchmark baselines match candidate metadata: {paths}")

    selected_path, selected_metadata = matches[0]
    return BaselineSelectionReport(
        schema_version=BASELINE_SELECTION_SCHEMA_VERSION,
        candidate_path=str(candidate_path),
        manifest_path=str(manifest),
        selected_path=str(selected_path),
        comparable=True,
        message="Selected benchmark baseline with matching environment metadata.",
        candidate_metadata=candidate_metadata,
        selected_metadata=selected_metadata,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the benchmark baseline selection CLI parser."""
    parser = argparse.ArgumentParser(
        prog="python -m gemstone_py.benchmark_baselines",
        description="Select the best committed baseline for a benchmark report.",
    )
    parser.add_argument(
        "candidate_report",
        help="Path to the generated benchmark report JSON to match.",
    )
    parser.add_argument(
        "--manifest",
        default=".github/benchmarks/index.json",
        help="Path to the committed baseline manifest JSON.",
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
    """Run the benchmark baseline selection CLI."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = select_baseline(
        candidate_report_path=args.candidate_report,
        manifest_path=args.manifest,
    )
    if args.json:
        output = json.dumps(report.as_dict(), indent=2)
    else:
        output = report.message
        if report.selected_path is not None:
            output += f"\nSelected baseline: {report.selected_path}"
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


def main_entry() -> None:
    """Console-script wrapper for benchmark baseline selection."""
    raise SystemExit(main())


if __name__ == "__main__":
    main_entry()
