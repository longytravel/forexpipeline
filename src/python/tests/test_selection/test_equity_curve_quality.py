"""Tests for equity curve quality metrics (Story 5.6, Task 9)."""
from __future__ import annotations

import numpy as np
import pytest

from selection.equity_curve_quality import (
    compute_all_quality_metrics,
    compute_dsr,
    compute_gain_to_pain,
    compute_k_ratio,
    compute_serenity_ratio,
    compute_ulcer_index,
)


class TestKRatio:
    def test_k_ratio_perfect_linear_curve(self):
        """Perfect linear equity curve → very high K-Ratio."""
        equity = np.linspace(100, 200, 100)
        k = compute_k_ratio(equity)
        assert k > 100.0  # Should be very high for perfect linearity

    def test_k_ratio_noisy_curve(self):
        """Noisy equity curve → lower K-Ratio than linear."""
        rng = np.random.default_rng(42)
        equity_linear = np.linspace(100, 200, 100)
        equity_noisy = equity_linear + rng.normal(0, 10, 100)
        k_noisy = compute_k_ratio(equity_noisy)
        k_linear = compute_k_ratio(equity_linear)
        assert k_noisy < k_linear

    def test_k_ratio_degenerate(self):
        """Single point or empty → 0.0."""
        assert compute_k_ratio(np.array([100])) == 0.0
        assert compute_k_ratio(np.array([])) == 0.0


class TestUlcerIndex:
    def test_ulcer_index_no_drawdown(self):
        """Monotonically increasing curve → Ulcer Index ≈ 0."""
        equity = np.linspace(100, 200, 100)
        ui = compute_ulcer_index(equity)
        assert ui == pytest.approx(0.0, abs=1e-10)

    def test_ulcer_index_deep_drawdown(self):
        """Deep drawdown → high Ulcer Index."""
        equity = np.array([100, 110, 120, 60, 70, 80, 90])  # 50% drawdown
        ui = compute_ulcer_index(equity)
        assert ui > 10.0  # Should be substantial

    def test_ulcer_index_degenerate(self):
        """Too few points → 0.0."""
        assert compute_ulcer_index(np.array([100])) == 0.0


class TestDSR:
    def test_dsr_high_sharpe_many_trials(self):
        """High Sharpe with many trials → DSR should show deflation effect."""
        dsr_few = compute_dsr(sharpe=2.0, n_trials=10, sharpe_std=0.5)
        dsr_many = compute_dsr(sharpe=2.0, n_trials=10000, sharpe_std=0.5)
        # More trials = more deflation → lower DSR
        assert dsr_few > dsr_many

    def test_dsr_low_trial_count(self):
        """Few trials → minimal deflation."""
        dsr = compute_dsr(sharpe=2.0, n_trials=5, sharpe_std=0.5)
        assert 0.0 <= dsr <= 1.0

    def test_dsr_degenerate(self):
        """Zero trials or zero std → 0.0."""
        assert compute_dsr(sharpe=2.0, n_trials=1, sharpe_std=0.5) == 0.0
        assert compute_dsr(sharpe=2.0, n_trials=10, sharpe_std=0.0) == 0.0


class TestGainToPain:
    def test_gain_to_pain_mixed(self):
        """Mixed returns → positive ratio."""
        returns = np.array([0.05, -0.02, 0.03, -0.01, 0.04])
        gtp = compute_gain_to_pain(returns)
        assert gtp > 0.0

    def test_gain_to_pain_all_positive(self):
        """All positive returns → capped at 1e6."""
        returns = np.array([0.01, 0.02, 0.03, 0.04])
        gtp = compute_gain_to_pain(returns)
        assert gtp == 1e6

    def test_gain_to_pain_empty(self):
        """Empty returns → 0.0."""
        assert compute_gain_to_pain(np.array([])) == 0.0


class TestSerenityRatio:
    def test_serenity_ratio_smooth_equity(self):
        """Smooth equity curve → higher serenity ratio."""
        equity_smooth = np.linspace(100, 200, 100)
        returns_smooth = np.diff(equity_smooth) / equity_smooth[:-1]
        sr_smooth = compute_serenity_ratio(returns_smooth, equity_smooth)

        rng = np.random.default_rng(42)
        equity_noisy = np.linspace(100, 200, 100) + rng.normal(0, 15, 100)
        equity_noisy = np.maximum(equity_noisy, 10)  # Prevent negative equity
        returns_noisy = np.diff(equity_noisy) / equity_noisy[:-1]
        sr_noisy = compute_serenity_ratio(returns_noisy, equity_noisy)

        assert sr_smooth > sr_noisy

    def test_serenity_ratio_degenerate(self):
        """Too few points → 0.0."""
        assert compute_serenity_ratio(np.array([0.01]), np.array([100])) == 0.0


class TestAllQualityMetrics:
    def test_compute_all_quality_metrics_integration(self):
        """All metrics computed and packaged correctly."""
        equity = np.linspace(100, 200, 100)
        returns = np.diff(equity) / equity[:-1]
        q = compute_all_quality_metrics(
            candidate_id=42,
            equity_curve=equity,
            returns=returns,
            sharpe=1.5,
            n_trials=100,
            sharpe_std=0.3,
        )

        assert q.candidate_id == 42
        assert q.k_ratio > 0
        assert q.ulcer_index >= 0
        assert 0 <= q.dsr <= 1
        assert q.gain_to_pain > 0
        assert q.serenity_ratio > 0

        # Serialization round-trip
        data = q.to_json()
        restored = type(q).from_json(data)
        assert restored.candidate_id == q.candidate_id
        assert restored.k_ratio == pytest.approx(q.k_ratio)
