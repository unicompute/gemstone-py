# GemStone Python Examples

Runnable examples for `gemstone-py`.

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
| Web application examples | Flask / Django |

## Prerequisites

```
pip install flask django pytest
export GS_LIB=/Users/tariq/GemStone64Bit3.7.4.3-arm64.Darwin/lib
export GS_STONE=gs64stone
export GS_USERNAME=DataCurator
export GS_PASSWORD=swordfish
```

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
uvicorn examples.fastapi.app:app --reload
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
