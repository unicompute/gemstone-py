import pathlib
import tomllib
import unittest


class NativeCrateTests(unittest.TestCase):
    def test_native_package_metadata_targets_gci_extension_module(self) -> None:
        pyproject = tomllib.loads(
            pathlib.Path("gemstone-py-native/pyproject.toml").read_text(encoding="utf-8")
        )
        cargo = tomllib.loads(
            pathlib.Path("gemstone-py-native/Cargo.toml").read_text(encoding="utf-8")
        )

        self.assertEqual(pyproject["project"]["name"], "gemstone-py-native")
        self.assertEqual(pyproject["project"]["license"], "MIT")
        self.assertIn(
            "License :: OSI Approved :: MIT License",
            pyproject["project"]["classifiers"],
        )
        self.assertIn("Programming Language :: Rust", pyproject["project"]["classifiers"])
        self.assertEqual(
            pyproject["tool"]["maturin"]["module-name"],
            "gemstone_py_native._gci",
        )
        self.assertEqual(cargo["package"]["name"], "gemstone-py-native")
        self.assertIn("repository", cargo["package"])
        self.assertIn("homepage", cargo["package"])
        self.assertIn("documentation", cargo["package"])
        self.assertIn("pyo3", cargo["dependencies"])
        self.assertIn("abi3-py311", cargo["dependencies"]["pyo3"]["features"])
        self.assertIn("pyo3/abi3-py311", pyproject["tool"]["maturin"]["features"])

    def test_native_extension_reexports_ctypes_surface(self) -> None:
        source = pathlib.Path("gemstone-py-native/src/lib.rs").read_text(encoding="utf-8")

        self.assertIn("struct NativeGciLibrary", source)
        self.assertIn('"GciErrSType"', source)
        self.assertIn('"gci_init"', source)
        self.assertIn('wrap_pyfunction!(_load_library, module)', source)
        self.assertIn('wrap_pyfunction!(_bind, module)', source)
        self.assertIn("fn _python_to_smallint", source)
        self.assertIn('#[pyo3(name = "GciExecuteStr")]', source)
        self.assertIn('#[pyo3(name = "GciPerform")]', source)

    def test_native_extension_releases_gil_around_gci_calls(self) -> None:
        source = pathlib.Path("gemstone-py-native/src/lib.rs").read_text(encoding="utf-8")

        self.assertIn("py.detach", source)
        self.assertIn("GciLoginEx", source)
        self.assertIn("GciCommit", source)

    def test_native_check_script_covers_wheel_and_sdist_smoke(self) -> None:
        source = pathlib.Path("scripts/run_native_checks.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("cargo fmt", source)
        self.assertIn("cargo check", source)
        self.assertIn("maturin build", source)
        self.assertIn("maturin sdist", source)
        self.assertIn("cp311-abi3", source)
        self.assertIn("License-Expression: MIT", source)
        self.assertIn("Classifier: Programming Language :: Rust", source)
        self.assertIn("GEMSTONE_PY_GCI_BACKEND=native", source)
        self.assertIn("Expected native backend", source)
        self.assertIn("_smallint_to_python", source)
        self.assertIn("sdist-built wheel", source)


if __name__ == "__main__":
    unittest.main()
