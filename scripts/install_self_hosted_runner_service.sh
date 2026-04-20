#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./scripts/install_self_hosted_runner_service.sh <install|reinstall|start|stop|restart|status|uninstall> [options]

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
