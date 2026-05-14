# Performance

`gemstone-py` keeps performance claims tied to benchmark artifacts. The
repository ships a maintained benchmark CLI, committed baselines, and a
comparison workflow so performance regressions can be reviewed as data instead
of anecdotes.

## Current Committed Baseline

The current public baseline is
[`.github/benchmarks/baseline.json`](../.github/benchmarks/baseline.json). It
was generated on 2026-04-20 with:

| Field | Value |
| --- | --- |
| Platform | `macOS-26.3.1-arm64-arm-64bit-Mach-O` |
| Python | `CPython 3.14.3` |
| Stone | `gs64stone` on `localhost` |
| Entries | `200` |
| Search runs | `10` |
| Suites | `persistent_root`, `gscollection`, `gstore`, `rchash` |

These numbers are a small smoke-sized profile, not a universal capacity claim.
They are useful as a reference point and as a regression baseline for the
configured self-hosted GemStone runner.

| Suite | Operation | Count | Elapsed | Approx. per operation | Ops/s | Note |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `persistent_root` | `write_mapping_commit` | 200 | 0.1099s | 0.550ms | 1,819 | Writes a Python mapping and commits. |
| `persistent_root` | `mapping_keys` | 200 | 0.0006s | 0.003ms | 337,316 | Reads committed mapping keys. |
| `gscollection` | `bulk_insert_and_index_commit` | 200 | 0.0980s | 0.490ms | 2,040 | Bulk inserts records and creates an index. |
| `gscollection` | `indexed_search` | 10 | 0.0126s | 1.263ms | 792 | `matched=540`. |
| `gstore` | `batch_write` | 200 | 0.0929s | 0.464ms | 2,153 | Transactional key/value write. |
| `gstore` | `snapshot_read` | 200 | 0.0689s | 0.344ms | 2,903 | Transactional key/value read. |
| `rchash` | `populate_commit` | 200 | 0.0159s | 0.079ms | 12,581 | Populates an `RCHash` and commits. |
| `rchash` | `items` | 200 | 0.0013s | 0.006ms | 154,644 | Reads committed hash items. |

## Run The Benchmarks

Run the default live benchmark suite against your configured stone:

```bash
./scripts/run_benchmarks.sh
gemstone-benchmarks --entries 500 --search-runs 20
```

Capture a JSON artifact:

```bash
./scripts/run_benchmarks.sh --json --output benchmark-report.json
```

The `gscollection` suite records both the legacy materialized path and the
streaming path:

- `indexed_search` and `indexed_search_iter` compare list-returning indexed
  search with chunked indexed iteration.
- `all_materialize` records `collection.all()` latency and peak Python
  allocation.
- `iter_stream_count` records the same full-collection pass while streaming
  through `collection.iter()`.

Use a larger entry count, such as `--entries 50000`, when you want to compare
large-result memory behavior rather than smoke-test latency.

## Round-Trip Reduction APIs

The lightweight performance direction is to reduce avoidable GCI round trips
without adding a client-side identity map. The main helpers are:

- `PersistentRoot.get_many(...)` and `PersistentRoot.update_many(...)` for
  top-level `UserGlobals` batches.
- `GsDict.get_many(...)` and `GsDict.update_many(...)` for nested
  `StringKeyValueDictionary` batches.
- `GemStoneSession.bulk_perform_value(...)` and `bulk_perform_oop(...)` for one
  selector across many receivers.
- `GemStoneSession.bulk_perform_calls_value(...)` and
  `bulk_perform_calls_oop(...)` for mixed receiver/selector calls.
- `perform_many_value(...)`, `perform_many_oop(...)`, `perform_calls_value(...)`,
  and `perform_calls_oop(...)` as readability aliases.

Use these when the unit of work is already a batch. They are not a substitute
for good repository-side indexing or a reason to pull large object graphs into
Python.

Compare two saved reports:

```bash
gemstone-benchmark-compare baseline.json candidate.json
gemstone-benchmark-compare baseline.json candidate.json --json --output benchmark-compare.json
```

Select the committed baseline that matches the generated report metadata:

```bash
python -m gemstone_py.benchmark_baselines benchmark-report.json \
  --manifest .github/benchmarks/index.json
```

Register a new accepted baseline:

```bash
gemstone-benchmark-baseline-register benchmark-report.json
```

## Native Backend Microbenchmark

The `gci` suite compares low-level helper-call overhead for the pure `ctypes`
backend and the optional PyO3 native backend. It does not require a live stone:

```bash
gemstone-benchmarks --suite gci --entries 1000000
```

To compare real GemStone workloads through each backend, run the same live
benchmark twice with an explicit backend and compare the artifacts:

```bash
GEMSTONE_PY_GCI_BACKEND=ctypes gemstone-benchmarks --json --output ctypes-report.json
GEMSTONE_PY_GCI_BACKEND=native gemstone-benchmarks --json --output native-report.json
gemstone-benchmark-compare ctypes-report.json native-report.json
```

## CI Policy

The manual `Benchmarks` workflow runs on the GemStone-capable self-hosted
runner, uploads the fresh benchmark report, selects the best committed baseline,
and enforces configured regression thresholds with
`gemstone-benchmark-compare`.

The committed thresholds are deliberately per-operation rather than one global
number. Write-heavy operations and indexed search have different run-to-run
jitter, so a single global threshold either hides meaningful regressions or
fails on normal noise.

When updating these numbers, commit both the new baseline report and the
manifest update under `.github/benchmarks/`.
