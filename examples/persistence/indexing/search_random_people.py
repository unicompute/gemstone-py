"""
Port of persistence/indexing/search_random_people.rb

Reads the RandomPeople collection committed by create_random_people.py
and benchmarks indexed search vs full table scan.

Run create_random_people.py first.  This script can run from a completely
separate process — even a separate machine with access to the same stone —
demonstrating GemStone's cross-session persistence.

Usage:
    python3 search_random_people.py
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import sys
import time

from gemstone_py.example_support import READ_POLICY, example_config, example_session
from gemstone_py.gsquery import GSCollection

COLLECTION_NAME = 'RandomPeople'


def bench(label: str, fn) -> object:
    t = time.perf_counter()
    result = fn()
    elapsed = time.perf_counter() - t
    print(f"  {elapsed:.3f}s  {label}")
    return result


def main():
    config = example_config()
    col = GSCollection(COLLECTION_NAME, config=config)
    with example_session(transaction_policy=READ_POLICY) as session:
        total = col.size(session=session)
        if total == 0:
            print(f"No data found in {COLLECTION_NAME!r}.")
            print("Run create_random_people.py first.")
            sys.exit(1)

        print(f"Searching {total:,} people in GemStone ({COLLECTION_NAME!r})…")
        print()

        # --- Indexed search (uses equality index on @age) ---
        youngsters_indexed = bench(
            "Find youngsters (@age < 25)  [indexed search:comparing:with:]",
            lambda: col.search('@age', 'lt', 25, session=session),
        )
        print(f"  Found {len(youngsters_indexed):,} youngsters\n")

        # --- Full table scan (no index on @marital_status) ---
        hermits = bench(
            "Find hermits (@marital_status = hermit)  [full select: scan]",
            lambda: col.search('@marital_status', 'eql', 'hermit', session=session),
        )
        print(f"  Found {len(hermits):,} hermits\n")

        # --- Intersection (Python-side, both result sets already fetched) ---
        young_hermits = bench(
            "Intersect youngsters ∩ hermits           [Python-side]",
            lambda: GSCollection.intersect(youngsters_indexed, hermits),
        )
        print(f"  Found {len(young_hermits):,} young hermits\n")

        # --- Multi-level indexed search on zip ---
        # Only available if the @zip index was created; fall back gracefully.
        lucrative = bench(
            "Find people in zip 45678 (@zip = 45678)  [indexed if available]",
            lambda: col.search('@zip', 'eql', 45678, session=session),
        )
        print(f"  Found {len(lucrative):,} people in zip 45678\n")

        lucrative_youngsters = GSCollection.intersect(youngsters_indexed, lucrative)
        print(f"  Young people in 45678: {len(lucrative_youngsters):,}")

        if young_hermits:
            print()
            print("Sample young hermits:")
            for p in young_hermits[:5]:
                print(f"  {p}")


if __name__ == '__main__':
    main()
