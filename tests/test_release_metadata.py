import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from gemstone_py import release_metadata


def _write_release_files(
    directory: pathlib.Path,
    *,
    version: str = "0.1.0",
    changelog_version: str | None = "0.1.0",
) -> tuple[pathlib.Path, pathlib.Path]:
    pyproject_path = directory / "pyproject.toml"
    changelog_path = directory / "CHANGELOG.md"
    pyproject_path.write_text(
        f"""
[project]
name = "gemstone-py"
version = "{version}"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    changelog_entry = (
        f"## {changelog_version} - 2026-04-20\n\n- Released.\n"
        if changelog_version is not None
        else "## Unreleased\n\n- Pending.\n"
    )
    changelog_path.write_text(
        "# Changelog\n\n" + changelog_entry,
        encoding="utf-8",
    )
    return pyproject_path, changelog_path


def _native_filenames() -> list[str]:
    return [
        "gemstone_py_native-0.1.0.tar.gz",
        "gemstone_py_native-0.1.0-cp311-abi3-manylinux_2_17_x86_64.whl",
        "gemstone_py_native-0.1.0-cp311-abi3-manylinux_2_17_aarch64.whl",
        "gemstone_py_native-0.1.0-cp311-abi3-manylinux_2_17_armv7l.whl",
        "gemstone_py_native-0.1.0-cp311-abi3-macosx_10_12_x86_64.whl",
        "gemstone_py_native-0.1.0-cp311-abi3-macosx_11_0_arm64.whl",
        "gemstone_py_native-0.1.0-cp311-abi3-win_amd64.whl",
        "gemstone_py_native-0.1.0-cp311-abi3-win_arm64.whl",
    ]


def _native_payload() -> dict[str, object]:
    filenames = _native_filenames()
    return {
        "info": {
            "name": "gemstone-py-native",
            "version": "0.1.0",
            "classifiers": [
                "Development Status :: 4 - Beta",
                "License :: OSI Approved :: MIT License",
                "Programming Language :: Python :: 3.11",
                "Programming Language :: Rust",
            ],
            "project_urls": {
                "Homepage": "https://github.com/unicompute/gemstone-py",
                "Repository": "https://github.com/unicompute/gemstone-py",
                "Issues": "https://github.com/unicompute/gemstone-py/issues",
            },
        },
        "releases": {
            "0.1.0": [{"filename": filename} for filename in filenames],
        },
    }


class ReleaseMetadataTests(unittest.TestCase):
    def test_normalize_tag_handles_refs_and_v_prefix(self):
        self.assertEqual(release_metadata.normalize_tag("refs/tags/v0.1.0"), "0.1.0")
        self.assertEqual(release_metadata.normalize_tag("v0.1.0"), "0.1.0")
        self.assertEqual(release_metadata.normalize_tag("0.1.0"), "0.1.0")

    def test_changelog_has_version_matches_heading(self):
        self.assertTrue(
            release_metadata.changelog_has_version(
                "# Changelog\n\n## 0.1.0 - 2026-04-20\n",
                "0.1.0",
            )
        )
        self.assertFalse(
            release_metadata.changelog_has_version(
                "# Changelog\n\n## Unreleased\n",
                "0.1.0",
            )
        )

    def test_validate_release_metadata_accepts_matching_tag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pyproject_path, changelog_path = _write_release_files(pathlib.Path(temp_dir))
            report = release_metadata.validate_release_metadata(
                pyproject_path=pyproject_path,
                changelog_path=changelog_path,
                tag="v0.1.0",
            )

        self.assertEqual(report.version, "0.1.0")
        self.assertEqual(report.normalized_tag, "0.1.0")
        self.assertTrue(report.changelog_contains_version)
        self.assertTrue(report.tag_matches_version)

    def test_validate_release_metadata_rejects_missing_changelog_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pyproject_path, changelog_path = _write_release_files(
                pathlib.Path(temp_dir),
                changelog_version=None,
            )
            with self.assertRaises(release_metadata.ReleaseMetadataError):
                release_metadata.validate_release_metadata(
                    pyproject_path=pyproject_path,
                    changelog_path=changelog_path,
                )

    def test_main_emits_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pyproject_path, changelog_path = _write_release_files(pathlib.Path(temp_dir))
            stream = io.StringIO()
            with redirect_stdout(stream):
                exit_code = release_metadata.main(
                    [
                        "--pyproject",
                        str(pyproject_path),
                        "--changelog",
                        str(changelog_path),
                        "--tag",
                        "v0.1.0",
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["version"], "0.1.0")
        self.assertEqual(payload["normalized_tag"], "0.1.0")

    def test_main_returns_error_for_mismatched_tag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pyproject_path, changelog_path = _write_release_files(pathlib.Path(temp_dir))
            error_stream = io.StringIO()
            with redirect_stderr(error_stream):
                exit_code = release_metadata.main(
                    [
                        "--pyproject",
                        str(pyproject_path),
                        "--changelog",
                        str(changelog_path),
                        "--tag",
                        "v0.2.0",
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertIn("does not match project.version", error_stream.getvalue())

    def test_validate_native_pypi_release_accepts_expected_files(self):
        payload = _native_payload()

        report = release_metadata.validate_native_pypi_release(
            payload,
            version="0.1.0",
        )

        self.assertEqual(report.package_name, "gemstone-py-native")
        self.assertEqual(report.version, "0.1.0")
        self.assertEqual(report.project_latest_version, "0.1.0")
        self.assertEqual(report.expected_sdist, "gemstone_py_native-0.1.0.tar.gz")
        self.assertIn("Programming Language :: Rust", report.classifiers)
        self.assertIn(
            "gemstone_py_native-0.1.0-cp311-abi3-manylinux_2_17_x86_64.whl",
            report.filenames,
        )

    def test_validate_native_pypi_release_rejects_missing_platform_wheel(self):
        payload = _native_payload()
        payload["releases"]["0.1.0"] = [
            entry
            for entry in payload["releases"]["0.1.0"]
            if "win_amd64" not in entry["filename"]
        ]

        with self.assertRaisesRegex(
            release_metadata.ReleaseMetadataError,
            "Missing native wheel",
        ):
            release_metadata.validate_native_pypi_release(payload, version="0.1.0")

    def test_validate_native_artifact_filenames_accepts_exact_publish_set(self):
        report = release_metadata.validate_native_artifact_filenames(
            _native_filenames(),
            version="0.1.0",
        )

        self.assertEqual(report.expected_sdist, "gemstone_py_native-0.1.0.tar.gz")
        self.assertEqual(len(report.filenames), 8)

    def test_validate_native_artifact_filenames_rejects_extra_artifact(self):
        with self.assertRaisesRegex(
            release_metadata.ReleaseMetadataError,
            "Unexpected native artifacts",
        ):
            release_metadata.validate_native_artifact_filenames(
                [*_native_filenames(), "native-sdist-build-smoke.whl"],
                version="0.1.0",
            )

    def test_main_verifies_native_artifact_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_dir = pathlib.Path(temp_dir)
            for filename in _native_filenames():
                (artifact_dir / filename).write_text("", encoding="utf-8")
            stream = io.StringIO()
            with redirect_stdout(stream):
                exit_code = release_metadata.main(
                    [
                        "--native-artifacts-dir",
                        str(artifact_dir),
                        "--native-version",
                        "0.1.0",
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["package_name"], "gemstone-py-native")
        self.assertEqual(payload["version"], "0.1.0")
        self.assertEqual(len(payload["filenames"]), 8)

    def test_validate_native_pypi_release_accepts_non_latest_release(self):
        payload = _native_payload()
        payload["info"]["version"] = "0.2.0"

        report = release_metadata.validate_native_pypi_release(
            payload,
            version="0.1.0",
        )

        self.assertEqual(report.version, "0.1.0")
        self.assertEqual(report.project_latest_version, "0.2.0")

    def test_validate_native_pypi_release_rejects_missing_classifier(self):
        payload = _native_payload()
        payload["info"]["classifiers"] = [
            "License :: OSI Approved :: MIT License",
            "Programming Language :: Python :: 3.11",
        ]

        with self.assertRaisesRegex(
            release_metadata.ReleaseMetadataError,
            "Missing native classifier",
        ):
            release_metadata.validate_native_pypi_release(payload, version="0.1.0")

    def test_main_verifies_native_pypi_release_json(self):
        stream = io.StringIO()
        with mock.patch.object(
            release_metadata,
            "wait_for_native_pypi_release",
            return_value=_native_payload(),
        ) as wait_for_release:
            with redirect_stdout(stream):
                exit_code = release_metadata.main(
                    [
                        "--native-pypi-json-url",
                        "https://test.pypi.org/pypi/gemstone-py-native/json",
                        "--native-version",
                        "0.1.0",
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 0)
        wait_for_release.assert_called_once()
        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["package_name"], "gemstone-py-native")
        self.assertEqual(payload["version"], "0.1.0")


if __name__ == "__main__":
    unittest.main()
