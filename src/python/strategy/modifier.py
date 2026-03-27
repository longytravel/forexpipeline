"""Strategy Modification — apply changes and create new versions (D10, FR73, FR12).

Applies structured modifications to a strategy specification, creating a new
versioned artifact. The previous version is never overwritten (immutability).

The modification primitives are deterministic and testable. Natural-language
interpretation lives in the Claude Code skill, not here.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomli_w
import tomllib

from artifacts.storage import crash_safe_write
from logging_setup.setup import get_logger
from strategy.hasher import compute_spec_hash
from strategy.loader import validate_strategy_spec
from strategy.specification import StrategySpecification
from strategy.storage import _clean_none_values
from strategy.versioner import (
    VersionDiff,
    VersionEntry,
    compute_version_diff,
    create_manifest,
    format_diff_text,
    increment_version,
    load_manifest,
    save_diff_artifact,
    save_manifest,
    update_manifest_version,
)

logger = get_logger("strategy.modifier")


@dataclass
class ModificationIntent:
    """A single intended modification to a specification."""

    field_path: str
    action: str  # "set", "add", "remove"
    new_value: Any
    description: str


@dataclass
class ModificationResult:
    """Result of applying modifications to a specification."""

    old_spec: StrategySpecification
    new_spec: StrategySpecification
    old_version: str
    new_version: str
    diff: VersionDiff
    saved_path: Path
    manifest_path: Path


# Field paths that are valid modification targets
_VALID_FIELD_PATHS = {
    "exit_rules.stop_loss.type",
    "exit_rules.stop_loss.value",
    "exit_rules.take_profit.type",
    "exit_rules.take_profit.value",
    "exit_rules.trailing",
    "entry_rules.filters",
    "entry_rules.conditions",
    "entry_rules.confirmation",
    "position_sizing.method",
    "position_sizing.risk_percent",
    "position_sizing.max_lots",
    "metadata.name",
    "metadata.timeframe",
}


def parse_modification_intent(structured_input: dict) -> list[ModificationIntent]:
    """Parse structured modification input into ModificationIntent list.

    Expected input format from Claude Code skill:
    {
        "modifications": [
            {"field": "exit_rules.stop_loss.value", "action": "set", "value": 2.0,
             "description": "wider stops"}
        ]
    }

    Args:
        structured_input: Dict with 'modifications' key.

    Returns:
        List of ModificationIntent.

    Raises:
        ValueError: If field path is invalid or input malformed.
    """
    modifications = structured_input.get("modifications", [])
    if not modifications:
        raise ValueError("No modifications specified")

    result: list[ModificationIntent] = []
    for mod in modifications:
        field_path = mod.get("field", "")
        action = mod.get("action", "set")
        value = mod.get("value")
        description = mod.get("description", "")

        # Validate field path
        if not _is_valid_field_path(field_path):
            raise ValueError(
                f"Unknown field path '{field_path}'. "
                f"Valid paths: {sorted(_VALID_FIELD_PATHS)}"
            )

        if action not in ("set", "add", "remove"):
            raise ValueError(f"Invalid action '{action}'. Must be set, add, or remove.")

        result.append(ModificationIntent(
            field_path=field_path,
            action=action,
            new_value=value,
            description=description,
        ))

    return result


def _is_valid_field_path(path: str) -> bool:
    """Check if a field path is a valid modification target."""
    # Exact match
    if path in _VALID_FIELD_PATHS:
        return True
    # Check if it's a sub-path of a valid path
    for valid in _VALID_FIELD_PATHS:
        if path.startswith(valid + ".") or path.startswith(valid + "["):
            return True
    return False


def apply_single_modification(
    spec: StrategySpecification, mod: ModificationIntent
) -> StrategySpecification:
    """Apply a single modification to a specification.

    Returns a modified copy — does NOT mutate original.

    Args:
        spec: Current specification.
        mod: Modification to apply.

    Returns:
        New StrategySpecification with modification applied.

    Raises:
        ValueError: If modification cannot be applied.
    """
    spec_dict = spec.model_dump(mode="python")
    modified = copy.deepcopy(spec_dict)

    parts = _parse_field_path(mod.field_path)

    try:
        if mod.action == "set":
            _set_nested(modified, parts, mod.new_value)
        elif mod.action == "add":
            _add_to_list(modified, parts, mod.new_value)
        elif mod.action == "remove":
            _remove_from_list(modified, parts, mod.new_value)
        else:
            raise ValueError(f"Unknown action: {mod.action}")
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(
            f"Cannot apply {mod.action} at path '{mod.field_path}': {e}"
        ) from e

    return StrategySpecification.model_validate(modified)


def _parse_field_path(path: str) -> list[str | int]:
    """Parse a dotted field path into components, handling array indices."""
    parts: list[str | int] = []
    for segment in path.split("."):
        if "[" in segment:
            # Handle array index like "conditions[0]"
            name, idx = segment.split("[", 1)
            parts.append(name)
            parts.append(int(idx.rstrip("]")))
        else:
            parts.append(segment)
    return parts


def _set_nested(d: dict, parts: list[str | int], value: Any) -> None:
    """Set a value at a nested path in a dict."""
    for i, part in enumerate(parts[:-1]):
        if isinstance(part, int):
            d = d[part]
        else:
            if part not in d:
                d[part] = {}
            d = d[part]

    final = parts[-1]
    if isinstance(final, int):
        d[final] = value
    else:
        d[final] = value


def _add_to_list(d: dict, parts: list[str | int], value: Any) -> None:
    """Add an item to a list at a nested path."""
    target = d
    for part in parts:
        if isinstance(part, int):
            target = target[part]
        else:
            target = target[part]

    if not isinstance(target, list):
        raise ValueError(f"Cannot add to non-list field at path")

    target.append(value)


def _remove_from_list(d: dict, parts: list[str | int], value: Any) -> None:
    """Remove an item from a list at a nested path."""
    target = d
    for part in parts:
        if isinstance(part, int):
            target = target[part]
        else:
            target = target[part]

    if not isinstance(target, list):
        raise ValueError(f"Cannot remove from non-list field at path")

    # Remove by index if value is int, otherwise by value match
    if isinstance(value, int) and 0 <= value < len(target):
        target.pop(value)
    else:
        # Try to remove by matching dict content
        for i, item in enumerate(target):
            if item == value:
                target.pop(i)
                break
        else:
            raise ValueError(f"Item not found in list for removal")


def find_latest_version(
    strategy_slug: str, artifacts_dir: Path
) -> tuple[str, Path]:
    """Find the highest version spec file for a strategy.

    Scans artifacts/strategies/{slug}/v*.toml for the highest version.

    Args:
        strategy_slug: Strategy identifier slug.
        artifacts_dir: Root artifacts directory.

    Returns:
        Tuple of (version_string, path_to_spec).

    Raises:
        FileNotFoundError: If no versions found.
    """
    artifacts_dir = Path(artifacts_dir).resolve()
    strategy_dir = artifacts_dir / "strategies" / strategy_slug

    if not strategy_dir.exists():
        raise FileNotFoundError(f"Strategy directory not found: {strategy_dir}")

    import re

    version_re = re.compile(r"^v(\d{3,})\.toml$")
    versions: list[tuple[int, str, Path]] = []

    for f in strategy_dir.iterdir():
        match = version_re.match(f.name)
        if match:
            num = int(match.group(1))
            ver_str = f"v{match.group(1)}"
            versions.append((num, ver_str, f))

    if not versions:
        raise FileNotFoundError(f"No specification versions in {strategy_dir}")

    versions.sort()
    _, ver_str, path = versions[-1]
    return ver_str, path


def apply_modifications(
    strategy_slug: str,
    modifications: list[ModificationIntent],
    artifacts_dir: Path,
) -> ModificationResult:
    """Apply modifications to a strategy, creating a new version.

    Steps:
    1. Load latest version spec
    2. Apply each modification sequentially
    3. Increment version, set status=draft, new timestamp
    4. Validate modified spec
    5. Save as new versioned artifact
    6. Compute diff
    7. Update manifest

    Args:
        strategy_slug: Strategy identifier slug.
        modifications: List of modifications to apply.
        artifacts_dir: Root artifacts directory.

    Returns:
        ModificationResult with old/new specs, diff, and paths.

    Raises:
        FileNotFoundError: If strategy not found.
        ValueError: If modification results in invalid spec.
    """
    artifacts_dir = Path(artifacts_dir).resolve()

    logger.info(
        "strategy_modification_start",
        extra={
            "strategy_slug": strategy_slug,
            "modifications_count": len(modifications),
        },
    )

    # Load latest version
    old_version, old_path = find_latest_version(strategy_slug, artifacts_dir)
    from strategy.loader import load_strategy_spec

    old_spec = load_strategy_spec(old_path)

    # Apply modifications sequentially
    current_spec = old_spec
    for mod in modifications:
        current_spec = apply_single_modification(current_spec, mod)

    # Increment version
    new_version = increment_version(old_version)

    # Update metadata for new version
    new_dict = current_spec.model_dump(mode="python")
    new_dict["metadata"]["version"] = new_version
    new_dict["metadata"]["status"] = "draft"
    new_dict["metadata"]["config_hash"] = None
    new_dict["metadata"]["confirmed_at"] = None

    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_dict["metadata"]["created_at"] = created_at

    new_spec = StrategySpecification.model_validate(new_dict)

    # Validate modified spec
    errors = validate_strategy_spec(new_spec)
    if errors:
        raise ValueError(
            f"Modified specification failed validation: {'; '.join(errors)}"
        )

    # Compute spec hash
    spec_hash = compute_spec_hash(new_spec)

    # Version collision guard
    strategy_dir = artifacts_dir / "strategies" / strategy_slug
    target_path = strategy_dir / f"{new_version}.toml"
    if target_path.exists():
        raise ValueError(
            f"Version collision: {target_path} already exists. "
            f"Cannot overwrite existing version (FR12 immutability)."
        )

    # Save new versioned artifact
    out_dict = new_spec.model_dump(mode="python")
    out_dict = _clean_none_values(out_dict)
    toml_content = tomli_w.dumps(out_dict)
    crash_safe_write(str(target_path), toml_content)

    # Compute diff
    diff = compute_version_diff(old_spec, new_spec)

    # Save diff artifact
    diff_text = format_diff_text(diff)
    save_diff_artifact(diff_text, strategy_slug, old_version, new_version, artifacts_dir)

    # Update manifest
    version_entry = VersionEntry(
        version=new_version,
        status="draft",
        created_at=created_at,
        confirmed_at=None,
        config_hash=None,
        spec_hash=spec_hash,
    )

    manifest = load_manifest(strategy_slug, artifacts_dir)
    if manifest is None:
        # Bootstrap manifest with the old version first, then add the new one
        old_spec_hash = compute_spec_hash(old_spec)
        old_entry = VersionEntry(
            version=old_version,
            status=old_spec.metadata.status or "draft",
            created_at=created_at,  # approximate — original timestamp unknown
            confirmed_at=None,
            config_hash=old_spec.metadata.config_hash,
            spec_hash=old_spec_hash,
        )
        manifest = create_manifest(strategy_slug, old_entry)
        manifest = update_manifest_version(manifest, version_entry)
    else:
        manifest = update_manifest_version(manifest, version_entry)

    manifest_path = save_manifest(manifest, artifacts_dir)

    logger.info(
        "strategy_modification_complete",
        extra={
            "strategy_slug": strategy_slug,
            "old_version": old_version,
            "new_version": new_version,
            "changes_count": len(diff.changes),
        },
    )

    return ModificationResult(
        old_spec=old_spec,
        new_spec=new_spec,
        old_version=old_version,
        new_version=new_version,
        diff=diff,
        saved_path=target_path,
        manifest_path=manifest_path,
    )
