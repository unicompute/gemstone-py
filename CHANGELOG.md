# Changelog

All notable changes to `gemstone-py` should be recorded here.

## Unreleased

- Added lightweight bulk send helpers, including mixed `PerformCall` batches
  and persistent-root/GsDict batch get/update paths for lower round-trip count.
- Added explicit transaction retry ergonomics and stronger conflict diagnostics,
  including formatted conflict reports and retry helpers that keep application
  retry loops visible instead of hiding them behind an ORM layer.
- Expanded inspection tooling with bounded slot output for safer object dumps.
- Added explicit, opt-in value converters for scalar-ish Python values, package
  root exports for the converter API, batch converter registry helpers, and an
  installed `gemstone-examples value-converters` preview.
- Added generated-wrapper metadata, `__gemstone_protocol__` and
  `__gemstone_selectors__`, so generated APIs can be audited by tools and logs
  without parsing generated source.
- Added schema fingerprinting helpers for checking expected GemStone-side roots,
  class definitions, and indexes before application startup.
- Bumped `gemstone-py-native` to 0.1.3 for the Rust-backed native wheel
  publish lane after the downstream live `RustCoreSession` smoke passed.

## 0.2.14 - 2026-05-11

- Added concrete Codegen examples for offline wrapper preview, reusable
  Workbench selection mappings, and live generated-wrapper probes.
- Expanded the README, examples guide, Codegen guide, Medium article draft,
  typed Codegen demo docs, and VS Code workbench README with runnable Codegen
  commands and selector examples.
- Added VS Code workbench Codegen screenshots for the Command Palette, sidebar
  actions, and Codegen Explorer flow.
- Added entrypoint smoke coverage so Codegen preview and live-probe help stay
  runnable without opening a live GemStone session.

## 0.2.13 - 2026-05-11

- Published the VS Code workbench `0.3.0` Codegen Explorer feature release,
  including live class browsing, wrapper target selection, generated-wrapper
  preview, repository diffing, mapping persistence, and live target probes.
- Documented the visual Codegen Explorer in the README, examples guide,
  Codegen guide, Medium article draft, and workbench README.
- Clarified source-checkout example commands versus installed package commands,
  including `examples.*` module entry points and packaged console scripts.
- Made the Litestar example index route expose its framework adapter and
  dependency-injection path, matching the FastAPI example's discoverable root
  route behavior.

## 0.2.12 - 2026-05-11

- Added VS Code workbench Codegen commands for checking generated wrappers,
  regenerating wrappers, running the generated-wrapper FastAPI demo, and
  opening the Codegen docs from the Command Palette and Examples/Docs sidebar
  views.
- Updated VS Code workbench documentation and smoke coverage so the Codegen
  workflow remains wired to the repository examples.

## 0.2.11 - 2026-05-11

- Added `gemstone-bootstrap`, an idempotent GemStone-side bootstrap/audit
  command for the `GStoreRoot`, `GSQueryRoot`, and bootstrap marker roots.
- Added `GemStoneSessionPool.stats()`, validation-query intervals, and
  idle-timeout eviction on checkout for pooled GemStone sessions.
- Added pool `minsize`, manual `sweep_idle()`, and optional daemon idle
  sweeping that never evicts checked-out sessions.
- Added `AsyncSessionPool` and FastAPI `pool_session_dependency(...)` for
  pool-backed async request handling.
- Added `gemstone_py.web_core` with framework-neutral sync/async request
  scopes, transaction finalizers, and provider protocols, and moved Flask and
  FastAPI request cleanup through the shared lifecycle core.
- Added `gemstone_py.frameworks.flask` as the Flask-specific adapter import
  path and `gemstone_py.aio.litestar` for Litestar dependency and ASGI
  middleware integration.
- Moved sync session provider implementations into `gemstone_py.session_providers`
  while keeping the historical `gemstone_py.web` and top-level imports stable.
- Added a dependency-light Django adapter under `gemstone_py.frameworks.django`
  for request-scoped GemStone sessions backed by the shared web lifecycle core.
- Added a runnable Litestar example, `gemstone-litestar-example`, and framework
  adapter docs showing how to build new adapters on `gemstone_py.web_core`.
- Added `gemstone-examples list`, `gemstone-examples litestar`, and
  `examples/cookbook/` as a stable index for the broader example set.
- Added a top-level two-minute README start path and made `gemstone_py.cli`
  executable through `python -m gemstone_py.cli`.
- Added `docs/plan3-feature-map.md`, `examples/cookbook/plan3_feature_map.py`,
  and `gemstone-examples plan3-map` to map each plan3 stream to code, examples,
  and docs.
- Expanded the Medium article with a plan3 summary section that emphasizes
  Codegen and maps all streams to user-facing features.
- Added chunked `GSCollection.iter(...)`, `search_iter(...)`, typed
  `Query.iter(...)`, and async iterator equivalents for large result sets.
- Made `GSCollection.search()`, `GSCollection.all()`, and typed `Query.all()`
  materialize through the chunked iterator path, with benchmark coverage for
  `all()` versus streaming `iter()` memory use.
- Added `gemstone_py.observability` with no-op defaults, OpenTelemetry and
  Prometheus adapters, session operation metrics, and slow-operation logging.
- Extended observability to sync/async session pools and chunked query
  iterators, including pool event counters and acquire-wait timings.
- Added `GemStoneSession.inspect(...)`, `dump(...)`, `describe_class(...)`, and
  the `gemstone-inspect` CLI for inspecting live GemStone objects and classes.
- Added `gemstone-codegen`, `@gemstone_selector(...)`, Protocol-to-`TypedOop`
  wrapper generation, async wrapper generation, CI `--check` mode, and a typed
  access codegen demo.
- Extended generated wrappers to preserve simple Protocol annotations, return
  `None` for command-style methods, wrap self-typed OOP results, and run a
  repository codegen drift check from CI/pre-commit.
- Added same-module cross-Protocol wrapper returns, generated `py.typed`
  markers, and `gemstone-codegen --clean` stale-wrapper cleanup.
- Added generated `.pyi` stubs for wrapper packages so IDEs and type checkers
  can consume the checked-in codegen output without inspecting implementation
  details.
- Added a runnable generated-wrapper FastAPI demo entry point with smoke
  coverage for the index, docs, and generated booking route.
- Added module-style migration planning, dry-run, version tracking,
  rollback, scaffold generation, and the `gemstone-migrations` CLI while
  preserving the legacy `Migration` base class.
- Extended `gemstone-migrations` with `current`, `plan`, `upgrade`, and
  `downgrade` commands plus manifest/checksum drift checks before applying
  new migrations.
- Added migration status and class-diff helpers, including
  `gemstone-migrations status` and `gemstone-migrations diff-class`, for
  comparing local Protocol/type-witness fields with live GemStone class
  instance variables.
- Added a GemStone-side advisory migration lock for real upgrade/downgrade
  runs, with stale-lock and forced-lock CLI controls.
- Added recorded migration dry-runs with `--dry-run --record` and a live
  GemStone migration upgrade/downgrade smoke test in the live check lane.
- Added `gemstone-publish-verify`, an end-to-end PyPI/TestPyPI verifier for
  project JSON, version-specific JSON, simple index pages, and temporary
  virtualenv install smoke checks.
- Added smoke coverage for the FastAPI example's `/`, `/docs`, and
  `/health/gemstone` routes.
- Tightened the VS Code workbench Marketplace workflow to publish with
  `VSCE_PAT` explicitly and verify the public Marketplace listing after
  publishing.
- Made the VS Code workbench database explorer launcher warn before startup
  when `GS_USERNAME` or `GS_PASSWORD` is missing from `gemstonePy.env`.
- Expanded install, release, and verification docs for installed packages,
  source checkouts, native acceleration, VSIX publishing, and release
  checklists.

## 0.2.10 - 2026-05-10

- Added `fastapi` and `examples` extras so new installs can opt into FastAPI
  and uvicorn dependencies explicitly.
- Added `gemstone-fastapi-example`, `gemstone-examples fastapi`, and
  `python -m examples.fastapi.run` runners that check optional dependencies
  before starting uvicorn.
- Made the FastAPI dependency message use the exact Python executable that is
  missing the optional dependencies.
- Changed the source-checkout dependency guidance to prefer a repository
  virtualenv, so Homebrew's externally managed Python does not send users down
  a failing global-install path.
- Made the FastAPI source-checkout runner automatically hand off to the local
  `.venv` Python when the current interpreter is missing FastAPI or uvicorn.
- Added a FastAPI example index at `/` so opening the base URL shows the
  available docs and health-check routes instead of FastAPI's default 404.
- Documented expected startup output plus curl and browser checks for verifying
  `examples.fastapi.run`.
- Made the FastAPI example print the same verification checks when the server
  starts.
- Made the FastAPI example start without GemStone credentials and report missing
  `GS_USERNAME` or `GS_PASSWORD` as a 503 response when the endpoint is called.
- Updated the VS Code workbench FastAPI example launcher to use the dependency
  checking repository runner instead of calling `python -m uvicorn` directly.

## 0.2.9 - 2026-05-10

- Added runnable examples for async sessions/FastAPI support, typed OOPs and
  typed queries, managed OOP lifetime handles, and native backend selection.
- Updated the README and documentation set to cover async, typed access,
  managed lifetimes, native backend selection, and the new examples.
- Expanded the examples guide with concrete usage commands and code snippets.
- Added a generated PDF for the Medium-style article and linked the article to
  its PNG header image asset.

## 0.2.8 - 2026-05-10

- Made the local/CI Ruff gate cover the whole repository with explicit legacy
  ignores for translated example metadata and embedded long-form content.
- Fixed full-repository Ruff findings in examples, tests, and compatibility
  modules without changing runtime behavior.
- Made benchmark baseline matching backend-aware so ctypes and native GCI
  benchmark reports are not compared accidentally.
- Registered a current macOS ARM64 Python 3.14.4 ctypes benchmark baseline for
  the self-hosted runner.
- Added post-release PyPI verification for `gemstone-py[fast]` so the workflow
  confirms the published native backend is installed and selected.

## 0.2.7 - 2026-05-10

- Updated the `fast` extra to require `gemstone-py-native>=0.1.2`, the first
  native release verified through PyPI Trusted Publishing.
- Bumped `gemstone-py-native` to 0.1.2 for the PyPI Trusted Publishing
  verification release.
- Removed PyPI API-token fallback from the pure release workflow now that PyPI
  publishes use GitHub OIDC trusted publishing.
- Removed PyPI API-token fallback from the native release workflow now that
  PyPI publishes use GitHub OIDC trusted publishing.
- Scoped the native wheel workflow's automatic push trigger to branch pushes so
  pure release tags do not start redundant native builds.
- Removed TestPyPI API-token fallback from pure and native release workflows now
  that TestPyPI publishes use GitHub OIDC trusted publishing.

## 0.2.6 - 2026-05-09

- Added the async session, async pool, FastAPI dependency, and async live coverage paths.
- Added typed managed object handles, identity-aware proxy caching, and explicit remote lifetime disposal support.
- Added the optional PyO3 native GCI extension package with Linux, macOS, Windows, x86_64, ARM64, and Linux ARMv7 wheel builds.
- Hardened TestPyPI/PyPI release verification for pure and native artifacts.

## 0.2.5 - 2026-04-22

- Updated documentation diagrams: improved arrow routing in architecture overview, examples map, and cookbook flow SVGs.
- Rebuilt companion PDF with corrected visuals.

## 0.2.4 - 2026-04-21

- Published to PyPI and Test PyPI.

## 0.2.3 - 2026-04-21

- Added a full `docs/` manual set with a setup guide, user manual, examples guide, cookbook, and a long-form humorous introduction.
- Added repository-native SVG diagrams, screenshot-style illustrations, and cartoons for the new docs set.
- Added a local PDF build pipeline for the docs and generated companion/manual/book PDFs under `docs/pdf/`.
- Fixed SVG layout issues in the generated book/manual assets so text fits cleanly in the rendered PDF boxes.

## 0.2.2 - 2026-04-21

- Cleaned the public package metadata and README rendering so PyPI no longer shows local absolute paths or repo-local file links in the long description.
- Added explicit project URLs for the homepage, repository, issues, changelog, and runner guide.

## 0.2.1 - 2026-04-21

- Upgraded the release workflows to Node 24-compatible GitHub Actions majors.
- Verified the tag-triggered release path against the updated workflow stack after the `0.2.0` publish.

## 0.2.0 - 2026-04-21

- Added benchmark smoke/regression profiles, scheduled runner health checks, and opt-in live soak coverage.

- Added metadata-aware benchmark comparison guardrails and threshold enforcement.
- Added release workflow validation for tag/version/changelog consistency before publishing.
- Added environment-specific benchmark baseline selection through `.github/benchmarks/index.json`.
- Switched manual PyPI publish to trusted publishing via GitHub OIDC.
- Ratcheted `mypy` further on `concurrency.py`, `gsquery.py`, `gstore.py`, `client.py`, and `web.py`.
- Added dedicated `Release Dry Run` and `Release TestPyPI` workflows for release rehearsals.
- Added built-artifact non-live behavior checks and benchmark baseline lifecycle tooling with manifest prune/drop support.
- Hardened the self-hosted runner bootstrap/service flow with health checks, upgrade support, and latest-release detection.
- Added optional live soak tests for repeated pool reuse and multi-writer contention convergence.
- Split benchmark governance into named `smoke` and `regression` profiles and scheduled runner-health drift detection.

## 0.1.0 - 2026-04-20

- Established `gemstone_py.*` as the canonical package surface.
- Added explicit transaction policy and config handling for sessions.
- Split runtime concerns across client, web, persistence, and benchmark modules.
- Added pooled and thread-local web/session providers with live integration coverage.
- Added benchmark and benchmark-compare CLIs plus GitHub benchmark workflows.
- Removed Ruby/MagLev runtime dependencies from the supported Python surface.
