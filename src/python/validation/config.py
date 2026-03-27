"""Typed validation configuration dataclasses (Story 5.4, Task 2)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WalkForwardConfig:
    n_windows: int = 5
    train_ratio: float = 0.80
    purge_bars: int = 1440
    embargo_bars: int = 720


@dataclass(frozen=True)
class CPCVConfig:
    n_groups: int = 10
    k_test_groups: int = 3
    purge_bars: int = 1440
    embargo_bars: int = 720
    pbo_red_threshold: float = 0.40


@dataclass(frozen=True)
class PerturbationConfig:
    levels: list[float] = field(default_factory=lambda: [0.05, 0.10, 0.20])
    min_performance_retention: float = 0.70


@dataclass(frozen=True)
class MonteCarloConfig:
    n_bootstrap: int = 1000
    n_permutation: int = 1000
    stress_multipliers: list[float] = field(default_factory=lambda: [1.5, 2.0, 3.0])
    confidence_level: float = 0.95


@dataclass(frozen=True)
class RegimeConfig:
    volatility_quantiles: list[float] = field(default_factory=lambda: [0.333, 0.667])
    min_trades_per_bucket: int = 30
    sessions: list[str] = field(
        default_factory=lambda: ["asian", "london", "new_york", "london_ny_overlap"]
    )


@dataclass(frozen=True)
class DSRConfig:
    significance_level: float = 0.05


@dataclass(frozen=True)
class ValidationConfig:
    stage_order: list[str] = field(
        default_factory=lambda: [
            "perturbation", "walk_forward", "cpcv", "monte_carlo", "regime"
        ]
    )
    short_circuit_on_validity_failure: bool = True
    checkpoint_interval: int = 1
    deterministic_seed_base: int = 42

    walk_forward: WalkForwardConfig = field(default_factory=WalkForwardConfig)
    cpcv: CPCVConfig = field(default_factory=CPCVConfig)
    perturbation: PerturbationConfig = field(default_factory=PerturbationConfig)
    monte_carlo: MonteCarloConfig = field(default_factory=MonteCarloConfig)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    dsr: DSRConfig = field(default_factory=DSRConfig)

    @classmethod
    def from_dict(cls, config: dict) -> ValidationConfig:
        """Build from full config dict (expects [validation] section).

        Validates critical ranges to prevent nonsensical configurations.
        """
        defaults = cls()
        v = config.get("validation", {})

        # Validate critical config ranges
        wf_raw = v.get("walk_forward", {})
        if wf_raw.get("n_windows", 5) < 1:
            raise ValueError("walk_forward.n_windows must be >= 1")
        if not (0.0 < wf_raw.get("train_ratio", 0.80) < 1.0):
            raise ValueError("walk_forward.train_ratio must be in (0, 1)")
        cpcv_raw = v.get("cpcv", {})
        n_g = cpcv_raw.get("n_groups", 10)
        k_t = cpcv_raw.get("k_test_groups", 3)
        if n_g < 2:
            raise ValueError("cpcv.n_groups must be >= 2")
        if k_t < 1 or k_t >= n_g:
            raise ValueError("cpcv.k_test_groups must be >= 1 and < n_groups")

        wf = v.get("walk_forward", {})
        cpcv = v.get("cpcv", {})
        pert = v.get("perturbation", {})
        mc = v.get("monte_carlo", {})
        regime = v.get("regime", {})
        dsr = v.get("dsr", {})

        return cls(
            stage_order=v.get("stage_order", defaults.stage_order),
            short_circuit_on_validity_failure=v.get(
                "short_circuit_on_validity_failure", True
            ),
            checkpoint_interval=v.get("checkpoint_interval", 1),
            deterministic_seed_base=v.get("deterministic_seed_base", 42),
            walk_forward=WalkForwardConfig(
                n_windows=wf.get("n_windows", 5),
                train_ratio=wf.get("train_ratio", 0.80),
                purge_bars=wf.get("purge_bars", 1440),
                embargo_bars=wf.get("embargo_bars", 720),
            ),
            cpcv=CPCVConfig(
                n_groups=cpcv.get("n_groups", 10),
                k_test_groups=cpcv.get("k_test_groups", 3),
                purge_bars=cpcv.get("purge_bars", 1440),
                embargo_bars=cpcv.get("embargo_bars", 720),
                pbo_red_threshold=cpcv.get("pbo_red_threshold", 0.40),
            ),
            perturbation=PerturbationConfig(
                levels=pert.get("levels", [0.05, 0.10, 0.20]),
                min_performance_retention=pert.get("min_performance_retention", 0.70),
            ),
            monte_carlo=MonteCarloConfig(
                n_bootstrap=mc.get("n_bootstrap", 1000),
                n_permutation=mc.get("n_permutation", 1000),
                stress_multipliers=mc.get("stress_multipliers", [1.5, 2.0, 3.0]),
                confidence_level=mc.get("confidence_level", 0.95),
            ),
            regime=RegimeConfig(
                volatility_quantiles=regime.get("volatility_quantiles", [0.333, 0.667]),
                min_trades_per_bucket=regime.get("min_trades_per_bucket", 30),
                sessions=regime.get("sessions", [
                    "asian", "london", "new_york", "london_ny_overlap"
                ]),
            ),
            dsr=DSRConfig(
                significance_level=dsr.get("significance_level", 0.05),
            ),
        )
