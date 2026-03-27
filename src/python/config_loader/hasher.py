"""Deterministic config hashing (D7, FR8/FR61).

Same config dict always produces the same SHA-256 hash regardless of key insertion order.
"""
import hashlib
import json


def compute_config_hash(config: dict) -> str:
    """Compute SHA-256 hash of config dict.

    Serializes to canonical JSON (sorted keys, no whitespace, no internal keys).
    Returns the hex digest.
    """
    # Strip internal keys (prefixed with _) before hashing
    cleaned = _strip_internal_keys(config)
    canonical = json.dumps(cleaned, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _strip_internal_keys(d: dict) -> dict:
    """Recursively remove keys starting with '_' (e.g. _env)."""
    result = {}
    for k, v in d.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict):
            result[k] = _strip_internal_keys(v)
        else:
            result[k] = v
    return result
