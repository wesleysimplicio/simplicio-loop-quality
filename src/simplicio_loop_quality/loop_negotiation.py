"""Pure fail-closed evaluation of the native Loop extension handshake."""

from __future__ import annotations

import json
from collections.abc import Mapping
from importlib import resources
from types import MappingProxyType
from typing import Any

EXPECTED_CONTRACTS = MappingProxyType(
    {
        "hub": "simplicio.hub-ipc/v1",
        "process_spec": "simplicio.process-spec/v1",
        "process_result": "simplicio.process-result/v1",
        "ledger": "simplicio.ops-event/v1",
        "run_outcome": "simplicio.run-outcome/v1",
        "invalidation": "simplicio.receipt-invalidation/v1",
        "oracle_matrix": "simplicio.completion-oracle-matrix/v1",
    }
)
REQUIRED_PROVIDER_CAPABILITIES = frozenset(
    {
        "hub_bridge",
        "process_supervision",
        "stage_composition",
        "receipt_invalidation",
        "run_outcome",
        "oracle_delegation",
    }
)


def compatibility_matrix() -> dict[str, Any]:
    resource = resources.files("simplicio_loop_quality.contracts").joinpath(
        "loop-compatibility-v1.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


def negotiate_loop(
    *,
    core_version: Any,
    provider_handshake: Any,
    core_handshake: Any,
    expected_roles: set[str],
    expected_handlers: set[str],
) -> dict[str, Any]:
    """Return deterministic atomic capability states and actionable reason codes."""

    matrix = compatibility_matrix()
    version = str(core_version or "")
    supported_versions = set(matrix["supported_versions"])
    capabilities: dict[str, bool] = {
        "core_version": version in supported_versions,
        "core_handshake": False,
        "stage_agents": False,
        "hub_ipc": False,
        "process_spec": False,
        "process_result": False,
        "ledger": False,
        "quality_hook": False,
        "receipt_invalidation": False,
        "completion_oracle": False,
        "run_outcome": False,
        "runtime_fingerprint": False,
        "stage_composition": False,
    }
    reasons: list[str] = []
    if not version:
        reasons.append("CORE_VERSION_UNAVAILABLE")
    elif version not in supported_versions:
        reasons.append(
            "CORE_VERSION_FUTURE_UNKNOWN"
            if _version_tuple(version) > max(_version_tuple(item) for item in supported_versions)
            else "CORE_VERSION_UNSUPPORTED"
        )

    if isinstance(core_handshake, Mapping):
        capabilities["core_handshake"] = (
            core_handshake.get("schema") == "simplicio.loop-extension-handshake/v1"
        )
        capabilities["completion_oracle"] = (
            core_handshake.get("completion_authority") == "core-completion-oracle-only"
        )
        core_caps = core_handshake.get("capabilities")
        capabilities["run_outcome"] = isinstance(core_caps, list) and "run-outcome/v1" in core_caps
    if not capabilities["core_handshake"]:
        reasons.append("CORE_HANDSHAKE_MISSING")

    if isinstance(provider_handshake, Mapping):
        provider = provider_handshake.get("provider")
        runtime = provider_handshake.get("runtime")
        contracts = provider_handshake.get("contracts")
        authorities = provider_handshake.get("authorities")
        composition = provider_handshake.get("composition")
        provided = set(provider.get("capabilities", [])) if isinstance(provider, Mapping) else set()
        capabilities["quality_hook"] = bool(
            provider_handshake.get("schema") == "simplicio.extension-handshake/v1"
            and provider_handshake.get("status") == "PASS"
            and isinstance(provider, Mapping)
            and provider.get("id") == "simplicio_loop_quality"
            and provider.get("policy") == "strict-default"
            and provided >= REQUIRED_PROVIDER_CAPABILITIES
        )
        roles = set(provider.get("roles", [])) if isinstance(provider, Mapping) else set()
        handlers = set(provider.get("handlers", [])) if isinstance(provider, Mapping) else set()
        capabilities["stage_agents"] = roles == expected_roles and handlers == expected_handlers
        if isinstance(contracts, Mapping):
            contract_capabilities = {
                "hub_ipc": "hub",
                "process_spec": "process_spec",
                "process_result": "process_result",
                "ledger": "ledger",
            }
            for capability, contract_name in contract_capabilities.items():
                capabilities[capability] = (
                    contracts.get(contract_name) == EXPECTED_CONTRACTS[contract_name]
                )
            capabilities["receipt_invalidation"] = (
                contracts.get("invalidation") == EXPECTED_CONTRACTS["invalidation"]
            )
            capabilities["completion_oracle"] = capabilities["completion_oracle"] and (
                contracts.get("oracle_matrix") == EXPECTED_CONTRACTS["oracle_matrix"]
            )
            capabilities["run_outcome"] = capabilities["run_outcome"] and (
                contracts.get("run_outcome") == EXPECTED_CONTRACTS["run_outcome"]
            )
        fingerprint = runtime.get("fingerprint") if isinstance(runtime, Mapping) else None
        capabilities["runtime_fingerprint"] = bool(
            isinstance(fingerprint, str)
            and len(fingerprint) == 71
            and fingerprint.startswith("sha256:")
            and all(character in "0123456789abcdef" for character in fingerprint[7:])
        )
        capabilities["stage_composition"] = bool(
            isinstance(composition, Mapping)
            and composition.get("dry_run") is True
            and composition.get("worker_execution") is False
        )
        capabilities["completion_oracle"] = capabilities["completion_oracle"] and bool(
            isinstance(authorities, Mapping)
            and authorities.get("completion_oracle") == "simplicio-loop"
            and authorities.get("exclusive") is True
            and authorities.get("provider_may_complete") is False
        )
    else:
        reasons.append("QUALITY_PROVIDER_UNREGISTERED")

    reason_by_capability = {
        "stage_agents": "STAGE_AGENT_BINDINGS_MISSING",
        "hub_ipc": "HUB_IPC_MISSING",
        "process_spec": "PROCESS_SPEC_MISSING",
        "process_result": "PROCESS_RESULT_MISSING",
        "ledger": "LEDGER_CONTRACT_MISSING",
        "quality_hook": "QUALITY_PROVIDER_HOOK_MISSING",
        "receipt_invalidation": "RECEIPT_INVALIDATION_MISSING",
        "completion_oracle": "ORACLE_CAPABILITY_MISSING",
        "run_outcome": "RUN_OUTCOME_MISSING",
        "runtime_fingerprint": "RUNTIME_FINGERPRINT_MISSING",
        "stage_composition": "STAGE_COMPOSITION_MISSING",
    }
    reasons.extend(code for name, code in reason_by_capability.items() if not capabilities[name])
    reasons = sorted(set(reasons))
    ready = all(capabilities.values()) and not reasons
    return {
        "schema": "simplicio.quality-loop-negotiation/v1",
        "core_version": version or None,
        "compatibility": matrix,
        "capabilities": dict(sorted(capabilities.items())),
        "ready": ready,
        "reason_code": "READY" if ready else reasons[0],
        "reason_codes": reasons,
    }


def _version_tuple(value: str) -> tuple[int, int, int]:
    try:
        parts = value.split(".")
        if len(parts) != 3:
            return (-1, -1, -1)
        return tuple(int(part) for part in parts)  # type: ignore[return-value]
    except (TypeError, ValueError):
        return (-1, -1, -1)
