#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./scripts/install_self_hosted_runner_service.sh <install|reinstall|start|stop|restart|status|check|uninstall> [options]

Options:
  --runner-root PATH   Runner installation directory
  --template PATH      Custom launchd plist template
  --start              Start after install/reinstall
  --help               Show this message

This wraps the runner's built-in svc.sh on macOS and injects the repository's
custom launchd template with KeepAlive enabled.
EOF
}

COMMAND="${1:-}"
if [[ -z "${COMMAND}" ]]; then
  usage >&2
  exit 1
fi
shift

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER_ROOT="${RUNNER_ROOT:-/Users/tariq/src/actions-runner-gemstone-py}"
TEMPLATE_PATH="${TEMPLATE_PATH:-${SCRIPT_DIR}/actions.runner.macos.plist.template}"
START_AFTER_INSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --runner-root)
      RUNNER_ROOT="$2"
      shift 2
      ;;
    --template)
      TEMPLATE_PATH="$2"
      shift 2
      ;;
    --start)
      START_AFTER_INSTALL=1
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

if [[ ! -d "${RUNNER_ROOT}" || ! -x "${RUNNER_ROOT}/svc.sh" ]]; then
  echo "Runner root does not contain svc.sh: ${RUNNER_ROOT}" >&2
  exit 1
fi

if [[ ! -f "${TEMPLATE_PATH}" ]]; then
  echo "Launchd template not found: ${TEMPLATE_PATH}" >&2
  exit 1
fi

cd "${RUNNER_ROOT}"
export GITHUB_ACTIONS_RUNNER_SERVICE_TEMPLATE="${TEMPLATE_PATH}"

safe_service_path() {
  if [[ -f .service ]]; then
    cat .service
  fi
}

safe_uninstall() {
  local plist_path
  plist_path="$(safe_service_path || true)"
  if [[ -n "${plist_path}" && -f "${plist_path}" ]]; then
    ./svc.sh uninstall || true
  fi
}

print_check_report() {
  local plist_path service_name log_root github_payload
  plist_path="$(safe_service_path || true)"
  service_name="$(python3 - <<'PY' "${RUNNER_ROOT}/.runner" 2>/dev/null || true
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
name = payload.get("agentName", "")
github_url = payload.get("gitHubUrl", "")
slug = ""
if github_url:
    slug = urlparse(github_url).path.strip("/").replace("/", "-")
if name and slug:
    print(("actions.runner." + slug + "." + name).replace(" ", "_"))
PY
)"
  log_root="${HOME}/Library/Logs/${service_name}"

  echo "Runner service check:"
  echo "  runner root:    ${RUNNER_ROOT}"
  echo "  service plist:  ${plist_path:-<not installed>}"
  echo "  service label:  ${service_name:-<unknown>}"
  if [[ -n "${service_name}" ]] && launchctl print "gui/$(id -u)/${service_name}" >/dev/null 2>&1; then
    echo "  launchctl:      running"
  else
    echo "  launchctl:      stopped"
  fi
  echo "  runsvc.sh:      $([[ -x "${RUNNER_ROOT}/runsvc.sh" ]] && echo present || echo missing)"
  echo "  logs:           $([[ -d "${log_root}" ]] && echo "${log_root}" || echo "<missing>")"
  github_payload=""
  if command -v gh >/dev/null 2>&1 && [[ -f "${RUNNER_ROOT}/.runner" ]]; then
    github_payload="$(gh api repos/unicompute/gemstone-py/actions/runners 2>/dev/null || true)"
  fi
  if [[ -n "${github_payload}" ]]; then
    python3 - <<'PY' "${RUNNER_ROOT}/.runner" "${github_payload}"
import json
import sys
from pathlib import Path

runner_payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
target = runner_payload.get("agentName")
payload = json.loads(sys.argv[2])
match = next((runner for runner in payload.get("runners", []) if runner.get("name") == target), None)
if match is None:
    print("  github status:  unavailable")
else:
    labels = ",".join(label.get("name", "") for label in match.get("labels", []) if label.get("name"))
    busy = "busy" if match.get("busy") else "idle"
    print(f"  github status:  {match.get('status', 'unknown')} ({busy})")
    print(f"  github labels:  {labels}")
PY
  else
    echo "  github status:  unavailable"
  fi
}

case "${COMMAND}" in
  install)
    if [[ -f .service ]]; then
      echo "Service already installed. Use reinstall or status." >&2
      exit 1
    fi
    ./svc.sh install
    if [[ "${START_AFTER_INSTALL}" == "1" ]]; then
      ./svc.sh start
    fi
    ;;
  reinstall)
    safe_uninstall
    ./svc.sh install
    if [[ "${START_AFTER_INSTALL}" == "1" ]]; then
      ./svc.sh start
    fi
    ;;
  start)
    ./svc.sh start
    ;;
  stop)
    ./svc.sh stop
    ;;
  restart)
    ./svc.sh stop || true
    ./svc.sh start
    ;;
  status)
    ./svc.sh status
    ;;
  check)
    print_check_report
    ;;
  uninstall)
    safe_uninstall
    ;;
  *)
    echo "Unknown command: ${COMMAND}" >&2
    usage >&2
    exit 1
    ;;
esac

plist_path="$(safe_service_path || true)"
if [[ -n "${plist_path}" ]]; then
  echo "LaunchAgent plist: ${plist_path}"
fi
