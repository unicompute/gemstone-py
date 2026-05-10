"""End-to-end verification for published PyPI and TestPyPI releases."""

from __future__ import annotations

import argparse
import html
import importlib.metadata as metadata
import json
import os
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.parse
import urllib.request
import venv
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from gemstone_py import release_metadata

FetchText = Callable[[str], str]

GEMSTONE_PACKAGE = "gemstone-py"
NATIVE_PACKAGE = "gemstone-py-native"
INDEXES = {
    "pypi": "https://pypi.org",
    "testpypi": "https://test.pypi.org",
}


class PublishVerifyError(ValueError):
    """Raised when a published release does not satisfy verification checks."""


@dataclass(frozen=True)
class PackageCheck:
    """A package/version pair to verify."""

    name: str
    version: str


@dataclass(frozen=True)
class IndexCheckReport:
    """Serializable verification report for one package on one index."""

    index: str
    package_name: str
    version: str
    latest_version: str | None
    project_json_files: tuple[str, ...]
    version_json_files: tuple[str, ...]
    simple_index_files: tuple[str, ...]
    installed: bool
    installed_version: str | None = None
    backend: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalized_distribution_name(name: str) -> str:
    """Return the PyPI filename prefix for a distribution name."""
    return name.replace("-", "_")


def expected_gemstone_files(version: str) -> tuple[str, ...]:
    """Return the expected pure-Python release artifacts."""
    prefix = normalized_distribution_name(GEMSTONE_PACKAGE)
    return (
        f"{prefix}-{version}-py3-none-any.whl",
        f"{prefix}-{version}.tar.gz",
    )


def default_version(pyproject_path: Path, package_name: str) -> str | None:
    """Read a local pyproject version or fall back to installed metadata."""
    if pyproject_path.exists():
        payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        project = payload.get("project")
        if isinstance(project, Mapping):
            version = project.get("version")
            if isinstance(version, str) and version:
                return version
    try:
        return metadata.version(package_name)
    except metadata.PackageNotFoundError:
        return None


def fetch_text(url: str) -> str:
    """Fetch URL text with cache-busting headers."""
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "gemstone-publish-verify/1",
        },
    )
    with urllib.request.urlopen(request) as response:  # noqa: S310
        data = response.read()
    return data.decode("utf-8") if isinstance(data, bytes) else str(data)


def fetch_json(url: str, fetcher: FetchText = fetch_text) -> Mapping[str, Any]:
    """Fetch and parse a JSON object."""
    payload = json.loads(fetcher(url))
    if not isinstance(payload, Mapping):
        raise PublishVerifyError(f"Expected JSON object from {url}")
    return payload


def cachebust_url(url: str) -> str:
    """Append a unique query parameter to bypass stale CDN project JSON."""
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}gemstone_publish_verify={time.time_ns()}"


def index_project_json_url(index_base_url: str, package_name: str) -> str:
    """Return a project-level PyPI JSON URL."""
    package = urllib.parse.quote(package_name)
    return cachebust_url(f"{index_base_url}/pypi/{package}/json")


def index_version_json_url(index_base_url: str, package_name: str, version: str) -> str:
    """Return a version-specific PyPI JSON URL."""
    package = urllib.parse.quote(package_name)
    quoted_version = urllib.parse.quote(version)
    return cachebust_url(f"{index_base_url}/pypi/{package}/{quoted_version}/json")


def index_simple_url(index_base_url: str, package_name: str) -> str:
    """Return a simple-index URL for a package."""
    normalized = package_name.replace("_", "-").lower()
    return cachebust_url(f"{index_base_url}/simple/{urllib.parse.quote(normalized)}/")


def release_files_from_project_payload(
    payload: Mapping[str, Any],
    *,
    package_name: str,
    version: str,
) -> tuple[str, ...]:
    """Return release filenames from project-level JSON after shape checks."""
    info = payload.get("info")
    releases = payload.get("releases")
    if not isinstance(info, Mapping) or not isinstance(releases, Mapping):
        raise PublishVerifyError("Project JSON is missing info/releases objects")
    if info.get("name") != package_name:
        raise PublishVerifyError(
            f"Project JSON package name {info.get('name')!r} did not match {package_name!r}"
        )
    release_files = releases.get(version)
    if not isinstance(release_files, Sequence) or isinstance(release_files, (str, bytes)):
        raise PublishVerifyError(f"Project JSON has no release files for {version!r}")
    return filenames_from_file_entries(release_files)


def release_files_from_version_payload(
    payload: Mapping[str, Any],
    *,
    package_name: str,
    version: str,
) -> tuple[str, ...]:
    """Return release filenames from version-specific JSON after shape checks."""
    info = payload.get("info")
    urls = payload.get("urls")
    if not isinstance(info, Mapping) or not isinstance(urls, Sequence):
        raise PublishVerifyError("Version JSON is missing info/urls objects")
    if info.get("name") != package_name:
        raise PublishVerifyError(
            f"Version JSON package name {info.get('name')!r} did not match {package_name!r}"
        )
    if info.get("version") != version:
        raise PublishVerifyError(
            f"Version JSON info.version {info.get('version')!r} did not match {version!r}"
        )
    return filenames_from_file_entries(urls)


def filenames_from_file_entries(entries: Sequence[Any]) -> tuple[str, ...]:
    """Extract sorted filenames from PyPI JSON file entries."""
    filenames = {
        entry["filename"]
        for entry in entries
        if isinstance(entry, Mapping) and isinstance(entry.get("filename"), str)
    }
    if not filenames:
        raise PublishVerifyError("PyPI JSON file entries contained no filenames")
    return tuple(sorted(filenames))


def latest_version(payload: Mapping[str, Any]) -> str | None:
    """Return info.version from a PyPI JSON payload when available."""
    info = payload.get("info")
    if not isinstance(info, Mapping):
        return None
    version = info.get("version")
    return version if isinstance(version, str) else None


def validate_expected_files(
    package: PackageCheck,
    filenames: Sequence[str],
    *,
    source: str,
) -> tuple[str, ...]:
    """Validate expected artifacts for a package release."""
    if package.name == GEMSTONE_PACKAGE:
        expected = set(expected_gemstone_files(package.version))
        actual = set(filenames)
        missing = expected - actual
        if missing:
            raise PublishVerifyError(
                f"{source} missing files for {package.name} {package.version}: "
                f"{sorted(missing)!r}; saw {sorted(actual)!r}"
            )
        return tuple(sorted(expected))
    if package.name == NATIVE_PACKAGE:
        report = release_metadata.validate_native_artifact_filenames(
            filenames,
            version=package.version,
            package_name=package.name,
            require_exact=False,
        )
        return tuple(str(filename) for filename in report.filenames)
    raise PublishVerifyError(f"Unsupported package for publish verification: {package.name}")


def validate_simple_index(
    simple_html: str,
    *,
    package: PackageCheck,
    expected_files: Sequence[str],
) -> tuple[str, ...]:
    """Verify that expected files are linked by the simple index."""
    decoded = urllib.parse.unquote(html.unescape(simple_html))
    missing = [filename for filename in expected_files if filename not in decoded]
    if missing:
        raise PublishVerifyError(
            f"Simple index missing files for {package.name} {package.version}: {missing!r}"
        )
    return tuple(sorted(expected_files))


def verify_index(
    *,
    package: PackageCheck,
    index: str,
    install: bool,
    allow_pypi_dependencies: bool,
    fetcher: FetchText = fetch_text,
) -> IndexCheckReport:
    """Verify one package/version pair against one package index."""
    index_base_url = INDEXES[index]
    project_payload = fetch_json(
        index_project_json_url(index_base_url, package.name),
        fetcher=fetcher,
    )
    project_files = release_files_from_project_payload(
        project_payload,
        package_name=package.name,
        version=package.version,
    )
    expected_files = validate_expected_files(
        package,
        project_files,
        source=f"{index} project JSON",
    )

    version_payload = fetch_json(
        index_version_json_url(index_base_url, package.name, package.version),
        fetcher=fetcher,
    )
    version_files = release_files_from_version_payload(
        version_payload,
        package_name=package.name,
        version=package.version,
    )
    validate_expected_files(package, version_files, source=f"{index} version JSON")

    simple_files = validate_simple_index(
        fetcher(index_simple_url(index_base_url, package.name)),
        package=package,
        expected_files=expected_files,
    )

    install_report = install_package(
        package,
        index=index,
        allow_pypi_dependencies=allow_pypi_dependencies,
    ) if install else {}

    installed_version = install_report.get("installed_version")
    backend = install_report.get("backend")
    return IndexCheckReport(
        index=index,
        package_name=package.name,
        version=package.version,
        latest_version=latest_version(project_payload),
        project_json_files=project_files,
        version_json_files=version_files,
        simple_index_files=simple_files,
        installed=install,
        installed_version=installed_version if isinstance(installed_version, str) else None,
        backend=backend if isinstance(backend, str) else None,
    )


def verify_index_with_retries(
    *,
    package: PackageCheck,
    index: str,
    install: bool,
    allow_pypi_dependencies: bool,
    attempts: int,
    sleep_seconds: float,
    fetcher: FetchText = fetch_text,
) -> IndexCheckReport:
    """Verify one package/index pair with retry support for fresh publishes."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return verify_index(
                package=package,
                index=index,
                install=install,
                allow_pypi_dependencies=allow_pypi_dependencies,
                fetcher=fetcher,
            )
        except (OSError, PublishVerifyError, release_metadata.ReleaseMetadataError) as exc:
            last_error = exc
            if attempt == attempts:
                break
            print(
                f"{package.name} {package.version} on {index} not verified yet; "
                f"retrying ({attempt}/{attempts})...",
                file=sys.stderr,
            )
            time.sleep(sleep_seconds)
    if last_error is None:
        raise PublishVerifyError("Verification did not run")
    raise last_error


def install_package(
    package: PackageCheck,
    *,
    index: str,
    allow_pypi_dependencies: bool,
) -> Mapping[str, str]:
    """Install a package into a temporary virtualenv and run a smoke check."""
    with tempfile.TemporaryDirectory(prefix="gemstone-publish-verify-") as temp_dir:
        builder = venv.EnvBuilder(with_pip=True)
        builder.create(temp_dir)
        python = venv_python(Path(temp_dir))
        install_command = build_install_command(
            python,
            package,
            index=index,
            allow_pypi_dependencies=allow_pypi_dependencies,
        )
        run_checked(install_command)
        probe = build_probe(package)
        completed = run_checked([str(python), "-c", probe])
        payload = json.loads(completed.stdout)
        if not isinstance(payload, Mapping):
            raise PublishVerifyError("Install probe did not emit a JSON object")
        return {str(key): str(value) for key, value in payload.items()}


def build_install_command(
    python: Path,
    package: PackageCheck,
    *,
    index: str,
    allow_pypi_dependencies: bool,
) -> list[str]:
    """Build the isolated pip install command for an index."""
    command = [
        str(python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--index-url",
        f"{INDEXES[index]}/simple/",
    ]
    if index == "testpypi" and allow_pypi_dependencies:
        command.extend(["--extra-index-url", "https://pypi.org/simple/"])
    command.append(f"{package.name}=={package.version}")
    return command


def venv_python(root: Path) -> Path:
    """Return the Python executable path in a virtualenv."""
    candidates = (
        root / "Scripts" / "python.exe",
        root / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise PublishVerifyError(f"Could not find Python in temporary virtualenv {root}")


def build_probe(package: PackageCheck) -> str:
    """Return Python code that verifies the installed distribution."""
    if package.name == GEMSTONE_PACKAGE:
        return f"""
import importlib.metadata as metadata
import json
import gemstone_py

version = metadata.version({package.name!r})
if version != {package.version!r}:
    raise SystemExit(f"expected {package.version}, got {{version}}")
print(json.dumps({{"installed_version": version}}))
"""
    if package.name == NATIVE_PACKAGE:
        return f"""
import importlib.metadata as metadata
import json
import gemstone_py._gci as gci

version = metadata.version({package.name!r})
if version != {package.version!r}:
    raise SystemExit(f"expected {package.version}, got {{version}}")
if gci.IMPLEMENTATION != "native":
    raise SystemExit(f"expected native backend, got {{gci.IMPLEMENTATION!r}}")
if gci._smallint_to_python(gci._python_to_smallint(-42)) != -42:
    raise SystemExit("native smallint helper round trip failed")
print(json.dumps({{"installed_version": version, "backend": gci.IMPLEMENTATION}}))
"""
    raise PublishVerifyError(f"Unsupported package for install probe: {package.name}")


def run_checked(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run a command and raise a compact verification error on failure."""
    env = {**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if completed.returncode != 0:
        command_text = " ".join(command)
        output = "\n".join(
            line
            for line in (completed.stdout, completed.stderr)
            if line.strip()
        ).strip()
        raise PublishVerifyError(
            f"Command failed with exit code {completed.returncode}: {command_text}\n{output}"
        )
    return completed


def build_parser() -> argparse.ArgumentParser:
    """Build the publish verification CLI parser."""
    parser = argparse.ArgumentParser(
        prog="gemstone-publish-verify",
        description="Verify gemstone-py releases on PyPI and TestPyPI.",
    )
    parser.add_argument(
        "--package",
        choices=["all", GEMSTONE_PACKAGE, NATIVE_PACKAGE],
        default="all",
        help="Package to verify. Defaults to both gemstone-py and gemstone-py-native.",
    )
    parser.add_argument(
        "--gemstone-version",
        help="gemstone-py version to verify. Defaults to local pyproject or installed metadata.",
    )
    parser.add_argument(
        "--native-version",
        help=(
            "gemstone-py-native version to verify. Defaults to local native "
            "pyproject or installed metadata."
        ),
    )
    parser.add_argument(
        "--index",
        choices=["both", "pypi", "testpypi"],
        default="both",
        help="Package index to verify. Defaults to both PyPI and TestPyPI.",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip temporary-venv pip install smoke checks.",
    )
    parser.add_argument(
        "--allow-pypi-dependencies",
        action="store_true",
        help=(
            "When verifying TestPyPI installs, add PyPI as an extra dependency index. "
            "Leave this off for strict TestPyPI-only artifact checks."
        ),
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=3,
        help="Verification attempts per package/index. Defaults to 3.",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=10.0,
        help="Seconds to wait between verification attempts. Defaults to 10.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser


def package_checks(args: argparse.Namespace) -> tuple[PackageCheck, ...]:
    """Resolve requested package/version pairs."""
    gemstone_version = args.gemstone_version or default_version(
        Path("pyproject.toml"),
        GEMSTONE_PACKAGE,
    )
    native_version = args.native_version or default_version(
        Path("gemstone-py-native") / "pyproject.toml",
        NATIVE_PACKAGE,
    )
    checks: list[PackageCheck] = []
    if args.package in {"all", GEMSTONE_PACKAGE}:
        if not gemstone_version:
            raise PublishVerifyError("--gemstone-version is required outside a checkout")
        checks.append(PackageCheck(GEMSTONE_PACKAGE, gemstone_version))
    if args.package in {"all", NATIVE_PACKAGE}:
        if not native_version:
            raise PublishVerifyError("--native-version is required outside a checkout")
        checks.append(PackageCheck(NATIVE_PACKAGE, native_version))
    return tuple(checks)


def selected_indexes(index: str) -> tuple[str, ...]:
    """Resolve selected package indexes."""
    if index == "both":
        return ("testpypi", "pypi")
    return (index,)


def main(argv: Sequence[str] | None = None) -> int:
    """Run publish verification."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        reports = [
            verify_index_with_retries(
                package=package,
                index=index,
                install=not args.skip_install,
                allow_pypi_dependencies=args.allow_pypi_dependencies,
                attempts=args.attempts,
                sleep_seconds=args.sleep_seconds,
            )
            for package in package_checks(args)
            for index in selected_indexes(args.index)
        ]
    except (OSError, PublishVerifyError, release_metadata.ReleaseMetadataError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps([report.as_dict() for report in reports], indent=2))
        return 0

    for report in reports:
        install_text = (
            f"; installed {report.installed_version}"
            if report.installed_version
            else "; install skipped"
        )
        backend_text = f"; backend {report.backend}" if report.backend else ""
        print(
            f"Verified {report.package_name} {report.version} on {report.index}: "
            f"{len(report.project_json_files)} files{install_text}{backend_text}"
        )
    return 0


def main_entry() -> None:
    """Console-script wrapper for publish verification."""
    raise SystemExit(main())


if __name__ == "__main__":
    main_entry()
