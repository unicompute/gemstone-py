#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

if [[ -x "${repo_root}/.venv/bin/python" ]]; then
  pybin="${repo_root}/.venv/bin/python"
else
  pybin="python3"
fi

artifacts_dir="$(mktemp -d "${TMPDIR:-/tmp}/gemstone-py-build.XXXXXX")"
wheel_venv="$(mktemp -d "${TMPDIR:-/tmp}/gemstone-py-wheel-venv.XXXXXX")"
sdist_venv="$(mktemp -d "${TMPDIR:-/tmp}/gemstone-py-sdist-venv.XXXXXX")"

cleanup() {
  rm -rf \
    "${artifacts_dir}" \
    "${wheel_venv}" \
    "${sdist_venv}" \
    "${repo_root}/build" \
    "${repo_root}/gemstone_py.egg-info"
}
trap cleanup EXIT

"${pybin}" -m build --no-isolation --sdist --wheel --outdir "${artifacts_dir}"

wheel_path="$(printf '%s\n' "${artifacts_dir}"/gemstone_py-*.whl | head -n 1)"
sdist_path="$(printf '%s\n' "${artifacts_dir}"/gemstone_py-*.tar.gz | head -n 1)"

if [[ ! -f "${wheel_path}" ]]; then
  echo "Wheel build artifact not found" >&2
  exit 1
fi
if [[ ! -f "${sdist_path}" ]]; then
  echo "sdist build artifact not found" >&2
  exit 1
fi

"${pybin}" -m venv "${wheel_venv}"
"${wheel_venv}/bin/python" -m pip install "${wheel_path}"
"${wheel_venv}/bin/python" -c "import gemstone_py; print(gemstone_py.__file__)"
"${wheel_venv}/bin/python" -m gemstone_py.api_contract >/dev/null
"${wheel_venv}/bin/gemstone-benchmark-baseline-register" --help >/dev/null
"${wheel_venv}/bin/gemstone-benchmark-compare" --help >/dev/null
"${wheel_venv}/bin/gemstone-benchmarks" --help >/dev/null
"${wheel_venv}/bin/gemstone-hello"
"${wheel_venv}/bin/gemstone-examples" hello
test -x "${wheel_venv}/bin/gemstone-smalltalk-demo"

"${pybin}" -m venv --system-site-packages "${sdist_venv}"
"${sdist_venv}/bin/python" -m pip install --no-build-isolation "${sdist_path}"
"${sdist_venv}/bin/python" -c "import gemstone_py; print(gemstone_py.__file__)"
"${sdist_venv}/bin/python" -m gemstone_py.api_contract >/dev/null
"${sdist_venv}/bin/gemstone-benchmark-baseline-register" --help >/dev/null
"${sdist_venv}/bin/gemstone-benchmark-compare" --help >/dev/null
"${sdist_venv}/bin/gemstone-benchmarks" --help >/dev/null
"${sdist_venv}/bin/gemstone-hello"
"${sdist_venv}/bin/gemstone-examples" hello
test -x "${sdist_venv}/bin/gemstone-smalltalk-demo"
