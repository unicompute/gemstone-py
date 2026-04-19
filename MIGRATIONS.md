# GemStone Migration Patterns

GemStone stores live Python objects (serialised as JSON Dictionaries in
UserGlobals or GStore).  When the shape of those objects changes — new
fields, renamed fields, restructured collections — you need to migrate
the persisted data.

This document describes the common migration patterns used in
`gemstone-py`.

---

## Pattern 1 — Simple field migration (in-place update)

**When to use:** Adding a new field with a default, renaming a field, or
changing a field's type.  Data volume is small enough to process in one
transaction.

**Example:**

```python
import json

import gemstone_py as gemstone

config = gemstone.GemStoneConfig.from_env()

def migrate_add_published_at():
    """
    Add a 'published_at' field (default None) to every post in GStore.
    Run once after deploying code that expects the new field.
    """
    with gemstone.GemStoneSession(
        config=config,
        transaction_policy=gemstone.TransactionPolicy.COMMIT_ON_SUCCESS,
    ) as s:
        # 1. Fetch all keys
        keys_raw = s.eval(
            "| ids | ids := ''."
            "((UserGlobals at: #GStoreRoot) at: 'posts') keysDo: [:k | ids := ids, k, '|']."
            "ids"
        )
        keys = [k for k in keys_raw.rstrip('|').split('|') if k]

        # 2. For each record, add the missing field
        for key in keys:
            raw = s.eval(
                f"((UserGlobals at: #GStoreRoot) at: 'posts') at: '{key}'"
            )
            record = json.loads(raw)
            if 'published_at' not in record:
                record['published_at'] = None
                serialised = json.dumps(record).replace("'", "''")
                s.eval(
                    f"((UserGlobals at: #GStoreRoot) at: 'posts')"
                    f" at: '{key}' put: '{serialised}'."
                )
if __name__ == '__main__':
    migrate_add_published_at()
    print("Migration complete.")
```

---

## Pattern 2 — Chunked migration (large collections)

**When to use:** Migrating tens of thousands of records.  Processing
everything in a single transaction holds a write lock for too long and
risks OOM on the Gem.

**Example:**

```python
import json

import gemstone_py as gemstone

config = gemstone.GemStoneConfig.from_env()
CHUNK = 500   # records per transaction

def migrate_rename_field(store_name: str, old_field: str, new_field: str):
    """
    Rename `old_field` to `new_field` across all records in a GStore,
    committing every CHUNK records to bound transaction size.
    """
    # --- Phase 1: collect all keys (read-only) ---
    with gemstone.GemStoneSession(config=config) as s:
        keys_raw = s.eval(
            f"| ids | ids := ''."
            f"((UserGlobals at: #GStoreRoot) at: '{store_name}')"
            f"  keysDo: [:k | ids := ids, k, '|']."
            f"ids"
        )
    keys = [k for k in keys_raw.rstrip('|').split('|') if k]
    total = len(keys)
    done  = 0

    # --- Phase 2: process in chunks ---
    while done < total:
        chunk = keys[done : done + CHUNK]
        with gemstone.GemStoneSession(
            config=config,
            transaction_policy=gemstone.TransactionPolicy.COMMIT_ON_SUCCESS,
        ) as s:
            for key in chunk:
                raw = s.eval(
                    f"((UserGlobals at: #GStoreRoot) at: '{store_name}')"
                    f" at: '{key}'"
                )
                record = json.loads(raw)
                if old_field in record:
                    record[new_field] = record.pop(old_field)
                    serialised = json.dumps(record).replace("'", "''")
                    s.eval(
                        f"((UserGlobals at: #GStoreRoot) at: '{store_name}')"
                        f" at: '{key}' put: '{serialised}'."
                    )
        done += len(chunk)
        print(f"  {done}/{total} records migrated")

    print("Migration complete.")

if __name__ == '__main__':
    migrate_rename_field('posts', 'body', 'content')
```

---

## Pattern 3 — Version-tracked migrations

For applications with multiple migrations that must be applied in order,
track which migrations have run in a dedicated GStore entry.

```python
# migrations/runner.py
from gemstone_py.gstore import GStore

MIGRATIONS = []   # populated by @migration decorator below

def migration(name: str):
    """Decorator to register a migration function."""
    def decorator(fn):
        MIGRATIONS.append((name, fn))
        return fn
    return decorator


def run_pending():
    db = GStore('_migrations')
    with db.transaction() as t:
        applied = set(t.get('applied', []))

    for name, fn in MIGRATIONS:
        if name not in applied:
            print(f"Running migration: {name}")
            fn()
            with db.transaction() as t:
                lst = t.get('applied', [])
                lst.append(name)
                t['applied'] = lst
            print(f"  done.")


# --- example migrations ---

@migration('001_add_published_at')
def add_published_at():
    # ... see Pattern 1 above ...
    pass

@migration('002_rename_body_to_content')
def rename_body():
    # ... see Pattern 2 above ...
    pass


if __name__ == '__main__':
    run_pending()
```

Run as a one-off script before starting the application:
```
python migrations/runner.py
```

---

## What NOT to do

- **Don't use `become:`** — it swaps the identity of two live Smalltalk
  objects in the repository heap. Our Python objects
  are stored as JSON Dictionaries, so there is no OOP identity to swap.
  Just update the JSON in place.

- **Don't schema-migrate GemStone itself** — GemStone has its own class
  history and schema migration tools (GsUpgrader).  Those are for upgrading
  the repository format across GemStone versions, not for application data.

- **Don't hold a transaction across user-visible delays** — GemStone
  write locks are held for the duration of a Gem's transaction.  Batch
  large migrations into chunks (Pattern 2) and commit frequently.

---

## Checklist for a new migration

1. Write the migration as a standalone Python script.
2. Test against a dev/staging repository first.
3. Take a GemStone backup (`gsbackup`) before running against production.
4. Run the script while the application is stopped or in read-only mode.
5. Register the migration in `runner.py` so it is tracked and not re-run.
