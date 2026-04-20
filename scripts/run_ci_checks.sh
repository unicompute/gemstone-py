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

lint_paths=(
  gemstone_py/__init__.py
  gemstone_py/api_contract.py
  gemstone_py/benchmark_baseline_register.py
  gemstone_py/benchmark_baselines.py
  gemstone_py/benchmark_compare.py
  gemstone_py/release_metadata.py
  gemstone_py/benchmarks.py
  gemstone_py/cli.py
  gemstone_py/example_support.py
  gemstone_py/session_facade.py
  examples/example.py
  examples/misc/smalltalk_demo.py
  tests/test_api_contract.py
  tests/test_benchmark_baseline_register.py
  tests/test_benchmark_baselines.py
  tests/test_benchmark_compare.py
  tests/test_release_metadata.py
  examples/hello_gemstone.py
  tests/test_benchmarks.py
  tests/test_cli.py
  tests/test_gemstone_session_api.py
  tests/test_smalltalk_bridge.py
)

"${pybin}" -m ruff check "${lint_paths[@]}"
"${pybin}" -m mypy
"${pybin}" -m unittest discover -s tests -p 'test*.py'
"${pybin}" -m gemstone_py.api_contract --help >/dev/null
"${pybin}" -m gemstone_py.benchmark_baseline_register --help >/dev/null
"${pybin}" -m gemstone_py.benchmark_baselines --help >/dev/null
"${pybin}" -m gemstone_py.benchmark_compare --help >/dev/null
"${pybin}" -m gemstone_py.release_metadata --help >/dev/null
"${pybin}" -m gemstone_py.benchmarks --help >/dev/null
if [[ "${GS_SKIP_BUILD_SMOKE:-0}" != "1" ]]; then
  "${repo_root}/scripts/run_build_smoke.sh"
fi
