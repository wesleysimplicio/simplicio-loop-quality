"""Declarative quality-agent profiles executed by simplicio-loop.

These objects are role definitions, not local workers.  They never schedule work,
spawn processes or own state.  The Loop stage-agent coordinator and Hub remain the
only execution authorities.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AgentSpec:
    role_id: str
    title: str
    specializes: str
    lanes: tuple[str, ...]
    authority: str = "quality"
    resource_class: str = "test"
    may_author_product_code: bool = False
    may_self_approve: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


AGENTS: tuple[AgentSpec, ...] = (
    AgentSpec("quality_planner_agent", "Quality Planner", "intake_planner", ("planning",)),
    AgentSpec(
        "test_infrastructure_agent",
        "Test Infrastructure Discovery",
        "intake_planner",
        ("toolchain_discovery",),
    ),
    AgentSpec(
        "static_quality_agent",
        "Static Code Quality",
        "runtime_reproduction_verifier",
        ("static_quality",),
    ),
    AgentSpec(
        "test_authoring_agent",
        "Test Authoring",
        "implementation_agent",
        ("test_authoring",),
    ),
    AgentSpec(
        "unit_component_agent",
        "Unit and Component Testing",
        "runtime_reproduction_verifier",
        ("unit", "component", "negative_paths"),
    ),
    AgentSpec(
        "integration_contract_agent",
        "Integration and Contract Testing",
        "runtime_reproduction_verifier",
        ("integration", "contract"),
    ),
    AgentSpec(
        "system_e2e_agent",
        "System and End-to-End Testing",
        "runtime_reproduction_verifier",
        ("system", "e2e"),
    ),
    AgentSpec(
        "accessibility_agent",
        "Accessibility Testing",
        "runtime_reproduction_verifier",
        ("accessibility",),
    ),
    AgentSpec(
        "regression_real_code_agent",
        "Regression and Packaged-Code Testing",
        "runtime_reproduction_verifier",
        ("regression", "smoke", "real_code"),
    ),
    AgentSpec(
        "implementation_completeness_agent",
        "Implementation Completeness",
        "blast_radius_reviewer",
        ("implementation_completeness",),
    ),
    AgentSpec(
        "test_selection_validation_agent",
        "Test Selection Validation",
        "blast_radius_reviewer",
        ("test_selection_validation",),
    ),
    AgentSpec(
        "property_fuzz_agent",
        "Property and Fuzz Testing",
        "runtime_reproduction_verifier",
        ("property", "fuzz"),
    ),
    AgentSpec("mutation_agent", "Mutation Testing", "runtime_reproduction_verifier", ("mutation",)),
    AgentSpec(
        "invariant_review_agent",
        "Invariant Review",
        "security_correctness_reviewer",
        ("invariants",),
    ),
    AgentSpec(
        "independent_code_review_agent",
        "Independent Code Review",
        "maintainability_reviewer",
        ("independent_code_review",),
        authority="audit",
    ),
    AgentSpec(
        "concurrency_reliability_agent",
        "Concurrency and Recovery Testing",
        "runtime_reproduction_verifier",
        ("concurrency", "fault_injection", "flaky_repeatability"),
    ),
    AgentSpec(
        "security_agent",
        "Application and Supply-Chain Security",
        "security_correctness_reviewer",
        ("application_security", "supply_chain_security"),
    ),
    AgentSpec(
        "performance_agent",
        "Performance and Load Testing",
        "runtime_reproduction_verifier",
        ("performance", "load_stress_soak"),
    ),
    AgentSpec(
        "compatibility_install_agent",
        "Compatibility, Installation and Migration Testing",
        "blast_radius_reviewer",
        ("compatibility", "installation", "upgrade_downgrade", "migration"),
    ),
    AgentSpec(
        "operational_readiness_agent",
        "Operational Readiness",
        "runtime_reproduction_verifier",
        ("operational_readiness",),
    ),
    AgentSpec(
        "privacy_compliance_agent",
        "Privacy Compliance",
        "security_correctness_reviewer",
        ("privacy_compliance",),
    ),
    AgentSpec(
        "documentation_quality_agent",
        "Executable Documentation Quality",
        "runtime_reproduction_verifier",
        ("documentation_quality",),
    ),
    AgentSpec(
        "evidence_audit_agent",
        "Independent Evidence Auditor",
        "review_panel",
        ("coverage", "observability", "evidence_audit"),
        authority="audit",
    ),
    AgentSpec(
        "quality_gate_agent",
        "Deterministic Quality Gate",
        "review_panel",
        ("quality_gate",),
        authority="gate",
    ),
)


def agent_ids(agents: Iterable[AgentSpec] = AGENTS) -> tuple[str, ...]:
    return tuple(agent.role_id for agent in agents)


def find_agent(role_id: str) -> AgentSpec:
    for agent in AGENTS:
        if agent.role_id == role_id:
            return agent
    raise KeyError(role_id)
