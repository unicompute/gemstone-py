# Release Checklist

Use this before cutting a tagged release or publishing artifacts.

1. Install the dev toolchain:
```bash
python3 -m pip install -e .[dev]
```

Update `pyproject.toml` and add an entry to [CHANGELOG.md](/Users/tariq/src/gemstone-py/CHANGELOG.md:1)
before cutting a new version.

The GitHub `Release` workflow now validates that the release tag matches
`project.version` and that the same version is present in
[CHANGELOG.md](/Users/tariq/src/gemstone-py/CHANGELOG.md:1).

2. Run the local CI lane:
```bash
./scripts/run_ci_checks.sh
```

3. Run the build/install artifact smoke lane:
```bash
./scripts/run_build_smoke.sh
```

4. Run the opt-in live GemStone lane against a configured stone:
```bash
GS_RUN_LIVE=1 ./scripts/run_live_checks.sh
```

5. Run the maintained benchmark lane and keep the JSON report with the release notes:
```bash
./scripts/run_benchmarks.sh --json --output benchmark-report.json
```

6. Compare the new benchmark report to the previous saved baseline:
```bash
gemstone-benchmark-compare previous-benchmark-report.json benchmark-report.json
gemstone-benchmark-compare previous-benchmark-report.json benchmark-report.json --suite-threshold persistent_root=7.5
gemstone-benchmark-compare previous-benchmark-report.json benchmark-report.json --operation-threshold persistent_root/mapping_keys=5
```
If you accept the new numbers, add the accepted report under
`.github/benchmarks/` and register it in
[.github/benchmarks/index.json](/Users/tariq/src/gemstone-py/.github/benchmarks/index.json:1)
so the GitHub `Benchmarks` workflow can select it automatically for matching
environments.

7. Build fresh release artifacts:
```bash
python3 -m build --sdist --wheel
```

8. Inspect the outputs under `dist/` and verify the console commands from an installed artifact:
```bash
gemstone-benchmark-compare --help
gemstone-hello
gemstone-examples hello
gemstone-smalltalk-demo
```

9. Use the manual `Release Dry Run` workflow for a GitHub-side rehearsal without publishing.

10. Use the manual `Release TestPyPI` workflow if you want a full publish rehearsal against TestPyPI. It now publishes to TestPyPI and then installs the published version back into a clean runner for post-publish API/CLI verification.

11. Run the optional live soak lane if you want higher confidence before a production release:
```bash
GS_RUN_LIVE=1 GS_RUN_LIVE_SOAK=1 ./scripts/run_live_checks.sh
```

12. Tag and publish only after the checks above are green.

For GitHub automation:

- use the manual `Release Dry Run` workflow to validate metadata, run CI, and upload build artifacts without publishing
- use the manual `Release TestPyPI` workflow for a trusted-publishing rehearsal against TestPyPI
- push a tag like `v0.1.1` to trigger the `Release` workflow and create a GitHub release
- configure PyPI trusted publishing for the repository's `pypi` GitHub environment
- configure TestPyPI trusted publishing for the repository's `testpypi` GitHub environment
- run the manual `Release` workflow and set `publish-to-pypi=true` with a matching `release-tag` to publish to PyPI without an API token

Trusted publisher values for this repository:

- PyPI/TestPyPI owner: `unicompute`
- PyPI/TestPyPI repository: `gemstone-py`
- PyPI workflow: `.github/workflows/release.yml`
- PyPI environment: `pypi`
- TestPyPI workflow: `.github/workflows/release-testpypi.yml`
- TestPyPI environment: `testpypi`

The failed TestPyPI claim that must match is:

- subject: `repo:unicompute/gemstone-py:environment:testpypi`
