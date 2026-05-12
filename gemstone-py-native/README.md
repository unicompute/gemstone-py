# gemstone-py-native

Optional PyO3 extension for `gemstone-py`.

The extension exports `gemstone_py_native._gci`, which matches the Python
`gemstone_py._gci` shim surface. The reusable GCI loader and raw ABI calls live
in `../crates/gemstone-gci`; this package is the thin PyO3 wrapper around that
shared Rust core. It exposes a `NativeGciLibrary` object with Rust-backed GCI
methods, releases the GIL around blocking GCI calls, and replaces hot OOP tag
helpers with native implementations. Wheels are built with the Python 3.11
stable ABI.

Direct Rust applications should use the separate `gemstone-rs` workspace. When
checked out beside `gemstone-py`, it lives at `../../gemstone-rs` from this
directory. It provides the safe Rust `Config` and `Session` API over the same
low-level GCI layer. Rust code imports it as `gemstone_rs`.

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

Run the direct Rust example:

```bash
cd ../../gemstone-rs
cargo run -p gemstone-rs --example eval
```

The repository workflow `Native Wheels` builds platform wheels for Linux x86_64,
Linux aarch64, Linux ARMv7, macOS x86_64, macOS aarch64, Windows x86_64, and Windows ARM64.
Manual workflow runs can publish the merged wheel set to TestPyPI or PyPI using trusted
publishing. The workflow also builds the generated native sdist back into a
wheel before uploading it, so missing source files fail before publish.
