"""
Migration: blog v1.0 → v2.0 — backfill the 'date' field.

Migration pattern:
  1. Load the new class definition
  2. Iterate over all existing instances
  3. Set missing fields to a sentinel / default value
  4. Commit

Here Python has no persistent class objects, so we work directly on the
stored StringKeyValueDictionaries.  We iterate every record in the store and
add 'date' = '0.0' (epoch) to records that are missing it.

Run:
    python3 migrate.py

The migration is idempotent: records that already have 'date' are skipped.
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

from gemstone_py.example_support import example_session
from gemstone_py.persistent_root import PersistentRoot

STORE_KEY     = 'BlogPosts'
UNKNOWN_DATE  = '0.0'          # epoch sentinel for missing dates


def migrate(s) -> int:
    """
    Backfill 'date' on records that don't have it.
    Returns the number of records updated.
    """
    root    = PersistentRoot(s)
    col     = root[STORE_KEY]
    updated = 0

    for post_id in col.keys():
        rec = col[post_id]
        if 'date' not in rec:
            rec['date'] = UNKNOWN_DATE
            updated += 1

    return updated


if __name__ == '__main__':
    print('Migration: blog v1.0 → v2.0 (add date field)')
    with example_session() as s:
        n = migrate(s)
        print(f'  updated {n} record(s)')
        print('  committed.')
