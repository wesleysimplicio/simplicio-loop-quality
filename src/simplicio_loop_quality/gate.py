"""Deterministic, fail-closed evaluation of a quality evidence receipt."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .policy import QualityPolicy


@dataclass(frozen=True)
class GateFinding:
    reason_code: str
    detail: str
    lane: str = ""


@dataclass(frozen=True)
class GateContext:
    """Trusted values supplied by the Loop, outside the producer receipt."""

    expected_run_id: str
    expected_task_id: str
    expected_attempt_id: str
    expected_source_sha: str
    expected_diff_hash: str
    expected_policy_hash: str
    artifact_root: Path
    trusted_by_loop: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_root", Path(self.artifact_root).resolve())


@dataclass(frozen=True)
class GateVerdict:
    status: str
    reason_code: str
    findings: tuple[GateFinding, ...]
    source_sha: str = ""
    policy_hash: str = ""

    @property
    def ready(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "simplicio.quality-gate-verdict/v1",
            "status": self.status,
            "ready": self.ready,
            "reason_code": self.reason_code,
            "source_sha": self.source_sha,
            "policy_hash": self.policy_hash,
            "findings": [asdict(finding) for finding in self.findings],
        }


def _finding(code: str, detail: str, lane: str = "") -> GateFinding:
    return GateFinding(reason_code=code, detail=detail, lane=lane)


_SOURCE_SHA_RE = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_BLOCKED_REASON_CODES = {
    "lane_blocked",
    "coverage_unmeasured",
    "verification_context_untrusted",
}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_evidence(
    items: Any,
    *,
    lane: str,
    source_sha: str,
    receipt: Mapping[str, Any],
    context: GateContext,
) -> list[GateFinding]:
    findings: list[GateFinding] = []
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)) or not items:
        return [_finding("lane_evidence_missing", "PASS requires at least one evidence item", lane)]
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            findings.append(
                _finding("lane_evidence_malformed", f"evidence[{index}] must be an object", lane)
            )
            continue
        for field in (
            "ref",
            "sha256",
            "source_sha",
            "run_id",
            "task_id",
            "attempt_id",
            "process_id",
            "tool_name",
            "tool_version",
            "environment_hash",
        ):
            if not str(item.get(field) or "").strip():
                findings.append(
                    _finding(
                        "lane_evidence_field_missing",
                        f"evidence[{index}].{field} is required",
                        lane,
                    )
                )
        evidence_sha = str(item.get("source_sha") or "").strip()
        if evidence_sha and evidence_sha != source_sha:
            findings.append(
                _finding(
                    "lane_evidence_source_mismatch",
                    f"evidence[{index}] is bound to {evidence_sha}, expected {source_sha}",
                    lane,
                )
            )
        for field in ("run_id", "task_id", "attempt_id"):
            if item.get(field) != receipt.get(field):
                findings.append(
                    _finding(
                        "lane_evidence_identity_mismatch",
                        f"evidence[{index}].{field} does not match the receipt",
                        lane,
                    )
                )
        command = item.get("command")
        if (
            not isinstance(command, Sequence)
            or isinstance(command, (str, bytes))
            or not command
            or not all(isinstance(arg, str) and arg for arg in command)
        ):
            findings.append(
                _finding(
                    "lane_evidence_command_invalid",
                    f"evidence[{index}].command must be a non-empty argument array",
                    lane,
                )
            )
        exit_code = item.get("exit_code")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int) or exit_code != 0:
            findings.append(
                _finding(
                    "lane_evidence_exit_invalid",
                    f"evidence[{index}].exit_code must be integer zero for PASS",
                    lane,
                )
            )
        duration_ms = item.get("duration_ms")
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, (int, float))
            or duration_ms < 0
        ):
            findings.append(
                _finding(
                    "lane_evidence_duration_invalid",
                    f"evidence[{index}].duration_ms must be non-negative",
                    lane,
                )
            )
        expected_hash = str(item.get("sha256") or "").strip().lower()
        if expected_hash and not _SHA256_RE.fullmatch(expected_hash):
            findings.append(
                _finding(
                    "lane_evidence_hash_invalid",
                    f"evidence[{index}].sha256 must be a full SHA-256 digest",
                    lane,
                )
            )
        environment_hash = str(item.get("environment_hash") or "").strip()
        if environment_hash and not _SHA256_RE.fullmatch(environment_hash):
            findings.append(
                _finding(
                    "lane_evidence_environment_invalid",
                    f"evidence[{index}].environment_hash must be a full SHA-256 digest",
                    lane,
                )
            )
        ref = str(item.get("ref") or "").strip()
        raw_ref = Path(ref)
        if ref and (raw_ref.is_absolute() or ".." in raw_ref.parts):
            findings.append(
                _finding(
                    "lane_evidence_ref_unsafe",
                    f"evidence[{index}].ref must stay below the artifact root",
                    lane,
                )
            )
        elif ref:
            artifact = (context.artifact_root / raw_ref).resolve()
            if context.artifact_root != artifact and context.artifact_root not in artifact.parents:
                findings.append(
                    _finding(
                        "lane_evidence_ref_unsafe",
                        f"evidence[{index}].ref escapes the artifact root",
                        lane,
                    )
                )
            elif not artifact.is_file():
                findings.append(
                    _finding(
                        "lane_evidence_artifact_missing",
                        f"evidence[{index}] artifact does not exist",
                        lane,
                    )
                )
            elif _SHA256_RE.fullmatch(expected_hash):
                try:
                    actual_hash = _file_sha256(artifact)
                except OSError as exc:
                    findings.append(
                        _finding(
                            "lane_evidence_artifact_unreadable",
                            f"evidence[{index}] artifact cannot be read: {exc}",
                            lane,
                        )
                    )
                else:
                    if actual_hash != expected_hash:
                        findings.append(
                            _finding(
                                "lane_evidence_hash_mismatch",
                                f"evidence[{index}] artifact digest does not match receipt",
                                lane,
                            )
                        )
    return findings


def _coverage_findings(receipt: Mapping[str, Any], policy: QualityPolicy) -> list[GateFinding]:
    coverage = receipt.get("coverage")
    if not isinstance(coverage, Mapping):
        return [_finding("coverage_missing", "coverage object is required", "coverage")]
    checks = (
        ("global_pct", policy.coverage.global_min_pct),
        ("changed_pct", policy.coverage.changed_min_pct),
        ("critical_pct", policy.coverage.critical_min_pct),
    )
    findings: list[GateFinding] = []
    for field, threshold in checks:
        value = coverage.get(field)
        if value is None:
            reason = str(coverage.get("reason_code") or "measurement_unavailable")
            findings.append(
                _finding(
                    "coverage_unmeasured",
                    f"coverage.{field} is null ({reason}); required >= {threshold:.1f}%",
                    "coverage",
                )
            )
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            findings.append(
                _finding(
                    "coverage_invalid",
                    f"coverage.{field} must be numeric or null",
                    "coverage",
                )
            )
            continue
        if not 0 <= float(value) <= 100:
            findings.append(
                _finding(
                    "coverage_invalid",
                    f"coverage.{field} must be between 0 and 100",
                    "coverage",
                )
            )
        elif float(value) < threshold:
            findings.append(
                _finding(
                    "coverage_below_threshold",
                    f"coverage.{field}={float(value):.2f}% is below {threshold:.2f}%",
                    "coverage",
                )
            )
    return findings


def evaluate_receipt(
    receipt: Any,
    policy: QualityPolicy,
    context: GateContext | None = None,
) -> GateVerdict:
    """Recompute a terminal verdict without trusting producer status fields."""

    if not isinstance(receipt, Mapping):
        finding = _finding("receipt_malformed", "quality receipt must be an object")
        return GateVerdict("BLOCKED", finding.reason_code, (finding,))

    if context is None:
        finding = _finding(
            "verification_context_missing",
            "trusted source identity and artifact root are required",
        )
        return GateVerdict("BLOCKED", finding.reason_code, (finding,))

    findings: list[GateFinding] = []
    if receipt.get("schema") != "simplicio.quality-evidence/v1":
        findings.append(
            _finding("receipt_schema_invalid", "schema must be simplicio.quality-evidence/v1")
        )
    for field in (
        "run_id",
        "task_id",
        "attempt_id",
        "source_sha",
        "diff_hash",
        "policy_hash",
        "generated_at",
    ):
        if not str(receipt.get(field) or "").strip():
            findings.append(_finding("receipt_field_missing", f"{field} is required"))

    source_sha = str(receipt.get("source_sha") or "").strip()
    policy_hash = str(receipt.get("policy_hash") or "").strip()
    identity_expectations = {
        "run_id": context.expected_run_id,
        "task_id": context.expected_task_id,
        "attempt_id": context.expected_attempt_id,
    }
    for field, expected in identity_expectations.items():
        actual = str(receipt.get(field) or "").strip()
        if actual and actual != expected:
            findings.append(
                _finding(
                    "receipt_identity_mismatch",
                    f"receipt {field} {actual!r} does not match trusted value {expected!r}",
                )
            )
    if source_sha and not _SOURCE_SHA_RE.fullmatch(source_sha):
        findings.append(_finding("source_sha_invalid", "source_sha must be a full Git digest"))
    if source_sha and source_sha != context.expected_source_sha:
        findings.append(
            _finding(
                "source_sha_mismatch",
                (
                    f"receipt source {source_sha} does not match trusted source "
                    f"{context.expected_source_sha}"
                ),
            )
        )
    if policy_hash and not _SHA256_RE.fullmatch(policy_hash):
        findings.append(
            _finding("policy_hash_invalid", "policy_hash must be a full SHA-256 digest")
        )
    if policy_hash and policy_hash != policy.canonical_hash:
        findings.append(
            _finding(
                "policy_hash_mismatch",
                f"receipt policy hash {policy_hash} does not match {policy.canonical_hash}",
            )
        )
    if policy_hash and policy_hash != context.expected_policy_hash:
        findings.append(
            _finding(
                "policy_context_mismatch",
                "receipt policy hash does not match the trusted Loop context",
            )
        )
    diff_hash = str(receipt.get("diff_hash") or "").strip()
    if diff_hash and not _SHA256_RE.fullmatch(diff_hash):
        findings.append(_finding("diff_hash_invalid", "diff_hash must be a full SHA-256 digest"))
    if diff_hash != context.expected_diff_hash:
        findings.append(
            _finding(
                "diff_hash_mismatch",
                "receipt diff hash does not match the trusted Loop context",
            )
        )
    generated_at = str(receipt.get("generated_at") or "").strip()
    if generated_at:
        try:
            timestamp = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            timestamp = None
        if timestamp is None or timestamp.tzinfo is None:
            findings.append(
                _finding(
                    "generated_at_invalid",
                    "generated_at must be an ISO-8601 timestamp with timezone",
                )
            )

    producer = str(receipt.get("producer_agent") or "").strip()
    auditor = str(receipt.get("audit_agent") or "").strip()
    if not producer:
        findings.append(_finding("producer_agent_missing", "producer_agent is required"))
    if not auditor:
        findings.append(_finding("audit_agent_missing", "audit_agent is required"))
    if producer and auditor and producer == auditor:
        findings.append(_finding("self_approval_forbidden", "producer and auditor must differ"))

    lanes = receipt.get("lanes")
    if not isinstance(lanes, Mapping):
        findings.append(_finding("lanes_missing", "lanes object is required"))
        lanes = {}

    for lane in policy.lanes:
        entry = lanes.get(lane)
        if not isinstance(entry, Mapping):
            findings.append(_finding("lane_missing", "required lane is missing", lane))
            continue
        status = str(entry.get("status") or "").strip().lower()
        if status in policy.reject_statuses:
            findings.append(
                _finding("lane_rejected_status", f"status {status!r} can never pass", lane)
            )
        elif status == "pass":
            findings.extend(
                _valid_evidence(
                    entry.get("evidence"),
                    lane=lane,
                    source_sha=source_sha,
                    receipt=receipt,
                    context=context,
                )
            )
        elif status == "not_applicable":
            justification = str(entry.get("justification") or "").strip()
            approved_by = entry.get("approved_by")
            if not justification:
                findings.append(
                    _finding("na_justification_missing", "NOT_APPLICABLE needs justification", lane)
                )
            if policy.na_requires_independent_approval and (
                not isinstance(approved_by, list)
                or not any(
                    isinstance(actor, str) and actor.strip() and actor.strip() != producer
                    for actor in approved_by
                )
            ):
                findings.append(
                    _finding(
                        "na_independent_approval_missing",
                        "NOT_APPLICABLE needs approval by an actor other than the producer",
                        lane,
                    )
                )
        elif status == "fail":
            findings.append(_finding("lane_failed", "quality lane failed", lane))
        elif status == "blocked":
            findings.append(_finding("lane_blocked", "quality lane is blocked", lane))
        else:
            findings.append(
                _finding(
                    "lane_status_invalid",
                    f"unsupported status {status or '<missing>'!r}",
                    lane,
                )
            )

    findings.extend(_coverage_findings(receipt, policy))
    if not context.trusted_by_loop:
        findings.append(
            _finding(
                "verification_context_untrusted",
                "standalone context is diagnostic; only Loop may authorize PASS",
            )
        )
    if findings:
        status = (
            "BLOCKED"
            if all(finding.reason_code in _BLOCKED_REASON_CODES for finding in findings)
            else "FAIL"
        )
        return GateVerdict(
            status=status,
            reason_code=findings[0].reason_code,
            findings=tuple(findings),
            source_sha=source_sha,
            policy_hash=policy_hash,
        )
    return GateVerdict(
        status="PASS",
        reason_code="quality_policy_satisfied",
        findings=(),
        source_sha=source_sha,
        policy_hash=policy_hash,
    )
