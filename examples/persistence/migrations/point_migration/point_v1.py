"""
Point v1.0 — Cartesian (x, y) point.

Stores Point objects as StringKeyValueDictionaries in GemStone under
PersistentRoot['Points'].  Each point has a version string so migration
scripts can identify which schema version each object was written with.

Run this to seed the store with v1 Cartesian points:
    python point_v1.py
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import math
import uuid

from gemstone_py.example_support import example_session
from gemstone_py.persistent_root import PersistentRoot

VERSION    = '1.0.0'
STORE_KEY  = 'Points'


def setup(s) -> None:
    root = PersistentRoot(s)
    if STORE_KEY not in root:
        root[STORE_KEY] = {}
        print(f'  created {STORE_KEY!r} store (schema v{VERSION})')


def new_point(s, x: float, y: float) -> str:
    """Store a Cartesian point and return its ID."""
    pid = str(uuid.uuid4())
    root = PersistentRoot(s)
    col  = root[STORE_KEY]
    col[pid] = {
        'id':      pid,
        'version': VERSION,
        'x':       str(x),
        'y':       str(y),
    }
    return pid


def all_points(s) -> list[dict]:
    root = PersistentRoot(s)
    col  = root[STORE_KEY]
    out  = []
    for k in col.keys():
        rec = col[k]
        out.append({f: rec.get(f, '') for f in rec.keys()})
    return out


if __name__ == '__main__':
    with example_session() as s:
        setup(s)
        samples = [
            (3.0, 4.0),
            (1.0, 0.0),
            (0.0, 5.0),
            (-2.0, 3.0),
            (6.0, 8.0),
        ]
        for x, y in samples:
            pid = new_point(s, x, y)
            print(f'  v1 point ({x}, {y})  id={pid[:8]}…')
        print(f'  {len(samples)} v1.0 points written')
