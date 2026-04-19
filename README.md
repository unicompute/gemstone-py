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
gemstone-hello
gemstone-smalltalk-demo
gemstone-examples hello
gemstone-examples smalltalk-demo
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

Run the build/install artifact smoke lane directly:

```bash
./scripts/run_build_smoke.sh
```

Run the opt-in live lane:

```bash
GS_RUN_LIVE=1 ./scripts/run_live_checks.sh
```

Run the live demo against a configured stone:

```bash
python3 example.py
```
