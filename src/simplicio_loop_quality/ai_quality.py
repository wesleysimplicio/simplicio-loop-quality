"""AI/LLM quality profile planning with deterministic safety checks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-ai-profile/v1"


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class AIQualityPlan:
    status: str
    checks: tuple[str, ...]
    model_id: str | None
    seed: int | None
    temperature: float | None
    blocked_reasons: tuple[str, ...]
    plan_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, **self.__dict__}


def plan_ai_quality(request: Mapping[str, Any]) -> AIQualityPlan:
    reasons: set[str] = set()
    model = str(request.get("model_id", "")).strip() or None
    checks = tuple(sorted(str(item) for item in request.get("checks", ())))
    seed = request.get("seed")
    temperature = request.get("temperature")
    if not model:
        reasons.add("MODEL_ID_MISSING")
    if isinstance(seed, bool) or not isinstance(seed, int):
        reasons.add("SEED_REQUIRED")
    if temperature is not None and (isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not 0 <= temperature <= 1):
        reasons.add("TEMPERATURE_INVALID")
    if not checks:
        reasons.add("AI_CHECKS_EMPTY")
    payload = {"model_id": model, "checks": checks, "seed": seed, "temperature": temperature, "reasons": sorted(reasons)}
    return AIQualityPlan("PLANNED" if not reasons else "BLOCKED", checks, model, seed if isinstance(seed, int) and not isinstance(seed, bool) else None, float(temperature) if isinstance(temperature, (int, float)) and not isinstance(temperature, bool) else None, tuple(sorted(reasons)), _hash(payload))


def normalize_ai_result(result: Mapping[str, Any], *, expected_plan_id: str) -> dict[str, Any]:
    reasons: list[str] = []
    if result.get("plan_id") != expected_plan_id:
        reasons.append("PLAN_STALE")
    if not result.get("evidence_refs"):
        reasons.append("EVIDENCE_MISSING")
    status = str(result.get("status", "BLOCKED")).upper()
    if status not in {"PASS", "FAIL", "BLOCKED"}:
        reasons.append("STATUS_INVALID")
        status = "BLOCKED"
    if reasons:
        status = "BLOCKED"
    return {"schema": SCHEMA, "status": status, "plan_id": result.get("plan_id"), "findings": list(result.get("findings", ())), "evidence_refs": list(result.get("evidence_refs", ())), "reason_codes": sorted(set(reasons))}


class AIQualityProfile:
    def plan(self, request: Mapping[str, Any]) -> AIQualityPlan:
        return plan_ai_quality(request)


__all__ = ["AIQualityPlan", "AIQualityProfile", "SCHEMA", "normalize_ai_result", "plan_ai_quality"]
