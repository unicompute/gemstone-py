"""Register benchmark report artifacts in the committed baseline manifest."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from .benchmark_baselines import BASELINE_MANIFEST_SCHEMA_VERSION, _load_report

BASELINE_REGISTRATION_SCHEMA_VERSION = 1
BASELINE_MAINTENANCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BaselineRegistrationReport:
    """Serializable summary for one manifest registration update."""

    schema_version: int
    source_report_path: str
    manifest_path: str
    registered_path: str
    copied: bool
    added_to_manifest: bool
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BaselineManifestMaintenanceReport:
    """Serializable summary for one manifest prune/drop operation."""

    schema_version: int
    manifest_path: str
    removed_paths: list[str]
    remaining_paths: list[str]
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_manifest_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": BASELINE_MANIFEST_SCHEMA_VERSION,
            "baselines": [],
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} does not contain a JSON object baseline manifest")
    schema_version = payload.get("schema_version")
    if schema_version != BASELINE_MANIFEST_SCHEMA_VERSION:
        raise SystemExit(
            f"{path} uses schema_version={schema_version!r}; "
            f"expected {BASELINE_MANIFEST_SCHEMA_VERSION}"
        )
    baselines = payload.get("baselines")
    if not isinstance(baselines, list):
        raise SystemExit(f"{path} is missing a valid 'baselines' list")
    return payload


def _entry_path_text(entry: Any) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and isinstance(entry.get("path"), str):
        return str(entry["path"])
    raise SystemExit("Baseline manifest entries must be string paths or objects with 'path'")


def _relative_or_absolute(target_path: Path, manifest_path: Path) -> str:
    try:
        return str(target_path.relative_to(manifest_path.parent))
    except ValueError:
        return str(target_path)


def _entry_absolute_path(entry_path: str, manifest_path: Path) -> Path:
    path = Path(entry_path)
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path.resolve()


def prune_manifest(
    *,
    manifest_path: str,
    drop_paths: Sequence[str] = (),
    remove_missing: bool = True,
) -> BaselineManifestMaintenanceReport:
    """Prune missing, duplicate, or explicitly dropped baseline manifest entries."""
    manifest = Path(manifest_path).resolve()
    payload = _load_manifest_payload(manifest)
    baselines = payload["baselines"]
    requested_drops = {
        str(_entry_absolute_path(path_text, manifest))
        for path_text in drop_paths
    }

    removed_paths: list[str] = []
    remaining_paths: list[str] = []
    seen_paths: set[str] = set()

    for entry in baselines:
        path_text = _entry_path_text(entry)
        absolute_path = _entry_absolute_path(path_text, manifest)
        absolute_path_text = str(absolute_path)
        should_remove = False
        if absolute_path_text in requested_drops:
            should_remove = True
        elif remove_missing and not absolute_path.exists():
            should_remove = True
        elif absolute_path_text in seen_paths:
            should_remove = True
        else:
            seen_paths.add(absolute_path_text)
            remaining_paths.append(path_text)
        if should_remove:
            removed_paths.append(path_text)

    if removed_paths:
        payload["baselines"] = remaining_paths
        manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    message = "No benchmark baseline manifest changes were necessary."
    if removed_paths:
        message = "Updated benchmark baseline manifest entries."

    return BaselineManifestMaintenanceReport(
        schema_version=BASELINE_MAINTENANCE_SCHEMA_VERSION,
        manifest_path=str(manifest),
        removed_paths=removed_paths,
        remaining_paths=remaining_paths,
        message=message,
    )


def register_baseline(
    *,
    report_path: str,
    manifest_path: str,
    copy_to: str | None = None,
) -> BaselineRegistrationReport:
    """Register one benchmark report in the baseline manifest and optionally copy it."""
    source_path = Path(report_path).resolve()
    if not source_path.exists():
        raise SystemExit(f"Benchmark report not found: {source_path}")
    _load_report(source_path)

    manifest = Path(manifest_path).resolve()
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = _load_manifest_payload(manifest)
    existing_entries = payload["baselines"]

    if copy_to is None:
        try:
            source_path.relative_to(manifest.parent)
            target_path = source_path
        except ValueError:
            target_path = (manifest.parent / source_path.name).resolve()
    else:
        requested_target = Path(copy_to)
        if not requested_target.is_absolute():
            requested_target = manifest.parent / requested_target
        target_path = requested_target.resolve()

    copied = source_path != target_path
    if copied:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)

    registered_path = _relative_or_absolute(target_path, manifest)
    existing_path_texts = {_entry_path_text(entry) for entry in existing_entries}
    added_to_manifest = registered_path not in existing_path_texts
    if added_to_manifest:
        existing_entries.append(registered_path)
        manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    message = "Registered benchmark baseline."
    if not added_to_manifest and not copied:
        message = "Benchmark baseline was already registered."
    elif not added_to_manifest and copied:
        message = "Updated benchmark baseline artifact without changing the manifest."

    return BaselineRegistrationReport(
        schema_version=BASELINE_REGISTRATION_SCHEMA_VERSION,
        source_report_path=str(source_path),
        manifest_path=str(manifest),
        registered_path=registered_path,
        copied=copied,
        added_to_manifest=added_to_manifest,
        message=message,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the benchmark baseline registration CLI parser."""
    parser = argparse.ArgumentParser(
        prog="python -m gemstone_py.benchmark_baseline_register",
        description="Register a benchmark report in the committed baseline manifest.",
    )
    parser.add_argument(
        "report",
        nargs="?",
        help="Path to the benchmark report JSON to register.",
    )
    parser.add_argument(
        "--manifest",
        default=".github/benchmarks/index.json",
        help="Path to the baseline manifest JSON to update.",
    )
    parser.add_argument(
        "--copy-to",
        help=(
            "Optional target path for the committed baseline artifact. Relative paths "
            "are resolved against the manifest directory."
        ),
    )
    parser.add_argument(
        "--drop-path",
        action="append",
        default=[],
        help=(
            "Remove this baseline path from the manifest after registration, or use "
            "without a report for manifest maintenance only. May be passed multiple times."
        ),
    )
    parser.add_argument(
        "--prune-missing",
        action="store_true",
        help="Remove missing and duplicate entries from the manifest.",
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
    """Run the benchmark baseline registration CLI."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    registration_report: BaselineRegistrationReport | None = None
    maintenance_report: BaselineManifestMaintenanceReport | None = None

    if args.report is not None:
        registration_report = register_baseline(
            report_path=args.report,
            manifest_path=args.manifest,
            copy_to=args.copy_to,
        )
    if args.prune_missing or args.drop_path:
        maintenance_report = prune_manifest(
            manifest_path=args.manifest,
            drop_paths=list(args.drop_path),
            remove_missing=args.prune_missing,
        )

    if registration_report is None and maintenance_report is None:
        parser.error("report is required unless --prune-missing or --drop-path is used.")

    if args.json:
        if registration_report is not None and maintenance_report is not None:
            output = json.dumps(
                {
                    "registration": registration_report.as_dict(),
                    "maintenance": maintenance_report.as_dict(),
                },
                indent=2,
            )
        elif registration_report is not None:
            output = json.dumps(registration_report.as_dict(), indent=2)
        else:
            assert maintenance_report is not None
            output = json.dumps(maintenance_report.as_dict(), indent=2)
    else:
        parts: list[str] = []
        if registration_report is not None:
            parts.append(registration_report.message)
            parts.append(f"Registered path: {registration_report.registered_path}")
        if maintenance_report is not None:
            parts.append(maintenance_report.message)
            if maintenance_report.removed_paths:
                parts.append(
                    "Removed paths: " + ", ".join(maintenance_report.removed_paths)
                )
        output = "\n".join(parts)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


def main_entry() -> None:
    """Console-script wrapper for benchmark baseline registration."""
    raise SystemExit(main())


if __name__ == "__main__":
    main_entry()
