"""Tests for validation.regime_analysis (Story 5.4, Task 7)."""
from __future__ import annotations

import numpy as np
import pyarrow as pa
import pytest

from validation.config import RegimeConfig
from validation.regime_analysis import (
    RegimeBucket,
    RegimeResult,
    classify_regimes,
    run_regime_analysis,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic data factories
# ---------------------------------------------------------------------------

def _make_market_data(n_bars: int = 5000, seed: int = 42) -> pa.Table:
    """Create synthetic M1 market data with varying volatility regimes.

    First third: low vol, second third: medium vol, last third: high vol.
    """
    rng = np.random.default_rng(seed)
    timestamps = np.arange(n_bars, dtype=np.int64)

    # Simulate price series with regime-varying volatility
    base_price = 1.1000
    vol_scales = np.concatenate([
        np.full(n_bars // 3, 0.0001),           # low vol
        np.full(n_bars // 3, 0.0005),           # medium vol
        np.full(n_bars - 2 * (n_bars // 3), 0.0015),  # high vol
    ])
    moves = rng.normal(0, vol_scales)
    close = base_price + np.cumsum(moves)
    high = close + np.abs(rng.normal(0, vol_scales))
    low = close - np.abs(rng.normal(0, vol_scales))
    open_ = close + rng.normal(0, vol_scales * 0.5)
    bid = close - 0.00005
    ask = close + 0.00005

    # Assign sessions cyclically: asian, london, new_york, london_ny_overlap
    sessions_list = ["asian", "london", "new_york", "london_ny_overlap"]
    session_labels = [sessions_list[i % len(sessions_list)] for i in range(n_bars)]

    quarantined = [False] * n_bars

    return pa.table({
        "timestamp": pa.array(timestamps, type=pa.int64()),
        "open": pa.array(open_, type=pa.float64()),
        "high": pa.array(high, type=pa.float64()),
        "low": pa.array(low, type=pa.float64()),
        "close": pa.array(close, type=pa.float64()),
        "bid": pa.array(bid, type=pa.float64()),
        "ask": pa.array(ask, type=pa.float64()),
        "session": pa.array(session_labels, type=pa.utf8()),
        "quarantined": pa.array(quarantined, type=pa.bool_()),
    })


def _make_trade_results(
    n_trades: int = 200,
    sessions: list[str] | None = None,
    seed: int = 42,
    max_entry_time: int = 5000,
) -> pa.Table:
    """Create synthetic trade results with entry_time, pnl_pips, entry_session."""
    rng = np.random.default_rng(seed)
    if sessions is None:
        sessions = ["asian", "london", "new_york", "london_ny_overlap"]

    trade_ids = [f"T{i:04d}" for i in range(n_trades)]
    entry_times = np.sort(rng.integers(0, max_entry_time, size=n_trades)).astype(np.int64)
    pnl_pips = rng.normal(0.5, 5.0, size=n_trades)
    entry_sessions = [sessions[i % len(sessions)] for i in range(n_trades)]

    return pa.table({
        "trade_id": pa.array(trade_ids, type=pa.utf8()),
        "entry_time": pa.array(entry_times, type=pa.int64()),
        "pnl_pips": pa.array(pnl_pips, type=pa.float64()),
        "entry_session": pa.array(entry_sessions, type=pa.utf8()),
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestClassifyRegimes:
    """Test classify_regimes — volatility tercile classification."""

    def test_regime_classification(self):
        """Classify synthetic market data into terciles, verify 3 levels present."""
        config = RegimeConfig()
        market_data = _make_market_data(n_bars=5000)

        classified = classify_regimes(market_data, config)

        # New column must exist
        assert "volatility_tercile" in classified.column_names

        # Exactly 3 distinct labels
        labels = set(classified.column("volatility_tercile").to_pylist())
        assert labels == {"low", "medium", "high"}

        # Row count unchanged
        assert len(classified) == len(market_data)

    def test_classify_empty_table(self):
        """Empty market data returns empty table (no crash)."""
        config = RegimeConfig()
        empty = pa.table({
            "timestamp": pa.array([], type=pa.int64()),
            "open": pa.array([], type=pa.float64()),
            "high": pa.array([], type=pa.float64()),
            "low": pa.array([], type=pa.float64()),
            "close": pa.array([], type=pa.float64()),
        })
        result = classify_regimes(empty, config)
        assert len(result) == 0


class TestRunRegimeAnalysis:
    """Test run_regime_analysis — cross-tabulation and bucket logic."""

    def test_regime_cross_tabulation(self):
        """Correct number of buckets: 3 vol levels * 4 sessions = 12."""
        config = RegimeConfig()
        market_data = _make_market_data(n_bars=5000)
        trade_results = _make_trade_results(n_trades=200)

        result = run_regime_analysis(trade_results, market_data, config)

        assert result.total_buckets == 3 * len(config.sessions)
        assert result.total_buckets == 12
        assert len(result.buckets) == 12

        # Each bucket has expected fields
        for bucket in result.buckets:
            assert bucket.volatility in ("low", "medium", "high")
            assert bucket.session in config.sessions
            assert isinstance(bucket.trade_count, int)
            assert isinstance(bucket.win_rate, float)
            assert isinstance(bucket.sharpe, float)
            assert isinstance(bucket.sufficient, bool)

    def test_regime_min_trade_threshold(self):
        """Buckets with <30 trades are marked insufficient."""
        # Use very few trades so most buckets are below threshold
        config = RegimeConfig(min_trades_per_bucket=30)
        market_data = _make_market_data(n_bars=5000)
        # Only 24 trades => at most 24/12=2 per bucket if evenly distributed
        trade_results = _make_trade_results(n_trades=24)

        result = run_regime_analysis(trade_results, market_data, config)

        # No bucket should have >= 30 trades
        for bucket in result.buckets:
            assert not bucket.sufficient, (
                f"Bucket {bucket.volatility}_{bucket.session} has "
                f"{bucket.trade_count} trades but should be insufficient"
            )
        assert result.sufficient_buckets == 0

    def test_regime_insufficient_bucket_flagging(self):
        """Empty/insufficient buckets are flagged, not fabricated with fake stats."""
        config = RegimeConfig(min_trades_per_bucket=30)
        market_data = _make_market_data(n_bars=5000)
        # Create trades in only 1 session so most buckets are empty
        trade_results = _make_trade_results(
            n_trades=100, sessions=["london"]
        )

        result = run_regime_analysis(trade_results, market_data, config)

        # Should have all 12 buckets
        assert result.total_buckets == 12

        # Only london buckets can have trades
        for bucket in result.buckets:
            if bucket.session != "london":
                assert bucket.trade_count == 0
                assert bucket.win_rate == 0.0
                assert bucket.avg_pnl == 0.0
                assert bucket.sharpe == 0.0
                assert not bucket.sufficient

        # Weakest regime should be among sufficient london buckets (or "none")
        if result.sufficient_buckets > 0:
            assert "london" in result.weakest_regime
        else:
            assert result.weakest_regime == "none"

    def test_empty_trade_results(self):
        """Zero trades returns empty result, no crash."""
        config = RegimeConfig()
        market_data = _make_market_data(n_bars=1000)
        trades = pa.table({
            "trade_id": pa.array([], type=pa.utf8()),
            "entry_time": pa.array([], type=pa.int64()),
            "pnl_pips": pa.array([], type=pa.float64()),
            "entry_session": pa.array([], type=pa.utf8()),
        })

        result = run_regime_analysis(trades, market_data, config)
        assert result.total_buckets == 0
        assert result.weakest_regime == "none"

    def test_weakest_regime_identification(self):
        """Weakest regime is the sufficient bucket with lowest Sharpe."""
        config = RegimeConfig(min_trades_per_bucket=5)
        market_data = _make_market_data(n_bars=5000)
        # Many trades to ensure sufficient buckets
        trade_results = _make_trade_results(n_trades=1000)

        result = run_regime_analysis(trade_results, market_data, config)

        sufficient = [b for b in result.buckets if b.sufficient]
        if sufficient:
            expected_weakest = min(sufficient, key=lambda b: b.sharpe)
            assert result.weakest_regime == f"{expected_weakest.volatility}_{expected_weakest.session}"
