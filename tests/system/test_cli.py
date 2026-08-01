import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from simplicio_loop_quality import cli
from tests.helpers import passing_receipt


class CliSystemTest(unittest.TestCase):
    def test_plan_creates_task_for_real_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "quality-task.md"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(["plan", "--repo", tmp, "--out", str(out)])
            self.assertEqual(code, 0)
            self.assertTrue(out.exists())
            self.assertIn("complete Simplicio quality layer", out.read_text(encoding="utf-8"))

    def test_default_task_path_does_not_dirty_target_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(["plan", "--repo", tmp])
            task = Path(stdout.getvalue().strip())
            self.assertEqual(code, 0)
            self.assertTrue(task.is_file())
            self.assertFalse(task.is_relative_to(Path(tmp)))

    def test_gate_cli_writes_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "receipt.json"
            verdict = Path(tmp) / "verdict.json"
            payload = passing_receipt(artifact_root=tmp)
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(
                    [
                        "gate",
                        "--receipt",
                        str(receipt),
                        "--source-sha",
                        payload["source_sha"],
                        "--artifact-root",
                        tmp,
                        "--out",
                        str(verdict),
                    ]
                )
            self.assertEqual(code, 2)
            payload = json.loads(verdict.read_text())
            self.assertEqual(payload["status"], "BLOCKED")
            self.assertEqual(payload["reason_code"], "verification_context_untrusted")

    def test_run_fails_closed_when_upstream_hook_is_missing(self):
        capabilities = {
            "ready": False,
            "reason_code": "missing_quality_provider_hook",
        }
        stderr = io.StringIO()
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(cli, "_loop_capabilities", return_value=capabilities),
            contextlib.redirect_stderr(stderr),
        ):
            code = cli.main(["run", "--repo", tmp])
        self.assertEqual(code, 3)
        self.assertIn("No unsafe local fallback", stderr.getvalue())

    def test_run_rejects_custom_policy_until_content_addressed_delivery_exists(self):
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / "policy.json"
            policy.write_text(
                json.dumps(
                    {
                        "schema": "simplicio.quality-policy/v1",
                        "policy_id": "custom",
                        "coverage": {
                            "global_min_pct": 85,
                            "changed_min_pct": 90,
                            "critical_min_pct": 100,
                        },
                        "na_requires_independent_approval": True,
                        "reject_statuses": ["skipped", "xfail", "flaky", "not_run", "unknown"],
                        "lanes": ["unit"],
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    cli,
                    "_loop_capabilities",
                    return_value={"ready": True, "reason_code": "ready"},
                ),
                contextlib.redirect_stderr(stderr),
            ):
                code = cli.main(["run", "--repo", tmp, "--policy", str(policy)])
        self.assertEqual(code, 2)
        self.assertIn("custom policies are diagnostic-only", stderr.getvalue())

    def test_plan_applies_global_project_cli_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layers = {
                "global.json": {"coverage": {"global_min_pct": 86}},
                "project.json": {"coverage": {"global_min_pct": 87}},
                "cli.json": {"coverage": {"global_min_pct": 88}},
            }
            for name, payload in layers.items():
                (root / name).write_text(json.dumps(payload), encoding="utf-8")
            task = root / "task.md"
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(
                    [
                        "plan",
                        "--repo",
                        tmp,
                        "--global-policy",
                        str(root / "global.json"),
                        "--project-policy",
                        str(root / "project.json"),
                        "--policy",
                        str(root / "cli.json"),
                        "--out",
                        str(task),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertIn(">= 88.0%", task.read_text(encoding="utf-8"))

    def test_gate_rejects_weak_policy_before_evidence_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = root / "receipt.json"
            weak = root / "weak.json"
            receipt.write_text(json.dumps(passing_receipt(artifact_root=tmp)), encoding="utf-8")
            weak.write_text(json.dumps({"coverage": {"global_min_pct": 1}}), encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = cli.main(
                    [
                        "gate",
                        "--receipt",
                        str(receipt),
                        "--source-sha",
                        "a" * 40,
                        "--artifact-root",
                        tmp,
                        "--policy",
                        str(weak),
                    ]
                )
            self.assertEqual(code, 2)
            self.assertIn("cannot lower coverage.global_min_pct", stderr.getvalue())

    def test_agents_manifest_and_policy_are_machine_readable(self):
        for command in ("agents", "manifest", "policy"):
            with self.subTest(command=command):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli.main([command])
                self.assertEqual(code, 0)
                self.assertTrue(json.loads(stdout.getvalue()))
