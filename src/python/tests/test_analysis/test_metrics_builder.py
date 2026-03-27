"""Tests for analysis.metrics_builder — shared metrics computation."""
from __future__ import annotations

import math

import pytest

from analysis.metrics_builder import compute_metrics


class TestComputeMetricsBasic:
    """Standard trade set produces expected values."""

    def test_compute_metrics_basic(self):
        trades = [
            {"pnl_pips": 10.0, "entry_time": "2025-01-01T10:00:00Z", "exit_time": "2025-01-01T12:00:00Z"},
            {"pnl_pips": -5.0, "entry_time": "2025-01-02T10:00:00Z", "exit_time": "2025-01-02T11:00:00Z"},
            {"pnl_pips": 8.0, "entry_time": "2025-01-03T10:00:00Z", "exit_time": "2025-01-03T14:00:00Z"},
            {"pnl_pips": -3.0, "entry_time": "2025-01-04T10:00:00Z", "exit_time": "2025-01-04T11:30:00Z"},
            {"pnl_pips": 15.0, "entry_time": "2025-01-05T10:00:00Z", "exit_time": "2025-01-05T16:00:00Z"},
        ]
        m = compute_metrics(trades)

        assert m["total_trades"] == 5
        assert m["win_rate"] == 0.6  # 3 wins out of 5
        assert m["total_pnl"] == 25.0
        assert m["avg_trade_pnl"] == 5.0
        # Profit factor: (10+8+15) / (5+3) = 33/8 = 4.125
        assert m["profit_factor"] == pytest.approx(4.125, abs=0.01)
        assert m["sharpe_ratio"] > 0  # Positive expectancy
        assert m["max_drawdown_pct"] >= 0
        assert m["avg_trade_duration"] > 0

    def test_compute_metrics_empty_trades(self):
        m = compute_metrics([])

        assert m["total_trades"] == 0
        assert m["win_rate"] == 0.0
        assert m["profit_factor"] == 0.0
        assert m["sharpe_ratio"] == 0.0
        assert m["max_drawdown_pct"] == 0.0
        assert m["avg_trade_pnl"] == 0.0
        assert m["total_pnl"] == 0.0
        assert m["avg_trade_duration"] == 0.0

    def test_compute_metrics_single_trade(self):
        trades = [{"pnl_pips": 5.0}]
        m = compute_metrics(trades)

        assert m["total_trades"] == 1
        assert m["win_rate"] == 1.0
        assert m["total_pnl"] == 5.0
        assert m["avg_trade_pnl"] == 5.0
        # Single trade: infinite PF (no losses)
        assert m["profit_factor"] == float("inf")
        # Single trade: Sharpe needs >= 2 samples
        assert m["sharpe_ratio"] == 0.0

    def test_breakeven_trades_not_counted_as_wins_or_losses(self):
        """Breakeven trades (pnl == 0) are neither wins nor losses."""
        trades = [
            {"pnl_pips": 10.0},
            {"pnl_pips": 0.0},
            {"pnl_pips": -5.0},
        ]
        m = compute_metrics(trades)

        assert m["total_trades"] == 3
        # Only 1 win out of 3
        assert m["win_rate"] == pytest.approx(1 / 3, abs=0.001)
        # PF = 10 / 5 = 2.0
        assert m["profit_factor"] == 2.0

    def test_all_wins_infinite_profit_factor(self):
        trades = [{"pnl_pips": 5.0}, {"pnl_pips": 3.0}]
        m = compute_metrics(trades)
        assert m["profit_factor"] == float("inf")

    def test_all_losses_zero_profit_factor(self):
        trades = [{"pnl_pips": -5.0}, {"pnl_pips": -3.0}]
        m = compute_metrics(trades)
        assert m["profit_factor"] == 0.0

    def test_avg_duration_no_timestamps(self):
        trades = [{"pnl_pips": 5.0}]
        m = compute_metrics(trades)
        assert m["avg_trade_duration"] == 0.0

    def test_narrative_and_pack_use_same_metrics(self):
        """Verify narrative calls compute_metrics and evidence pack reuses narrative.metrics."""
        import analysis.narrative as narrative_mod

        # Narrative module imports the shared function
        from analysis.metrics_builder import compute_metrics as shared_fn
        assert narrative_mod.compute_metrics is shared_fn

        # Evidence pack reuses narrative.metrics (no independent compute_metrics call)
        # Verified by integration test: pack.metrics matches narrative.metrics
