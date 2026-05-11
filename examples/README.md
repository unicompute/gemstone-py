# GemStone Python Examples

Runnable examples for `gemstone-py`.

## Start Here

Run the quickstart first. It is intentionally small: connect, evaluate
Smalltalk, write a value under `UserGlobals`, and read it back.

```bash
python -m examples.quickstart
```

Then use the broader examples as a cookbook. The import paths are stable and
are referenced by tests and docs, so the examples stay in their current
directories rather than being moved under a physical `cookbook/` package.

For a fresh stone, initialize the GemStone-side roots used by the persistence
helpers before exploring the larger examples:

```bash
gemstone-bootstrap --status
gemstone-bootstrap
```

The command creates missing `GStoreRoot` and `GSQueryRoot` entries under
`UserGlobals` without replacing existing application data.

## Example Map

| Role | Path | Use it when |
| --- | --- | --- |
| Quickstart | `examples/quickstart.py` | You want the smallest live connection example. |
| Grand tour | `examples/example.py` | You want one script that touches most persistence helpers. |
| Realistic reference app | `examples/webstack/` | You want a web app with users, follows, and persisted posts. |
| Async/FastAPI cookbook | `examples/async_features/`, `examples/fastapi/` | You need async sessions or request dependencies. |
| Typed-access cookbook | `examples/typed_access/` | You want `TypedOop`, protocols, and typed queries. |
| Lifetime cookbook | `examples/lifetime/` | You need managed OOP/export-set lifetime examples. |
| Native backend cookbook | `examples/native_backend/` | You need to verify `ctypes` versus native backend selection. |
| Persistence cookbook | `examples/persistence/` | You want indexing, migrations, key/value, and collection recipes. |
| Flask cookbook | `examples/flask/` | You need request sessions, Flask sessions, or small web ports. |
| Django comparison | `examples/django/myapp/` | You want a familiar Django CRUD comparison app. |

## Feature Mapping

| GemStone / app concept | Python example surface |
|------------------------|------------------------|
| Session-bound persistence | `PersistentRoot(session)` or `GemStoneSessionFacade(session).persistent_root` |
| Async sessions and request-friendly access | `examples/async_features/` and `examples/fastapi/` |
| Typed OOPs and typed collection queries | `examples/typed_access/` |
| Export-set lifetime handles | `examples/lifetime/` |
| Optional native backend discovery | `examples/native_backend/` |
| Model-style helpers | `gemstone_model.py` |
| Request transaction wrapper | Flask `SessionInterface` / `before_request` |
| Web application examples | Flask / Django / `examples/webstack/` |

## Prerequisites

```
pip install flask django pytest
export GS_LIB=/Users/tariq/GemStone64Bit3.7.4.3-arm64.Darwin/lib
export GS_STONE=gs64stone
export GS_STONE_NAME=gs64stone
export GS_USERNAME=DataCurator
export GS_PASSWORD=swordfish
```

`GS_STONE_NAME` is accepted as an alias when `GS_STONE` is absent. Setting both
to the same value keeps these examples and companion tools aligned.

## Scope

- Plain GemStone ports: persistence helpers, collection wrappers, `SmalltalkBridge`, and `GemStoneSessionFacade` work on a normal GemStone image.

See [PORTING_SCOPE.md](/Users/tariq/src/gemstone-py/PORTING_SCOPE.md) for the full split.

Use canonical `gemstone_py.*` imports throughout the examples.

For maintained performance measurement of the core persistence helpers, use
the real benchmark lane instead of the example scripts:

```bash
./scripts/run_benchmarks.sh
gemstone-benchmarks --entries 500 --search-runs 20
```

The runnable examples no longer patch `sys.path` at startup. Run them as
modules from the repo root, or use the installed console scripts for the
packaged demos:

```bash
python -m examples.misc.smalltalk_demo
gemstone-smalltalk-demo
```

For Flask examples that install request-session handling, use
`flask_request_session_provider_snapshot(app)` to inspect pool/provider state
and `close_flask_request_session_provider(app)` during explicit shutdown.

---

## quickstart.py

The canonical first live example. It verifies the connection with `3 + 4`,
stores a small Python dictionary under `UserGlobals`, and reads it back.

```
python -m examples.quickstart
gemstone-examples quickstart
```

---

## async_features/

Runs the async session facade, async persistent root, async managed OOP handles,
and async `GSCollection` wrapper against a configured stone.

```
python -m examples.async_features.session_root_and_collection
```

---

## typed_access/

Shows both static typing surfaces:

- `TypedOop[T]` with `@gemstone_class(...)`
- typed `GSCollection.query(Protocol)` predicates

```
python -m examples.typed_access.typed_oops_and_queries
```

`simple_blog_queries.py` also contains importable helper functions for the
existing simple-blog data shape.

---

## lifetime/

Demonstrates `execute_managed(...)` for automatic export-set retention and
`session.handle(...)` for explicit scoped retention of a raw OOP.

```
python -m examples.lifetime.managed_oop_handles
```

---

## native_backend/

Prints whether the optional PyO3 native backend is importable and which GCI
backend the current Python process selected.

```
python -m examples.native_backend.check_backend
GEMSTONE_PY_GCI_BACKEND=ctypes python -m examples.native_backend.check_backend
GEMSTONE_PY_GCI_BACKEND=native python -m examples.native_backend.check_backend
```

---

## fastapi/

Minimal FastAPI app using `gemstone_py.aio.fastapi.session_dependency`.

```
python -m pip install -e ".[examples]"
python -m examples.fastapi.run --reload
```

---

## hello_gemstone.py

Prints Python version and engine.

```
python -m examples.hello_gemstone
gemstone-hello
```

---

## misc/

`misc/smalltalk_demo.py` is the default Smalltalk-first path and demonstrates
`SmalltalkBridge`, Python marshalling, and `GemStoneSessionFacade`.

```
python -m examples.misc.smalltalk_demo
gemstone-smalltalk-demo
```

---

## persistence/hat_trick/

Stores a hat (OrderedCollection) and rabbits in GemStone UserGlobals.

```
python -m examples.persistence.hat_trick.create_hat
python -m examples.persistence.hat_trick.add_rabbit_to_hat
python -m examples.persistence.hat_trick.show_hat_contents
```

---

## persistence/indexing/

Creates 10,000 Person objects in GemStone and benchmarks filtering queries in Python.

```
python -m examples.persistence.indexing.index_example
```

---

## flask/sinatra_port/

Direct Flask translation showing routes, URL parameters, sessions, and redirects.

```
python -m examples.flask.sinatra_port.app
pytest test_app.py -v   # run the tests
```

---

## flask/simple_blog/

A blog with posts and tags stored in GemStone.

```
python -m examples.flask.simple_blog.blog_app
# visit http://localhost:5000/posts
```

---

## flask/sessions/

HTTP sessions stored in GemStone UserGlobals using a Flask `SessionInterface`.

```
python -m examples.flask.sessions.msessions
# visit http://localhost:4568
```

---

## webstack/

MagTag, the Twitter-like demo. Users, following, and tweets persisted in GemStone.

```
python -m examples.webstack.magtag_app
# visit http://localhost:4567/setup   (create demo users)
# login as pbm0 / pbm0
```

---

## django/myapp/

A Posts CRUD app using Django ORM + SQLite. Same REST routes, JSON
responses, and form handling.

```
cd django/myapp
pip install django
python manage.py migrate
python manage.py runserver
# visit http://localhost:8000/posts/
```
