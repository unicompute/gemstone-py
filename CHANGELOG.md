# Changelog

All notable changes to `gemstone-py` should be recorded here.

## Unreleased

- Added benchmark smoke/regression profiles, scheduled runner health checks, and opt-in live soak coverage.

## 0.2.0 - 2026-04-21

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
