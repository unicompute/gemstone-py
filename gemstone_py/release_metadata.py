"""Validate release metadata against pyproject and changelog state."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None


CHANGELOG_VERSION_TEMPLATE = r"^##\s+{version}(?:\s+-|\s*$)"


class ReleaseMetadataError(ValueError):
    """Raised when release metadata does not satisfy the release guardrails."""


@dataclass(frozen=True)
class ReleaseValidationReport:
    """Serializable report for release metadata validation."""

    version: str
    tag: str | None
    normalized_tag: str | None
    changelog_contains_version: bool
    tag_matches_version: bool | None
    pyproject_path: str
    changelog_path: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_project_version(pyproject_path: Path) -> str:
    """Read the `project.version` value from `pyproject.toml`."""
    if tomllib is None:  # pragma: no cover - Python 3.10 fallback
        raise ReleaseMetadataError(
            "Python 3.11+ or the 'tomli' package is required to read pyproject.toml"
        )
    try:
        payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReleaseMetadataError(f"pyproject file not found: {pyproject_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ReleaseMetadataError(f"Invalid pyproject.toml: {exc}") from exc

    project = payload.get("project")
    if not isinstance(project, dict):
        raise ReleaseMetadataError("pyproject.toml is missing a [project] table")
    version = project.get("version")
    if not isinstance(version, str) or not version:
        raise ReleaseMetadataError("pyproject.toml is missing project.version")
    return version


def normalize_tag(tag: str) -> str:
    """Normalise a git tag or ref name to its version payload."""
    normalized = tag.removeprefix("refs/tags/").strip()
    return normalized[1:] if normalized.startswith("v") else normalized


def changelog_has_version(changelog_text: str, version: str) -> bool:
    """Return true when the changelog contains a heading for `version`."""
    pattern = re.compile(
        CHANGELOG_VERSION_TEMPLATE.format(version=re.escape(version)),
        re.MULTILINE,
    )
    return bool(pattern.search(changelog_text))


def validate_release_metadata(
    *,
    pyproject_path: Path,
    changelog_path: Path,
    tag: str | None = None,
) -> ReleaseValidationReport:
    """Validate version/changelog/tag release metadata and return a report."""
    version = load_project_version(pyproject_path)
    try:
        changelog_text = changelog_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ReleaseMetadataError(f"changelog file not found: {changelog_path}") from exc

    if not changelog_has_version(changelog_text, version):
        raise ReleaseMetadataError(
            f"CHANGELOG does not contain an entry for version {version!r}"
        )

    normalized_tag = normalize_tag(tag) if tag else None
    if normalized_tag is not None and normalized_tag != version:
        raise ReleaseMetadataError(
            f"Release tag {tag!r} does not match project.version {version!r}"
        )

    return ReleaseValidationReport(
        version=version,
        tag=tag,
        normalized_tag=normalized_tag,
        changelog_contains_version=True,
        tag_matches_version=None if normalized_tag is None else True,
        pyproject_path=str(pyproject_path),
        changelog_path=str(changelog_path),
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the release metadata CLI parser."""
    parser = argparse.ArgumentParser(
        prog="python -m gemstone_py.release_metadata",
        description="Validate release version, changelog, and optional tag metadata.",
    )
    parser.add_argument(
        "--pyproject",
        default="pyproject.toml",
        help="Path to pyproject.toml. Defaults to ./pyproject.toml.",
    )
    parser.add_argument(
        "--changelog",
        default="CHANGELOG.md",
        help="Path to the release changelog. Defaults to ./CHANGELOG.md.",
    )
    parser.add_argument(
        "--tag",
        help="Optional release tag or refs/tags/* ref name to validate against project.version.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON report instead of a short text summary.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the release metadata validation CLI."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        report = validate_release_metadata(
            pyproject_path=Path(args.pyproject),
            changelog_path=Path(args.changelog),
            tag=args.tag,
        )
    except ReleaseMetadataError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(f"Validated release metadata for version {report.version}")
        if report.tag is not None:
            print(f"Release tag: {report.tag}")
    return 0


def main_entry() -> None:
    """Console-script wrapper for release metadata validation."""
    raise SystemExit(main())


if __name__ == "__main__":
    main_entry()
