"""Container-image/Kubernetes quality profile planning."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

SCHEMA = "simplicio.quality-container-profile/v1"


def plan_container_profile(
    files: list[str], *, image: str | None = None
) -> dict[str, Any]:
    manifests = tuple(
        sorted(path for path in files if path.endswith(("Dockerfile", ".yaml", ".yml")))
    )
    reasons = []
    if not image:
        reasons.append("IMAGE_REFERENCE_MISSING")
    if not manifests:
        reasons.append("CONTAINER_MANIFEST_MISSING")
    checks = ("image_digest", "nonroot", "secret_leak", "healthcheck", "kubernetes_schema")
    payload = {"image": image, "manifests": manifests, "checks": checks}
    plan_id = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema": SCHEMA,
        "status": "PLANNED" if not reasons else "BLOCKED",
        "image": image,
        "manifests": manifests,
        "checks": checks,
        "reason_codes": reasons,
        "plan_id": plan_id,
    }


def normalize_container_result(result: Mapping[str, Any], *, expected_plan_id: str) -> dict[str, Any]:
    reasons = []
    if result.get("plan_id") != expected_plan_id:
        reasons.append("PLAN_STALE")
    if not result.get("image_digest"):
        reasons.append("IMAGE_DIGEST_MISSING")
    status = str(result.get("status", "BLOCKED")).upper()
    if reasons:
        status = "BLOCKED"
    return {"schema": SCHEMA, "status": status, "reason_codes": reasons}


__all__ = ["SCHEMA", "normalize_container_result", "plan_container_profile"]
