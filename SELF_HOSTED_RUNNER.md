# Self-Hosted Runner

The live GemStone and benchmark workflows are intended to run on a macOS ARM64
runner that can reach the local stone and has the GemStone client libraries
installed.

The repository workflows now default to the repo-specific runner labels:

- `self-hosted`
- `macOS`
- `ARM64`
- `gemstone-py-local`

## Minimum Runner Expectations

The workflow actions have been updated to the current Node 24-compatible majors:

- `actions/checkout@v6`
- `actions/setup-python@v6`
- `actions/upload-artifact@v7`
- `actions/download-artifact@v5`

Those action lines require a current self-hosted runner. The local bootstrap
script defaults to runner `2.333.1`, which is newer than the minimum Node 24
runner requirement published by the GitHub actions.

## Bootstrap

From the repository root:

```bash
./scripts/bootstrap_self_hosted_runner.sh
```

That script:

- downloads the macOS ARM64 GitHub runner if needed
- configures the runner under `/Users/tariq/src/actions-runner-gemstone-py`
- registers it for `unicompute/gemstone-py`
- applies labels `self-hosted,macOS,ARM64,gemstone-py-local`
- creates `hostedtoolcache/` and persists `RUNNER_TOOL_CACHE` plus `AGENT_TOOLSDIRECTORY` into `.env`

If `gh` is authenticated, the script mints its own registration token. If not,
set `RUNNER_TOKEN` explicitly before running it.

Useful overrides:

```bash
RUNNER_VERSION=2.333.1 ./scripts/bootstrap_self_hosted_runner.sh
RUNNER_ROOT=/Users/tariq/src/actions-runner-gemstone-py ./scripts/bootstrap_self_hosted_runner.sh
RUNNER_NAME=gemstone-py-local-arm64 ./scripts/bootstrap_self_hosted_runner.sh
```

To inspect the current install without changing it:

```bash
./scripts/bootstrap_self_hosted_runner.sh --check
```

To upgrade the runner binaries in place while preserving the registration,
service metadata, `_work/`, and `hostedtoolcache/`:

```bash
./scripts/bootstrap_self_hosted_runner.sh --upgrade --runner-version 2.333.1
```

## Service Install

The repository includes a hardened launchd template with `KeepAlive` enabled.
Install it through the runner's own `svc.sh` wrapper:

```bash
./scripts/install_self_hosted_runner_service.sh install --start
```

To replace an existing service with the hardened template:

```bash
./scripts/install_self_hosted_runner_service.sh reinstall --start
```

Useful service commands:

```bash
./scripts/install_self_hosted_runner_service.sh check
./scripts/install_self_hosted_runner_service.sh status
./scripts/install_self_hosted_runner_service.sh restart
./scripts/install_self_hosted_runner_service.sh stop
./scripts/install_self_hosted_runner_service.sh uninstall
```

The generated launch agent lives under:

```bash
~/Library/LaunchAgents/actions.runner.unicompute-gemstone-py.gemstone-py-local-arm64.plist
```

The service logs are written under:

```bash
~/Library/Logs/actions.runner.unicompute-gemstone-py.gemstone-py-local-arm64/
```

## Health Checks

Check the launch agent and runner status locally:

```bash
./scripts/install_self_hosted_runner_service.sh status
launchctl list | grep actions.runner
```

Check the runner registration from GitHub:

```bash
gh api repos/unicompute/gemstone-py/actions/runners
```

## Workflow Defaults

The `Benchmarks`, `Live GemStone Tests`, and `Destructive Live GemStone Tests`
manual workflows all default to:

```json
["self-hosted","macOS","ARM64","gemstone-py-local"]
```

That keeps live/benchmark jobs bound to the GemStone-capable local runner
instead of any generic self-hosted machine.
