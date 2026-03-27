"""Indicator Type Registry (D10, Story 2.3).

Data-driven registry loaded from contracts/indicator_registry.toml.
Both Python (this module) and Rust (Story 2.8) consume the same source file.
Extensible: add indicators to the TOML without code changes.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

# Default path to the shared indicator registry contract
_DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[3] / "contracts" / "indicator_registry.toml"


class IndicatorMeta(BaseModel):
    """Metadata for a known indicator type."""

    model_config = ConfigDict(strict=True)

    name: str
    category: str  # trend, volatility, momentum, price_action, structure
    description: str
    required_params: list[str]
    optional_params: list[str]


# Module-level registry cache
_registry: Optional[dict[str, IndicatorMeta]] = None
_registry_path: Optional[Path] = None


def _load_registry(registry_path: Path | None = None) -> dict[str, IndicatorMeta]:
    """Load indicator registry from TOML file.

    Args:
        registry_path: Path to indicator_registry.toml. Uses default if None.

    Returns:
        Dict mapping indicator key -> IndicatorMeta.
    """
    path = registry_path or _DEFAULT_REGISTRY_PATH
    if not path.exists():
        raise FileNotFoundError(f"Indicator registry not found: {path}")

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    indicators_raw = raw.get("indicators", {})
    registry: dict[str, IndicatorMeta] = {}

    for key, meta in indicators_raw.items():
        registry[key] = IndicatorMeta.model_validate(meta)

    logger.debug("Loaded %d indicators from %s", len(registry), path)
    return registry


def get_registry(registry_path: Path | None = None) -> dict[str, IndicatorMeta]:
    """Get the indicator registry, loading from TOML if not cached.

    Args:
        registry_path: Optional override path.

    Returns:
        Dict mapping indicator key -> IndicatorMeta.
    """
    global _registry, _registry_path

    effective_path = registry_path or _DEFAULT_REGISTRY_PATH
    if _registry is None or _registry_path != effective_path:
        _registry = _load_registry(effective_path)
        _registry_path = effective_path

    return _registry


def is_indicator_known(indicator_type: str, registry_path: Path | None = None) -> bool:
    """Check if an indicator type is in the registry.

    Args:
        indicator_type: Indicator key (e.g., "sma", "atr").
        registry_path: Optional override path.

    Returns:
        True if the indicator is known.
    """
    registry = get_registry(registry_path)
    return indicator_type in registry


def get_indicator_params(
    indicator_type: str, registry_path: Path | None = None
) -> IndicatorMeta:
    """Get metadata for a known indicator.

    Args:
        indicator_type: Indicator key.
        registry_path: Optional override path.

    Returns:
        IndicatorMeta for the indicator.

    Raises:
        KeyError: If indicator is not in registry.
    """
    registry = get_registry(registry_path)
    if indicator_type not in registry:
        raise KeyError(
            f"Unknown indicator '{indicator_type}'. "
            f"Known: {sorted(registry.keys())}"
        )
    return registry[indicator_type]


def reset_registry() -> None:
    """Clear cached registry (for testing)."""
    global _registry, _registry_path
    _registry = None
    _registry_path = None
