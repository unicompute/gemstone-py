"""
GStore benchmark.

Compares GStore against a plain dict (in-memory baseline) across three
workloads:

    write     — N sequential writes (no reads)
    read      — N sequential reads after a pre-fill
    random_rw — N operations alternating read and write

Run:
    python3 examples/persistence/gstore/main.py

Output is a table of elapsed times and ops/sec for each workload and
backend.
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import time
import json
import random

from gemstone_py.example_support import example_config
from gemstone_py.gstore import GStore

# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------

N          = 200          # operations per workload
STORE_NAME = 'benchmark.db'
SEED       = 42

_rng = random.Random(SEED)


# -----------------------------------------------------------------------
# Baseline — plain Python dict (no I/O, just measures loop overhead)
# -----------------------------------------------------------------------

class DictStore:
    """Minimal PStore-compatible wrapper around a plain dict."""

    def __init__(self):
        self._data = {}

    class _Txn:
        def __init__(self, data): self._data = data
        def __getitem__(self, k): return self._data[k]
        def __setitem__(self, k, v): self._data[k] = v
        def get(self, k, d=None): return self._data.get(k, d)

    def transaction(self, read_only=False):
        from contextlib import contextmanager
        @contextmanager
        def _ctx():
            yield self._Txn(self._data)
        return _ctx()

    def rm(self): self._data.clear()


# -----------------------------------------------------------------------
# Workloads
# -----------------------------------------------------------------------

def _make_value(i: int) -> dict:
    return {'id': i, 'name': f'item-{i}', 'score': _rng.randint(0, 10_000)}


def run_write(store, n: int) -> float:
    start = time.perf_counter()
    for i in range(n):
        with store.transaction() as t:
            t[f'key:{i}'] = _make_value(i)
    return time.perf_counter() - start


def run_read(store, n: int) -> float:
    # Pre-fill
    for i in range(n):
        with store.transaction() as t:
            t[f'key:{i}'] = _make_value(i)
    start = time.perf_counter()
    for i in range(n):
        with store.transaction(read_only=True) as t:
            _ = t.get(f'key:{i}')
    return time.perf_counter() - start


def run_random_rw(store, n: int) -> float:
    # Pre-fill half the keys
    for i in range(n // 2):
        with store.transaction() as t:
            t[f'key:{i}'] = _make_value(i)
    start = time.perf_counter()
    for _ in range(n):
        i = _rng.randint(0, n - 1)
        if _rng.random() < 0.5:
            with store.transaction() as t:
                t[f'key:{i}'] = _make_value(i)
        else:
            with store.transaction(read_only=True) as t:
                _ = t.get(f'key:{i}')
    return time.perf_counter() - start


# -----------------------------------------------------------------------
# Runner
# -----------------------------------------------------------------------

def _fmt(elapsed: float, n: int) -> str:
    ops = n / elapsed if elapsed > 0 else float('inf')
    return f"{elapsed:7.3f}s  ({ops:8.1f} ops/s)"


def run_benchmark(label: str, store) -> None:
    print(f"\n{'─' * 56}")
    print(f"  {label}")
    print(f"{'─' * 56}")

    t = run_write(store, N)
    print(f"  write     {_fmt(t, N)}")

    t = run_read(store, N)
    print(f"  read      {_fmt(t, N)}")

    t = run_random_rw(store, N)
    print(f"  random_rw {_fmt(t, N)}")

    # Clean up after each backend so they start fresh
    try:
        store.rm(STORE_NAME) if callable(getattr(store, 'rm', None)) and \
            hasattr(store, '_filename') else None
    except Exception:
        pass


def main():
    config = example_config()
    print(f"GStore benchmark  (N={N} ops per workload)")
    print(f"{'═' * 56}")

    # ── In-memory dict baseline ─────────────────────────────────
    run_benchmark('DictStore (in-memory baseline)', DictStore())

    # ── GStore (GemStone-backed) ─────────────────────────────────
    try:
        gs = GStore(STORE_NAME, config=config)
        run_benchmark('GStore (GemStone-backed)', gs)
        GStore.rm(STORE_NAME, config=config)
    except Exception as e:
        print(f"\n  GStore unavailable: {e}")
        print("  (Start a GemStone stone and set $GEMSTONE to run this section)")

    print(f"\n{'═' * 56}")


if __name__ == '__main__':
    main()
