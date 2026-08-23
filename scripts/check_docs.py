#!/usr/bin/env python3
"""Dependency-free documentation and runbook contract check."""

from __future__ import annotations

import sys
from pathlib import Path

REQUIRED = {
    "docs/ARCHITECTURE.md": ("Completion Oracle", "Loop"),
    "docs/QUALITY_CONTRACT.md": ("PASS", "BLOCKED", "evidence"),
    "docs/OPERATIONS.md": ("Recovery", "cancellation", "waiver"),
    "docs/ADAPTER_AUTHORING.md": ("ProcessSpec", "scheduler", "unit tests"),
}


def check_docs(root: Path) -> list[str]:
    errors = []
    for relative, markers in REQUIRED.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"missing: {relative}")
            continue
        text = path.read_text(encoding="utf-8").lower()
        for marker in markers:
            if marker.lower() not in text:
                errors.append(f"{relative}: missing marker {marker}")
    return errors


def main() -> int:
    errors = check_docs(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
