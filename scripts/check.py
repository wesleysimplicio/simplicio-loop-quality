#!/usr/bin/env python3
"""Dependency-free local gate for the repository bootstrap."""

from __future__ import annotations

import compileall
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT))


def main() -> int:
    compiled = compileall.compile_dir(SRC, quiet=1)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if compiled and result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
