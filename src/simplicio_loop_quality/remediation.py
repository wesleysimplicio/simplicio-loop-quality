"""Finding normalization and Loop recovery requests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-remediation/v1"


def _hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class RemediationRequest:
    finding_id: str
    fingerprint: str
    severity: str
    owner_stage: str
    evidence_refs: tuple[str, ...]
    source_sha: str
    status: str = "OPEN"

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, **self.__dict__}


def normalize_findings(
    findings: list[Mapping[str, Any]], *, source_sha: str
) -> tuple[RemediationRequest, ...]:
    requests: dict[str, RemediationRequest] = {}
    for index, item in enumerate(findings):
        detail = str(item.get("detail", item.get("message", "")))
        fingerprint = _hash(
            {"path": item.get("path"), "rule": item.get("rule"), "detail": detail}
        )
        request = RemediationRequest(
            str(item.get("finding_id", f"finding-{index}")),
            fingerprint,
            str(item.get("severity", "error")),
            str(item.get("owner_stage", "recovery")),
            tuple(sorted(str(x) for x in item.get("evidence_refs", ()))),
            source_sha,
        )
        requests.setdefault(fingerprint, request)
    return tuple(sorted(requests.values(), key=lambda x: x.fingerprint))


def reverify(
    request: RemediationRequest, *, candidate_status: str, candidate_source_sha: str
) -> RemediationRequest:
    if candidate_source_sha != request.source_sha:
        return RemediationRequest(
            request.finding_id,
            request.fingerprint,
            request.severity,
            request.owner_stage,
            request.evidence_refs,
            candidate_source_sha,
            "STALE",
        )
    status = "RESOLVED" if candidate_status.upper() == "PASS" else "REOPENED"
    return RemediationRequest(
        request.finding_id,
        request.fingerprint,
        request.severity,
        request.owner_stage,
        request.evidence_refs,
        request.source_sha,
        status,
    )


__all__ = ["RemediationRequest", "SCHEMA", "normalize_findings", "reverify"]
