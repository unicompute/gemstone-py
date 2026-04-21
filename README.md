# gemstone-py

`gemstone-py` is a direct Python bridge to GemStone/S over GCI, plus a set of translated persistence helpers and plain-GemStone session utilities.

The repository has a single canonical package import path:

```python
from gemstone_py import GemStoneConfig, GemStoneSession, TransactionPolicy
from gemstone_py.persistent_root import PersistentRoot
```

## Supported API

New code should treat `gemstone_py.*` as the supported public API:

```python
from gemstone_py import GemStoneConfig, GemStoneSession, TransactionPolicy
from gemstone_py.web import (
    GemStoneSessionPool,
    GemStoneThreadLocalSessionProvider,
    install_flask_request_session,
    session_scope,
)
from gemstone_py.persistent_root import PersistentRoot
from gemstone_py.gstore import GStore
from gemstone_py.gsquery import GSCollection
from gemstone_py.session_facade import GemStoneSessionFacade
```

## Install

```bash
cd /Users/tariq/src/gemstone-py
python3 -m pip install -e .
```

Installed demo commands:

```bash
gemstone-benchmark-baseline-register
gemstone-benchmarks
gemstone-hello
gemstone-smalltalk-demo
gemstone-examples hello
gemstone-examples smalltalk-demo
```

Operational helper scripts:

```bash
./scripts/bootstrap_self_hosted_runner.sh
./scripts/install_self_hosted_runner_service.sh status
```

## Configure

Set explicit GemStone connection settings in the environment:

```bash
export GS_LIB=/opt/gemstone/product/lib
export GS_STONE=gs64stone
export GS_USERNAME=DataCurator
export GS_PASSWORD=swordfish
```

Optional settings:

```bash
export GS_HOST=localhost
export GS_NETLDI=netldi
export GS_GEM_SERVICE=gemnetobject
export GS_HOST_USERNAME=
export GS_HOST_PASSWORD=
export GS_LIB_PATH=/full/path/to/libgcirpc-3.7.4.3-64.dylib
```

`GS_LIB` points at the GemStone `lib/` directory and is used for library discovery. `GS_LIB_PATH` is only needed when you want to pin an exact `libgcirpc` file.

## Quick Start

```python
from gemstone_py import GemStoneConfig, GemStoneSession, TransactionPolicy
from gemstone_py.session_facade import GemStoneSessionFacade

config = GemStoneConfig.from_env()

with GemStoneSession(
    config=config,
    transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
) as session:
    facade = GemStoneSessionFacade(session)
    facade["ExampleDict"] = {"name": "Tariq"}
```

Direct `GemStoneSession(...)` contexts are manual by default. That keeps transaction behavior explicit:

```python
with GemStoneSession(config=config) as session:
    session.eval("3 + 4")
    session.abort()
```

If you want the old auto-commit behavior for a scoped unit of work, pass `TransactionPolicy.COMMIT_ON_SUCCESS` explicitly or use `session_scope(...)`.

## Flask Requests

For request-scoped Flask work you can keep the core API lazy and explicit while
still using a bounded pool of logged-in sessions:

```python
from flask import Flask
from gemstone_py import GemStoneConfig, install_flask_request_session

app = Flask(__name__)
install_flask_request_session(
    app,
    config=GemStoneConfig.from_env(),
    pool_size=4,
    max_session_age=1800,
    max_session_uses=500,
    warmup_sessions=2,
    close_on_after_serving=True,
)
```

`install_flask_request_session(...)` still supports one-session-per-request
without a pool. `GemStoneSessionPool` is the production-safe option when you
want concurrent request handling without sharing a single logged-in GCI
session across threads.

For worker models that prefer one session per thread instead of a shared pool:

```python
from flask import Flask
from gemstone_py import GemStoneConfig, install_flask_request_session

app = Flask(__name__)
install_flask_request_session(
    app,
    config=GemStoneConfig.from_env(),
    thread_local=True,
)
```

For observability, snapshot the configured provider without reaching into
private Flask extension state:

```python
from gemstone_py import (
    flask_request_session_provider_metrics,
    flask_request_session_provider_snapshot,
)

snapshot = flask_request_session_provider_snapshot(app)
if snapshot is not None:
    print(snapshot.created, snapshot.available, snapshot.in_use)

metrics = flask_request_session_provider_metrics(app)
if metrics is not None:
    print(metrics["acquire_calls"], metrics["recycle_use_discards"])
```

For push-style export hooks, pass `metrics_exporter=` or `event_listener=` when
you create a pooled/thread-local provider through `install_flask_request_session(...)`
or `session_scope(...)`.

Use `warm_flask_request_session_provider(app)` to pre-create pool sessions
manually, and `close_flask_request_session_provider(app)` during server
shutdown when you manage lifecycle explicitly.

## Verification

Run the unit tests:

```bash
python3 -m unittest discover -s tests -p 'test*.py'
```

Run the local CI/static-check lane:

```bash
python3 -m pip install -e .[dev]
./scripts/run_ci_checks.sh
```

Run the maintained benchmark lane against a configured stone:

```bash
./scripts/run_benchmarks.sh
gemstone-benchmarks --entries 500 --search-runs 20
```

To capture a benchmark artifact locally:

```bash
./scripts/run_benchmarks.sh --json --output benchmark-report.json
```

Benchmark artifacts now include a `schema_version` field. To compare two saved
reports:

```bash
gemstone-benchmark-compare baseline.json candidate.json
gemstone-benchmark-compare baseline.json candidate.json --json --output benchmark-compare.json
gemstone-benchmark-compare baseline.json candidate.json --max-regression-pct 10
gemstone-benchmark-compare baseline.json candidate.json --suite-threshold persistent_root=7.5
gemstone-benchmark-compare baseline.json candidate.json --operation-threshold persistent_root/mapping_keys=5
```

To select the committed environment-specific baseline for a generated report:

```bash
python -m gemstone_py.benchmark_baselines benchmark-report.json
python -m gemstone_py.benchmark_baselines benchmark-report.json --manifest .github/benchmarks/index.json --json
```

To register a new accepted benchmark artifact in the committed manifest:

```bash
gemstone-benchmark-baseline-register benchmark-report.json
gemstone-benchmark-baseline-register benchmark-report.json --copy-to baseline-macos-arm64.json
```

Run the build/install artifact smoke lane directly:

```bash
./scripts/run_build_smoke.sh
```

That smoke lane now validates the installed package API contract directly from
the built wheel and sdist via `python -m gemstone_py.api_contract`, including
non-live behavior checks for release metadata, benchmark baseline lifecycle,
benchmark baseline selection, and benchmark threshold comparison.

For release prep, use [RELEASE_CHECKLIST.md](/Users/tariq/src/gemstone-py/RELEASE_CHECKLIST.md:1)
and keep [CHANGELOG.md](/Users/tariq/src/gemstone-py/CHANGELOG.md:1) updated. GitHub also provides a
`Release` workflow for tagged/manual artifact builds and optional PyPI publish.
It validates the release tag against `project.version` and requires the same
version to appear in [CHANGELOG.md](/Users/tariq/src/gemstone-py/CHANGELOG.md:1)
before artifacts are built or published. Manual PyPI publish now uses PyPI
trusted publishing via GitHub OIDC in the `pypi` environment rather than a
long-lived API token.

For rehearsal without creating a GitHub release or publishing to PyPI, use the
manual `Release Dry Run` workflow. It validates release metadata, runs
`./scripts/run_ci_checks.sh`, builds sdist/wheel artifacts, and uploads the
resulting `dist/` contents for inspection.

For an end-to-end publish rehearsal, use the manual `Release TestPyPI`
workflow. It runs the same verification/build steps and then publishes the
artifacts to TestPyPI via GitHub OIDC trusted publishing in the `testpypi`
environment, then installs the just-published version back from TestPyPI and
runs `python -m gemstone_py.api_contract --json` plus the public CLI smoke
checks against that published artifact.

On GitHub, use the manual `Benchmarks` workflow to run the same lane against a
configured stone and upload `benchmark-report.json` as an artifact. If the
repository contains [.github/benchmarks/index.json](/Users/tariq/src/gemstone-py/.github/benchmarks/index.json:1),
the workflow selects the committed baseline whose metadata matches the
candidate report, then runs `gemstone-benchmark-compare`, uploads selection and
comparison artifacts, and writes the selection/comparison tables into the
workflow summary. The repository already includes a committed baseline at
[.github/benchmarks/baseline.json](/Users/tariq/src/gemstone-py/.github/benchmarks/baseline.json:1)
registered in the manifest for the default benchmark parameters. Threshold
enforcement is skipped when no committed baseline matches the candidate
metadata, and the workflow can fail on regressions larger than the configured
percentage. The workflow also accepts `suite-thresholds` and
`operation-thresholds` inputs for per-suite and per-operation regression
policies when one global threshold is too blunt. On the self-hosted GemStone
runner, the default workflow input now uses a fuller per-operation threshold
set:

- `persistent_root/write_mapping_commit=30`
- `persistent_root/mapping_keys=40`
- `gscollection/bulk_insert_and_index_commit=30`
- `gscollection/indexed_search=50`
- `gstore/batch_write=35`
- `gstore/snapshot_read=40`
- `rchash/populate_commit=80`
- `rchash/items=35`

Those defaults are broader than the original single global threshold because
repeated local samples on the self-hosted GemStone host showed meaningful
timing jitter across several write-heavy operations, with especially noisy
outliers in `gscollection/indexed_search` and `rchash/populate_commit`.

Run the opt-in live lane:

```bash
GS_RUN_LIVE=1 ./scripts/run_live_checks.sh
```

Destructive live coverage is available separately on GitHub through the manual
`Destructive Live GemStone Tests` workflow, which requires
`confirm=DESTROY` and runs with `GS_RUN_DESTRUCTIVE_LIVE=1`.

## Self-Hosted Runner

The live GemStone and benchmark workflows now target a repo-specific
self-hosted label set by default:

- `self-hosted`
- `macOS`
- `ARM64`
- `gemstone-py-local`

The workflows also use the current Node 24-compatible action majors:

- `actions/checkout@v6`
- `actions/setup-python@v6`
- `actions/upload-artifact@v7`
- `actions/download-artifact@v5`

That means the GemStone host should keep its self-hosted runner current.

To bootstrap or repair the runner on the macOS GemStone host:

```bash
./scripts/bootstrap_self_hosted_runner.sh
./scripts/bootstrap_self_hosted_runner.sh --check
./scripts/bootstrap_self_hosted_runner.sh --upgrade --runner-version 2.333.1
./scripts/install_self_hosted_runner_service.sh check
./scripts/install_self_hosted_runner_service.sh install --start
./scripts/install_self_hosted_runner_service.sh status
```

See [SELF_HOSTED_RUNNER.md](/Users/tariq/src/gemstone-py/SELF_HOSTED_RUNNER.md:1) for the full bootstrap,
launchd, log-path, and health-check flow.

Run the live demo against a configured stone:

```bash
python3 example.py
```
