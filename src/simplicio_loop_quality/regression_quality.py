"""Fail-before/pass-after regression proof normalization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-regression/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class RegressionCase:
    case_id: str
    baseline_status: str
    candidate_status: str
    baseline_fingerprint: str | None
    candidate_fingerprint: str | None
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class RegressionVerdict:
    status: str
    cases: tuple[RegressionCase, ...]
    reason_codes: tuple[str, ...]
    receipt_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "cases": [case.__dict__ for case in self.cases], "reason_codes": list(self.reason_codes), "receipt_id": self.receipt_id}


def prove_regression(cases: list[Mapping[str, Any]], *, source_sha: str, policy_hash: str) -> RegressionVerdict:
    normalized: list[RegressionCase] = []
    reasons: set[str] = set()
    for item in cases:
        case = RegressionCase(
            str(item.get("case_id", "")), str(item.get("baseline_status", "")), str(item.get("candidate_status", "")),
            item.get("baseline_fingerprint"), item.get("candidate_fingerprint"), tuple(sorted(str(ref) for ref in item.get("evidence_refs", ()))),
        )
        normalized.append(case)
        if not case.case_id:
            reasons.add("CASE_ID_MISSING")
        if case.baseline_status != "FAIL":
            reasons.add("FAIL_BEFORE_NOT_PROVEN")
        if case.candidate_status != "PASS":
            reasons.add("PASS_AFTER_NOT_PROVEN")
        if not case.baseline_fingerprint or not case.candidate_fingerprint:
            reasons.add("FINGERPRINT_MISSING")
        if not case.evidence_refs:
            reasons.add("EVIDENCE_MISSING")
    if not normalized:
        reasons.add("REGRESSION_CASES_EMPTY")
    payload = {"source_sha": source_sha, "policy_hash": policy_hash, "cases": [case.__dict__ for case in normalized], "reasons": sorted(reasons)}
    status = "PASS" if normalized and not reasons else ("BLOCKED" if not normalized else "FAIL")
    return RegressionVerdict(status, tuple(sorted(normalized, key=lambda item: item.case_id)), tuple(sorted(reasons)), _hash(payload))


class RegressionTestAgent:
    def prove(self, request: Mapping[str, Any]) -> RegressionVerdict:
        return prove_regression(list(request.get("cases", ())), source_sha=str(request.get("source_sha", "")), policy_hash=str(request.get("policy_hash", "")))


__all__ = ["RegressionCase", "RegressionTestAgent", "RegressionVerdict", "SCHEMA", "prove_regression"]
