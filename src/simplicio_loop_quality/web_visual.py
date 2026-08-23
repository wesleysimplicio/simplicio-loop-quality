"""Web/UI visual-regression scenario planning."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

SCHEMA = "simplicio.quality-web-visual/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def plan_web_visual(request: Mapping[str, Any]) -> dict[str, Any]:
    routes = tuple(sorted(str(x) for x in request.get("routes", ())))
    viewports = tuple(sorted(str(x) for x in request.get("viewports", ("desktop", "mobile"))))
    reasons = []
    if not routes:
        reasons.append("ROUTES_MISSING")
    if not viewports:
        reasons.append("VIEWPORTS_MISSING")
    scenarios = tuple((route, viewport) for route in routes for viewport in viewports)
    payload = {"routes": routes, "viewports": viewports, "scenarios": scenarios}
    return {"schema": SCHEMA, "status": "PLANNED" if not reasons else "BLOCKED", "routes": routes, "viewports": viewports, "scenarios": scenarios, "reason_codes": reasons, "plan_id": _hash(payload)}


def normalize_visual_result(result: Mapping[str, Any], *, expected_plan_id: str) -> dict[str, Any]:
    reasons = []
    if result.get("plan_id") != expected_plan_id:
        reasons.append("PLAN_STALE")
    if not result.get("screenshot_refs"):
        reasons.append("SCREENSHOT_EVIDENCE_MISSING")
    if result.get("pixel_diffs"):
        reasons.append("VISUAL_DIFF")
    status = str(result.get("status", "BLOCKED")).upper()
    if reasons:
        status = "BLOCKED" if "SCREENSHOT_EVIDENCE_MISSING" in reasons else "FAIL"
    return {"schema": SCHEMA, "status": status, "reason_codes": reasons}


__all__ = ["SCHEMA", "normalize_visual_result", "plan_web_visual"]
