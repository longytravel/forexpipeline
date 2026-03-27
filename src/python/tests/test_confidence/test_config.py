"""Tests for confidence scoring configuration (Task 2)."""
from pathlib import Path

import pytest

from confidence.config import (
    ConfidenceConfig,
    WeightConfig,
    confidence_config_from_dict,
    load_confidence_config,
)

CONFIG_PATH = Path(__file__).resolve().parents[4] / "config" / "base.toml"


def _valid_config_dict() -> dict:
    return {
        "hard_gates": {
            "dsr_pass_required": True,
            "pbo_max_threshold": 0.40,
            "cost_stress_survival_multiplier": 1.5,
        },
        "weights": {
            "walk_forward_oos_consistency": 0.25,
            "cpcv_pbo_margin": 0.15,
            "parameter_stability": 0.15,
            "monte_carlo_stress_survival": 0.15,
            "regime_uniformity": 0.15,
            "in_sample_oos_coherence": 0.15,
        },
        "thresholds": {
            "green_minimum": 0.70,
            "yellow_minimum": 0.40,
        },
        "anomaly": {
            "min_population_size": 20,
        },
    }


def test_confidence_config_loads():
    """Config loads from real base.toml without errors."""
    config = load_confidence_config(CONFIG_PATH)
    assert isinstance(config, ConfidenceConfig)
    assert config.hard_gates.pbo_max_threshold == 0.40
    assert config.thresholds.green_minimum == 0.70
    assert config.anomaly.min_population_size == 20


def test_confidence_config_from_dict():
    """Config builds from dict correctly."""
    config = confidence_config_from_dict(_valid_config_dict())
    assert config.hard_gates.dsr_pass_required is True
    assert config.weights.walk_forward_oos_consistency == 0.25


def test_weights_sum_validation():
    """Weights that don't sum to 1.0 raise ValueError."""
    data = _valid_config_dict()
    data["weights"]["walk_forward_oos_consistency"] = 0.50  # breaks sum
    with pytest.raises(ValueError, match="must sum to 1.0"):
        confidence_config_from_dict(data)


def test_weights_as_dict():
    """WeightConfig.as_dict returns all component names."""
    config = confidence_config_from_dict(_valid_config_dict())
    weights_dict = config.weights.as_dict()
    assert len(weights_dict) == 6
    assert abs(sum(weights_dict.values()) - 1.0) < 1e-6


def test_missing_hard_gates_key_raises():
    """Missing hard_gates section raises KeyError."""
    data = _valid_config_dict()
    del data["hard_gates"]
    with pytest.raises(KeyError):
        confidence_config_from_dict(data)


def test_anomaly_defaults_when_missing():
    """Missing anomaly section defaults to min_population_size=20."""
    data = _valid_config_dict()
    del data["anomaly"]
    config = confidence_config_from_dict(data)
    assert config.anomaly.min_population_size == 20
