"""
Persist and query a 2D KD-tree in GemStone.

Builds a 2D KD-tree of random points, serialises it into GemStone via
PersistentRoot, then reads it back and runs a nearest-neighbour query.

Here we serialise the tree as a JSON blob stored in a
StringKeyValueDictionary.

Usage
-----
    # Build and store (run once)
    python3 persist.py commit

    # Query the stored tree
    python3 persist.py query 10.5 23.7

    # Show stats
    python3 persist.py stats

    # Delete the stored tree
    python3 persist.py drop
"""

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import json
import sys

import gemstone_py as gemstone
from examples.persistence.kdtree.kdtree import Point2D, SearchResult, Tree2D
from gemstone_py.example_support import READ_POLICY, example_session
from gemstone_py.persistent_root import PersistentRoot

_KEY = 'KDTree2D'
_SIZE = 1000


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _tree_to_json(tree: Tree2D) -> str:
    """Serialise the tree to a JSON string (list of (x, y, data) triples)."""
    points = [{'x': p.x, 'y': p.y, 'data': str(p.data)} for p in tree]
    return json.dumps(points)


def _json_to_tree(raw: str) -> Tree2D:
    """Rebuild a Tree2D from its serialised JSON representation."""
    records = json.loads(raw)
    points  = [Point2D(r['x'], r['y'], r.get('data')) for r in records]
    return Tree2D(points)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_commit(size: int = _SIZE) -> None:
    """Build a random Tree2D and persist it in GemStone."""
    print(f"Building Tree2D with {size} random points…")
    tree = Tree2D.random(size)
    print(f"  depth={tree.max_depth()}  balanced={tree.balanced()}")

    serialised = _tree_to_json(tree)
    print(f"  serialised size = {len(serialised):,} bytes")

    with example_session() as s:
        root = PersistentRoot(s)
        root[_KEY] = {'points': serialised, 'size': str(size)}
    print(f"  stored at PersistentRoot[{_KEY!r}]")


def cmd_query(x: float, y: float, k: int = 5) -> None:
    """Load the stored tree from GemStone and run a nearest-neighbour query."""
    with example_session(transaction_policy=READ_POLICY) as s:
        s.abort()
        root = PersistentRoot(s)
        if _KEY not in root:
            print(f"No tree stored. Run: python3 persist.py commit")
            return
        record = root[_KEY]
        raw    = record['points']

    tree   = _json_to_tree(raw)
    target = Point2D(x, y, 'query')
    print(f"Querying tree for {k} nearest points to ({x}, {y})…")
    results = tree.nearest_k(target, k)
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r.value}  dist={r.distance:.4f}")


def cmd_stats() -> None:
    """Print stats about the stored tree."""
    with example_session(transaction_policy=READ_POLICY) as s:
        s.abort()
        root = PersistentRoot(s)
        if _KEY not in root:
            print(f"No tree stored. Run: python3 persist.py commit")
            return
        record = root[_KEY]
        raw    = record['points']
        size   = record.get('size', '?')

    tree = _json_to_tree(raw)
    pts  = list(tree)
    print(f"Tree2D in GemStone at PersistentRoot[{_KEY!r}]:")
    print(f"  stored size   = {size}")
    print(f"  point count   = {len(pts)}")
    print(f"  tree depth    = {tree.max_depth()}")
    print(f"  balanced      = {tree.balanced()}")
    if pts:
        xs = [p.x for p in pts]
        ys = [p.y for p in pts]
        print(f"  x range       = [{min(xs):.3f}, {max(xs):.3f}]")
        print(f"  y range       = [{min(ys):.3f}, {max(ys):.3f}]")


def cmd_drop() -> None:
    """Delete the stored tree from GemStone."""
    with example_session() as s:
        root = PersistentRoot(s)
        if _KEY in root:
            ug  = object.__getattribute__(root, '_ug')
            sym = s.new_symbol(_KEY)
            s.perform_oop(ug, 'removeKey:ifAbsent:', sym, gemstone.OOP_NIL)
    print(f"Dropped PersistentRoot[{_KEY!r}]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'stats'

    if cmd == 'commit':
        size = int(sys.argv[2]) if len(sys.argv) > 2 else _SIZE
        cmd_commit(size)

    elif cmd == 'query':
        if len(sys.argv) < 4:
            print("Usage: python3 persist.py query <x> <y> [k]")
            sys.exit(1)
        x = float(sys.argv[2])
        y = float(sys.argv[3])
        k = int(sys.argv[4]) if len(sys.argv) > 4 else 5
        cmd_query(x, y, k)

    elif cmd == 'stats':
        cmd_stats()

    elif cmd == 'drop':
        cmd_drop()

    else:
        print(f"Unknown command {cmd!r}. Use: commit | query | stats | drop")
        sys.exit(1)
