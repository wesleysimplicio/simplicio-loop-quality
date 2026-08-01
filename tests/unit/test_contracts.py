import copy
import json
import unittest
from importlib import resources
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st
from jsonschema import Draft202012Validator, FormatChecker

from simplicio_loop_quality.contract_migrations import (
    ContractMigrationError,
    canonical_hash,
    migrate_legacy_contract,
)
from simplicio_loop_quality.contract_validation import (
    ContractSemanticError,
    project_report_to_loop_v2,
    validate_contract_document,
    validate_contract_semantics,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "contracts-v1-corpus.json"


class ContractSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        resource = resources.files("simplicio_loop_quality.contracts").joinpath(
            "quality-contracts-v1.schema.json"
        )
        cls.schema = json.loads(resource.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema, format_checker=FormatChecker())
        cls.corpus = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def assertValid(self, value):
        errors = sorted(self.validator.iter_errors(value), key=lambda error: list(error.path))
        self.assertEqual(errors, [], [error.message for error in errors])

    def assertInvalid(self, value):
        self.assertTrue(list(self.validator.iter_errors(value)))

    def test_golden_report_preserves_zero_and_explicit_unavailable_metric(self):
        report = self.corpus["report"]
        self.assertValid(report)
        measured = report["lanes"]["unit"]["metrics"][0]
        unavailable = report["lanes"]["coverage"]["metrics"][0]
        self.assertEqual(measured["value"], 0)
        self.assertIsNone(measured["unavailable_reason"])
        self.assertIsNone(unavailable["value"])
        self.assertEqual(unavailable["samples"], 0)
        self.assertEqual(unavailable["unavailable_reason"], "tool_unavailable")

    def test_invalid_golden_mutation_corpus_fails_closed(self):
        for mutation in self.corpus["invalid_mutations"]:
            value = copy.deepcopy(self.corpus["report"])
            target = value
            for part in mutation["path"][:-1]:
                target = target[part]
            target[mutation["path"][-1]] = mutation["value"]
            with self.subTest(name=mutation["name"]):
                self.assertInvalid(value)

    def test_every_contract_document_validates_and_round_trips(self):
        identity = self.corpus["identity"]
        evidence = self.corpus["evidence"]
        finding = {
            "finding_id": "finding-1",
            "identity": identity,
            "lane": "unit",
            "severity": "HIGH",
            "reason_code": "assertion_failed",
            "detail": "focused assertion failed",
            "evidence_refs": [evidence["ref"]],
        }
        waiver = {
            "waiver_id": "waiver-1",
            "identity": identity,
            "scope": "documentation",
            "justification": "not structurally applicable",
            "requested_by": "requester",
            "approved_by": "independent-approver",
            "expires_at": "2026-12-31T00:00:00Z",
            "policy_hash": identity["policy_hash"],
        }
        documents = [
            {
                "schema": "simplicio.quality-plan/v2",
                "identity": identity,
                "repository": "repo",
                "lanes": ["unit"],
                "agents": ["unit-executor"],
                "toolchain": evidence["toolchain"],
            },
            {
                "schema": "simplicio.quality-stage-request/v1",
                "identity": identity,
                "stage_id": "stage-1",
                "lane": "unit",
                "agent": "unit-executor",
                "command": ["python", "-m", "pytest"],
                "timeout_ms": 1000,
            },
            {
                "schema": "simplicio.quality-stage-result/v1",
                "identity": identity,
                "stage_id": "stage-1",
                "status": "FAIL",
                "started_at": "2026-08-01T00:00:00Z",
                "completed_at": "2026-08-01T00:00:01Z",
                "exit_code": 1,
                "evidence": [evidence],
                "metrics": [],
                "findings": [finding],
            },
            self.corpus["report"],
            {"schema": "simplicio.quality-finding/v1", "finding": finding},
            {"schema": "simplicio.quality-waiver/v1", "waiver": waiver},
            {
                "schema": "simplicio.quality-gate-verdict/v2",
                "identity": identity,
                "status": "BLOCKED",
                "ready": False,
                "authority": "quality-extension",
                "terminal": False,
                "reason_code": "findings_present",
                "findings": [finding],
            },
            migrate_legacy_contract({"schema": "simplicio.quality-evidence/v1", "run_id": "run-1"}),
        ]
        for document in documents:
            with self.subTest(schema=document["schema"]):
                self.assertValid(document)
                self.assertEqual(document, json.loads(json.dumps(document, sort_keys=True)))

    @given(
        st.text(min_size=1, max_size=24).filter(
            lambda value: (
                value
                not in {
                    "schema",
                    "identity",
                    "producer_agent",
                    "audit_agent",
                    "generated_at",
                    "lanes",
                    "findings",
                }
            )
        )
    )
    def test_property_unknown_top_level_fields_never_validate(self, field):
        value = copy.deepcopy(self.corpus["report"])
        value[field] = True
        self.assertInvalid(value)

    def test_migration_is_deterministic_idempotent_and_never_invents_pass(self):
        legacy = {"schema": "simplicio.quality-evidence/v1", "run_id": "run-1"}
        first = migrate_legacy_contract(legacy)
        second = migrate_legacy_contract(legacy)
        self.assertEqual(first, second)
        self.assertEqual(first["source_hash"], canonical_hash(legacy))
        self.assertEqual(first["status"], "BLOCKED")
        self.assertIsNone(first["migrated"])
        self.assertEqual(migrate_legacy_contract(first), first)
        self.assertValid(first)

    def test_migration_rejects_unknown_non_object_and_tampered_receipt(self):
        cases = [
            [],
            {"schema": "unknown/v1"},
            {
                "schema": "simplicio.quality-contract-migration/v1",
                "source_schema": "simplicio.quality-evidence/v1",
                "source_hash": "bad",
                "status": "BLOCKED",
                "reason_code": "legacy_contract_requires_reverification",
                "migrated": None,
            },
            {
                "schema": "simplicio.quality-contract-migration/v1",
                "source_schema": "simplicio.quality-evidence/v1",
                "source_hash": "0" * 64,
                "status": "PASS",
                "reason_code": "legacy_contract_requires_reverification",
                "migrated": None,
            },
            {
                "schema": "simplicio.quality-contract-migration/v1",
                "source_schema": "simplicio.quality-evidence/v1",
                "source_hash": "0" * 64,
                "status": "BLOCKED",
                "reason_code": "legacy_contract_requires_reverification",
                "migrated": None,
                "unexpected": True,
            },
        ]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ContractMigrationError):
                migrate_legacy_contract(value)

    def test_installed_loop_v2_contract_is_consumed_without_vendoring(self):
        from simplicio_loop import quality_matrix_v2

        projection = project_report_to_loop_v2(self.corpus["report"])
        self.assertEqual(quality_matrix_v2.validate_v2(projection), [])
        self.assertFalse(quality_matrix_v2.evaluate_v2(projection)["ready"])
        self.assertEqual(projection["identity"]["head_sha"], self.corpus["identity"]["source_sha"])
        self.assertEqual(projection["lanes"]["unit_component"]["metrics"][0]["value"], 0)
        self.assertNotIn("quality-matrix", self.schema["$id"])

    def test_semantic_bindings_status_and_waivers_fail_closed(self):
        mutations = []
        stale = copy.deepcopy(self.corpus["report"])
        stale["lanes"]["unit"]["evidence"] = [copy.deepcopy(self.corpus["evidence"])]
        stale["lanes"]["unit"]["evidence"][0]["identity"]["run_id"] = "stale"
        mutations.append(stale)
        self_audit = copy.deepcopy(self.corpus["report"])
        self_audit["audit_agent"] = self_audit["producer_agent"]
        mutations.append(self_audit)
        unknown_finding = copy.deepcopy(self.corpus["report"])
        unknown_finding["lanes"]["unit"]["finding_ids"] = ["missing"]
        mutations.append(unknown_finding)
        for value in mutations:
            with self.subTest(value=value):
                self.assertTrue(validate_contract_semantics(value))
                with self.assertRaises(ContractSemanticError):
                    project_report_to_loop_v2(value)

    def test_semantic_waiver_requires_independent_current_matching_approval(self):
        report = copy.deepcopy(self.corpus["report"])
        lane = report["lanes"]["unit"]
        lane["status"] = "NOT_APPLICABLE"
        lane["evidence"] = []
        lane["waiver"] = {
            "waiver_id": "w-1",
            "identity": report["identity"],
            "scope": "unit",
            "justification": "not applicable",
            "requested_by": "same",
            "approved_by": "same",
            "expires_at": "2025-01-01T00:00:00Z",
            "policy_hash": "0" * 64,
        }
        errors = validate_contract_semantics(report)
        self.assertTrue(any("independent" in error for error in errors))
        self.assertTrue(any("expired" in error for error in errors))
        self.assertTrue(any("policy mismatch" in error for error in errors))

    def test_stage_pass_requires_bound_evidence_zero_exit_and_ordered_time(self):
        stage = {
            "schema": "simplicio.quality-stage-result/v1",
            "identity": self.corpus["identity"],
            "stage_id": "stage",
            "status": "PASS",
            "started_at": "2026-08-02T00:00:00Z",
            "completed_at": "2026-08-01T00:00:00Z",
            "exit_code": 1,
            "evidence": [],
            "metrics": [],
            "findings": [],
        }
        self.assertInvalid(stage)
        errors = validate_contract_semantics(stage)
        self.assertGreaterEqual(len(errors), 3)

    def test_stage_na_and_evidence_audit_are_fail_closed(self):
        stage = {
            "schema": "simplicio.quality-stage-result/v1",
            "identity": self.corpus["identity"],
            "stage_id": "stage",
            "status": "NOT_APPLICABLE",
            "started_at": "2026-08-01T00:00:00Z",
            "completed_at": "2026-08-01T00:00:01Z",
            "exit_code": None,
            "evidence": [],
            "metrics": [],
            "findings": [],
        }
        self.assertInvalid(stage)
        self.assertTrue(validate_contract_semantics(stage))
        stage["status"] = "BLOCKED"
        stage["evidence"] = [copy.deepcopy(self.corpus["evidence"])]
        stage["evidence"][0]["audit_agent"] = stage["evidence"][0]["producer_agent"]
        self.assertTrue(any("independent" in error for error in validate_contract_semantics(stage)))

    def test_projection_rejects_unknown_schema_and_top_level_fields(self):
        unknown = copy.deepcopy(self.corpus["report"])
        unknown["schema"] = "unknown/v1"
        with self.assertRaises(ContractSemanticError):
            project_report_to_loop_v2(unknown)
        extra = copy.deepcopy(self.corpus["report"])
        extra["unexpected"] = True
        with self.assertRaises(ContractSemanticError):
            project_report_to_loop_v2(extra)

    def test_projection_applies_full_nested_schema_before_mapping(self):
        mutations = []
        unknown_lane_field = copy.deepcopy(self.corpus["report"])
        unknown_lane_field["lanes"]["unit"]["unexpected"] = True
        mutations.append(unknown_lane_field)
        invalid_metric = copy.deepcopy(self.corpus["report"])
        invalid_metric["lanes"]["unit"]["metrics"][0]["samples"] = 0
        mutations.append(invalid_metric)
        bad_timestamp = copy.deepcopy(self.corpus["report"])
        bad_timestamp["generated_at"] = "not-a-time"
        mutations.append(bad_timestamp)
        for value in mutations:
            with self.subTest(value=value):
                self.assertTrue(validate_contract_document(value))
                with self.assertRaises(ContractSemanticError):
                    project_report_to_loop_v2(value)
