"""Minimal BK-tree for approximate nearest-neighbor search over a discrete
metric distance (Hamming distance between perceptual hashes here).

Used for the cross-batch duplicate lookup (spec Section 6.4) so a new card
only needs one Hamming-distance-bounded query instead of a brute-force scan
over the entire historical log.
"""

from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class _Node(Generic[T]):
    __slots__ = ("value", "payload", "children")

    def __init__(self, value: str, payload: T) -> None:
        self.value = value
        self.payload = payload
        self.children: dict[int, "_Node[T]"] = {}


class BKTree(Generic[T]):
    def __init__(self, distance_fn: Callable[[str, str], int]) -> None:
        self._distance_fn = distance_fn
        self._root: _Node[T] | None = None

    def add(self, value: str, payload: T) -> None:
        if self._root is None:
            self._root = _Node(value, payload)
            return

        node = self._root
        while True:
            dist = self._distance_fn(value, node.value)
            child = node.children.get(dist)
            if child is None:
                node.children[dist] = _Node(value, payload)
                return
            node = child

    def query(self, value: str, max_distance: int) -> list[tuple[T, int]]:
        if self._root is None:
            return []

        results: list[tuple[T, int]] = []
        stack = [self._root]
        while stack:
            node = stack.pop()
            dist = self._distance_fn(value, node.value)
            if dist <= max_distance:
                results.append((node.payload, dist))

            low, high = dist - max_distance, dist + max_distance
            for child_dist, child in node.children.items():
                if low <= child_dist <= high:
                    stack.append(child)
        return results
