"""Strategy Specification Storage with Versioning (D10, FR12, NFR15).

Persistence primitives: save (auto-increment version), load, list versions,
immutability enforcement. Uses crash-safe write pattern.

Story 2.5 builds operator-facing lifecycle on top of these primitives.
"""

from __future__ import annotations

import logging
import re
import tomllib
from pathlib import Path

import tomli_w

from artifacts.storage import clean_partial_files, crash_safe_write
from strategy.specification import StrategySpecification

logger = logging.getLogger(__name__)

VERSION_RE = re.compile(r"^v(\d{3,})\.toml$")


def save_strategy_spec(spec: StrategySpecification, strategy_dir: Path) -> Path:
    """Save a strategy specification with auto-incremented version.

    Layout: strategy_dir/v001.toml, v002.toml, etc.
    Uses crash-safe write pattern (NFR15).

    Args:
        spec: Validated StrategySpecification to save.
        strategy_dir: Directory for this strategy's versions.

    Returns:
        Path to the saved version file.
    """
    strategy_dir = Path(strategy_dir)
    strategy_dir.mkdir(parents=True, exist_ok=True)

    # Clean any leftover partial files from prior crashes
    clean_partial_files(strategy_dir)

    # Determine next version
    existing = list_versions(strategy_dir)
    if existing:
        last_num = int(existing[-1][1:])  # "v003" -> 3
        next_num = last_num + 1
    else:
        next_num = 1

    version_str = f"v{next_num:03d}" if next_num < 1000 else f"v{next_num}"
    output_path = strategy_dir / f"{version_str}.toml"

    # Serialize spec to TOML, updating embedded version to match filename
    spec_dict = spec.model_dump(mode="python")
    spec_dict["metadata"]["version"] = version_str
    # Convert None values to omit them (TOML doesn't have null)
    spec_dict = _clean_none_values(spec_dict)
    toml_content = tomli_w.dumps(spec_dict)

    # Crash-safe write
    crash_safe_write(str(output_path), toml_content)

    logger.info("Saved strategy spec: %s", output_path)
    return output_path


def load_latest_version(
    strategy_dir: Path,
) -> tuple[StrategySpecification, str]:
    """Load the highest version specification from a strategy directory.

    Args:
        strategy_dir: Directory containing versioned spec files.

    Returns:
        Tuple of (StrategySpecification, version_string).

    Raises:
        FileNotFoundError: If no versions exist.
    """
    strategy_dir = Path(strategy_dir)
    versions = list_versions(strategy_dir)
    if not versions:
        raise FileNotFoundError(f"No specification versions found in {strategy_dir}")

    latest = versions[-1]
    spec_path = strategy_dir / f"{latest}.toml"

    with open(spec_path, "rb") as f:
        raw = tomllib.load(f)

    spec = StrategySpecification.model_validate(raw)
    return spec, latest


def list_versions(strategy_dir: Path) -> list[str]:
    """List all version strings in sorted order.

    Args:
        strategy_dir: Directory containing versioned spec files.

    Returns:
        Sorted list of version strings (e.g., ["v001", "v002", "v003"]).
    """
    strategy_dir = Path(strategy_dir)
    if not strategy_dir.exists():
        return []

    versions: list[tuple[int, str]] = []
    for f in strategy_dir.iterdir():
        match = VERSION_RE.match(f.name)
        if match:
            num = int(match.group(1))
            ver_str = f"v{num:03d}" if num < 1000 else f"v{num}"
            versions.append((num, ver_str))

    versions.sort()
    return [v for _, v in versions]


def is_version_immutable(strategy_dir: Path, version: str) -> bool:
    """Check if a version exists (all saved versions are immutable).

    Args:
        strategy_dir: Directory containing versioned spec files.
        version: Version string (e.g., "v001").

    Returns:
        True if the version file exists (and is therefore immutable).
    """
    spec_path = Path(strategy_dir) / f"{version}.toml"
    return spec_path.exists()


def _clean_none_values(d: dict) -> dict:
    """Recursively remove None values (TOML has no null type)."""
    result = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, dict):
            result[k] = _clean_none_values(v)
        elif isinstance(v, list):
            result[k] = [
                _clean_none_values(item) if isinstance(item, dict) else item
                for item in v
                if item is not None
            ]
        else:
            result[k] = v
    return result
