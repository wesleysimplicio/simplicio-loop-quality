import ast
import unittest
from pathlib import Path

SOURCE_ROOTS = (Path("src/simplicio_loop_quality"), Path("scripts"))
FORBIDDEN_MODULES = {"threading", "multiprocessing", "concurrent.futures"}
FORBIDDEN_CALLS = {
    "os.system",
    "os.popen",
    "asyncio.create_subprocess_exec",
    "asyncio.create_subprocess_shell",
    "__import__",
    "eval",
    "exec",
}
FORBIDDEN_NAME_PARTS = (
    "scheduler",
    "worker_pool",
    "worktree_manager",
    "lease_manager",
    "process_supervisor",
    "daemon",
)


def python_files():
    return [path for root in SOURCE_ROOTS for path in root.rglob("*.py")]


def qualified_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


class ArchitectureBoundaryTest(unittest.TestCase):
    def test_runtime_has_no_duplicate_orchestration_modules(self):
        offenders = [
            str(path)
            for path in python_files()
            if any(part in path.stem.lower() for part in FORBIDDEN_NAME_PARTS)
        ]
        self.assertEqual(offenders, [])

    def test_only_thin_loop_invoker_owns_one_subprocess_call(self):
        subprocess_imports = []
        subprocess_calls = []
        forbidden_imports = []
        forbidden_calls = []
        for path in python_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                else:
                    modules = []
                if "subprocess" in modules:
                    subprocess_imports.append(str(path))
                forbidden_imports.extend(
                    f"{path}:{module}" for module in modules if module in FORBIDDEN_MODULES
                )
                if isinstance(node, ast.Call):
                    name = qualified_name(node.func)
                    if name.startswith("subprocess."):
                        subprocess_calls.append(f"{path}:{name}")
                    if name in FORBIDDEN_CALLS:
                        forbidden_calls.append(f"{path}:{name}")
        expected = str(Path("src/simplicio_loop_quality/loop_invoker.py"))
        self.assertEqual(subprocess_imports, [expected])
        self.assertTrue(all(call == f"{expected}:subprocess.run" for call in subprocess_calls))
        self.assertEqual(forbidden_imports, [])
        self.assertEqual(forbidden_calls, [])
