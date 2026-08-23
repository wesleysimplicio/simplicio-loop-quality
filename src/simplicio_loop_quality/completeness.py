"""Implementation-completeness mapping for acceptance criteria."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-completeness/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class CriterionStatus:
    criterion_id: str
    implementation_refs: tuple[str, ...]
    test_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    status: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class CompletenessVerdict:
    status: str
    criteria: tuple[CriterionStatus, ...]
    receipt_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "criteria": [item.__dict__ for item in self.criteria], "receipt_id": self.receipt_id}


def evaluate_completeness(criteria: list[Mapping[str, Any]], *, source_sha: str, policy_hash: str) -> CompletenessVerdict:
    results: list[CriterionStatus] = []
    for item in criteria:
        implementation = tuple(sorted(str(value) for value in item.get("implementation_refs", ()) if value))
        tests = tuple(sorted(str(value) for value in item.get("test_refs", ()) if value))
        evidence = tuple(sorted(str(value) for value in item.get("evidence_refs", ()) if value))
        reasons: list[str] = []
        if not implementation:
            reasons.append("IMPLEMENTATION_MISSING")
        if not tests:
            reasons.append("TEST_MISSING")
        if not evidence:
            reasons.append("EVIDENCE_MISSING")
        results.append(CriterionStatus(str(item.get("criterion_id", "")), implementation, tests, evidence, "PASS" if not reasons else "BLOCKED", tuple(reasons)))
    if not results:
        status = "BLOCKED"
    elif any(item.status != "PASS" for item in results):
        status = "BLOCKED"
    else:
        status = "PASS"
    payload = {"source_sha": source_sha, "policy_hash": policy_hash, "status": status, "criteria": [item.__dict__ for item in results]}
    return CompletenessVerdict(status, tuple(sorted(results, key=lambda item: item.criterion_id)), _hash(payload))


class ImplementationCompletenessAgent:
    def evaluate(self, request: Mapping[str, Any]) -> CompletenessVerdict:
        return evaluate_completeness(list(request.get("criteria", ())), source_sha=str(request.get("source_sha", "")), policy_hash=str(request.get("policy_hash", "")))


__all__ = ["CompletenessVerdict", "CriterionStatus", "ImplementationCompletenessAgent", "SCHEMA", "evaluate_completeness"]
