from simplicio_loop.extension_handshake import extension_handshake
from simplicio_loop.extension_registry import ExtensionRegistry

from simplicio_loop_quality.provider import provider
import simplicio_loop_quality.provider as provider_module


def test_provider_has_exact_callable_role_and_effect_bindings():
    runtime = provider()
    expected = {row["role_id"] for row in runtime.manifest["role_bindings"]} | {
        row["effect_id"] for row in runtime.manifest["effect_handlers"]
    }
    assert set(runtime.bindings) == expected
    assert all(callable(binding) for binding in runtime.bindings.values())
    registry = ExtensionRegistry()
    registry.register(runtime.manifest, runtime=runtime)
    handshake = extension_handshake("simplicio_loop_quality", "strict-default", registry=registry)
    assert handshake["status"] == "PASS"
    assert handshake["authorities"]["provider_may_complete"] is False
    assert handshake["composition"]["worker_execution"] is False


def test_role_binding_and_receipt_handler_are_fail_closed_and_nonterminal():
    runtime = provider()
    role = runtime.bindings["unit_component_agent"]
    assert role()["reason_code"] == "INVALID_ROLE_REQUEST"
    result = role({"stage": "unit"})
    assert (result["status"], result["reason_code"], result["terminal"]) == (
        "BLOCKED",
        "HUB_STAGE_DISPATCH_REQUIRED",
        False,
    )
    publish = runtime.bindings["publish_quality_receipt"]
    invalid = publish({"schema": "unknown/v1"})
    assert (invalid["status"], invalid["terminal"]) == ("BLOCKED", False)


def test_productive_provider_submits_check_through_hub_adapter(tmp_path, monkeypatch):
    check = tmp_path / "scripts" / "check.py"
    check.parent.mkdir()
    check.write_text("raise SystemExit(0)\n", encoding="utf-8")
    captured = {}

    class _Receipt:
        status = "PASS"
        reason_code = "PROCESS_SUCCEEDED"
        raw_evidence = {"process_result": {"returncode": 0}}

    class _Adapter:
        def submit(self, request):
            captured["request"] = request
            return object()

        def poll(self, _submission):
            return {"state": "completed"}

        def collect(self, _submission):
            return _Receipt()

    monkeypatch.setattr(provider_module, "_hub_adapter", lambda: _Adapter())
    result = provider_module.run(
        run_id="run-1", tasks=[], attempt=1, repo=str(tmp_path), worktree="",
        head="head", diff_hash="diff", policy="strict-default",
    )
    assert result["status"] == "PASS"
    assert captured["request"].argv[1].endswith("scripts\\check.py") or captured["request"].argv[1].endswith("scripts/check.py")
