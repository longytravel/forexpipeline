"""Selection configuration loader (Story 5.6, Task 1).

Loads [selection] section from config/base.toml with validation.
Follows the pattern established in confidence/config.py.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass(frozen=True)
class SelectionConfig:
    """Configuration for the candidate selection pipeline."""

    min_cluster_size: int
    hdbscan_min_samples: int
    topsis_top_n: int
    stability_threshold: float
    target_candidates: int  # 5-20
    deterministic_ratio: float  # 0.8
    diversity_dimensions: list[str]
    max_clustering_candidates: int
    random_seed: int | None  # None = derive from optimization_run_id hash

    def __post_init__(self) -> None:
        if not 5 <= self.target_candidates <= 20:
            raise ValueError(
                f"target_candidates must be 5-20, got {self.target_candidates}"
            )
        if not 0.0 <= self.deterministic_ratio <= 1.0:
            raise ValueError(
                f"deterministic_ratio must be 0.0-1.0, got {self.deterministic_ratio}"
            )
        if self.min_cluster_size < 2:
            raise ValueError(
                f"min_cluster_size must be >= 2, got {self.min_cluster_size}"
            )
        if self.max_clustering_candidates < 100:
            raise ValueError(
                f"max_clustering_candidates must be >= 100, got {self.max_clustering_candidates}"
            )

    def config_hash(self) -> str:
        """Compute deterministic hash of this configuration for manifest."""
        data = {
            "min_cluster_size": self.min_cluster_size,
            "hdbscan_min_samples": self.hdbscan_min_samples,
            "topsis_top_n": self.topsis_top_n,
            "stability_threshold": self.stability_threshold,
            "target_candidates": self.target_candidates,
            "deterministic_ratio": self.deterministic_ratio,
            "diversity_dimensions": sorted(self.diversity_dimensions),
            "max_clustering_candidates": self.max_clustering_candidates,
            "random_seed": self.random_seed,
        }
        content = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"

    def resolve_seed(self, optimization_run_id: str) -> int:
        """Return explicit seed or derive from optimization_run_id hash."""
        if self.random_seed is not None:
            return self.random_seed
        return int(hashlib.sha256(optimization_run_id.encode()).hexdigest()[:8], 16)


def load_selection_config(config_path: Path) -> SelectionConfig:
    """Load selection configuration from TOML file.

    Args:
        config_path: Path to the base config TOML file.

    Returns:
        Parsed and validated SelectionConfig.

    Raises:
        KeyError: If required config keys are missing.
        ValueError: If config values are out of range.
    """
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    conf = raw["selection"]
    return _build_selection_config(conf)


def selection_config_from_dict(data: dict[str, Any]) -> SelectionConfig:
    """Build SelectionConfig from a pre-loaded dict (e.g. from pipeline context)."""
    return _build_selection_config(data)


def _build_selection_config(conf: dict[str, Any]) -> SelectionConfig:
    """Build SelectionConfig from a selection config dict."""
    return SelectionConfig(
        min_cluster_size=conf["min_cluster_size"],
        hdbscan_min_samples=conf["hdbscan_min_samples"],
        topsis_top_n=conf["topsis_top_n"],
        stability_threshold=conf["stability_threshold"],
        target_candidates=conf["target_candidates"],
        deterministic_ratio=conf["deterministic_ratio"],
        diversity_dimensions=list(conf["diversity_dimensions"]),
        max_clustering_candidates=conf["max_clustering_candidates"],
        random_seed=conf.get("random_seed"),
    )
