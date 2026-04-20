# Changelog

All notable changes to `gemstone-py` should be recorded here.

## Unreleased

- Added metadata-aware benchmark comparison guardrails and threshold enforcement.
- Added release workflow validation for tag/version/changelog consistency before publishing.
- Added environment-specific benchmark baseline selection through `.github/benchmarks/index.json`.
- Switched manual PyPI publish to trusted publishing via GitHub OIDC.
- Ratcheted `mypy` further on `concurrency.py`, `gsquery.py`, and `gstore.py`.
- Added a dedicated `Release Dry Run` GitHub workflow for release rehearsals without publishing.
- Tightened `mypy` to `strict` on `client.py`.
- Added a `Release TestPyPI` workflow and built-artifact non-live behavior checks.
- Extended benchmark baseline lifecycle tooling with manifest prune/drop support.

## 0.1.0 - 2026-04-20

- Established `gemstone_py.*` as the canonical package surface.
- Added explicit transaction policy and config handling for sessions.
- Split runtime concerns across client, web, persistence, and benchmark modules.
- Added pooled and thread-local web/session providers with live integration coverage.
- Added benchmark and benchmark-compare CLIs plus GitHub benchmark workflows.
- Removed Ruby/MagLev runtime dependencies from the supported Python surface.
