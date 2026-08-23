"""Independent evidence audit primitives.

The auditor recomputes bindings and content digests.  A producer's claim is
never accepted merely because it has a receipt-shaped dictionary.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-evidence-audit/v1"
REQUIRED_IDENTITY = ("run_id", "task_id", "attempt_id", "fence", "source_sha", "policy_hash")


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class AuditFinding:
    code: str
    detail: str
    evidence_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail, "evidence_id": self.evidence_id}


@dataclass(frozen=True)
class AuditVerdict:
    status: str
    findings: tuple[AuditFinding, ...]
    audited_count: int
    auditor_id: str
    receipt_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "status": self.status,
            "findings": [item.to_dict() for item in self.findings],
            "audited_count": self.audited_count,
            "auditor_id": self.auditor_id,
            "receipt_id": self.receipt_id,
        }


def audit_evidence(
    records: list[Mapping[str, Any]],
    *,
    expected_identity: Mapping[str, Any],
    auditor_id: str,
) -> AuditVerdict:
    """Audit bindings, independence and content hashes without executing work."""

    findings: list[AuditFinding] = []
    if not auditor_id.strip():
        findings.append(
            AuditFinding("AUDITOR_ID_MISSING", "independent auditor identity is required")
        )
    for key in REQUIRED_IDENTITY:
        if key not in expected_identity or expected_identity[key] in (None, ""):
            findings.append(
                AuditFinding("EXPECTED_IDENTITY_MISSING", f"missing expected identity: {key}")
            )
    for index, record in enumerate(records):
        evidence_id = str(record.get("evidence_id", f"record-{index}"))
        identity = record.get("identity")
        if not isinstance(identity, Mapping):
            findings.append(
                AuditFinding("IDENTITY_MISSING", "record has no bound identity", evidence_id)
            )
        else:
            for key in REQUIRED_IDENTITY:
                if identity.get(key) != expected_identity.get(key):
                    findings.append(
                        AuditFinding("STALE_OR_CROSS_RUN", f"identity mismatch: {key}", evidence_id)
                    )
        producer = str(record.get("producer_agent", ""))
        executor = str(record.get("executor_agent", ""))
        auditor = str(record.get("auditor_agent", ""))
        if not producer or not executor or not auditor:
            findings.append(
                AuditFinding(
                    "IDENTITY_SEPARATION_MISSING",
                    "producer, executor and auditor are required",
                    evidence_id,
                )
            )
        if len({producer, executor, auditor}) != 3 or auditor == auditor_id:
            findings.append(
                AuditFinding(
                    "IDENTITY_NOT_INDEPENDENT", "audit seat is not independent", evidence_id
                )
            )
        expected_digest = hashlib.sha256(str(record.get("content", "")).encode()).hexdigest()
        if record.get("content") is not None and record.get("sha256") != expected_digest:
            findings.append(
                AuditFinding("ARTIFACT_TAMPERED", "content digest does not match", evidence_id)
            )
        if not record.get("sha256") and record.get("content") is None:
            findings.append(
                AuditFinding(
                    "ARTIFACT_HASH_MISSING",
                    "raw content or digest is required",
                    evidence_id,
                )
            )
    status = "PASS" if records and not findings else ("BLOCKED" if not records else "FAIL")
    payload = {
        "status": status,
        "findings": [item.to_dict() for item in findings],
        "audited_count": len(records),
        "auditor_id": auditor_id,
    }
    return AuditVerdict(status, tuple(findings), len(records), auditor_id, _digest(payload))


class EvidenceAuditAgent:
    def audit(self, request: Mapping[str, Any]) -> AuditVerdict:
        return audit_evidence(
            list(request.get("records", ())),
            expected_identity=request.get("identity", {}),
            auditor_id=str(request.get("auditor_id", "")),
        )


__all__ = [
    "AuditFinding",
    "AuditVerdict",
    "EvidenceAuditAgent",
    "SCHEMA",
    "audit_evidence",
]
