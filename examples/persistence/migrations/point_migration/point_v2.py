"""
Point v2.0 — Polar (r, theta) point.

v2 points store polar coordinates (r, theta) instead of Cartesian (x, y).
The migration script (migrate_v1_to_v2.py) converts v1 Cartesian points
to v2 polar points in-place by rewriting the GemStone dictionary fields.

The version field allows the reader to handle both schemas gracefully,
using the stored schema version to guard migration code.
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import math
import uuid

from gemstone_py.example_support import READ_POLICY, example_session
from gemstone_py.persistent_root import PersistentRoot

VERSION   = '2.0.0'
STORE_KEY = 'Points'


def new_point(s, r: float, theta: float) -> str:
    """Store a polar point and return its ID."""
    pid = str(uuid.uuid4())
    root = PersistentRoot(s)
    col  = root[STORE_KEY]
    col[pid] = {
        'id':      pid,
        'version': VERSION,
        'r':       str(r),
        'theta':   str(theta),
    }
    return pid


def read_point(rec: dict) -> dict:
    """
    Read a point record regardless of schema version.

    v1 records have 'x' and 'y'; v2 records have 'r' and 'theta'.
    Returns a normalised dict with both representations filled in.
    Newer code can read older objects by checking VERSION.
    """
    version = rec.get('version', '1.0.0')
    if version.startswith('1.'):
        x = float(rec.get('x', 0))
        y = float(rec.get('y', 0))
        r     = math.sqrt(x * x + y * y)
        theta = math.atan2(y, x)
        return {'version': version, 'x': x, 'y': y, 'r': r, 'theta': theta}
    else:
        r     = float(rec.get('r', 0))
        theta = float(rec.get('theta', 0))
        x = r * math.cos(theta)
        y = r * math.sin(theta)
        return {'version': version, 'r': r, 'theta': theta, 'x': x, 'y': y}


def all_points(s) -> list[dict]:
    root = PersistentRoot(s)
    col  = root[STORE_KEY]
    out  = []
    for k in col.keys():
        raw = col[k]
        rec = {f: raw.get(f, '') for f in raw.keys()}
        out.append(read_point(rec))
    return out


if __name__ == '__main__':
    with example_session(transaction_policy=READ_POLICY) as s:
        root = PersistentRoot(s)
        if STORE_KEY not in root:
            print("  No Points store found — run point_v1.py first")
            sys.exit(1)
        points = all_points(s)
        print(f"  {len(points)} points in store (mixed v1/v2):")
        for p in points:
            print(f"    v{p['version']}  r={p['r']:.3f}  theta={p['theta']:.3f}"
                  f"  x={p['x']:.3f}  y={p['y']:.3f}")
