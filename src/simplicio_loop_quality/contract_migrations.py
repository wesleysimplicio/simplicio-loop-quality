"""Deterministic, fail-closed compatibility receipts for legacy quality contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

MIGRATION_SCHEMA = "simplicio.quality-contract-migration/v1"
LEGACY_SCHEMAS = frozenset(
    {
        "simplicio.quality-plan/v1",
        "simplicio.quality-evidence/v1",
        "simplicio.quality-gate-verdict/v1",
    }
)


class ContractMigrationError(ValueError):
    """Raised when input cannot be migrated without inventing evidence."""


def canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def migrate_legacy_contract(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic BLOCKED receipt; legacy evidence must be reverified for v2."""

    if not isinstance(value, Mapping):
        raise ContractMigrationError("legacy contract must be an object")
    source_schema = value.get("schema")
    if source_schema == MIGRATION_SCHEMA:
        expected = {
            "schema",
            "source_schema",
            "source_hash",
            "status",
            "reason_code",
            "migrated",
        }
        if set(value) != expected:
            raise ContractMigrationError("migration receipt fields are ambiguous")
        if (
            value.get("source_schema") not in LEGACY_SCHEMAS
            or not isinstance(value.get("source_hash"), str)
            or len(value["source_hash"]) != 64
            or any(character not in "0123456789abcdef" for character in value["source_hash"])
            or value.get("status") != "BLOCKED"
            or value.get("reason_code") != "legacy_contract_requires_reverification"
            or value.get("migrated") is not None
        ):
            raise ContractMigrationError("migration receipt must remain fail-closed")
        return dict(value)
    if source_schema not in LEGACY_SCHEMAS:
        raise ContractMigrationError("unsupported legacy contract schema")
    return {
        "schema": MIGRATION_SCHEMA,
        "source_schema": source_schema,
        "source_hash": canonical_hash(value),
        "status": "BLOCKED",
        "reason_code": "legacy_contract_requires_reverification",
        "migrated": None,
    }
