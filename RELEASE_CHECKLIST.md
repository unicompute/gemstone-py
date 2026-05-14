# Release Checklist

Use this before cutting a tagged release or publishing artifacts.

1. Install the dev toolchain:
```bash
python3 -m pip install -e .[dev]
```

Update `pyproject.toml` and add an entry to [CHANGELOG.md](https://github.com/unicompute/gemstone-py/blob/main/CHANGELOG.md)
before cutting a new version.
Use [docs/releases/next.md](https://github.com/unicompute/gemstone-py/blob/main/docs/releases/next.md)
as the draft release-note source for the next package release, then copy it to
a versioned `docs/releases/vX.Y.Z.md` file once the final version is chosen.

The GitHub `Release` workflow now validates that the release tag matches
`project.version` and that the same version is present in
[CHANGELOG.md](https://github.com/unicompute/gemstone-py/blob/main/CHANGELOG.md).

2. Run the local CI lane:
```bash
./scripts/run_ci_checks.sh
```

For a full local release verification wrapper, including native checks, public
PyPI/TestPyPI verification, VSIX packaging, Marketplace version verification,
and GitHub release asset checks:

```bash
./scripts/release_all.sh
make release
```

Use `./scripts/release_all.sh --skip-public-verify` for a local-only preflight
before the PyPI, Marketplace, and GitHub release assets exist.

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
[.github/benchmarks/index.json](https://github.com/unicompute/gemstone-py/blob/main/.github/benchmarks/index.json)
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
gemstone-examples value-converters
gemstone-smalltalk-demo
```

9. Use the manual `Release Dry Run` workflow for a GitHub-side rehearsal without publishing.

10. Use the manual `Release TestPyPI` workflow if you want a full publish rehearsal against TestPyPI. It now publishes to TestPyPI and then installs the published version back into a clean runner for post-publish API/CLI verification.

11. After a real PyPI publish, use the manual `Post Release Verify` workflow to confirm the published package installs from real PyPI, the API contract passes, the public CLI entry points work, and the PyPI metadata is clean.

12. Verify the public package indexes from your local shell:
```bash
gemstone-publish-verify --gemstone-version 0.2.10 --native-version 0.1.2
```

Use `--skip-install` for a faster metadata-only check. The verifier checks
PyPI and TestPyPI project JSON, version-specific JSON, the simple index, and
temporary-virtualenv installs. It also cache-busts JSON reads so stale
TestPyPI project metadata is less likely to hide a good release, and retries
each package/index pair while fresh publishes propagate.

13. Verify release checksums after downloading artifacts from GitHub.

For Python release assets, download `SHA256SUMS` beside the `dist/` artifacts
and run:

```bash
shasum -a 256 -c SHA256SUMS
```

For VS Code workbench assets, download the VSIX and its checksum file, then run:

```bash
shasum -a 256 -c gemstone-py-workbench-<version>.vsix.sha256
```

14. Run the optional live soak lane if you want higher confidence before a production release:
```bash
GS_RUN_LIVE=1 GS_RUN_LIVE_SOAK=1 ./scripts/run_live_checks.sh
```

15. Publish the VS Code workbench if extension docs, screenshots, or behavior changed:
```bash
gh workflow run vscode-extension.yml \
  --ref main \
  -f publish-to-marketplace=true \
  -f create-github-release=true
```

The workflow packages the VSIX, publishes it with `VSCE_PAT`, verifies the
Marketplace listing, and can create or update the scoped GitHub release
`vscode-workbench-v<version>`. The release upload includes the VSIX and a
matching `.vsix.sha256` checksum file.

16. Verify the Marketplace publisher domain.

The VS Code workflow checks that the publisher domain is
`https://unicompute.com`. After the Microsoft Marketplace portal reports the
domain as verified, run the workflow with `require-domain-verified=true`, or
check from a shell:

```bash
npx vsce show unicompute.gemstone-py-workbench --json
```

If `isDomainVerified` is still `false`, open the `unicompute` publisher in the
Marketplace management portal, start domain verification, publish the DNS record
Microsoft provides, and rerun the check.

17. Run the scheduled/manual `Full Release Verify` workflow after production
publishes. It runs `scripts/release_all.sh` without skips, including package
tests, native checks, PyPI/TestPyPI verification, VSIX packaging, Marketplace
version and domain checks, and GitHub release asset checks.

18. Run the manual `VS Code Workbench Live` workflow on the GemStone host when
you want the extension-host test to execute `gemstone-py: Verify Workbench
Setup` against the real stone and assert that `3 + 4` returns `7`.

19. Update external documentation surfaces:

- GitHub release notes for the package tag
- Visual Studio Marketplace release notes/screenshots when the VSIX changed
- Medium article Markdown/PDF when docs changed

20. Tag and publish only after the checks above are green.

For GitHub automation:

- use the manual `Release Dry Run` workflow to validate metadata, run CI, and upload build artifacts without publishing
- use the manual `Release TestPyPI` workflow for a trusted-publishing rehearsal against TestPyPI
- use the manual `Post Release Verify` workflow after production publish
- use the scheduled/manual `Full Release Verify` workflow after production publish to run the complete local/public wrapper without skips
- use `gemstone-publish-verify` after TestPyPI/PyPI publishes to check both indexes directly
- use the manual `VS Code Extension` workflow to publish the VSIX after updating screenshots, docs, or extension behavior
- use the manual `VS Code Workbench Live` workflow to test the extension setup verifier against the real GemStone host
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
- VSIX workflow: `.github/workflows/vscode-extension.yml`
- VSIX live workflow: `.github/workflows/vscode-workbench-live.yml`
- VSIX secret: `VSCE_PAT`
- VSIX Marketplace item: `unicompute.gemstone-py-workbench`

The failed TestPyPI claim that must match is:

- subject: `repo:unicompute/gemstone-py:environment:testpypi`
