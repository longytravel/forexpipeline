"""Strategy Confirmation — lock specifications for pipeline use (D10, FR12, FR59).

Confirms a draft specification: sets status to 'confirmed', attaches config_hash,
records confirmation timestamp, and updates the version manifest.

Idempotent: confirming an already-confirmed spec returns existing result.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config_loader.hasher import compute_config_hash
from logging_setup.setup import get_logger
from strategy.hasher import compute_spec_hash
from strategy.loader import load_strategy_spec
from strategy.specification import StrategySpecification
from strategy.storage import _clean_none_values, save_strategy_spec
from strategy.versioner import (
    SpecificationManifest,
    VersionEntry,
    create_manifest,
    load_manifest,
    save_manifest,
    update_manifest_version,
)

logger = get_logger("strategy.confirmer")


@dataclass
class ConfirmationResult:
    """Result of a strategy confirmation operation."""

    spec: StrategySpecification
    saved_path: Path
    version: str
    config_hash: str
    spec_hash: str
    confirmed_at: str
    manifest_path: Path


def _load_config_as_dict(config_dir: Path) -> dict:
    """Load pipeline config files into a dict for hashing.

    Reads base.toml + active environment TOML, concatenates into a dict
    for compute_config_hash().

    Args:
        config_dir: Path to config/ directory.

    Returns:
        Dict representing merged config content.
    """
    config_dir = Path(config_dir).resolve()
    base_path = config_dir / "base.toml"

    if not base_path.exists():
        raise FileNotFoundError(f"Config base.toml not found: {base_path}")

    with open(base_path, "rb") as f:
        config = tomllib.load(f)

    # Detect active environment
    import os

    env = os.environ.get("PIPELINE_ENV", "local")
    env_path = config_dir / "environments" / f"{env}.toml"

    if env_path.exists():
        with open(env_path, "rb") as f:
            env_config = tomllib.load(f)
        # Merge environment config into base
        _deep_merge(config, env_config)

    return config


def _deep_merge(base: dict, override: dict) -> None:
    """Merge override dict into base dict recursively (in-place)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def confirm_specification(
    strategy_slug: str,
    version: str,
    artifacts_dir: Path,
    config_dir: Path,
) -> ConfirmationResult:
    """Confirm a draft specification for pipeline use.

    Steps:
    1. Load spec from artifacts/strategies/{slug}/{version}.toml
    2. If already confirmed: return existing result (idempotent)
    3. Compute config_hash from pipeline config
    4. Set status=confirmed, config_hash, confirmed_at
    5. Compute spec_hash
    6. Save spec (same version file — status change is metadata update)
    7. Update manifest with confirmation details
    8. Return ConfirmationResult

    Args:
        strategy_slug: Strategy identifier slug.
        version: Version to confirm (e.g., "v001").
        artifacts_dir: Root artifacts directory.
        config_dir: Path to config/ directory for config hash computation.

    Returns:
        ConfirmationResult with confirmation details.

    Raises:
        FileNotFoundError: If spec file not found.
        ValueError: If spec has unexpected status.
    """
    artifacts_dir = Path(artifacts_dir).resolve()
    config_dir = Path(config_dir).resolve()

    spec_path = artifacts_dir / "strategies" / strategy_slug / f"{version}.toml"
    strategy_dir = artifacts_dir / "strategies" / strategy_slug

    logger.info(
        "strategy_confirmation_start",
        extra={"strategy_slug": strategy_slug, "version": version},
    )

    # Load spec
    spec = load_strategy_spec(spec_path)

    # Idempotent: if already confirmed, return existing result
    if spec.metadata.status == "confirmed":
        spec_hash = compute_spec_hash(spec)
        manifest = load_manifest(strategy_slug, artifacts_dir)
        manifest_path = artifacts_dir / "strategies" / strategy_slug / "manifest.json"

        logger.info(
            "strategy_already_confirmed",
            extra={"strategy_slug": strategy_slug, "version": version},
        )

        return ConfirmationResult(
            spec=spec,
            saved_path=spec_path,
            version=version,
            config_hash=spec.metadata.config_hash or "",
            spec_hash=spec_hash,
            confirmed_at=spec.metadata.confirmed_at or "",
            manifest_path=manifest_path,
        )

    # Compute config hash
    config_dict = _load_config_as_dict(config_dir)
    config_hash = compute_config_hash(config_dict)

    # Update spec metadata
    confirmed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Create updated spec with confirmed status
    spec_dict = spec.model_dump(mode="python")
    spec_dict["metadata"]["status"] = "confirmed"
    spec_dict["metadata"]["config_hash"] = config_hash
    spec_dict["metadata"]["confirmed_at"] = confirmed_at

    # Rebuild spec from dict to get validated model
    confirmed_spec = StrategySpecification.model_validate(spec_dict)

    # Compute spec hash (content hash, excludes timestamps/status)
    spec_hash = compute_spec_hash(confirmed_spec)

    # Save confirmed spec — same version file (status metadata update, not content change)
    # We write directly instead of using save_strategy_spec() which auto-increments
    import tomli_w
    from artifacts.storage import crash_safe_write

    out_dict = confirmed_spec.model_dump(mode="python")
    out_dict["metadata"]["version"] = version
    out_dict = _clean_none_values(out_dict)
    toml_content = tomli_w.dumps(out_dict)
    crash_safe_write(str(spec_path), toml_content)

    # Update manifest
    version_entry = VersionEntry(
        version=version,
        status="confirmed",
        created_at=spec_dict["metadata"].get("created_at") or confirmed_at,
        confirmed_at=confirmed_at,
        config_hash=config_hash,
        spec_hash=spec_hash,
    )

    manifest = load_manifest(strategy_slug, artifacts_dir)
    if manifest is None:
        manifest = create_manifest(strategy_slug, version_entry)
    else:
        manifest = update_manifest_version(manifest, version_entry)

    manifest_path = save_manifest(manifest, artifacts_dir)

    logger.info(
        "strategy_confirmed",
        extra={
            "strategy_slug": strategy_slug,
            "version": version,
            "config_hash": config_hash,
            "spec_hash": spec_hash,
        },
    )

    return ConfirmationResult(
        spec=confirmed_spec,
        saved_path=spec_path,
        version=version,
        config_hash=config_hash,
        spec_hash=spec_hash,
        confirmed_at=confirmed_at,
        manifest_path=manifest_path,
    )
