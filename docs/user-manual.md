# User Manual

This manual explains the public surface of `gemstone-py` from the point of view
of a user who wants to build reliable code, not just make a demo print a nice
dictionary once.

## The Mental Model

Three ideas matter more than the rest:

1. Python code drives the application.
2. GemStone stores the persistent state.
3. Transactions are explicit enough that you can explain them to another human.

`gemstone-py` is not trying to hide GemStone completely. It gives you a Pythonic
surface, but it still wants you to understand:

- when sessions are opened and closed
- when transactions commit or abort
- which data structures are persisted in GemStone
- what happens when two sessions try to change the same thing

That restraint is a strength. The library does not pretend that distributed
state is a teddy bear.

## Core Building Blocks

### `GemStoneConfig`

`GemStoneConfig` is the runtime configuration object. In most applications you
will construct it from the environment:

```python
from gemstone_py import GemStoneConfig

config = GemStoneConfig.from_env()
```

Use it when:

- you want a single source of connection settings
- you need to pass the same config into sessions, stores, or web providers
- you want to validate missing credentials early

### `GemStoneSession`

This is the direct session object. Use it when you want explicit session and
transaction control.

Typical pattern:

```python
from gemstone_py import GemStoneSession, TransactionPolicy

with GemStoneSession(
    config=config,
    transaction_policy=TransactionPolicy.COMMIT_ON_SUCCESS,
) as session:
    print(session.eval("System myUserProfile userId"))
```

Useful methods include:

- `eval(...)`
  Evaluate Smalltalk code directly.
- `commit()`
  Commit the current transaction.
- `abort()`
  Abort the current transaction.
- `global_get(...)`
  Resolve named objects from the repository.

When to use it:

- scripts
- lower-level tooling
- integration code that must control failure behaviour precisely

### `session_scope(...)`

This is the higher-level unit-of-work helper. It is usually the right answer for
application code.

```python
from gemstone_py import session_scope

with session_scope(config=config) as session:
    ...
```

Why it exists:

- it makes commit-on-success intent obvious
- it composes naturally with service-layer code
- it avoids sprinkling `commit()` everywhere like nervous confetti

## Transaction Policies

`TransactionPolicy` exists so you do not have to guess what a context manager
will do.

The main values are:

- `MANUAL`
- `COMMIT_ON_SUCCESS`
- `ABORT_ON_EXIT`

Recommended use:

| Situation | Policy |
| --- | --- |
| low-level explicit control | `MANUAL` |
| script that writes data | `COMMIT_ON_SUCCESS` |
| read-only inspection | `ABORT_ON_EXIT` |
| request/response web unit of work | `COMMIT_ON_SUCCESS` via `session_scope(...)` or request integration |

## `PersistentRoot`

`PersistentRoot` is the friendliest entry point into repository-backed state.

The default instance is the user's `UserGlobals` dictionary:

```python
from gemstone_py.persistent_root import PersistentRoot

root = PersistentRoot(session)
root["CustomerCount"] = 12
```

Other dictionaries are also available:

- `PersistentRoot.globals(session)`
- `PersistentRoot.published(session)`
- `PersistentRoot.session_methods(session)`

Use `PersistentRoot` when:

- you want a stable named entry point
- you are storing dictionaries, counters, queues, or domain objects
- you want something simple and direct

Use something more specialized when:

- you need indexed search across many rows -> `GSCollection`
- you want a file-like key/value store abstraction -> `GStore`
- you want append-only event style logging -> `ObjectLog`

### Good Practices With `PersistentRoot`

- keep the top-level key space tidy
- use descriptive names
- group related data under one top-level bucket when it makes sense
- do not turn `UserGlobals` into a junk drawer with no naming discipline

## `GSCollection`

`GSCollection` is the indexed collection helper. It is the right tool when you
need more than "look up a dictionary by a single well-known key."

Use it for:

- indexed search
- filtering by stored attributes
- application collections with repeatable lookup patterns

Typical pattern:

```python
from gemstone_py.gsquery import GSCollection

people = GSCollection("People", config=config)
people.insert({"name": "Tariq", "city": "London"})
people.create_equality_index("city")
matches = people.search("city", "London")
```

Think of it as the package's middle ground between:

- raw repository objects
- and a full ORM that wants to restructure your life

## `GStore`

`GStore` is a GemStone-backed key/value store with its own transactional
behaviour around store operations.

Use it when:

- you want a store-like API
- you want separate named stores
- you want a compact way to persist structured payloads

Typical pattern:

```python
from gemstone_py.gstore import GStore

store = GStore("inventory.db", config=config)
store["sku:123"] = {"name": "Hat", "stock": 8}
print(store["sku:123"])
```

`GStore` is especially handy in examples, utilities, and small application
components that want a store-shaped abstraction without building a full domain
model first.

## `ObjectLog`

`ObjectLog` is the package's event-log helper. It is good for:

- audit trails
- structured append-only logging
- "what happened?" questions after a workflow ran

Typical pattern:

```python
from gemstone_py.objectlog import ObjectLog

log = ObjectLog(config=config)
log.info("user_created", {"user": "tariq", "source": "manual"})
for entry in log.entries():
    print(entry)
```

This is not a replacement for Python logging. It is a repository-resident event
log for when the record should live with the data.

## Concurrency Helpers

The concurrency helpers give you shared, repository-backed coordination
primitives:

- `RCCounter`
- `RCHash`
- `RCQueue`

These are useful when you need shared mutable state between sessions and want
the concurrency semantics to live in GemStone instead of in a Python process.

Use them carefully:

- they are powerful
- they make contention visible
- they will teach you honesty about multi-session behaviour

The package also includes:

- nested transaction helpers
- conflict detection helpers
- instance listing utilities

### Commit Conflicts

When two sessions modify the same object and both try to commit, GemStone raises
a conflict. The second committer gets a `CommitConflictError`.

This is not a bug. It is the correct behaviour of an optimistic concurrency
system. The right response is:

1. catch `CommitConflictError`
2. call `session.abort()` to reset the transaction
3. reload the data
4. reapply the change (with a narrowed scope if possible)
5. retry the commit

Keep retries bounded. Log them. If you see frequent conflicts on the same
object, that is a signal the write pattern needs rethinking — not that the
concurrency model is wrong.

```python
from gemstone_py import GemStoneSession, TransactionPolicy
from gemstone_py.concurrency import CommitConflictError

for attempt in range(3):
    with GemStoneSession(config=config,
                         transaction_policy=TransactionPolicy.MANUAL) as session:
        try:
            counter = session.global_get("Visits")
            session.eval(f"Visits := {counter + 1}")
            session.commit()
            break
        except CommitConflictError:
            session.abort()
            if attempt == 2:
                raise
```

## Web Integration

The web integration lives in `gemstone_py.web`.

The main pieces are:

- `install_flask_request_session(...)`
- `GemStoneSessionPool`
- `GemStoneThreadLocalSessionProvider`
- `session_scope(...)`

### One Session Per Request

If you are building a Flask app, use the request integration so the request
lifecycle decides the final transaction outcome.

That avoids the worst class of web persistence bugs:

- request handled an exception
- response still rendered
- persistence layer silently committed partial work anyway

The package already corrected this behaviour at the framework layer, so use it.

### Pool vs Thread-Local

Use `GemStoneSessionPool` when:

- you have multiple request workers
- you want bounded reuse
- you want production-friendly pooling semantics

Use `GemStoneThreadLocalSessionProvider` when:

- your threading model is simple and stable
- one session per thread is the clearest fit

## Benchmarks and Build Lanes

This package has both examples and maintained operational lanes. Keep them
separate in your head.

Examples are for:

- learning
- translation exercises
- inspection

The benchmark lane is for:

- reproducible measurement
- stored JSON reports
- baseline comparison
- GitHub workflow enforcement

The CLI is:

```bash
gemstone-benchmarks --entries 500 --search-runs 20
```

## Release and Packaging Surface

The public install surface is the `gemstone_py` package.

The package now has:

- PyPI publishing
- TestPyPI rehearsal
- post-release verification against real PyPI
- installed-artifact API contract checks

That means you can treat the package as a real distributable unit, not just a
working directory with ambition.

## Recommended Adoption Path

If you are bringing `gemstone-py` into a project, a sensible order is:

1. start with `GemStoneConfig` + `GemStoneSession`
2. move most application work into `session_scope(...)`
3. use `PersistentRoot` first for obvious top-level state
4. introduce `GSCollection` only when indexed queries are justified
5. use web providers once request lifecycles matter
6. add benchmarks and live tests once the system is real

That order keeps the learning curve honest without making the first week feel
like a database theology seminar.

## Manual Summary

If you remember only five things:

1. Be explicit about transaction policy.
2. Use `PersistentRoot` first unless you need something more specialized.
3. Let Flask request teardown decide commit vs abort.
4. Treat concurrency helpers as real shared state, not cute toys.
5. The examples teach the package; the maintained workflows prove it.
