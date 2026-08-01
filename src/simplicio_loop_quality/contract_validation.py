"""Fail-closed semantic validation and Loop v2 projection for Quality contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


class ContractSemanticError(ValueError):
    """Raised when a Quality contract cannot be projected safely."""


def validate_contract_document(document: Any, *, now: datetime | None = None) -> list[str]:
    """Apply the packaged Draft 2020-12 schema and cross-object semantics."""

    resource = resources.files("simplicio_loop_quality.contracts").joinpath(
        "quality-contracts-v1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [
        f"${''.join(f'[{part!r}]' for part in error.path)}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    ]
    if not errors:
        errors.extend(validate_contract_semantics(document, now=now))
    return errors


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _check_bound_item(item: Any, identity: Any, path: str, errors: list[str]) -> None:
    if not isinstance(item, Mapping):
        errors.append(f"{path}: expected object")
        return
    if item.get("identity") != identity:
        errors.append(f"{path}.identity: stale binding")


def _check_waiver(waiver: Any, identity: Any, path: str, errors: list[str], now: datetime) -> None:
    _check_bound_item(waiver, identity, path, errors)
    if not isinstance(waiver, Mapping) or not isinstance(identity, Mapping):
        return
    if waiver.get("requested_by") == waiver.get("approved_by"):
        errors.append(f"{path}: independent approval required")
    if waiver.get("policy_hash") != identity.get("policy_hash"):
        errors.append(f"{path}.policy_hash: policy mismatch")
    expiry = _timestamp(waiver.get("expires_at"))
    if expiry is None:
        errors.append(f"{path}.expires_at: invalid timestamp")
    elif expiry <= now:
        errors.append(f"{path}.expires_at: expired")


def validate_contract_semantics(document: Any, *, now: datetime | None = None) -> list[str]:
    """Return cross-object/status errors not expressible in portable JSON Schema."""

    if not isinstance(document, Mapping):
        return ["$: expected object"]
    identity = document.get("identity")
    schema = document.get("schema")
    errors: list[str] = []
    now = now or datetime.now(timezone.utc)

    if schema == "simplicio.quality-evidence/v2":
        if _timestamp(document.get("generated_at")) is None:
            errors.append("$.generated_at: invalid timestamp")
        if document.get("producer_agent") == document.get("audit_agent"):
            errors.append("$: audit agent must be independent")
        evidence_refs: set[str] = set()
        lanes = document.get("lanes", {})
        for lane_name, lane in lanes.items() if isinstance(lanes, Mapping) else ():
            path = f"$.lanes.{lane_name}"
            if not isinstance(lane, Mapping):
                continue
            evidence = lane.get("evidence", [])
            for index, item in enumerate(evidence if isinstance(evidence, list) else []):
                _check_bound_item(item, identity, f"{path}.evidence[{index}]", errors)
                if isinstance(item, Mapping):
                    evidence_refs.add(str(item.get("ref")))
                    if _timestamp(item.get("generated_at")) is None:
                        errors.append(f"{path}.evidence[{index}].generated_at: invalid timestamp")
                    if item.get("producer_agent") == item.get("audit_agent"):
                        errors.append(f"{path}.evidence[{index}]: auditor must be independent")
            status = lane.get("status")
            waiver = lane.get("waiver")
            if status == "PASS" and not evidence:
                errors.append(f"{path}: PASS requires evidence")
            if status == "NOT_APPLICABLE":
                if waiver is None:
                    errors.append(f"{path}: NOT_APPLICABLE requires waiver")
                else:
                    _check_waiver(waiver, identity, f"{path}.waiver", errors, now)
            elif waiver is not None:
                errors.append(f"{path}.waiver: allowed only for NOT_APPLICABLE")
        finding_ids: set[str] = set()
        for index, finding in enumerate(document.get("findings", [])):
            _check_bound_item(finding, identity, f"$.findings[{index}]", errors)
            if isinstance(finding, Mapping):
                finding_ids.add(str(finding.get("finding_id")))
                for ref in finding.get("evidence_refs", []):
                    if ref not in evidence_refs:
                        errors.append(f"$.findings[{index}].evidence_refs: unknown evidence {ref}")
        for lane_name, lane in lanes.items() if isinstance(lanes, Mapping) else ():
            if isinstance(lane, Mapping):
                for finding_id in lane.get("finding_ids", []):
                    if finding_id not in finding_ids:
                        errors.append(
                            f"$.lanes.{lane_name}.finding_ids: unknown finding {finding_id}"
                        )

    elif schema == "simplicio.quality-stage-result/v1":
        evidence = document.get("evidence", [])
        evidence_refs: set[str] = set()
        for index, item in enumerate(evidence if isinstance(evidence, list) else []):
            _check_bound_item(item, identity, f"$.evidence[{index}]", errors)
            if isinstance(item, Mapping):
                evidence_refs.add(str(item.get("ref")))
                if item.get("producer_agent") == item.get("audit_agent"):
                    errors.append(f"$.evidence[{index}]: auditor must be independent")
        for index, finding in enumerate(document.get("findings", [])):
            _check_bound_item(finding, identity, f"$.findings[{index}]", errors)
            if isinstance(finding, Mapping):
                for ref in finding.get("evidence_refs", []):
                    if ref not in evidence_refs:
                        errors.append(f"$.findings[{index}].evidence_refs: unknown evidence {ref}")
        if document.get("status") == "PASS":
            if not evidence:
                errors.append("$: PASS requires evidence")
            if document.get("exit_code") != 0:
                errors.append("$.exit_code: PASS requires zero")
        waiver = document.get("waiver")
        if document.get("status") == "NOT_APPLICABLE":
            if waiver is None:
                errors.append("$: NOT_APPLICABLE requires waiver")
            else:
                _check_waiver(waiver, identity, "$.waiver", errors, now)
        elif waiver is not None:
            errors.append("$.waiver: allowed only for NOT_APPLICABLE")
        started = _timestamp(document.get("started_at"))
        completed = _timestamp(document.get("completed_at"))
        if started and completed and completed < started:
            errors.append("$.completed_at: precedes started_at")

    elif schema == "simplicio.quality-finding/v1":
        _check_bound_item(
            document.get("finding"),
            document.get("finding", {}).get("identity"),
            "$.finding",
            errors,
        )
    elif schema == "simplicio.quality-waiver/v1":
        waiver = document.get("waiver")
        waiver_identity = waiver.get("identity") if isinstance(waiver, Mapping) else None
        _check_waiver(waiver, waiver_identity, "$.waiver", errors, now)
    elif schema == "simplicio.quality-gate-verdict/v2":
        for index, finding in enumerate(document.get("findings", [])):
            _check_bound_item(finding, identity, f"$.findings[{index}]", errors)
        if document.get("status") == "PASS" and not document.get("ready"):
            errors.append("$.ready: PASS requires true")
        if document.get("status") != "PASS" and document.get("ready"):
            errors.append("$.ready: non-PASS verdict cannot be ready")
    return errors


_LANE_MAP = {
    "unit": "unit_component",
    "integration": "integration_contract",
    "system": "system_e2e",
    "regression": "regression_smoke_artifact",
    "benchmark": "performance_load_stress_soak",
}


def project_report_to_loop_v2(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project a validated report into the installed Loop-owned terminal contract."""

    if not isinstance(report, Mapping) or report.get("schema") != "simplicio.quality-evidence/v2":
        raise ContractSemanticError("expected simplicio.quality-evidence/v2")
    errors = validate_contract_document(report)
    if errors:
        raise ContractSemanticError("; ".join(errors))
    from simplicio_loop import quality_matrix_v2

    source_identity = report["identity"]
    identity = {
        "run_id": source_identity["run_id"],
        "task_id": source_identity["task_id"],
        "attempt_id": source_identity["attempt_id"],
        "head_sha": source_identity["source_sha"],
        "tree_hash": source_identity["tree_hash"],
        "diff_hash": source_identity["diff_hash"],
        "policy_hash": source_identity["policy_hash"],
        "config_hash": source_identity["config_hash"],
        "produced_at": report["generated_at"],
    }
    lanes = {
        name: {
            "status": "BLOCKED",
            "reason_code": "not_reported_by_quality_extension",
            "evidence": [],
            "metrics": [],
        }
        for name in quality_matrix_v2.LANES
    }
    for source_name, source_lane in report["lanes"].items():
        target_name = _LANE_MAP.get(source_name, source_name)
        if target_name not in lanes:
            raise ContractSemanticError(f"unknown Loop v2 lane: {source_name}")
        evidence = [
            {
                "uri": item["ref"],
                "sha256": item["sha256"],
                "run_id": item["identity"]["run_id"],
                "attempt_id": item["identity"]["attempt_id"],
                "head_sha": item["identity"]["source_sha"],
                "author": item["producer_agent"],
                "auditor": item["audit_agent"],
            }
            for item in source_lane["evidence"]
        ]
        metrics = [
            {
                "name": metric["name"],
                "value": metric["value"],
                "unit": metric["unit"],
                "sample_count": metric["samples"],
                "source": metric["source"],
                "reason_code": metric["unavailable_reason"],
            }
            for metric in source_lane["metrics"]
        ]
        projected = {
            "status": source_lane["status"],
            "reason_code": source_lane["reason_code"],
            "evidence": evidence,
            "metrics": metrics,
        }
        waiver = source_lane.get("waiver")
        if waiver is not None:
            projected["waiver"] = {
                "scope": waiver["scope"],
                "justification": waiver["justification"],
                "approver": waiver["approved_by"],
                "expires_at": waiver["expires_at"],
                "policy_hash": waiver["policy_hash"],
            }
        lanes[target_name] = projected
    projection = {"schema": quality_matrix_v2.SCHEMA, "identity": identity, "lanes": lanes}
    core_errors = quality_matrix_v2.validate_v2(projection)
    if core_errors:
        raise ContractSemanticError("; ".join(core_errors))
    return projection
