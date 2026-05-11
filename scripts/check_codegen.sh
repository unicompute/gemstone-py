#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

if [[ -x "${repo_root}/.venv/bin/python" ]]; then
  pybin="${repo_root}/.venv/bin/python"
else
  pybin="python3"
fi

"${pybin}" -m gemstone_py.codegen \
  --module examples.typed_access.codegen_demo.models \
  --output examples/typed_access/codegen_demo/generated \
  --check
