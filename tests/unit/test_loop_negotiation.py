import copy

import pytest
from simplicio_loop.extension_handshake import extension_handshake
from simplicio_loop.extension_registry import ExtensionRegistry

from simplicio_loop_quality.loop_negotiation import negotiate_loop
from simplicio_loop_quality.provider import provider


def native_handshakes():
    runtime = provider()
    registry = ExtensionRegistry()
    registry.register(runtime.manifest, runtime=runtime)
    provider_value = extension_handshake(
        "simplicio_loop_quality", "strict-default", registry=registry
    )
    core_value = {
        "schema": "simplicio.loop-extension-handshake/v1",
        "capabilities": ["run-outcome/v1"],
        "completion_authority": "core-completion-oracle-only",
    }
    roles = {row["role_id"] for row in runtime.manifest["role_bindings"]}
    handlers = {row["effect_id"] for row in runtime.manifest["effect_handlers"]}
    return provider_value, core_value, roles, handlers


@pytest.mark.parametrize("version", ["3.38.22"])
def test_n_and_current_are_supported(version):
    handshake, core, roles, handlers = native_handshakes()
    report = negotiate_loop(
        core_version=version,
        provider_handshake=handshake,
        core_handshake=core,
        expected_roles=roles,
        expected_handlers=handlers,
    )
    assert report["ready"] is True
    assert report["reason_code"] == "READY"
    assert all(report["capabilities"].values())


def test_n_minus_1_fixture_is_explicitly_blocked():
    handshake, core, roles, handlers = native_handshakes()
    report = negotiate_loop(
        core_version="3.38.21",
        provider_handshake=handshake,
        core_handshake=core,
        expected_roles=roles,
        expected_handlers=handlers,
    )
    assert report["ready"] is False
    assert "CORE_VERSION_UNSUPPORTED" in report["reason_codes"]


@pytest.mark.parametrize(
    ("version", "reason"),
    [
        ("3.38.19", "CORE_VERSION_UNSUPPORTED"),
        ("3.38.23", "CORE_VERSION_FUTURE_UNKNOWN"),
        ("4.0.0", "CORE_VERSION_FUTURE_UNKNOWN"),
        (None, "CORE_VERSION_UNAVAILABLE"),
    ],
)
def test_old_future_unknown_and_missing_versions_block(version, reason):
    handshake, core, roles, handlers = native_handshakes()
    report = negotiate_loop(
        core_version=version,
        provider_handshake=handshake,
        core_handshake=core,
        expected_roles=roles,
        expected_handlers=handlers,
    )
    assert report["ready"] is False
    assert reason in report["reason_codes"]


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda value: value["contracts"].pop("hub"), "HUB_IPC_MISSING"),
        (lambda value: value["contracts"].pop("process_spec"), "PROCESS_SPEC_MISSING"),
        (lambda value: value["contracts"].pop("ledger"), "LEDGER_CONTRACT_MISSING"),
        (lambda value: value["provider"].update(roles=[]), "STAGE_AGENT_BINDINGS_MISSING"),
        (lambda value: value["runtime"].update(fingerprint="bad"), "RUNTIME_FINGERPRINT_MISSING"),
        (lambda value: value["authorities"].update(exclusive=False), "ORACLE_CAPABILITY_MISSING"),
        (
            lambda value: value["composition"].update(worker_execution=True),
            "STAGE_COMPOSITION_MISSING",
        ),
    ],
)
def test_partially_capable_loop_reports_atomic_reason(mutation, reason):
    handshake, core, roles, handlers = native_handshakes()
    candidate = copy.deepcopy(handshake)
    mutation(candidate)
    report = negotiate_loop(
        core_version="3.38.22",
        provider_handshake=candidate,
        core_handshake=core,
        expected_roles=roles,
        expected_handlers=handlers,
    )
    assert report["ready"] is False
    assert reason in report["reason_codes"]
    assert report["reason_codes"] == sorted(set(report["reason_codes"]))


def test_unregistered_provider_and_malformed_core_fail_closed():
    _, _, roles, handlers = native_handshakes()
    report = negotiate_loop(
        core_version="3.38.22",
        provider_handshake=None,
        core_handshake={},
        expected_roles=roles,
        expected_handlers=handlers,
    )
    assert report["ready"] is False
    assert "QUALITY_PROVIDER_UNREGISTERED" in report["reason_codes"]
    assert "CORE_HANDSHAKE_MISSING" in report["reason_codes"]
