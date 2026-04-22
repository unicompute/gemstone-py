# Changelog

All notable changes to `gemstone-py` should be recorded here.

## Unreleased

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
