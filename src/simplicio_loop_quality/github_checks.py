"""CI-neutral GitHub Check/annotation payload projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

SCHEMA = "simplicio.quality-github-checks/v1"


@dataclass(frozen=True)
class CheckProjection:
    conclusion: str
    title: str
    summary: str
    annotations: tuple[Mapping[str, Any], ...]
    issue_action: str

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "conclusion": self.conclusion, "title": self.title, "summary": self.summary, "annotations": [dict(x) for x in self.annotations], "issue_action": self.issue_action}


def project_check(verdict: Mapping[str, Any]) -> CheckProjection:
    status = str(verdict.get("status", "BLOCKED")).upper()
    conclusion = {"PASS": "success", "FAIL": "failure", "BLOCKED": "neutral"}.get(status, "neutral")
    findings = verdict.get("findings", verdict.get("reason_codes", ()))
    annotations = tuple({"path": str(item.get("path", "")), "message": str(item.get("detail", item.get("message", item))), "level": "failure" if status == "FAIL" else "warning"} if isinstance(item, Mapping) else {"path": "", "message": str(item), "level": "warning"} for item in findings)
    action = "close" if status == "PASS" else "keep-open"
    return CheckProjection(conclusion, "Simplicio Quality", f"Quality status: {status}", annotations, action)


class GitHubChecksProjector:
    def project(self, verdict: Mapping[str, Any]) -> CheckProjection:
        return project_check(verdict)


__all__ = ["CheckProjection", "GitHubChecksProjector", "SCHEMA", "project_check"]
