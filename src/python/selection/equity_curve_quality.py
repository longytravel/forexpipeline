"""Equity curve quality metrics (Story 5.6, Task 3, FR27).

Five pure, deterministic metrics per candidate:
K-Ratio, Ulcer Index, DSR, Gain-to-Pain Ratio, Serenity Ratio.
"""
from __future__ import annotations

import numpy as np
from scipy import stats as scipy_stats

from selection.models import EquityCurveQuality


def compute_k_ratio(equity_curve: np.ndarray) -> float:
    """K-Ratio: linear regression slope / standard error of slope.

    Measures equity curve smoothness. Higher = smoother growth.
    A perfectly linear equity curve yields a very high K-Ratio.

    Args:
        equity_curve: Cumulative equity values (at least 2 points).

    Returns:
        K-Ratio value. Returns 0.0 for degenerate inputs.
    """
    n = len(equity_curve)
    if n < 2:
        return 0.0

    x = np.arange(n, dtype=np.float64)
    result = scipy_stats.linregress(x, equity_curve)
    slope = result.slope
    stderr = result.stderr

    if stderr == 0.0 or np.isnan(stderr):
        # Perfect linear curve or degenerate — slope/0 → use large value
        return float(np.sign(slope) * 1e6) if slope != 0.0 else 0.0

    return float(slope / stderr)


def compute_ulcer_index(equity_curve: np.ndarray) -> float:
    """Ulcer Index: RMS of percentage drawdowns from running peak.

    Lower = less painful drawdowns. Returns 0.0 for no-drawdown curves.

    Args:
        equity_curve: Cumulative equity values.

    Returns:
        Ulcer Index value (>= 0). Returns 0.0 for degenerate inputs.
    """
    if len(equity_curve) < 2:
        return 0.0

    equity = np.asarray(equity_curve, dtype=np.float64)
    running_max = np.maximum.accumulate(equity)

    # Avoid division by zero for curves starting at 0
    mask = running_max > 0
    pct_drawdown = np.zeros_like(equity)
    pct_drawdown[mask] = ((equity[mask] - running_max[mask]) / running_max[mask]) * 100.0

    return float(np.sqrt(np.mean(pct_drawdown**2)))


def compute_dsr(sharpe: float, n_trials: int, sharpe_std: float) -> float:
    """Deflated Sharpe Ratio (Bailey & López de Prado).

    Adjusts Sharpe ratio for multiple testing bias.
    DSR < 0.95 suggests the observed Sharpe may be due to luck.

    Args:
        sharpe: Observed Sharpe ratio.
        n_trials: Total number of strategy trials (for deflation).
        sharpe_std: Standard deviation of Sharpe estimates across trials.

    Returns:
        DSR value in [0, 1]. Returns 0.0 for degenerate inputs.
    """
    if n_trials < 2 or sharpe_std <= 0.0:
        return 0.0

    # Expected max Sharpe under null hypothesis (from order statistics)
    # E[max(Z_1, ..., Z_n)] ≈ (1 - γ) * Φ^{-1}(1 - 1/n) + γ * Φ^{-1}(1 - 1/(ne))
    # Simplified approximation using Euler-Mascheroni constant γ ≈ 0.5772
    from scipy.stats import norm

    gamma = 0.5772156649
    z = norm.ppf(1.0 - 1.0 / n_trials)
    expected_max_sharpe = (1.0 - gamma) * z + gamma * norm.ppf(1.0 - 1.0 / (n_trials * np.e))

    sharpe_deflated = sharpe_std * expected_max_sharpe

    if sharpe_std == 0:
        return 0.0

    # PSR: probability that observed Sharpe > deflated Sharpe
    test_stat = (sharpe - sharpe_deflated) / sharpe_std
    dsr = float(norm.cdf(test_stat))

    return max(0.0, min(1.0, dsr))


def compute_gain_to_pain(returns: np.ndarray) -> float:
    """Gain-to-Pain Ratio: sum(returns) / sum(abs(negative returns)).

    Higher = better. Returns inf for all-positive returns (capped at 1e6).

    Args:
        returns: Array of period returns.

    Returns:
        Gain-to-Pain ratio. Returns 0.0 for empty/all-zero returns.
    """
    if len(returns) == 0:
        return 0.0

    returns = np.asarray(returns, dtype=np.float64)
    total_gain = float(np.sum(returns))
    pain = float(np.sum(np.abs(returns[returns < 0])))

    if pain == 0.0:
        return 1e6 if total_gain > 0 else 0.0

    return float(total_gain / pain)


def compute_serenity_ratio(
    returns: np.ndarray, equity_curve: np.ndarray
) -> float:
    """Serenity Ratio: Sharpe-like measure penalized by drawdown severity.

    Combines return consistency with drawdown behavior.
    Higher = smoother, more consistent returns.

    Args:
        returns: Array of period returns.
        equity_curve: Cumulative equity values.

    Returns:
        Serenity ratio value. Returns 0.0 for degenerate inputs.
    """
    if len(returns) < 2 or len(equity_curve) < 2:
        return 0.0

    returns = np.asarray(returns, dtype=np.float64)
    equity = np.asarray(equity_curve, dtype=np.float64)

    # Annualized return / annualized vol component
    mean_ret = float(np.mean(returns))
    std_ret = float(np.std(returns, ddof=1))
    if std_ret == 0.0:
        sharpe_component = 0.0
    else:
        sharpe_component = mean_ret / std_ret

    # Drawdown penalty component (Ulcer Index based)
    ulcer = compute_ulcer_index(equity)
    if ulcer == 0.0:
        dd_penalty = 1.0  # No drawdown = no penalty
    else:
        dd_penalty = 1.0 / (1.0 + ulcer / 100.0)

    return float(sharpe_component * dd_penalty)


def compute_all_quality_metrics(
    candidate_id: int,
    equity_curve: np.ndarray,
    returns: np.ndarray,
    sharpe: float,
    n_trials: int,
    sharpe_std: float,
) -> EquityCurveQuality:
    """Compute all five quality metrics for a single candidate.

    Args:
        candidate_id: Unique candidate identifier.
        equity_curve: Cumulative equity curve.
        returns: Period returns array.
        sharpe: Observed Sharpe ratio.
        n_trials: Total trials for DSR deflation.
        sharpe_std: Standard deviation of Sharpe estimates.

    Returns:
        EquityCurveQuality with all five metrics.
    """
    return EquityCurveQuality(
        candidate_id=candidate_id,
        k_ratio=compute_k_ratio(equity_curve),
        ulcer_index=compute_ulcer_index(equity_curve),
        dsr=compute_dsr(sharpe, n_trials, sharpe_std),
        gain_to_pain=compute_gain_to_pain(returns),
        serenity_ratio=compute_serenity_ratio(returns, equity_curve),
    )
