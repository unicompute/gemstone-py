#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

if [[ -x "${repo_root}/.venv/bin/python" ]]; then
  pybin="${repo_root}/.venv/bin/python"
else
  pybin="python3"
fi

"${pybin}" -m compileall gemstone_py tests examples
"${pybin}" -m ruff check .
"${pybin}" -m mypy
"${repo_root}/scripts/check_codegen.sh"
"${pybin}" -m unittest discover -s tests -p 'test*.py'
"${pybin}" -m gemstone_py.api_contract --help >/dev/null
"${pybin}" -m gemstone_py.benchmark_baseline_register --help >/dev/null
"${pybin}" -m gemstone_py.benchmark_baselines --help >/dev/null
"${pybin}" -m gemstone_py.benchmark_compare --help >/dev/null
"${pybin}" -m gemstone_py.release_metadata --help >/dev/null
"${pybin}" -m gemstone_py.publish_verify --help >/dev/null
"${pybin}" -m gemstone_py.benchmarks --help >/dev/null
if [[ "${GS_SKIP_BUILD_SMOKE:-0}" != "1" ]]; then
  "${repo_root}/scripts/run_build_smoke.sh"
fi
