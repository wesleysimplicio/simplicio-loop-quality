"""Independent, source-bound review finding normalization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-code-review/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class ReviewFinding:
    finding_id: str
    severity: str
    category: str
    path: str
    detail: str
    evidence_ref: str | None


@dataclass(frozen=True)
class ReviewVerdict:
    status: str
    reviewer_id: str
    source_sha: str
    findings: tuple[ReviewFinding, ...]
    reason_codes: tuple[str, ...]
    review_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "reviewer_id": self.reviewer_id, "source_sha": self.source_sha, "findings": [item.__dict__ for item in self.findings], "reason_codes": list(self.reason_codes), "review_id": self.review_id}


def review_diff(findings: list[Mapping[str, Any]], *, reviewer_id: str, author_id: str, source_sha: str, diff_source_sha: str) -> ReviewVerdict:
    reasons: set[str] = set()
    if not reviewer_id.strip():
        reasons.add("REVIEWER_MISSING")
    if reviewer_id == author_id:
        reasons.add("SELF_REVIEW_FORBIDDEN")
    if source_sha != diff_source_sha:
        reasons.add("STALE_DIFF")
    normalized: list[ReviewFinding] = []
    for index, item in enumerate(findings):
        evidence = item.get("evidence_ref")
        if not evidence:
            reasons.add("UNSUPPORTED_CLAIM")
        severity = str(item.get("severity", "blocking")).lower()
        if severity not in {"blocking", "suggestion", "info"}:
            reasons.add("SEVERITY_INVALID")
            severity = "blocking"
        normalized.append(ReviewFinding(str(item.get("finding_id", f"finding-{index}")), severity, str(item.get("category", "correctness")), str(item.get("path", "")), str(item.get("detail", "")), str(evidence) if evidence else None))
    if any(item.severity == "blocking" for item in normalized):
        reasons.add("BLOCKING_FINDINGS")
    status = "PASS" if not reasons else "FAIL"
    payload = {"status": status, "reviewer_id": reviewer_id, "source_sha": source_sha, "findings": [item.__dict__ for item in normalized], "reasons": sorted(reasons)}
    return ReviewVerdict(status, reviewer_id, source_sha, tuple(sorted(normalized, key=lambda item: item.finding_id)), tuple(sorted(reasons)), _hash(payload))


class IndependentCodeReviewAgent:
    def review(self, request: Mapping[str, Any]) -> ReviewVerdict:
        return review_diff(list(request.get("findings", ())), reviewer_id=str(request.get("reviewer_id", "")), author_id=str(request.get("author_id", "")), source_sha=str(request.get("source_sha", "")), diff_source_sha=str(request.get("diff_source_sha", "")))


__all__ = ["IndependentCodeReviewAgent", "ReviewFinding", "ReviewVerdict", "SCHEMA", "review_diff"]
