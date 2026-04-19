"""
Stores Person objects in GemStone via PersistentRoot and queries them.

This example uses gsquery.GSCollection for indexed queries.

Run:
    python index_example.py
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import time

from examples.persistence.indexing.lib.person import Person
from gemstone_py.example_support import example_config, example_session
from gemstone_py.persistent_root import PersistentRoot
from gemstone_py.gsquery import GSCollection

POPULATION = 1_000


def bench(label, fn):
    t = time.perf_counter()
    r = fn()
    print(f'  {time.perf_counter()-t:.3f}s  {label}')
    return r


def main():
    config = example_config()
    with example_session() as s:
        root = PersistentRoot(s)

        print(f'\nCreating {POPULATION:,} people in GemStone...')
        col = GSCollection('IndexExamplePeople', config=config)

        def create():
            def records():
                for _ in range(POPULATION):
                    p = Person.random()
                    yield {
                        '@name':           p.name,
                        '@age':            p.age,
                        '@gender':         p.gender,
                        '@marital_status': p.marital_status,
                        '@zip':            p.address.zip_code,
                    }
            col.bulk_insert(records(), session=s)
        bench(f'Insert {POPULATION:,} people', create)

        col.add_index_for_class('@age', 'SmallInt', session=s)
        print(f'  Index on @age created')
        print(f'  Total in GemStone: {col.size(session=s):,}')

        print('\nQuerying...')

        youngsters = bench('Find youngsters (@age < 25)',
                           lambda: col.search('@age', 'lt', 25, session=s))
        print(f'  Found {len(youngsters):,} youngsters')

        old_ones = col.search('@age', 'gte', 75, session=s)
        hermits  = col.search('@marital_status', 'eql', 'hermit', session=s)
        old_hermits = GSCollection.intersect(old_ones, hermits)
        print(f'  Found {len(old_hermits):,} old hermits')
        for p in old_hermits[:3]:
            print(f'    {p}')

        col.remove_all_indexes(session=s)
        GSCollection.drop('IndexExamplePeople', session=s)


if __name__ == '__main__':
    main()
