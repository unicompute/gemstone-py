"""
k-d tree — pure Python implementation.

A KD-tree is a binary space-partitioning tree for K-dimensional Euclidean
points.  It supports:
  - Bulk construction from a list of points (balanced on build)
  - Nearest-neighbour search (nearest)
  - K-nearest-neighbour search (nearest_k)
  - In-order iteration (each, __iter__)
  - Insertion of new points (insert_point)
  - Removal of the root node (remove)

This module is a self-contained Python port — it does not require GemStone.
The persistence example (persist.py) shows how to store a Tree2D in GemStone
via PersistentRoot.

Classes
-------
PointKD       — K-dimensional Euclidean point with optional data label
Point2D       — 2D specialisation (x, y) with random factory
SearchResult  — (value, distance) pair returned by nearest_k
BestK         — fixed-size max-heap that tracks the K best results
TreeKD        — K-dimensional KD-tree
Tree2D        — 2D specialisation of TreeKD
"""

from __future__ import annotations

PORTING_STATUS = "translated_example"
RUNTIME_REQUIREMENT = "Runs as translated example code on plain GemStone images or standard Python web stacks"

import math
import random
from typing import Any, Iterator, Optional


# ---------------------------------------------------------------------------
# Heap / BestK
# ---------------------------------------------------------------------------

class Heap:
    """
    Array-backed min-heap (by default; pass a comparator for max-heap).

    The comparator `cmp(a, b)` returns True if `a` should be closer to
    the root than `b`.  Default: min-heap (smaller values at root).
    """

    def __init__(self, cmp=None):
        self._data: list = []
        self._cmp  = cmp or (lambda a, b: a < b)

    def __len__(self) -> int:
        return len(self._data)

    @property
    def size(self) -> int:
        return len(self._data)

    def add(self, el) -> 'Heap':
        self._data.append(el)
        self._bubble_up(len(self._data) - 1)
        return self

    def top(self):
        if not self._data:
            raise IndexError("Empty heap")
        return self._data[0]

    def delete_top(self):
        if not self._data:
            raise IndexError("Empty heap")
        top = self._data[0]
        last = self._data.pop()
        if self._data:
            self._data[0] = last
            self._percolate_down(0)
        return top

    def values(self) -> list:
        return list(self._data)

    def remove_all(self) -> list:
        return [self.delete_top() for _ in range(len(self._data))]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _left(i):  return 2 * i + 1
    @staticmethod
    def _right(i): return 2 * i + 2
    @staticmethod
    def _parent(i): return (i - 1) // 2

    def _bubble_up(self, i: int) -> None:
        while i > 0:
            p = self._parent(i)
            if self._cmp(self._data[i], self._data[p]):
                self._data[i], self._data[p] = self._data[p], self._data[i]
                i = p
            else:
                break

    def _percolate_down(self, i: int) -> None:
        n = len(self._data)
        while True:
            li = self._left(i)
            if li >= n:
                break
            ri = self._right(i)
            child = li if ri >= n or self._cmp(self._data[li], self._data[ri]) else ri
            if self._cmp(self._data[child], self._data[i]):
                self._data[child], self._data[i] = self._data[i], self._data[child]
                i = child
            else:
                break


class BestK(Heap):
    """
    Fixed-capacity heap that keeps the K best elements seen so far.

    By default "best" means smallest (min-heap externally, stored as a
    max-heap internally so the worst best-so-far is at the root and can
    be evicted quickly).
    """

    def __init__(self, k: int, cmp=None):
        if k <= 0:
            raise ValueError(f"k must be > 0, got {k}")
        # Invert the comparator: root = worst of the best-so-far
        user_cmp = cmp or (lambda a, b: a < b)
        super().__init__(cmp=lambda a, b: not user_cmp(a, b))
        self._limit = k

    @property
    def full(self) -> bool:
        return len(self._data) >= self._limit

    def worst(self):
        return self.top()

    def add(self, el) -> 'BestK':
        if len(self._data) >= self._limit:
            if self._cmp(self.top(), el):   # el is better than worst
                super().add(el)
                self.delete_top()
        else:
            super().add(el)
        return self


# ---------------------------------------------------------------------------
# Points
# ---------------------------------------------------------------------------

class PointKD:
    """
    K-dimensional Euclidean point with optional data label.

    Coordinates are stored in `tuple` (list).  The first three are also
    exposed as `x`, `y`, `z` for fast access (None if the dimension is
    lower than that axis).
    """

    def __init__(self, coords: list, data: Any = None):
        self.tuple = list(coords)
        self.data  = data
        self.x = coords[0] if len(coords) > 0 else None
        self.y = coords[1] if len(coords) > 1 else None
        self.z = coords[2] if len(coords) > 2 else None

    def __getitem__(self, index: int):
        if index < 0 or index >= len(self.tuple):
            raise IndexError(f"index {index} out of range [0, {len(self.tuple)})")
        return self.tuple[index]

    def distance_sq(self, other: 'PointKD') -> float:
        """Squared Euclidean distance to `other`."""
        k = len(self.tuple)
        if k == 1:
            dx = self.x - other.x
            return dx * dx
        if k == 2:
            dx = self.x - other.x
            dy = self.y - other.y
            return dx * dx + dy * dy
        if k == 3:
            dx = self.x - other.x
            dy = self.y - other.y
            dz = self.z - other.z
            return dx * dx + dy * dy + dz * dz
        return sum((self.tuple[i] - other.tuple[i]) ** 2 for i in range(k))

    def distance(self, other: 'PointKD') -> float:
        return math.sqrt(self.distance_sq(other))

    def __eq__(self, other):
        return isinstance(other, PointKD) and self.tuple == other.tuple and self.data == other.data

    def __hash__(self):
        return hash((tuple(self.tuple), self.data))

    def __repr__(self):
        return f"Point[{', '.join(str(c) for c in self.tuple)}] {self.data}"


class Point2D(PointKD):
    """
    2-dimensional point with x, y coordinates.

    Port of lib/tree2d.rb — Point2D.
    """

    MAX_SCALAR = 360.0
    MID_POINT  = MAX_SCALAR / 2.0

    def __init__(self, x: float, y: float, data: Any = None):
        super().__init__([x, y], data)

    @classmethod
    def random(cls, data: Any = None) -> 'Point2D':
        """Return a Point2D with random lat/lon coordinates."""
        x = random.uniform(-cls.MID_POINT, cls.MID_POINT)
        y = random.uniform(-cls.MID_POINT, cls.MID_POINT)
        return cls(x, y, data or ':target')

    def __repr__(self):
        return f"Point2D({self.x:.4f}, {self.y:.4f}) {self.data}"


# ---------------------------------------------------------------------------
# SearchResult
# ---------------------------------------------------------------------------

class SearchResult:
    """A point and its squared distance from a query point."""

    def __init__(self, value: PointKD, distance_sq: float):
        self.value       = value
        self.distance_sq = distance_sq
        self.distance    = math.sqrt(distance_sq)

    def __lt__(self, other): return self.distance_sq <  other.distance_sq
    def __le__(self, other): return self.distance_sq <= other.distance_sq
    def __gt__(self, other): return self.distance_sq >  other.distance_sq
    def __ge__(self, other): return self.distance_sq >= other.distance_sq
    def __eq__(self, other): return self.distance_sq == other.distance_sq

    def __repr__(self):
        return f"SearchResult(dist={self.distance:.4f}, value={self.value})"


# ---------------------------------------------------------------------------
# TreeKD  (port of lib/treekd.rb)
# ---------------------------------------------------------------------------

class TreeKD:
    """
    K-dimensional KD-tree.

    Values are stored in both leaves and interior nodes.  Construction
    from a list of points is balanced (median-split on cycling axes).

    Balanced tree construction and nearest-neighbour search for K dimensions.
    """

    def __init__(self, points: list, dimension: int, depth: int = 0):
        self.dimension = dimension
        self._axis  = depth % dimension
        self.left:  Optional['TreeKD'] = None
        self.right: Optional['TreeKD'] = None
        self.value: Optional[PointKD] = None

        if not points:
            return

        axis = self._axis
        if axis == 0:
            sorted_pts = sorted(points, key=lambda p: p.x)
        elif axis == 1:
            sorted_pts = sorted(points, key=lambda p: p.y)
        elif axis == 2:
            sorted_pts = sorted(points, key=lambda p: p.z)
        else:
            sorted_pts = sorted(points, key=lambda p: p[axis])

        pivot = len(sorted_pts) // 2
        self.value = sorted_pts[pivot]

        left_pts  = sorted_pts[:pivot]
        right_pts = sorted_pts[pivot + 1:]

        if left_pts:
            self.left  = TreeKD(left_pts,  dimension, depth + 1)
        if right_pts:
            self.right = TreeKD(right_pts, dimension, depth + 1)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def leaf(self) -> bool:
        return self.left is None and self.right is None

    @property
    def empty(self) -> bool:
        return self.value is None

    def max_depth(self) -> int:
        """Maximum depth of the tree (0 = empty, 1 = single node)."""
        if self.empty:
            return 0
        if self.leaf:
            return 1
        ld = self.left.max_depth()  if self.left  else 0
        rd = self.right.max_depth() if self.right else 0
        return max(ld, rd) + 1

    def balanced(self) -> bool:
        if self.empty or self.leaf:
            return True
        ld = self.left.max_depth()  if self.left  else 0
        rd = self.right.max_depth() if self.right else 0
        return abs(ld - rd) <= 1

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def insert_point(self, point: PointKD) -> None:
        """Insert a point.  The tree may become unbalanced over time."""
        if self.empty:
            self.value = point
            return
        axis = self._axis
        if point[axis] >= self.value[axis]:
            if self.right is None:
                self.right = TreeKD([point], self.dimension, self._axis + 1)
            else:
                self.right.insert_point(point)
        else:
            if self.left is None:
                self.left = TreeKD([point], self.dimension, self._axis + 1)
            else:
                self.left.insert_point(point)

    def rebuild(self) -> 'TreeKD':
        """Return a new balanced tree with all current points."""
        points = list(self)
        return TreeKD(points, self.dimension)

    def remove(self) -> None:
        """Remove the root node in-place; rebalances subtree."""
        pts = []
        if self.left:
            pts.extend(self.left)
        if self.right:
            pts.extend(self.right)
        replacement = TreeKD(pts, self.dimension) if pts else TreeKD([], self.dimension)
        self.value = replacement.value
        self.left  = replacement.left
        self.right = replacement.right

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def nearest(self, target: PointKD) -> Optional[SearchResult]:
        """Return the nearest point to `target`, or None if tree is empty."""
        results = self.nearest_k(target, 1)
        return results[0] if results else None

    def nearest_k(self, target: PointKD, k: int = 1) -> list[SearchResult]:
        """Return the `k` nearest SearchResults to `target`."""
        bestk = BestK(k, cmp=lambda a, b: a < b)
        self._nearest_k(target, bestk)
        return sorted(bestk.values())

    def _nearest_k(self, target: PointKD, bestk: BestK) -> None:
        if self.empty:
            return

        my_result = SearchResult(self.value, target.distance_sq(self.value))

        if self.leaf:
            bestk.add(my_result)
            return

        axis = self._axis
        if axis == 0:
            cmp = (target.x > self.value.x) - (target.x < self.value.x)
        elif axis == 1:
            cmp = (target.y > self.value.y) - (target.y < self.value.y)
        elif axis == 2:
            cmp = (target.z > self.value.z) - (target.z < self.value.z)
        else:
            cmp = (target[axis] > self.value[axis]) - (target[axis] < self.value[axis])

        if cmp < 0:
            near, far = self.left, self.right
        else:
            near, far = self.right, self.left

        if near:
            near._nearest_k(target, bestk)

        # Check whether the far subtree might contain closer points
        if far and not (bestk.full and self._axis_too_far(target, bestk)):
            far._nearest_k(target, bestk)

        bestk.add(my_result)

    def _axis_too_far(self, target: PointKD, bestk: BestK) -> bool:
        axis = self._axis
        if axis == 0:
            d = self.value.x - target.x
        elif axis == 1:
            d = self.value.y - target.y
        elif axis == 2:
            d = self.value.z - target.z
        else:
            d = self.value[axis] - target[axis]
        return bestk.worst().distance_sq < d * d

    # ------------------------------------------------------------------
    # Iteration (in-order: left → value → right)
    # ------------------------------------------------------------------

    def __iter__(self) -> Iterator[PointKD]:
        if self.left:
            yield from self.left
        if self.value is not None:
            yield self.value
        if self.right:
            yield from self.right

    def pre_order(self) -> Iterator['TreeKD']:
        yield self
        if self.left:  yield from self.left.pre_order()
        if self.right: yield from self.right.pre_order()

    def post_order(self) -> Iterator['TreeKD']:
        if self.left:  yield from self.left.post_order()
        if self.right: yield from self.right.post_order()
        yield self

    def in_order(self) -> Iterator['TreeKD']:
        if self.left:  yield from self.left.in_order()
        yield self
        if self.right: yield from self.right.in_order()

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def print_tree(self, offset: int = 0) -> None:
        if self.right:
            self.right.print_tree(offset + 2)
        print(' ' * offset + str(self.value))
        if self.left:
            self.left.print_tree(offset + 2)

    def __repr__(self):
        return (
            f"Tree{self.dimension}D(value={self.value!r}, "
            f"left={self.left!r}, right={self.right!r})"
        )


class Tree2D(TreeKD):
    """
    2-dimensional KD-tree.
    """

    def __init__(self, points: list, depth: int = 0):
        super().__init__(points, 2, depth)

    @classmethod
    def random(cls, size: int = 1000) -> 'Tree2D':
        """Create a Tree2D with `size` random Point2D nodes."""
        points = [Point2D.random(f"point {i}") for i in range(size)]
        return cls(points)

    def insert_point(self, point: PointKD) -> None:
        if self.empty:
            self.value = point
            return
        axis = self._axis
        cmp_val = point[axis] >= self.value[axis]
        if cmp_val:
            if self.right is None:
                self.right = Tree2D([point], self._axis + 1)
            else:
                self.right.insert_point(point)
        else:
            if self.left is None:
                self.left = Tree2D([point], self._axis + 1)
            else:
                self.left.insert_point(point)
