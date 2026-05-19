# Plan3 Feature Map

This page maps the plan3 improvement streams to the code, examples, and docs
that now carry each feature. It is a quick orientation page for release review,
new contributors, and the VS Code workbench docs view.

The same map is available from the command line:

```bash
gemstone-examples plan3-map
python -m examples.cookbook.plan3_feature_map
```

## Status

| Stream | Status | Main Surface |
| --- | --- | --- |
| 1. Pool + health | Landed | `GemStoneSessionPool`, `AsyncSessionPool`, pool-backed FastAPI/Litestar dependencies |
| 2. Streaming results | Landed | `GSCollection.search_iter(...)`, `GSCollection.iter(...)`, `Query.iter(...)`, async query iteration |
| 3. Typed codegen | Landed | `gemstone-codegen`, generated wrappers, async wrappers, `.pyi` stubs, drift checks |
| 4. Observability | Landed | tracing, metrics, slow-operation logging, pool/session observations |
| 5. Migrations | Landed | module migrations, rollback, dry-run, class diff, schema fingerprinting |
| 6. Inspect/debug | Landed | `session.inspect(...)`, `session.dump(...)`, `session.describe_class(...)`, `gemstone-inspect` |
| 7. Framework adapters | Landed | `web_core`, Flask/Django adapters, FastAPI/Litestar async adapters |
| 8. Examples | Landed | quickstart, examples guide, cookbook map, workbench example runner |
| 9. Performance docs | Landed | benchmark CLI, compare/register helpers, committed baseline docs |
| 10. Native wheels | Landed | PyO3 native package, stable-ABI wheel workflow, release checks |
| 11. Bootstrap | Landed | packaged GemStone-side `init.st`, `gemstone-bootstrap`, setup docs |

## Stream Details

| Stream | Modules | Examples | Docs |
| --- | --- | --- | --- |
| Pool + health | `gemstone_py.session_providers`, `gemstone_py.aio.pool` | `examples/fastapi/`, `examples/litestar/` | [User Manual](user-manual.md), [Cookbook](cookbook.md) |
| Streaming results | `gemstone_py.gsquery`, `gemstone_py.aio.gsquery` | `examples/async_features/` | [Examples Guide](examples-guide.md), [Performance](performance.md) |
| Typed codegen | `gemstone_py.codegen` | `examples/typed_access/codegen_demo/` | [Type-Safe Smalltalk Codegen](codegen.md) |
| Observability | `gemstone_py.observability` | `examples/fastapi/`, `examples/litestar/` | [Observability](observability.md) |
| Migrations | `gemstone_py.migrations` | `examples/persistence/migrations/` | [Cookbook](cookbook.md), [User Manual](user-manual.md) |
| Inspect/debug | `gemstone_py.inspection`, `GemStoneSession.inspect`, `GemStoneSession.dump`, `GemStoneSession.describe_class` | `examples/cookbook/` | [User Manual](user-manual.md) |
| Framework adapters | `gemstone_py.web_core`, `gemstone_py.frameworks`, `gemstone_py.aio.fastapi`, `gemstone_py.aio.litestar` | `examples/fastapi/`, `examples/litestar/`, `examples/django/` | [Framework Adapters](framework-adapters.md) |
| Examples | `gemstone_py.cli` | `examples/quickstart.py`, `examples/webstack/`, `examples/cookbook/` | [Examples Guide](examples-guide.md), [examples/README.md](../examples/README.md) |
| Performance docs | `gemstone_py.benchmarks`, `gemstone_py.benchmark_compare` | `examples/native_backend/` | [Performance](performance.md) |
| Native wheels | `gemstone_py.native`, `gemstone-py-native/` | `examples/native_backend/` | [README](../README.md), [Release Checklist](../RELEASE_CHECKLIST.md) |
| Bootstrap | `gemstone_py.bootstrap`, `gemstone_py/_gemstone_side/` | `examples/quickstart.py`, `examples/cookbook/` | [Setup Guide](setup-guide.md) |

## Verification Gates

Before treating the plan3 batch as release-ready, run the local checks:

```bash
.venv/bin/python -m ruff check gemstone_py tests
.venv/bin/python -m mypy
.venv/bin/python -m pytest -q
./scripts/check_codegen.sh
```

Then run the live GemStone checks on a configured stone:

```bash
GS_RUN_LIVE=1 ./scripts/run_live_checks.sh
```

For release packaging, validate the native package workflow and the workbench
extension release checks:

```bash
./scripts/run_native_checks.sh
cd vscode-gemstone-py-workbench
npm run release:preflight
npm run release:verify-vsix
```
