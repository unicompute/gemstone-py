import io
import json
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

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


if __name__ == "__main__":
    unittest.main()
