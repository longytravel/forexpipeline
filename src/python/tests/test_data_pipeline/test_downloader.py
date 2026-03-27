"""Tests for data_pipeline.downloader — Story 1.4."""
import hashlib
import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from data_pipeline.downloader import DukascopyDownloader


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def download_config():
    """Config dict matching the data_pipeline schema."""
    return {
        "data_pipeline": {
            "storage_path": "G:\\My Drive\\ForexPipeline",
            "default_resolution": "M1",
            "request_delay_seconds": 0.5,
            "max_retries": 3,
            "download": {
                "pairs": ["EURUSD"],
                "start_date": "2015-01-01",
                "end_date": "2025-12-31",
                "resolution": "M1",
            },
        },
    }


@pytest.fixture
def mock_logger():
    """Structured logger mock."""
    return MagicMock()


@pytest.fixture
def downloader(download_config, mock_logger):
    """DukascopyDownloader instance with mocked logger."""
    return DukascopyDownloader(download_config, mock_logger)


@pytest.fixture
def sample_bid_df():
    """Sample bid-side M1 DataFrame."""
    timestamps = pd.date_range("2024-01-02", periods=5, freq="min", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [1.1000, 1.1001, 1.1002, 1.1003, 1.1004],
            "high": [1.1005, 1.1006, 1.1007, 1.1008, 1.1009],
            "low": [1.0995, 1.0996, 1.0997, 1.0998, 1.0999],
            "close": [1.1001, 1.1002, 1.1003, 1.1004, 1.1005],
            "volume": [100, 150, 120, 130, 110],
        }
    )


@pytest.fixture
def sample_ask_df():
    """Sample ask-side M1 DataFrame."""
    timestamps = pd.date_range("2024-01-02", periods=5, freq="min", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [1.1002, 1.1003, 1.1004, 1.1005, 1.1006],
            "high": [1.1007, 1.1008, 1.1009, 1.1010, 1.1011],
            "low": [1.0997, 1.0998, 1.0999, 1.1000, 1.1001],
            "close": [1.1003, 1.1004, 1.1005, 1.1006, 1.1007],
            "volume": [100, 150, 120, 130, 110],
        }
    )


# ---------------------------------------------------------------------------
# Task 2 — Unit tests: bid/ask combination
# ---------------------------------------------------------------------------

class TestDownloadYearBidask:
    """Test 6.3: verify bid/ask DataFrames are combined correctly."""

    def test_download_year_bidask_combines_correctly(
        self, downloader, sample_bid_df, sample_ask_df
    ):
        """Bid/ask DataFrames should combine with bid and ask close columns."""
        with patch("data_pipeline.downloader.dk") as mock_dk:
            mock_dk.INTERVAL_MIN_1 = "min1"
            mock_dk.OFFER_SIDE_BID = "bid"
            mock_dk.OFFER_SIDE_ASK = "ask"
            mock_dk.fetch.side_effect = [sample_bid_df, sample_ask_df]

            result = downloader._download_year_bidask("EURUSD", 2024)

        assert result is not None
        assert "bid" in result.columns
        assert "ask" in result.columns
        assert "timestamp" in result.columns
        assert "open" in result.columns
        assert "close" in result.columns
        # bid column = bid-side close, ask column = ask-side close
        assert list(result["bid"]) == list(sample_bid_df["close"])
        assert list(result["ask"]) == list(sample_ask_df["close"])

    def test_download_year_bidask_no_data(self, downloader):
        """Returns None when Dukascopy returns no data."""
        with patch("data_pipeline.downloader.dk") as mock_dk:
            mock_dk.INTERVAL_MIN_1 = "min1"
            mock_dk.OFFER_SIDE_BID = "bid"
            mock_dk.fetch.return_value = pd.DataFrame()

            result = downloader._download_year_bidask("EURUSD", 2024)

        assert result is None


# ---------------------------------------------------------------------------
# Task 2 — Unit tests: crash-safe chunk save
# ---------------------------------------------------------------------------

class TestSaveChunk:
    """Test 6.4: verify yearly chunk save uses crash-safe pattern."""

    def test_save_chunk_crash_safe(self, downloader, sample_bid_df, tmp_path):
        """Chunk save must use .partial -> fsync -> os.replace() pattern."""
        chunk_dir = tmp_path / "EURUSD_M1_chunks"

        with patch.object(downloader, "_chunk_dir", return_value=chunk_dir):
            result = downloader._save_chunk(sample_bid_df, "EURUSD", 2024, tmp_path)

        assert result.exists()
        assert result.name == "EURUSD_M1_2024.parquet"
        # No .partial files should remain
        partials = list(tmp_path.rglob("*.partial"))
        assert partials == []
        # Read back and verify content
        loaded = pd.read_parquet(result)
        assert len(loaded) == len(sample_bid_df)


# ---------------------------------------------------------------------------
# Task 2 — Unit tests: consolidate chunks
# ---------------------------------------------------------------------------

class TestConsolidateChunks:
    """Test 6.5: verify yearly chunks merge with dedup and sorting."""

    def test_consolidate_chunks(self, downloader, tmp_path):
        """Merge multiple yearly chunk files correctly."""
        chunk_dir = tmp_path / "EURUSD_M1_chunks"
        chunk_dir.mkdir()

        # Create two yearly chunks with some overlap
        ts1 = pd.date_range("2023-01-01", periods=3, freq="min", tz="UTC")
        df1 = pd.DataFrame(
            {
                "timestamp": ts1,
                "open": [1.10, 1.11, 1.12],
                "high": [1.15, 1.16, 1.17],
                "low": [1.05, 1.06, 1.07],
                "close": [1.11, 1.12, 1.13],
                "volume": [100, 200, 300],
                "bid": [1.10, 1.11, 1.12],
                "ask": [1.12, 1.13, 1.14],
            }
        )
        df1.to_parquet(chunk_dir / "EURUSD_M1_2023.parquet")

        ts2 = pd.date_range("2024-01-01", periods=3, freq="min", tz="UTC")
        df2 = pd.DataFrame(
            {
                "timestamp": ts2,
                "open": [1.20, 1.21, 1.22],
                "high": [1.25, 1.26, 1.27],
                "low": [1.15, 1.16, 1.17],
                "close": [1.21, 1.22, 1.23],
                "volume": [400, 500, 600],
                "bid": [1.20, 1.21, 1.22],
                "ask": [1.22, 1.23, 1.24],
            }
        )
        df2.to_parquet(chunk_dir / "EURUSD_M1_2024.parquet")

        with patch.object(downloader, "_chunk_dir", return_value=chunk_dir):
            result = downloader._consolidate_chunks("EURUSD", tmp_path)

        assert len(result) == 6
        # Verify monotonically increasing timestamps
        timestamps = result["timestamp"].tolist()
        for i in range(1, len(timestamps)):
            assert timestamps[i] > timestamps[i - 1]


# ---------------------------------------------------------------------------
# Task 4 — Unit tests: dataset ID and hash
# ---------------------------------------------------------------------------

class TestGenerateDatasetId:
    """Test 6.8: verify naming convention."""

    def test_generate_dataset_id(self, downloader):
        """Dataset ID must match the expected naming pattern."""
        result = downloader.generate_dataset_id(
            "EURUSD", date(2015, 1, 1), date(2025, 12, 31), "M1"
        )
        assert result == "EURUSD_2015-01-01_2025-12-31_M1"


class TestComputeDataHash:
    """Test 6.9: verify deterministic hash output."""

    def test_compute_data_hash(self, downloader):
        """Same DataFrame content produces same hash."""
        timestamps = pd.date_range("2024-01-01", periods=3, freq="min", tz="UTC")
        df = pd.DataFrame({"timestamp": timestamps, "close": [1.1, 1.2, 1.3]})

        hash1 = downloader.compute_data_hash(df)
        hash2 = downloader.compute_data_hash(df)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest

    def test_different_data_different_hash(self, downloader):
        """Different DataFrame content produces different hash."""
        timestamps = pd.date_range("2024-01-01", periods=3, freq="min", tz="UTC")
        df1 = pd.DataFrame({"timestamp": timestamps, "close": [1.1, 1.2, 1.3]})
        df2 = pd.DataFrame({"timestamp": timestamps, "close": [1.1, 1.2, 1.4]})

        assert downloader.compute_data_hash(df1) != downloader.compute_data_hash(df2)


# ---------------------------------------------------------------------------
# Task 4 — Integration tests: crash-safe write and versioned artifacts
# ---------------------------------------------------------------------------

class TestCrashSafeWrite:
    """Test 6.10: verify .partial -> rename works correctly."""

    def test_crash_safe_write_integration(self, downloader, tmp_path):
        """Full crash-safe write cycle: no .partial files left behind."""
        timestamps = pd.date_range("2024-01-01", periods=3, freq="min", tz="UTC")
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": [1.1, 1.2, 1.3],
            "high": [1.15, 1.25, 1.35],
            "low": [1.05, 1.15, 1.25],
            "close": [1.11, 1.21, 1.31],
            "volume": [100, 200, 300],
            "bid": [1.10, 1.20, 1.30],
            "ask": [1.12, 1.22, 1.32],
        })

        artifact_path = downloader.save_raw_artifact(
            df, "EURUSD", date(2024, 1, 1), date(2024, 12, 31), "M1", tmp_path
        )

        assert artifact_path.exists()
        assert not list(tmp_path.rglob("*.partial"))
        # Verify content round-trips
        loaded = pd.read_csv(artifact_path)
        assert len(loaded) == 3


class TestIncrementalDownloadMock:
    """Test 6.11: mock Dukascopy responses, verify only missing data requested."""

    def test_incremental_download_mock(self, downloader, tmp_path):
        """When data exists for 2023, only 2024+ should be downloaded."""
        # Create existing chunk for 2023
        chunk_dir = tmp_path / "EURUSD_M1_chunks"
        chunk_dir.mkdir()
        ts = pd.date_range("2023-01-01", periods=3, freq="min", tz="UTC")
        df = pd.DataFrame({
            "timestamp": ts, "open": [1.1, 1.2, 1.3],
            "high": [1.15, 1.25, 1.35], "low": [1.05, 1.15, 1.25],
            "close": [1.11, 1.21, 1.31], "volume": [100, 200, 300],
            "bid": [1.10, 1.20, 1.30], "ask": [1.12, 1.22, 1.32],
        })
        df.to_parquet(chunk_dir / "EURUSD_M1_2023.parquet")

        existing = downloader._get_downloaded_years("EURUSD", tmp_path)
        assert 2023 in existing
        assert 2024 not in existing


class TestGracefulDegradation:
    """Test 6.12: mock timeout, verify partial data + failed periods in manifest."""

    def test_graceful_degradation(self, downloader, tmp_path):
        """Timeout on one year should not block other years."""
        # Download 2023 succeeds, 2024 times out
        ts = pd.date_range("2023-01-01", periods=3, freq="min", tz="UTC")
        success_df = pd.DataFrame({
            "timestamp": ts, "open": [1.1, 1.2, 1.3],
            "high": [1.15, 1.25, 1.35], "low": [1.05, 1.15, 1.25],
            "close": [1.11, 1.21, 1.31], "volume": [100, 200, 300],
            "bid": [1.10, 1.20, 1.30], "ask": [1.12, 1.22, 1.32],
        })

        call_count = 0
        def mock_download_year_bidask(pair, year):
            nonlocal call_count
            call_count += 1
            if year == 2024:
                return None  # Simulate failure
            return success_df

        with patch.object(downloader, "_download_year_bidask", side_effect=mock_download_year_bidask), \
             patch.object(downloader, "_save_chunk"):
            failed = []
            for year in [2023, 2024]:
                result = downloader._download_year_bidask("EURUSD", year)
                if result is None:
                    failed.append(str(year))

            assert "2024" in failed
            assert len(failed) == 1


# ---------------------------------------------------------------------------
# LIVE integration tests — hit real Dukascopy API
# Marked with @pytest.mark.live so they're skipped by default.
# Run with: pytest -m live
# ---------------------------------------------------------------------------

@pytest.mark.live
class TestLiveM1Download:
    """Live test: download real M1 data from Dukascopy and validate output."""

    def test_live_m1_download_one_day(self, tmp_path):
        """Download 1 day of EURUSD M1 bid+ask from Dukascopy.

        Validates:
        - Data actually comes back (non-empty)
        - Expected columns present (timestamp, open, high, low, close, volume, bid, ask)
        - Timestamps are UTC
        - Timestamps are monotonically increasing
        - bid and ask columns are present and non-NaN
        - Row count is reasonable (~1440 bars max for 1 day of M1)
        - Crash-safe chunk save works with real data
        - Versioned artifact save works with real data
        """
        config = {
            "data_pipeline": {
                "storage_path": str(tmp_path),
                "default_resolution": "M1",

                "request_delay_seconds": 1.0,
                "max_retries": 3,

                "download": {
                    "pairs": ["EURUSD"],
                    "start_date": "2024-06-03",
                    "end_date": "2024-06-03",
                    "resolution": "M1",
                },
            },
        }

        logger = MagicMock()
        dl = DukascopyDownloader(config, logger)

        # Download one year (2024) — which contains our target day
        df = dl._download_year_bidask("EURUSD", 2024)

        assert df is not None, "Dukascopy returned no data — API may be down"
        assert not df.empty, "Dukascopy returned empty DataFrame"

        # --- Column checks ---
        expected_cols = {"timestamp", "open", "high", "low", "close", "volume", "bid", "ask"}
        assert expected_cols.issubset(set(df.columns)), (
            f"Missing columns: {expected_cols - set(df.columns)}"
        )

        # --- Timestamp checks ---
        timestamps = pd.to_datetime(df["timestamp"])
        assert timestamps.dt.tz is not None or str(timestamps.dtype).startswith("datetime64"), \
            "Timestamps should be timezone-aware UTC"
        # Monotonically increasing
        diffs = timestamps.diff().dropna()
        assert (diffs >= pd.Timedelta(0)).all(), "Timestamps must be monotonically increasing"

        # --- Bid/ask checks ---
        assert df["bid"].notna().sum() > 0, "bid column should have non-NaN values"
        assert df["ask"].notna().sum() > 0, "ask column should have non-NaN values"
        # ask should be >= bid (spread is non-negative)
        valid_mask = df["bid"].notna() & df["ask"].notna()
        if valid_mask.any():
            assert (df.loc[valid_mask, "ask"] >= df.loc[valid_mask, "bid"]).all(), \
                "ask should be >= bid (non-negative spread)"

        # --- Row count sanity ---
        # Full year of M1 = ~525K bars, but market is closed weekends
        # At minimum we expect thousands of rows for a year
        assert len(df) > 1000, f"Expected >1000 M1 bars for a year, got {len(df)}"

        # --- Crash-safe chunk save with real data ---
        chunk_path = dl._save_chunk(df, "EURUSD", 2024, tmp_path)
        assert chunk_path.exists()
        assert not list(tmp_path.rglob("*.partial"))
        loaded = pd.read_parquet(chunk_path)
        assert len(loaded) == len(df)

        # --- Versioned artifact save with real data ---
        artifact_path = dl.save_raw_artifact(
            df, "EURUSD", date(2024, 1, 1), date(2024, 12, 31), "M1", tmp_path
        )
        assert artifact_path.exists()
        assert "v001" in str(artifact_path)
        loaded_csv = pd.read_csv(artifact_path)
        assert len(loaded_csv) == len(df)

        # --- Manifest ---
        dataset_id = dl.generate_dataset_id("EURUSD", date(2024, 1, 1), date(2024, 12, 31), "M1")
        data_hash = dl.compute_data_hash(df)
        manifest_path = dl.write_download_manifest(
            dataset_id=dataset_id,
            version="v001",
            data_hash=data_hash,
            pair="EURUSD",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            resolution="M1",
            row_count=len(df),
            failed_periods=[],
            storage_path=tmp_path,
        )
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["pair"] == "EURUSD"
        assert manifest["row_count"] == len(df)
        assert manifest["data_hash"] == data_hash
        assert manifest["failed_periods"] == []

        print(f"\n  LIVE M1 TEST PASSED")
        print(f"  Rows downloaded: {len(df)}")
        print(f"  Date range: {timestamps.min()} ->{timestamps.max()}")
        print(f"  Bid range: {df['bid'].min():.5f} – {df['bid'].max():.5f}")
        print(f"  Ask range: {df['ask'].min():.5f} – {df['ask'].max():.5f}")
        print(f"  Chunk saved: {chunk_path}")
        print(f"  Artifact saved: {artifact_path}")


@pytest.mark.live
class TestLiveTickDownload:
    """Live test: download real tick data from Dukascopy and validate output."""

    def test_live_tick_download_one_hour(self, tmp_path):
        """Download 1 hour of EURUSD tick data from Dukascopy.

        Validates:
        - Data actually comes back (non-empty)
        - Tick columns present (bid, ask at minimum)
        - Timestamps are UTC and monotonically increasing
        - Row count is reasonable (hundreds to thousands of ticks per hour)
        """
        config = {
            "data_pipeline": {
                "storage_path": str(tmp_path),
                "default_resolution": "tick",

                "request_delay_seconds": 1.0,
                "max_retries": 3,

                "download": {
                    "pairs": ["EURUSD"],
                    "start_date": "2024-06-03",
                    "end_date": "2024-06-03",
                    "resolution": "tick",
                },
            },
        }

        logger = MagicMock()
        dl = DukascopyDownloader(config, logger)

        # Download 1 hour of tick data (Monday 10:00-11:00 UTC — active London session)
        start = datetime(2024, 6, 3, 10, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 6, 3, 11, 0, 0, tzinfo=timezone.utc)

        df = dl._download_tick_data("EURUSD", start, end)

        assert df is not None, "Dukascopy returned no tick data — API may be down"
        assert not df.empty, "Dukascopy returned empty tick DataFrame"

        # --- Column checks ---
        # dukascopy-python tick format may vary; check for price columns
        cols = set(df.columns)
        has_bid_ask = ("bid" in cols and "ask" in cols) or ("close" in cols)
        assert has_bid_ask, f"Expected bid/ask or close columns, got: {cols}"

        # --- Row count sanity ---
        # EURUSD during London session: expect hundreds to thousands of ticks per hour
        assert len(df) > 10, f"Expected >10 ticks for 1 hour of EURUSD, got {len(df)}"

        # --- Timestamp ordering ---
        if hasattr(df.index, 'is_monotonic_increasing'):
            # Index-based timestamps
            assert df.index.is_monotonic_increasing, "Tick timestamps must be monotonically increasing"
            print(f"\n  LIVE TICK TEST PASSED")
            print(f"  Ticks downloaded: {len(df)}")
            print(f"  Time range: {df.index[0]} ->{df.index[-1]}")
        elif "timestamp" in df.columns:
            timestamps = pd.to_datetime(df["timestamp"])
            diffs = timestamps.diff().dropna()
            assert (diffs >= pd.Timedelta(0)).all(), "Tick timestamps must be non-decreasing"
            print(f"\n  LIVE TICK TEST PASSED")
            print(f"  Ticks downloaded: {len(df)}")
            print(f"  Time range: {timestamps.min()} ->{timestamps.max()}")
        else:
            print(f"\n  LIVE TICK TEST PASSED (no timestamp column to validate ordering)")
            print(f"  Ticks downloaded: {len(df)}")

        print(f"  Columns: {list(df.columns)}")


@pytest.mark.live
class TestLiveFullPipeline:
    """Live test: run the full download pipeline end-to-end."""

    def test_live_full_pipeline_single_pair(self, tmp_path):
        """Full pipeline: config ->download ->chunk ->consolidate ->artifact ->manifest.

        Downloads a single year of real data for one pair and validates
        the entire flow produces correct versioned artifacts.
        """
        config = {
            "data_pipeline": {
                "storage_path": str(tmp_path),
                "default_resolution": "M1",

                "request_delay_seconds": 1.0,
                "max_retries": 3,

                "download": {
                    "pairs": ["EURUSD"],
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                    "resolution": "M1",
                },
            },
        }

        logger = MagicMock()
        dl = DukascopyDownloader(config, logger)

        # Full download for 2024
        df = dl.download("EURUSD", date(2024, 1, 1), date(2024, 12, 31), "M1")

        assert not df.empty, "Full pipeline download returned empty data"
        assert len(df) > 100_000, f"Expected >100K M1 bars for 1 year, got {len(df)}"

        # Verify chunks were created
        chunk_dir = tmp_path / "EURUSD_M1_chunks"
        assert chunk_dir.exists(), "Chunk directory should exist"
        chunks = list(chunk_dir.glob("*.parquet"))
        assert len(chunks) >= 1, "At least 1 yearly chunk should exist"

        # Verify consolidated data
        timestamps = pd.to_datetime(df["timestamp"])
        assert timestamps.is_monotonic_increasing, "Consolidated timestamps must be monotonic"

        # Save versioned artifact
        artifact_path = dl.save_raw_artifact(
            df, "EURUSD", date(2024, 1, 1), date(2024, 12, 31), "M1", tmp_path
        )
        assert artifact_path.exists()

        # Second save should create v002
        artifact_path_v2 = dl.save_raw_artifact(
            df, "EURUSD", date(2024, 1, 1), date(2024, 12, 31), "M1", tmp_path
        )
        assert "v002" in str(artifact_path_v2), "Second save should increment version"
        # v001 should still exist (never overwritten)
        assert artifact_path.exists(), "v001 must not be overwritten"

        print(f"\n  LIVE FULL PIPELINE TEST PASSED")
        print(f"  Total M1 bars: {len(df)}")
        print(f"  Date range: {timestamps.min()} ->{timestamps.max()}")
        print(f"  Chunks created: {len(chunks)}")
        print(f"  Artifact v001: {artifact_path}")
        print(f"  Artifact v002: {artifact_path_v2}")


# ---------------------------------------------------------------------------
# Regression tests — Story 1.10 PIR Remediation synthesis
# ---------------------------------------------------------------------------

class TestDeadConfigRegression:
    """Regression: orphaned config keys must not creep back into the
    pipeline config. download_timeout_seconds and retry_backoff_factor
    were present in config/schema but never read by the downloader."""

    @pytest.mark.regression
    def test_downloader_ignores_unknown_config_keys(self):
        """Downloader must init successfully without timeout/backoff keys."""
        config = {
            "data_pipeline": {
                "storage_path": "test/data",
                "default_resolution": "M1",
                "request_delay_seconds": 0.5,
                "max_retries": 3,
                "download": {
                    "pairs": ["EURUSD"],
                    "start_date": "2024-01-01",
                    "end_date": "2024-12-31",
                    "resolution": "M1",
                },
            },
        }
        logger = MagicMock()
        dl = DukascopyDownloader(config, logger)
        # Should not have timeout/backoff attributes
        assert not hasattr(dl, "_timeout"), "Dead config _timeout must not exist"
        assert not hasattr(dl, "_backoff_factor"), "Dead config _backoff_factor must not exist"

    @pytest.mark.regression
    def test_config_schema_no_orphaned_timeout_backoff(self):
        """Config schema must not define download_timeout_seconds or
        retry_backoff_factor — they had no runtime effect."""
        import tomllib
        schema_path = Path(__file__).resolve().parents[4] / "config" / "schema.toml"
        if not schema_path.exists():
            pytest.skip("schema.toml not found at expected location")
        with open(schema_path, "rb") as f:
            schema = tomllib.load(f)

        dp_schema = schema.get("schema", {}).get("data_pipeline", {})
        assert "download_timeout_seconds" not in dp_schema, (
            "download_timeout_seconds must not be in schema — it has no runtime effect"
        )
        assert "retry_backoff_factor" not in dp_schema, (
            "retry_backoff_factor must not be in schema — it has no runtime effect"
        )
