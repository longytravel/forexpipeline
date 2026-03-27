"""Tests for signal pre-computation stage (D14).

Covers: column naming, indicator computation, forward-fill (no lookahead),
and end-to-end enrichment round-trip.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from orchestrator.signal_precompute import (
    build_signal_column_name,
    precompute_signals,
    precompute_signals_from_spec,
    _compute_indicator,
    _forward_fill_to_m1,
    _precompute_core,
    _rollup_timeframe,
)


# ---------------------------------------------------------------------------
# Column naming tests — must match Rust build_signal_column_name()
# ---------------------------------------------------------------------------

class TestBuildSignalColumnName:
    def test_sma_with_period(self):
        assert build_signal_column_name("sma", {"period": 20}) == "sma_20"

    def test_ema_with_period(self):
        assert build_signal_column_name("ema", {"period": 50}) == "ema_50"

    def test_sma_crossover_no_period_suffix(self):
        """sma_crossover has fast_period/slow_period, NOT period.
        Rust only appends 'period', 'length', 'window' keys."""
        params = {"fast_period": 20, "slow_period": 50}
        assert build_signal_column_name("sma_crossover", params) == "sma_crossover"

    def test_ema_crossover_no_period_suffix(self):
        params = {"fast_period": 12, "slow_period": 26}
        assert build_signal_column_name("ema_crossover", params) == "ema_crossover"

    def test_atr_with_period(self):
        assert build_signal_column_name("atr", {"period": 14}) == "atr_14"

    def test_rsi_with_period(self):
        assert build_signal_column_name("rsi", {"period": 14}) == "rsi_14"

    def test_bollinger_with_period(self):
        params = {"period": 20, "num_std": 2.0}
        assert build_signal_column_name("bollinger_bands", params) == "bollinger_bands_20"

    def test_float_period_truncated(self):
        assert build_signal_column_name("sma", {"period": 20.0}) == "sma_20"

    def test_window_key(self):
        assert build_signal_column_name("custom", {"window": 10}) == "custom_10"

    def test_length_key(self):
        assert build_signal_column_name("custom", {"length": 5}) == "custom_5"


# ---------------------------------------------------------------------------
# Synthetic M1 data helper
# ---------------------------------------------------------------------------

def _make_m1_data(n_hours: int = 100) -> pd.DataFrame:
    """Create synthetic M1 OHLCV data spanning n_hours.

    Generates a trending price series with known SMA crossover points.
    """
    n_bars = n_hours * 60  # M1 bars
    np.random.seed(42)

    # Create a price series with a clear trend change
    base = 1.10000
    # First half: downtrend, second half: uptrend
    half = n_bars // 2
    trend_down = np.linspace(0, -0.005, half)
    trend_up = np.linspace(-0.005, 0.005, n_bars - half)
    trend = np.concatenate([trend_down, trend_up])

    noise = np.random.normal(0, 0.0001, n_bars)
    closes = base + trend + noise

    # Generate OHLC from close
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    highs = np.maximum(opens, closes) + np.abs(noise) * 0.5
    lows = np.minimum(opens, closes) - np.abs(noise) * 0.5
    bids = closes - 0.00005
    asks = closes + 0.00005

    # Timestamps: starting 2025-01-06 00:00 UTC (Monday)
    start_ts = 1736121600  # 2025-01-06 00:00:00 UTC
    timestamps = np.arange(start_ts, start_ts + n_bars * 60, 60)

    # Session labels (simplified: all london for H1 0800-1600)
    sessions = []
    for ts in timestamps:
        hour = (ts % 86400) // 3600
        if 8 <= hour < 16:
            sessions.append("london")
        elif 0 <= hour < 8:
            sessions.append("asian")
        else:
            sessions.append("new_york")

    return pd.DataFrame({
        "timestamp": timestamps.astype(np.int64),
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "bid": bids,
        "ask": asks,
        "session": sessions,
        "quarantined": np.zeros(n_bars, dtype=bool),
    })


def _write_test_arrow(df: pd.DataFrame, path: Path) -> None:
    table = pa.Table.from_pandas(df, preserve_index=False)
    with ipc.new_file(str(path), table.schema) as writer:
        writer.write_table(table)


def _write_test_spec(path: Path, timeframe: str = "H1") -> None:
    spec = f"""
[metadata]
schema_version = "1"
name = "test-strategy"
version = "v001"
pair = "EURUSD"
timeframe = "{timeframe}"
created_by = "test"

[[entry_rules.conditions]]
indicator = "sma_crossover"
threshold = 0.0
comparator = "crosses_above"

[entry_rules.conditions.parameters]
fast_period = 20
slow_period = 50

[[entry_rules.filters]]
type = "session"

[entry_rules.filters.params]
include = ["london"]

[exit_rules.stop_loss]
type = "fixed_pips"
value = 50.0

[position_sizing]
method = "fixed_lots"
risk_percent = 1.0
max_lots = 0.1

[optimization_plan]
schema_version = 2
objective_function = "sharpe"

[optimization_plan.parameters.fast_period]
type = "integer"
min = 5.0
max = 50.0
step = 5.0

[cost_model_reference]
version = "v001"
"""
    path.write_text(spec.strip(), encoding="utf-8")


# ---------------------------------------------------------------------------
# Rollup tests
# ---------------------------------------------------------------------------

class TestRollup:
    def test_m1_to_h1_bar_count(self):
        """100 hours of M1 data should produce ~100 H1 bars."""
        m1 = _make_m1_data(100)
        m1["_datetime"] = pd.to_datetime(m1["timestamp"], unit="s", utc=True)
        h1 = _rollup_timeframe(m1, "H1")
        # Should be close to 100 (some periods may be partial)
        assert 95 <= len(h1) <= 105

    def test_ohlcv_aggregation(self):
        """Verify OHLCV aggregation rules: O=first, H=max, L=min, C=last."""
        m1 = _make_m1_data(2)  # 2 hours = 120 M1 bars
        m1["_datetime"] = pd.to_datetime(m1["timestamp"], unit="s", utc=True)
        h1 = _rollup_timeframe(m1, "H1")

        # For the first hour: bars 0-59
        first_hour = m1.iloc[:60]
        first_h1 = h1.iloc[0]

        assert abs(first_h1["open"] - first_hour["open"].iloc[0]) < 1e-10
        assert abs(first_h1["high"] - first_hour["high"].max()) < 1e-10
        assert abs(first_h1["low"] - first_hour["low"].min()) < 1e-10
        assert abs(first_h1["close"] - first_hour["close"].iloc[-1]) < 1e-10

    def test_m1_passthrough(self):
        """M1 timeframe returns data unchanged."""
        m1 = _make_m1_data(2)
        m1["_datetime"] = pd.to_datetime(m1["timestamp"], unit="s", utc=True)
        result = _rollup_timeframe(m1, "M1")
        assert len(result) == len(m1)


# ---------------------------------------------------------------------------
# Indicator computation tests
# ---------------------------------------------------------------------------

class TestIndicators:
    @pytest.fixture()
    def tf_df(self):
        m1 = _make_m1_data(200)
        m1["_datetime"] = pd.to_datetime(m1["timestamp"], unit="s", utc=True)
        return _rollup_timeframe(m1, "H1")

    def test_sma_crossover_returns_series(self, tf_df):
        params = {"fast_period": 20, "slow_period": 50}
        result = _compute_indicator("sma_crossover", params, tf_df)
        assert result is not None
        assert len(result) == len(tf_df)

    def test_sma_crossover_nan_during_warmup(self, tf_df):
        """First 50 bars should be NaN (slow_period warmup)."""
        params = {"fast_period": 20, "slow_period": 50}
        result = _compute_indicator("sma_crossover", params, tf_df)
        assert result.iloc[:49].isna().all()

    def test_sma_crossover_sign_change(self, tf_df):
        """With downtrend then uptrend, crossover should change sign."""
        params = {"fast_period": 20, "slow_period": 50}
        result = _compute_indicator("sma_crossover", params, tf_df)
        valid = result.dropna()
        # Should have both positive and negative values
        assert (valid > 0).any() and (valid < 0).any()

    def test_sma_simple(self, tf_df):
        result = _compute_indicator("sma", {"period": 10}, tf_df)
        assert result is not None
        # First 9 should be NaN
        assert result.iloc[:9].isna().all()
        assert result.iloc[9:].notna().all()

    def test_ema(self, tf_df):
        result = _compute_indicator("ema", {"period": 10}, tf_df)
        assert result is not None

    def test_atr(self, tf_df):
        result = _compute_indicator("atr", {"period": 14}, tf_df)
        assert result is not None
        # ATR should be positive
        valid = result.dropna()
        assert (valid > 0).all()

    def test_rsi_bounded(self, tf_df):
        result = _compute_indicator("rsi", {"period": 14}, tf_df)
        assert result is not None
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_unsupported_returns_none(self, tf_df):
        result = _compute_indicator("unknown_indicator", {}, tf_df)
        assert result is None


# ---------------------------------------------------------------------------
# Forward-fill / no-lookahead tests
# ---------------------------------------------------------------------------

class TestForwardFill:
    def test_no_lookahead_bias(self):
        """M1 bars within an incomplete H1 period must NOT see that period's
        indicator values — they should see the PREVIOUS completed period's."""
        m1 = _make_m1_data(10)  # 10 hours
        m1["_datetime"] = pd.to_datetime(m1["timestamp"], unit="s", utc=True)
        h1 = _rollup_timeframe(m1, "H1")

        # Create a simple indicator: just the close price of each H1 bar
        indicator = h1["close"].copy()
        indicator.name = "test_indicator"
        indicator_columns = {"test_close": indicator}

        result = _forward_fill_to_m1(m1, h1, indicator_columns, "H1")

        # The first hour's M1 bars (0:00-0:59) should have NaN because
        # there's no COMPLETED prior H1 bar
        first_hour_signals = result.iloc[:60]["test_close"]
        assert first_hour_signals.isna().all(), (
            "First hour should be NaN — no completed prior bar"
        )

        # The second hour's M1 bars (1:00-1:59) should see the FIRST hour's
        # indicator value, not the second hour's
        h1_first_close = h1.iloc[0]["close"]
        second_hour_signals = result.iloc[60:120]["test_close"]
        assert (second_hour_signals == h1_first_close).all(), (
            f"Second hour should see first hour's close ({h1_first_close}), "
            f"got {second_hour_signals.unique()}"
        )

    def test_indicator_columns_present_in_output(self):
        """Enriched DataFrame should have all indicator columns."""
        m1 = _make_m1_data(5)
        m1["_datetime"] = pd.to_datetime(m1["timestamp"], unit="s", utc=True)
        h1 = _rollup_timeframe(m1, "H1")

        indicator_columns = {
            "sma_crossover": h1["close"] * 0,  # Dummy
        }

        result = _forward_fill_to_m1(m1, h1, indicator_columns, "H1")
        assert "sma_crossover" in result.columns


# ---------------------------------------------------------------------------
# End-to-end precompute test
# ---------------------------------------------------------------------------

class TestPrecomputeE2E:
    def test_full_roundtrip(self, tmp_path):
        """Write M1 data + spec, run precompute, verify enriched output."""
        m1 = _make_m1_data(200)
        data_path = tmp_path / "market-data.arrow"
        _write_test_arrow(m1, data_path)

        spec_path = tmp_path / "strategy.toml"
        _write_test_spec(spec_path)

        enriched_path = tmp_path / "enriched.arrow"
        result = precompute_signals(spec_path, data_path, enriched_path)

        assert result == enriched_path
        assert enriched_path.exists()

        # Read back and verify
        reader = ipc.open_file(str(enriched_path))
        table = reader.read_all()
        df = table.to_pandas()

        # Should have all original columns
        for col in ["timestamp", "open", "high", "low", "close", "bid", "ask",
                     "session", "quarantined"]:
            assert col in df.columns, f"Missing original column: {col}"

        # Should have the sma_crossover signal column
        assert "sma_crossover" in df.columns, (
            f"Missing sma_crossover column. Columns: {list(df.columns)}"
        )

        # Signal column should have NaN warmup then valid values
        valid = df["sma_crossover"].dropna()
        assert len(valid) > 0, "No valid sma_crossover values"

        # No lookahead: first 50 H1 bars' worth of M1 data should be NaN
        # (50 bars * 60 min/bar = 3000 M1 bars minimum warmup)
        # But with shift, it's actually 51 * 60 = 3060
        first_chunk = df["sma_crossover"].iloc[:3000]
        assert first_chunk.isna().all(), "Warmup period should be all NaN"

    def test_original_rows_preserved(self, tmp_path):
        """Row count should be identical to input M1 data."""
        m1 = _make_m1_data(100)
        data_path = tmp_path / "market-data.arrow"
        _write_test_arrow(m1, data_path)

        spec_path = tmp_path / "strategy.toml"
        _write_test_spec(spec_path)

        enriched_path = tmp_path / "enriched.arrow"
        precompute_signals(spec_path, data_path, enriched_path)

        reader = ipc.open_file(str(enriched_path))
        table = reader.read_all()
        assert table.num_rows == len(m1)


# ---------------------------------------------------------------------------
# Year-range filtering tests
# ---------------------------------------------------------------------------

def _make_multi_year_m1_data() -> pd.DataFrame:
    """Create synthetic M1 data spanning 2020-2025 (1 hour per year)."""
    frames = []
    for year in range(2020, 2026):
        # 60 M1 bars per year (1 hour), starting Jan 5 (Monday)
        start_ts = int(pd.Timestamp(f"{year}-01-05 10:00:00", tz="UTC").timestamp())
        n_bars = 60
        timestamps = np.arange(start_ts, start_ts + n_bars * 60, 60)
        closes = np.full(n_bars, 1.1 + (year - 2020) * 0.01)
        frames.append(pd.DataFrame({
            "timestamp": timestamps.astype(np.int64),
            "open": closes,
            "high": closes + 0.001,
            "low": closes - 0.001,
            "close": closes,
            "bid": closes - 0.00005,
            "ask": closes + 0.00005,
            "session": "london",
            "quarantined": np.zeros(n_bars, dtype=bool),
        }))
    return pd.concat(frames, ignore_index=True)


class TestYearRangeFiltering:
    """Tests for year_range parameter in signal precompute."""

    def test_year_range_reduces_bar_count(self, tmp_path):
        """Filtering to a subset of years should reduce bar count."""
        m1 = _make_multi_year_m1_data()
        data_path = tmp_path / "market-data.arrow"
        _write_test_arrow(m1, data_path)

        spec = {
            "metadata": {"name": "test", "version": "v001", "pair": "EURUSD", "timeframe": "M1"},
            "entry_rules": {"conditions": []},
            "exit_rules": {},
        }

        # Without year range — all bars
        out_all = tmp_path / "all.arrow"
        _precompute_core(spec, data_path, out_all)
        reader_all = ipc.open_file(str(out_all))
        total_bars = reader_all.read_all().num_rows

        # With year range [2022, 2024] — should have ~3 years of data
        out_filtered = tmp_path / "filtered.arrow"
        _precompute_core(spec, data_path, out_filtered, year_range=(2022, 2024))
        reader_filtered = ipc.open_file(str(out_filtered))
        filtered_bars = reader_filtered.read_all().num_rows

        assert filtered_bars < total_bars
        # 3 out of 6 years => half the data
        assert filtered_bars == 180  # 3 years * 60 bars

    def test_year_range_none_returns_all(self, tmp_path):
        """year_range=None should return all bars (backwards compatible)."""
        m1 = _make_multi_year_m1_data()
        data_path = tmp_path / "market-data.arrow"
        _write_test_arrow(m1, data_path)

        spec = {
            "metadata": {"name": "test", "version": "v001", "pair": "EURUSD", "timeframe": "M1"},
            "entry_rules": {"conditions": []},
            "exit_rules": {},
        }

        out = tmp_path / "out.arrow"
        _precompute_core(spec, data_path, out, year_range=None)
        reader = ipc.open_file(str(out))
        assert reader.read_all().num_rows == len(m1)

    def test_year_range_inclusive_boundaries(self, tmp_path):
        """Year range should be inclusive on both ends."""
        m1 = _make_multi_year_m1_data()
        data_path = tmp_path / "market-data.arrow"
        _write_test_arrow(m1, data_path)

        spec = {
            "metadata": {"name": "test", "version": "v001", "pair": "EURUSD", "timeframe": "M1"},
            "entry_rules": {"conditions": []},
            "exit_rules": {},
        }

        # Single year [2023, 2023]
        out = tmp_path / "single-year.arrow"
        _precompute_core(spec, data_path, out, year_range=(2023, 2023))
        reader = ipc.open_file(str(out))
        assert reader.read_all().num_rows == 60  # exactly 1 year of data


# ---------------------------------------------------------------------------
# Output resolution tests (H1 mode for pre-screening)
# ---------------------------------------------------------------------------

class TestOutputResolution:
    """Tests for output_resolution parameter in signal precompute."""

    def test_h1_output_has_fewer_bars_than_m1(self, tmp_path):
        """H1 output should have ~1/60th the bars of M1 output."""
        m1 = _make_m1_data(100)  # 100 hours
        data_path = tmp_path / "market-data.arrow"
        _write_test_arrow(m1, data_path)

        spec = {
            "metadata": {
                "name": "test", "version": "v001",
                "pair": "EURUSD", "timeframe": "H1",
            },
            "entry_rules": {
                "conditions": [{
                    "indicator": "sma_crossover",
                    "parameters": {"fast_period": 20, "slow_period": 50},
                }],
            },
            "exit_rules": {},
        }

        # M1 output (default)
        out_m1 = tmp_path / "m1.arrow"
        _precompute_core(spec, data_path, out_m1, output_resolution="M1")
        reader_m1 = ipc.open_file(str(out_m1))
        m1_rows = reader_m1.read_all().num_rows

        # H1 output
        out_h1 = tmp_path / "h1.arrow"
        _precompute_core(spec, data_path, out_h1, output_resolution="H1")
        reader_h1 = ipc.open_file(str(out_h1))
        h1_rows = reader_h1.read_all().num_rows

        assert h1_rows < m1_rows
        # H1 should be roughly 1/60th of M1
        assert h1_rows == pytest.approx(m1_rows / 60, abs=10)

    def test_h1_output_has_indicator_columns(self, tmp_path):
        """H1 output should contain indicator signal columns."""
        m1 = _make_m1_data(100)
        data_path = tmp_path / "market-data.arrow"
        _write_test_arrow(m1, data_path)

        spec = {
            "metadata": {
                "name": "test", "version": "v001",
                "pair": "EURUSD", "timeframe": "H1",
            },
            "entry_rules": {
                "conditions": [{
                    "indicator": "sma_crossover",
                    "parameters": {"fast_period": 20, "slow_period": 50},
                }],
            },
            "exit_rules": {},
        }

        out = tmp_path / "h1.arrow"
        _precompute_core(spec, data_path, out, output_resolution="H1")
        reader = ipc.open_file(str(out))
        table = reader.read_all()

        col_names = [f.name for f in table.schema]
        assert "sma_crossover" in col_names

    def test_default_resolution_is_m1(self, tmp_path):
        """Default output_resolution should be M1 (backwards compatible)."""
        m1 = _make_m1_data(10)
        data_path = tmp_path / "market-data.arrow"
        _write_test_arrow(m1, data_path)

        spec = {
            "metadata": {
                "name": "test", "version": "v001",
                "pair": "EURUSD", "timeframe": "H1",
            },
            "entry_rules": {"conditions": []},
            "exit_rules": {},
        }

        out = tmp_path / "default.arrow"
        _precompute_core(spec, data_path, out)
        reader = ipc.open_file(str(out))
        # Should have M1 bar count (not H1)
        assert reader.read_all().num_rows == len(m1)
