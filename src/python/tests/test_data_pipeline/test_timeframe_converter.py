"""Tests for timeframe_converter module (Story 1.7).

Covers:
- M1 to M5/H1/D1/W aggregation with correct OHLC
- Bid/ask aggregation (last per period)
- Quarantined bar exclusion
- Fully quarantined period omission
- Session column handling (M5 preserve, H1 majority, D1/W mixed)
- Determinism (same input -> identical output)
- Tick-to-M1 aggregation
- Crash-safe write pattern
- Live integration tests
"""
import hashlib
import logging
import os
import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc
import pyarrow.parquet as pq
import pytest

from data_pipeline.timeframe_converter import (
    VALID_TIMEFRAMES,
    _US_PER_MINUTE,
    _US_PER_HOUR,
    _US_PER_DAY,
    _US_PER_SECOND,
    _FOREX_WEEK_EPOCH_OFFSET_US,
    _US_PER_WEEK,
    _compute_period_start,
    aggregate_ticks_to_m1,
    compute_session_for_timestamp,
    convert_timeframe,
    is_tick_data,
    run_timeframe_conversion,
    validate_output_schema,
    write_arrow_ipc,
    write_parquet,
)

# --- Helpers ---

ARROW_SCHEMAS_TOML = """\
[market_data]
description = "M1 bar data with session and quarantine columns"
columns = [
  { name = "timestamp", type = "int64", nullable = false },
  { name = "open", type = "float64", nullable = false },
  { name = "high", type = "float64", nullable = false },
  { name = "low", type = "float64", nullable = false },
  { name = "close", type = "float64", nullable = false },
  { name = "bid", type = "float64", nullable = false },
  { name = "ask", type = "float64", nullable = false },
  { name = "session", type = "utf8", nullable = false },
  { name = "quarantined", type = "bool", nullable = false },
]

[tick_data]
description = "Individual bid/ask ticks"
columns = [
  { name = "timestamp", type = "int64", nullable = false },
  { name = "bid", type = "float64", nullable = false },
  { name = "ask", type = "float64", nullable = false },
  { name = "bid_volume", type = "float64", nullable = true },
  { name = "ask_volume", type = "float64", nullable = true },
  { name = "session", type = "utf8", nullable = false },
  { name = "quarantined", type = "bool", nullable = false },
]
"""

# Base timestamp: 2024-01-08 00:00:00 UTC (Monday) in epoch microseconds
# 2024-01-08 = 19730 days after epoch = 19730 * 86400 * 1_000_000
BASE_TS = 19730 * _US_PER_DAY


def _make_m1_table(
    n_bars: int,
    start_ts: int = BASE_TS,
    session: str = "asian",
    quarantined: list[bool] | None = None,
    open_start: float = 1.1000,
    price_step: float = 0.0001,
) -> pa.Table:
    """Create a synthetic M1 table with n bars starting at start_ts."""
    timestamps = [start_ts + i * _US_PER_MINUTE for i in range(n_bars)]
    opens = [open_start + i * price_step for i in range(n_bars)]
    highs = [o + 0.0005 for o in opens]
    lows = [o - 0.0003 for o in opens]
    closes = [o + 0.0002 for o in opens]
    bids = [c - 0.00005 for c in closes]
    asks = [c + 0.00005 for c in closes]
    sessions = [session] * n_bars
    if quarantined is None:
        quarantined = [False] * n_bars

    return pa.table({
        "timestamp": pa.array(timestamps, type=pa.int64()),
        "open": pa.array(opens, type=pa.float64()),
        "high": pa.array(highs, type=pa.float64()),
        "low": pa.array(lows, type=pa.float64()),
        "close": pa.array(closes, type=pa.float64()),
        "bid": pa.array(bids, type=pa.float64()),
        "ask": pa.array(asks, type=pa.float64()),
        "session": pa.array(sessions, type=pa.utf8()),
        "quarantined": pa.array(quarantined, type=pa.bool_()),
    })


def _make_contracts(tmp_path: Path) -> Path:
    """Create test contracts directory."""
    contracts = tmp_path / "contracts"
    contracts.mkdir(exist_ok=True)
    (contracts / "arrow_schemas.toml").write_text(ARROW_SCHEMAS_TOML)
    return contracts


def _make_config(tmp_path: Path) -> dict:
    """Create a test config dict."""
    return {
        "data": {"storage_path": str(tmp_path)},
        "data_pipeline": {
            "storage_path": str(tmp_path),
            "storage": {
                "arrow_ipc_path": str(tmp_path / "arrow"),
                "parquet_path": str(tmp_path / "parquet"),
            },
            "parquet": {"compression": "snappy"},
            "timeframe_conversion": {
                "target_timeframes": ["M5", "H1", "D1", "W"],
                "source_timeframe": "M1",
            },
        },
        "sessions": {
            "timezone": "UTC",
            "asian": {"start": "00:00", "end": "08:00", "label": "Asian"},
            "london": {"start": "08:00", "end": "16:00", "label": "London"},
            "new_york": {"start": "13:00", "end": "21:00", "label": "New York"},
            "london_ny_overlap": {"start": "13:00", "end": "16:00", "label": "Overlap"},
            "off_hours": {"start": "21:00", "end": "00:00", "label": "Off Hours"},
        },
    }


@pytest.fixture
def logger():
    return logging.getLogger("test_timeframe_converter")


# =============================================================================
# Task 7: Unit Tests
# =============================================================================


class TestM1ToM5:
    """Test M1 to M5 aggregation (AC #1)."""

    def test_basic_10_bars_to_2_m5(self):
        """10 M1 bars (00:00-00:09) -> 2 M5 bars with correct OHLC."""
        table = _make_m1_table(10, start_ts=BASE_TS)
        result = convert_timeframe(table, "M1", "M5")

        assert result.num_rows == 2

        # First M5 bar: bars 0-4
        assert result.column("timestamp")[0].as_py() == BASE_TS
        # open = first bar's open
        assert result.column("open")[0].as_py() == table.column("open")[0].as_py()
        # high = max of bars 0-4 highs
        expected_high = max(table.column("high")[i].as_py() for i in range(5))
        assert result.column("high")[0].as_py() == expected_high
        # low = min of bars 0-4 lows
        expected_low = min(table.column("low")[i].as_py() for i in range(5))
        assert result.column("low")[0].as_py() == expected_low
        # close = last bar's close (bar 4)
        assert result.column("close")[0].as_py() == table.column("close")[4].as_py()

        # Second M5 bar: bars 5-9
        assert result.column("timestamp")[1].as_py() == BASE_TS + 5 * _US_PER_MINUTE

    def test_incomplete_m5_period(self):
        """7 M1 bars -> 2 M5 bars (second has only 2 bars)."""
        table = _make_m1_table(7, start_ts=BASE_TS)
        result = convert_timeframe(table, "M1", "M5")

        assert result.num_rows == 2
        # Second M5 bar should use bars 5-6
        assert result.column("open")[1].as_py() == table.column("open")[5].as_py()
        assert result.column("close")[1].as_py() == table.column("close")[6].as_py()


class TestM1ToH1:
    """Test M1 to H1 aggregation (AC #1)."""

    def test_60_bars_to_1_h1(self):
        """60 M1 bars -> 1 H1 bar with correct OHLC."""
        table = _make_m1_table(60, start_ts=BASE_TS)
        result = convert_timeframe(table, "M1", "H1")

        assert result.num_rows == 1
        assert result.column("timestamp")[0].as_py() == BASE_TS
        assert result.column("open")[0].as_py() == table.column("open")[0].as_py()
        assert result.column("close")[0].as_py() == table.column("close")[59].as_py()

        expected_high = max(table.column("high")[i].as_py() for i in range(60))
        assert result.column("high")[0].as_py() == expected_high

        expected_low = min(table.column("low")[i].as_py() for i in range(60))
        assert result.column("low")[0].as_py() == expected_low

    def test_multi_hour_bars(self):
        """120 M1 bars -> 2 H1 bars."""
        table = _make_m1_table(120, start_ts=BASE_TS)
        result = convert_timeframe(table, "M1", "H1")

        assert result.num_rows == 2
        assert result.column("timestamp")[0].as_py() == BASE_TS
        assert result.column("timestamp")[1].as_py() == BASE_TS + _US_PER_HOUR


class TestM1ToD1:
    """Test M1 to D1 aggregation (AC #1)."""

    def test_daily_aggregation(self):
        """M1 bars spanning a full day -> 1 D1 bar."""
        # 1440 minutes in a day
        table = _make_m1_table(1440, start_ts=BASE_TS)
        result = convert_timeframe(table, "M1", "D1")

        assert result.num_rows == 1
        assert result.column("timestamp")[0].as_py() == BASE_TS
        assert result.column("open")[0].as_py() == table.column("open")[0].as_py()
        assert result.column("close")[0].as_py() == table.column("close")[1439].as_py()

    def test_multi_day_bars(self):
        """Bars spanning 2 days -> 2 D1 bars."""
        table = _make_m1_table(2880, start_ts=BASE_TS)  # 2 days
        result = convert_timeframe(table, "M1", "D1")

        assert result.num_rows == 2
        assert result.column("session")[0].as_py() == "mixed"
        assert result.column("session")[1].as_py() == "mixed"


class TestM1ToW:
    """Test M1 to Weekly aggregation (AC #1)."""

    def test_weekly_aggregation(self):
        """Bars spanning a full week -> 1 W bar."""
        # Start at a Sunday 22:00 UTC boundary for forex week alignment
        # 2024-01-07 (Sunday) 22:00 UTC
        sunday_22 = (19729 * _US_PER_DAY) + (22 * _US_PER_HOUR)
        # Create enough bars for a week (7 days * 24 hours * 60 min)
        table = _make_m1_table(10080, start_ts=sunday_22)
        result = convert_timeframe(table, "M1", "W")

        assert result.num_rows == 1
        assert result.column("session")[0].as_py() == "mixed"

    def test_multi_week_bars(self):
        """Bars spanning 2+ weeks -> multiple W bars."""
        sunday_22 = (19729 * _US_PER_DAY) + (22 * _US_PER_HOUR)
        table = _make_m1_table(20160, start_ts=sunday_22)  # 2 weeks
        result = convert_timeframe(table, "M1", "W")

        assert result.num_rows == 2


class TestBidAskAggregation:
    """Test bid/ask aggregation rules (AC #2)."""

    def test_last_bid_last_ask(self):
        """Bid and ask should be from the last bar in each period."""
        table = _make_m1_table(10, start_ts=BASE_TS)
        result = convert_timeframe(table, "M1", "M5")

        # First M5 bar: bid/ask should be from bar 4 (last in period)
        assert result.column("bid")[0].as_py() == table.column("bid")[4].as_py()
        assert result.column("ask")[0].as_py() == table.column("ask")[4].as_py()

        # Second M5 bar: bid/ask should be from bar 9
        assert result.column("bid")[1].as_py() == table.column("bid")[9].as_py()
        assert result.column("ask")[1].as_py() == table.column("ask")[9].as_py()


class TestQuarantinedBarExclusion:
    """Test quarantined bar handling (AC #5)."""

    def test_quarantined_excluded_from_ohlc(self):
        """Quarantined bars must not contribute to OHLC values."""
        quarantined = [False, True, False, False, False,
                       False, False, False, False, False]
        table = _make_m1_table(10, quarantined=quarantined)
        result = convert_timeframe(table, "M1", "M5")

        # First M5 period: bars 0,2,3,4 (bar 1 is quarantined)
        # open should come from bar 0
        assert result.column("open")[0].as_py() == table.column("open")[0].as_py()
        # The quarantined bar's high should NOT be considered
        non_q_highs = [table.column("high")[i].as_py() for i in [0, 2, 3, 4]]
        assert result.column("high")[0].as_py() == max(non_q_highs)

    def test_fully_quarantined_period_omitted(self):
        """Period where all bars are quarantined should be omitted entirely."""
        quarantined = [True, True, True, True, True,
                       False, False, False, False, False]
        table = _make_m1_table(10, quarantined=quarantined)
        result = convert_timeframe(table, "M1", "M5")

        # Only the second M5 period (bars 5-9) should appear
        assert result.num_rows == 1
        assert result.column("timestamp")[0].as_py() == BASE_TS + 5 * _US_PER_MINUTE

    def test_all_quarantined_returns_empty(self):
        """If all bars are quarantined, result should be empty."""
        quarantined = [True] * 10
        table = _make_m1_table(10, quarantined=quarantined)
        result = convert_timeframe(table, "M1", "M5")

        assert result.num_rows == 0

    def test_quarantined_false_in_output(self):
        """Output bars should always have quarantined=False."""
        table = _make_m1_table(10)
        result = convert_timeframe(table, "M1", "M5")

        for i in range(result.num_rows):
            assert result.column("quarantined")[i].as_py() is False


class TestSessionColumnHandling:
    """Test session column preservation/recomputation (AC #4)."""

    def test_m5_preserves_first_bar_session(self):
        """M5 session = session of first bar in group."""
        sessions = ["asian"] * 5 + ["london"] * 5
        table = _make_m1_table(10)
        # Replace session column
        table = table.drop("session")
        table = table.append_column("session", pa.array(sessions, type=pa.utf8()))
        # Reorder columns to match schema
        table = pa.table({
            "timestamp": table.column("timestamp"),
            "open": table.column("open"),
            "high": table.column("high"),
            "low": table.column("low"),
            "close": table.column("close"),
            "bid": table.column("bid"),
            "ask": table.column("ask"),
            "session": table.column("session"),
            "quarantined": table.column("quarantined"),
        })

        result = convert_timeframe(table, "M1", "M5")

        assert result.column("session")[0].as_py() == "asian"
        assert result.column("session")[1].as_py() == "london"

    def test_h1_majority_session(self):
        """H1 session = majority session in the hour."""
        # 60 bars: 40 london + 20 london_ny_overlap
        sessions = ["london"] * 40 + ["london_ny_overlap"] * 20
        table = _make_m1_table(60)
        table = table.drop("session")
        table = table.append_column("session", pa.array(sessions, type=pa.utf8()))
        table = pa.table({
            "timestamp": table.column("timestamp"),
            "open": table.column("open"),
            "high": table.column("high"),
            "low": table.column("low"),
            "close": table.column("close"),
            "bid": table.column("bid"),
            "ask": table.column("ask"),
            "session": table.column("session"),
            "quarantined": table.column("quarantined"),
        })

        result = convert_timeframe(table, "M1", "H1")

        assert result.column("session")[0].as_py() == "london"

    def test_d1_session_is_mixed(self):
        """D1 session should always be 'mixed'."""
        table = _make_m1_table(1440, start_ts=BASE_TS)
        result = convert_timeframe(table, "M1", "D1")

        assert result.column("session")[0].as_py() == "mixed"

    def test_w_session_is_mixed(self):
        """W session should always be 'mixed'."""
        sunday_22 = (19729 * _US_PER_DAY) + (22 * _US_PER_HOUR)
        table = _make_m1_table(10080, start_ts=sunday_22)
        result = convert_timeframe(table, "M1", "W")

        assert result.column("session")[0].as_py() == "mixed"


class TestComputeSessionForTimestamp:
    """Test compute_session_for_timestamp utility."""

    def setup_method(self):
        self.schedule = {
            "timezone": "UTC",
            "asian": {"start": "00:00", "end": "08:00", "label": "Asian"},
            "london": {"start": "08:00", "end": "16:00", "label": "London"},
            "new_york": {"start": "13:00", "end": "21:00", "label": "New York"},
            "london_ny_overlap": {"start": "13:00", "end": "16:00", "label": "Overlap"},
            "off_hours": {"start": "21:00", "end": "00:00", "label": "Off Hours"},
        }

    def test_asian_session(self):
        # 2024-01-08 03:00 UTC
        ts = BASE_TS + 3 * _US_PER_HOUR
        assert compute_session_for_timestamp(ts, self.schedule) == "asian"

    def test_london_session(self):
        # 2024-01-08 10:00 UTC
        ts = BASE_TS + 10 * _US_PER_HOUR
        assert compute_session_for_timestamp(ts, self.schedule) == "london"

    def test_overlap_session(self):
        # 2024-01-08 14:00 UTC
        ts = BASE_TS + 14 * _US_PER_HOUR
        assert compute_session_for_timestamp(ts, self.schedule) == "london_ny_overlap"

    def test_off_hours_session(self):
        # 2024-01-08 22:00 UTC
        ts = BASE_TS + 22 * _US_PER_HOUR
        assert compute_session_for_timestamp(ts, self.schedule) == "off_hours"


class TestDeterminism:
    """Test conversion determinism (AC #7)."""

    def test_same_input_identical_output(self):
        """Run conversion twice on same input, verify identical output."""
        table = _make_m1_table(120, start_ts=BASE_TS)

        result1 = convert_timeframe(table, "M1", "H1")
        result2 = convert_timeframe(table, "M1", "H1")

        assert result1.num_rows == result2.num_rows
        for col_name in result1.schema.names:
            col1 = result1.column(col_name)
            col2 = result2.column(col_name)
            for i in range(result1.num_rows):
                assert col1[i].as_py() == col2[i].as_py(), (
                    f"Mismatch at row {i}, column {col_name}"
                )

    def test_determinism_with_arrow_ipc_hash(self, tmp_path, logger):
        """Write Arrow IPC twice, verify file hashes match."""
        table = _make_m1_table(60, start_ts=BASE_TS)
        result = convert_timeframe(table, "M1", "H1")

        path1 = tmp_path / "out1.arrow"
        path2 = tmp_path / "out2.arrow"
        write_arrow_ipc(result, path1, logger)
        write_arrow_ipc(result, path2, logger)

        hash1 = hashlib.sha256(path1.read_bytes()).hexdigest()
        hash2 = hashlib.sha256(path2.read_bytes()).hexdigest()
        assert hash1 == hash2


class TestTickToM1:
    """Test tick-to-M1 aggregation (AC #3)."""

    def test_basic_tick_aggregation(self):
        """Known tick data -> correct M1 bars."""
        # 10 ticks in minute 0, 10 ticks in minute 1
        timestamps = []
        bids = []
        asks = []
        for minute in range(2):
            for tick in range(10):
                ts = BASE_TS + minute * _US_PER_MINUTE + tick * _US_PER_SECOND
                timestamps.append(ts)
                bid = 1.1000 + minute * 0.001 + tick * 0.0001
                ask = bid + 0.0002
                bids.append(bid)
                asks.append(ask)

        tick_table = pa.table({
            "timestamp": pa.array(timestamps, type=pa.int64()),
            "bid": pa.array(bids, type=pa.float64()),
            "ask": pa.array(asks, type=pa.float64()),
            "session": pa.array(["asian"] * 20, type=pa.utf8()),
            "quarantined": pa.array([False] * 20, type=pa.bool_()),
        })

        result = aggregate_ticks_to_m1(tick_table)

        assert result.num_rows == 2

        # First M1 bar: ticks 0-9
        # mid = (bid + ask) / 2
        first_mid = (bids[0] + asks[0]) / 2
        last_mid_m0 = (bids[9] + asks[9]) / 2
        assert abs(result.column("open")[0].as_py() - first_mid) < 1e-10
        assert abs(result.column("close")[0].as_py() - last_mid_m0) < 1e-10
        # Last bid/ask from minute 0
        assert abs(result.column("bid")[0].as_py() - bids[9]) < 1e-10
        assert abs(result.column("ask")[0].as_py() - asks[9]) < 1e-10

    def test_empty_tick_table(self):
        """Empty tick table -> empty M1 table."""
        tick_table = pa.table({
            "timestamp": pa.array([], type=pa.int64()),
            "bid": pa.array([], type=pa.float64()),
            "ask": pa.array([], type=pa.float64()),
            "session": pa.array([], type=pa.utf8()),
            "quarantined": pa.array([], type=pa.bool_()),
        })

        result = aggregate_ticks_to_m1(tick_table)
        assert result.num_rows == 0

    def test_mid_price_calculation(self):
        """Verify mid = (bid + ask) / 2."""
        tick_table = pa.table({
            "timestamp": pa.array([BASE_TS, BASE_TS + _US_PER_SECOND], type=pa.int64()),
            "bid": pa.array([1.1000, 1.1010], type=pa.float64()),
            "ask": pa.array([1.1002, 1.1012], type=pa.float64()),
            "session": pa.array(["asian", "asian"], type=pa.utf8()),
            "quarantined": pa.array([False, False], type=pa.bool_()),
        })

        result = aggregate_ticks_to_m1(tick_table)

        assert result.num_rows == 1
        # open mid = (1.1000 + 1.1002) / 2 = 1.1001
        assert abs(result.column("open")[0].as_py() - 1.1001) < 1e-10
        # close mid = (1.1010 + 1.1012) / 2 = 1.1011
        assert abs(result.column("close")[0].as_py() - 1.1011) < 1e-10
        # high mid = max(1.1001, 1.1011) = 1.1011
        assert abs(result.column("high")[0].as_py() - 1.1011) < 1e-10
        # low mid = min(1.1001, 1.1011) = 1.1001
        assert abs(result.column("low")[0].as_py() - 1.1001) < 1e-10


class TestIsTickData:
    """Test tick data detection."""

    def test_detects_tick_data(self):
        """Table with bid/ask but no OHLC -> tick data."""
        table = pa.table({
            "timestamp": pa.array([1], type=pa.int64()),
            "bid": pa.array([1.1], type=pa.float64()),
            "ask": pa.array([1.2], type=pa.float64()),
        })
        assert is_tick_data(table) is True

    def test_detects_bar_data(self):
        """Table with OHLC + bid/ask -> bar data."""
        table = _make_m1_table(1)
        assert is_tick_data(table) is False


class TestCrashSafeWrite:
    """Test crash-safe write pattern (AC #6)."""

    def test_arrow_ipc_write_no_partial_after(self, tmp_path, logger):
        """After write, .partial file should not exist."""
        table = _make_m1_table(5)
        result = convert_timeframe(table, "M1", "M5")
        path = tmp_path / "test.arrow"

        write_arrow_ipc(result, path, logger)

        assert path.exists()
        assert not path.with_name("test.arrow.partial").exists()

    def test_parquet_write_no_partial_after(self, tmp_path, logger):
        """After Parquet write, .partial should not exist."""
        table = _make_m1_table(5)
        result = convert_timeframe(table, "M1", "M5")
        path = tmp_path / "test.parquet"

        write_parquet(result, path, logger)

        assert path.exists()
        assert not path.with_name("test.parquet.partial").exists()

    def test_arrow_ipc_readable_after_write(self, tmp_path, logger):
        """Written Arrow IPC file should be mmap-readable."""
        table = _make_m1_table(10)
        result = convert_timeframe(table, "M1", "M5")
        path = tmp_path / "test.arrow"

        write_arrow_ipc(result, path, logger)

        mmap = pa.memory_map(str(path), "r")
        reader = pa.ipc.open_file(mmap)
        read_table = reader.read_all()
        mmap.close()

        assert read_table.num_rows == result.num_rows

    def test_parquet_readable_after_write(self, tmp_path, logger):
        """Written Parquet file should be readable."""
        table = _make_m1_table(10)
        result = convert_timeframe(table, "M1", "M5")
        path = tmp_path / "test.parquet"

        write_parquet(result, path, logger)

        read_table = pq.read_table(str(path))
        assert read_table.num_rows == result.num_rows


class TestValidation:
    """Test schema validation and edge cases."""

    def test_invalid_source_timeframe(self):
        table = _make_m1_table(10)
        with pytest.raises(ValueError, match="Invalid source timeframe"):
            convert_timeframe(table, "M2", "M5")

    def test_invalid_target_timeframe(self):
        table = _make_m1_table(10)
        with pytest.raises(ValueError, match="Invalid target timeframe"):
            convert_timeframe(table, "M1", "M2")

    def test_target_not_higher_than_source(self):
        table = _make_m1_table(10)
        with pytest.raises(ValueError, match="must be higher"):
            convert_timeframe(table, "H1", "M5")

    def test_validate_output_schema(self, tmp_path):
        """Output schema must match contracts."""
        contracts = _make_contracts(tmp_path)
        table = _make_m1_table(10)
        result = convert_timeframe(table, "M1", "M5")

        # Should not raise
        validate_output_schema(result, contracts)

    def test_schema_validation_fails_on_mismatch(self, tmp_path):
        """Schema validation should fail on column mismatch."""
        contracts = _make_contracts(tmp_path)
        # Table missing columns
        bad_table = pa.table({
            "timestamp": pa.array([1], type=pa.int64()),
            "open": pa.array([1.0], type=pa.float64()),
        })

        from data_pipeline.schema_loader import SchemaValidationError
        with pytest.raises(SchemaValidationError):
            validate_output_schema(bad_table, contracts)


class TestPeriodStartComputation:
    """Test period boundary computation."""

    def test_m5_period_start(self):
        """M5 period boundaries align to 5-minute intervals."""
        timestamps = pa.array([
            BASE_TS,                          # 00:00 -> 00:00
            BASE_TS + 3 * _US_PER_MINUTE,     # 00:03 -> 00:00
            BASE_TS + 5 * _US_PER_MINUTE,     # 00:05 -> 00:05
            BASE_TS + 7 * _US_PER_MINUTE,     # 00:07 -> 00:05
        ], type=pa.int64())

        result = _compute_period_start(timestamps, "M5")
        assert result[0].as_py() == BASE_TS
        assert result[1].as_py() == BASE_TS
        assert result[2].as_py() == BASE_TS + 5 * _US_PER_MINUTE
        assert result[3].as_py() == BASE_TS + 5 * _US_PER_MINUTE

    def test_h1_period_start(self):
        """H1 period boundaries align to hour."""
        timestamps = pa.array([
            BASE_TS + 30 * _US_PER_MINUTE,    # 00:30 -> 00:00
            BASE_TS + 90 * _US_PER_MINUTE,    # 01:30 -> 01:00
        ], type=pa.int64())

        result = _compute_period_start(timestamps, "H1")
        assert result[0].as_py() == BASE_TS
        assert result[1].as_py() == BASE_TS + _US_PER_HOUR

    def test_d1_period_start(self):
        """D1 period boundaries align to day (UTC)."""
        timestamps = pa.array([
            BASE_TS + 12 * _US_PER_HOUR,      # 12:00 -> day start
        ], type=pa.int64())

        result = _compute_period_start(timestamps, "D1")
        assert result[0].as_py() == BASE_TS


class TestRunTimeframeConversion:
    """Test the orchestration entry point."""

    def test_full_pipeline(self, tmp_path, logger, monkeypatch):
        """End-to-end: write M1 source, run conversion, check outputs."""
        # Setup contracts
        contracts = _make_contracts(tmp_path)

        config = _make_config(tmp_path)
        config["data_pipeline"]["contracts_path"] = str(contracts)
        config["data_pipeline"]["timeframe_conversion"]["target_timeframes"] = ["M5"]

        # Create source M1 Arrow IPC
        source_table = _make_m1_table(20, start_ts=BASE_TS)
        source_dir = tmp_path / "data-pipeline"
        source_dir.mkdir(parents=True)
        source_path = source_dir / "EURUSD_M1.arrow"

        with open(source_path, "wb") as f:
            writer = pa.ipc.new_file(f, source_table.schema)
            writer.write_table(source_table)
            writer.close()

        results = run_timeframe_conversion("EURUSD", source_path, config, logger)

        assert "M5" in results
        assert results["M5"]["arrow"].exists()
        assert results["M5"]["parquet"].exists()

        # Verify written data
        mmap = pa.memory_map(str(results["M5"]["arrow"]), "r")
        reader = pa.ipc.open_file(mmap)
        m5_table = reader.read_all()
        mmap.close()

        assert m5_table.num_rows == 4  # 20 M1 bars -> 4 M5 bars


# =============================================================================
# Live Integration Tests
# =============================================================================


@pytest.mark.live
class TestLiveTimeframeConversion:
    """Live integration tests — exercise real system behavior."""

    def test_live_m1_to_all_timeframes(self, tmp_path, monkeypatch):
        """Full conversion from M1 to all timeframes, verify real files on disk."""
        contracts = _make_contracts(tmp_path)

        config = _make_config(tmp_path)
        config["data_pipeline"]["contracts_path"] = str(contracts)
        logger = logging.getLogger("live_test")

        # Create realistic M1 data: 1 week of M1 bars (10080 bars)
        sunday_22 = (19729 * _US_PER_DAY) + (22 * _US_PER_HOUR)
        source_table = _make_m1_table(10080, start_ts=sunday_22)

        # Write source Arrow IPC
        source_dir = tmp_path / "data-pipeline"
        source_dir.mkdir(parents=True)
        source_path = source_dir / "EURUSD_M1.arrow"
        with open(source_path, "wb") as f:
            writer = pa.ipc.new_file(f, source_table.schema)
            writer.write_table(source_table)
            writer.close()

        results = run_timeframe_conversion("EURUSD", source_path, config, logger)

        # Verify all 4 timeframes produced
        assert len(results) == 4
        for tf in ["M5", "H1", "D1", "W"]:
            assert tf in results, f"Missing timeframe: {tf}"
            arrow_path = results[tf]["arrow"]
            parquet_path = results[tf]["parquet"]

            # Files must exist on disk
            assert arrow_path.exists(), f"Arrow file missing: {arrow_path}"
            assert parquet_path.exists(), f"Parquet file missing: {parquet_path}"

            # Read and verify Arrow IPC
            mmap = pa.memory_map(str(arrow_path), "r")
            reader = pa.ipc.open_file(mmap)
            table = reader.read_all()
            mmap.close()

            assert table.num_rows > 0, f"Empty table for {tf}"
            assert set(table.schema.names) == {
                "timestamp", "open", "high", "low", "close",
                "bid", "ask", "session", "quarantined"
            }

            # Read and verify Parquet
            pq_table = pq.read_table(str(parquet_path))
            assert pq_table.num_rows == table.num_rows

        # Verify expected row counts
        m5_rows = pa.ipc.open_file(
            pa.memory_map(str(results["M5"]["arrow"]), "r")
        ).read_all().num_rows
        assert m5_rows == 10080 // 5  # 2016

        h1_rows = pa.ipc.open_file(
            pa.memory_map(str(results["H1"]["arrow"]), "r")
        ).read_all().num_rows
        assert h1_rows == 10080 // 60  # 168

    def test_live_quarantine_exclusion_e2e(self, tmp_path, monkeypatch):
        """Live test: quarantined bars are excluded from real conversion output."""
        contracts = _make_contracts(tmp_path)

        config = _make_config(tmp_path)
        config["data_pipeline"]["contracts_path"] = str(contracts)
        config["data_pipeline"]["timeframe_conversion"]["target_timeframes"] = ["M5"]
        logger = logging.getLogger("live_test_quarantine")

        # 10 M1 bars: first 5 quarantined, last 5 valid
        quarantined = [True] * 5 + [False] * 5
        source_table = _make_m1_table(10, quarantined=quarantined)

        source_dir = tmp_path / "data-pipeline"
        source_dir.mkdir(parents=True)
        source_path = source_dir / "EURUSD_M1.arrow"
        with open(source_path, "wb") as f:
            writer = pa.ipc.new_file(f, source_table.schema)
            writer.write_table(source_table)
            writer.close()

        results = run_timeframe_conversion("EURUSD", source_path, config, logger)

        # Only 1 M5 bar (from the 5 non-quarantined bars)
        arrow_path = results["M5"]["arrow"]
        mmap = pa.memory_map(str(arrow_path), "r")
        reader = pa.ipc.open_file(mmap)
        table = reader.read_all()
        mmap.close()

        assert table.num_rows == 1
        # All output bars should be non-quarantined
        for i in range(table.num_rows):
            assert table.column("quarantined")[i].as_py() is False

    def test_live_determinism_file_hash(self, tmp_path, monkeypatch):
        """Live test: running conversion twice produces bit-identical files."""
        contracts = _make_contracts(tmp_path)

        config = _make_config(tmp_path)
        config["data_pipeline"]["contracts_path"] = str(contracts)
        config["data_pipeline"]["timeframe_conversion"]["target_timeframes"] = ["H1"]
        logger = logging.getLogger("live_test_determinism")

        source_table = _make_m1_table(120, start_ts=BASE_TS)

        # Run 1
        run1_dir = tmp_path / "run1" / "data-pipeline"
        run1_dir.mkdir(parents=True)
        source1 = run1_dir.parent / "source.arrow"
        with open(source1, "wb") as f:
            writer = pa.ipc.new_file(f, source_table.schema)
            writer.write_table(source_table)
            writer.close()
        config1 = {**config, "data_pipeline": {**config["data_pipeline"], "storage_path": str(run1_dir.parent)}}
        results1 = run_timeframe_conversion("EURUSD", source1, config1, logger)

        # Run 2
        run2_dir = tmp_path / "run2" / "data-pipeline"
        run2_dir.mkdir(parents=True)
        source2 = run2_dir.parent / "source.arrow"
        with open(source2, "wb") as f:
            writer = pa.ipc.new_file(f, source_table.schema)
            writer.write_table(source_table)
            writer.close()
        config2 = {**config, "data_pipeline": {**config["data_pipeline"], "storage_path": str(run2_dir.parent)}}
        results2 = run_timeframe_conversion("EURUSD", source2, config2, logger)

        # Compare file hashes
        hash1 = hashlib.sha256(results1["H1"]["arrow"].read_bytes()).hexdigest()
        hash2 = hashlib.sha256(results2["H1"]["arrow"].read_bytes()).hexdigest()
        assert hash1 == hash2, "Arrow IPC files are not bit-identical"

        hash1_pq = hashlib.sha256(results1["H1"]["parquet"].read_bytes()).hexdigest()
        hash2_pq = hashlib.sha256(results2["H1"]["parquet"].read_bytes()).hexdigest()
        assert hash1_pq == hash2_pq, "Parquet files are not bit-identical"


# =============================================================================
# Regression Tests (from review synthesis)
# =============================================================================


@pytest.mark.regression
class TestRegressionH1SessionRecomputation:
    """Regression: H1 session must be recomputed from config schedule, not M1 labels."""

    def test_h1_session_recomputed_from_schedule(self):
        """H1 session uses config schedule, not pre-labeled M1 session values.

        Creates M1 bars at 00:00 UTC (asian session per schedule) but labels
        them as 'london'. With session_schedule, the H1 bar must get 'asian'.
        """
        # 60 M1 bars at 00:00-00:59 UTC = asian session per schedule
        # Intentionally mislabeled as "london"
        table = _make_m1_table(60, start_ts=BASE_TS, session="london")
        session_schedule = {
            "timezone": "UTC",
            "asian": {"start": "00:00", "end": "08:00"},
            "london": {"start": "08:00", "end": "16:00"},
            "new_york": {"start": "13:00", "end": "21:00"},
            "london_ny_overlap": {"start": "13:00", "end": "16:00"},
            "off_hours": {"start": "21:00", "end": "00:00"},
        }
        result = convert_timeframe(
            table, "M1", "H1", session_schedule=session_schedule
        )
        # Must be "asian" (from schedule), NOT "london" (from M1 labels)
        assert result.column("session")[0].as_py() == "asian"

    def test_h1_session_tie_break_starts_during_hour(self):
        """When sessions tie in an hour, prefer the one starting during that hour.

        Custom schedule: asian ends at 08:30, london starts at 08:30.
        For the 08:00 hour: 30 min asian + 30 min london = tie.
        London starts during the hour (08:30), so london wins.
        """
        schedule = {
            "timezone": "UTC",
            "asian": {"start": "00:00", "end": "08:30"},
            "london": {"start": "08:30", "end": "16:00"},
        }
        start_ts = BASE_TS + 8 * _US_PER_HOUR  # 08:00 UTC
        table = _make_m1_table(60, start_ts=start_ts, session="dummy")
        result = convert_timeframe(
            table, "M1", "H1", session_schedule=schedule
        )
        assert result.column("session")[0].as_py() == "london"


@pytest.mark.regression
class TestRegressionPartialPreexistingOutput:
    """Regression: Existing output files must not be overwritten when partner is missing."""

    def test_partial_preexisting_output_not_overwritten(self, tmp_path, logger, monkeypatch):
        """If only arrow exists (parquet missing), arrow must NOT be overwritten."""
        contracts = _make_contracts(tmp_path)
        config = _make_config(tmp_path)
        config["data_pipeline"]["contracts_path"] = str(contracts)
        config["data_pipeline"]["timeframe_conversion"]["target_timeframes"] = ["M5"]

        source_table = _make_m1_table(20, start_ts=BASE_TS)
        source_dir = tmp_path / "data-pipeline"
        source_dir.mkdir(parents=True)
        source_path = source_dir / "EURUSD_M1.arrow"
        with open(source_path, "wb") as f:
            writer = pa.ipc.new_file(f, source_table.schema)
            writer.write_table(source_table)
            writer.close()

        # Run once to create both outputs
        results = run_timeframe_conversion("EURUSD", source_path, config, logger)
        arrow_path = results["M5"]["arrow"]
        parquet_path = results["M5"]["parquet"]

        # Record original arrow content hash
        original_arrow_hash = hashlib.sha256(arrow_path.read_bytes()).hexdigest()

        # Delete only parquet — simulates partial state
        parquet_path.unlink()

        # Run again — should recreate parquet, NOT overwrite arrow
        results2 = run_timeframe_conversion("EURUSD", source_path, config, logger)

        assert hashlib.sha256(arrow_path.read_bytes()).hexdigest() == original_arrow_hash
        assert parquet_path.exists()


@pytest.mark.regression
class TestRegressionEmptyTableSchema:
    """Regression: Empty result schema must match non-empty result schema."""

    def test_empty_table_schema_matches_non_empty(self):
        """Fully quarantined input produces empty table with same schema as valid output."""
        table_all_q = _make_m1_table(10, quarantined=[True] * 10)
        empty_result = convert_timeframe(table_all_q, "M1", "M5")

        table_valid = _make_m1_table(10)
        valid_result = convert_timeframe(table_valid, "M1", "M5")

        assert empty_result.schema == valid_result.schema


@pytest.mark.regression
class TestRegressionEmptyInputGuard:
    """Regression: Empty source data must not crash in _extract_date_range."""

    def test_empty_input_returns_empty_dict(self, tmp_path, logger, monkeypatch):
        """Empty source Arrow file returns {} without crashing."""
        contracts = _make_contracts(tmp_path)
        config = _make_config(tmp_path)
        config["data_pipeline"]["contracts_path"] = str(contracts)

        empty_table = _make_m1_table(0)
        source_dir = tmp_path / "data-pipeline"
        source_dir.mkdir(parents=True)
        source_path = source_dir / "EURUSD_M1.arrow"
        with open(source_path, "wb") as f:
            writer = pa.ipc.new_file(f, empty_table.schema)
            writer.write_table(empty_table)
            writer.close()

        results = run_timeframe_conversion("EURUSD", source_path, config, logger)
        assert results == {}


@pytest.mark.regression
class TestRegressionInvalidTargetTimeframe:
    """Regression: Invalid timeframe in config must raise ValueError early."""

    def test_invalid_target_timeframe_in_config_raises(self, tmp_path, logger, monkeypatch):
        """Config with invalid timeframe raises ValueError before any conversion."""
        contracts = _make_contracts(tmp_path)
        config = _make_config(tmp_path)
        config["data_pipeline"]["contracts_path"] = str(contracts)
        config["data_pipeline"]["timeframe_conversion"]["target_timeframes"] = ["M5", "INVALID"]

        source_table = _make_m1_table(20, start_ts=BASE_TS)
        source_dir = tmp_path / "data-pipeline"
        source_dir.mkdir(parents=True)
        source_path = source_dir / "EURUSD_M1.arrow"
        with open(source_path, "wb") as f:
            writer = pa.ipc.new_file(f, source_table.schema)
            writer.write_table(source_table)
            writer.close()

        with pytest.raises(ValueError, match="Invalid target timeframe"):
            run_timeframe_conversion("EURUSD", source_path, config, logger)
