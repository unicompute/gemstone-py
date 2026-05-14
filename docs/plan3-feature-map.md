# Plan3 Feature Map

This page maps the plan3 streams to the current repository surface. It is a
navigation aid for users and maintainers: start here when you know the feature
area but not the module, example, or doc page.

| Stream | Feature | Main modules | Examples | Docs |
| --- | --- | --- | --- | --- |
| 1 | Pool + health | `gemstone_py.session_providers`, `gemstone_py.aio.pool` | `examples/fastapi/`, `examples/litestar/` | `docs/user-manual.md`, `docs/cookbook.md` |
| 2 | Streaming results | `gemstone_py.gsquery`, `gemstone_py.aio.gsquery` | `examples/async_features/` | `docs/examples-guide.md`, `docs/performance.md` |
| 3 | Typed codegen | `gemstone_py.codegen` | `examples/typed_access/codegen_demo/` | `docs/codegen.md` |
| 4 | Observability | `gemstone_py.observability` | web examples with provider snapshots and metrics | `docs/observability.md` |
| 5 | Migrations | `gemstone_py.migrations` | `examples/persistence/migrations/` | `docs/cookbook.md`, `docs/user-manual.md` |
| 6 | Inspect/debug | `gemstone_py.inspection`, `GemStoneSession.inspect`, `dump`, `describe_class` | `examples/cookbook/` | `docs/user-manual.md` |
| 7 | Framework adapters | `gemstone_py.web_core`, `gemstone_py.frameworks`, `gemstone_py.aio.fastapi`, `gemstone_py.aio.litestar` | `examples/fastapi/`, `examples/litestar/`, `examples/django/` | `docs/framework-adapters.md` |
| 8 | Examples | `gemstone_py.cli` | `examples/quickstart.py`, `examples/webstack/`, `examples/cookbook/` | `examples/README.md`, `docs/examples-guide.md` |
| 9 | Performance docs | `gemstone_py.benchmarks`, `gemstone_py.benchmark_compare` | `examples/native_backend/` | `docs/performance.md` |
| 10 | Native wheels | `gemstone_py.native`, `gemstone-py-native/` | `examples/native_backend/` | `README.md`, `RELEASE_CHECKLIST.md` |
| 11 | Bootstrap | `gemstone_py.bootstrap`, `gemstone_py/_gemstone_side/` | `examples/quickstart.py`, `examples/cookbook/` | `docs/setup-guide.md` |
| 12 | Bulk operations | `GemStoneSession.bulk_perform_*`, `PersistentRoot.get_many`, `GsDict.update_many`, `OrderedCollection.extend` | `examples/example.py`, cookbook snippets | `docs/user-manual.md`, `docs/performance.md`, `docs/cookbook.md` |
| 13 | Retry and diagnostics | `gemstone_py.transactions`, `gemstone_py.concurrency` | conflict examples and tests | `docs/user-manual.md`, `docs/cookbook.md`, `docs/observability.md` |
| 14 | Explicit value conversion | `gemstone_py.converters` | `examples/cookbook/value_converters.py` | `docs/cookbook.md`, `docs/user-manual.md` |
| 15 | Schema fingerprinting | `gemstone_py.migrations.schema_fingerprint`, `gemstone-migrations fingerprint` | migration examples | `docs/user-manual.md`, `docs/cookbook.md` |

## Commands

From an installed package:

```bash
gemstone-examples plan3-map
gemstone-examples value-converters
```

From a source checkout:

```bash
python -m examples.cookbook.plan3_feature_map
python -m gemstone_py.cli plan3-map
```

## Notes

The historical example paths are intentionally stable. `examples/cookbook/`
acts as a table of contents rather than a mass move of existing modules, so old
links, tests, and user imports continue to work.
