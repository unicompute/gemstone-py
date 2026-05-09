"""Validate release metadata against pyproject and changelog state."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import tomllib
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

CHANGELOG_VERSION_TEMPLATE = r"^##\s+{version}(?:\s+-|\s*$)"
NATIVE_PACKAGE_NAME = "gemstone-py-native"
NATIVE_REQUIRED_WHEEL_MARKERS: tuple[tuple[str, ...], ...] = (
    ("manylinux", "x86_64"),
    ("manylinux", "aarch64"),
    ("manylinux", "armv7l"),
    ("macosx", "x86_64"),
    ("macosx", "arm64"),
    ("win_amd64",),
    ("win_arm64",),
)
NATIVE_REQUIRED_PROJECT_URLS = ("Homepage", "Repository", "Issues")
NATIVE_REQUIRED_CLASSIFIERS = (
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Rust",
)


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


@dataclass(frozen=True)
class NativePyPIReleaseReport:
    """Serializable report for published native wheel metadata validation."""

    package_name: str
    version: str
    project_latest_version: str | None
    expected_sdist: str
    required_wheel_markers: tuple[tuple[str, ...], ...]
    filenames: tuple[str, ...]
    classifiers: tuple[str, ...]
    project_urls: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NativeArtifactSetReport:
    """Serializable report for local native publish artifact validation."""

    package_name: str
    version: str
    expected_sdist: str
    required_wheel_markers: tuple[tuple[str, ...], ...]
    filenames: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_project_version(pyproject_path: Path) -> str:
    """Read the `project.version` value from `pyproject.toml`."""
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


def validate_native_pypi_release(
    payload: Mapping[str, Any],
    *,
    version: str,
    package_name: str = NATIVE_PACKAGE_NAME,
    required_wheel_markers: Sequence[Sequence[str]] = NATIVE_REQUIRED_WHEEL_MARKERS,
) -> NativePyPIReleaseReport:
    """Validate PyPI JSON metadata for a published native package release."""
    try:
        info = payload["info"]
        releases = payload["releases"]
    except KeyError as exc:
        raise ReleaseMetadataError(f"PyPI payload missing key: {exc.args[0]}") from exc
    if not isinstance(info, Mapping) or not isinstance(releases, Mapping):
        raise ReleaseMetadataError("PyPI payload has invalid info/releases shape")

    package_info_name = info.get("name")
    if package_info_name != package_name:
        raise ReleaseMetadataError(
            f"Unexpected native package name: {package_info_name!r}"
        )
    package_info_version = info.get("version")
    project_latest_version = package_info_version if isinstance(package_info_version, str) else None

    release_files = releases.get(version)
    if not isinstance(release_files, Sequence) or isinstance(
        release_files, (str, bytes)
    ):
        raise ReleaseMetadataError(f"Native release {version!r} has no file metadata")

    filenames: set[str] = set()
    for entry in release_files:
        if isinstance(entry, Mapping) and isinstance(entry.get("filename"), str):
            filenames.add(entry["filename"])
    if not filenames:
        raise ReleaseMetadataError(f"Native release {version!r} has no files")

    artifact_report = validate_native_artifact_filenames(
        sorted(filenames),
        version=version,
        package_name=package_name,
        required_wheel_markers=required_wheel_markers,
        require_exact=False,
    )

    project_urls = info.get("project_urls")
    if not isinstance(project_urls, Mapping):
        raise ReleaseMetadataError("Native package metadata is missing project URLs")
    for key in NATIVE_REQUIRED_PROJECT_URLS:
        if key not in project_urls:
            raise ReleaseMetadataError(f"Missing native project URL {key!r}")

    classifiers = info.get("classifiers")
    if not isinstance(classifiers, Sequence) or isinstance(classifiers, (str, bytes)):
        raise ReleaseMetadataError("Native package metadata is missing classifiers")
    classifier_set = {classifier for classifier in classifiers if isinstance(classifier, str)}
    for classifier in NATIVE_REQUIRED_CLASSIFIERS:
        if classifier not in classifier_set:
            raise ReleaseMetadataError(f"Missing native classifier {classifier!r}")

    return NativePyPIReleaseReport(
        package_name=package_name,
        version=version,
        project_latest_version=project_latest_version,
        expected_sdist=artifact_report.expected_sdist,
        required_wheel_markers=artifact_report.required_wheel_markers,
        filenames=artifact_report.filenames,
        classifiers=tuple(sorted(classifier_set)),
        project_urls=tuple(sorted(str(key) for key in project_urls)),
    )


def validate_native_artifact_filenames(
    filenames: Sequence[str],
    *,
    version: str,
    package_name: str = NATIVE_PACKAGE_NAME,
    required_wheel_markers: Sequence[Sequence[str]] = NATIVE_REQUIRED_WHEEL_MARKERS,
    require_exact: bool = True,
) -> NativeArtifactSetReport:
    """Validate native package artifact filenames for a release version."""
    if isinstance(filenames, (str, bytes)):
        raise ReleaseMetadataError("Native artifact filenames must be a sequence")

    filename_list = sorted(str(filename) for filename in filenames)
    if not filename_list:
        raise ReleaseMetadataError("Native artifact set is empty")
    if len(filename_list) != len(set(filename_list)):
        raise ReleaseMetadataError(f"Duplicate native artifact filenames: {filename_list!r}")

    normalized_package_name = package_name.replace("-", "_")
    expected_sdist = f"{normalized_package_name}-{version}.tar.gz"
    if expected_sdist not in filename_list:
        raise ReleaseMetadataError(
            f"Missing native sdist {expected_sdist!r}: {filename_list!r}"
        )

    normalized_required_markers = tuple(tuple(markers) for markers in required_wheel_markers)
    wheel_names = [filename for filename in filename_list if filename.endswith(".whl")]
    for markers in normalized_required_markers:
        matches = [
            filename
            for filename in wheel_names
            if all(marker in filename for marker in markers)
        ]
        if not matches:
            raise ReleaseMetadataError(
                f"Missing native wheel with markers {markers!r}: {filename_list!r}"
            )
        if require_exact and len(matches) != 1:
            raise ReleaseMetadataError(
                f"Expected one native wheel with markers {markers!r}, got {matches!r}"
            )

    if require_exact:
        expected_count = 1 + len(normalized_required_markers)
        if len(filename_list) != expected_count:
            raise ReleaseMetadataError(
                f"Unexpected native artifacts: expected {expected_count}, got {filename_list!r}"
            )
        expected_prefix = f"{normalized_package_name}-{version}-"
        for filename in wheel_names:
            if not filename.startswith(expected_prefix):
                raise ReleaseMetadataError(f"Unexpected native wheel filename {filename!r}")

    return NativeArtifactSetReport(
        package_name=package_name,
        version=version,
        expected_sdist=expected_sdist,
        required_wheel_markers=normalized_required_markers,
        filenames=tuple(filename_list),
    )


def validate_native_artifact_directory(
    directory: Path,
    *,
    version: str,
    package_name: str = NATIVE_PACKAGE_NAME,
) -> NativeArtifactSetReport:
    """Validate native publish artifacts in a local directory."""
    try:
        filenames = sorted(path.name for path in directory.iterdir() if path.is_file())
    except FileNotFoundError as exc:
        raise ReleaseMetadataError(f"Native artifact directory not found: {directory}") from exc
    return validate_native_artifact_filenames(
        filenames,
        version=version,
        package_name=package_name,
        require_exact=True,
    )


def fetch_pypi_json(url: str) -> Mapping[str, Any]:
    """Fetch a PyPI JSON payload."""
    with urllib.request.urlopen(url) as response:  # noqa: S310
        payload = json.load(response)
    if not isinstance(payload, Mapping):
        raise ReleaseMetadataError("PyPI JSON response was not an object")
    return payload


def wait_for_native_pypi_release(
    *,
    url: str,
    version: str,
    attempts: int = 6,
    sleep_seconds: float = 20.0,
) -> Mapping[str, Any]:
    """Poll PyPI JSON metadata until a release version has visible files."""
    for attempt in range(1, attempts + 1):
        payload = fetch_pypi_json(url)
        releases = payload.get("releases", {})
        if isinstance(releases, Mapping):
            release_files = releases.get(version)
            if release_files:
                return payload
        print(f"Native release {version} not visible yet; retrying ({attempt}/{attempts})...")
        time.sleep(sleep_seconds)
    raise ReleaseMetadataError(f"Native release {version} did not appear in package metadata.")


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
    parser.add_argument(
        "--native-pypi-json-url",
        help="Verify a gemstone-py-native release from a PyPI/TestPyPI JSON URL.",
    )
    parser.add_argument(
        "--native-artifacts-dir",
        help="Verify a local directory containing native publish artifacts.",
    )
    parser.add_argument(
        "--native-version",
        help="Native package version expected in the PyPI/TestPyPI JSON payload.",
    )
    parser.add_argument(
        "--native-package-name",
        default=NATIVE_PACKAGE_NAME,
        help=f"Native package name to verify. Defaults to {NATIVE_PACKAGE_NAME}.",
    )
    parser.add_argument(
        "--native-attempts",
        type=int,
        default=6,
        help="Number of PyPI JSON polling attempts for native release verification.",
    )
    parser.add_argument(
        "--native-sleep-seconds",
        type=float,
        default=20.0,
        help="Seconds to sleep between native PyPI JSON polling attempts.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the release metadata validation CLI."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.native_artifacts_dir or args.native_pypi_json_url or args.native_version:
        if args.native_artifacts_dir and args.native_pypi_json_url:
            print(
                "--native-artifacts-dir and --native-pypi-json-url are mutually exclusive",
                file=sys.stderr,
            )
            return 1
        if args.native_artifacts_dir:
            if not args.native_version:
                print("--native-version is required with --native-artifacts-dir", file=sys.stderr)
                return 1
            try:
                native_artifact_report = validate_native_artifact_directory(
                    Path(args.native_artifacts_dir),
                    version=args.native_version,
                    package_name=args.native_package_name,
                )
            except ReleaseMetadataError as exc:
                print(str(exc), file=sys.stderr)
                return 1

            if args.json:
                print(json.dumps(native_artifact_report.as_dict(), indent=2))
            else:
                print(
                    "Validated native artifact set "
                    f"{native_artifact_report.package_name} "
                    f"{native_artifact_report.version} with "
                    f"{len(native_artifact_report.filenames)} files"
                )
            return 0

        if not args.native_pypi_json_url or not args.native_version:
            print(
                "--native-pypi-json-url and --native-version must be provided together",
                file=sys.stderr,
            )
            return 1
        try:
            payload = wait_for_native_pypi_release(
                url=args.native_pypi_json_url,
                version=args.native_version,
                attempts=args.native_attempts,
                sleep_seconds=args.native_sleep_seconds,
            )
            native_report = validate_native_pypi_release(
                payload,
                version=args.native_version,
                package_name=args.native_package_name,
            )
        except ReleaseMetadataError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        if args.json:
            print(json.dumps(native_report.as_dict(), indent=2))
        else:
            print(
                "Validated native package "
                f"{native_report.package_name} {native_report.version} with "
                f"{len(native_report.filenames)} files"
            )
        return 0

    try:
        release_report = validate_release_metadata(
            pyproject_path=Path(args.pyproject),
            changelog_path=Path(args.changelog),
            tag=args.tag,
        )
    except ReleaseMetadataError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(release_report.as_dict(), indent=2))
    else:
        print(f"Validated release metadata for version {release_report.version}")
        if release_report.tag is not None:
            print(f"Release tag: {release_report.tag}")
    return 0


def main_entry() -> None:
    """Console-script wrapper for release metadata validation."""
    raise SystemExit(main())


if __name__ == "__main__":
    main_entry()
