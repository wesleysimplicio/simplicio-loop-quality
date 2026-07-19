"""Command-line interface for the quality extension."""

from __future__ import annotations

import argparse
import inspect
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
from .policy import (
    PolicyError,
    ensure_authoritative_policy,
    load_policy,
    load_strict_policy,
)


def _policy(path: str = ""):
    return load_policy(path) if path else load_strict_policy()


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
    with suppress(metadata.PackageNotFoundError):
        result["version"] = metadata.version("simplicio-loop")
    try:
        from simplicio_loop import __version__ as loop_module_version
        from simplicio_loop import extension_manifest, oracle, runner
    except ImportError:
        return result
    result["installed"] = True
    result["version"] = result["version"] or loop_module_version
    manifest = _extension_manifest()
    core_requirement = manifest["requires_core"]
    actual_version = _version_triplet(result["version"])
    minimum = _version_triplet(core_requirement["min_version"])
    maximum = _version_triplet(core_requirement["max_version"])
    result["version_compatible"] = bool(
        actual_version
        and minimum
        and maximum
        and minimum <= actual_version <= maximum
    )
    errors = extension_manifest.validate_manifest(manifest)
    result["manifest_valid"] = not errors
    result["manifest_errors"] = errors
    result["extension_handshake"] = callable(
        getattr(extension_manifest, "extension_handshake", None)
    )
    params = inspect.signature(runner.conduct_run).parameters
    result["quality_provider_hook"] = "quality_provider" in params
    result["completion_oracle"] = callable(
        getattr(oracle, "evaluate_completion", None)
    ) and bool(getattr(runner, "ORACLE_IS_TERMINAL_AUTHORITY", False))
    result["terminal_run_outcome"] = (
        getattr(runner, "RUN_OUTCOME_SCHEMA", None) == "simplicio.run-outcome/v1"
        and bool(getattr(runner, "RUN_EXIT_IS_TERMINAL", False))
    )
    missing = [
        name
        for name, present in (
            ("manifest", result["manifest_valid"]),
            ("core_version", result["version_compatible"]),
            ("extension_handshake", result["extension_handshake"]),
            ("quality_provider_hook", result["quality_provider_hook"]),
            ("completion_oracle", result["completion_oracle"]),
            ("terminal_run_outcome", result["terminal_run_outcome"]),
        )
        if not present
    ]
    result["ready"] = not missing
    result["reason_code"] = "ready" if not missing else "missing_" + "_and_".join(missing)
    return result


def _write_task(args: argparse.Namespace, policy=None) -> Path:
    policy = policy or _policy(args.policy)
    text = render_quality_task(args.repo, policy, source_issue=args.issue)
    if args.out:
        target = Path(args.out).resolve()
    else:
        run_id = f"quality-{uuid.uuid4().hex[:12]}"
        target = (
            Path(tempfile.gettempdir())
            / "simplicio-loop-quality"
            / "tasks"
            / run_id
            / "task.md"
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
    if args.policy:
        raise PolicyError(
            "custom policies are diagnostic-only until Loop supports content-addressed "
            "policy delivery"
        )
    policy = _policy(args.policy)
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
        quality_policy_hash=policy.canonical_hash,
    )
    completed = invoker.run(command)
    return int(completed.returncode)


def cmd_gate(args: argparse.Namespace) -> int:
    receipt = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    context = GateContext(
        expected_run_id=str(receipt.get("run_id") or ""),
        expected_task_id=str(receipt.get("task_id") or ""),
        expected_attempt_id=str(receipt.get("attempt_id") or ""),
        expected_source_sha=args.source_sha,
        expected_diff_hash=str(receipt.get("diff_hash") or ""),
        expected_policy_hash=str(receipt.get("policy_hash") or ""),
        artifact_root=Path(args.artifact_root),
    )
    verdict = evaluate_receipt(receipt, _policy(args.policy), context)
    payload = verdict.to_dict()
    if args.out:
        write_json_atomic(args.out, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if verdict.ready else 2


def _add_task_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", required=True, help="target repository")
    parser.add_argument("--issue", default="", help="optional source issue URL or identifier")
    parser.add_argument(
        "--policy",
        default="",
        help="policy JSON; strict packaged policy by default",
    )
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
    gate.add_argument("--policy", default="")
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
