#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./scripts/bootstrap_self_hosted_runner.sh [options]

Options:
  --repo-slug OWNER/REPO       GitHub repository slug
  --runner-root PATH           Runner installation directory
  --runner-name NAME           Registered runner name
  --runner-version VERSION     Actions runner version to download/configure
  --labels CSV                 Comma-separated runner labels
  --work-folder NAME           Runner work folder name
  --token TOKEN                Explicit registration token
  --help                       Show this message

Environment fallback:
  REPO_SLUG, RUNNER_ROOT, RUNNER_NAME, RUNNER_VERSION, RUNNER_LABELS,
  RUNNER_WORK_FOLDER, RUNNER_TOKEN

This script downloads or refreshes a macOS ARM64 self-hosted runner, configures
the local tool cache directory, and registers the runner with --replace.
If gh is installed and authenticated, it can mint the registration token
automatically for the target repository.
EOF
}

REPO_SLUG="${REPO_SLUG:-unicompute/gemstone-py}"
RUNNER_ROOT="${RUNNER_ROOT:-/Users/tariq/src/actions-runner-gemstone-py}"
RUNNER_NAME="${RUNNER_NAME:-gemstone-py-local-arm64}"
RUNNER_VERSION="${RUNNER_VERSION:-2.333.1}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted,macOS,ARM64,gemstone-py-local}"
RUNNER_WORK_FOLDER="${RUNNER_WORK_FOLDER:-_work}"
RUNNER_TOKEN="${RUNNER_TOKEN:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-slug)
      REPO_SLUG="$2"
      shift 2
      ;;
    --runner-root)
      RUNNER_ROOT="$2"
      shift 2
      ;;
    --runner-name)
      RUNNER_NAME="$2"
      shift 2
      ;;
    --runner-version)
      RUNNER_VERSION="$2"
      shift 2
      ;;
    --labels)
      RUNNER_LABELS="$2"
      shift 2
      ;;
    --work-folder)
      RUNNER_WORK_FOLDER="$2"
      shift 2
      ;;
    --token)
      RUNNER_TOKEN="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

RUNNER_URL="https://github.com/${REPO_SLUG}"
RUNNER_ARCHIVE="actions-runner-osx-arm64-${RUNNER_VERSION}.tar.gz"
RUNNER_DOWNLOAD_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_ARCHIVE}"
TOOL_CACHE_ROOT="${RUNNER_ROOT}/hostedtoolcache"

if [[ -z "${RUNNER_TOKEN}" ]]; then
  if command -v gh >/dev/null 2>&1; then
    RUNNER_TOKEN="$(gh api -X POST "repos/${REPO_SLUG}/actions/runners/registration-token" --jq .token)"
  else
    echo "RUNNER_TOKEN is not set and gh is unavailable; cannot mint a registration token." >&2
    exit 1
  fi
fi

mkdir -p "${RUNNER_ROOT}"
cd "${RUNNER_ROOT}"

if [[ ! -x ./config.sh ]]; then
  if [[ ! -f "${RUNNER_ARCHIVE}" ]]; then
    curl -fL -o "${RUNNER_ARCHIVE}" "${RUNNER_DOWNLOAD_URL}"
  fi
  tar xzf "${RUNNER_ARCHIVE}"
fi

mkdir -p "${TOOL_CACHE_ROOT}" "${RUNNER_WORK_FOLDER}"

tmp_env="$(mktemp)"
if [[ -f .env ]]; then
  grep -vE '^(RUNNER_TOOL_CACHE|AGENT_TOOLSDIRECTORY|LANG)=' .env > "${tmp_env}" || true
fi
printf 'LANG=%s\n' "${LANG:-en_GB.UTF-8}" >> "${tmp_env}"
printf 'RUNNER_TOOL_CACHE=%s\n' "${TOOL_CACHE_ROOT}" >> "${tmp_env}"
printf 'AGENT_TOOLSDIRECTORY=%s\n' "${TOOL_CACHE_ROOT}" >> "${tmp_env}"
mv "${tmp_env}" .env

./config.sh \
  --unattended \
  --replace \
  --url "${RUNNER_URL}" \
  --token "${RUNNER_TOKEN}" \
  --name "${RUNNER_NAME}" \
  --labels "${RUNNER_LABELS}" \
  --work "${RUNNER_WORK_FOLDER}"

cat <<EOF
Runner configured.
  repo:         ${REPO_SLUG}
  root:         ${RUNNER_ROOT}
  name:         ${RUNNER_NAME}
  labels:       ${RUNNER_LABELS}
  tool cache:   ${TOOL_CACHE_ROOT}
  work folder:  ${RUNNER_WORK_FOLDER}

Next step:
  ./scripts/install_self_hosted_runner_service.sh install --runner-root "${RUNNER_ROOT}" --start
EOF
