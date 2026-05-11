# Examples Cookbook

This directory is the stable table of contents for the broader example set.
The runnable modules stay in their historical locations so existing docs,
tests, and user imports keep working.

| Topic | Path | Run |
| --- | --- | --- |
| Quickstart | `examples/quickstart.py` | `python -m examples.quickstart` |
| Plan3 feature map | `examples/cookbook/plan3_feature_map.py` | `python -m examples.cookbook.plan3_feature_map` |
| Realistic web app | `examples/webstack/` | `python -m examples.webstack.magtag_app` |
| Async session basics | `examples/async_features/` | `python -m examples.async_features.session_root_and_collection` |
| FastAPI request dependency | `examples/fastapi/` | `python -m examples.fastapi.run --reload` |
| Litestar request dependency | `examples/litestar/` | `python -m examples.litestar.run --reload` |
| Typed access | `examples/typed_access/` | `python -m examples.typed_access.typed_oops_and_queries` |
| Generated wrappers | `examples/typed_access/codegen_demo/` | `python -m examples.typed_access.codegen_demo.run --reload` |
| Managed OOP lifetime | `examples/lifetime/` | `python -m examples.lifetime.managed_oop_handles` |
| Native backend check | `examples/native_backend/` | `python -m examples.native_backend.check_backend` |
| Persistence recipes | `examples/persistence/` | See each subdirectory README or source docstring. |
| Flask ports | `examples/flask/` | See `examples/README.md`. |
| Django comparison app | `examples/django/myapp/` | `python manage.py runserver` from that directory. |

From an installed package, use:

```bash
gemstone-examples list
gemstone-examples plan3-map
gemstone-examples quickstart
gemstone-examples fastapi --reload
gemstone-examples litestar --reload
```
