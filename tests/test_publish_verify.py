import json
import pathlib
import unittest

from gemstone_py import publish_verify


def _pure_files(version: str = "0.2.10") -> list[str]:
    return [
        f"gemstone_py-{version}-py3-none-any.whl",
        f"gemstone_py-{version}.tar.gz",
    ]


def _native_files(version: str = "0.1.2") -> list[str]:
    return [
        f"gemstone_py_native-{version}.tar.gz",
        f"gemstone_py_native-{version}-cp311-abi3-manylinux_2_31_x86_64.whl",
        f"gemstone_py_native-{version}-cp311-abi3-manylinux_2_31_aarch64.whl",
        f"gemstone_py_native-{version}-cp311-abi3-manylinux_2_34_armv7l.whl",
        f"gemstone_py_native-{version}-cp311-abi3-macosx_10_12_x86_64.whl",
        f"gemstone_py_native-{version}-cp311-abi3-macosx_11_0_arm64.whl",
        f"gemstone_py_native-{version}-cp311-abi3-win_amd64.whl",
        f"gemstone_py_native-{version}-cp311-abi3-win_arm64.whl",
    ]


def _project_payload(package_name: str, version: str, filenames: list[str]) -> str:
    return json.dumps(
        {
            "info": {
                "name": package_name,
                "version": version,
                "classifiers": [
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
                version: [{"filename": filename} for filename in filenames],
            },
        }
    )


def _version_payload(package_name: str, version: str, filenames: list[str]) -> str:
    payload = json.loads(_project_payload(package_name, version, filenames))
    payload["urls"] = payload["releases"][version]
    del payload["releases"]
    return json.dumps(payload)


class PublishVerifyTests(unittest.TestCase):
    def test_verify_index_checks_project_version_and_simple_indexes(self):
        version = "0.2.10"
        files = _pure_files(version)

        def fetcher(url: str) -> str:
            if f"/pypi/gemstone-py/{version}/json" in url:
                return _version_payload("gemstone-py", version, files)
            if "/pypi/gemstone-py/json" in url:
                return _project_payload("gemstone-py", version, files)
            if "/simple/gemstone-py/" in url:
                return "\n".join(f'<a href="{filename}">{filename}</a>' for filename in files)
            raise AssertionError(f"unexpected URL {url}")

        report = publish_verify.verify_index(
            package=publish_verify.PackageCheck("gemstone-py", version),
            index="testpypi",
            install=False,
            allow_pypi_dependencies=False,
            fetcher=fetcher,
        )

        self.assertEqual(report.package_name, "gemstone-py")
        self.assertEqual(report.version, version)
        self.assertEqual(report.index, "testpypi")
        self.assertEqual(set(report.project_json_files), set(files))
        self.assertFalse(report.installed)

    def test_verify_index_checks_native_platform_artifacts(self):
        version = "0.1.2"
        files = _native_files(version)

        def fetcher(url: str) -> str:
            if f"/pypi/gemstone-py-native/{version}/json" in url:
                return _version_payload("gemstone-py-native", version, files)
            if "/pypi/gemstone-py-native/json" in url:
                return _project_payload("gemstone-py-native", version, files)
            if "/simple/gemstone-py-native/" in url:
                return "\n".join(f'<a href="{filename}">{filename}</a>' for filename in files)
            raise AssertionError(f"unexpected URL {url}")

        report = publish_verify.verify_index(
            package=publish_verify.PackageCheck("gemstone-py-native", version),
            index="pypi",
            install=False,
            allow_pypi_dependencies=False,
            fetcher=fetcher,
        )

        self.assertEqual(report.package_name, "gemstone-py-native")
        self.assertEqual(len(report.project_json_files), 8)
        self.assertIn(
            f"gemstone_py_native-{version}-cp311-abi3-win_arm64.whl",
            report.simple_index_files,
        )

    def test_simple_index_reports_missing_expected_files(self):
        with self.assertRaisesRegex(publish_verify.PublishVerifyError, "Simple index"):
            publish_verify.validate_simple_index(
                "<a>gemstone_py-0.2.10.tar.gz</a>",
                package=publish_verify.PackageCheck("gemstone-py", "0.2.10"),
                expected_files=_pure_files(),
            )

    def test_testpypi_install_command_is_strict_unless_extra_deps_enabled(self):
        package = publish_verify.PackageCheck("gemstone-py-native", "0.1.2")

        strict_command = publish_verify.build_install_command(
            pathlib.Path("/tmp/venv/bin/python"),
            package,
            index="testpypi",
            allow_pypi_dependencies=False,
        )
        relaxed_command = publish_verify.build_install_command(
            pathlib.Path("/tmp/venv/bin/python"),
            package,
            index="testpypi",
            allow_pypi_dependencies=True,
        )

        self.assertNotIn("--extra-index-url", strict_command)
        self.assertIn("--extra-index-url", relaxed_command)
        self.assertIn("gemstone-py-native==0.1.2", relaxed_command)


if __name__ == "__main__":
    unittest.main()
