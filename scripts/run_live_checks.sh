#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

if [[ -x "${repo_root}/.venv/bin/python" ]]; then
  pybin="${repo_root}/.venv/bin/python"
else
  pybin="python3"
fi

export GS_RUN_LIVE="${GS_RUN_LIVE:-1}"
export GS_RUN_DESTRUCTIVE_LIVE="${GS_RUN_DESTRUCTIVE_LIVE:-0}"
export GS_RUN_LIVE_SOAK="${GS_RUN_LIVE_SOAK:-0}"
"${pybin}" -m unittest tests.test_live_smoke tests.test_live_integration
