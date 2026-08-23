"""Project hermetic requirements into a Loop-owned stage request."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

SCHEMA = "simplicio.quality-hermetic-binding/v1"


def build_hub_environment_request(plan: Mapping[str, Any], *, identity: Mapping[str, Any], stage_id: str) -> dict[str, Any]:
    """Build data for Hub submission; never provisions or starts services locally."""

    request = {
        "schema": SCHEMA,
        "identity": dict(identity),
        "stage_id": stage_id,
        "services": list(plan.get("services", ())),
        "ports": list(plan.get("ports", ())),
        "filesystem": list(plan.get("filesystem", ())),
        "network": plan.get("network", "none"),
        "credentials": list(plan.get("credentials", ())),
        "seed": plan.get("seed"),
        "cleanup_required": True,
        "executor": "simplicio-loop-hub",
    }
    return {**request, "request_hash": hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def validate_cleanup_receipt(receipt: Mapping[str, Any]) -> tuple[str, ...]:
    reasons = []
    if receipt.get("executor") != "simplicio-loop-hub":
        reasons.append("CLEANUP_EXECUTOR_INVALID")
    if receipt.get("status") != "PASS":
        reasons.append("CLEANUP_NOT_VERIFIED")
    if not receipt.get("released_resources"):
        reasons.append("RELEASE_EVIDENCE_MISSING")
    return tuple(sorted(reasons))


__all__ = ["SCHEMA", "build_hub_environment_request", "validate_cleanup_receipt"]
