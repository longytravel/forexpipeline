"""Deterministic Strategy Specification Hashing (D7, FR18/FR61).

Same spec always produces the same SHA-256 hash regardless of field order.
Follows compute_config_hash() pattern from config_loader/hasher.py:
canonical JSON (sorted keys, no whitespace) -> SHA-256.
"""

from __future__ import annotations

import hashlib
import json

from strategy.specification import StrategySpecification


# Lifecycle metadata fields excluded from content hash — these change
# independently of strategy content (status transitions, timestamps).
_LIFECYCLE_FIELDS = {"status", "config_hash", "confirmed_at", "created_at", "version"}


def compute_spec_hash(spec: StrategySpecification) -> str:
    """Compute SHA-256 content hash of a strategy specification.

    Serializes to canonical JSON (sorted keys, no whitespace),
    stripping internal/transient fields (prefixed with '_') and
    lifecycle metadata (status, config_hash, timestamps) so the
    hash reflects only strategy content.

    Args:
        spec: Validated StrategySpecification instance.

    Returns:
        Hex digest of the SHA-256 hash.
    """
    raw = spec.model_dump(mode="python")
    cleaned = _strip_internal_keys(raw)
    _strip_lifecycle_fields(cleaned)
    canonical = json.dumps(cleaned, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_spec_hash(spec: StrategySpecification, expected_hash: str) -> bool:
    """Compare computed hash vs stored/expected hash.

    Args:
        spec: Validated StrategySpecification instance.
        expected_hash: The expected hex digest.

    Returns:
        True if hashes match.
    """
    return compute_spec_hash(spec) == expected_hash


def _strip_lifecycle_fields(d: dict) -> None:
    """Remove lifecycle metadata fields from spec dict before hashing.

    Modifies dict in-place. Only strips from the top-level 'metadata' key.
    """
    if "metadata" in d and isinstance(d["metadata"], dict):
        for field in _LIFECYCLE_FIELDS:
            d["metadata"].pop(field, None)


def _strip_internal_keys(d: dict) -> dict:
    """Recursively remove keys starting with '_' (transient/internal)."""
    result = {}
    for k, v in d.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict):
            result[k] = _strip_internal_keys(v)
        elif isinstance(v, list):
            result[k] = [
                _strip_internal_keys(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            result[k] = v
    return result
