# gemstone-py-native

Optional PyO3 extension for `gemstone-py`.

The extension exports `gemstone_py_native._gci`, which matches the Python
`gemstone_py._gci` shim surface. It loads `libgcirpc` with `libloading`,
exposes a `NativeGciLibrary` object with Rust-backed GCI methods, releases the
GIL around blocking GCI calls, and replaces hot OOP tag helpers with native
implementations. Wheels are built with the Python 3.11 stable ABI.

Build locally:

```bash
python -m pip install maturin
cd gemstone-py-native
maturin develop
```

Package wheels:

```bash
cd gemstone-py-native
maturin build --release
```

The repository workflow `Native Wheels` builds platform wheels for Linux x86_64,
Linux aarch64, macOS x86_64, macOS aarch64, and Windows x86_64. Manual workflow
runs can publish the merged wheel set to TestPyPI or PyPI using trusted
publishing. The workflow also builds the generated native sdist back into a
wheel before uploading it, so missing source files fail before publish.
