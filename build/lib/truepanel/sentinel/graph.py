"""Deterministic graph traversal for Project SENTINEL."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from .models import KnowledgeEdge, KnowledgeNode


@dataclass(frozen=True, slots=True)
class ImpactPath:
    """One downstream object reachable from an observed source."""

    node_id: str
    depth: int
    via: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "depth": self.depth,
            "via": list(self.via),
        }


class KnowledgeGraph:
    """Small read-only-oriented graph with deterministic serialization.

    Edge direction describes propagation: if ``A -> B`` then evidence about A
    may have consequences for B. Traversal is cycle-safe and stable across
    insertion order so snapshots remain testable and reviewable.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, KnowledgeNode] = {}
        self._edges: set[KnowledgeEdge] = set()

    def add_node(self, node: KnowledgeNode) -> None:
        existing = self._nodes.get(node.id)
        if existing is not None and existing != node:
            raise ValueError(f"conflicting SENTINEL node: {node.id}")
        self._nodes[node.id] = node

    def add_edge(self, edge: KnowledgeEdge) -> None:
        if edge.source == edge.target:
            raise ValueError("SENTINEL self-edges are not allowed")
        missing = [
            node_id
            for node_id in (edge.source, edge.target)
            if node_id not in self._nodes
        ]
        if missing:
            raise ValueError(
                "SENTINEL edge references missing node(s): "
                + ", ".join(sorted(missing))
            )
        self._edges.add(edge)

    def node(self, node_id: str) -> KnowledgeNode | None:
        return self._nodes.get(node_id)

    def blast_radius(
        self,
        node_id: str,
        *,
        max_depth: int | None = None,
    ) -> list[ImpactPath]:
        """Return downstream effects without pretending unreachable data exists."""

        if node_id not in self._nodes:
            return []
        if max_depth is not None and max_depth < 1:
            return []

        outgoing: dict[str, list[KnowledgeEdge]] = {}
        for edge in self._edges:
            outgoing.setdefault(edge.source, []).append(edge)
        for edges in outgoing.values():
            edges.sort(key=lambda item: (item.target, item.relation.value))

        result: list[ImpactPath] = []
        visited = {node_id}
        queue = deque([(node_id, 0, (node_id,))])

        while queue:
            current, depth, path = queue.popleft()
            if max_depth is not None and depth >= max_depth:
                continue
            for edge in outgoing.get(current, []):
                if edge.target in visited:
                    continue
                visited.add(edge.target)
                next_path = (*path, edge.target)
                result.append(
                    ImpactPath(
                        node_id=edge.target,
                        depth=depth + 1,
                        via=next_path,
                    )
                )
                queue.append((edge.target, depth + 1, next_path))

        return sorted(result, key=lambda item: (item.depth, item.node_id))

    def to_payload(self) -> dict[str, Any]:
        nodes = sorted(self._nodes.values(), key=lambda item: item.id)
        edges = sorted(
            self._edges,
            key=lambda item: (
                item.source,
                item.target,
                item.relation.value,
            ),
        )
        return {
            "nodes": [node.to_payload() for node in nodes],
            "edges": [edge.to_payload() for edge in edges],
        }
