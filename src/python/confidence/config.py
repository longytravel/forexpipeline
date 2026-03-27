"""Confidence scoring configuration (Story 5.5, Task 2).

Loads [confidence] section from config/base.toml with validation.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


# Default matching config/base.toml [confidence.hard_gates].pbo_max_threshold.
# Used as fallback when scorer is called without full config.
DEFAULT_PBO_MAX_THRESHOLD: float = 0.40


@dataclass(frozen=True)
class HardGateConfig:
    """Hard gate thresholds — any failure → RED."""

    dsr_pass_required: bool
    pbo_max_threshold: float
    cost_stress_survival_multiplier: float


@dataclass(frozen=True)
class WeightConfig:
    """Component weights for composite score (must sum to 1.0)."""

    walk_forward_oos_consistency: float
    cpcv_pbo_margin: float
    parameter_stability: float
    monte_carlo_stress_survival: float
    regime_uniformity: float
    in_sample_oos_coherence: float

    def __post_init__(self) -> None:
        total = (
            self.walk_forward_oos_consistency
            + self.cpcv_pbo_margin
            + self.parameter_stability
            + self.monte_carlo_stress_survival
            + self.regime_uniformity
            + self.in_sample_oos_coherence
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Confidence weights must sum to 1.0, got {total:.6f}. "
                f"Weights: walk_forward={self.walk_forward_oos_consistency}, "
                f"cpcv={self.cpcv_pbo_margin}, parameter={self.parameter_stability}, "
                f"monte_carlo={self.monte_carlo_stress_survival}, "
                f"regime={self.regime_uniformity}, coherence={self.in_sample_oos_coherence}"
            )

    def as_dict(self) -> dict[str, float]:
        """Return weights as {component_name: weight} dict."""
        return {
            "walk_forward_oos_consistency": self.walk_forward_oos_consistency,
            "cpcv_pbo_margin": self.cpcv_pbo_margin,
            "parameter_stability": self.parameter_stability,
            "monte_carlo_stress_survival": self.monte_carlo_stress_survival,
            "regime_uniformity": self.regime_uniformity,
            "in_sample_oos_coherence": self.in_sample_oos_coherence,
        }


@dataclass(frozen=True)
class ThresholdConfig:
    """Rating thresholds applied after hard gates pass."""

    green_minimum: float
    yellow_minimum: float


@dataclass(frozen=True)
class AnomalyConfig:
    """Anomaly detection configuration."""

    min_population_size: int


@dataclass(frozen=True)
class ConfidenceConfig:
    """Complete confidence scoring configuration."""

    hard_gates: HardGateConfig
    weights: WeightConfig
    thresholds: ThresholdConfig
    anomaly: AnomalyConfig


def load_confidence_config(config_path: Path) -> ConfidenceConfig:
    """Load confidence configuration from TOML file.

    Args:
        config_path: Path to the base config TOML file.

    Returns:
        Parsed and validated ConfidenceConfig.

    Raises:
        KeyError: If required config keys are missing.
        ValueError: If weights don't sum to 1.0.
    """
    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    conf = raw["confidence"]
    return _build_confidence_config(conf)


def confidence_config_from_dict(data: dict[str, Any]) -> ConfidenceConfig:
    """Build ConfidenceConfig from a pre-loaded dict (e.g. from pipeline context)."""
    return _build_confidence_config(data)


def _build_confidence_config(conf: dict[str, Any]) -> ConfidenceConfig:
    """Build ConfidenceConfig from a confidence config dict."""
    hg = conf["hard_gates"]
    wt = conf["weights"]
    th = conf["thresholds"]
    an = conf.get("anomaly", {"min_population_size": 20})

    return ConfidenceConfig(
        hard_gates=HardGateConfig(
            dsr_pass_required=hg["dsr_pass_required"],
            pbo_max_threshold=hg["pbo_max_threshold"],
            cost_stress_survival_multiplier=hg["cost_stress_survival_multiplier"],
        ),
        weights=WeightConfig(
            walk_forward_oos_consistency=wt["walk_forward_oos_consistency"],
            cpcv_pbo_margin=wt["cpcv_pbo_margin"],
            parameter_stability=wt["parameter_stability"],
            monte_carlo_stress_survival=wt["monte_carlo_stress_survival"],
            regime_uniformity=wt["regime_uniformity"],
            in_sample_oos_coherence=wt["in_sample_oos_coherence"],
        ),
        thresholds=ThresholdConfig(
            green_minimum=th["green_minimum"],
            yellow_minimum=th["yellow_minimum"],
        ),
        anomaly=AnomalyConfig(
            min_population_size=an["min_population_size"],
        ),
    )
