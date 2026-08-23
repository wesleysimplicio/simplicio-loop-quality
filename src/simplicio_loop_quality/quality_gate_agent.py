"""Deterministic terminal-quality recommendation with no Loop authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-gate-agent/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class QualityGateRecommendation:
    status: str
    reason_codes: tuple[str, ...]
    source_sha: str
    policy_hash: str
    receipt_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "ready": False, "reason_codes": list(self.reason_codes), "source_sha": self.source_sha, "policy_hash": self.policy_hash, "receipt_id": self.receipt_id}


def evaluate_quality_gate(receipt: Mapping[str, Any], *, source_sha: str, policy_hash: str) -> QualityGateRecommendation:
    reasons: set[str] = set()
    if receipt.get("source_sha") != source_sha:
        reasons.add("SOURCE_STALE")
    if receipt.get("policy_hash") != policy_hash:
        reasons.add("POLICY_STALE")
    if str(receipt.get("audit_status", "")).upper() != "PASS":
        reasons.add("INDEPENDENT_AUDIT_REQUIRED")
    lanes = receipt.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        reasons.add("LANE_RECEIPTS_MISSING")
    elif any(str(lane.get("status", "")).upper() != "PASS" for lane in lanes if isinstance(lane, Mapping)):
        reasons.add("LANE_NOT_PASS")
    if receipt.get("findings"):
        reasons.add("FINDINGS_PRESENT")
    status = "PASS" if not reasons else "BLOCKED"
    payload = {"status": status, "reasons": sorted(reasons), "source_sha": source_sha, "policy_hash": policy_hash}
    return QualityGateRecommendation(status, tuple(sorted(reasons)), source_sha, policy_hash, _hash(payload))


class QualityGateAgent:
    def evaluate(self, request: Mapping[str, Any]) -> QualityGateRecommendation:
        return evaluate_quality_gate(request.get("receipt", {}), source_sha=str(request.get("source_sha", "")), policy_hash=str(request.get("policy_hash", "")))


__all__ = ["QualityGateAgent", "QualityGateRecommendation", "SCHEMA", "evaluate_quality_gate"]
