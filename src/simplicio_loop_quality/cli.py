"""Command-line interface for the quality extension."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import uuid
from collections.abc import Sequence
from contextlib import suppress
from importlib import metadata, resources
from pathlib import Path
from typing import Any

from . import __version__
from .agents import AGENTS
from .evidence import write_json_atomic
from .gate import GateContext, evaluate_receipt
from .goal import render_quality_task
from .loop_invoker import LoopInvoker, LoopUnavailable
from .loop_negotiation import negotiate_loop
from .policy import (
    PolicyError,
    ensure_authoritative_policy,
    load_policy_mapping,
    resolve_policy,
)


def _resolution(global_path: str = "", project_path: str = "", cli_path: str = ""):
    return resolve_policy(
        global_policy=load_policy_mapping(global_path) if global_path else None,
        project_policy=load_policy_mapping(project_path) if project_path else None,
        cli_policy=load_policy_mapping(cli_path) if cli_path else None,
    )


def _policy(global_path: str = "", project_path: str = "", cli_path: str = ""):
    return _resolution(global_path, project_path, cli_path).policy


def _extension_manifest() -> dict[str, Any]:
    resource = resources.files("simplicio_loop_quality.contracts").joinpath("loop-extension.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def _version_triplet(value: Any) -> tuple[int, int, int] | None:
    match = re.match(r"^([0-9]+)\.([0-9]+)\.([0-9]+)", str(value or ""))
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _loop_capabilities() -> dict[str, Any]:
    result: dict[str, Any] = {
        "installed": False,
        "version": None,
        "version_compatible": False,
        "manifest_valid": False,
        "extension_handshake": False,
        "quality_provider_hook": False,
        "completion_oracle": False,
        "terminal_run_outcome": False,
        "ready": False,
        "reason_code": "loop_unavailable",
    }
    distribution_version = None
    with suppress(metadata.PackageNotFoundError):
        distribution_version = metadata.version("simplicio-loop")
    try:
        from simplicio_loop import __version__ as loop_module_version
        from simplicio_loop import extension_handshake as provider_handshake
        from simplicio_loop import extension_manifest
    except ImportError:
        return result
    result["installed"] = True
    result["version"] = loop_module_version
    result["module_version"] = loop_module_version
    result["distribution_version"] = distribution_version
    version_metadata_mismatch = bool(
        distribution_version and distribution_version != loop_module_version
    )
    manifest = _extension_manifest()
    core_requirement = manifest["requires_core"]
    actual_version = _version_triplet(result["version"])
    minimum = _version_triplet(core_requirement["min_version"])
    maximum = _version_triplet(core_requirement["max_version"])
    result["version_compatible"] = bool(
        actual_version and minimum and maximum and minimum <= actual_version <= maximum
    )
    errors = extension_manifest.validate_manifest(manifest)
    result["manifest_valid"] = not errors
    result["manifest_errors"] = errors
    core_handshake: dict[str, Any] = {}
    handshake_fn = getattr(extension_manifest, "extension_handshake", None)
    if callable(handshake_fn):
        try:
            candidate = handshake_fn()
            if isinstance(candidate, dict):
                core_handshake = candidate
        except (OSError, RuntimeError, TypeError, ValueError):
            pass
    result["extension_handshake"] = (
        core_handshake.get("schema") == "simplicio.loop-extension-handshake/v1"
    )
    result["completion_oracle"] = (
        core_handshake.get("completion_authority") == "core-completion-oracle-only"
    )
    capabilities = core_handshake.get("capabilities")
    result["terminal_run_outcome"] = (
        isinstance(capabilities, list) and "run-outcome/v1" in capabilities
    )
    provider: dict[str, Any] | None = None
    try:
        provider = provider_handshake.extension_handshake(
            manifest["extension_id"], "strict-default"
        )
    except provider_handshake.ExtensionHandshakeError as exc:
        result["provider_reason_code"] = exc.reason_code
        result["provider_detail"] = exc.detail
    else:
        provider_identity = provider.get("provider")
        result["quality_provider_hook"] = bool(
            provider.get("schema") == "simplicio.extension-handshake/v1"
            and provider.get("status") == "PASS"
            and isinstance(provider_identity, dict)
            and provider_identity.get("id") == manifest["extension_id"]
            and provider_identity.get("policy") == "strict-default"
        )
        fingerprint = provider.get("runtime", {}).get("fingerprint")
        result["runtime_fingerprint"] = fingerprint
        result["runtime_fingerprint_valid"] = bool(
            isinstance(fingerprint, str)
            and fingerprint.startswith("sha256:")
            and len(fingerprint) == 71
            and all(character in "0123456789abcdefABCDEF" for character in fingerprint[7:])
        )
    expected_roles = {row["role_id"] for row in manifest["role_bindings"]}
    expected_handlers = {row["effect_id"] for row in manifest["effect_handlers"]}
    negotiation = negotiate_loop(
        core_version=result["version"],
        provider_handshake=provider,
        core_handshake=core_handshake,
        expected_roles=expected_roles,
        expected_handlers=expected_handlers,
    )
    if version_metadata_mismatch:
        negotiation["ready"] = False
        negotiation["reason_codes"] = sorted(
            set(negotiation["reason_codes"]) | {"CORE_VERSION_METADATA_MISMATCH"}
        )
        negotiation["reason_code"] = negotiation["reason_codes"][0]
    result["negotiation"] = negotiation
    result["capabilities"] = negotiation["capabilities"]
    result["reason_codes"] = negotiation["reason_codes"]
    result["ready"] = bool(result["manifest_valid"] and negotiation["ready"])
    result["reason_code"] = "READY" if result["ready"] else negotiation["reason_code"]
    return result


def _write_task(args: argparse.Namespace, policy=None) -> Path:
    policy = policy or _policy(
        getattr(args, "global_policy", ""),
        getattr(args, "project_policy", ""),
        getattr(args, "policy", ""),
    )
    text = render_quality_task(args.repo, policy, source_issue=args.issue)
    if args.out:
        target = Path(args.out).resolve()
    else:
        run_id = f"quality-{uuid.uuid4().hex[:12]}"
        target = (
            Path(tempfile.gettempdir()) / "simplicio-loop-quality" / "tasks" / run_id / "task.md"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def cmd_doctor(_args: argparse.Namespace) -> int:
    payload = {
        "schema": "simplicio.quality-doctor/v1",
        "extension_version": __version__,
        "loop": _loop_capabilities(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["loop"]["ready"] else 3


def cmd_agents(_args: argparse.Namespace) -> int:
    print(json.dumps([agent.to_dict() for agent in AGENTS], ensure_ascii=False, indent=2))
    return 0


def cmd_manifest(_args: argparse.Namespace) -> int:
    print(json.dumps(_extension_manifest(), ensure_ascii=False, indent=2))
    return 0


def cmd_policy(args: argparse.Namespace) -> int:
    resolution = _resolution(args.global_policy, args.project_policy, args.policy)
    print(json.dumps(resolution.to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    target = _write_task(args)
    print(str(target))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    capabilities = _loop_capabilities()
    if not capabilities["ready"]:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason_code": capabilities["reason_code"],
                    "detail": (
                        "The installed simplicio-loop lacks the required fail-closed quality "
                        "provider path. No unsafe local fallback was started."
                    ),
                    "loop": capabilities,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 3
    if any((args.global_policy, args.project_policy, args.policy)):
        raise PolicyError(
            "custom policies are diagnostic-only until Loop supports content-addressed "
            "policy delivery"
        )
    policy = _policy()
    ensure_authoritative_policy(policy)
    task = _write_task(args, policy)
    manifest = _extension_manifest()
    invoker = LoopInvoker()
    command = invoker.build_command(
        repository=args.repo,
        task_path=task,
        delivery=args.delivery,
        max_iterations=args.max_iterations,
        quality_provider=manifest["extension_id"],
        quality_policy=policy.policy_id,
        handshake_fingerprint=capabilities["runtime_fingerprint"],
    )
    completed = invoker.run(command)
    return int(completed.returncode)


def cmd_gate(args: argparse.Namespace) -> int:
    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    policy = _policy(args.global_policy, args.project_policy, args.policy)
    context = GateContext(
        expected_run_id=str(receipt.get("run_id") or ""),
        expected_task_id=str(receipt.get("task_id") or ""),
        expected_attempt_id=str(receipt.get("attempt_id") or ""),
        expected_source_sha=args.source_sha,
        expected_diff_hash=str(receipt.get("diff_hash") or ""),
        expected_policy_hash=policy.canonical_hash,
        artifact_root=Path(args.artifact_root),
    )
    verdict = evaluate_receipt(receipt, policy, context)
    payload = verdict.to_dict()
    if args.out:
        write_json_atomic(args.out, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if verdict.ready else 2


def _add_policy_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--global-policy", default="", help="global policy JSON overlay")
    parser.add_argument("--project-policy", default="", help="project policy JSON overlay")
    parser.add_argument("--policy", default="", help="CLI policy JSON overlay")


def _add_task_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", required=True, help="target repository")
    parser.add_argument("--issue", default="", help="optional source issue URL or identifier")
    _add_policy_arguments(parser)
    parser.add_argument("--out", default="", help="task/output path")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simplicio-loop-quality",
        description="Complete testing and quality layer executed by simplicio-loop",
    )
    parser.add_argument("-V", "--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="validate the Loop extension boundary")
    doctor.set_defaults(func=cmd_doctor)

    agents = sub.add_parser("agents", help="list declarative quality-agent profiles")
    agents.set_defaults(func=cmd_agents)

    manifest = sub.add_parser("manifest", help="print the loop-extension manifest")
    manifest.set_defaults(func=cmd_manifest)

    policy = sub.add_parser("policy", help="resolve and audit policy precedence")
    _add_policy_arguments(policy)
    policy.set_defaults(func=cmd_policy)

    plan = sub.add_parser("plan", help="render the strict quality task")
    _add_task_arguments(plan)
    plan.set_defaults(func=cmd_plan)

    run = sub.add_parser("run", help="invoke one authoritative simplicio-loop quality run")
    _add_task_arguments(run)
    run.add_argument("--delivery", choices=("verified",), default="verified")
    run.add_argument("--max-iterations", type=int, default=20)
    run.set_defaults(func=cmd_run)

    gate = sub.add_parser("gate", help="recompute a quality evidence verdict")
    gate.add_argument("--receipt", required=True)
    gate.add_argument("--source-sha", required=True, help="trusted source SHA supplied by Loop")
    gate.add_argument(
        "--artifact-root",
        required=True,
        help="trusted Loop artifact directory used to rehash every evidence item",
    )
    _add_policy_arguments(gate)
    gate.add_argument("--out", default="")
    gate.set_defaults(func=cmd_gate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError, json.JSONDecodeError, PolicyError, LoopUnavailable) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
