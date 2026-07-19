"""Versioned quality policy loading and validation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any


class PolicyError(ValueError):
    """Raised when a quality policy is ambiguous or unsafe."""


@dataclass(frozen=True)
class CoverageThresholds:
    global_min_pct: float
    changed_min_pct: float
    critical_min_pct: float

    def __post_init__(self) -> None:
        for name, value in (
            ("global_min_pct", self.global_min_pct),
            ("changed_min_pct", self.changed_min_pct),
            ("critical_min_pct", self.critical_min_pct),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PolicyError(f"coverage.{name} must be numeric")
            if not 0 <= float(value) <= 100:
                raise PolicyError(f"coverage.{name} must be between 0 and 100")


@dataclass(frozen=True)
class QualityPolicy:
    schema: str
    policy_id: str
    lanes: tuple[str, ...]
    coverage: CoverageThresholds
    reject_statuses: frozenset[str]
    na_requires_independent_approval: bool = True

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> QualityPolicy:
        allowed = {
            "schema",
            "policy_id",
            "coverage",
            "na_requires_independent_approval",
            "reject_statuses",
            "lanes",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise PolicyError("unknown policy fields: " + ", ".join(unknown))
        if payload.get("schema") != "simplicio.quality-policy/v1":
            raise PolicyError("policy schema must be simplicio.quality-policy/v1")
        policy_id = str(payload.get("policy_id") or "").strip()
        if not policy_id:
            raise PolicyError("policy_id is required")
        raw_lanes = payload.get("lanes")
        if not isinstance(raw_lanes, list) or not raw_lanes:
            raise PolicyError("lanes must be a non-empty array")
        lanes = tuple(str(lane).strip() for lane in raw_lanes)
        if any(not lane for lane in lanes) or len(lanes) != len(set(lanes)):
            raise PolicyError("lanes must be unique non-empty strings")
        coverage = payload.get("coverage")
        if not isinstance(coverage, Mapping):
            raise PolicyError("coverage must be an object")
        coverage_allowed = {"global_min_pct", "changed_min_pct", "critical_min_pct"}
        coverage_unknown = sorted(set(coverage) - coverage_allowed)
        if coverage_unknown:
            raise PolicyError("unknown coverage fields: " + ", ".join(coverage_unknown))
        missing = sorted(coverage_allowed - set(coverage))
        if missing:
            raise PolicyError("missing coverage fields: " + ", ".join(missing))
        thresholds = CoverageThresholds(
            global_min_pct=coverage["global_min_pct"],
            changed_min_pct=coverage["changed_min_pct"],
            critical_min_pct=coverage["critical_min_pct"],
        )
        reject = payload.get("reject_statuses")
        if not isinstance(reject, list) or not all(
            isinstance(item, str) and item for item in reject
        ):
            raise PolicyError("reject_statuses must be an array of non-empty strings")
        approval = payload.get("na_requires_independent_approval", True)
        if not isinstance(approval, bool):
            raise PolicyError("na_requires_independent_approval must be boolean")
        return cls(
            schema=str(payload["schema"]),
            policy_id=policy_id,
            lanes=lanes,
            coverage=thresholds,
            reject_statuses=frozenset(item.lower() for item in reject),
            na_requires_independent_approval=approval,
        )

    @property
    def canonical_hash(self) -> str:
        raw = {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "lanes": list(self.lanes),
            "coverage": {
                "global_min_pct": self.coverage.global_min_pct,
                "changed_min_pct": self.coverage.changed_min_pct,
                "critical_min_pct": self.coverage.critical_min_pct,
            },
            "reject_statuses": sorted(self.reject_statuses),
            "na_requires_independent_approval": self.na_requires_independent_approval,
        }
        encoded = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def load_policy(path: str | Path) -> QualityPolicy:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise PolicyError("policy root must be an object")
    return QualityPolicy.from_mapping(payload)


def load_strict_policy() -> QualityPolicy:
    resource = resources.files("simplicio_loop_quality.contracts").joinpath("strict-default.json")
    payload = json.loads(resource.read_text(encoding="utf-8"))
    return QualityPolicy.from_mapping(payload)


def ensure_authoritative_policy(
    policy: QualityPolicy,
    baseline: QualityPolicy | None = None,
) -> QualityPolicy:
    """Reject any policy that weakens the mandatory production floor."""

    baseline = baseline or load_strict_policy()
    weaknesses: list[str] = []
    missing_lanes = sorted(set(baseline.lanes) - set(policy.lanes))
    if missing_lanes:
        weaknesses.append("missing lanes: " + ", ".join(missing_lanes))
    for field in ("global_min_pct", "changed_min_pct", "critical_min_pct"):
        actual = float(getattr(policy.coverage, field))
        required = float(getattr(baseline.coverage, field))
        if actual < required:
            weaknesses.append(f"coverage.{field}={actual:g} < {required:g}")
    if baseline.na_requires_independent_approval and not policy.na_requires_independent_approval:
        weaknesses.append("independent N/A approval is disabled")
    missing_rejections = sorted(baseline.reject_statuses - policy.reject_statuses)
    if missing_rejections:
        weaknesses.append("non-passing statuses accepted: " + ", ".join(missing_rejections))
    if weaknesses:
        raise PolicyError("authoritative policy weakens strict-default: " + "; ".join(weaknesses))
    return policy
