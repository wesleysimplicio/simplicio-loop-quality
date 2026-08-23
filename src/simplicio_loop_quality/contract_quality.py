"""Contract conformance checks for quality stage documents."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-contract-test/v1"
REQUIRED = ("schema", "identity", "stage_id", "lane", "status")


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class ContractFinding:
    code: str
    path: str
    detail: str


@dataclass(frozen=True)
class ContractResult:
    status: str
    findings: tuple[ContractFinding, ...]
    document_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": self.status, "findings": [item.__dict__ for item in self.findings], "document_hash": self.document_hash}


def validate_contract(document: Mapping[str, Any], *, expected_source_sha: str | None = None, expected_policy_hash: str | None = None) -> ContractResult:
    findings: list[ContractFinding] = []
    for key in REQUIRED:
        if key not in document:
            findings.append(ContractFinding("FIELD_MISSING", f"$.{key}", f"required field missing: {key}"))
    identity = document.get("identity", {})
    if not isinstance(identity, Mapping):
        findings.append(ContractFinding("IDENTITY_INVALID", "$.identity", "identity must be an object"))
    elif expected_source_sha and identity.get("source_sha") != expected_source_sha:
        findings.append(ContractFinding("SOURCE_STALE", "$.identity.source_sha", "source binding differs"))
    if expected_policy_hash and identity.get("policy_hash") != expected_policy_hash:
        findings.append(ContractFinding("POLICY_STALE", "$.identity.policy_hash", "policy binding differs"))
    status = str(document.get("status", "")).upper()
    if status not in {"PASS", "FAIL", "BLOCKED", "PLANNED"}:
        findings.append(ContractFinding("STATUS_INVALID", "$.status", "unknown contract status"))
    if status == "PASS" and not document.get("evidence"):
        findings.append(ContractFinding("PASS_WITHOUT_EVIDENCE", "$.evidence", "PASS requires evidence"))
    return ContractResult("PASS" if not findings else "FAIL", tuple(findings), _hash(document))


def compare_contracts(documents: list[Mapping[str, Any]]) -> tuple[ContractFinding, ...]:
    findings: list[ContractFinding] = []
    seen: dict[tuple[str, str], str] = {}
    for index, document in enumerate(documents):
        key = (str(document.get("stage_id", "")), str(document.get("lane", "")))
        fingerprint = _hash(document)
        if key in seen and seen[key] != fingerprint:
            findings.append(
                ContractFinding(
                    "CONTRADICTION",
                    f"$[{index}]",
                    f"conflicts with earlier {key[0]}/{key[1]} document",
                )
            )
        seen[key] = fingerprint
    return tuple(findings)


class ContractTestAgent:
    def validate(self, request: Mapping[str, Any]) -> ContractResult:
        return validate_contract(
            request.get("document", {}),
            expected_source_sha=request.get("source_sha"),
            expected_policy_hash=request.get("policy_hash"),
        )


__all__ = [
    "SCHEMA",
    "ContractFinding",
    "ContractResult",
    "ContractTestAgent",
    "compare_contracts",
    "validate_contract",
]
