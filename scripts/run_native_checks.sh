#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

if [[ -x "${repo_root}/.venv/bin/python" ]]; then
  pybin="${repo_root}/.venv/bin/python"
else
  pybin="python3"
fi

native_root="${repo_root}/gemstone-py-native"
artifacts_dir="$(mktemp -d "${TMPDIR:-/tmp}/gemstone-py-native.XXXXXX")"
native_venv="$(mktemp -d "${TMPDIR:-/tmp}/gemstone-py-native-venv.XXXXXX")"

cleanup() {
  rm -rf "${artifacts_dir}" "${native_venv}"
}
trap cleanup EXIT

cargo fmt --manifest-path "${native_root}/Cargo.toml" --check
cargo check \
  --manifest-path "${native_root}/Cargo.toml" \
  --target-dir "${artifacts_dir}/cargo-check-target"

"${pybin}" -m maturin build \
  --manifest-path "${native_root}/Cargo.toml" \
  --out "${artifacts_dir}/wheel" \
  --target-dir "${artifacts_dir}/wheel-target"

wheel_path="$(printf '%s\n' "${artifacts_dir}"/wheel/gemstone_py_native-*.whl | head -n 1)"
if [[ ! -f "${wheel_path}" ]]; then
  echo "Native wheel build artifact not found" >&2
  exit 1
fi

"${pybin}" - "${wheel_path}" <<'PY'
import sys
from pathlib import Path
from zipfile import ZipFile

wheel = Path(sys.argv[1])
if "cp311-abi3" not in wheel.name:
    raise SystemExit(f"Native wheel is not abi3 tagged: {wheel.name}")

with ZipFile(wheel) as archive:
    metadata_name = next(
        name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
    )
    metadata = archive.read(metadata_name).decode("utf-8")

for expected in [
    "Name: gemstone-py-native",
    "License-Expression: MIT",
    "Classifier: License :: OSI Approved :: MIT License",
    "Classifier: Programming Language :: Rust",
]:
    if expected not in metadata:
        raise SystemExit(f"Native wheel metadata missing {expected!r}")
PY

"${pybin}" -m venv "${native_venv}"
"${native_venv}/bin/python" -m pip install --no-deps "${wheel_path}"
PYTHONPATH="${repo_root}" \
  GEMSTONE_PY_GCI_BACKEND=native \
  "${native_venv}/bin/python" - <<'PY'
import gemstone_py._gci as gci

if gci.IMPLEMENTATION != "native":
    raise SystemExit(f"Expected native backend, got {gci.IMPLEMENTATION!r}")
if gci._smallint_to_python(gci._python_to_smallint(-42)) != -42:
    raise SystemExit("Native smallint helper round trip failed")
PY

"${pybin}" -m maturin sdist \
  --manifest-path "${native_root}/Cargo.toml" \
  --out "${artifacts_dir}/sdist"

sdist_path="$(printf '%s\n' "${artifacts_dir}"/sdist/gemstone_py_native-*.tar.gz | head -n 1)"
if [[ ! -f "${sdist_path}" ]]; then
  echo "Native sdist build artifact not found" >&2
  exit 1
fi

"${pybin}" - "${sdist_path}" "${artifacts_dir}" <<'PY'
import subprocess
import sys
import tarfile
from pathlib import Path

archive_path = Path(sys.argv[1])
artifacts_dir = Path(sys.argv[2])
extract_root = artifacts_dir / "sdist-src"
wheel_dir = artifacts_dir / "sdist-wheel"

with tarfile.open(archive_path) as archive:
    archive.extractall(extract_root)

manifests = [
    manifest
    for manifest in sorted(extract_root.glob("**/Cargo.toml"))
    if 'name = "gemstone-py-native"' in manifest.read_text(encoding="utf-8")
]
if len(manifests) != 1:
    raise SystemExit(f"Expected one native package Cargo.toml from sdist, got {manifests!r}")

subprocess.run(
    [
        sys.executable,
        "-m",
        "maturin",
        "build",
        "--manifest-path",
        str(manifests[0]),
        "--out",
        str(wheel_dir),
        "--target-dir",
        str(artifacts_dir / "sdist-target"),
    ],
    check=True,
)

wheels = sorted(wheel_dir.glob("gemstone_py_native-*.whl"))
if len(wheels) != 1:
    raise SystemExit(f"Expected one native sdist-built wheel, got {wheels!r}")
if "cp311-abi3" not in wheels[0].name:
    raise SystemExit(f"Native sdist-built wheel is not abi3 tagged: {wheels[0].name}")
PY

echo "Native checks passed"
