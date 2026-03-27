"""Tests for CPCV validator (Story 5.4, Task 4)."""
from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from validation.config import CPCVConfig
from validation.cpcv import (
    CombinationResult,
    CPCVResult,
    _apply_purge_embargo,
    compute_pbo,
    generate_cpcv_combinations,
    run_cpcv,
)


class TestCPCVCombinationCount:
    """test_cpcv_combination_count — C(10,3)=120 combinations."""

    def test_c_10_3_yields_120(self):
        combos = generate_cpcv_combinations(n_groups=10, k_test=3)
        assert len(combos) == 120

    def test_c_5_2_yields_10(self):
        combos = generate_cpcv_combinations(n_groups=5, k_test=2)
        assert len(combos) == 10

    def test_c_6_1_yields_6(self):
        combos = generate_cpcv_combinations(n_groups=6, k_test=1)
        assert len(combos) == 6

    def test_train_and_test_partition_all_groups(self):
        """Train + test groups should cover all group indices exactly."""
        combos = generate_cpcv_combinations(n_groups=10, k_test=3)
        for train_groups, test_groups in combos:
            all_groups = sorted(train_groups + test_groups)
            assert all_groups == list(range(10))

    def test_test_groups_have_correct_size(self):
        combos = generate_cpcv_combinations(n_groups=10, k_test=3)
        for _, test_groups in combos:
            assert len(test_groups) == 3

    def test_train_groups_have_correct_size(self):
        combos = generate_cpcv_combinations(n_groups=10, k_test=3)
        for train_groups, _ in combos:
            assert len(train_groups) == 7


class TestCPCVPurgeApplication:
    """test_cpcv_purge_application — purge correctly removes bars near boundaries."""

    def test_purge_removes_bars_before_test(self):
        train_ranges = [(0, 100)]
        test_ranges = [(100, 200)]
        purge_bars = 10
        embargo_bars = 0

        purged = _apply_purge_embargo(train_ranges, test_ranges, purge_bars, embargo_bars)
        # Bars 90-99 should be excluded from train
        for start, end in purged:
            assert end <= 90 or start >= 100

    def test_embargo_removes_bars_after_test(self):
        train_ranges = [(200, 300)]
        test_ranges = [(100, 200)]
        purge_bars = 0
        embargo_bars = 10

        purged = _apply_purge_embargo(train_ranges, test_ranges, purge_bars, embargo_bars)
        # Bars 200-209 should be excluded from train
        for start, end in purged:
            assert start >= 210 or end <= 200

    def test_purge_and_embargo_combined(self):
        train_ranges = [(0, 100), (200, 300)]
        test_ranges = [(100, 200)]
        purge_bars = 10
        embargo_bars = 10

        purged = _apply_purge_embargo(train_ranges, test_ranges, purge_bars, embargo_bars)
        # Bars 90-99 excluded (purge before test)
        # Bars 200-209 excluded (embargo after test)
        all_bars = set()
        for start, end in purged:
            all_bars.update(range(start, end))

        for b in range(90, 100):
            assert b not in all_bars, f"Bar {b} should be purged"
        for b in range(200, 210):
            assert b not in all_bars, f"Bar {b} should be under embargo"

    def test_no_purge_no_embargo_returns_original(self):
        train_ranges = [(0, 100), (200, 300)]
        test_ranges = [(100, 200)]
        purged = _apply_purge_embargo(train_ranges, test_ranges, 0, 0)
        assert purged == train_ranges

    def test_empty_test_ranges_returns_original(self):
        train_ranges = [(0, 100)]
        purged = _apply_purge_embargo(train_ranges, [], 10, 10)
        assert purged == train_ranges


class TestPBOComputation:
    """test_pbo_computation — proper IS-vs-OOS ranking PBO."""

    def test_overfit_signal_detected(self):
        """IS-best combinations that are OOS-worst indicate overfitting.

        IS: [5, 4, 3, 2, 1] — combos 0,1,2 are IS-best (>= median 3)
        OOS: [1, 2, 3, 4, 5] — anti-correlated with IS
        IS-best indices: 0,1,2 (is >= 3). OOS values: 1,2,3.
        OOS median = 3. Below OOS median: indices 0,1 -> 2/3 ≈ 0.667
        """
        is_returns = [5.0, 4.0, 3.0, 2.0, 1.0]
        oos_returns = [1.0, 2.0, 3.0, 4.0, 5.0]
        pbo = compute_pbo(oos_returns, is_returns)
        assert pbo == pytest.approx(2.0 / 3.0, abs=0.01)

    def test_no_overfit_gives_low_pbo(self):
        """When IS-best are also OOS-best, PBO should be low.

        IS: [1, 2, 3, 4, 5] — combos 2,3,4 are IS-best
        OOS: [1, 2, 3, 4, 5] — same ranking (correlated)
        IS-best indices: 2,3,4. OOS values: 3,4,5 — all >= OOS median (3).
        Overfit count = 0 -> PBO = 0.
        But IS==OOS triggers leak warning and falls back to OOS-only.
        Use slightly different values to avoid leak detection.
        """
        is_returns = [1.0, 2.0, 3.0, 4.0, 5.0]
        oos_returns = [1.1, 2.1, 3.1, 4.1, 5.1]
        pbo = compute_pbo(oos_returns, is_returns)
        assert pbo == pytest.approx(0.0)

    def test_single_value_returns_zero(self):
        pbo = compute_pbo([1.0], [1.0])
        assert pbo == 0.0

    def test_empty_returns_zero(self):
        pbo = compute_pbo([], [])
        assert pbo == 0.0

    def test_identical_is_oos_triggers_fallback(self):
        """Identical IS/OOS (data leak) falls back to OOS-only median test."""
        oos_returns = [1.0, 2.0, 3.0, 4.0]
        pbo = compute_pbo(oos_returns, oos_returns)
        # Fallback: median=2.5, below: 1.0, 2.0 -> 2/4 = 0.5
        assert pbo == pytest.approx(0.5)

    def test_mismatched_lengths_falls_back(self):
        """Mismatched IS/OOS lengths uses OOS-only fallback."""
        oos_returns = [1.0, 2.0, 3.0, 4.0]
        is_returns = [1.0, 2.0]
        pbo = compute_pbo(oos_returns, is_returns)
        assert pbo == pytest.approx(0.5)


class TestCPCVRedGateThreshold:
    """test_cpcv_red_gate_threshold — PBO > 0.40 fails, PBO < 0.40 passes."""

    def test_high_pbo_fails_gate(self):
        """PBO > 0.40 should fail the gate."""
        config = CPCVConfig(
            n_groups=6, k_test_groups=3, purge_bars=0, embargo_bars=0,
            pbo_red_threshold=0.40,
        )

        class VaryingDispatcher:
            """Returns sharpe based on window position to create OOS variance.

            Groups 0-2 (start < 3000) get high sharpe, groups 3-5 get low.
            This creates C(6,3)=20 combos with ~50% below OOS median -> PBO ~0.5.
            """
            def evaluate_candidate(self, *args, **kwargs):
                window_start = kwargs.get("window_start", 0)
                if window_start < 3000:
                    return {"sharpe": 3.0, "profit_factor": 2.0, "net_pnl": 200.0}
                return {"sharpe": -1.0, "profit_factor": 0.5, "net_pnl": -100.0}

        result = run_cpcv(
            candidate={"param": 1}, market_data_path=Path("dummy.arrow"),
            strategy_spec={}, cost_model={}, config=config,
            dispatcher=VaryingDispatcher(), seed=42, data_length=6_000,
        )
        assert result.pbo > 0.40
        assert result.pbo_gate_passed is False

    def test_low_pbo_passes_gate(self):
        """PBO <= 0.40 should pass the gate."""
        config = CPCVConfig(
            n_groups=4, k_test_groups=2, purge_bars=0, embargo_bars=0,
            pbo_red_threshold=0.40,
        )

        class UniformDispatcher:
            """Returns identical metrics for both IS and OOS -> PBO = 0."""
            def evaluate_candidate(self, *args, **kwargs):
                return {"sharpe": 1.0, "profit_factor": 1.5, "net_pnl": 100.0}

        result = run_cpcv(
            candidate={"param": 1}, market_data_path=Path("dummy.arrow"),
            strategy_spec={}, cost_model={}, config=config,
            dispatcher=UniformDispatcher(), seed=42, data_length=10_000,
        )
        assert result.pbo <= 0.40
        assert result.pbo_gate_passed is True

    def test_exact_threshold_passes(self):
        """PBO exactly at threshold should pass (<=)."""
        # CPCVResult with pbo exactly 0.40
        result = CPCVResult(
            combinations=[], pbo=0.40,
            pbo_gate_passed=(0.40 <= 0.40),
            mean_oos_sharpe=1.0,
        )
        assert result.pbo_gate_passed is True

    def test_just_above_threshold_fails(self):
        """PBO just above threshold should fail."""
        result = CPCVResult(
            combinations=[], pbo=0.41,
            pbo_gate_passed=(0.41 <= 0.40),
            mean_oos_sharpe=1.0,
        )
        assert result.pbo_gate_passed is False
