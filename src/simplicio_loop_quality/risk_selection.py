"""Deterministic, monotonic risk classification for quality-suite selection.

This module produces a plan for the Loop.  It never executes a lane, applies a
waiver, or schedules a retry.  Missing evidence increases uncertainty instead
of silently lowering the selected quality surface.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

SCHEMA = "simplicio.quality-risk-selection/v1"
LEVELS = ("low", "medium", "high", "critical")
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _tokens(value: Any) -> set[str]:
    if isinstance(value, str):
        return {item.lower() for item in _TOKEN_RE.findall(value)}
    if isinstance(value, Mapping):
        result: set[str] = set()
        for key, item in value.items():
            result |= _tokens(key)
            result |= _tokens(item)
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        result: set[str] = set()
        for item in value:
            result |= _tokens(item)
        return result
    return set()


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class RiskAssessment:
    category_scores: Mapping[str, float]
    level: str
    reasons: tuple[str, ...]
    unknown: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "category_scores": dict(sorted(self.category_scores.items())),
            "level": self.level,
            "reasons": list(self.reasons),
            "unknown": self.unknown,
        }


@dataclass(frozen=True)
class SuiteSelection:
    schema: str
    assessment: RiskAssessment
    mandatory_lanes: tuple[str, ...]
    budgets: Mapping[str, int | float]
    inputs_hash: str
    waiver_ids: tuple[str, ...] = ()

    @property
    def policy_level(self) -> str:
        return self.assessment.level

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "assessment": self.assessment.to_dict(),
            "mandatory_lanes": list(self.mandatory_lanes),
            "budgets": dict(sorted(self.budgets.items())),
            "inputs_hash": self.inputs_hash,
            "waiver_ids": list(self.waiver_ids),
        }


class RiskSelectionError(ValueError):
    """Raised when a risk selection input or exclusion is unsafe."""


_CATEGORY_LANES: dict[str, tuple[str, ...]] = {
    "api": ("contract", "integration", "compatibility"),
    "security": ("application_security", "supply_chain_security"),
    "data": ("integration", "migration", "regression"),
    "concurrency": ("concurrency", "fault_injection", "flaky_repeatability"),
    "performance": ("performance", "load_stress_soak"),
    "packaging": ("installation", "compatibility", "supply_chain_security"),
    "blast_radius": ("regression", "integration", "system"),
}


def assess_risk(impact: Mapping[str, Any]) -> RiskAssessment:
    """Score risk from explicit impact facts without guessing absent facts."""

    tokens = _tokens(impact)
    changed = impact.get("changed_files", ())
    impacted = impact.get("impacted_files", ())
    unknowns = impact.get("unknowns", ())
    changed_count = len(changed) if isinstance(changed, (list, tuple)) else 0
    impacted_count = len(impacted) if isinstance(impacted, (list, tuple)) else changed_count
    scores = {category: 0.0 for category in _CATEGORY_LANES}
    reasons: set[str] = set()

    patterns = {
        "api": {"api", "public", "endpoint", "route", "export", "contract", "schema"},
        "security": {"auth", "security", "secret", "token", "password", "crypto", "permission"},
        "data": {"db", "database", "sql", "migration", "schema", "storage", "delete"},
        "concurrency": {"async", "thread", "concurrent", "worker", "lock", "race", "queue"},
        "performance": {"perf", "performance", "benchmark", "latency", "hotpath", "load"},
        "packaging": {
            "package", "pyproject", "cargo", "docker", "container", "workflow", "release"
        },
    }
    for category, needles in patterns.items():
        matches = sorted(tokens & needles)
        if matches:
            scores[category] = min(1.0, 0.55 + 0.1 * len(matches))
            reasons.add(f"{category}:{','.join(matches)}")

    scores["blast_radius"] = min(1.0, 0.2 + 0.08 * max(0, impacted_count - 1))
    if changed_count >= 5:
        scores["blast_radius"] = max(scores["blast_radius"], 0.7)
        reasons.add("blast_radius:many_changed_files")
    if unknowns:
        scores["blast_radius"] = max(scores["blast_radius"], 0.75)
        reasons.add("blast_radius:unknown_facts")

    maximum = max(scores.values())
    if maximum >= 0.85 or scores["security"] >= 0.65:
        level = "critical"
    elif maximum >= 0.65:
        level = "high"
    elif maximum >= 0.4:
        level = "medium"
    else:
        level = "low"
    return RiskAssessment(scores, level, tuple(sorted(reasons)), bool(unknowns))


def _validate_waiver(waiver: Mapping[str, Any], *, lane: str, source_sha: str | None) -> str:
    waiver_id = str(waiver.get("waiver_id", ""))
    if not waiver_id or not str(waiver.get("justification", "")).strip():
        raise RiskSelectionError(f"waiver for {lane} requires an id and justification")
    if (
        not str(waiver.get("approver", "")).strip()
        or waiver.get("approver") == waiver.get("created_by")
    ):
        raise RiskSelectionError(f"waiver {waiver_id} requires an independent approver")
    scope = str(waiver.get("scope", ""))
    if not scope or scope in {"*", "**", "all", "global"}:
        raise RiskSelectionError(f"waiver {waiver_id} has an overbroad scope")
    expires = str(waiver.get("expires_at", ""))
    try:
        expiry = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RiskSelectionError(f"waiver {waiver_id} has an invalid expiry") from exc
    if expiry.tzinfo is None or expiry.astimezone(timezone.utc) <= datetime.now(timezone.utc):
        raise RiskSelectionError(f"waiver {waiver_id} is expired")
    if source_sha and waiver.get("source_sha") != source_sha:
        raise RiskSelectionError(f"waiver {waiver_id} is stale for the source SHA")
    return waiver_id


def select_quality_suites(
    impact: Mapping[str, Any],
    *,
    available_lanes: Iterable[str] = (),
    exclusions: Mapping[str, Mapping[str, Any]] | None = None,
    source_sha: str | None = None,
) -> SuiteSelection:
    """Select a monotonic lane set; every exclusion needs a scoped waiver."""

    assessment = assess_risk(impact)
    lanes = {"invariants", "evidence_audit"}
    for category, score in assessment.category_scores.items():
        if score >= 0.4:
            lanes.update(_CATEGORY_LANES.get(category, ()))
    available = set(available_lanes)
    if available:
        lanes &= available | {"invariants", "evidence_audit"}
    waivers: list[str] = []
    for lane, waiver in (exclusions or {}).items():
        if lane in lanes:
            waiver_id = _validate_waiver(waiver, lane=lane, source_sha=source_sha)
            lanes.remove(lane)
            waivers.append(waiver_id)
    if not lanes:
        raise RiskSelectionError("risk selection cannot exclude every mandatory lane")
    budgets = {
        "max_attempts": 1,
        "max_duration_ms": {
            "low": 30_000, "medium": 60_000, "high": 120_000, "critical": 300_000
        }[assessment.level],
        "max_parallelism": 1 if assessment.level == "critical" else 4,
    }
    inputs = {
        "impact": impact,
        "available_lanes": sorted(available),
        "exclusions": exclusions or {},
    }
    return SuiteSelection(
        SCHEMA,
        assessment,
        tuple(sorted(lanes)),
        budgets,
        _digest(inputs),
        tuple(sorted(waivers)),
    )


def is_monotonic(base: SuiteSelection, expanded: SuiteSelection) -> bool:
    """Return whether adding impact can only preserve or increase assurance."""

    return set(base.mandatory_lanes).issubset(expanded.mandatory_lanes) and LEVELS.index(
        base.policy_level
    ) <= LEVELS.index(expanded.policy_level)


__all__ = [
    "RiskAssessment",
    "RiskSelectionError",
    "SuiteSelection",
    "assess_risk",
    "is_monotonic",
    "select_quality_suites",
]
