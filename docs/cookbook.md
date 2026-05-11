# Cookbook

This cookbook is a collection of direct recipes. Each one is deliberately short
enough to copy, adapt, and keep moving.

![Cookbook flow](assets/diagrams/cookbook-flow.svg)

## Recipe 1: Open a Session and Evaluate Smalltalk

```python
from gemstone_py import GemStoneConfig, GemStoneSession

config = GemStoneConfig.from_env()

with GemStoneSession(config=config) as session:
    print(session.eval("3 factorial"))
```

Use this when:

- you want the smallest live sanity check
- you need to inspect a repository value quickly

## Recipe 2: Commit a Write Safely

```python
from gemstone_py import GemStoneConfig, TransactionPolicy, GemStoneSession
from gemstone_py.persistent_root import PersistentRoot

config = GemStoneConfig.from_env()

with GemStoneSession(
    config=config,
    transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
) as session:
    root = PersistentRoot(session)
    root["CookbookExample"] = {"answer": 42}
```

Why this recipe exists:

- it avoids the classic "the write seemed to work but vanished" mistake

## Recipe 3: Read From `PersistentRoot`

```python
from gemstone_py import GemStoneSession
from gemstone_py.persistent_root import PersistentRoot

with GemStoneSession(config=config) as session:
    root = PersistentRoot(session)
    print(root["CookbookExample"])
```

## Recipe 4: Use `session_scope(...)`

```python
from gemstone_py import GemStoneConfig, session_scope
from gemstone_py.persistent_root import PersistentRoot

config = GemStoneConfig.from_env()

with session_scope(config=config) as session:
    root = PersistentRoot(session)
    root["ScopedWork"] = {"kind": "unit-of-work"}
```

This is the recipe to prefer in application code.

## Recipe 5: Create a Named `GSCollection`

```python
from gemstone_py.gsquery import GSCollection

people = GSCollection("CookbookPeople", config=config)
people.insert({"@name": "Ada", "@city": "London"})
people.insert({"@name": "Grace", "@city": "New York"})
people.add_index("@city")
```

## Recipe 6: Search an Indexed Collection

```python
matches = people.search("@city", "eql", "London")
for row in matches:
    print(row)
```

Use `GSCollection` when you need repeated search, not when you merely enjoy the
idea of repeated search.

## Recipe 7: Keep a Store-Like Dataset in `GStore`

```python
from gemstone_py.gstore import GStore

store = GStore("cookbook.db", config=config)
store["sku:hat"] = {"name": "Hat", "stock": 8}
store["sku:cape"] = {"name": "Cape", "stock": 3}
print(store["sku:hat"])
```

## Recipe 8: Append a Persistent Event Log Entry

```python
from gemstone_py.objectlog import ObjectLog

log = ObjectLog(config=config)
log.info("inventory_adjusted", {"sku": "hat", "delta": -1})
```

Later:

```python
for entry in log.entries():
    print(entry)
```

## Recipe 9: Share a Counter Between Sessions

```python
from gemstone_py.concurrency import RCCounter

with session_scope(config=config) as session:
    counter = RCCounter(session)
    counter += 1
```

Use shared counters when the number truly lives in GemStone, not when a local
integer would do and you are simply feeling theatrical.

## Recipe 10: Share a Queue

```python
from gemstone_py.concurrency import RCQueue
from gemstone_py.persistent_root import PersistentRoot

with session_scope(config=config) as session:
    root = PersistentRoot(session)
    root["WorkQueue"] = RCQueue(session)
```

## Recipe 11: Install Flask Request Sessions

```python
from flask import Flask
from gemstone_py import GemStoneConfig, install_flask_request_session

app = Flask(__name__)

install_flask_request_session(
    app,
    config=GemStoneConfig.from_env(),
    pool_size=4,
)
```

This is the default production-friendly shape.

## Recipe 12: Use a Thread-Local Provider for Simpler Hosting

```python
install_flask_request_session(
    app,
    config=GemStoneConfig.from_env(),
    thread_local=True,
)
```

Good when the server model is simple and you want one session per thread.

## Recipe 13: Inspect Provider Health

```python
from gemstone_py import flask_request_session_provider_snapshot

@app.get("/health/gemstone")
def gemstone_health():
    return flask_request_session_provider_snapshot()
```

Operational visibility is better than optimism.

## Recipe 14: Open an Async Session

```python
from gemstone_py import GemStoneConfig
from gemstone_py.aio import AsyncSession

config = GemStoneConfig.from_env()

async with AsyncSession.connect(config=config) as session:
    print(await session.eval("3 + 4"))
```

Use this when the surrounding application is already async.

## Recipe 15: Use an Async Transaction

```python
async with AsyncSession.connect(config=config) as session:
    async with session.transaction():
        root = session.root()
        await root.set("AsyncCookbook", {"status": "ok"})
```

The transaction context commits on success and aborts on exception.

## Recipe 16: Add FastAPI Dependency Injection

```python
from fastapi import Depends, FastAPI
from gemstone_py import GemStoneConfig
from gemstone_py.aio import AsyncSession
from gemstone_py.aio.fastapi import session_dependency

app = FastAPI()
get_gemstone = session_dependency(config=GemStoneConfig.from_env())

@app.get("/health/gemstone")
async def gemstone_health(session: AsyncSession = Depends(get_gemstone)):
    return {"result": await session.eval("3 + 4")}
```

## Recipe 17: Query With a Typed Protocol

```python
from typing import Protocol
from gemstone_py.gsquery import GSCollection

class PostRecord(Protocol):
    title: str
    status: str

posts = GSCollection("SimplePosts", config=config).query(PostRecord)
for post in posts.where(lambda row: row.status == "published").all():
    print(post.title)
```

The lambda records an indexed GemStone path. It is not called for every row in
Python.

## Recipe 18: Generate a Typed Smalltalk Wrapper

```python
from typing import Protocol
from gemstone_py import gemstone_class, gemstone_selector

@gemstone_class("OkzBooking", async_=True)
class OkzBookingProto(Protocol):
    status: str

    @classmethod
    @gemstone_selector("findById:")
    def find_by_id(cls, booking_id: str) -> "OkzBookingProto":
        ...

    def mark_paid(self, at_posix_seconds: int) -> None:
        ...
```

Generate and check in the wrapper:

```bash
gemstone-codegen \
  --module examples.typed_access.codegen_demo.models \
  --output examples/typed_access/codegen_demo/generated \
  --clean
```

Use it without hand-writing the class-side Smalltalk string:

```python
from examples.typed_access.codegen_demo.generated import OkzBooking

booking = OkzBooking.find_by_id(session, "B-1001")
print(booking.status)
booking.mark_paid(1_779_912_000)
```

## Recipe 19: Keep an OOP Alive Explicitly

```python
with GemStoneSession(config=config) as session:
    ref = session.execute_managed("OrderedCollection new")
    ref.send("add:", session.new_string("kept"))
    print(ref.print_string())
    ref.close()
```

For a raw OOP:

```python
with session.handle(raw_oop) as handle:
    print(handle.send("printString"))
```

## Recipe 20: Check the Native Backend

```bash
python -m pip install "gemstone-py[fast]"
python -m examples.native_backend.check_backend
```

Force a backend before Python starts:

```bash
GEMSTONE_PY_GCI_BACKEND=ctypes python -m examples.native_backend.check_backend
GEMSTONE_PY_GCI_BACKEND=native python -m examples.native_backend.check_backend
```

## Recipe 21: Run the Maintained Benchmarks

```bash
gemstone-benchmarks --entries 500 --search-runs 20
```

Or emit JSON:

```bash
gemstone-benchmarks --json --output benchmark-report.json
```

## Recipe 22: Compare Benchmark Reports

```bash
gemstone-benchmark-compare old.json new.json --json --output compare.json
```

That turns performance arguments into evidence, which is disappointingly healthy.

## Recipe 23: Register a New Accepted Benchmark Baseline

```bash
gemstone-benchmark-baseline-register \
  benchmark-report.json \
  --manifest .github/benchmarks/index.json
```

## Recipe 24: Verify the Installed Artifact

```bash
python -m gemstone_py.api_contract --json
```

This is useful after installation, after release, and after any moment when you
feel your package metadata may have become sentient.

For a full PyPI/TestPyPI release check:

```bash
gemstone-publish-verify --gemstone-version 0.2.10 --native-version 0.1.2
```

That command checks project JSON, version-specific JSON, the simple index, and
temporary-virtualenv installs for both the pure package and native package.

## Recipe 25: Scaffold and Run Module-Style Migrations

Create a numbered migration file:

```bash
gemstone-migrations scaffold add_amount_to_booking --directory migrations
```

A migration module exposes `upgrade(session)`, optional `downgrade(session)`,
and optional `dependencies`:

```python
id = "002_add_amount_to_booking"
dependencies = ("001_initial",)

def upgrade(session):
    ...

def downgrade(session):
    ...
```

Register modules in a manifest and apply them:

```python
from gemstone_py import GemStoneConfig, GemStoneSession
from gemstone_py.migrations import current_version, load_manifest, upgrade

steps = load_manifest("my_app.migrations.manifest")

with GemStoneSession(config=GemStoneConfig.from_env()) as session:
    print(current_version(session))
    print(upgrade(session, steps, dry_run=True))
    upgrade(session, steps)
```

Applied versions are recorded under `GemstonePyMigrations` in `UserGlobals`.

## Recipe 26: Run the Live Test Lane

```bash
GS_RUN_LIVE=1 ./scripts/run_live_checks.sh
```

Longer soak run:

```bash
GS_RUN_LIVE=1 GS_RUN_LIVE_SOAK=1 ./scripts/run_live_checks.sh
```

## Recipe 27: Handle Commit Conflicts Without Pretending They Are Rare

When multiple sessions modify overlapping state, conflicts are normal. The right
pattern:

```python
from gemstone_py import GemStoneConfig, GemStoneSession, TransactionPolicy
from gemstone_py.concurrency import CommitConflictError

config = GemStoneConfig.from_env()

for attempt in range(3):
    with GemStoneSession(config=config,
                         transaction_policy=TransactionPolicy.MANUAL) as session:
        try:
            # reload data each attempt — previous read is stale after abort
            root = PersistentRoot(session)
            root["counter"] = (root.get("counter") or 0) + 1
            session.commit()
            break
        except CommitConflictError:
            session.abort()
            if attempt == 2:
                raise
```

Rules:

- keep the write unit small
- reload data after every abort — the previous read is stale
- bound the retry count — do not loop forever
- log conflicts — frequent conflicts signal a design smell, not bad luck

## Recipe 28: Learn a Queue With a Hat

The hat trick example is memorable because it teaches a real primitive through a
slightly ridiculous scenario. You should keep more examples like that in your
own codebase than you probably do.

## Recipe 29: Explain `gemstone-py` to a New Teammate

Use this sentence:

> "It is a Python package that talks directly to GemStone Smalltalk, keeps
> transactions explicit, gives us persistence helpers instead of a fake ORM,
> supports async, typed access, managed OOP lifetimes, and optional native
> wheels, and already has real CI, release, benchmark, and live verification
> lanes."

That sentence has rescued several meetings already. At minimum, it should rescue yours.
