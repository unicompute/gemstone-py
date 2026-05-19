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
        self.assertIn("gemstone-gci", cargo["dependencies"])
        self.assertIn("gemstone-rs", cargo["dependencies"])
        self.assertEqual(cargo["dependencies"]["gemstone-rs"]["version"], "0.2.2")
        self.assertIn("abi3-py311", cargo["dependencies"]["pyo3"]["features"])
        self.assertIn("pyo3/abi3-py311", pyproject["tool"]["maturin"]["features"])

    def test_rust_workspace_keeps_native_gci_crate_self_contained(self) -> None:
        workspace = tomllib.loads(pathlib.Path("Cargo.toml").read_text(encoding="utf-8"))
        gci = tomllib.loads(
            pathlib.Path("crates/gemstone-gci/Cargo.toml").read_text(encoding="utf-8")
        )

        self.assertIn("crates/gemstone-gci", workspace["workspace"]["members"])
        self.assertNotIn("crates/gemstone-rs", workspace["workspace"]["members"])
        self.assertNotIn("gemstone-py-native", workspace["workspace"]["members"])
        self.assertEqual(gci["package"]["name"], "gemstone-gci")

    def test_docs_point_rust_users_to_gemstone_rs(self) -> None:
        readme = pathlib.Path("README.md").read_text(encoding="utf-8")
        rust_doc = pathlib.Path("docs/rust-client.md").read_text(encoding="utf-8")

        self.assertIn("separate `gemstone-rs` workspace", readme)
        self.assertIn("gemstone_rs", readme)
        self.assertIn("gemstone-rs/crates/gemstone-rs", rust_doc)
        self.assertIn("Session::login", rust_doc)
        self.assertIn("GS_RUN_LIVE_RUST", readme)

    def test_low_level_rust_crate_exposes_oop_helpers(self) -> None:
        source = pathlib.Path("crates/gemstone-gci/src/lib.rs").read_text(
            encoding="utf-8"
        )

        self.assertIn("pub fn from_smallint", source)
        self.assertIn("pub fn from_bool", source)
        self.assertIn("pub fn from_char", source)
        self.assertIn("pub fn char_to_oop", source)

    def test_native_extension_reexports_ctypes_surface(self) -> None:
        source = pathlib.Path("gemstone-py-native/src/lib.rs").read_text(encoding="utf-8")

        self.assertIn("struct NativeGciLibrary", source)
        self.assertIn("GciLibrary", source)
        self.assertIn('"GciErrSType"', source)
        self.assertIn('"gci_init"', source)
        self.assertIn("struct RustCoreSession", source)
        self.assertIn("PyNativeSession::login_from_env", source)
        self.assertIn("fn rust_core_capabilities_json", source)
        self.assertIn("fn rust_core_compatibility_json", source)
        self.assertIn("fn rust_core_conformance_json", source)
        self.assertIn("fn eval_json", source)
        self.assertIn("fn perform_json", source)
        self.assertIn("fn value_to_oop_symbol", source)
        self.assertIn("RustCoreSession", source)
        self.assertIn('"rust_core_capabilities_json"', source)
        self.assertIn('wrap_pyfunction!(_load_library, module)', source)
        self.assertIn('wrap_pyfunction!(_bind, module)', source)
        self.assertIn("wrap_pyfunction!(rust_core_capabilities_json, module)", source)
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
        self.assertIn('name = "gemstone-py-native"', source)
        self.assertIn("License-Expression: MIT", source)
        self.assertIn("Classifier: Programming Language :: Rust", source)
        self.assertIn("GEMSTONE_PY_GCI_BACKEND=native", source)
        self.assertIn("Expected native backend", source)
        self.assertIn("_smallint_to_python", source)
        self.assertIn("PIP_NO_CACHE_DIR=1", source)
        self.assertIn("rust_core_available", source)
        self.assertIn("Expected gemstone-rs shared core bridge from sdist install", source)


if __name__ == "__main__":
    unittest.main()
