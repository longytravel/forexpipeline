"""Versioned cost model storage with crash-safe writes (Story 2.6).

Handles save/load of cost model JSON artifacts and manifest management.
All writes use crash_safe_write() for atomic file operations (NFR15).
Versions are immutable — never overwritten.

Source: architecture.md — D2, D7; FR20, FR60; NFR15.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from artifacts.storage import crash_safe_write
from cost_model.schema import CostModelArtifact, validate_cost_model
from logging_setup.setup import get_logger

_log = get_logger("cost_model.storage")

_VERSION_RE = re.compile(r"^v(\d{3,})$")


def _artifact_dir(pair: str, artifacts_dir: Path) -> Path:
    """Return the directory for a pair's cost model artifacts."""
    return Path(artifacts_dir).resolve() / "cost_models" / pair


def _version_path(pair: str, version: str, artifacts_dir: Path) -> Path:
    return _artifact_dir(pair, artifacts_dir) / f"{version}.json"


def _manifest_path(pair: str, artifacts_dir: Path) -> Path:
    return _artifact_dir(pair, artifacts_dir) / "manifest.json"


def _compute_hash(content: str) -> str:
    """Compute SHA-256 hash with sha256: prefix for self-describing format."""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _discover_schema_path(artifacts_dir: Path) -> Path | None:
    """Try to find cost_model_schema.toml relative to artifacts_dir."""
    # artifacts_dir is typically <project>/artifacts; schema at <project>/contracts/
    project_root = Path(artifacts_dir).resolve().parent
    candidate = project_root / "contracts" / "cost_model_schema.toml"
    if candidate.exists():
        return candidate
    return None


def save_cost_model(
    artifact: CostModelArtifact,
    artifacts_dir: Path,
    schema_path: Path | None = None,
) -> Path:
    """Save cost model artifact as JSON via crash-safe write.

    Validates against schema before saving. If schema_path is not provided,
    attempts to auto-discover it from the project structure.

    Args:
        artifact: The cost model artifact to save.
        artifacts_dir: Root artifacts directory.
        schema_path: Path to schema for validation before save.
            Auto-discovered if not provided.

    Returns:
        Path to the saved artifact file.

    Raises:
        FileExistsError: If the version file already exists (immutable versioning).
        ValueError: If schema validation fails.
    """
    dest = _version_path(artifact.pair, artifact.version, artifacts_dir)

    if dest.exists():
        raise FileExistsError(
            f"Version collision: {dest} already exists. "
            f"Cost model versions are immutable — use get_next_version() "
            f"to determine the next available version."
        )

    # Auto-discover schema if not provided (AC5: always validate before save)
    resolved_schema = schema_path or _discover_schema_path(artifacts_dir)
    if resolved_schema is not None:
        errors = validate_cost_model(artifact, resolved_schema)
        if errors:
            raise ValueError(
                f"Schema validation failed before save: {errors}"
            )
    else:
        _log.warning(
            "cost_model_save_unvalidated: schema not found for pre-save "
            "validation — AC5 requires validation before save. Pass "
            "schema_path explicitly or ensure "
            "contracts/cost_model_schema.toml is discoverable.",
            extra={"ctx": {
                "pair": artifact.pair,
                "version": artifact.version,
            }},
        )

    content = json.dumps(artifact.to_dict(), indent=2, sort_keys=False)
    crash_safe_write(str(dest), content)

    _log.info(
        "cost_model_saved",
        extra={"ctx": {
            "pair": artifact.pair,
            "version": artifact.version,
            "path": str(dest),
            "manifest_updated": False,
        }},
    )
    return dest


def load_cost_model(
    pair: str,
    version: str,
    artifacts_dir: Path,
    schema_path: Path | None = None,
) -> CostModelArtifact:
    """Load a cost model artifact from JSON.

    Args:
        pair: Currency pair (e.g. "EURUSD").
        version: Version string (e.g. "v001").
        artifacts_dir: Root artifacts directory.
        schema_path: Optional schema path for post-load validation.

    Returns:
        Reconstructed CostModelArtifact.

    Raises:
        FileNotFoundError: If the version file doesn't exist.
        ValueError: If schema validation fails.
    """
    path = _version_path(pair, version, artifacts_dir)
    if not path.exists():
        raise FileNotFoundError(f"Cost model not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    artifact = CostModelArtifact.from_dict(data)

    _log.info(
        "cost_model_load",
        extra={"ctx": {
            "pair": pair,
            "version": version,
            "path": str(path),
        }},
    )

    if schema_path is not None:
        errors = validate_cost_model(artifact, schema_path)
        if errors:
            raise ValueError(f"Loaded artifact failed validation: {errors}")

    return artifact


def load_latest_cost_model(
    pair: str, artifacts_dir: Path
) -> CostModelArtifact | None:
    """Load the highest-versioned cost model for a pair.

    Returns None if no versions exist.
    """
    versions = list_versions(pair, artifacts_dir)
    if not versions:
        return None
    return load_cost_model(pair, versions[-1], artifacts_dir)


def load_approved_cost_model(
    pair: str, artifacts_dir: Path
) -> CostModelArtifact | None:
    """Load the latest *approved* cost model for a pair via manifest pointer.

    Uses the manifest's ``latest_approved_version`` pointer — not raw
    "latest file" — per AC9 and anti-pattern #18.

    Returns None if no approved version exists.
    """
    manifest = load_manifest(pair, artifacts_dir)
    if manifest is None:
        return None
    approved_version = manifest.get("latest_approved_version")
    if approved_version is None:
        return None
    return load_cost_model(pair, approved_version, artifacts_dir)


def get_next_version(pair: str, artifacts_dir: Path) -> str:
    """Return the next available version string for a pair.

    Returns "v001" if no versions exist, otherwise increments the highest.
    """
    versions = list_versions(pair, artifacts_dir)
    if not versions:
        return "v001"
    latest = versions[-1]
    m = _VERSION_RE.match(latest)
    if not m:
        return "v001"
    num = int(m.group(1)) + 1
    return f"v{num:03d}"


def list_versions(pair: str, artifacts_dir: Path) -> list[str]:
    """Return sorted list of existing version strings for a pair.

    Sorts numerically (v001, v002, ..., v999, v1000) to avoid
    lexicographic ordering issues with 4+ digit versions.
    """
    pair_dir = _artifact_dir(pair, artifacts_dir)
    if not pair_dir.exists():
        return []

    versions: list[tuple[int, str]] = []
    for f in pair_dir.iterdir():
        if f.suffix == ".json" and f.stem != "manifest":
            m = _VERSION_RE.match(f.stem)
            if m:
                versions.append((int(m.group(1)), f.stem))

    versions.sort(key=lambda x: x[0])
    return [v[1] for v in versions]


def save_manifest(
    pair: str,
    artifact: CostModelArtifact,
    artifacts_dir: Path,
    config_hash: str | None = None,
    input_hash: str | None = None,
) -> Path:
    """Create or update manifest.json with version history.

    Each version entry includes: version, status, created_at, approved_at,
    config_hash, artifact_hash, input_hash.

    Args:
        pair: Currency pair.
        artifact: The artifact being registered.
        artifacts_dir: Root artifacts directory.
        config_hash: Hash of config used to build the artifact.
        input_hash: Hash of input data used to build the artifact.

    Returns:
        Path to manifest.json.
    """
    manifest = load_manifest(pair, artifacts_dir) or {
        "pair": pair,
        "latest_approved_version": None,
        "versions": {},
    }

    # Compute artifact hash from the saved JSON content
    artifact_content = json.dumps(artifact.to_dict(), indent=2, sort_keys=False)
    artifact_hash = _compute_hash(artifact_content)

    # Warn if input_hash matches latest version (duplicate detection)
    if input_hash is not None:
        for ver_key, ver_entry in manifest.get("versions", {}).items():
            if ver_entry.get("input_hash") == input_hash:
                _log.warning(
                    "Duplicate input detected: input_hash matches existing "
                    f"version {ver_key}. Creating new version anyway.",
                    extra={"ctx": {
                        "pair": pair,
                        "new_version": artifact.version,
                        "existing_version": ver_key,
                        "input_hash": input_hash,
                    }},
                )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest["versions"][artifact.version] = {
        "version": artifact.version,
        "status": "draft",
        "created_at": now,
        "approved_at": None,
        "config_hash": config_hash,
        "artifact_hash": artifact_hash,
        "input_hash": input_hash,
    }

    dest = _manifest_path(pair, artifacts_dir)
    content = json.dumps(manifest, indent=2, sort_keys=False)
    crash_safe_write(str(dest), content)

    _log.info(
        "cost_model_saved",
        extra={"ctx": {
            "pair": pair,
            "version": artifact.version,
            "path": str(dest),
            "manifest_updated": True,
        }},
    )
    return dest


def load_manifest(pair: str, artifacts_dir: Path) -> dict | None:
    """Load manifest.json for a pair. Returns None if not found."""
    path = _manifest_path(pair, artifacts_dir)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def approve_version(pair: str, version: str, artifacts_dir: Path) -> Path:
    """Approve a version — set status to 'approved', update latest_approved_version.

    The latest_approved_version pointer is always computed as the max()
    of all approved versions (not just the last-touched entry), per
    lessons-learned from Story 2.5.

    Args:
        pair: Currency pair.
        version: Version to approve.
        artifacts_dir: Root artifacts directory.

    Returns:
        Path to updated manifest.json.

    Raises:
        FileNotFoundError: If manifest or version doesn't exist.
        ValueError: If version is not in manifest.
    """
    manifest = load_manifest(pair, artifacts_dir)
    if manifest is None:
        raise FileNotFoundError(
            f"No manifest found for {pair} in {artifacts_dir}"
        )

    if version not in manifest.get("versions", {}):
        raise ValueError(
            f"Version {version} not found in manifest for {pair}"
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest["versions"][version]["status"] = "approved"
    manifest["versions"][version]["approved_at"] = now

    # Compute latest_approved_version from max() of all approved versions
    # (not just last-touched — lesson from Story 2.5)
    approved_versions: list[tuple[int, str]] = []
    for ver_key, ver_entry in manifest["versions"].items():
        if ver_entry.get("status") == "approved":
            m = _VERSION_RE.match(ver_key)
            if m:
                approved_versions.append((int(m.group(1)), ver_key))

    if approved_versions:
        approved_versions.sort(key=lambda x: x[0])
        manifest["latest_approved_version"] = approved_versions[-1][1]

    dest = _manifest_path(pair, artifacts_dir)
    content = json.dumps(manifest, indent=2, sort_keys=False)
    crash_safe_write(str(dest), content)

    return dest
