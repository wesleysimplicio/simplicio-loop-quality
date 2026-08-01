"""Productive Loop extension entry point for the Quality provider."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import resources
from types import MappingProxyType
from typing import Any

from simplicio_loop_quality.contract_validation import validate_contract_document


def _manifest() -> dict[str, Any]:
    resource = resources.files("simplicio_loop_quality.contracts").joinpath("loop-extension.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def _role_binding(request: Any = None, **_kwargs: Any) -> dict[str, Any]:
    """Reject direct role execution; stage dispatch must arrive through the Loop Hub."""

    if not isinstance(request, Mapping):
        return {
            "schema": "simplicio.quality-provider-binding-result/v1",
            "status": "BLOCKED",
            "reason_code": "INVALID_ROLE_REQUEST",
            "terminal": False,
        }
    return {
        "schema": "simplicio.quality-provider-binding-result/v1",
        "status": "BLOCKED",
        "reason_code": "HUB_STAGE_DISPATCH_REQUIRED",
        "terminal": False,
    }


def _publish_quality_receipt(receipt: Any = None, **_kwargs: Any) -> dict[str, Any]:
    """Validate a receipt but never publish or grant terminal authority locally."""

    errors = validate_contract_document(receipt)
    return {
        "schema": "simplicio.quality-provider-binding-result/v1",
        "status": "VALIDATED" if not errors else "BLOCKED",
        "reason_code": "RECEIPT_VALIDATED" if not errors else "INVALID_QUALITY_RECEIPT",
        "errors": tuple(errors),
        "terminal": False,
    }


@dataclass(frozen=True)
class QualityProviderRuntime:
    manifest: Mapping[str, Any]
    bindings: Mapping[str, Callable[..., Any]]


def provider() -> QualityProviderRuntime:
    """Return an immutable runtime object consumed by Loop's extension registry."""

    manifest = _manifest()
    role_ids = [row["role_id"] for row in manifest["role_bindings"]]
    effect_ids = [row["effect_id"] for row in manifest["effect_handlers"]]
    bindings: dict[str, Callable[..., Any]] = {role_id: _role_binding for role_id in role_ids}
    bindings.update({effect_id: _publish_quality_receipt for effect_id in effect_ids})
    return QualityProviderRuntime(MappingProxyType(manifest), MappingProxyType(bindings))
