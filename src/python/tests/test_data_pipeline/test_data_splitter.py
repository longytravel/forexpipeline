"""Tests for data_pipeline.data_splitter (Story 1.8)."""
import math
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.ipc
import pytest

from data_pipeline.data_splitter import (
    SplitError,
    _build_split_filename,
    _find_timeframe_files,
    split_train_test,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MARKET_SCHEMA = pa.schema([
    pa.field("timestamp", pa.int64(), nullable=False),
    pa.field("open", pa.float64(), nullable=False),
    pa.field("high", pa.float64(), nullable=False),
    pa.field("low", pa.float64(), nullable=False),
    pa.field("close", pa.float64(), nullable=False),
    pa.field("bid", pa.float64(), nullable=False),
    pa.field("ask", pa.float64(), nullable=False),
    pa.field("session", pa.utf8(), nullable=False),
    pa.field("quarantined", pa.bool_(), nullable=False),
])


def _make_table(n_rows: int, start_ts_us: int = 1_704_067_200_000_000) -> pa.Table:
    """Create a test market_data Arrow table with n_rows M1 bars.

    Timestamps start at start_ts_us and increment by 60s (60_000_000 us).
    """
    timestamps = [start_ts_us + i * 60_000_000 for i in range(n_rows)]
    return pa.table(
        {
            "timestamp": pa.array(timestamps, type=pa.int64()),
            "open": pa.array([1.1000 + i * 0.0001 for i in range(n_rows)], type=pa.float64()),
            "high": pa.array([1.1010 + i * 0.0001 for i in range(n_rows)], type=pa.float64()),
            "low": pa.array([1.0990 + i * 0.0001 for i in range(n_rows)], type=pa.float64()),
            "close": pa.array([1.1005 + i * 0.0001 for i in range(n_rows)], type=pa.float64()),
            "bid": pa.array([1.0999 + i * 0.0001 for i in range(n_rows)], type=pa.float64()),
            "ask": pa.array([1.1001 + i * 0.0001 for i in range(n_rows)], type=pa.float64()),
            "session": pa.array(["london"] * n_rows, type=pa.utf8()),
            "quarantined": pa.array([False] * n_rows, type=pa.bool_()),
        },
        schema=_MARKET_SCHEMA,
    )


def _make_split_config(ratio: float = 0.7, mode: str = "ratio", split_date: str = "") -> dict:
    """Create a config dict with splitting section."""
    return {
        "data_pipeline": {
            "splitting": {
                "split_ratio": ratio,
                "split_mode": mode,
                "split_date": split_date,
            }
        }
    }


# ---------------------------------------------------------------------------
# split_train_test — ratio mode
# ---------------------------------------------------------------------------

class TestSplitByRatio:
    def test_100_bars_70_30(self):
        """100 bars with ratio 0.7 -> 70 train, 30 test."""
        table = _make_table(100)
        config = _make_split_config(ratio=0.7)

        train, test, meta = split_train_test(table, config)

        assert train.num_rows == 70
        assert test.num_rows == 30
        assert meta["train_bar_count"] == 70
        assert meta["test_bar_count"] == 30

    def test_split_ratio_actual(self):
        table = _make_table(100)
        config = _make_split_config(ratio=0.7)
        _, _, meta = split_train_test(table, config)
        assert meta["split_ratio_actual"] == 0.7

    def test_split_index_uses_floor(self):
        """Split index = floor(total * ratio) — never rounds up."""
        table = _make_table(101)
        config = _make_split_config(ratio=0.7)
        train, test, _ = split_train_test(table, config)
        expected_train = int(math.floor(101 * 0.7))  # 70
        assert train.num_rows == expected_train
        assert test.num_rows == 101 - expected_train

    def test_large_ratio(self):
        """Ratio near max (0.95) still works."""
        table = _make_table(200)
        config = _make_split_config(ratio=0.95)
        train, test, _ = split_train_test(table, config)
        assert train.num_rows == 190
        assert test.num_rows == 10

    def test_small_ratio(self):
        """Ratio near min (0.5) still works."""
        table = _make_table(200)
        config = _make_split_config(ratio=0.5)
        train, test, _ = split_train_test(table, config)
        assert train.num_rows == 100
        assert test.num_rows == 100


# ---------------------------------------------------------------------------
# split_train_test — date mode
# ---------------------------------------------------------------------------

class TestSplitByDate:
    def test_date_split(self):
        """Split bars from 2024-01-01 spanning 365 days at 2024-07-01."""
        # 2024-01-01 00:00:00 UTC in microseconds
        start_us = 1_704_067_200_000_000
        table = _make_table(365 * 24 * 60, start_ts_us=start_us)  # 1 year of M1

        # 2024-07-01 00:00:00 UTC
        config = _make_split_config(mode="date", split_date="2024-07-01")
        train, test, meta = split_train_test(table, config)

        # Train should contain bars before 2024-07-01
        train_max_ts = pc.max(train.column("timestamp")).as_py()
        test_min_ts = pc.min(test.column("timestamp")).as_py()

        split_us = int(
            datetime(2024, 7, 1, tzinfo=timezone.utc).timestamp() * 1_000_000
        )
        assert train_max_ts < split_us
        assert test_min_ts >= split_us

    def test_date_split_requires_split_date(self):
        """split_mode='date' with empty split_date raises SplitError."""
        table = _make_table(100)
        config = _make_split_config(mode="date", split_date="")
        with pytest.raises(SplitError, match="split_date"):
            split_train_test(table, config)


# ---------------------------------------------------------------------------
# Temporal guarantee (AC #2)
# ---------------------------------------------------------------------------

class TestTemporalGuarantee:
    def test_strict_temporal_ordering(self):
        """max(train.timestamp) < min(test.timestamp)."""
        table = _make_table(100)
        config = _make_split_config(ratio=0.7)
        train, test, _ = split_train_test(table, config)

        train_max = pc.max(train.column("timestamp")).as_py()
        test_min = pc.min(test.column("timestamp")).as_py()
        assert train_max < test_min

    def test_no_data_leakage(self):
        """Train set contains NO timestamps >= split point (AC #2)."""
        table = _make_table(100)
        config = _make_split_config(ratio=0.7)
        train, test, meta = split_train_test(table, config)

        split_ts = meta["split_timestamp_us"]
        train_timestamps = train.column("timestamp").to_pylist()

        # Every train timestamp must be <= split_ts
        for ts in train_timestamps:
            assert ts <= split_ts

        # Every test timestamp must be > split_ts
        test_timestamps = test.column("timestamp").to_pylist()
        for ts in test_timestamps:
            assert ts > split_ts

    def test_no_shuffle(self):
        """Data order is preserved — train is the beginning, test is the end."""
        table = _make_table(100)
        config = _make_split_config(ratio=0.7)
        train, test, _ = split_train_test(table, config)

        train_ts = train.column("timestamp").to_pylist()
        test_ts = test.column("timestamp").to_pylist()

        # Both should be in ascending order
        assert train_ts == sorted(train_ts)
        assert test_ts == sorted(test_ts)

        # Train end comes before test start
        assert train_ts[-1] < test_ts[0]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_split_same_data_twice_identical(self):
        """Splitting the same data twice produces identical output."""
        table = _make_table(100)
        config = _make_split_config(ratio=0.7)

        train1, test1, meta1 = split_train_test(table, config)
        train2, test2, meta2 = split_train_test(table, config)

        assert train1.equals(train2)
        assert test1.equals(test2)
        assert meta1 == meta2


# ---------------------------------------------------------------------------
# Edge cases and errors
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_table_raises(self):
        """Cannot split an empty table."""
        empty = pa.table(
            {
                "timestamp": pa.array([], type=pa.int64()),
                "open": pa.array([], type=pa.float64()),
                "high": pa.array([], type=pa.float64()),
                "low": pa.array([], type=pa.float64()),
                "close": pa.array([], type=pa.float64()),
                "bid": pa.array([], type=pa.float64()),
                "ask": pa.array([], type=pa.float64()),
                "session": pa.array([], type=pa.utf8()),
                "quarantined": pa.array([], type=pa.bool_()),
            },
            schema=_MARKET_SCHEMA,
        )
        config = _make_split_config()
        with pytest.raises(SplitError, match="empty"):
            split_train_test(empty, config)

    def test_unknown_split_mode_raises(self):
        table = _make_table(10)
        config = _make_split_config(mode="random")
        with pytest.raises(SplitError, match="Unknown split_mode"):
            split_train_test(table, config)

    def test_split_with_explicit_timestamp(self):
        """Providing split_timestamp_us overrides config mode."""
        table = _make_table(100)
        config = _make_split_config(ratio=0.5)  # Would give 50/50

        # Pick timestamp at row 80
        ts_at_80 = table.column("timestamp")[80].as_py()
        train, test, meta = split_train_test(table, config, split_timestamp_us=ts_at_80)

        assert train.num_rows == 80
        assert test.num_rows == 20

    def test_metadata_contains_required_fields(self):
        table = _make_table(100)
        config = _make_split_config()
        _, _, meta = split_train_test(table, config)

        required_keys = {
            "split_timestamp_us",
            "split_date_iso",
            "train_bar_count",
            "test_bar_count",
            "split_ratio_actual",
            "split_mode",
            "configured_ratio",
        }
        assert required_keys.issubset(meta.keys())

    def test_flat_config_supported(self):
        """Config can be flat (just splitting keys) or nested."""
        table = _make_table(100)
        flat_config = {"split_ratio": 0.7, "split_mode": "ratio"}
        train, test, _ = split_train_test(table, flat_config)
        assert train.num_rows == 70


# ---------------------------------------------------------------------------
# _find_timeframe_files
# ---------------------------------------------------------------------------

class TestFindTimeframeFiles:
    def test_finds_known_timeframes(self, tmp_path):
        """Finds M1, M5, H1, D1, W arrow files."""
        for tf in ("M1", "M5", "H1", "D1", "W"):
            (tmp_path / f"EURUSD_2024-01-01_2024-12-31_{tf}.arrow").write_bytes(b"x")

        found = _find_timeframe_files("EURUSD", tmp_path)
        assert set(found.keys()) == {"M1", "M5", "H1", "D1", "W"}

    def test_excludes_train_test_files(self, tmp_path):
        """Split output files should NOT be included."""
        (tmp_path / "EURUSD_2024-01-01_2024-12-31_M1.arrow").write_bytes(b"x")
        (tmp_path / "EURUSD_2024-01-01_2024-12-31_M1_train.arrow").write_bytes(b"x")
        (tmp_path / "EURUSD_2024-01-01_2024-12-31_M1_test.arrow").write_bytes(b"x")

        found = _find_timeframe_files("EURUSD", tmp_path)
        assert set(found.keys()) == {"M1"}

    def test_filters_by_pair(self, tmp_path):
        (tmp_path / "EURUSD_2024-01-01_2024-12-31_M1.arrow").write_bytes(b"x")
        (tmp_path / "GBPUSD_2024-01-01_2024-12-31_M1.arrow").write_bytes(b"x")

        found = _find_timeframe_files("EURUSD", tmp_path)
        assert "M1" in found
        assert "EURUSD" in found["M1"].name

    def test_empty_dir(self, tmp_path):
        assert _find_timeframe_files("EURUSD", tmp_path) == {}


# ---------------------------------------------------------------------------
# Regression tests (Review Synthesis 1.8)
# ---------------------------------------------------------------------------

@pytest.mark.regression
class TestRegressionUnsortedInput:
    """Regression: ratio split must sort by timestamp before slicing.

    Codex HIGH finding — unsorted input was sliced by row position,
    producing non-chronological partitions.
    """

    def test_unsorted_input_produces_chronological_split(self):
        """Feeding reverse-ordered timestamps must still produce correct split."""
        n = 100
        start_us = 1_704_067_200_000_000
        # Build table in REVERSE timestamp order
        timestamps = [start_us + (n - 1 - i) * 60_000_000 for i in range(n)]
        table = pa.table(
            {
                "timestamp": pa.array(timestamps, type=pa.int64()),
                "open": pa.array([1.1] * n, type=pa.float64()),
                "high": pa.array([1.11] * n, type=pa.float64()),
                "low": pa.array([1.09] * n, type=pa.float64()),
                "close": pa.array([1.1] * n, type=pa.float64()),
                "bid": pa.array([1.1] * n, type=pa.float64()),
                "ask": pa.array([1.1] * n, type=pa.float64()),
                "session": pa.array(["london"] * n, type=pa.utf8()),
                "quarantined": pa.array([False] * n, type=pa.bool_()),
            },
            schema=_MARKET_SCHEMA,
        )
        config = _make_split_config(ratio=0.7)
        train, test, meta = split_train_test(table, config)

        # Train must be the earliest 70 bars, test the latest 30
        train_ts = train.column("timestamp").to_pylist()
        test_ts = test.column("timestamp").to_pylist()
        assert train_ts == sorted(train_ts), "Train not in ascending order"
        assert test_ts == sorted(test_ts), "Test not in ascending order"
        assert train_ts[-1] < test_ts[0], "Temporal guarantee violated"
        assert train.num_rows == 70
        assert test.num_rows == 30

    def test_shuffled_input_produces_chronological_split(self):
        """Randomly shuffled timestamps are sorted before splitting."""
        import random

        n = 200
        start_us = 1_704_067_200_000_000
        timestamps = [start_us + i * 60_000_000 for i in range(n)]
        shuffled = timestamps[:]
        random.Random(42).shuffle(shuffled)

        table = pa.table(
            {
                "timestamp": pa.array(shuffled, type=pa.int64()),
                "open": pa.array([1.1] * n, type=pa.float64()),
                "high": pa.array([1.11] * n, type=pa.float64()),
                "low": pa.array([1.09] * n, type=pa.float64()),
                "close": pa.array([1.1] * n, type=pa.float64()),
                "bid": pa.array([1.1] * n, type=pa.float64()),
                "ask": pa.array([1.1] * n, type=pa.float64()),
                "session": pa.array(["london"] * n, type=pa.utf8()),
                "quarantined": pa.array([False] * n, type=pa.bool_()),
            },
            schema=_MARKET_SCHEMA,
        )
        config = _make_split_config(ratio=0.7)
        train, test, _ = split_train_test(table, config)

        train_max = pc.max(train.column("timestamp")).as_py()
        test_min = pc.min(test.column("timestamp")).as_py()
        assert train_max < test_min


@pytest.mark.regression
class TestRegressionHashInFilenames:
    """Regression: split filenames must include data hash so new downloads
    produce distinct files (AC #5).

    Codex HIGH finding — filenames without hash caused stale artifact reuse.
    """

    def test_build_split_filename_includes_hash(self):
        """Filename includes hash when data_hash8 is provided."""
        name = _build_split_filename(
            "EURUSD", "2024-01-01", "2024-12-31", "M1", "train", "arrow",
            data_hash8="a3b8f2c1",
        )
        assert name == "EURUSD_2024-01-01_2024-12-31_a3b8f2c1_M1_train.arrow"

    def test_different_hashes_produce_different_filenames(self):
        """Two downloads with different hashes must produce different filenames."""
        name1 = _build_split_filename(
            "EURUSD", "2024-01-01", "2024-12-31", "M1", "train", "arrow",
            data_hash8="aaaaaaaa",
        )
        name2 = _build_split_filename(
            "EURUSD", "2024-01-01", "2024-12-31", "M1", "train", "arrow",
            data_hash8="bbbbbbbb",
        )
        assert name1 != name2


@pytest.mark.regression
class TestRegressionDateModeMetadata:
    """Regression: date-mode metadata must include the configured split date.

    Codex MEDIUM finding — metadata only recorded the actual last-train
    timestamp, losing traceability to the user-configured boundary.
    """

    def test_date_mode_includes_configured_split_date(self):
        """Metadata contains configured_split_date when split_mode='date'."""
        start_us = 1_704_067_200_000_000
        table = _make_table(365 * 24 * 60, start_ts_us=start_us)
        config = _make_split_config(mode="date", split_date="2024-07-01")
        _, _, meta = split_train_test(table, config)

        assert "configured_split_date" in meta
        assert meta["configured_split_date"] == "2024-07-01"

    def test_ratio_mode_has_no_configured_split_date(self):
        """Ratio mode should not include configured_split_date."""
        table = _make_table(100)
        config = _make_split_config(ratio=0.7)
        _, _, meta = split_train_test(table, config)

        assert "configured_split_date" not in meta
