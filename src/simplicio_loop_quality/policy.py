"""Versioned, monotonic quality policy parsing and resolution."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from importlib import resources
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "simplicio.quality-policy/v1"
RESOLUTION_SCHEMA = "simplicio.quality-policy-resolution/v1"
RISK_LEVELS = ("low", "medium", "high", "critical")


class PolicyError(ValueError):
    """Raised when a quality policy is ambiguous or unsafe."""


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _strings(value: Any, field: str, *, nonempty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (nonempty and not value):
        raise PolicyError(f"{field} must be {'a non-empty' if nonempty else 'an'} array")
    if not all(isinstance(item, str) and item.strip() == item and item for item in value):
        raise PolicyError(f"{field} must contain non-empty strings without surrounding space")
    if len(value) != len(set(value)):
        raise PolicyError(f"{field} must not contain duplicates")
    return tuple(value)


def _number(value: Any, field: str, *, minimum: float, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PolicyError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise PolicyError(f"{field} must be finite")
    if result < minimum or (maximum is not None and result > maximum):
        suffix = f" and {maximum:g}" if maximum is not None else ""
        raise PolicyError(f"{field} must be between {minimum:g}{suffix}")
    return result


@dataclass(frozen=True)
class CoverageThresholds:
    global_min_pct: float
    changed_min_pct: float
    critical_min_pct: float

    def __post_init__(self) -> None:
        for name in ("global_min_pct", "changed_min_pct", "critical_min_pct"):
            _number(getattr(self, name), f"coverage.{name}", minimum=0, maximum=100)

    def to_dict(self) -> dict[str, float]:
        return {
            name: float(getattr(self, name))
            for name in ("global_min_pct", "changed_min_pct", "critical_min_pct")
        }


@dataclass(frozen=True)
class PerformanceBudget:
    max_duration_ms: float
    max_peak_memory_mb: float

    def __post_init__(self) -> None:
        _number(self.max_duration_ms, "performance.max_duration_ms", minimum=1)
        _number(self.max_peak_memory_mb, "performance.max_peak_memory_mb", minimum=1)

    def to_dict(self) -> dict[str, float]:
        return {
            "max_duration_ms": float(self.max_duration_ms),
            "max_peak_memory_mb": float(self.max_peak_memory_mb),
        }


@dataclass(frozen=True)
class RiskPolicy:
    level: str
    mandatory_lanes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.level not in RISK_LEVELS:
            raise PolicyError("risk.level must be one of: " + ", ".join(RISK_LEVELS))
        if len(self.mandatory_lanes) != len(set(self.mandatory_lanes)) or any(
            not isinstance(lane, str) or not lane for lane in self.mandatory_lanes
        ):
            raise PolicyError("risk.mandatory_lanes must be unique non-empty strings")
        if self.level == "critical" and not self.mandatory_lanes:
            raise PolicyError("critical risk requires mandatory lanes")

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level, "mandatory_lanes": list(self.mandatory_lanes)}


@dataclass(frozen=True)
class QualityPolicy:
    schema: str
    policy_id: str
    lanes: tuple[str, ...]
    coverage: CoverageThresholds
    performance: PerformanceBudget
    risk: RiskPolicy
    reject_statuses: frozenset[str]
    na_requires_independent_approval: bool = True

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> QualityPolicy:
        allowed = {
            "schema",
            "policy_id",
            "coverage",
            "performance",
            "risk",
            "na_requires_independent_approval",
            "reject_statuses",
            "lanes",
        }
        unknown = sorted(set(payload) - allowed)
        missing = sorted(allowed - set(payload))
        if unknown:
            raise PolicyError("unknown policy fields: " + ", ".join(unknown))
        if missing:
            raise PolicyError("missing policy fields: " + ", ".join(missing))
        if payload.get("schema") != POLICY_SCHEMA:
            raise PolicyError(f"policy schema must be {POLICY_SCHEMA}")
        policy_id = payload.get("policy_id")
        if not isinstance(policy_id, str) or not policy_id or policy_id.strip() != policy_id:
            raise PolicyError("policy_id must be a non-empty string without surrounding space")
        lanes = _strings(payload.get("lanes"), "lanes")
        coverage = payload.get("coverage")
        if not isinstance(coverage, Mapping):
            raise PolicyError("coverage must be an object")
        coverage_fields = {"global_min_pct", "changed_min_pct", "critical_min_pct"}
        if set(coverage) != coverage_fields:
            raise PolicyError(
                "coverage must contain exactly: " + ", ".join(sorted(coverage_fields))
            )
        thresholds = CoverageThresholds(**{name: coverage[name] for name in coverage_fields})
        performance = payload.get("performance")
        if not isinstance(performance, Mapping) or set(performance) != {
            "max_duration_ms",
            "max_peak_memory_mb",
        }:
            raise PolicyError("performance must contain max_duration_ms and max_peak_memory_mb")
        budget = PerformanceBudget(
            max_duration_ms=performance["max_duration_ms"],
            max_peak_memory_mb=performance["max_peak_memory_mb"],
        )
        risk = payload.get("risk")
        if not isinstance(risk, Mapping) or set(risk) != {"level", "mandatory_lanes"}:
            raise PolicyError("risk must contain level and mandatory_lanes")
        risk_policy = RiskPolicy(
            level=risk["level"],
            mandatory_lanes=_strings(
                risk["mandatory_lanes"], "risk.mandatory_lanes", nonempty=False
            ),
        )
        missing_risk_lanes = sorted(set(risk_policy.mandatory_lanes) - set(lanes))
        if missing_risk_lanes:
            raise PolicyError(
                "risk mandatory lanes missing from lanes: " + ", ".join(missing_risk_lanes)
            )
        reject = _strings(payload.get("reject_statuses"), "reject_statuses")
        normalized_reject = tuple(item.lower() for item in reject)
        if len(normalized_reject) != len(set(normalized_reject)):
            raise PolicyError("reject_statuses must not contain case-insensitive duplicates")
        approval = payload.get("na_requires_independent_approval")
        if not isinstance(approval, bool):
            raise PolicyError("na_requires_independent_approval must be boolean")
        return cls(
            schema=POLICY_SCHEMA,
            policy_id=policy_id,
            lanes=lanes,
            coverage=thresholds,
            performance=budget,
            risk=risk_policy,
            reject_statuses=frozenset(normalized_reject),
            na_requires_independent_approval=approval,
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "lanes": list(self.lanes),
            "coverage": self.coverage.to_dict(),
            "performance": self.performance.to_dict(),
            "risk": self.risk.to_dict(),
            "reject_statuses": sorted(self.reject_statuses),
            "na_requires_independent_approval": self.na_requires_independent_approval,
        }

    @property
    def canonical_hash(self) -> str:
        return _digest(self.to_mapping())


@dataclass(frozen=True)
class PolicySource:
    layer: str
    digest: str


@dataclass(frozen=True)
class PolicyResolution:
    policy: QualityPolicy
    sources: tuple[PolicySource, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": RESOLUTION_SCHEMA,
            "policy": self.policy.to_mapping(),
            "policy_hash": self.policy.canonical_hash,
            "sources": [source.__dict__ for source in self.sources],
        }


def _layer_mapping(value: QualityPolicy | Mapping[str, Any]) -> Mapping[str, Any]:
    return value.to_mapping() if isinstance(value, QualityPolicy) else value


def _merge(current: QualityPolicy, raw: Mapping[str, Any], layer: str) -> QualityPolicy:
    allowed = {
        "schema",
        "policy_id",
        "coverage",
        "performance",
        "risk",
        "na_requires_independent_approval",
        "reject_statuses",
        "lanes",
    }
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise PolicyError(f"{layer} has unknown policy fields: " + ", ".join(unknown))
    if "schema" in raw and raw["schema"] != POLICY_SCHEMA:
        raise PolicyError(f"{layer} policy schema must be {POLICY_SCHEMA}")
    result = current
    if "policy_id" in raw:
        value = raw["policy_id"]
        if not isinstance(value, str) or not value or value.strip() != value:
            raise PolicyError(f"{layer}.policy_id must be a non-empty string")
        result = replace(result, policy_id=value)
    if "lanes" in raw:
        lanes = _strings(raw["lanes"], f"{layer}.lanes")
        missing = sorted(set(result.lanes) - set(lanes))
        if missing:
            raise PolicyError(f"{layer} cannot remove lanes: " + ", ".join(missing))
        result = replace(result, lanes=lanes)
    if "coverage" in raw:
        values = raw["coverage"]
        if not isinstance(values, Mapping):
            raise PolicyError(f"{layer}.coverage must be an object")
        unknown_coverage = set(values) - set(current.coverage.to_dict())
        if unknown_coverage:
            raise PolicyError(
                f"{layer} has unknown coverage fields: " + ", ".join(sorted(unknown_coverage))
            )
        merged = current.coverage.to_dict()
        for name, value in values.items():
            checked = _number(value, f"{layer}.coverage.{name}", minimum=0, maximum=100)
            if checked < merged[name]:
                raise PolicyError(f"{layer} cannot lower coverage.{name}")
            merged[name] = checked
        result = replace(result, coverage=CoverageThresholds(**merged))
    if "performance" in raw:
        values = raw["performance"]
        if not isinstance(values, Mapping):
            raise PolicyError(f"{layer}.performance must be an object")
        merged = current.performance.to_dict()
        unknown_budget = set(values) - set(merged)
        if unknown_budget:
            raise PolicyError(
                f"{layer} has unknown performance fields: " + ", ".join(sorted(unknown_budget))
            )
        for name, value in values.items():
            checked = _number(value, f"{layer}.performance.{name}", minimum=1)
            if checked > merged[name]:
                raise PolicyError(f"{layer} cannot loosen performance.{name}")
            merged[name] = checked
        result = replace(result, performance=PerformanceBudget(**merged))
    if "risk" in raw:
        values = raw["risk"]
        if not isinstance(values, Mapping) or set(values) - {"level", "mandatory_lanes"}:
            raise PolicyError(f"{layer}.risk has invalid fields")
        level = values.get("level", result.risk.level)
        if level not in RISK_LEVELS or RISK_LEVELS.index(level) < RISK_LEVELS.index(
            result.risk.level
        ):
            raise PolicyError(f"{layer} cannot lower risk level")
        lanes = (
            _strings(values["mandatory_lanes"], f"{layer}.risk.mandatory_lanes", nonempty=False)
            if "mandatory_lanes" in values
            else result.risk.mandatory_lanes
        )
        missing = sorted(set(result.risk.mandatory_lanes) - set(lanes))
        if missing:
            raise PolicyError(f"{layer} cannot remove risk mandatory lanes: " + ", ".join(missing))
        if set(lanes) - set(result.lanes):
            raise PolicyError(f"{layer} risk mandatory lanes must also be policy lanes")
        if level == "critical":
            if not lanes:
                raise PolicyError(f"{layer} critical risk requires mandatory lanes")
            if result.risk.level != "critical" and set(lanes) == set(result.risk.mandatory_lanes):
                raise PolicyError(f"{layer} critical risk must add at least one mandatory lane")
        result = replace(result, risk=RiskPolicy(level, lanes))
    if "reject_statuses" in raw:
        raw_reject = _strings(raw["reject_statuses"], f"{layer}.reject_statuses")
        normalized_reject = tuple(item.lower() for item in raw_reject)
        if len(normalized_reject) != len(set(normalized_reject)):
            raise PolicyError(
                f"{layer}.reject_statuses must not contain case-insensitive duplicates"
            )
        reject = frozenset(normalized_reject)
        missing = sorted(result.reject_statuses - reject)
        if missing:
            raise PolicyError(f"{layer} cannot accept statuses: " + ", ".join(missing))
        result = replace(result, reject_statuses=reject)
    if "na_requires_independent_approval" in raw:
        approval = raw["na_requires_independent_approval"]
        if not isinstance(approval, bool):
            raise PolicyError(f"{layer}.na_requires_independent_approval must be boolean")
        if result.na_requires_independent_approval and not approval:
            raise PolicyError(f"{layer} cannot disable independent N/A approval")
        result = replace(result, na_requires_independent_approval=approval)
    return ensure_authoritative_policy(result)


def resolve_policy(
    *,
    global_policy: QualityPolicy | Mapping[str, Any] | None = None,
    project_policy: QualityPolicy | Mapping[str, Any] | None = None,
    cli_policy: QualityPolicy | Mapping[str, Any] | None = None,
    baseline: QualityPolicy | None = None,
) -> PolicyResolution:
    result = ensure_authoritative_policy(baseline) if baseline else load_strict_policy()
    sources = [PolicySource("strict-default", result.canonical_hash)]
    for layer, value in (
        ("global", global_policy),
        ("project", project_policy),
        ("cli", cli_policy),
    ):
        if value is None:
            continue
        raw = _layer_mapping(value)
        if not isinstance(raw, Mapping):
            raise PolicyError(f"{layer} policy must be an object")
        result = _merge(result, raw, layer)
        sources.append(PolicySource(layer, _digest(raw)))
    return PolicyResolution(result, tuple(sources))


def load_policy_mapping(path: str | Path) -> Mapping[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise PolicyError("policy root must be an object")
    return payload


def load_policy(path: str | Path) -> QualityPolicy:
    return QualityPolicy.from_mapping(load_policy_mapping(path))


def load_strict_policy() -> QualityPolicy:
    resource = resources.files("simplicio_loop_quality.contracts").joinpath("strict-default.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    return QualityPolicy.from_mapping(payload)


def ensure_authoritative_policy(
    policy: QualityPolicy, baseline: QualityPolicy | None = None
) -> QualityPolicy:
    baseline = baseline or load_strict_policy()
    weaknesses = []
    if set(baseline.lanes) - set(policy.lanes):
        weaknesses.append("mandatory lanes removed")
    for name, required in baseline.coverage.to_dict().items():
        if policy.coverage.to_dict()[name] < required:
            weaknesses.append(f"coverage.{name} lowered")
    for name, required in baseline.performance.to_dict().items():
        if policy.performance.to_dict()[name] > required:
            weaknesses.append(f"performance.{name} loosened")
    if RISK_LEVELS.index(policy.risk.level) < RISK_LEVELS.index(baseline.risk.level):
        weaknesses.append("risk level lowered")
    if set(baseline.risk.mandatory_lanes) - set(policy.risk.mandatory_lanes):
        weaknesses.append("risk mandatory lanes removed")
    if baseline.reject_statuses - policy.reject_statuses:
        weaknesses.append("non-passing statuses accepted")
    if baseline.na_requires_independent_approval and not policy.na_requires_independent_approval:
        weaknesses.append("independent N/A approval disabled")
    if weaknesses:
        raise PolicyError("authoritative policy weakens strict-default: " + "; ".join(weaknesses))
    return policy
