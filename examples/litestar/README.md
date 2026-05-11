# Litestar Example

Minimal Litestar app using `gemstone_py.aio.litestar.session_dependency`.

Install the optional dependencies from a source checkout:

```bash
python -m pip install -e ".[examples]"
```

Run the app:

```bash
python -m examples.litestar.run --reload
```

The example intentionally mirrors the FastAPI example's routes so you can
compare framework adapters directly. The Litestar-specific pieces are:

- `@get(...)` route decorators from `litestar`
- `Provide(...)` dependency injection from `litestar.di`
- `gemstone_py.aio.litestar.session_dependency`
- Litestar schema docs at `/schema/swagger` and `/schema/openapi.json`

Then test it from a second terminal:

```bash
curl -i http://127.0.0.1:8000/
curl -i http://127.0.0.1:8000/health/gemstone
```

The root route should include:

```json
{"name":"gemstone-py Litestar example","framework":"Litestar","adapter":"gemstone_py.aio.litestar.session_dependency","dependencyInjection":"litestar.di.Provide","endpoints":{"health":"/health/gemstone","docs":"/schema/swagger","openapi":"/schema/openapi.json"}}
```
