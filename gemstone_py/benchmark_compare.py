"""Compare two gemstone-py benchmark report artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Sequence, cast

from .benchmarks import BENCHMARK_REPORT_SCHEMA_VERSION

BENCHMARK_COMPARISON_SCHEMA_VERSION = 3
COMPARABLE_METADATA_FIELDS: tuple[str, ...] = (
    "stone",
    "platform",
    "python_version",
    "python_implementation",
    "entries",
    "search_runs",
    "suites",
)


@dataclass(frozen=True)
class BenchmarkComparisonRow:
    """Comparison for one `(suite, operation)` benchmark row."""

    suite: str
    operation: str
    status: str
    baseline_ops_per_second: float | None
    candidate_ops_per_second: float | None
    delta_ops_per_second: float | None
    delta_percent: float | None
    baseline_count: int | None
    candidate_count: int | None
    baseline_note: str | None = None
    candidate_note: str | None = None
    applied_regression_pct: float | None = None
    threshold_scope: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the row."""
        return asdict(self)


@dataclass(frozen=True)
class BenchmarkComparisonReport:
    """Serializable comparison payload for two benchmark artifacts."""

    schema_version: int
    baseline_path: str
    candidate_path: str
    comparable: bool
    compatibility_issues: list[str]
    max_regression_pct: float | None
    suite_regression_pcts: dict[str, float]
    operation_regression_pcts: dict[str, float]
    threshold_exceeded: bool
    threshold_exceeded_operations: list[str]
    baseline_metadata: dict[str, Any]
    candidate_metadata: dict[str, Any]
    baseline_generated_at: str | None
    candidate_generated_at: str | None
    baseline_stone: str | None
    candidate_stone: str | None
    rows: list[BenchmarkComparisonRow]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable report payload."""
        payload = asdict(self)
        payload["rows"] = [row.as_dict() for row in self.rows]
        return payload


def _load_report(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
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


def _result_index(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in payload["results"]:
        suite = row.get("suite")
        operation = row.get("operation")
        if not isinstance(suite, str) or not isinstance(operation, str):
            raise SystemExit("Benchmark report rows must include string suite/operation keys")
        index[(suite, operation)] = row
    return index


def _metadata_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        field: _normalise_metadata_value(field, payload.get(field))
        for field in COMPARABLE_METADATA_FIELDS
    }


def _normalise_metadata_value(field: str, value: Any) -> Any:
    if field == "suites" and isinstance(value, list):
        suite_names = [suite for suite in value if isinstance(suite, str)]
        if len(suite_names) == len(value):
            return sorted(suite_names)
    return value


def _compare_metadata(
    baseline_metadata: dict[str, Any],
    candidate_metadata: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    for field in COMPARABLE_METADATA_FIELDS:
        baseline_value = baseline_metadata.get(field)
        candidate_value = candidate_metadata.get(field)
        if baseline_value == candidate_value:
            continue
        issues.append(
            f"{field} differs: baseline={baseline_value!r}, candidate={candidate_value!r}"
        )
    return issues


def _threshold_exceeded_operations(
    rows: Sequence[BenchmarkComparisonRow], *, comparable: bool
) -> list[str]:
    if not comparable:
        return []

    exceeded: list[str] = []
    for row in rows:
        threshold = row.applied_regression_pct
        if threshold is None:
            continue
        if row.status == "missing_in_candidate":
            exceeded.append(f"{row.suite}/{row.operation}")
            continue
        if row.status != "regressed" or row.delta_percent is None:
            continue
        if abs(row.delta_percent) >= threshold:
            exceeded.append(f"{row.suite}/{row.operation}")
    return exceeded


def _effective_threshold(
    row: BenchmarkComparisonRow,
    *,
    max_regression_pct: float | None,
    suite_regression_pcts: dict[str, float],
    operation_regression_pcts: dict[str, float],
) -> tuple[float | None, str | None]:
    operation_key = f"{row.suite}/{row.operation}"
    if operation_key in operation_regression_pcts:
        return operation_regression_pcts[operation_key], "operation"
    if row.suite in suite_regression_pcts:
        return suite_regression_pcts[row.suite], "suite"
    if max_regression_pct is not None:
        return max_regression_pct, "global"
    return None, None


def _compare_row(
    key: tuple[str, str],
    baseline: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
) -> BenchmarkComparisonRow:
    suite, operation = key
    baseline_ops = None if baseline is None else float(baseline["ops_per_second"])
    candidate_ops = None if candidate is None else float(candidate["ops_per_second"])
    delta_ops: float | None = None
    delta_percent: float | None = None

    if baseline is None:
        status = "missing_in_baseline"
    elif candidate is None:
        status = "missing_in_candidate"
    else:
        assert baseline_ops is not None
        assert candidate_ops is not None
        delta_ops = candidate_ops - baseline_ops
        if baseline_ops == 0.0:
            delta_percent = None
        else:
            delta_percent = (delta_ops / baseline_ops) * 100.0
        if delta_ops > 0:
            status = "improved"
        elif delta_ops < 0:
            status = "regressed"
        else:
            status = "unchanged"

    return BenchmarkComparisonRow(
        suite=suite,
        operation=operation,
        status=status,
        baseline_ops_per_second=baseline_ops,
        candidate_ops_per_second=candidate_ops,
        delta_ops_per_second=delta_ops,
        delta_percent=delta_percent,
        baseline_count=None if baseline is None else int(baseline["count"]),
        candidate_count=None if candidate is None else int(candidate["count"]),
        baseline_note=None if baseline is None else baseline.get("note"),
        candidate_note=None if candidate is None else candidate.get("note"),
    )


def compare_reports(
    *,
    baseline_path: str,
    candidate_path: str,
    max_regression_pct: float | None = None,
    suite_regression_pcts: dict[str, float] | None = None,
    operation_regression_pcts: dict[str, float] | None = None,
) -> BenchmarkComparisonReport:
    """Compare two benchmark reports and return a serialisable summary."""
    baseline_payload = _load_report(baseline_path)
    candidate_payload = _load_report(candidate_path)
    baseline_index = _result_index(baseline_payload)
    candidate_index = _result_index(candidate_payload)
    baseline_metadata = _metadata_snapshot(baseline_payload)
    candidate_metadata = _metadata_snapshot(candidate_payload)
    suite_thresholds = dict(sorted((suite_regression_pcts or {}).items()))
    operation_thresholds = dict(sorted((operation_regression_pcts or {}).items()))
    compatibility_issues = _compare_metadata(baseline_metadata, candidate_metadata)
    comparable = not compatibility_issues

    keys = sorted(set(baseline_index) | set(candidate_index))
    rows: list[BenchmarkComparisonRow] = []
    for key in keys:
        row = _compare_row(key, baseline_index.get(key), candidate_index.get(key))
        threshold, scope = _effective_threshold(
            row,
            max_regression_pct=max_regression_pct,
            suite_regression_pcts=suite_thresholds,
            operation_regression_pcts=operation_thresholds,
        )
        if threshold is not None:
            row = replace(
                row,
                applied_regression_pct=threshold,
                threshold_scope=scope,
            )
        rows.append(row)
    threshold_exceeded_operations = _threshold_exceeded_operations(rows, comparable=comparable)
    return BenchmarkComparisonReport(
        schema_version=BENCHMARK_COMPARISON_SCHEMA_VERSION,
        baseline_path=baseline_path,
        candidate_path=candidate_path,
        comparable=comparable,
        compatibility_issues=compatibility_issues,
        max_regression_pct=max_regression_pct,
        suite_regression_pcts=suite_thresholds,
        operation_regression_pcts=operation_thresholds,
        threshold_exceeded=bool(threshold_exceeded_operations),
        threshold_exceeded_operations=threshold_exceeded_operations,
        baseline_metadata=baseline_metadata,
        candidate_metadata=candidate_metadata,
        baseline_generated_at=_optional_str(baseline_payload.get("generated_at")),
        candidate_generated_at=_optional_str(candidate_payload.get("generated_at")),
        baseline_stone=_optional_str(baseline_payload.get("stone")),
        candidate_stone=_optional_str(candidate_payload.get("stone")),
        rows=rows,
    )


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _format_float(value: float | None, *, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{value:+.1f}{suffix}" if suffix else f"{value:.1f}"


def format_comparison(report: BenchmarkComparisonReport) -> str:
    """Render a comparison report as a simple aligned table."""
    if not report.rows:
        return "No benchmark comparison rows."

    suite_width = max(len("Suite"), *(len(row.suite) for row in report.rows))
    operation_width = max(len("Operation"), *(len(row.operation) for row in report.rows))
    baseline_width = max(
        len("Baseline Ops/s"),
        *(len(_format_float(row.baseline_ops_per_second)) for row in report.rows),
    )
    candidate_width = max(
        len("Candidate Ops/s"),
        *(len(_format_float(row.candidate_ops_per_second)) for row in report.rows),
    )
    delta_width = max(
        len("Delta Ops/s"),
        *(len(_format_float(row.delta_ops_per_second, suffix="")) for row in report.rows),
    )
    percent_width = max(
        len("Delta %"),
        *(len(_format_float(row.delta_percent, suffix="%")) for row in report.rows),
    )
    status_width = max(len("Status"), *(len(row.status) for row in report.rows))

    lines = [
        f"Baseline: {report.baseline_path}\n"
        f"Candidate: {report.candidate_path}\n"
        f"Comparable: {'yes' if report.comparable else 'no'}"
    ]
    if report.compatibility_issues:
        lines.append("Compatibility Issues:")
        lines.extend(f"- {issue}" for issue in report.compatibility_issues)
    if report.suite_regression_pcts:
        lines.append(
            "Suite Thresholds: "
            + ", ".join(
                f"{suite}={threshold:.1f}%"
                for suite, threshold in report.suite_regression_pcts.items()
            )
        )
    if report.operation_regression_pcts:
        lines.append(
            "Operation Thresholds: "
            + ", ".join(
                f"{operation}={threshold:.1f}%"
                for operation, threshold in report.operation_regression_pcts.items()
            )
        )
    if report.max_regression_pct is not None:
        if report.comparable:
            lines.append(
                f"Regression Threshold: {report.max_regression_pct:.1f}% "
                f"({'exceeded' if report.threshold_exceeded else 'ok'})"
            )
            if report.threshold_exceeded_operations:
                lines.append(
                    "Threshold Exceeded Operations: "
                    + ", ".join(report.threshold_exceeded_operations)
                )
        else:
            lines.append(
                f"Regression Threshold: skipped ({report.max_regression_pct:.1f}%) "
                "due to metadata mismatch"
            )

    header = (
        f"{'Suite':<{suite_width}}  "
        f"{'Operation':<{operation_width}}  "
        f"{'Baseline Ops/s':>{baseline_width}}  "
        f"{'Candidate Ops/s':>{candidate_width}}  "
        f"{'Delta Ops/s':>{delta_width}}  "
        f"{'Delta %':>{percent_width}}  "
        f"{'Status':<{status_width}}"
    )
    separator = (
        f"{'-' * suite_width}  "
        f"{'-' * operation_width}  "
        f"{'-' * baseline_width}  "
        f"{'-' * candidate_width}  "
        f"{'-' * delta_width}  "
        f"{'-' * percent_width}  "
        f"{'-' * status_width}"
    )
    lines.extend([header, separator])
    for row in report.rows:
        lines.append(
            f"{row.suite:<{suite_width}}  "
            f"{row.operation:<{operation_width}}  "
            f"{_format_float(row.baseline_ops_per_second):>{baseline_width}}  "
            f"{_format_float(row.candidate_ops_per_second):>{candidate_width}}  "
            f"{_format_float(row.delta_ops_per_second):>{delta_width}}  "
            f"{_format_float(row.delta_percent, suffix='%'):>{percent_width}}  "
            f"{row.status:<{status_width}}"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build the benchmark compare CLI parser."""
    parser = argparse.ArgumentParser(
        prog="gemstone-benchmark-compare",
        description="Compare two gemstone-py benchmark report JSON artifacts.",
    )
    parser.add_argument("baseline", help="Path to the baseline benchmark report JSON.")
    parser.add_argument("candidate", help="Path to the candidate benchmark report JSON.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a formatted table.",
    )
    parser.add_argument(
        "--output",
        help="Write the rendered output to this file instead of stdout.",
    )
    parser.add_argument(
        "--max-regression-pct",
        type=float,
        help=(
            "Maximum allowed regression percentage before the command exits "
            "non-zero. Skipped when report metadata is not comparable."
        ),
    )
    parser.add_argument(
        "--suite-threshold",
        action="append",
        default=[],
        metavar="SUITE=PCT",
        help=(
            "Per-suite regression threshold override. Repeatable. "
            "Overrides --max-regression-pct for matching suites."
        ),
    )
    parser.add_argument(
        "--operation-threshold",
        action="append",
        default=[],
        metavar="SUITE/OPERATION=PCT",
        help=(
            "Per-operation regression threshold override. Repeatable. "
            "Overrides both --suite-threshold and --max-regression-pct."
        ),
    )
    return parser


def _parse_threshold_specs(
    specs: Sequence[str], *, label: str
) -> dict[str, float]:
    thresholds: dict[str, float] = {}
    for spec in specs:
        key, separator, raw_value = spec.partition("=")
        key = key.strip()
        raw_value = raw_value.strip()
        if separator != "=" or not key or not raw_value:
            raise SystemExit(f"Invalid {label} threshold {spec!r}; expected NAME=PCT")
        try:
            value = float(raw_value)
        except ValueError as exc:
            raise SystemExit(
                f"Invalid {label} threshold {spec!r}; {raw_value!r} is not a number"
            ) from exc
        if value < 0:
            raise SystemExit(f"Invalid {label} threshold {spec!r}; value must be non-negative")
        thresholds[key] = value
    return thresholds


def main(argv: Sequence[str] | None = None) -> int:
    """Run the benchmark compare CLI."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    suite_thresholds = _parse_threshold_specs(args.suite_threshold, label="suite")
    operation_thresholds = _parse_threshold_specs(
        args.operation_threshold,
        label="operation",
    )
    report = compare_reports(
        baseline_path=args.baseline,
        candidate_path=args.candidate,
        max_regression_pct=args.max_regression_pct,
        suite_regression_pcts=suite_thresholds,
        operation_regression_pcts=operation_thresholds,
    )
    if args.json:
        output = json.dumps(report.as_dict(), indent=2)
    else:
        output = format_comparison(report)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    if report.comparable and report.threshold_exceeded:
        return 2
    return 0


def main_entry() -> None:
    """Console-script wrapper for gemstone-benchmark-compare."""
    raise SystemExit(main())


if __name__ == "__main__":
    main_entry()
