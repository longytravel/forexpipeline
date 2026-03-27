"""Tests for walk-forward rolling OOS validator (Story 5.4, Task 3)."""
from __future__ import annotations

import pytest

from validation.config import WalkForwardConfig
from validation.walk_forward import (
    WindowSpec,
    generate_walk_forward_windows,
    run_walk_forward,
)


class TestWalkForwardWindowGeneration:
    """test_walk_forward_window_generation — 5 windows for 100000 bars."""

    def test_generates_expected_window_count(self):
        config = WalkForwardConfig(
            n_windows=5, train_ratio=0.80, purge_bars=100, embargo_bars=50
        )
        windows = generate_walk_forward_windows(100_000, config)
        assert len(windows) == 5

    def test_all_windows_have_valid_boundaries(self):
        config = WalkForwardConfig(
            n_windows=5, train_ratio=0.80, purge_bars=100, embargo_bars=50
        )
        windows = generate_walk_forward_windows(100_000, config)
        for w in windows:
            assert w.train_start >= 0
            assert w.train_end > w.train_start
            assert w.test_start >= 0
            assert w.test_end > w.test_start
            assert w.test_end <= 100_000

    def test_window_ids_are_sequential(self):
        config = WalkForwardConfig(
            n_windows=5, train_ratio=0.80, purge_bars=100, embargo_bars=50
        )
        windows = generate_walk_forward_windows(100_000, config)
        for i, w in enumerate(windows):
            assert w.window_id == i

    def test_test_windows_advance_over_data(self):
        """Test segments should move forward with each window."""
        config = WalkForwardConfig(
            n_windows=5, train_ratio=0.80, purge_bars=100, embargo_bars=50
        )
        windows = generate_walk_forward_windows(100_000, config)
        for i in range(1, len(windows)):
            assert windows[i].test_start > windows[i - 1].test_start

    def test_anchored_train_starts_at_zero(self):
        """Anchored walk-forward: all train segments start at bar 0."""
        config = WalkForwardConfig(
            n_windows=5, train_ratio=0.80, purge_bars=100, embargo_bars=50
        )
        windows = generate_walk_forward_windows(100_000, config)
        for w in windows:
            assert w.train_start == 0


class TestWalkForwardPurgeEmbargo:
    """test_walk_forward_purge_embargo — purge/embargo gaps exist."""

    def test_purge_gap_exists_between_train_and_test(self):
        purge = 200
        embargo = 100
        config = WalkForwardConfig(
            n_windows=5, train_ratio=0.80, purge_bars=purge, embargo_bars=embargo
        )
        windows = generate_walk_forward_windows(100_000, config)
        for w in windows:
            # There must be a gap between train_end and test_start
            gap = w.test_start - w.train_end
            assert gap >= purge, (
                f"Window {w.window_id}: gap={gap} < purge={purge}"
            )

    def test_embargo_accounted_in_test_start(self):
        purge = 200
        embargo = 100
        config = WalkForwardConfig(
            n_windows=5, train_ratio=0.80, purge_bars=purge, embargo_bars=embargo
        )
        windows = generate_walk_forward_windows(100_000, config)
        for w in windows:
            # test_start should be at least purge_end + embargo
            assert w.test_start >= w.purge_end + embargo

    def test_purge_region_is_between_train_and_test(self):
        config = WalkForwardConfig(
            n_windows=5, train_ratio=0.80, purge_bars=200, embargo_bars=100
        )
        windows = generate_walk_forward_windows(100_000, config)
        for w in windows:
            assert w.purge_start >= w.train_end or w.purge_start == w.train_end
            assert w.purge_end <= w.test_start


class TestWalkForwardTemporalOrdering:
    """test_walk_forward_temporal_ordering — train_end < test_start."""

    def test_train_ends_before_test_starts(self):
        config = WalkForwardConfig(
            n_windows=5, train_ratio=0.80, purge_bars=100, embargo_bars=50
        )
        windows = generate_walk_forward_windows(100_000, config)
        for w in windows:
            assert w.train_end < w.test_start, (
                f"Window {w.window_id}: train_end={w.train_end} >= test_start={w.test_start}"
            )

    def test_temporal_ordering_with_large_purge(self):
        config = WalkForwardConfig(
            n_windows=5, train_ratio=0.80, purge_bars=1440, embargo_bars=720
        )
        windows = generate_walk_forward_windows(100_000, config)
        for w in windows:
            assert w.train_end < w.test_start

    def test_temporal_ordering_with_many_windows(self):
        config = WalkForwardConfig(
            n_windows=10, train_ratio=0.80, purge_bars=50, embargo_bars=25
        )
        windows = generate_walk_forward_windows(100_000, config)
        for w in windows:
            assert w.train_end < w.test_start


class TestWalkForwardDeterministic:
    """test_walk_forward_deterministic — same inputs produce same outputs."""

    def test_window_generation_is_deterministic(self):
        config = WalkForwardConfig(
            n_windows=5, train_ratio=0.80, purge_bars=100, embargo_bars=50
        )
        windows_a = generate_walk_forward_windows(100_000, config)
        windows_b = generate_walk_forward_windows(100_000, config)

        assert len(windows_a) == len(windows_b)
        for a, b in zip(windows_a, windows_b):
            assert a.window_id == b.window_id
            assert a.train_start == b.train_start
            assert a.train_end == b.train_end
            assert a.test_start == b.test_start
            assert a.test_end == b.test_end
            assert a.purge_start == b.purge_start
            assert a.purge_end == b.purge_end

    def test_run_walk_forward_deterministic(self):
        """Full run_walk_forward produces identical results with same seed."""
        from pathlib import Path
        from unittest.mock import MagicMock

        config = WalkForwardConfig(
            n_windows=3, train_ratio=0.80, purge_bars=50, embargo_bars=25
        )
        dispatcher = MagicMock()
        dispatcher.evaluate_candidate = MagicMock(return_value={
            "sharpe": 1.5, "profit_factor": 1.8, "max_drawdown": 0.05,
            "trade_count": 42, "net_pnl": 500.0,
        })

        result_a = run_walk_forward(
            candidate={"param": 1}, market_data_path=Path("dummy.arrow"),
            strategy_spec={}, cost_model={}, config=config,
            dispatcher=dispatcher, seed=42, data_length=50_000,
        )
        # Reset mock call count but keep return value
        dispatcher.evaluate_candidate.reset_mock()

        result_b = run_walk_forward(
            candidate={"param": 1}, market_data_path=Path("dummy.arrow"),
            strategy_spec={}, cost_model={}, config=config,
            dispatcher=dispatcher, seed=42, data_length=50_000,
        )

        assert result_a.aggregate_sharpe == result_b.aggregate_sharpe
        assert result_a.aggregate_pf == result_b.aggregate_pf
        assert result_a.is_oos_divergence == result_b.is_oos_divergence
        assert len(result_a.windows) == len(result_b.windows)


class TestWalkForwardShortData:
    """test_walk_forward_short_data — very short data returns empty."""

    def test_zero_length_returns_empty(self):
        config = WalkForwardConfig(
            n_windows=5, train_ratio=0.80, purge_bars=100, embargo_bars=50
        )
        windows = generate_walk_forward_windows(0, config)
        assert windows == []

    def test_negative_length_returns_empty(self):
        config = WalkForwardConfig(
            n_windows=5, train_ratio=0.80, purge_bars=100, embargo_bars=50
        )
        windows = generate_walk_forward_windows(-10, config)
        assert windows == []

    def test_data_shorter_than_gaps_returns_empty(self):
        config = WalkForwardConfig(
            n_windows=5, train_ratio=0.80, purge_bars=1440, embargo_bars=720
        )
        # 5 windows * (1440 + 720) = 10800 gap total, data only 5000
        windows = generate_walk_forward_windows(5000, config)
        assert windows == []

    def test_run_walk_forward_short_data_returns_empty_result(self):
        from pathlib import Path

        config = WalkForwardConfig(
            n_windows=5, train_ratio=0.80, purge_bars=1440, embargo_bars=720
        )

        class MockDispatcher:
            pass

        result = run_walk_forward(
            candidate={"param": 1}, market_data_path=Path("dummy.arrow"),
            strategy_spec={}, cost_model={}, config=config,
            dispatcher=MockDispatcher(), seed=42, data_length=100,
        )
        assert result.windows == []
        assert result.aggregate_sharpe == 0.0
        assert result.aggregate_pf == 0.0
