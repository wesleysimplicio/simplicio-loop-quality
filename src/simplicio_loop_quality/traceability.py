"""Acceptance-criteria traceability for Loop-owned quality runs.

The module is deliberately a pure planning and validation layer.  It does not
run tests, retry work, schedule tasks, or decide completion.  Test execution and
evidence acceptance remain responsibilities of :mod:`simplicio-loop` and its
independent evidence auditor.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .evidence import canonical_json, write_json_atomic

TRACEABILITY_SCHEMA = "simplicio.quality-ac-traceability/v1"
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
_CRITERION_RE = re.compile(
    r"^\s*[-*]\s+(?:\[[ xX]\]\s+)?(?:\*\*)?"
    r"([A-Za-z][A-Za-z0-9._-]*)(?:\*\*)?\s*(?::|[-—])\s*(.+?)\s*$"
)
_TEST_RE = re.compile(
    r"^\s*[-*]\s+(?:`([^`]+)`|(?:\*\*)?([A-Za-z][A-Za-z0-9._:/-]*)"
    r"(?:\*\*)?)\s*(?::|[-—])\s*(.+?)\s*$"
)
_NESTED_FIELD_RE = re.compile(r"^\s{2,}[-*]?\s*([A-Za-z][A-Za-z _-]*):\s*(.*?)\s*$")
_SUCCESS_STATUSES = {"accept", "accepted", "pass", "passed", "success", "verified"}
_FAILURE_STATUSES = {
    "blocked",
    "fail",
    "failed",
    "flaky",
    "not_applicable",
    "rejected",
    "unknown",
}


@dataclass(frozen=True)
class TraceabilityFinding:
    """A deterministic problem found in an AC traceability graph."""

    reason_code: str
    detail: str
    status: str = "FAIL"
    criterion_id: str = ""
    test_id: str = ""
    evidence_ref: str = ""

    def to_dict(self) -> dict[str, str]:
        return {key: value for key, value in asdict(self).items() if value}


@dataclass(frozen=True)
class TraceabilityVerdict:
    """Non-terminal result consumed by the quality gate and Loop Oracle."""

    status: str
    findings: tuple[TraceabilityFinding, ...]
    mapping: tuple[dict[str, Any], ...]
    mapping_sha256: str
    document: Mapping[str, Any]

    @property
    def ready(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TRACEABILITY_SCHEMA,
            "status": self.status,
            "ready": self.ready,
            "mapping": [copy.deepcopy(row) for row in self.mapping],
            "mapping_sha256": self.mapping_sha256,
            "findings": [finding.to_dict() for finding in self.findings],
        }


class TraceabilityInputError(ValueError):
    """Raised when a traceability source cannot be decoded."""


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalized_text(value: Any) -> str:
    return _clean(value).casefold()


def _tokens(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        backticks = [_clean(item) for item in re.findall(r"`([^`]+)`", value)]
        if backticks:
            return [item for item in backticks if item]
        return [item for item in (_clean(part) for part in re.split(r"[,;]", value)) if item]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                token = item.get("id") or item.get("test_id") or item.get("name")
            else:
                token = item
            token = _clean(token)
            if token:
                result.append(token)
        return result
    return []


def _mapping_records(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return [dict({"id": key}, **item) if isinstance(item, Mapping) else {"id": key, "text": item}
                for key, item in value.items()]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _parse_field_value(value: str) -> list[str]:
    return _tokens(value)


def parse_markdown_issue(markdown: str) -> dict[str, Any]:
    """Parse the documented Markdown issue format into a traceability input.

    Stable IDs are intentionally required in the Markdown itself.  Generating
    IDs from bullet order would make a rename or reorder silently change proof
    ownership, which is precisely the ambiguity this contract prevents.
    """

    if not isinstance(markdown, str) or not markdown.strip():
        raise TraceabilityInputError("Markdown issue must be a non-empty string")

    criteria: list[dict[str, Any]] = []
    tests: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    section = ""
    for raw_line in markdown.splitlines():
        heading = _MARKDOWN_HEADING_RE.match(raw_line)
        if heading:
            section = _normalized_text(heading.group(1))
            current = None
            continue

        top_level = raw_line == raw_line.lstrip()
        if top_level and ("acceptance criteria" in section or section in {"criteria", "acceptance"}):
            match = _CRITERION_RE.match(raw_line)
            if match:
                current = {
                    "id": _clean(match.group(1)),
                    "text": _clean(match.group(2)),
                    "required": "[ ]" in raw_line or "[x]" in raw_line.lower(),
                    "planned_test_ids": [],
                    "evidence_types": [],
                }
                criteria.append(current)
                continue
        elif top_level and ("planned tests" in section or section in {"tests", "test plan"}):
            match = _TEST_RE.match(raw_line)
            if match:
                current = {
                    "id": _clean(match.group(1) or match.group(2)),
                    "name": _clean(match.group(3)),
                    "criterion_ids": [],
                    "evidence_types": [],
                }
                tests.append(current)
                continue

        field = _NESTED_FIELD_RE.match(raw_line)
        if not field or current is None:
            continue
        field_name = _normalized_text(field.group(1))
        values = _parse_field_value(field.group(2))
        if field_name in {"tests", "planned tests", "test ids", "planned test ids"}:
            key = "planned_test_ids" if "criterion" in current or "text" in current else "criterion_ids"
            current[key].extend(values)
        elif field_name in {"criteria", "criterion", "criterion ids", "acceptance criteria"}:
            current["criterion_ids"].extend(values)
        elif field_name in {"evidence", "evidence types", "planned evidence", "proof"}:
            current["evidence_types"].extend(values)

    return {
        "schema": TRACEABILITY_SCHEMA,
        "criteria": criteria,
        "tests": tests,
        "evidence": [],
    }


def load_traceability_source(source: Mapping[str, Any] | str | Path) -> Mapping[str, Any]:
    """Load JSON/Markdown input without executing any test or process."""

    if isinstance(source, Mapping):
        return copy.deepcopy(dict(source))
    path = Path(source) if isinstance(source, Path) else None
    if path is not None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise TraceabilityInputError(f"cannot read traceability source: {exc}") from exc
        if path.suffix.lower() in {".json", ".jsonc"}:
            source = text
        else:
            return parse_markdown_issue(text)
    if not isinstance(source, str) or not source.strip():
        raise TraceabilityInputError("traceability source must be a mapping, path or text")
    try:
        value = json.loads(source)
    except json.JSONDecodeError:
        return parse_markdown_issue(source)
    if not isinstance(value, Mapping):
        raise TraceabilityInputError("JSON traceability source must be an object")
    return copy.deepcopy(dict(value))


def _criterion_records(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = raw.get("criteria", raw.get("acceptance_criteria", []))
    records: list[dict[str, Any]] = []
    for item in _mapping_records(values):
        record = {
            "id": _clean(item.get("id") or item.get("ac_id") or item.get("criterion_id")),
            "text": _clean(item.get("text") or item.get("description")),
            "required": bool(item.get("required", True)),
            "planned_test_ids": _tokens(
                item.get("planned_test_ids", item.get("planned_tests", item.get("tests")))
            ),
            "evidence_types": _tokens(
                item.get("evidence_types", item.get("planned_evidence_types", item.get("evidence")))
            ),
        }
        records.append(record)
    return records


def _test_records(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = raw.get("tests", raw.get("planned_tests", []))
    records: list[dict[str, Any]] = []
    for item in _mapping_records(values):
        records.append(
            {
                "id": _clean(item.get("id") or item.get("test_id")),
                "name": _clean(item.get("name") or item.get("title") or item.get("description")),
                "criterion_ids": _tokens(
                    item.get(
                        "criterion_ids",
                        item.get("criteria", item.get("acceptance_criteria", item.get("ac_ids"))),
                    )
                ),
                "evidence_types": _tokens(
                    item.get("evidence_types", item.get("evidence_type", item.get("evidence")))
                ),
            }
        )
    return records


def _evidence_records(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = raw.get("evidence", raw.get("accepted_evidence", []))
    records: list[dict[str, Any]] = []
    for item in _mapping_records(values):
        accepted = item.get("accepted")
        status = _clean(item.get("status") or item.get("outcome") or item.get("result"))
        if accepted is None and status:
            accepted = status.casefold() in _SUCCESS_STATUSES
        records.append(
            {
                "ref": _clean(item.get("ref") or item.get("evidence_ref") or item.get("uri")),
                "test_id": _clean(item.get("test_id") or item.get("test")),
                "criterion_ids": _tokens(
                    item.get("criterion_ids", item.get("criterion_id", item.get("criteria")))
                ),
                "evidence_type": _clean(
                    item.get("evidence_type") or item.get("type") or item.get("kind")
                ),
                "accepted": accepted if isinstance(accepted, bool) else None,
                "status": status,
                "producer_agent": _clean(item.get("producer_agent") or item.get("producer")),
                "audit_agent": _clean(item.get("audit_agent") or item.get("auditor")),
                "identity": copy.deepcopy(item.get("identity"))
                if isinstance(item.get("identity"), Mapping)
                else None,
            }
        )
    return records


def _normalize_document(source: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    raw = dict(load_traceability_source(source))
    nested = raw.get("acceptance_traceability") or raw.get("traceability")
    if isinstance(nested, Mapping):
        merged = dict(nested)
        for key in ("identity", "repository", "issue"):
            if key not in merged and key in raw:
                merged[key] = raw[key]
        raw = merged
    return {
        "schema": TRACEABILITY_SCHEMA,
        **{
            key: copy.deepcopy(raw[key])
            for key in ("identity", "repository", "issue")
            if key in raw
        },
        "criteria": _criterion_records(raw),
        "tests": _test_records(raw),
        "evidence": _evidence_records(raw),
        "provided_mapping": copy.deepcopy(raw.get("mapping"))
        if "mapping" in raw
        else None,
    }


def _finding(
    reason_code: str,
    detail: str,
    *,
    status: str = "FAIL",
    criterion_id: str = "",
    test_id: str = "",
    evidence_ref: str = "",
) -> TraceabilityFinding:
    return TraceabilityFinding(
        reason_code=reason_code,
        detail=detail,
        status=status,
        criterion_id=criterion_id,
        test_id=test_id,
        evidence_ref=evidence_ref,
    )


def _record_signature(record: Mapping[str, Any], fields: Sequence[str]) -> tuple[Any, ...]:
    return tuple(
        tuple(record.get(field, [])) if isinstance(record.get(field), list) else record.get(field)
        for field in fields
    )


def _deduplicate_findings(findings: Sequence[TraceabilityFinding]) -> tuple[TraceabilityFinding, ...]:
    unique: dict[tuple[str, str, str, str, str], TraceabilityFinding] = {}
    for finding in findings:
        key = (
            finding.reason_code,
            finding.criterion_id,
            finding.test_id,
            finding.evidence_ref,
            finding.detail,
        )
        unique[key] = finding
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                item.status,
                item.reason_code,
                item.criterion_id,
                item.test_id,
                item.evidence_ref,
                item.detail,
            ),
        )
    )


def _mapping_hash(mapping: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(canonical_json({"mapping": list(mapping)})).hexdigest()


def _provided_mapping(value: Any) -> list[dict[str, Any]]:
    rows = _mapping_records(value)
    result: list[dict[str, Any]] = []
    for row in rows:
        criterion_id = _clean(row.get("criterion_id") or row.get("ac_id"))
        test_id = _clean(row.get("test_id") or row.get("test"))
        refs = _tokens(row.get("evidence_refs", row.get("evidence")))
        result.append(
            {
                "criterion_id": criterion_id,
                "test_id": test_id,
                "evidence_refs": sorted(set(refs)),
            }
        )
    return sorted(result, key=lambda item: (item["criterion_id"], item["test_id"]))


def evaluate_traceability(
    source: Mapping[str, Any] | str | Path,
    *,
    expected_identity: Mapping[str, Any] | None = None,
) -> TraceabilityVerdict:
    """Validate an AC graph and compute its deterministic AC→test→evidence map."""

    document = _normalize_document(source)
    findings: list[TraceabilityFinding] = []
    criteria = document["criteria"]
    tests = document["tests"]
    evidence = document["evidence"]

    identity = document.get("identity")
    if expected_identity is not None:
        if not isinstance(identity, Mapping):
            findings.append(
                _finding(
                    "traceability_identity_missing",
                    "traceability identity is required for a Loop-bound gate",
                    status="BLOCKED",
                )
            )
        else:
            for field, expected in expected_identity.items():
                if field not in identity:
                    findings.append(
                        _finding(
                            "traceability_identity_missing",
                            f"identity.{field} is required for a Loop-bound gate",
                            status="BLOCKED",
                        )
                    )
                elif identity.get(field) != expected:
                    findings.append(
                        _finding(
                            "traceability_identity_mismatch",
                            f"identity.{field} does not match the trusted Loop context",
                            status="BLOCKED",
                        )
                    )

    criterion_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    test_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    evidence_by_ref: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for criterion in criteria:
        criterion_id = criterion["id"]
        if not criterion_id:
            findings.append(_finding("criterion_id_missing", "every acceptance criterion needs a stable ID"))
        elif not _ID_RE.fullmatch(criterion_id):
            findings.append(
                _finding("criterion_id_invalid", f"criterion ID {criterion_id!r} is not stable", criterion_id=criterion_id)
            )
        if not criterion["text"]:
            findings.append(
                _finding("criterion_text_missing", "acceptance criterion text is required", criterion_id=criterion_id)
            )
        criterion_by_id[criterion_id].append(criterion)

    for criterion_id, records in criterion_by_id.items():
        if not criterion_id or len(records) < 2:
            continue
        signatures = {
            _record_signature(record, ("text", "required", "planned_test_ids", "evidence_types"))
            for record in records
        }
        code = "contradictory_criterion" if len(signatures) > 1 else "ambiguous_duplicate_criterion"
        findings.append(
            _finding(
                code,
                f"criterion {criterion_id} is declared more than once; ambiguity cannot be guessed",
                status="BLOCKED",
                criterion_id=criterion_id,
            )
        )

    criterion_texts: dict[str, list[str]] = defaultdict(list)
    for criterion in criteria:
        if criterion["text"]:
            criterion_texts[_normalized_text(criterion["text"])].append(criterion["id"])
    for ids in criterion_texts.values():
        distinct_ids = sorted(set(ids))
        if len(distinct_ids) > 1:
            findings.append(
                _finding(
                    "ambiguous_duplicate_criterion",
                    f"criteria {', '.join(distinct_ids)} have the same normalized statement",
                    status="BLOCKED",
                    criterion_id=distinct_ids[0],
                )
            )

    for test in tests:
        test_id = test["id"]
        if not test_id:
            findings.append(_finding("test_id_missing", "every planned test needs a stable ID"))
        elif not _ID_RE.fullmatch(test_id):
            findings.append(_finding("test_id_invalid", f"test ID {test_id!r} is invalid", test_id=test_id))
        if not test["name"]:
            findings.append(_finding("test_name_missing", "planned test name is required", test_id=test_id))
        test_by_id[test_id].append(test)

    for test_id, records in test_by_id.items():
        if not test_id or len(records) < 2:
            continue
        signatures = {
            _record_signature(record, ("name", "criterion_ids", "evidence_types")) for record in records
        }
        code = "contradictory_test" if len(signatures) > 1 else "ambiguous_duplicate_test"
        findings.append(
            _finding(
                code,
                f"test {test_id} is declared more than once; ambiguity cannot be guessed",
                status="BLOCKED",
                test_id=test_id,
            )
        )

    test_names: dict[str, list[str]] = defaultdict(list)
    for test in tests:
        if test["name"]:
            test_names[_normalized_text(test["name"])].append(test["id"])
    for ids in test_names.values():
        distinct_ids = sorted(set(ids))
        if len(distinct_ids) > 1:
            findings.append(
                _finding(
                    "ambiguous_duplicate_test",
                    f"tests {', '.join(distinct_ids)} have the same normalized name",
                    status="BLOCKED",
                    test_id=distinct_ids[0],
                )
            )

    defined_criteria = {key for key in criterion_by_id if key}
    defined_tests = {key for key in test_by_id if key}
    planned_by_criterion: dict[str, set[str]] = defaultdict(set)
    planned_by_test: dict[str, set[str]] = defaultdict(set)
    for criterion in criteria:
        criterion_id = criterion["id"]
        for test_id in criterion["planned_test_ids"]:
            planned_by_criterion[criterion_id].add(test_id)
            planned_by_test[test_id].add(criterion_id)
            if test_id not in defined_tests:
                findings.append(
                    _finding(
                        "planned_test_missing",
                        f"criterion {criterion_id} plans unknown test {test_id}",
                        criterion_id=criterion_id,
                        test_id=test_id,
                    )
                )

        if not criterion["planned_test_ids"]:
            findings.append(
                _finding(
                    "orphan_criterion",
                    f"required criterion {criterion_id or '<missing>'} has no planned test",
                    criterion_id=criterion_id,
                )
            )
        if not criterion["evidence_types"]:
            findings.append(
                _finding(
                    "evidence_type_missing",
                    f"criterion {criterion_id or '<missing>'} has no planned evidence type",
                    criterion_id=criterion_id,
                )
            )

    linked_tests: set[str] = set()
    for test in tests:
        test_id = test["id"]
        criterion_ids = set(test["criterion_ids"])
        unknown = sorted(criterion_ids - defined_criteria)
        for criterion_id in unknown:
            findings.append(
                _finding(
                    "orphan_test_criterion",
                    f"test {test_id} references unknown criterion {criterion_id}",
                    test_id=test_id,
                    criterion_id=criterion_id,
                )
            )
        if not criterion_ids or test_id not in planned_by_test:
            findings.append(
                _finding(
                    "irrelevant_test",
                    f"test {test_id or '<missing>'} is not planned for any acceptance criterion",
                    test_id=test_id,
                )
            )
        for criterion_id in criterion_ids & defined_criteria:
            linked_tests.add(test_id)
            if test_id not in planned_by_criterion.get(criterion_id, set()):
                findings.append(
                    _finding(
                        "contradictory_test_link",
                        f"test {test_id} claims {criterion_id}, but the criterion does not plan it",
                        status="BLOCKED",
                        criterion_id=criterion_id,
                        test_id=test_id,
                    )
                )
        for criterion_id in planned_by_test.get(test_id, set()):
            if criterion_id not in criterion_ids:
                findings.append(
                    _finding(
                        "contradictory_test_link",
                        f"criterion {criterion_id} plans {test_id}, but the test does not claim it",
                        status="BLOCKED",
                        criterion_id=criterion_id,
                        test_id=test_id,
                    )
                )
        if not test["evidence_types"]:
            findings.append(
                _finding("test_evidence_type_missing", f"test {test_id} has no evidence type", test_id=test_id)
            )

    for test_id in sorted(defined_tests - linked_tests):
        if test_id in planned_by_test:
            continue
        findings.append(
            _finding(
                "irrelevant_test",
                f"test {test_id} has no usable criterion link",
                test_id=test_id,
            )
        )

    accepted_by_pair: dict[tuple[str, str], set[str]] = defaultdict(set)
    evidence_signature_by_ref: dict[str, set[tuple[Any, ...]]] = defaultdict(set)
    for item in evidence:
        ref = item["ref"]
        test_id = item["test_id"]
        criterion_ids = set(item["criterion_ids"])
        if not ref:
            findings.append(_finding("evidence_ref_missing", "evidence ref is required"))
        evidence_by_ref[ref].append(item)
        if ref:
            evidence_signature_by_ref[ref].add(
                (test_id, tuple(sorted(criterion_ids)), item["evidence_type"], item["accepted"], item["status"])
            )
        if test_id not in defined_tests:
            findings.append(
                _finding("irrelevant_evidence", f"evidence {ref or '<missing>'} references unknown test {test_id}", evidence_ref=ref, test_id=test_id)
            )
            continue
        if not criterion_ids:
            findings.append(
                _finding("evidence_criterion_missing", f"evidence {ref} has no criterion link", evidence_ref=ref)
            )
        for criterion_id in sorted(criterion_ids):
            if criterion_id not in defined_criteria:
                findings.append(
                    _finding("irrelevant_evidence", f"evidence {ref} references unknown criterion {criterion_id}", evidence_ref=ref, criterion_id=criterion_id)
                )
            elif test_id not in planned_by_criterion.get(criterion_id, set()):
                findings.append(
                    _finding("irrelevant_evidence", f"evidence {ref} is outside the planned {criterion_id}→{test_id} link", evidence_ref=ref, criterion_id=criterion_id, test_id=test_id)
                )

        if item["evidence_type"] not in {
            *{
                evidence_type
                for criterion in criteria
                if criterion["id"] in criterion_ids
                for evidence_type in criterion["evidence_types"]
            },
            *{
                evidence_type
                for test in tests
                if test["id"] == test_id
                for evidence_type in test["evidence_types"]
            },
        }:
            findings.append(
                _finding("irrelevant_evidence_type", f"evidence {ref} has an unplanned evidence type", evidence_ref=ref, test_id=test_id)
            )

        if item["accepted"] is None:
            findings.append(_finding("evidence_status_missing", f"evidence {ref} has no accepted status", evidence_ref=ref))
        if item["accepted"] is True and item["status"].casefold() in _FAILURE_STATUSES:
            findings.append(
                _finding("contradictory_evidence", f"evidence {ref} is both accepted and {item['status']}", status="BLOCKED", evidence_ref=ref)
            )
        if item["accepted"] is True:
            if not item["producer_agent"] or not item["audit_agent"]:
                findings.append(_finding("evidence_independence_missing", f"accepted evidence {ref} lacks producer/auditor identity", evidence_ref=ref))
            elif item["producer_agent"] == item["audit_agent"]:
                findings.append(_finding("evidence_self_approval", f"accepted evidence {ref} was audited by its producer", status="BLOCKED", evidence_ref=ref))
            else:
                for criterion_id in criterion_ids:
                    accepted_by_pair[(criterion_id, test_id)].add(ref)

        if identity is not None and item["identity"] is not None and item["identity"] != identity:
            findings.append(_finding("stale_evidence_binding", f"evidence {ref} is bound to a different run identity", status="BLOCKED", evidence_ref=ref))

    for ref, records in evidence_by_ref.items():
        if ref and len(records) > 1 and len(evidence_signature_by_ref[ref]) > 1:
            findings.append(_finding("contradictory_evidence", f"evidence ref {ref} has contradictory claims", status="BLOCKED", evidence_ref=ref))

    mapping: list[dict[str, Any]] = []
    for criterion_id in sorted(defined_criteria):
        for test_id in sorted(planned_by_criterion.get(criterion_id, set())):
            refs = sorted(accepted_by_pair.get((criterion_id, test_id), set()))
            mapping.append(
                {
                    "criterion_id": criterion_id,
                    "test_id": test_id,
                    "evidence_refs": refs,
                }
            )

    provided = document.get("provided_mapping")
    if provided is not None and _provided_mapping(provided) != mapping:
        findings.append(
            _finding(
                "mapping_mismatch",
                "persisted AC→test→evidence mapping differs from the recomputed mapping",
                status="BLOCKED",
            )
        )

    for criterion in criteria:
        criterion_id = criterion["id"]
        if criterion.get("required", True) and not any(
            refs for (mapped_criterion, _), refs in accepted_by_pair.items() if mapped_criterion == criterion_id
        ):
            findings.append(
                _finding(
                    "required_criterion_unproven",
                    f"required criterion {criterion_id or '<missing>'} lacks accepted independent evidence",
                    criterion_id=criterion_id,
                )
            )

    final_findings = _deduplicate_findings(findings)
    status = "BLOCKED" if any(item.status == "BLOCKED" for item in final_findings) else "FAIL" if final_findings else "PASS"
    return TraceabilityVerdict(
        status=status,
        findings=final_findings,
        mapping=tuple(copy.deepcopy(mapping)),
        mapping_sha256=_mapping_hash(mapping),
        document=document,
    )


def build_traceability_document(
    source: Mapping[str, Any] | str | Path,
    *,
    expected_identity: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], TraceabilityVerdict]:
    """Return the canonical persisted document and its non-terminal verdict."""

    verdict = evaluate_traceability(source, expected_identity=expected_identity)
    payload = copy.deepcopy(dict(verdict.document))
    payload.pop("provided_mapping", None)
    payload["mapping"] = [copy.deepcopy(row) for row in verdict.mapping]
    payload["mapping_sha256"] = verdict.mapping_sha256
    payload["status"] = verdict.status
    payload["findings"] = [finding.to_dict() for finding in verdict.findings]
    return payload, verdict


def persist_traceability(
    source: Mapping[str, Any] | str | Path,
    output: str | Path,
    *,
    expected_identity: Mapping[str, Any] | None = None,
) -> TraceabilityVerdict:
    """Atomically persist the AC mapping, including fail-closed findings."""

    payload, verdict = build_traceability_document(source, expected_identity=expected_identity)
    write_json_atomic(output, payload)
    return verdict


def validate_traceability(source: Mapping[str, Any] | str | Path) -> tuple[TraceabilityFinding, ...]:
    """Compatibility helper returning deterministic findings only."""

    return evaluate_traceability(source).findings


build_acceptance_traceability = build_traceability_document
evaluate_acceptance_traceability = evaluate_traceability
persist_acceptance_traceability = persist_traceability
