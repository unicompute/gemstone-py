# Changelog

All notable changes to `gemstone-py` should be recorded here.

## Unreleased

## 0.2.10 - 2026-05-10

- Added `fastapi` and `examples` extras so new installs can opt into FastAPI
  and uvicorn dependencies explicitly.
- Added `gemstone-fastapi-example`, `gemstone-examples fastapi`, and
  `python -m examples.fastapi.run` runners that check optional dependencies
  before starting uvicorn.
- Made the FastAPI dependency message use the exact Python executable that is
  missing the optional dependencies.
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
