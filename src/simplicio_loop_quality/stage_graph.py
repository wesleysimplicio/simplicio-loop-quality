"""Deterministic quality stage graph compilation without execution authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-stage-graph/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class StageGraph:
    status: str
    stages: tuple[Mapping[str, Any], ...]
    edges: tuple[tuple[str, str], ...]
    graph_hash: str
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "stages": [dict(x) for x in self.stages], "edges": [list(x) for x in self.edges], "graph_hash": self.graph_hash, "reason_codes": list(self.reason_codes)}


def compile_stage_graph(stages: list[Mapping[str, Any]], edges: list[tuple[str, str]], *, policy_hash: str) -> StageGraph:
    reasons: set[str] = set()
    ids = [str(stage.get("id", "")) for stage in stages]
    if not all(ids):
        reasons.add("STAGE_ID_MISSING")
    if len(ids) != len(set(ids)):
        reasons.add("STAGE_ID_DUPLICATE")
    known = set(ids)
    if any(left not in known or right not in known for left, right in edges):
        reasons.add("EDGE_ENDPOINT_UNKNOWN")
    adjacency = {stage_id: [] for stage_id in ids}
    for left, right in edges:
        if left in adjacency:
            adjacency[left].append(right)
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(node: str) -> None:
        if node in visiting:
            reasons.add("GRAPH_CYCLE")
            return
        if node in visited:
            return
        visiting.add(node)
        for child in adjacency.get(node, ()):
            visit(child)
        visiting.remove(node)
        visited.add(node)
    for node in ids:
        visit(node)
    payload = {"policy_hash": policy_hash, "stages": sorted(stages, key=lambda x: str(x.get("id", ""))), "edges": sorted(edges), "reasons": sorted(reasons)}
    return StageGraph("PLANNED" if not reasons else "BLOCKED", tuple(sorted(stages, key=lambda x: str(x.get("id", "")))), tuple(sorted(edges)), _hash(payload), tuple(sorted(reasons)))


class QualityStageGraphCompiler:
    def compile(self, request: Mapping[str, Any]) -> StageGraph:
        return compile_stage_graph(list(request.get("stages", ())), [tuple(edge) for edge in request.get("edges", ())], policy_hash=str(request.get("policy_hash", "")))


__all__ = ["QualityStageGraphCompiler", "SCHEMA", "StageGraph", "compile_stage_graph"]
