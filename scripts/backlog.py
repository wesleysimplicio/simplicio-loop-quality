#!/usr/bin/env python3
"""Validate and render the canonical GitHub issue backlog."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKLOG = ROOT / "backlog" / "issues.json"
ID_RE = re.compile(r"^QLT-([0-9]{3})$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BLOCKER_RE = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/[1-9][0-9]*$"
)
MILESTONE_RANGE_RE = re.compile(r"^(QLT-[0-9]{3})\.\.(QLT-[0-9]{3})$")
ALLOWED_PRIORITIES = {"P0", "P1", "P2", "P3"}
ALLOWED_EPICS = {
    "Foundation",
    "Loop integration",
    "Planning and governance",
    "Core quality agents",
    "Advanced assurance",
    "Universal support",
    "Production readiness",
}
GITHUB_TITLE_LIMIT = 256
GITHUB_BODY_LIMIT = 65_536


class BacklogError(ValueError):
    pass


def load_backlog(path: str | Path = BACKLOG) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise BacklogError("backlog root must be an object")
    return payload


def validate_backlog(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema") != "simplicio.quality-backlog/v1":
        errors.append("invalid backlog schema")
    repository = payload.get("repository")
    if not isinstance(repository, str) or not REPOSITORY_RE.fullmatch(repository):
        errors.append("repository must be owner/name")
    if not str(payload.get("generated_from") or "").strip():
        errors.append("generated_from is required")
    issues = payload.get("issues")
    if not isinstance(issues, list) or not issues:
        return errors + ["issues must be a non-empty array"]
    seen: set[str] = set()
    titles: set[str] = set()
    expected = 1
    for index, issue in enumerate(issues):
        path = f"issues[{index}]"
        if not isinstance(issue, dict):
            errors.append(f"{path} must be an object")
            continue
        issue_id = str(issue.get("id") or "")
        match = ID_RE.match(issue_id)
        if not match:
            errors.append(f"{path}.id is invalid")
        elif int(match.group(1)) != expected:
            errors.append(f"{path}.id expected QLT-{expected:03d}, got {issue_id}")
        expected += 1
        if issue_id in seen:
            errors.append(f"duplicate issue id: {issue_id}")
        for field in ("title", "epic", "priority", "problem"):
            if not isinstance(issue.get(field), str) or not issue[field].strip():
                errors.append(f"{path}.{field} is required")
        title = issue.get("title")
        if isinstance(title, str):
            if len(title) > GITHUB_TITLE_LIMIT - len("[QLT-000] "):
                errors.append(f"{path}.title exceeds GitHub limit")
            if title in titles:
                errors.append(f"duplicate issue title: {title}")
            titles.add(title)
        if issue.get("priority") not in ALLOWED_PRIORITIES:
            errors.append(f"{path}.priority is unsupported")
        if issue.get("epic") not in ALLOWED_EPICS:
            errors.append(f"{path}.epic is unsupported")
        for field in ("depends_on", "blocked_by", "steps", "acceptance", "tests"):
            value = issue.get(field)
            if not isinstance(value, list):
                errors.append(f"{path}.{field} must be an array")
                continue
            if field in {"steps", "acceptance", "tests"} and not value:
                errors.append(f"{path}.{field} cannot be empty")
            if not all(isinstance(item, str) and item.strip() for item in value):
                errors.append(f"{path}.{field} must contain non-empty strings")
            if len(value) != len(set(item for item in value if isinstance(item, str))):
                errors.append(f"{path}.{field} contains duplicates")
        dependencies = issue.get("depends_on")
        if isinstance(dependencies, list):
            for dependency in dependencies:
                if not isinstance(dependency, str):
                    continue
                if dependency not in seen:
                    errors.append(f"{path} depends on missing or later issue {dependency}")
        blockers = issue.get("blocked_by")
        if isinstance(blockers, list):
            for blocker in blockers:
                if isinstance(blocker, str) and not BLOCKER_RE.fullmatch(blocker):
                    errors.append(f"{path}.blocked_by has invalid GitHub issue URL")
        seen.add(issue_id)
    common = payload.get("common_definition_of_done")
    if not isinstance(common, list) or not common:
        errors.append("common_definition_of_done must be a non-empty array")
    elif not all(isinstance(item, str) and item.strip() for item in common):
        errors.append("common_definition_of_done must contain non-empty strings")

    milestones = payload.get("milestones")
    covered: list[str] = []
    if not isinstance(milestones, list) or not milestones:
        errors.append("milestones must be a non-empty array")
    else:
        milestone_ids: set[str] = set()
        for index, milestone in enumerate(milestones):
            path = f"milestones[{index}]"
            if not isinstance(milestone, Mapping):
                errors.append(f"{path} must be an object")
                continue
            milestone_id = milestone.get("id")
            if milestone_id != f"M{index}":
                errors.append(f"{path}.id expected M{index}")
            if milestone_id in milestone_ids:
                errors.append(f"duplicate milestone id: {milestone_id}")
            milestone_ids.add(str(milestone_id))
            if not isinstance(milestone.get("title"), str) or not milestone["title"].strip():
                errors.append(f"{path}.title is required")
            raw_range = milestone.get("issues")
            match = MILESTONE_RANGE_RE.fullmatch(str(raw_range or ""))
            if not match:
                errors.append(f"{path}.issues must be QLT-NNN..QLT-NNN")
                continue
            start = int(match.group(1).split("-")[1])
            end = int(match.group(2).split("-")[1])
            if start > end:
                errors.append(f"{path}.issues range is reversed")
                continue
            covered.extend(f"QLT-{number:03d}" for number in range(start, end + 1))
    issue_ids = [item.get("id") for item in issues if isinstance(item, Mapping)]
    if covered != issue_ids:
        errors.append("milestone ranges must cover every issue exactly once and in order")

    if not errors:
        for issue in issues:
            if len(render_issue(payload, issue["id"])) > GITHUB_BODY_LIMIT:
                errors.append(f"{issue['id']} body exceeds GitHub limit")
    return errors


def _bullets(values: Sequence[str], *, checklist: bool = False) -> str:
    marker = "- [ ]" if checklist else "-"
    return "\n".join(f"{marker} {value}" for value in values)


def render_issue(payload: Mapping[str, Any], issue_id: str) -> str:
    issue = next((item for item in payload["issues"] if item["id"] == issue_id), None)
    if issue is None:
        raise BacklogError(f"unknown issue: {issue_id}")
    dependencies = issue.get("depends_on") or []
    blockers = issue.get("blocked_by") or []
    dependency_text = _bullets(dependencies) if dependencies else "- None"
    blocker_text = _bullets(blockers) if blockers else "- None"
    common = payload["common_definition_of_done"]
    return f"""<!-- backlog-id: {issue_id} -->

## Problem

{issue['problem']}

## Scope and implementation steps

{_bullets(issue['steps'], checklist=True)}

## Acceptance criteria

{_bullets(issue['acceptance'], checklist=True)}

## Required tests and evidence

{_bullets(issue['tests'], checklist=True)}

## Dependencies

{dependency_text}

## Upstream blockers

{blocker_text}

## Common Definition of Done

{_bullets(common, checklist=True)}

## Architecture invariant

All commands and agents execute through `simplicio-loop`. This issue must not introduce a local
scheduler, queue, worker pool, process supervisor, worktree manager, retry engine or alternative
completion state.
"""


def milestone_for(payload: Mapping[str, Any], issue_id: str) -> str:
    number = int(issue_id.split("-")[1])
    for milestone in payload["milestones"]:
        match = MILESTONE_RANGE_RE.fullmatch(milestone["issues"])
        if match:
            start = int(match.group(1).split("-")[1])
            end = int(match.group(2).split("-")[1])
            if start <= number <= end:
                return str(milestone["title"])
    raise BacklogError(f"issue has no milestone: {issue_id}")


def export_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Create idempotency-friendly records for the GitHub publishing adapter."""

    records: list[dict[str, Any]] = []
    for issue in payload["issues"]:
        issue_id = issue["id"]
        epic_label = re.sub(r"[^a-z0-9]+", "-", issue["epic"].lower()).strip("-")
        records.append(
            {
                "backlog_id": issue_id,
                "repository": payload["repository"],
                "title": f"[{issue_id}] {issue['title']}",
                "body": render_issue(payload, issue_id),
                "labels": [f"priority:{issue['priority'].lower()}", f"epic:{epic_label}"],
                "milestone": milestone_for(payload, issue_id),
            }
        )
    return records


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "list", "render", "export"))
    parser.add_argument("issue_id", nargs="?")
    parser.add_argument("--path", default=str(BACKLOG))
    args = parser.parse_args(argv)
    payload = load_backlog(args.path)
    errors = validate_backlog(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2))
        return 1
    if args.action == "check":
        print(json.dumps({"ok": True, "issues": len(payload["issues"])}, indent=2))
    elif args.action == "list":
        for issue in payload["issues"]:
            print(f"{issue['id']}\t[{issue['priority']}] {issue['title']}")
    elif args.action == "render":
        if not args.issue_id:
            parser.error("render requires issue_id")
        print(render_issue(payload, args.issue_id))
    else:
        for record in export_records(payload):
            print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
