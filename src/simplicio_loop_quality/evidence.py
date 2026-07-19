"""Canonical hashing and atomic evidence persistence."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def evidence_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def write_json_atomic(path: str | Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try:
        temporary.write_text(rendered, encoding="utf-8")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target
