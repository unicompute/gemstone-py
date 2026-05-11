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

### Which Install Path Should I Use?

| Use case | Command |
| --- | --- |
| Normal users | `python3 -m pip install gemstone-py` |
| Native acceleration | `python3 -m pip install "gemstone-py[fast]"` |
| Source checkout examples/development | `python3 -m pip install -e ".[examples,dev]"` |
| VS Code users | `code --install-extension unicompute.gemstone-py-workbench` |

For a normal installed package:

```bash
python3 -m pip install gemstone-py
```

The package requires Python 3.11 or newer. The default install uses the
pure-ctypes GCI path.

For the optional native PyO3 fast path:

```bash
python3 -m pip install "gemstone-py[fast]"
```

That installs `gemstone-py-native` when a wheel is available for your platform.
Check the selected backend with:

```bash
python -c "from gemstone_py import _gci; print(_gci.IMPLEMENTATION)"
```

The native package source lives in `gemstone-py-native/` and builds the
`gemstone_py_native._gci` PyO3 extension with `maturin`.
When the native package is installed, `gemstone_py` uses it automatically.
Set `GEMSTONE_PY_GCI_BACKEND=ctypes` or `GEMSTONE_PY_GCI_BACKEND=native` to
force one backend while testing.
The `Native Wheels` workflow builds Python 3.11 stable-ABI wheels for Linux
x86_64, Linux aarch64, Linux ARMv7, macOS x86_64, macOS aarch64, Windows x86_64,
and Windows ARM64, with one native sdist and manual TestPyPI/PyPI publishing gates.
Linux wheels are built with Maturin's Zig path and `--compatibility pypi` so the workflow rejects
non-PyPI-compatible Linux tags instead of uploading local `linux_*` wheels. Each
matrix job checks the built wheel's `cp311-abi3` tag and expected platform
markers, then installs the wheel and verifies that `gemstone_py._gci` selects
the native backend before upload. Before publishing, the publish jobs verify
that the merged artifact set contains exactly the expected native sdist and seven
platform wheels. The publish jobs also install the just-published native package
and verify that `gemstone_py._gci` selects the native backend, then check
package metadata for the expected sdist and Linux/macOS/Windows wheel families.
The sdist job also builds the native sdist back into a wheel before upload,
catching missing source archive contents before publish. PyPI publishes require
a native release tag that matches `gemstone-py-native`'s version, for example
`native-v0.1.2`. TestPyPI and PyPI publishes require GitHub OIDC Trusted
Publishing and produce PyPI publish attestations.

For development from source:

```bash
git clone https://github.com/unicompute/gemstone-py.git
cd gemstone-py
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
```

For the web examples without the full development toolchain:

```bash
python3 -m pip install -e ".[examples]"
```

## Quickstart

For the smallest live example from a source checkout:

```bash
export GS_LIB=/opt/gemstone/product/lib
export GS_STONE=gs64stone
export GS_STONE_NAME=gs64stone
export GS_USERNAME=DataCurator
export GS_PASSWORD=swordfish
python -m examples.quickstart
```

The same flow in application code:

```python
from gemstone_py import GemStoneConfig, GemStoneSession, TransactionPolicy
from gemstone_py.persistent_root import PersistentRoot

config = GemStoneConfig.from_env()
with GemStoneSession(config=config, transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS) as session:
    print(session.eval("3 + 4"))
    PersistentRoot(session)["GemstonePyQuickstart"] = {"message": "Hello from Python"}
```

Installed demo commands:

```bash
gemstone-benchmark-baseline-register
gemstone-benchmarks
gemstone-bootstrap --status
gemstone-bootstrap
gemstone-hello
gemstone-smalltalk-demo
gemstone-examples hello
gemstone-examples quickstart
gemstone-examples smalltalk-demo
gemstone-examples fastapi --reload
gemstone-fastapi-example --reload
gemstone-publish-verify --gemstone-version 0.2.10 --native-version 0.1.2 --skip-install
```

Feature examples from the repository checkout:

```bash
python -m examples.quickstart
python -m examples.async_features.session_root_and_collection
python -m examples.typed_access.typed_oops_and_queries
python -m examples.lifetime.managed_oop_handles
python -m examples.native_backend.check_backend
python -m examples.fastapi.run --reload
```

If you want to initialize the GemStone-side roots used by the higher-level
helpers before running examples, use the packaged bootstrap command:

```bash
gemstone-bootstrap --status
gemstone-bootstrap
```

The command is idempotent. It creates missing `UserGlobals` entries for
`GStoreRoot`, `GSQueryRoot`, and `GemstonePyBootstrapVersion`, and it leaves
existing application data in place.

The repository also includes a companion VS Code extension scaffold under
[`vscode-gemstone-py-workbench/`](vscode-gemstone-py-workbench/). It adds a
GemStone Py sidebar for running examples, checking the active backend, opening
docs/PDFs, launching or embedding the Python database explorer, and running
maintainer checks.
Use Jasper for full GemStone/S Smalltalk IDE work; use this workbench for the
Python-facing `gemstone-py` workflow.

Install it from the Visual Studio Marketplace:

```bash
code --install-extension unicompute.gemstone-py-workbench
```

Marketplace page:
https://marketplace.visualstudio.com/items?itemName=unicompute.gemstone-py-workbench

The extension uses the current VS Code workspace as the default `gemstone-py`
checkout. Configure `gemstonePy.explorerPath` if you want the workbench to
launch a local `python-gemstone-database-explorer` checkout, or run
`gemstone-py: Configure Workbench` from the Command Palette for a guided
first-run setup. After configuration, run `gemstone-py: Verify Workbench Setup`
to check Python paths, `GS_STONE`/`GS_STONE_NAME`, credentials, native backend
state, and live GemStone connectivity from one output report.
The report can open settings, copy itself, or copy an environment export script.

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
export GS_STONE_NAME=gs64stone
export GS_USERNAME=DataCurator
export GS_PASSWORD=swordfish
```

`GS_STONE` is the canonical stone variable. `GS_STONE_NAME` is accepted as an
alias when `GS_STONE` is absent; setting both to the same value keeps older and
newer tooling aligned.

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

## Async Usage

`gemstone_py.aio.AsyncSession` wraps one synchronous `GemStoneSession` in a
single-worker executor so GCI calls stay on one owning thread while FastAPI or
asyncio handlers avoid blocking the event loop:

```python
from gemstone_py import GemStoneConfig
from gemstone_py.aio import AsyncSession

config = GemStoneConfig.from_env()

async with AsyncSession.connect(config=config) as session:
    ref = await session.execute_managed("Date today")
    print(await ref.print_string())
    value = await session.eval("3 + 4")

    async with session.transaction():
        await session.eval("System myUserProfile")
```

For FastAPI:

```bash
python -m pip install "gemstone-py[fastapi]"
gemstone-fastapi-example --reload
```

When the server starts, you should see output like:

```text
INFO:     Will watch for changes in these directories: ['/path/to/gemstone-py']
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [49045] using WatchFiles
INFO:     Started server process [49048]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

With that server running, test it from a second terminal.

Basic checks:

```bash
curl -i http://127.0.0.1:8000/
```

Expected:

```text
HTTP/1.1 200 OK
```

Body should include:

```json
{"name":"gemstone-py FastAPI example","endpoints":{"health":"/health/gemstone","docs":"/docs","openapi":"/openapi.json"}}
```

Then test the GemStone endpoint:

```bash
curl -i http://127.0.0.1:8000/health/gemstone
```

Expected if GemStone credentials/environment are set and the stone is reachable:

```json
{"result":7}
```

Also open these in a browser:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/health/gemstone
```

```python
from fastapi import Depends, FastAPI
from gemstone_py import GemStoneConfig
from gemstone_py.aio import AsyncSession, AsyncSessionPool
from gemstone_py.aio.fastapi import pool_session_dependency, session_dependency

app = FastAPI()
get_gemstone = session_dependency(config=GemStoneConfig.from_env())

@app.get("/health/gemstone")
async def gemstone_health(session: AsyncSession = Depends(get_gemstone)):
    return {"result": await session.eval("3 + 4")}
```

For production-style async apps, create an `AsyncSessionPool` during application
startup and use `pool_session_dependency(...)`:

```python
pool = AsyncSessionPool(
    maxsize=8,
    minsize=2,
    config=GemStoneConfig.from_env(),
    idle_timeout_seconds=900,
    validation_query="1 + 1",
    validation_interval_seconds=60,
)
get_pooled_gemstone = pool_session_dependency(pool)
```

See `examples/async_features/session_root_and_collection.py` for async
sessions, async persistent-root access, async `GSCollection`, and managed async
OOP handles in one runnable script. See `examples/fastapi/app.py` for the
minimal FastAPI dependency-injection shape.

## Typed OOPs and Handles

The untyped API remains available. New code can add phantom types for static
checking and IDE hints:

```python
from typing import Protocol
from gemstone_py import GemStoneSession, gemstone_class

@gemstone_class("OkzBooking")
class OkzBooking(Protocol):
    status: str

with GemStoneSession(config=config) as session:
    booking = session.execute_typed("OkzBooking findById: 'x'", OkzBooking)
    status = booking.proxy().status
```

Typed `GSCollection` queries keep the existing string form and also accept a
field-recording lambda. The lambda is executed against a query builder, not a
live object, so attribute access becomes a GemStone ivar path. Untyped queries
still return dictionaries; typed queries materialize lightweight rows with
attribute access:

```python
from typing import Protocol
from gemstone_py.gsquery import GSCollection

class BlogPostRecord(Protocol):
    status: str
    timestamp: float

posts = GSCollection("SimplePosts").query(BlogPostRecord)
published = posts.where(lambda post: post.status == "published").all()
recent = posts.where(lambda post: post.status == "published").where(
    lambda post: post.timestamp >= cutoff
).all()
```

For large `GSCollection` result sets, iterate in chunks instead of materializing
the full list:

```python
people = GSCollection("People", config=config)
for row in people.search_iter("@status", "eql", "active", chunk_size=500):
    process(row)

for post in posts.where(lambda post: post.status == "published").iter(chunk_size=500):
    process(post)
```

For long-lived raw OOPs, use managed or explicitly scoped handles:

```python
with GemStoneSession(config=config) as session:
    ref = session.execute_managed("OrderedCollection new")
    print(ref.print_string())

    with session.handle(int(ref)) as handle:
        print(handle.send("size"))
```

`execute()` and `perform()` keep the historic raw-OOP return behavior.
Use `execute_managed()` / `perform_managed()` when you want automatic
export-set lifetime management, and `perform_value()` when you want the old
marshalled Python value from a message send.

Runnable examples:

```bash
python -m examples.typed_access.typed_oops_and_queries
python -m examples.lifetime.managed_oop_handles
```

To inspect native backend selection after installing `gemstone-py[fast]`:

```bash
python -m examples.native_backend.check_backend
```

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
    pool_minsize=1,
    idle_timeout_seconds=900,
    idle_sweep_interval_seconds=60,
    validation_query="1 + 1",
    validation_interval_seconds=60,
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

For operations dashboards, call `pool.stats()` to get stable counters for
current capacity, idle/in-use sessions, total created sessions, evictions,
validation failures, and acquire wait time.
The idle sweeper runs only against sessions sitting in the pool; checked-out
sessions are never evicted by background maintenance.

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

## Production Flask Guidance

For production Flask usage:

- use `pool_size=` or `thread_local=True` instead of sharing one logged-in session
- set `max_session_age` and `max_session_uses` so pooled sessions are recycled before they go stale
- use `close_on_after_serving=True` when Flask owns the process lifecycle
- use `metrics_exporter=` or `event_listener=` so session-pool behavior is visible outside request code
- keep request handlers inside `session_scope()` and let teardown own the final commit/abort decision
- use `warm_flask_request_session_provider(app, count)` during startup if cold request latency matters

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

Run the live lane with the optional longer soak coverage:

```bash
GS_RUN_LIVE=1 GS_RUN_LIVE_SOAK=1 ./scripts/run_live_checks.sh
```

The live lane includes sync coverage, concrete async/FastAPI/lifetime coverage,
and an async-runner parity pass over the existing live integration suite.

Run the maintained benchmark lane against a configured stone:

```bash
./scripts/run_benchmarks.sh
gemstone-benchmarks --entries 500 --search-runs 20
```

See [`docs/performance.md`](docs/performance.md) for the current committed
benchmark baseline, methodology, and regression policy.

To compare the low-level ctypes and PyO3 helper-call overhead without a live
stone:

```bash
gemstone-benchmarks --suite gci --entries 1000000
```

To compare real GemStone workloads through each GCI backend, run the same
benchmark twice with a forced backend and compare the saved reports:

```bash
GEMSTONE_PY_GCI_BACKEND=ctypes gemstone-benchmarks --json --output ctypes-report.json
GEMSTONE_PY_GCI_BACKEND=native gemstone-benchmarks --json --output native-report.json
gemstone-benchmark-compare ctypes-report.json native-report.json
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

Run the optional native extension smoke lane directly:

```bash
./scripts/run_native_checks.sh
```

That native lane runs `cargo fmt --check`, `cargo check`, builds a local native
wheel, verifies its abi3 tag and package metadata, installs the wheel in a temp
environment to check native backend selection, builds the native sdist, and then
builds a wheel back from the extracted sdist.

That smoke lane now validates the installed package API contract directly from
the built wheel and sdist via `python -m gemstone_py.api_contract`, including
non-live behavior checks for release metadata, benchmark baseline lifecycle,
benchmark baseline selection, and benchmark threshold comparison.

For release prep, use
[RELEASE_CHECKLIST.md](https://github.com/unicompute/gemstone-py/blob/main/RELEASE_CHECKLIST.md)
and keep
[CHANGELOG.md](https://github.com/unicompute/gemstone-py/blob/main/CHANGELOG.md)
updated. GitHub also provides a
`Release` workflow for tagged/manual artifact builds and optional PyPI publish.
It validates the release tag against `project.version` and requires the same
version to appear in
[CHANGELOG.md](https://github.com/unicompute/gemstone-py/blob/main/CHANGELOG.md)
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

For a real-PyPI post-publish check, use the manual `Post Release Verify`
workflow. It polls PyPI for the requested release, installs the published
package from real PyPI, runs `python -m gemstone_py.api_contract --json`,
checks the public CLI entry points, and validates the PyPI JSON metadata plus
long description.

For local end-to-end index verification across PyPI and TestPyPI, use the
packaged verifier. It checks project JSON, version-specific JSON, the simple
index, and temporary-virtualenv installs:

```bash
gemstone-publish-verify --gemstone-version 0.2.10 --native-version 0.1.2
```

Use `--skip-install` when you only want the metadata/index checks, or
`--index pypi` / `--index testpypi` to narrow the target.

GitHub releases include SHA-256 checksum assets. Download the Python artifacts
and `SHA256SUMS` into the same directory, then verify them with:

```bash
shasum -a 256 -c SHA256SUMS
```

For a VS Code workbench release, download both
`gemstone-py-workbench-<version>.vsix` and
`gemstone-py-workbench-<version>.vsix.sha256`, then run:

```bash
shasum -a 256 -c gemstone-py-workbench-<version>.vsix.sha256
```

On GitHub, use the manual `Benchmarks` workflow to run the same lane against a
configured stone and upload `benchmark-report.json` as an artifact. The
workflow now supports named policy profiles:

- `smoke`: broader per-operation thresholds intended for routine runner health checks
- `regression`: stricter thresholds intended for deliberate performance review

If the
repository contains
[.github/benchmarks/index.json](https://github.com/unicompute/gemstone-py/blob/main/.github/benchmarks/index.json),
the workflow selects the committed baseline whose metadata matches the
candidate report, then runs `gemstone-benchmark-compare`, uploads selection and
comparison artifacts, and writes the selection/comparison tables into the
workflow summary. The repository already includes a committed baseline at
[.github/benchmarks/baseline.json](https://github.com/unicompute/gemstone-py/blob/main/.github/benchmarks/baseline.json)
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

Run the opt-in live soak lane:

```bash
GS_RUN_LIVE=1 GS_RUN_LIVE_SOAK=1 ./scripts/run_live_checks.sh
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
- `actions/download-artifact@v8`

That means the GemStone host should keep its self-hosted runner current.
External GitHub Actions are also pinned to immutable commit SHAs in the
workflow files for supply-chain hardening.

To bootstrap or repair the runner on the macOS GemStone host:

```bash
./scripts/bootstrap_self_hosted_runner.sh
./scripts/bootstrap_self_hosted_runner.sh --latest-version
./scripts/bootstrap_self_hosted_runner.sh --check
./scripts/bootstrap_self_hosted_runner.sh --upgrade --runner-version 2.333.1
./scripts/bootstrap_self_hosted_runner.sh --upgrade --use-latest
./scripts/install_self_hosted_runner_service.sh check
./scripts/install_self_hosted_runner_service.sh install --start
./scripts/install_self_hosted_runner_service.sh status
```

See
[SELF_HOSTED_RUNNER.md](https://github.com/unicompute/gemstone-py/blob/main/SELF_HOSTED_RUNNER.md)
for the full bootstrap,
launchd, log-path, and health-check flow.

## Release And Admin Operations

For repository operations:

- use the scheduled/manual `Runner Health` workflow to detect self-hosted runner drift and offline state
- use `Release Dry Run` before cutting a new version
- use `Release TestPyPI` as the full publish rehearsal
- use `Native Wheels` with `publish-to-testpypi=true` before publishing the optional native package
- use `./scripts/run_native_checks.sh` before starting the native wheel publish workflow
- use `Post Release Verify` after a real PyPI publish to validate the public artifact and metadata
- use `Full Release Verify` after publishing to run `scripts/release_all.sh` without skips against PyPI, TestPyPI, Marketplace, GitHub release assets, and VSIX packaging
- use `gemstone-publish-verify --gemstone-version <version> --native-version <native-version>` to check PyPI and TestPyPI from your shell
- use `Native Wheels` with `publish-to-pypi=true` and a matching native `release-tag` only after the native wheel matrix passes on all target platforms
- use the real `Release` workflow only after `CHANGELOG.md`, `pyproject.toml`, live checks, and benchmarks all match the intended version
- keep a second Mac host or at least a documented rebuild path for the `gemstone-py-local` self-hosted runner

Run the live demo against a configured stone:

```bash
python3 example.py
```
