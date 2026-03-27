"""Strategy Versioning — version management, diffs, and manifest (D10, FR12, FR58).

Provides version incrementing, field-level diff computation, and manifest
management for strategy specification lifecycle.

Manifest is JSON (not TOML) — it's artifact metadata, not configuration (D7 scope).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from artifacts.storage import crash_safe_write
from logging_setup.setup import get_logger
from strategy.specification import StrategySpecification

logger = get_logger("strategy.versioner")


@dataclass
class FieldChange:
    """A single field-level change between spec versions."""

    field_path: str
    old_value: str
    new_value: str
    description: str


@dataclass
class VersionDiff:
    """Diff between two specification versions."""

    old_version: str
    new_version: str
    changes: list[FieldChange]


@dataclass
class VersionEntry:
    """A single version record in the manifest."""

    version: str
    status: str
    created_at: str
    confirmed_at: str | None
    config_hash: str | None
    spec_hash: str


@dataclass
class SpecificationManifest:
    """Version history manifest for a strategy."""

    strategy_slug: str
    versions: list[VersionEntry]
    current_version: str
    latest_confirmed_version: str | None


# --- Metadata fields to ignore in diffs (expected to differ between versions) ---
_DIFF_IGNORE_FIELDS = {
    "metadata.version", "metadata.config_hash", "metadata.status",
    "metadata.created_at", "metadata.confirmed_at",
}


def increment_version(current_version: str) -> str:
    """Increment a version string.

    Args:
        current_version: Current version (e.g., "v001").

    Returns:
        Next version string (e.g., "v002"). Zero-padded to 3 digits minimum.
    """
    num = int(current_version[1:])
    next_num = num + 1
    if next_num < 1000:
        return f"v{next_num:03d}"
    return f"v{next_num}"


def compute_version_diff(
    old_spec: StrategySpecification, new_spec: StrategySpecification
) -> VersionDiff:
    """Deep-compare two specifications and produce a field-level diff.

    Ignores metadata fields that are expected to differ (version, timestamps, hashes).
    Compares nested structures recursively.

    Args:
        old_spec: Previous version specification.
        new_spec: New version specification.

    Returns:
        VersionDiff with list of FieldChange entries.
    """
    old_dict = old_spec.model_dump(mode="python")
    new_dict = new_spec.model_dump(mode="python")

    changes: list[FieldChange] = []
    _compare_dicts(old_dict, new_dict, "", changes)

    return VersionDiff(
        old_version=old_spec.metadata.version,
        new_version=new_spec.metadata.version,
        changes=changes,
    )


def _compare_dicts(
    old: dict, new: dict, prefix: str, changes: list[FieldChange]
) -> None:
    """Recursively compare two dicts and collect FieldChange entries."""
    all_keys = sorted(set(list(old.keys()) + list(new.keys())))

    for key in all_keys:
        path = f"{prefix}.{key}" if prefix else key

        # Skip metadata fields that are expected to change
        if path in _DIFF_IGNORE_FIELDS:
            continue

        old_val = old.get(key)
        new_val = new.get(key)

        if old_val == new_val:
            continue

        if old_val is None and new_val is not None:
            changes.append(FieldChange(
                field_path=path,
                old_value="(none)",
                new_value=_format_value(new_val),
                description=f"{_humanize_path(path)} added: {_format_value(new_val)}",
            ))
        elif old_val is not None and new_val is None:
            changes.append(FieldChange(
                field_path=path,
                old_value=_format_value(old_val),
                new_value="(none)",
                description=f"{_humanize_path(path)} removed",
            ))
        elif isinstance(old_val, dict) and isinstance(new_val, dict):
            _compare_dicts(old_val, new_val, path, changes)
        elif isinstance(old_val, list) and isinstance(new_val, list):
            _compare_lists(old_val, new_val, path, changes)
        else:
            changes.append(FieldChange(
                field_path=path,
                old_value=str(old_val),
                new_value=str(new_val),
                description=f"{_humanize_path(path)} changed from {old_val} to {new_val}",
            ))


def _compare_lists(
    old: list, new: list, path: str, changes: list[FieldChange]
) -> None:
    """Compare two lists and collect changes."""
    max_len = max(len(old), len(new))

    for i in range(max_len):
        item_path = f"{path}[{i}]"
        if i >= len(old):
            changes.append(FieldChange(
                field_path=item_path,
                old_value="(none)",
                new_value=_format_value(new[i]),
                description=f"{_humanize_path(path)} item added: {_format_value(new[i])}",
            ))
        elif i >= len(new):
            changes.append(FieldChange(
                field_path=item_path,
                old_value=_format_value(old[i]),
                new_value="(none)",
                description=f"{_humanize_path(path)} item removed: {_format_value(old[i])}",
            ))
        elif old[i] != new[i]:
            if isinstance(old[i], dict) and isinstance(new[i], dict):
                _compare_dicts(old[i], new[i], item_path, changes)
            else:
                changes.append(FieldChange(
                    field_path=item_path,
                    old_value=str(old[i]),
                    new_value=str(new[i]),
                    description=f"{_humanize_path(item_path)} changed from {old[i]} to {new[i]}",
                ))


def _format_value(val: object) -> str:
    """Format a value for display in diffs — plain English, no raw dict/list repr."""
    if isinstance(val, dict):
        parts = []
        for k, v in val.items():
            parts.append(f"{k}: {_format_value(v)}")
        return ", ".join(parts)
    if isinstance(val, list):
        return ", ".join(_format_value(item) for item in val)
    return str(val)


def _humanize_path(path: str) -> str:
    """Convert a field path to human-readable form."""
    # Remove leading dots, replace dots with spaces, clean up
    path = path.lstrip(".")
    replacements = {
        "exit_rules.stop_loss.value": "Stop loss value",
        "exit_rules.stop_loss.type": "Stop loss type",
        "exit_rules.take_profit.value": "Take profit value",
        "exit_rules.take_profit.type": "Take profit type",
        "exit_rules.trailing": "Trailing stop",
        "position_sizing.risk_percent": "Risk per trade",
        "position_sizing.method": "Sizing method",
        "position_sizing.max_lots": "Max lots",
        "metadata.name": "Strategy name",
        "metadata.pair": "Pair",
        "metadata.timeframe": "Timeframe",
    }
    for field_path, display in replacements.items():
        if path == field_path:
            return display
    # Fallback: capitalize and replace underscores
    return path.replace("_", " ").replace(".", " > ")


def format_diff_text(diff: VersionDiff) -> str:
    """Render a VersionDiff as plain English change list.

    Deterministic: identical diffs produce identical output.

    Args:
        diff: VersionDiff to format.

    Returns:
        Formatted multi-line string.
    """
    if not diff.changes:
        return f"No changes between {diff.old_version} and {diff.new_version}."

    lines: list[str] = [f"Changes ({diff.old_version} → {diff.new_version}):"]
    for change in diff.changes:
        lines.append(f"  * {change.description}")

    return "\n".join(lines)


def save_diff_artifact(
    diff_text: str,
    strategy_slug: str,
    old_version: str,
    new_version: str,
    artifacts_dir: Path,
) -> Path:
    """Save formatted diff as a persistent artifact.

    Layout: artifacts_dir/strategies/{slug}/diffs/{old}_{new}_diff.txt

    Uses crash-safe write pattern (NFR15).

    Args:
        diff_text: Formatted diff text.
        strategy_slug: Strategy identifier slug.
        old_version: Old version string.
        new_version: New version string.
        artifacts_dir: Root artifacts directory.

    Returns:
        Path to the saved diff file.
    """
    artifacts_dir = Path(artifacts_dir).resolve()
    diffs_dir = artifacts_dir / "strategies" / strategy_slug / "diffs"
    diffs_dir.mkdir(parents=True, exist_ok=True)

    output_path = diffs_dir / f"{old_version}_{new_version}_diff.txt"
    crash_safe_write(str(output_path), diff_text)

    logger.info(
        "version_diff_artifact_saved",
        extra={
            "strategy_slug": strategy_slug,
            "old_version": old_version,
            "new_version": new_version,
            "path": str(output_path),
        },
    )
    return output_path


def load_manifest(
    strategy_slug: str, artifacts_dir: Path
) -> SpecificationManifest | None:
    """Load manifest from JSON file.

    Args:
        strategy_slug: Strategy identifier slug.
        artifacts_dir: Root artifacts directory.

    Returns:
        SpecificationManifest or None if not found.
    """
    artifacts_dir = Path(artifacts_dir).resolve()
    manifest_path = artifacts_dir / "strategies" / strategy_slug / "manifest.json"

    if not manifest_path.exists():
        return None

    with open(manifest_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    versions = [
        VersionEntry(
            version=v["version"],
            status=v["status"],
            created_at=v["created_at"],
            confirmed_at=v.get("confirmed_at"),
            config_hash=v.get("config_hash"),
            spec_hash=v["spec_hash"],
        )
        for v in raw["versions"]
    ]

    return SpecificationManifest(
        strategy_slug=raw["strategy_slug"],
        versions=versions,
        current_version=raw["current_version"],
        latest_confirmed_version=raw.get("latest_confirmed_version"),
    )


def save_manifest(manifest: SpecificationManifest, artifacts_dir: Path) -> Path:
    """Save manifest to JSON file using crash-safe write.

    Args:
        manifest: SpecificationManifest to save.
        artifacts_dir: Root artifacts directory.

    Returns:
        Path to saved manifest file.
    """
    artifacts_dir = Path(artifacts_dir).resolve()
    strategy_dir = artifacts_dir / "strategies" / manifest.strategy_slug
    strategy_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = strategy_dir / "manifest.json"

    data = {
        "strategy_slug": manifest.strategy_slug,
        "current_version": manifest.current_version,
        "latest_confirmed_version": manifest.latest_confirmed_version,
        "versions": [
            {
                "version": v.version,
                "status": v.status,
                "created_at": v.created_at,
                "confirmed_at": v.confirmed_at,
                "config_hash": v.config_hash,
                "spec_hash": v.spec_hash,
            }
            for v in manifest.versions
        ],
    }

    content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    crash_safe_write(str(manifest_path), content)

    logger.info(
        "manifest_updated",
        extra={
            "strategy_slug": manifest.strategy_slug,
            "version": manifest.current_version,
            "event_type": "saved",
        },
    )
    return manifest_path


def create_manifest(
    strategy_slug: str, version_entry: VersionEntry
) -> SpecificationManifest:
    """Create a new manifest with an initial version entry.

    Args:
        strategy_slug: Strategy identifier slug.
        version_entry: Initial version entry.

    Returns:
        New SpecificationManifest.
    """
    latest_confirmed = (
        version_entry.version if version_entry.status == "confirmed" else None
    )
    return SpecificationManifest(
        strategy_slug=strategy_slug,
        versions=[version_entry],
        current_version=version_entry.version,
        latest_confirmed_version=latest_confirmed,
    )


def update_manifest_version(
    manifest: SpecificationManifest, version_entry: VersionEntry
) -> SpecificationManifest:
    """Add or update a version entry in the manifest.

    If the version already exists, update it. Otherwise, add it.
    Always updates current_version. Updates latest_confirmed_version
    only if the entry is confirmed.

    Args:
        manifest: Existing manifest.
        version_entry: Version entry to add/update.

    Returns:
        Updated SpecificationManifest (new object, original not mutated).
    """
    # Copy versions list
    new_versions = list(manifest.versions)

    # Find existing version entry
    found = False
    for i, v in enumerate(new_versions):
        if v.version == version_entry.version:
            new_versions[i] = version_entry
            found = True
            break

    if not found:
        new_versions.append(version_entry)

    # Update confirmed pointer
    latest_confirmed = manifest.latest_confirmed_version
    if version_entry.status == "confirmed":
        latest_confirmed = version_entry.version

    # current_version tracks the highest version (by numeric value), not
    # just the entry being updated — prevents regression when confirming
    # an older version after a newer draft exists.
    def _version_num(v: str) -> int:
        return int(v.lstrip("v"))

    highest_version = max(
        (v.version for v in new_versions), key=_version_num
    )

    return SpecificationManifest(
        strategy_slug=manifest.strategy_slug,
        versions=new_versions,
        current_version=highest_version,
        latest_confirmed_version=latest_confirmed,
    )
