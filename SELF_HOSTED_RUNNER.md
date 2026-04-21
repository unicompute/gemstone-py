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
script keeps a reproducible pinned default (`2.333.1` today), but it can also
query GitHub for the latest available runner release before bootstrapping or
upgrading.

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
./scripts/bootstrap_self_hosted_runner.sh --latest-version
./scripts/bootstrap_self_hosted_runner.sh --use-latest
```

To inspect the current install without changing it:

```bash
./scripts/bootstrap_self_hosted_runner.sh --check
```

That check now reports the installed, target, and latest available runner
versions together, so version drift is visible without upgrading.

To upgrade the runner binaries in place while preserving the registration,
service metadata, `_work/`, and `hostedtoolcache/`:

```bash
./scripts/bootstrap_self_hosted_runner.sh --upgrade --runner-version 2.333.1
./scripts/bootstrap_self_hosted_runner.sh --upgrade --use-latest
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

The repository also includes a scheduled/manual `Runner Health` workflow. It:

- resolves the latest available GitHub Actions runner release
- compares that to the pinned default in `bootstrap_self_hosted_runner.sh`
- checks that at least one runner with label `gemstone-py-local` is online

Use that workflow to detect runner drift before it breaks the live or benchmark lanes.

## Recovery And Redundancy

The fastest recovery path is to provision a second Mac host with a distinct
runner root and runner name, then apply the same repository labels:

```bash
RUNNER_ROOT=/Users/tariq/src/actions-runner-gemstone-py-backup \
RUNNER_NAME=gemstone-py-backup-arm64 \
./scripts/bootstrap_self_hosted_runner.sh --use-latest
./scripts/install_self_hosted_runner_service.sh install --runner-root /Users/tariq/src/actions-runner-gemstone-py-backup --start
```

If you want workflows to keep targeting either host automatically, give the
backup runner the same `gemstone-py-local` label set. If you want to direct
workflows to the backup runner only during recovery, register it under a
different label and override the `runner-labels` workflow input manually.

## Workflow Defaults

The `Benchmarks`, `Live GemStone Tests`, and `Destructive Live GemStone Tests`
manual workflows all default to:

```json
["self-hosted","macOS","ARM64","gemstone-py-local"]
```

That keeps live/benchmark jobs bound to the GemStone-capable local runner
instead of any generic self-hosted machine.
