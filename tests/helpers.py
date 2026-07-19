from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from simplicio_loop_quality.policy import QualityPolicy, load_strict_policy


def passing_receipt(
    policy: QualityPolicy | None = None,
    *,
    artifact_root: str | Path,
) -> dict[str, Any]:
    policy = policy or load_strict_policy()
    root = Path(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    source_sha = "a" * 40
    run_id = "run-1"
    task_id = "task-1"
    attempt_id = "attempt-1"
    lanes: dict[str, Any] = {}
    for lane in policy.lanes:
        ref = Path("artifacts") / f"{lane}.json"
        artifact = root / ref
        artifact.parent.mkdir(parents=True, exist_ok=True)
        content = f'{{"lane":"{lane}","status":"PASS"}}\n'.encode()
        artifact.write_bytes(content)
        lanes[lane] = {
            "status": "pass",
            "evidence": [
                {
                    "ref": ref.as_posix(),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "source_sha": source_sha,
                    "run_id": run_id,
                    "task_id": task_id,
                    "attempt_id": attempt_id,
                    "process_id": f"process-{lane}",
                    "tool_name": "fixture-runner",
                    "tool_version": "1.0.0",
                    "command": ["fixture-runner", lane],
                    "exit_code": 0,
                    "duration_ms": 1.0,
                    "environment_hash": "d" * 64,
                    "seed": None,
                }
            ],
        }
    return {
        "schema": "simplicio.quality-evidence/v1",
        "run_id": run_id,
        "task_id": task_id,
        "attempt_id": attempt_id,
        "source_sha": source_sha,
        "diff_hash": "b" * 64,
        "generated_at": "2026-07-19T12:00:00Z",
        "policy_hash": policy.canonical_hash,
        "producer_agent": "test-agent",
        "audit_agent": "evidence-audit-agent",
        "lanes": lanes,
        "coverage": {
            "global_pct": policy.coverage.global_min_pct,
            "changed_pct": policy.coverage.changed_min_pct,
            "critical_pct": policy.coverage.critical_min_pct,
            "reason_code": None,
        },
    }
