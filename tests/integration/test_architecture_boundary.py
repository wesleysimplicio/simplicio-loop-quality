import ast
import unittest
from pathlib import Path


class ArchitectureBoundaryTest(unittest.TestCase):
    def test_runtime_has_no_duplicate_orchestration_modules(self):
        forbidden_names = {
            "scheduler.py",
            "queue.py",
            "worker_pool.py",
            "worktree_manager.py",
            "lease_manager.py",
            "process_supervisor.py",
            "daemon.py",
        }
        files = list(Path("src/simplicio_loop_quality").rglob("*.py"))
        self.assertFalse(forbidden_names & {path.name for path in files})

    def test_only_thin_loop_invoker_imports_subprocess(self):
        offenders = []
        for path in Path("src/simplicio_loop_quality").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                if any(name == "subprocess" for name in names) and path.name != "loop_invoker.py":
                    offenders.append(str(path))
        self.assertEqual(offenders, [])
