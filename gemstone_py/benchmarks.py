"""Maintained benchmark lane for gemstone-py persistence helpers."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence, TypeVar, cast

from gemstone_py import (
    GemStoneConfig,
    GemStoneConfigurationError,
    GemStoneSession,
    TransactionPolicy,
)
from gemstone_py.concurrency import RCHash
from gemstone_py.gsquery import GSCollection
from gemstone_py.gstore import GStore
from gemstone_py.persistent_root import PersistentRoot

DEFAULT_ENTRIES = 200
DEFAULT_SEARCH_RUNS = 10
DEFAULT_SUITES = ("persistent_root", "gscollection", "gstore", "rchash")
BENCHMARK_REPORT_SCHEMA_VERSION = 1


class SupportsKeys(Protocol):
    """Protocol for GemStone-backed mappings that can list string keys."""

    def keys(self) -> list[str]:
        ...


T = TypeVar("T")


@dataclass(frozen=True)
class BenchmarkResult:
    """One measured benchmark operation."""

    suite: str
    operation: str
    count: int
    elapsed_seconds: float
    ops_per_second: float
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable view of the result."""
        return asdict(self)

    def with_note(self, note: str | None) -> "BenchmarkResult":
        """Return a copy of the result with updated note text."""
        return replace(self, note=note)


@dataclass(frozen=True)
class BenchmarkReport:
    """Serializable benchmark report with run metadata."""

    schema_version: int
    generated_at: str
    python_version: str
    python_implementation: str
    platform: str
    stone: str
    host: str
    entries: int
    search_runs: int
    suites: list[str]
    results: list[BenchmarkResult]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable report payload."""
        payload = asdict(self)
        payload["results"] = [result.as_dict() for result in self.results]
        return payload


def _benchmark_config() -> GemStoneConfig:
    try:
        return GemStoneConfig.from_env()
    except GemStoneConfigurationError as exc:
        raise SystemExit(
            f"{exc}\n"
            "Set GS_USERNAME and GS_PASSWORD before running gemstone-benchmarks."
        ) from exc


def _measure(
    suite: str,
    operation: str,
    count: int,
    fn: Callable[[], T],
) -> tuple[BenchmarkResult, T]:
    started_at = time.perf_counter()
    value = fn()
    elapsed = max(time.perf_counter() - started_at, 1e-12)
    ops_per_second = float(count) / elapsed if count > 0 else 0.0
    return (
        BenchmarkResult(
            suite=suite,
            operation=operation,
            count=count,
            elapsed_seconds=elapsed,
            ops_per_second=ops_per_second,
        ),
        value,
    )


def _payloads(entries: int) -> dict[str, dict[str, Any]]:
    return {
        f"item:{index}": {
            "id": index,
            "name": f"item-{index}",
            "active": index % 2 == 0,
            "score": index % 97,
        }
        for index in range(entries)
    }


def _collection_records(entries: int) -> list[dict[str, object]]:
    return [
        {
            "@name": f"person-{index}",
            "@age": index % 100,
            "@city": f"city-{index % 25}",
            "@score": index % 500,
        }
        for index in range(entries)
    ]


def _cleanup_root_key(session: GemStoneSession, root: PersistentRoot, key: str) -> None:
    session.abort()
    if key in root:
        del root[key]
        session.commit()


def benchmark_persistent_root(
    config: GemStoneConfig,
    *,
    entries: int,
) -> list[BenchmarkResult]:
    bucket_key = f"BenchmarkPersistentRoot_{uuid.uuid4().hex}"
    payload = _payloads(entries)
    results: list[BenchmarkResult] = []

    with GemStoneSession(config=config, transaction_policy=TransactionPolicy.MANUAL) as session:
        root = PersistentRoot(session)
        try:
            result, _ = _measure(
                "persistent_root",
                "write_mapping_commit",
                entries,
                lambda: _persistent_root_write(session, root, bucket_key, payload),
            )
            results.append(result)

            session.abort()
            bucket = cast(SupportsKeys, root[bucket_key])
            result, keys = _measure(
                "persistent_root",
                "mapping_keys",
                entries,
                bucket.keys,
            )
            if len(keys) != entries:
                raise RuntimeError(
                    f"PersistentRoot benchmark expected {entries} keys, got {len(keys)}"
                )
            results.append(result)
        finally:
            _cleanup_root_key(session, root, bucket_key)

    return results


def _persistent_root_write(
    session: GemStoneSession,
    root: PersistentRoot,
    bucket_key: str,
    payload: dict[str, dict[str, Any]],
) -> None:
    root[bucket_key] = payload
    session.commit()


def benchmark_gscollection(
    config: GemStoneConfig,
    *,
    entries: int,
    search_runs: int,
) -> list[BenchmarkResult]:
    collection_name = f"BenchmarkGSCollection_{uuid.uuid4().hex}"
    collection = GSCollection(collection_name, config=config)
    records = _collection_records(entries)
    search_thresholds = [25 + (index % 5) for index in range(search_runs)]
    results: list[BenchmarkResult] = []

    with GemStoneSession(config=config, transaction_policy=TransactionPolicy.MANUAL) as session:
        try:
            result, inserted = _measure(
                "gscollection",
                "bulk_insert_and_index_commit",
                entries,
                lambda: _gscollection_insert_and_index(session, collection, records),
            )
            if inserted != entries:
                raise RuntimeError(
                    f"GSCollection benchmark inserted {inserted} rows, expected {entries}"
                )
            results.append(result)

            session.abort()
            result, matched = _measure(
                "gscollection",
                "indexed_search",
                search_runs,
                lambda: _gscollection_search(session, collection, search_thresholds),
            )
            results.append(result.with_note(f"matched={matched}"))
        finally:
            session.abort()
            GSCollection.drop(collection_name, session=session)
            session.commit()

    return results


def _gscollection_insert_and_index(
    session: GemStoneSession,
    collection: GSCollection,
    records: list[dict[str, object]],
) -> int:
    inserted = collection.bulk_insert(records, session=session)
    collection.add_index_for_class("@age", "SmallInt", session=session)
    session.commit()
    return inserted


def _gscollection_search(
    session: GemStoneSession,
    collection: GSCollection,
    thresholds: list[int],
) -> int:
    total = 0
    for threshold in thresholds:
        total += len(collection.search("@age", "lt", threshold, session=session))
    return total


def benchmark_gstore(
    config: GemStoneConfig,
    *,
    entries: int,
) -> list[BenchmarkResult]:
    filename = f"benchmark-{uuid.uuid4().hex}.db"
    store = GStore(filename, config=config)
    payload = _payloads(entries)
    results: list[BenchmarkResult] = []

    try:
        result, _ = _measure(
            "gstore",
            "batch_write",
            entries,
            lambda: _gstore_write(store, payload),
        )
        results.append(result)

        result, reads = _measure(
            "gstore",
            "snapshot_read",
            entries,
            lambda: _gstore_read(store, payload),
        )
        if reads != entries:
            raise RuntimeError(f"GStore benchmark read {reads} rows, expected {entries}")
        results.append(result)
    finally:
        GStore.rm(filename, config=config)

    return results


def _gstore_write(store: GStore, payload: dict[str, dict[str, Any]]) -> None:
    with store.transaction() as txn:
        for key, value in payload.items():
            txn[key] = value


def _gstore_read(store: GStore, payload: dict[str, dict[str, Any]]) -> int:
    reads = 0
    with store.transaction(read_only=True) as txn:
        for key in payload:
            if txn.get(key) is not None:
                reads += 1
    return reads


def benchmark_rchash(
    config: GemStoneConfig,
    *,
    entries: int,
) -> list[BenchmarkResult]:
    root_key = f"BenchmarkRCHash_{uuid.uuid4().hex}"
    results: list[BenchmarkResult] = []

    with GemStoneSession(config=config, transaction_policy=TransactionPolicy.MANUAL) as session:
        root = PersistentRoot(session)
        rc_hash = RCHash(session)
        root[root_key] = rc_hash
        session.commit()
        try:
            result, _ = _measure(
                "rchash",
                "populate_commit",
                entries,
                lambda: _rchash_populate(session, rc_hash, entries),
            )
            results.append(result)

            session.abort()
            committed_hash = cast(RCHash, root[root_key])
            result, items = _measure(
                "rchash",
                "items",
                entries,
                committed_hash.items,
            )
            if len(items) != entries:
                raise RuntimeError(
                    f"RCHash benchmark fetched {len(items)} rows, expected {entries}"
                )
            results.append(result)
        finally:
            _cleanup_root_key(session, root, root_key)

    return results


def _rchash_populate(session: GemStoneSession, rc_hash: RCHash, entries: int) -> None:
    for index in range(entries):
        rc_hash[f"key:{index}"] = index
    session.commit()


SUITE_RUNNERS: dict[str, Callable[..., list[BenchmarkResult]]] = {
    "persistent_root": benchmark_persistent_root,
    "gscollection": benchmark_gscollection,
    "gstore": benchmark_gstore,
    "rchash": benchmark_rchash,
}


def run_benchmark_suite(
    *,
    config: GemStoneConfig,
    suites: Sequence[str] = DEFAULT_SUITES,
    entries: int = DEFAULT_ENTRIES,
    search_runs: int = DEFAULT_SEARCH_RUNS,
) -> list[BenchmarkResult]:
    """Run the requested benchmark suites and return the measured results."""
    results: list[BenchmarkResult] = []
    for suite in suites:
        runner = SUITE_RUNNERS[suite]
        if suite == "gscollection":
            results.extend(runner(config, entries=entries, search_runs=search_runs))
        else:
            results.extend(runner(config, entries=entries))
    return results


def build_report(
    *,
    config: GemStoneConfig,
    suites: Sequence[str],
    entries: int,
    search_runs: int,
    results: Sequence[BenchmarkResult],
) -> BenchmarkReport:
    """Build a benchmark report with local runtime metadata."""
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return BenchmarkReport(
        schema_version=BENCHMARK_REPORT_SCHEMA_VERSION,
        generated_at=generated_at,
        python_version=sys.version.split()[0],
        python_implementation=platform.python_implementation(),
        platform=platform.platform(),
        stone=config.stone,
        host=config.host,
        entries=entries,
        search_runs=search_runs,
        suites=list(suites),
        results=list(results),
    )


def format_results(results: Sequence[BenchmarkResult]) -> str:
    """Render benchmark results as a simple aligned table."""
    if not results:
        return "No benchmark results."

    suite_width = max(len("Suite"), *(len(result.suite) for result in results))
    operation_width = max(len("Operation"), *(len(result.operation) for result in results))
    count_width = max(len("Count"), *(len(str(result.count)) for result in results))
    elapsed_width = max(
        len("Elapsed"),
        *(len(f"{result.elapsed_seconds:.4f}s") for result in results),
    )
    ops_width = max(
        len("Ops/s"),
        *(len(f"{result.ops_per_second:.1f}") for result in results),
    )
    note_width = max(len("Note"), *(len(result.note or "") for result in results))

    lines = [
        (
            f"{'Suite':<{suite_width}}  "
            f"{'Operation':<{operation_width}}  "
            f"{'Count':>{count_width}}  "
            f"{'Elapsed':>{elapsed_width}}  "
            f"{'Ops/s':>{ops_width}}  "
            f"{'Note':<{note_width}}"
        ),
        (
            f"{'-' * suite_width}  "
            f"{'-' * operation_width}  "
            f"{'-' * count_width}  "
            f"{'-' * elapsed_width}  "
            f"{'-' * ops_width}  "
            f"{'-' * note_width}"
        ),
    ]
    for result in results:
        lines.append(
            f"{result.suite:<{suite_width}}  "
            f"{result.operation:<{operation_width}}  "
            f"{result.count:>{count_width}}  "
            f"{result.elapsed_seconds:>{elapsed_width}.4f}s  "
            f"{result.ops_per_second:>{ops_width}.1f}  "
            f"{(result.note or ''):<{note_width}}"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build the benchmark CLI parser."""
    parser = argparse.ArgumentParser(
        prog="gemstone-benchmarks",
        description=(
            "Run maintained gemstone-py benchmark suites against a configured "
            "GemStone stone."
        ),
    )
    parser.add_argument(
        "--suite",
        action="append",
        choices=sorted(SUITE_RUNNERS),
        dest="suites",
        help="Benchmark suite to run. Pass multiple times to select a subset.",
    )
    parser.add_argument(
        "--entries",
        type=int,
        default=DEFAULT_ENTRIES,
        help="Entry count used for PersistentRoot, GSCollection, GStore, and RCHash workloads.",
    )
    parser.add_argument(
        "--search-runs",
        type=int,
        default=DEFAULT_SEARCH_RUNS,
        help="Indexed search repetitions for the GSCollection benchmark.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a formatted table.",
    )
    parser.add_argument(
        "--output",
        help="Write the rendered output to this file instead of stdout.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the benchmark CLI."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.entries < 1:
        raise SystemExit("--entries must be at least 1")
    if args.search_runs < 1:
        raise SystemExit("--search-runs must be at least 1")

    config = _benchmark_config()
    suites = tuple(args.suites or DEFAULT_SUITES)
    results = run_benchmark_suite(
        config=config,
        suites=suites,
        entries=args.entries,
        search_runs=args.search_runs,
    )
    report = build_report(
        config=config,
        suites=suites,
        entries=args.entries,
        search_runs=args.search_runs,
        results=results,
    )
    if args.json:
        output = json.dumps(report.as_dict(), indent=2)
    else:
        output = format_results(report.results)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


def main_entry() -> None:
    """Console-script wrapper for gemstone-benchmarks."""
    raise SystemExit(main())


if __name__ == "__main__":
    main_entry()
