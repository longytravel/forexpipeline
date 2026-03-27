"""Deflated Sharpe Ratio calculator (Story 5.4, Task 8).

Implements Bailey & Lopez de Prado's Deflated Sharpe Ratio to correct
for multiple testing bias across ALL candidates explored during optimization.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

from logging_setup.setup import get_logger

logger = get_logger("validation.dsr")


@dataclass
class DSRResult:
    dsr: float
    p_value: float
    passed: bool
    num_trials: int
    expected_max_sharpe: float


def compute_expected_max_sharpe(
    num_trials: int,
    sharpe_std: float,
    skew: float = 0.0,
    kurt: float = 3.0,
) -> float:
    """Compute E[max(SR)] under multiple testing per Bailey & Lopez de Prado.

    E[max(SR)] approx sqrt(2*ln(N)) - (ln(pi) + ln(ln(N))) / (2*sqrt(2*ln(N)))
    adjusted for skewness and kurtosis.
    """
    if num_trials <= 1:
        return 0.0

    log_n = np.log(num_trials)
    sqrt_2_log_n = np.sqrt(2 * log_n)

    # Bailey & Lopez de Prado expected max Sharpe
    e_max_sr = sqrt_2_log_n - (np.log(np.pi) + np.log(log_n)) / (2 * sqrt_2_log_n)

    return float(e_max_sr * sharpe_std) if sharpe_std > 0 else float(e_max_sr)


def compute_dsr(
    observed_sharpe: float,
    num_trials: int,
    sharpe_variance: float,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    significance_level: float = 0.05,
) -> DSRResult:
    """Compute Deflated Sharpe Ratio per Bailey & Lopez de Prado.

    DSR tests whether the observed Sharpe exceeds what would be expected
    from random chance given N independent trials.

    Args:
        observed_sharpe: The best Sharpe ratio observed
        num_trials: Total candidates explored during optimization (NOT just promoted)
        sharpe_variance: Variance of Sharpe ratios across all trials
        skewness: Skewness of returns
        kurtosis: Kurtosis of returns (3.0 = normal)
        significance_level: Alpha for hypothesis test

    Returns:
        DSRResult with deflated Sharpe, p-value, and pass/fail
    """
    if num_trials <= 1:
        return DSRResult(
            dsr=observed_sharpe, p_value=0.0, passed=True,
            num_trials=num_trials, expected_max_sharpe=0.0,
        )

    sharpe_std = np.sqrt(sharpe_variance) if sharpe_variance > 0 else 1.0

    e_max_sr = compute_expected_max_sharpe(
        num_trials, sharpe_std, skewness, kurtosis
    )

    # Apply non-normality correction to SE per Bailey & Lopez de Prado.
    # The variance of the SR estimator under non-normal returns:
    #   V(SR) ∝ 1 - γ₃·SR + (γ₄-1)/4 · SR²
    # Under normality (γ₃=0, γ₄=3): V(SR) ∝ 1 + 0.5·SR²
    # Scale sharpe_std by the ratio so correction=1.0 under normality.
    adjusted_std = sharpe_std
    if (skewness != 0 or kurtosis != 3.0) and observed_sharpe != 0:
        sr = observed_sharpe
        non_normal_var = 1.0 - skewness * sr + (kurtosis - 1.0) / 4.0 * sr**2
        normal_var = 1.0 + 0.5 * sr**2
        if non_normal_var > 0 and normal_var > 0:
            adjusted_std = sharpe_std * np.sqrt(non_normal_var / normal_var)

    # DSR = Prob(SR_observed > E[max(SR)])
    # Using the standard normal CDF
    if adjusted_std > 0:
        z_stat = (observed_sharpe - e_max_sr) / adjusted_std
    else:
        z_stat = 0.0

    # P-value: probability of observing this Sharpe under the null
    # (that the strategy is no better than the best random trial)
    p_value = 1.0 - float(norm.cdf(z_stat))

    # DSR value is the probability that observed exceeds expected max
    dsr_value = float(norm.cdf(z_stat))

    passed = p_value < significance_level

    logger.info(
        f"DSR computed: dsr={dsr_value:.4f}, p={p_value:.4f}, "
        f"E[max_SR]={e_max_sr:.4f}, observed={observed_sharpe:.4f}, "
        f"trials={num_trials}, gate={'PASS' if passed else 'FAIL'}",
        extra={
            "component": "validation.dsr",
            "ctx": {
                "dsr": dsr_value,
                "p_value": p_value,
                "e_max_sharpe": e_max_sr,
                "observed_sharpe": observed_sharpe,
                "num_trials": num_trials,
                "significance_level": significance_level,
            },
        },
    )

    return DSRResult(
        dsr=dsr_value,
        p_value=p_value,
        passed=passed,
        num_trials=num_trials,
        expected_max_sharpe=e_max_sr,
    )
