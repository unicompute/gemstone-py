"""
Structured migration: Point v1.0 (Cartesian) → v2.0 (Polar).

The pattern here is:
    1. find_old  — identify all v1 objects using list_instances / version check
    2. migrate   — convert each object in-place (rewrite its fields)
    3. commit    — durable after each chunk (crash-safe)

GemStone's GCI doesn't expose `become:` to external clients, so we:
    - rewrite the dictionary fields in-place (same OOP, new data)
    - update the 'version' field to mark the record as migrated
    - idempotent: skip records already at v2

Run order:
    python point_v1.py          # seed v1 data
    python migrate_v1_to_v2.py  # migrate to v2
    python point_v2.py          # verify mixed/fully-migrated store

"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import math
import gemstone_py as gemstone
from gemstone_py.example_support import MANUAL_POLICY, example_session
from gemstone_py.persistent_root import PersistentRoot

STORE_KEY  = 'Points'
FROM_VER   = '1.0.0'
TO_VER     = '2.0.0'
CHUNK_SIZE = 50


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------

def _cartesian_to_polar(x: float, y: float) -> tuple[float, float]:
    r     = math.sqrt(x * x + y * y)
    theta = math.atan2(y, x)
    return r, theta


# ---------------------------------------------------------------------------
# find_old
# ---------------------------------------------------------------------------

def find_old_keys(s) -> list[str]:
    """
    Return the IDs of all Points that have version == FROM_VER.

    Since our points are dictionaries (not typed Smalltalk objects), we
    can't use listInstances; instead we iterate the store and check the
    'version' field.
    """
    root = PersistentRoot(s)
    if STORE_KEY not in root:
        return []
    col  = root[STORE_KEY]
    old  = []
    for k in col.keys():
        rec = col[k]
        if rec.get('version', '') == FROM_VER:
            old.append(k)
    return old


# ---------------------------------------------------------------------------
# migrate — chunked, crash-safe
# ---------------------------------------------------------------------------

def _migrate_one(s, col, key: str) -> bool:
    """
    Convert one Point record from Cartesian to Polar in-place.

    Returns True if the record was migrated, False if already at v2.
    """
    rec = col[key]
    if rec.get('version', '') != FROM_VER:
        return False   # already migrated — idempotent

    x = float(rec.get('x', 0))
    y = float(rec.get('y', 0))
    r, theta = _cartesian_to_polar(x, y)

    # Rewrite the dictionary fields in-place on the same OOP.
    rec['r']       = str(r)
    rec['theta']   = str(theta)
    rec['version'] = TO_VER
    # Keep x/y for backward-compat readers; mark them as derived.
    return True


def migrate() -> None:
    """
    Migrate all v1 Points to v2, CHUNK_SIZE at a time.

    Commits after each chunk so a crash loses at most one chunk worth of
    work.
    """
    with example_session(transaction_policy=MANUAL_POLICY) as s:
        root = PersistentRoot(s)
        if STORE_KEY not in root:
            print("  No Points store found — run point_v1.py first")
            return

        col      = root[STORE_KEY]
        old_keys = find_old_keys(s)
        total    = len(old_keys)

        if not total:
            print("  No v1.0.0 points found — already migrated or store is empty")
            return

        print(f"  Found {total} v{FROM_VER} points to migrate → v{TO_VER}")

        migrated  = 0
        chunk_num = 0
        chunk     = []

        for key in old_keys:
            chunk.append(key)
            if len(chunk) >= CHUNK_SIZE:
                n = _process_chunk(s, col, chunk)
                migrated  += n
                chunk_num += 1
                print(f"  chunk {chunk_num}: migrated {migrated}/{total}")
                chunk = []

        if chunk:
            n = _process_chunk(s, col, chunk)
            migrated  += n
            chunk_num += 1
            print(f"  chunk {chunk_num}: migrated {migrated}/{total} (final)")

    print(f"\n  Done.  {migrated} points migrated in {chunk_num} chunk(s).")


def _process_chunk(s: gemstone.GemStoneSession, col, keys: list) -> int:
    """Migrate a batch of keys and commit."""
    n = 0
    for key in keys:
        try:
            if _migrate_one(s, col, key):
                n += 1
        except Exception as e:
            print(f"  WARNING: skipping {key!r}: {e}")
    s.commit()
    return n


if __name__ == '__main__':
    print(f"Migrating Points: v{FROM_VER} → v{TO_VER}")
    print("─" * 56)
    migrate()
