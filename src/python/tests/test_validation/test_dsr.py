"""Tests for validation.dsr (Story 5.4, Task 8)."""
from __future__ import annotations

import numpy as np
import pytest

from validation.dsr import DSRResult, compute_dsr, compute_expected_max_sharpe


class TestExpectedMaxSharpe:
    """Test compute_expected_max_sharpe — analytical properties."""

    def test_single_trial(self):
        """With 1 trial, expected max Sharpe is 0."""
        assert compute_expected_max_sharpe(1, sharpe_std=1.0) == 0.0

    def test_monotone_in_trials(self):
        """More trials => higher expected max Sharpe (monotonically increasing)."""
        vals = [
            compute_expected_max_sharpe(n, sharpe_std=1.0)
            for n in [10, 100, 1000, 10000]
        ]
        for i in range(len(vals) - 1):
            assert vals[i] < vals[i + 1], (
                f"Expected max SR should increase with trials: "
                f"{vals[i]:.4f} >= {vals[i+1]:.4f}"
            )

    def test_scales_with_sharpe_std(self):
        """Expected max Sharpe scales with sharpe_std."""
        e1 = compute_expected_max_sharpe(100, sharpe_std=1.0)
        e2 = compute_expected_max_sharpe(100, sharpe_std=2.0)
        assert abs(e2 - 2.0 * e1) < 1e-10, "Should scale linearly with sharpe_std"

    def test_positive_for_many_trials(self):
        """E[max(SR)] is positive for N > 1."""
        assert compute_expected_max_sharpe(10, sharpe_std=1.0) > 0
        assert compute_expected_max_sharpe(1000, sharpe_std=1.0) > 0


class TestComputeDSR:
    """Test compute_dsr — deflated Sharpe ratio computation."""

    def test_dsr_known_values(self):
        """Verify DSR computation against known analytical properties.

        With a very high observed Sharpe relative to few trials,
        DSR should be high (close to 1) and pass.
        With observed Sharpe near the expected max, DSR ~ 0.5.
        """
        # Very strong signal with few trials => should easily pass
        # E[max(SR)] for 10 trials ~ 1.685, so observed=5.0 gives z ~ 3.3
        result_strong = compute_dsr(
            observed_sharpe=5.0,
            num_trials=10,
            sharpe_variance=1.0,
            significance_level=0.05,
        )
        assert result_strong.dsr > 0.95, f"Strong signal should have high DSR, got {result_strong.dsr}"
        assert result_strong.passed is True
        assert result_strong.p_value < 0.05

        # Observed Sharpe exactly at expected max => DSR ~ 0.5
        e_max = compute_expected_max_sharpe(100, sharpe_std=1.0)
        result_at_max = compute_dsr(
            observed_sharpe=e_max,
            num_trials=100,
            sharpe_variance=1.0,
            significance_level=0.05,
        )
        assert abs(result_at_max.dsr - 0.5) < 0.01, (
            f"At expected max, DSR should be ~0.5, got {result_at_max.dsr}"
        )
        assert abs(result_at_max.p_value - 0.5) < 0.01

    def test_dsr_multiple_testing_correction(self):
        """More trials => higher expected max SR => harder to pass.

        Same observed Sharpe should yield lower DSR with more trials.
        """
        observed = 2.0
        variance = 1.0

        result_10 = compute_dsr(
            observed_sharpe=observed, num_trials=10,
            sharpe_variance=variance,
        )
        result_100 = compute_dsr(
            observed_sharpe=observed, num_trials=100,
            sharpe_variance=variance,
        )
        result_1000 = compute_dsr(
            observed_sharpe=observed, num_trials=1000,
            sharpe_variance=variance,
        )

        # DSR should decrease with more trials (all else equal)
        assert result_10.dsr > result_100.dsr > result_1000.dsr, (
            f"DSR should decrease with more trials: "
            f"{result_10.dsr:.4f}, {result_100.dsr:.4f}, {result_1000.dsr:.4f}"
        )

        # Expected max Sharpe should increase with more trials
        assert (
            result_10.expected_max_sharpe
            < result_100.expected_max_sharpe
            < result_1000.expected_max_sharpe
        )

    def test_dsr_threshold(self):
        """DSR with significance_level=0.05, verify pass/fail boundary."""
        # Mediocre signal with many trials => should fail
        result_fail = compute_dsr(
            observed_sharpe=0.5,
            num_trials=1000,
            sharpe_variance=1.0,
            significance_level=0.05,
        )
        assert result_fail.passed is False, (
            f"Mediocre SR=0.5 with 1000 trials should fail, "
            f"p={result_fail.p_value:.4f}"
        )
        assert result_fail.p_value >= 0.05

        # Strong signal with few trials => should pass
        result_pass = compute_dsr(
            observed_sharpe=5.0,
            num_trials=10,
            sharpe_variance=1.0,
            significance_level=0.05,
        )
        assert result_pass.passed is True
        assert result_pass.p_value < 0.05

    def test_dsr_single_trial(self):
        """With 1 trial, DSR equals observed Sharpe and always passes."""
        result = compute_dsr(
            observed_sharpe=1.5, num_trials=1, sharpe_variance=1.0,
        )
        assert result.dsr == 1.5
        assert result.passed is True
        assert result.p_value == 0.0
        assert result.expected_max_sharpe == 0.0

    def test_dsr_result_fields(self):
        """DSRResult contains all expected fields with correct types."""
        result = compute_dsr(
            observed_sharpe=2.0, num_trials=50, sharpe_variance=0.5,
        )
        assert isinstance(result, DSRResult)
        assert isinstance(result.dsr, float)
        assert isinstance(result.p_value, float)
        assert isinstance(result.passed, bool)
        assert isinstance(result.num_trials, int)
        assert isinstance(result.expected_max_sharpe, float)
        assert 0.0 <= result.dsr <= 1.0
        assert 0.0 <= result.p_value <= 1.0
        assert result.num_trials == 50
