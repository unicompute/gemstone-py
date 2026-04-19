"""
Port of persistence/indexing/create_random_people.rb

Creates a persistent IdentitySet of random Person objects in GemStone,
adds an equality index on @age, and commits.  Run this script once;
then run search_random_people.py (potentially from a different process
or machine) to query the same committed data.

This two-script pattern is the core demonstration of GemStone's
cross-session persistence: data written by one process is immediately
available to any other session after commit.

Usage:
    python3 create_random_people.py [population]
    python3 create_random_people.py 100000
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import sys
import time

from examples.persistence.indexing.lib.person import Person
from gemstone_py.example_support import example_config, example_session
from gemstone_py.gsquery import GSCollection

COLLECTION_NAME = 'RandomPeople'
POPULATION      = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000


def main():
    config = example_config()
    print(f"Creating {POPULATION:,} random people in GemStone…")
    print(f"  collection: {COLLECTION_NAME!r}")

    with example_session() as session:
        GSCollection.drop(COLLECTION_NAME, session=session)
        col = GSCollection(COLLECTION_NAME, config=config)

        t0 = time.perf_counter()

        def records():
            for i in range(POPULATION):
                p = Person.random()
                if (i + 1) % 1000 == 0:
                    print(f"  {i + 1:,} inserted…", end='\r', flush=True)
                yield {
                    '@name':           p.name,
                    '@age':            p.age,
                    '@gender':         p.gender,
                    '@marital_status': p.marital_status,
                    '@zip':            p.address.zip_code,
                }

        inserted = col.bulk_insert(records(), session=session)

        elapsed = time.perf_counter() - t0
        print(f"  {inserted:,} people inserted in {elapsed:.2f}s")

        # Add equality index on @age for fast range queries
        print("  Adding equality index on @age…")
        col.add_index_for_class('@age', 'SmallInt', session=session)
        print(f"  Index created.  Total in GemStone: {col.size(session=session):,}")

    print()
    print("Done.  Now run search_random_people.py to query the data.")
    print("The data is committed and visible to any other GemStone session.")


if __name__ == '__main__':
    main()
