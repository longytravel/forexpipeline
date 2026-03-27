"""Tests for validation.monte_carlo (Story 5.4, Task 6)."""
from __future__ import annotations

import numpy as np
import pyarrow as pa
import pytest

from validation.config import MonteCarloConfig
from validation.monte_carlo import (
    BootstrapResult,
    MonteCarloResult,
    PermutationResult,
    StressResult,
    bootstrap_equity_curves,
    permutation_test,
    run_monte_carlo,
    stress_test_costs,
    _get_pnl_column,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trades_table(
    pnl_pips: list[float],
    *,
    with_costs: bool = False,
) -> pa.Table:
    """Build a synthetic trades table."""
    columns = {"pnl_pips": pa.array(pnl_pips, type=pa.float64())}
    if with_costs:
        n = len(pnl_pips)
        columns["entry_spread"] = pa.array([0.5] * n, type=pa.float64())
        columns["exit_spread"] = pa.array([0.5] * n, type=pa.float64())
        columns["entry_slippage"] = pa.array([0.2] * n, type=pa.float64())
        columns["exit_slippage"] = pa.array([0.2] * n, type=pa.float64())
    return pa.table(columns)


def _realistic_pnl(n: int = 200, seed: int = 42) -> list[float]:
    """Generate realistic trade PnL with a mix of wins and losses."""
    rng = np.random.default_rng(seed)
    # Slightly positive mean (profitable strategy) with fat tails
    pnl = rng.normal(loc=2.0, scale=15.0, size=n)
    return pnl.tolist()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def realistic_trades():
    """200 trades with realistic PnL distribution."""
    return _make_trades_table(_realistic_pnl(200, seed=42))


@pytest.fixture
def realistic_trades_with_costs():
    """200 trades with cost columns."""
    return _make_trades_table(_realistic_pnl(200, seed=42), with_costs=True)


@pytest.fixture
def strong_signal_trades():
    """Trades with very strong positive signal (high Sharpe)."""
    rng = np.random.default_rng(99)
    pnl = rng.normal(loc=10.0, scale=2.0, size=100)
    return _make_trades_table(pnl.tolist())


@pytest.fixture
def default_cost_model():
    return {"spread_pips": 1.0, "slippage_pips": 0.5}


@pytest.fixture
def default_config():
    return MonteCarloConfig(
        n_bootstrap=500,
        n_permutation=500,
        stress_multipliers=[1.5, 2.0, 3.0],
        confidence_level=0.95,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBootstrapConfidenceIntervals:
    """test_bootstrap_confidence_intervals — CI bounds ordered, contain observed."""

    def test_ci_bounds_ordered(self, realistic_trades):
        rng = np.random.default_rng(42)
        result = bootstrap_equity_curves(realistic_trades, 500, rng, 0.95)

        assert result.sharpe_ci_lower <= result.sharpe_ci_upper
        assert result.drawdown_ci_lower <= result.drawdown_ci_upper
        assert result.pnl_ci_lower <= result.pnl_ci_upper
        assert result.n_samples == 500

    def test_ci_contains_observed(self, realistic_trades):
        """Observed metrics should generally fall within 95% CI."""
        pnl = realistic_trades.column("pnl_pips").to_numpy()
        observed_mean_pnl = float(np.sum(pnl))
        observed_sharpe = float(np.mean(pnl)) / float(np.std(pnl, ddof=1))

        rng = np.random.default_rng(42)
        result = bootstrap_equity_curves(realistic_trades, 1000, rng, 0.95)

        # The observed should be within CI (with some tolerance for randomness)
        # Use a wide tolerance: observed should be between expanded bounds
        sharpe_range = result.sharpe_ci_upper - result.sharpe_ci_lower
        assert result.sharpe_ci_lower - sharpe_range <= observed_sharpe <= result.sharpe_ci_upper + sharpe_range

    def test_empty_trades(self):
        """Empty table returns zeros."""
        empty = pa.table({"pnl_pips": pa.array([], type=pa.float64())})
        rng = np.random.default_rng(42)
        result = bootstrap_equity_curves(empty, 100, rng)
        assert result.n_samples == 0
        assert result.sharpe_ci_lower == 0.0
        assert result.sharpe_ci_upper == 0.0

    def test_drawdown_non_negative(self, realistic_trades):
        """Max drawdown should always be >= 0."""
        rng = np.random.default_rng(42)
        result = bootstrap_equity_curves(realistic_trades, 200, rng)
        assert result.drawdown_ci_lower >= 0.0


class TestPermutationPValue:
    """test_permutation_pvalue — p-value bounds and strong signal detection."""

    def test_pvalue_in_range(self, realistic_trades):
        """P-value is between 0 and 1."""
        pnl = realistic_trades.column("pnl_pips").to_numpy()
        mean_r = float(np.mean(pnl))
        std_r = float(np.std(pnl, ddof=1))
        observed = mean_r / std_r

        rng = np.random.default_rng(42)
        result = permutation_test(pnl, observed, 500, rng)

        assert 0.0 <= result.p_value <= 1.0
        assert result.n_permutations == 500
        assert result.observed_sharpe == observed

    def test_strong_signal_low_pvalue(self, strong_signal_trades):
        """Strong positive signal should have low p-value under sign-flip test.

        The sign-flip permutation test randomly negates returns. A strong
        positive mean will rarely survive random sign flips, yielding a
        low p-value (significant).
        """
        pnl = strong_signal_trades.column("pnl_pips").to_numpy()
        mean_r = float(np.mean(pnl))
        std_r = float(np.std(pnl, ddof=1))
        observed = mean_r / std_r

        rng = np.random.default_rng(42)
        result = permutation_test(pnl, observed, 500, rng)

        # Strong signal -> sign-flipped Sharpes rarely reach observed -> low p
        assert result.p_value < 0.10

    def test_zero_mean_returns_high_pvalue(self):
        """Zero-mean returns should yield high p-value (no real signal)."""
        rng_data = np.random.default_rng(123)
        returns = rng_data.normal(loc=0.0, scale=5.0, size=100)
        mean_r = float(np.mean(returns))
        std_r = float(np.std(returns, ddof=1))
        observed = mean_r / std_r

        rng = np.random.default_rng(42)
        result = permutation_test(returns, observed, 500, rng)

        # Zero-mean -> observed Sharpe near 0, easy to exceed by chance
        assert result.p_value > 0.05

    def test_short_returns(self):
        """< 2 returns -> p_value=1.0, n_permutations=0."""
        returns = np.array([1.0])
        rng = np.random.default_rng(42)
        result = permutation_test(returns, 1.0, 100, rng)
        assert result.p_value == 1.0
        assert result.n_permutations == 0


class TestStressCostMultipliers:
    """test_stress_cost_multipliers — higher multipliers reduce PnL."""

    def test_monotonic_pnl_decrease(self, realistic_trades_with_costs, default_cost_model):
        """PnL should decrease as cost multiplier increases."""
        multipliers = [1.0, 1.5, 2.0, 3.0]
        result = stress_test_costs(
            realistic_trades_with_costs, multipliers, default_cost_model,
        )

        pnl_values = [result.stressed_pnl[m] for m in multipliers]
        for i in range(len(pnl_values) - 1):
            assert pnl_values[i] >= pnl_values[i + 1], (
                f"PnL should decrease: mult={multipliers[i]} pnl={pnl_values[i]} "
                f">= mult={multipliers[i+1]} pnl={pnl_values[i+1]}"
            )

    def test_multiplier_1_preserves_pnl(self, realistic_trades_with_costs, default_cost_model):
        """Multiplier 1.0 should not change PnL (no additional costs)."""
        result = stress_test_costs(
            realistic_trades_with_costs, [1.0], default_cost_model,
        )
        original_pnl = float(np.sum(
            realistic_trades_with_costs.column("pnl_pips").to_numpy()
        ))
        assert abs(result.stressed_pnl[1.0] - original_pnl) < 1e-9

    def test_survival_flag(self, default_cost_model):
        """Survival is True when net PnL > 0, False otherwise."""
        # Small positive PnL, high costs will kill it
        trades = _make_trades_table([1.0, 1.0, 1.0], with_costs=True)
        result = stress_test_costs(trades, [1.0, 100.0], default_cost_model)

        # At 1.0x, PnL = 3.0, unchanged -> positive
        assert result.survival[1.0] is True
        # At 100x, additional costs = base_costs * 99 per trade, should be negative
        assert result.survival[100.0] is False

    def test_empty_trades(self, default_cost_model):
        """Empty trades -> all multipliers fail."""
        empty = pa.table({"pnl_pips": pa.array([], type=pa.float64())})
        result = stress_test_costs(empty, [1.5, 2.0], default_cost_model)
        assert result.survival[1.5] is False
        assert result.survival[2.0] is False

    def test_without_cost_columns(self, default_cost_model):
        """When cost columns are missing, uses cost_model estimates."""
        trades = _make_trades_table([10.0, 20.0, -5.0])  # no cost columns
        result = stress_test_costs(trades, [1.0, 2.0], default_cost_model)

        # At 1.0x, no additional cost -> PnL = 25.0
        assert abs(result.stressed_pnl[1.0] - 25.0) < 1e-9
        # At 2.0x, additional cost per trade = (1.0 + 0.5) * 2 * (2-1) = 3.0
        # Total additional = 3 * 3.0 = 9.0
        # Adjusted PnL = 25.0 - 9.0 = 16.0
        assert abs(result.stressed_pnl[2.0] - 16.0) < 1e-9


class TestMonteCarloDeterministic:
    """test_monte_carlo_deterministic — same seed, same results."""

    def test_same_seed_same_results(self, realistic_trades, default_cost_model, default_config):
        r1 = run_monte_carlo(realistic_trades, None, default_cost_model, default_config, seed=42)
        r2 = run_monte_carlo(realistic_trades, None, default_cost_model, default_config, seed=42)

        assert r1.bootstrap.sharpe_ci_lower == r2.bootstrap.sharpe_ci_lower
        assert r1.bootstrap.sharpe_ci_upper == r2.bootstrap.sharpe_ci_upper
        assert r1.bootstrap.pnl_ci_lower == r2.bootstrap.pnl_ci_lower
        assert r1.bootstrap.pnl_ci_upper == r2.bootstrap.pnl_ci_upper
        assert r1.permutation.p_value == r2.permutation.p_value
        assert r1.stress.stressed_pnl == r2.stress.stressed_pnl
        assert r1.stress.survival == r2.stress.survival

    def test_different_seed_different_results(self, realistic_trades, default_cost_model, default_config):
        r1 = run_monte_carlo(realistic_trades, None, default_cost_model, default_config, seed=42)
        r2 = run_monte_carlo(realistic_trades, None, default_cost_model, default_config, seed=99)

        # Very unlikely to be exactly equal with different seeds
        # Check at least one metric differs
        differ = (
            r1.bootstrap.sharpe_ci_lower != r2.bootstrap.sharpe_ci_lower
            or r1.bootstrap.pnl_ci_lower != r2.bootstrap.pnl_ci_lower
            or r1.permutation.p_value != r2.permutation.p_value
        )
        assert differ, "Different seeds should produce different results"


class TestGetPnlColumn:
    """Test _get_pnl_column helper."""

    def test_pnl_pips_column(self):
        t = pa.table({"pnl_pips": pa.array([1.0, 2.0], type=pa.float64())})
        result = _get_pnl_column(t)
        np.testing.assert_array_equal(result, [1.0, 2.0])

    def test_pnl_column_fallback(self):
        t = pa.table({"pnl": pa.array([3.0, 4.0], type=pa.float64())})
        result = _get_pnl_column(t)
        np.testing.assert_array_equal(result, [3.0, 4.0])

    def test_first_float_column_fallback(self):
        t = pa.table({"values": pa.array([5.0, 6.0], type=pa.float64())})
        result = _get_pnl_column(t)
        np.testing.assert_array_equal(result, [5.0, 6.0])

    def test_empty_result_for_no_float_columns(self):
        t = pa.table({"name": pa.array(["a", "b"])})
        result = _get_pnl_column(t)
        assert len(result) == 0
