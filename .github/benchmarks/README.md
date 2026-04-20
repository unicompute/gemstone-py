# Benchmark Baselines

The manual `Benchmarks` GitHub Actions workflow now selects an environment-
specific committed baseline through `.github/benchmarks/index.json`.

The repository currently includes:

- `.github/benchmarks/baseline.json`
- `.github/benchmarks/index.json`

The committed baseline report was generated on 2026-04-20 against `gs64stone`
with the workflow's default benchmark parameters (`entries=200`,
`search_runs=10`).

To maintain benchmark baselines:

1. Generate a report with `./scripts/run_benchmarks.sh --json --output benchmark-report.json`
2. Register the accepted report with `gemstone-benchmark-baseline-register benchmark-report.json`
3. Commit the copied report and the manifest update under `.github/benchmarks/`

To prune or replace manifest entries later:

- remove stale or missing baselines with `gemstone-benchmark-baseline-register --prune-missing`
- replace one accepted baseline with another by registering the new report and passing `--drop-path old-baseline.json`

Each workflow run then:

- uploads the fresh `benchmark-report.json`
- selects the committed baseline whose `stone`, platform, Python runtime, and benchmark parameters match the candidate report
- compares the candidate report to that selected baseline with `gemstone-benchmark-compare`
- uploads `baseline-selection.json`, `benchmark-compare.txt`, and `benchmark-compare.json`
- writes the selection and comparison summary into the workflow summary
- skips threshold enforcement when no committed baseline matches the candidate metadata
- fails the workflow when a comparable benchmark row regresses beyond the configured `max-regression-pct`

If one global threshold is too blunt, the workflow also accepts:

- `suite-thresholds` as a comma-separated list like `persistent_root=7.5,gstore=12`
- `operation-thresholds` as a comma-separated list like `persistent_root/mapping_keys=5`

Operation thresholds override suite thresholds, which override the global
`max-regression-pct`.

The committed workflow currently defaults `operation-thresholds` to
`persistent_root/mapping_keys=25,gstore/snapshot_read=25`, because
`mapping_keys` is sub-millisecond and `gstore/snapshot_read` has shown
meaningful host-to-host and run-to-run jitter on otherwise healthy runs.

Use the `baseline-report` workflow input only when you need to override the
manifest selection manually for a one-off comparison.
