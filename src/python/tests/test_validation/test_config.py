"""Tests for validation configuration (Task 2)."""
from validation.config import (
    CPCVConfig,
    DSRConfig,
    MonteCarloConfig,
    PerturbationConfig,
    RegimeConfig,
    ValidationConfig,
    WalkForwardConfig,
)


def test_validation_config_defaults():
    """Default config should match Brief 5C recommendations."""
    cfg = ValidationConfig()
    assert cfg.stage_order == [
        "perturbation", "walk_forward", "cpcv", "monte_carlo", "regime"
    ]
    assert cfg.short_circuit_on_validity_failure is True
    assert cfg.deterministic_seed_base == 42

    assert cfg.walk_forward.n_windows == 5
    assert cfg.walk_forward.purge_bars == 1440
    assert cfg.cpcv.n_groups == 10
    assert cfg.cpcv.pbo_red_threshold == 0.40
    assert cfg.perturbation.levels == [0.05, 0.10, 0.20]
    assert cfg.monte_carlo.n_bootstrap == 1000
    assert cfg.regime.min_trades_per_bucket == 30
    assert cfg.dsr.significance_level == 0.05


def test_validation_config_loads():
    """Config loads from nested dict matching base.toml structure."""
    config = {
        "validation": {
            "stage_order": ["walk_forward", "cpcv"],
            "deterministic_seed_base": 99,
            "walk_forward": {"n_windows": 8, "train_ratio": 0.75},
            "cpcv": {"n_groups": 5, "pbo_red_threshold": 0.50},
            "monte_carlo": {"n_bootstrap": 500},
            "regime": {"min_trades_per_bucket": 50},
            "dsr": {"significance_level": 0.01},
        }
    }
    cfg = ValidationConfig.from_dict(config)
    assert cfg.stage_order == ["walk_forward", "cpcv"]
    assert cfg.deterministic_seed_base == 99
    assert cfg.walk_forward.n_windows == 8
    assert cfg.walk_forward.train_ratio == 0.75
    assert cfg.cpcv.n_groups == 5
    assert cfg.cpcv.pbo_red_threshold == 0.50
    assert cfg.monte_carlo.n_bootstrap == 500
    assert cfg.regime.min_trades_per_bucket == 50
    assert cfg.dsr.significance_level == 0.01


def test_validation_config_from_empty_dict():
    """from_dict with empty dict produces defaults."""
    cfg = ValidationConfig.from_dict({})
    defaults = ValidationConfig()
    assert cfg.stage_order == defaults.stage_order
    assert cfg.walk_forward.n_windows == defaults.walk_forward.n_windows
    assert cfg.cpcv.pbo_red_threshold == defaults.cpcv.pbo_red_threshold
