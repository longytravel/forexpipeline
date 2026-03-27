"""Monte Carlo simulator — bootstrap, permutation, stress (Story 5.4, Task 6).

Python-only computations on trade results. NO Rust dispatch needed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pyarrow as pa

from logging_setup.setup import get_logger
from validation.config import MonteCarloConfig

logger = get_logger("validation.monte_carlo")


@dataclass
class BootstrapResult:
    sharpe_ci_lower: float
    sharpe_ci_upper: float
    drawdown_ci_lower: float
    drawdown_ci_upper: float
    pnl_ci_lower: float
    pnl_ci_upper: float
    n_samples: int


@dataclass
class PermutationResult:
    observed_sharpe: float
    p_value: float
    n_permutations: int


@dataclass
class StressResult:
    multipliers: list[float]
    survival: dict[float, bool]  # multiplier -> survived (positive PnL)
    stressed_pnl: dict[float, float]  # multiplier -> net PnL after stress


@dataclass
class MonteCarloResult:
    bootstrap: BootstrapResult
    permutation: PermutationResult
    stress: StressResult
    artifact_path: Path | None = None


def bootstrap_equity_curves(
    trades: pa.Table,
    n_samples: int,
    rng: np.random.Generator,
    confidence_level: float = 0.95,
) -> BootstrapResult:
    """Bootstrap resample trade results with replacement.

    Rebuilds equity curves from resampled trade sequences.
    Computes confidence intervals for Sharpe, max drawdown, net PnL.
    """
    pnl_col = _get_pnl_column(trades)
    if len(pnl_col) == 0:
        return BootstrapResult(
            sharpe_ci_lower=0.0, sharpe_ci_upper=0.0,
            drawdown_ci_lower=0.0, drawdown_ci_upper=0.0,
            pnl_ci_lower=0.0, pnl_ci_upper=0.0,
            n_samples=0,
        )

    pnl_array = pnl_col

    sharpes = []
    drawdowns = []
    pnls = []

    for _ in range(n_samples):
        # Resample with replacement
        indices = rng.integers(0, len(pnl_array), size=len(pnl_array))
        resampled = pnl_array[indices]

        # Compute metrics on resampled sequence
        net_pnl = float(np.sum(resampled))
        pnls.append(net_pnl)

        mean_ret = float(np.mean(resampled))
        std_ret = float(np.std(resampled, ddof=1)) if len(resampled) > 1 else 1.0
        sharpe = mean_ret / std_ret if std_ret > 0 else 0.0
        sharpes.append(sharpe)

        # Max drawdown from cumulative equity
        cum_equity = np.cumsum(resampled)
        running_max = np.maximum.accumulate(cum_equity)
        drawdown = running_max - cum_equity
        max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0
        drawdowns.append(max_dd)

    alpha = 1.0 - confidence_level
    lower_pct = alpha / 2 * 100
    upper_pct = (1 - alpha / 2) * 100

    return BootstrapResult(
        sharpe_ci_lower=float(np.percentile(sharpes, lower_pct)),
        sharpe_ci_upper=float(np.percentile(sharpes, upper_pct)),
        drawdown_ci_lower=float(np.percentile(drawdowns, lower_pct)),
        drawdown_ci_upper=float(np.percentile(drawdowns, upper_pct)),
        pnl_ci_lower=float(np.percentile(pnls, lower_pct)),
        pnl_ci_upper=float(np.percentile(pnls, upper_pct)),
        n_samples=n_samples,
    )


def permutation_test(
    returns: np.ndarray,
    observed_sharpe: float,
    n_permutations: int,
    rng: np.random.Generator,
) -> PermutationResult:
    """Sign-flip permutation test for Sharpe ratio significance.

    Tests H0: mean return = 0 by randomly flipping signs of returns.
    This is order-invariant-safe: sign flips change the mean while
    preserving variance structure, unlike order shuffling which leaves
    mean/std unchanged and produces degenerate p-values.

    P-value = (count + 1) / (N + 1) per Phipson & Smyth (2010)
    to prevent impossible p=0.
    """
    if len(returns) < 2:
        return PermutationResult(
            observed_sharpe=observed_sharpe, p_value=1.0, n_permutations=0,
        )

    count_exceeding = 0
    for _ in range(n_permutations):
        # Sign-flip: randomly negate each return with 50% probability
        signs = rng.choice([-1.0, 1.0], size=len(returns))
        flipped = returns * signs
        mean_r = float(np.mean(flipped))
        std_r = float(np.std(flipped, ddof=1))
        perm_sharpe = mean_r / std_r if std_r > 0 else 0.0
        if perm_sharpe >= observed_sharpe:
            count_exceeding += 1

    # Corrected p-value: (count+1)/(N+1) prevents impossible p=0
    p_value = (count_exceeding + 1) / (n_permutations + 1)

    return PermutationResult(
        observed_sharpe=observed_sharpe,
        p_value=p_value,
        n_permutations=n_permutations,
    )


def stress_test_costs(
    trades: pa.Table,
    multipliers: list[float],
    cost_model: dict,
) -> StressResult:
    """Re-evaluate with widened spreads/slippage.

    Recalculates PnL from existing trade entry/exit prices with inflated costs.
    Does NOT re-run through Rust — answers "would these trades survive higher costs?"
    """
    survival = {}
    stressed_pnl = {}

    # Extract trade data
    pnl_col = _get_pnl_column(trades)
    if len(pnl_col) == 0:
        for m in multipliers:
            survival[m] = False
            stressed_pnl[m] = 0.0
        return StressResult(multipliers=multipliers, survival=survival, stressed_pnl=stressed_pnl)

    # Get cost columns if available
    has_costs = all(
        col in trades.column_names
        for col in ["entry_spread", "exit_spread", "entry_slippage", "exit_slippage"]
    )

    if has_costs:
        entry_spread = trades.column("entry_spread").to_numpy()
        exit_spread = trades.column("exit_spread").to_numpy()
        entry_slip = trades.column("entry_slippage").to_numpy()
        exit_slip = trades.column("exit_slippage").to_numpy()
        base_costs = entry_spread + exit_spread + entry_slip + exit_slip
    else:
        # Estimate costs from cost model
        avg_spread = cost_model.get("spread_pips", 1.0)
        avg_slippage = cost_model.get("slippage_pips", 0.5)
        base_costs = np.full(len(pnl_col), (avg_spread + avg_slippage) * 2)

    base_pnl = pnl_col

    for mult in multipliers:
        # Additional cost = base_costs * (mult - 1)
        additional_cost = base_costs * (mult - 1.0)
        adjusted_pnl = base_pnl - additional_cost
        net = float(np.sum(adjusted_pnl))
        stressed_pnl[mult] = net
        survival[mult] = net > 0

    return StressResult(
        multipliers=multipliers,
        survival=survival,
        stressed_pnl=stressed_pnl,
    )


def run_monte_carlo(
    trade_results: pa.Table,
    equity_curve: pa.Table | None,
    cost_model: dict,
    config: MonteCarloConfig,
    seed: int,
) -> MonteCarloResult:
    """Run full Monte Carlo analysis: bootstrap, permutation, stress.

    Input: trade results from walk-forward OOS windows.
    """
    rng = np.random.Generator(np.random.PCG64(seed))

    # Bootstrap
    bootstrap = bootstrap_equity_curves(
        trade_results, config.n_bootstrap, rng, config.confidence_level,
    )

    # Permutation test
    pnl_col = _get_pnl_column(trade_results)
    if len(pnl_col) > 1:
        mean_r = float(np.mean(pnl_col))
        std_r = float(np.std(pnl_col, ddof=1))
        observed_sharpe = mean_r / std_r if std_r > 0 else 0.0
    else:
        observed_sharpe = 0.0

    permutation = permutation_test(
        pnl_col, observed_sharpe, config.n_permutation, rng,
    )

    # Stress test
    stress = stress_test_costs(
        trade_results, config.stress_multipliers, cost_model,
    )

    logger.info(
        f"Monte Carlo complete: bootstrap CI=[{bootstrap.sharpe_ci_lower:.3f}, "
        f"{bootstrap.sharpe_ci_upper:.3f}], perm p={permutation.p_value:.3f}",
        extra={
            "component": "validation.monte_carlo",
            "ctx": {
                "bootstrap_ci": [bootstrap.sharpe_ci_lower, bootstrap.sharpe_ci_upper],
                "permutation_p": permutation.p_value,
                "stress_survival": stress.survival,
            },
        },
    )

    return MonteCarloResult(
        bootstrap=bootstrap,
        permutation=permutation,
        stress=stress,
    )


def _get_pnl_column(trades: pa.Table) -> np.ndarray:
    """Extract PnL column from trades table, handling both schemas."""
    if "pnl_pips" in trades.column_names:
        return trades.column("pnl_pips").to_numpy()
    if "pnl" in trades.column_names:
        return trades.column("pnl").to_numpy()
    if len(trades.column_names) > 0:
        # Last resort: use first numeric column
        for name in trades.column_names:
            col = trades.column(name)
            if pa.types.is_floating(col.type):
                return col.to_numpy()
    return np.array([], dtype=np.float64)
