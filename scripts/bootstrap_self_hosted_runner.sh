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
  --check                      Report runner install, service, and GitHub status
  --upgrade                    Upgrade the installed runner in place to --runner-version
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
CHECK_ONLY=0
UPGRADE_ONLY=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_TEMPLATE="${SCRIPT_DIR}/actions.runner.macos.plist.template"

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
    --check)
      CHECK_ONLY=1
      shift
      ;;
    --upgrade)
      UPGRADE_ONLY=1
      shift
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
RUNNER_JSON_PATH="${RUNNER_ROOT}/.runner"
SERVICE_CONFIG_PATH="${RUNNER_ROOT}/.service"

current_runner_version() {
  if [[ ! -f "${RUNNER_ROOT}/bin/Runner.Listener.deps.json" ]]; then
    return 1
  fi
  python3 - <<'PY' "${RUNNER_ROOT}/bin/Runner.Listener.deps.json"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for key in payload.get("libraries", {}):
    if key.startswith("Runner.Listener/"):
        print(key.split("/", 1)[1])
        raise SystemExit(0)
raise SystemExit(1)
PY
}

configured_runner_name() {
  if [[ ! -f "${RUNNER_JSON_PATH}" ]]; then
    return 1
  fi
  python3 - <<'PY' "${RUNNER_JSON_PATH}"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
name = payload.get("agentName", "")
if name:
    print(name)
    raise SystemExit(0)
raise SystemExit(1)
PY
}

configured_service_name() {
  local runner_name
  runner_name="$(configured_runner_name 2>/dev/null || true)"
  if [[ -z "${runner_name}" ]]; then
    return 1
  fi
  local service_name="actions.runner.${REPO_SLUG//\//-}.${runner_name}"
  echo "${service_name// /_}"
}

service_installed() {
  [[ -f "${SERVICE_CONFIG_PATH}" ]]
}

service_plist_path() {
  if service_installed; then
    cat "${SERVICE_CONFIG_PATH}"
  fi
}

service_running() {
  local service_name
  service_name="$(configured_service_name 2>/dev/null || true)"
  [[ -n "${service_name}" ]] || return 1
  launchctl print "gui/$(id -u)/${service_name}" >/dev/null 2>&1
}

github_runner_payload() {
  local runner_name
  runner_name="$(configured_runner_name 2>/dev/null || true)"
  [[ -n "${runner_name}" ]] || return 1
  command -v gh >/dev/null 2>&1 || return 1
  gh api "repos/${REPO_SLUG}/actions/runners" 2>/dev/null | python3 - <<'PY' "${runner_name}"
import json
import sys

target = sys.argv[1]
payload = json.load(sys.stdin)
for runner in payload.get("runners", []):
    if runner.get("name") == target:
        print(json.dumps(runner))
        raise SystemExit(0)
raise SystemExit(1)
PY
}

persist_runner_env() {
  mkdir -p "${TOOL_CACHE_ROOT}" "${RUNNER_WORK_FOLDER}"
  local tmp_env
  tmp_env="$(mktemp)"
  if [[ -f "${RUNNER_ROOT}/.env" ]]; then
    grep -vE '^(RUNNER_TOOL_CACHE|AGENT_TOOLSDIRECTORY|LANG)=' "${RUNNER_ROOT}/.env" > "${tmp_env}" || true
  fi
  printf 'LANG=%s\n' "${LANG:-en_GB.UTF-8}" >> "${tmp_env}"
  printf 'RUNNER_TOOL_CACHE=%s\n' "${TOOL_CACHE_ROOT}" >> "${tmp_env}"
  printf 'AGENT_TOOLSDIRECTORY=%s\n' "${TOOL_CACHE_ROOT}" >> "${tmp_env}"
  mv "${tmp_env}" "${RUNNER_ROOT}/.env"
}

download_runner_archive() {
  local archive_path="$1"
  curl -fL -o "${archive_path}" "${RUNNER_DOWNLOAD_URL}"
}

print_check_report() {
  local installed_version configured_name service_name plist_path
  local github_payload github_status github_labels github_busy

  installed_version="$(current_runner_version 2>/dev/null || true)"
  configured_name="$(configured_runner_name 2>/dev/null || true)"
  service_name="$(configured_service_name 2>/dev/null || true)"
  plist_path="$(service_plist_path 2>/dev/null || true)"
  github_payload="$(github_runner_payload 2>/dev/null || true)"

  echo "Runner check:"
  echo "  repo:            ${REPO_SLUG}"
  echo "  root:            ${RUNNER_ROOT}"
  echo "  target version:  ${RUNNER_VERSION}"
  echo "  installed:       ${installed_version:-<missing>}"
  echo "  configured name: ${configured_name:-<missing>}"
  echo "  labels:          ${RUNNER_LABELS}"
  echo "  work folder:     ${RUNNER_WORK_FOLDER}"
  echo "  tool cache:      ${TOOL_CACHE_ROOT}"
  echo "  service config:  ${SERVICE_CONFIG_PATH}"
  echo "  service plist:   ${plist_path:-<not installed>}"
  echo "  service status:  $(service_running && echo running || echo stopped)"
  if [[ -n "${service_name}" ]]; then
    echo "  service label:   ${service_name}"
  fi

  if [[ -n "${github_payload}" ]]; then
    github_status="$(python3 - <<'PY' "${github_payload}"
import json
import sys
payload = json.loads(sys.argv[1])
print(payload.get("status", "unknown"))
PY
)"
    github_busy="$(python3 - <<'PY' "${github_payload}"
import json
import sys
payload = json.loads(sys.argv[1])
print("busy" if payload.get("busy") else "idle")
PY
)"
    github_labels="$(python3 - <<'PY' "${github_payload}"
import json
import sys
payload = json.loads(sys.argv[1])
labels = [entry.get("name", "") for entry in payload.get("labels", [])]
print(",".join(label for label in labels if label))
PY
)"
    echo "  github status:   ${github_status} (${github_busy})"
    echo "  github labels:   ${github_labels:-<none>}"
  else
    echo "  github status:   unavailable"
  fi

  if [[ -n "${installed_version}" && "${installed_version}" != "${RUNNER_VERSION}" ]]; then
    echo "  upgrade needed:  yes"
  else
    echo "  upgrade needed:  no"
  fi
}

upgrade_runner_in_place() {
  local installed_version temp_root archive_path unpack_root was_running=0
  installed_version="$(current_runner_version 2>/dev/null || true)"

  if [[ ! -x "${RUNNER_ROOT}/config.sh" ]]; then
    echo "Runner is not installed at ${RUNNER_ROOT}; use the default bootstrap path first." >&2
    exit 1
  fi

  if [[ -n "${installed_version}" && "${installed_version}" == "${RUNNER_VERSION}" ]]; then
    echo "Runner is already at version ${RUNNER_VERSION}; nothing to upgrade."
    print_check_report
    return
  fi

  temp_root="$(mktemp -d)"
  archive_path="${temp_root}/${RUNNER_ARCHIVE}"
  unpack_root="${temp_root}/runner"
  mkdir -p "${unpack_root}"

  echo "Upgrading runner at ${RUNNER_ROOT} from ${installed_version:-<unknown>} to ${RUNNER_VERSION}"
  download_runner_archive "${archive_path}"
  tar xzf "${archive_path}" -C "${unpack_root}"

  if service_installed; then
    if service_running; then
      was_running=1
      "${SCRIPT_DIR}/install_self_hosted_runner_service.sh" stop --runner-root "${RUNNER_ROOT}"
    fi
  fi

  rsync -a --delete \
    --exclude '.credentials' \
    --exclude '.credentials_rsaparams' \
    --exclude '.env' \
    --exclude '.path' \
    --exclude '.runner' \
    --exclude '.service' \
    --exclude '_diag' \
    --exclude '_work' \
    --exclude 'hostedtoolcache' \
    "${unpack_root}/" "${RUNNER_ROOT}/"

  persist_runner_env
  cp "${RUNNER_ROOT}/bin/runsvc.sh" "${RUNNER_ROOT}/runsvc.sh"
  chmod u+x "${RUNNER_ROOT}/runsvc.sh"

  if service_installed && [[ "${was_running}" == "1" ]]; then
    "${SCRIPT_DIR}/install_self_hosted_runner_service.sh" start --runner-root "${RUNNER_ROOT}"
  fi

  rm -rf "${temp_root}"
  print_check_report
}

if [[ "${CHECK_ONLY}" == "1" ]]; then
  print_check_report
  exit 0
fi

if [[ "${UPGRADE_ONLY}" == "1" ]]; then
  upgrade_runner_in_place
  exit 0
fi

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
    download_runner_archive "${RUNNER_ARCHIVE}"
  fi
  tar xzf "${RUNNER_ARCHIVE}"
fi

persist_runner_env

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
