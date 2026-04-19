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
  gemstone_py/cli.py
  gemstone_py/example_support.py
  gemstone_py/session_facade.py
  examples/example.py
  examples/misc/smalltalk_demo.py
  examples/hello_gemstone.py
  tests/test_cli.py
  tests/test_gemstone_session_api.py
  tests/test_smalltalk_bridge.py
)

"${pybin}" -m ruff check "${lint_paths[@]}"
"${pybin}" -m mypy
"${pybin}" -m unittest discover -s tests -p 'test*.py'
"${repo_root}/scripts/run_build_smoke.sh"
