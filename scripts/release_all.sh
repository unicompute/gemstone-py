#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

run_ci=1
run_native=1
run_public_verify=1
run_vsix=1

usage() {
  cat <<'EOF'
Usage: scripts/release_all.sh [options]

Run the local and public release verification lane:
  - package tests and build smoke checks
  - native wheel checks
  - PyPI/TestPyPI publish verification
  - VSIX build and checksum generation
  - Marketplace version verification
  - GitHub release asset verification

Options:
  --skip-ci              Skip scripts/run_ci_checks.sh
  --skip-native          Skip scripts/run_native_checks.sh
  --skip-public-verify   Skip PyPI/TestPyPI, Marketplace, and GitHub release checks
  --skip-vsix            Skip VSIX build/checksum checks
  -h, --help             Show this help

Environment:
  GEMSTONE_VERSION       gemstone-py version to verify (defaults to pyproject.toml)
  NATIVE_VERSION         gemstone-py-native version to verify (defaults to native pyproject.toml)
  VSCODE_VERSION         VS Code workbench version to verify (defaults to package.json)
  PUBLISH_VERIFY_ARGS    Extra args for gemstone-publish-verify
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-ci)
      run_ci=0
      ;;
    --skip-native)
      run_native=0
      ;;
    --skip-public-verify)
      run_public_verify=0
      ;;
    --skip-vsix)
      run_vsix=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ -x "${repo_root}/.venv/bin/python" ]]; then
  pybin="${repo_root}/.venv/bin/python"
else
  pybin="python3"
fi

log() {
  printf '\n==> %s\n' "$*"
}

read_pyproject_version() {
  local path="$1"
  "${pybin}" - "$path" <<'PY'
import sys
import tomllib
from pathlib import Path

payload = tomllib.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload["project"]["version"])
PY
}

gemstone_version="${GEMSTONE_VERSION:-$(read_pyproject_version pyproject.toml)}"
native_version="${NATIVE_VERSION:-$(read_pyproject_version gemstone-py-native/pyproject.toml)}"
vscode_version="$(
  cd vscode-gemstone-py-workbench
  node -p "process.env.VSCODE_VERSION || require('./package.json').version"
)"

log "Release versions"
printf 'gemstone-py: %s\n' "${gemstone_version}"
printf 'gemstone-py-native: %s\n' "${native_version}"
printf 'gemstone-py Workbench: %s\n' "${vscode_version}"

if [[ "${run_ci}" == "1" ]]; then
  log "Package tests and build smoke checks"
  "${repo_root}/scripts/run_ci_checks.sh"
fi

if [[ "${run_native}" == "1" ]]; then
  log "Native wheel checks"
  "${repo_root}/scripts/run_native_checks.sh"
fi

if [[ "${run_public_verify}" == "1" ]]; then
  log "PyPI and TestPyPI verification"
  # shellcheck disable=SC2206
  extra_publish_args=(${PUBLISH_VERIFY_ARGS:-})
  "${pybin}" -m gemstone_py.publish_verify \
    --gemstone-version "${gemstone_version}" \
    --native-version "${native_version}" \
    "${extra_publish_args[@]}"
fi

if [[ "${run_vsix}" == "1" ]]; then
  log "VSIX build and checksum"
  (
    cd vscode-gemstone-py-workbench
    npm ci
    npm run compile
    npm run check
    npm run test:smoke
    if [[ "${SKIP_VSCODE_INTEGRATION:-0}" != "1" ]]; then
      if command -v xvfb-run >/dev/null 2>&1; then
        xvfb-run -a npm run test:integration
      else
        npm run test:integration
      fi
    fi
    npm run release:preflight
    npx vsce package --no-dependencies
    npm run release:verify-vsix
    checksum_file="gemstone-py-workbench-${vscode_version}.vsix.sha256"
    if command -v sha256sum >/dev/null 2>&1; then
      sha256sum "gemstone-py-workbench-${vscode_version}.vsix" > "${checksum_file}"
    else
      shasum -a 256 "gemstone-py-workbench-${vscode_version}.vsix" > "${checksum_file}"
    fi
  )
fi

if [[ "${run_public_verify}" == "1" ]]; then
  log "Marketplace version verification"
  (
    cd vscode-gemstone-py-workbench
    npx vsce show unicompute.gemstone-py-workbench --json > marketplace.json
    EXPECTED_VERSION="${vscode_version}" node -e '
    const fs = require("fs");
    const expected = process.env.EXPECTED_VERSION;
    const payload = JSON.parse(fs.readFileSync("marketplace.json", "utf8"));
    const versions = (payload.versions || []).map((entry) => entry.version);
    const publisher = payload.publisher || {};
    if (payload.displayName !== "gemstone-py Workbench") {
      throw new Error(`Unexpected Marketplace display name: ${payload.displayName}`);
    }
    if (publisher.domain !== "https://unicompute.com") {
      throw new Error(`Unexpected Marketplace publisher domain: ${publisher.domain}`);
    }
    if (publisher.isDomainVerified !== true) {
      const message = "Marketplace publisher domain is not verified for unicompute.com";
      if (process.env.REQUIRE_VSCODE_DOMAIN_VERIFIED === "1") {
        throw new Error(message);
      }
      console.warn(`WARNING: ${message}`);
    }
    if (versions[0] !== expected) {
      throw new Error(`Marketplace latest version is ${versions[0]}, expected ${expected}`);
    }
    '
  )

  log "GitHub release asset verification"
  gh release view "v${gemstone_version}" --json assets,url > package-release.json
  GEMSTONE_VERSION="${gemstone_version}" node -e '
  const fs = require("fs");
  const version = process.env.GEMSTONE_VERSION;
  const payload = JSON.parse(fs.readFileSync("package-release.json", "utf8"));
  const names = (payload.assets || []).map((asset) => asset.name);
  for (const expected of [
    `gemstone_py-${version}-py3-none-any.whl`,
    `gemstone_py-${version}.tar.gz`,
    "SHA256SUMS",
  ]) {
    if (!names.includes(expected)) {
      throw new Error(`GitHub release ${payload.url} is missing ${expected}`);
    }
  }
  '

  gh release view "vscode-workbench-v${vscode_version}" --json assets,url > vscode-release.json
  VSCODE_VERSION="${vscode_version}" node -e '
  const fs = require("fs");
  const version = process.env.VSCODE_VERSION;
  const payload = JSON.parse(fs.readFileSync("vscode-release.json", "utf8"));
  const names = (payload.assets || []).map((asset) => asset.name);
  for (const expected of [
    `gemstone-py-workbench-${version}.vsix`,
    `gemstone-py-workbench-${version}.vsix.sha256`,
  ]) {
    if (!names.includes(expected)) {
      throw new Error(`GitHub release ${payload.url} is missing ${expected}`);
    }
  }
  '
fi

log "Release verification complete"
