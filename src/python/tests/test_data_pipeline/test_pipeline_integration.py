"""Pipeline integration tests.

Two kinds of tests live here:

1. BOUNDARY TESTS — verify two adjacent stages are interface-compatible.
   Use synthetic data, fast, no disk artifacts needed.

2. CHAIN TEST — loads real pipeline artifacts already on disk and runs
   the full chain forward.  Does NOT re-download data or re-build
   anything that already exists.  When a new stage is added (backtester,
   strategy, etc.), you add one more step that picks up where the
   previous stage left off.

Marked @pytest.mark.live — run with: pytest -m live
"""
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.ipc
import pytest

from data_pipeline.arrow_converter import ArrowConverter
from data_pipeline.downloader import DukascopyDownloader
from data_pipeline.quality_checker import DataQualityChecker, ValidationResult
from data_pipeline.timeframe_converter import convert_timeframe

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
_TEST_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _TEST_DIR.parent.parent.parent.parent

CONTRACTS_PATH = _PROJECT_ROOT / "contracts"
CONFIG_PATH = _PROJECT_ROOT / "config"


def _load_real_config() -> dict:
    import tomllib

    with open(CONFIG_PATH / "base.toml", "rb") as f:
        return tomllib.load(f)


def _make_realistic_df(n: int = 500) -> pd.DataFrame:
    """Minimal synthetic M1 data matching downloader output format."""
    rng = np.random.default_rng(42)
    timestamps = pd.date_range("2024-06-05 00:00", periods=n, freq="min", tz="UTC")
    base = 1.1000
    prices = base + rng.standard_normal(n).cumsum() * 0.0001

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": prices,
            "high": prices + rng.uniform(0.0001, 0.001, n),
            "low": prices - rng.uniform(0.0001, 0.001, n),
            "close": prices + rng.standard_normal(n) * 0.0002,
            "volume": rng.integers(10, 1000, n).astype(float),
            "bid": prices,
            "ask": prices + rng.uniform(0.0001, 0.0005, n),
        }
    )


def _find_arrow_files(storage_path: Path) -> list[Path]:
    """Find existing Arrow IPC files from prior pipeline runs."""
    if not storage_path.exists():
        return []
    return sorted(storage_path.rglob("*.arrow"))


def _setup_storage_config(config: dict, tmp_path: Path) -> dict:
    config["data_pipeline"]["storage"] = {
        "arrow_ipc_path": str(tmp_path / "arrow"),
        "parquet_path": str(tmp_path / "parquet"),
    }
    return config


# ===================================================================
# BOUNDARY TESTS — fast, synthetic data, test interface compatibility
# ===================================================================


@pytest.mark.live
class TestDownloadToValidation:
    """Boundary: Downloader (1-4) → Quality Checker (1-5)."""

    @pytest.mark.live
    def test_download_output_validates_successfully(self, tmp_path):
        """Download real data, feed directly into quality checker."""
        config = _load_real_config()
        logger = logging.getLogger("integration.dl_to_val")

        downloader = DukascopyDownloader(config, logger)
        dl_date = date(2024, 6, 5)
        raw_df = downloader.download(
            pair="EURUSD",
            start_date=dl_date,
            end_date=dl_date,
            resolution="M1",
        )

        assert not raw_df.empty, "Download must return data"
        initial_rows = len(raw_df)

        ts = pd.to_datetime(raw_df["timestamp"])
        actual_start = ts.min().date()
        actual_end = ts.max().date()

        checker = DataQualityChecker(config, logger)
        result = checker.validate(
            df=raw_df,
            pair="EURUSD",
            resolution="M1",
            start_date=actual_start,
            end_date=actual_end,
            storage_path=tmp_path,
            dataset_id="EURUSD_dukascopy_integration",
            version="v001",
        )

        assert isinstance(result, ValidationResult)
        assert result.quality_score >= 0
        assert result.rating in ("GREEN", "YELLOW", "RED")
        assert result.validated_df is not None
        assert len(result.validated_df) == initial_rows, "Validation must not drop rows"
        assert "quarantined" in result.validated_df.columns

        report = json.loads(result.report_path.read_text())
        assert "gap_penalty" in report["penalty_breakdown"]


@pytest.mark.live
class TestValidationToStorage:
    """Boundary: Quality Checker (1-5) → Arrow Converter (1-6)."""

    @pytest.mark.live
    def test_validated_df_converts_to_arrow(self, tmp_path):
        """Validate synthetic data, feed into Arrow converter."""
        config = _setup_storage_config(_load_real_config(), tmp_path)
        logger = logging.getLogger("integration.val_to_store")

        df = _make_realistic_df(500)

        checker = DataQualityChecker(config, logger)
        val_result = checker.validate(
            df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2024, 6, 5),
            end_date=date(2024, 6, 5),
            storage_path=tmp_path,
            dataset_id="EURUSD_val_to_store_integration",
            version="v001",
        )
        assert val_result.validated_df is not None

        config["data_pipeline"]["contracts_path"] = str(CONTRACTS_PATH)
        converter = ArrowConverter(config, logger)

        conv_result = converter.convert(
            validated_df=val_result.validated_df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2024, 6, 5),
            end_date=date(2024, 6, 5),
            dataset_id="EURUSD_val_to_store_integration",
            version="v001",
            quality_score=val_result.quality_score,
            rating=val_result.rating,
        )

        assert Path(conv_result.arrow_path).exists()
        assert Path(conv_result.parquet_path).exists()
        assert conv_result.row_count == len(val_result.validated_df)

        mmap = pa.memory_map(str(conv_result.arrow_path), "r")
        table = pa.ipc.open_file(mmap).read_all()
        mmap.close()

        required = {"timestamp", "open", "high", "low", "close", "bid", "ask", "session", "quarantined"}
        missing = required - set(table.schema.names)
        assert not missing, f"Columns lost at validation→storage boundary: {missing}"


@pytest.mark.live
class TestStorageToTimeframe:
    """Boundary: Arrow Converter (1-6) → Timeframe Converter (1-7)."""

    @pytest.mark.live
    def test_arrow_output_converts_to_all_timeframes(self, tmp_path):
        """Convert to Arrow IPC, then aggregate to M5 and H1."""
        config = _setup_storage_config(_load_real_config(), tmp_path)
        logger = logging.getLogger("integration.store_to_tf")

        df = _make_realistic_df(1000)
        df["quarantined"] = False

        config["data_pipeline"]["contracts_path"] = str(CONTRACTS_PATH)
        converter = ArrowConverter(config, logger)

        conv_result = converter.convert(
            validated_df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2024, 6, 5),
            end_date=date(2024, 6, 5),
            dataset_id="EURUSD_store_to_tf_integration",
            version="v001",
            quality_score=0.95,
            rating="GREEN",
        )

        mmap = pa.memory_map(str(conv_result.arrow_path), "r")
        m1_table = pa.ipc.open_file(mmap).read_all()
        mmap.close()

        session_schedule = config.get("sessions", {})

        for target_tf, expected_ratio_range in [("M5", (4.0, 6.0)), ("H1", (50, 70))]:
            tf_table = convert_timeframe(m1_table, "M1", target_tf, session_schedule)

            assert tf_table.num_rows > 0, f"{target_tf} produced no rows"
            ratio = m1_table.num_rows / tf_table.num_rows
            lo, hi = expected_ratio_range
            assert lo <= ratio <= hi, f"M1/{target_tf} ratio {ratio:.1f} outside [{lo}, {hi}]"
            assert "session" in tf_table.schema.names, f"Session lost in {target_tf}"

            highs = tf_table.column("high").to_pylist()
            lows = tf_table.column("low").to_pylist()
            opens = tf_table.column("open").to_pylist()
            closes = tf_table.column("close").to_pylist()
            for i in range(len(highs)):
                assert highs[i] >= lows[i], f"{target_tf} bar {i}: high < low"
                assert highs[i] >= opens[i], f"{target_tf} bar {i}: high < open"
                assert highs[i] >= closes[i], f"{target_tf} bar {i}: high < close"
                assert lows[i] <= opens[i], f"{target_tf} bar {i}: low > open"
                assert lows[i] <= closes[i], f"{target_tf} bar {i}: low > close"


# ===================================================================
# CHAIN TEST — uses real pipeline artifacts, grows with each epic
# ===================================================================
#
# HOW TO EXTEND:
#   When you build a new pipeline stage (e.g. backtester in Epic 3):
#   1. Add a step below that LOADS the output from the previous stage
#   2. Runs YOUR new stage against it
#   3. Asserts on YOUR output
#   You do NOT re-download data. You do NOT re-build strategies.
#   You pick up what's already on disk.
#


@pytest.mark.live
class TestPipelineChain:
    """Full pipeline chain using real artifacts already on disk.

    This test loads existing pipeline outputs and chains forward.
    It does NOT re-download data or redo prior stages.  Each new
    epic just adds one more step.

    If no artifacts exist yet (fresh machine), the test bootstraps
    from synthetic data so it still exercises the full chain.
    """

    @pytest.mark.live
    def test_chain_data_through_all_stages(self, tmp_path):
        config = _load_real_config()
        logger = logging.getLogger("integration.chain")
        session_schedule = config.get("sessions", {})

        # --- Find existing M1 Arrow IPC, or create one ---
        storage_path = Path(config.get("data_pipeline", {}).get("storage_path", ""))
        existing = _find_arrow_files(storage_path)
        m1_files = [f for f in existing if "_M1" in f.stem and "train" not in f.stem and "test" not in f.stem]

        if m1_files:
            # USE EXISTING DATA — don't re-download
            arrow_path = m1_files[0]
            mmap = pa.memory_map(str(arrow_path), "r")
            m1_table = pa.ipc.open_file(mmap).read_all()
            mmap.close()
        else:
            # No artifacts yet — bootstrap from synthetic data
            config = _setup_storage_config(config, tmp_path)
            df = _make_realistic_df(1000)
            df["quarantined"] = False

            checker = DataQualityChecker(config, logger)
            val_result = checker.validate(
                df=df,
                pair="EURUSD",
                resolution="M1",
                start_date=date(2024, 6, 5),
                end_date=date(2024, 6, 5),
                storage_path=tmp_path,
                dataset_id="EURUSD_chain_bootstrap",
                version="v001",
            )

            config["data_pipeline"]["contracts_path"] = str(CONTRACTS_PATH)
            converter = ArrowConverter(config, logger)
            conv_result = converter.convert(
                validated_df=val_result.validated_df,
                pair="EURUSD",
                resolution="M1",
                start_date=date(2024, 6, 5),
                end_date=date(2024, 6, 5),
                dataset_id="EURUSD_chain_bootstrap",
                version="v001",
                quality_score=val_result.quality_score,
                rating=val_result.rating,
            )

            mmap = pa.memory_map(str(conv_result.arrow_path), "r")
            m1_table = pa.ipc.open_file(mmap).read_all()
            mmap.close()

        assert m1_table.num_rows > 0, "No M1 data available"

        # --- Stage: Timeframe conversion (Epic 1) ---
        m5_table = convert_timeframe(m1_table, "M1", "M5", session_schedule)
        h1_table = convert_timeframe(m1_table, "M1", "H1", session_schedule)

        assert m5_table.num_rows > 0
        assert h1_table.num_rows > 0
        assert "session" in m5_table.schema.names
        assert "session" in h1_table.schema.names
        assert m5_table.num_rows < m1_table.num_rows
        assert h1_table.num_rows < m5_table.num_rows

        # --- Stage: Data splitting (Epic 1, Story 1-8) ---
        # TODO: when data_splitter is built, add:
        #   from data_pipeline.data_splitter import split_train_test
        #   train, test, meta = split_train_test(h1_table, config)
        #   assert max(train timestamp) < min(test timestamp)
        #   assert train.num_rows + test.num_rows == h1_table.num_rows

        # --- Stage: Strategy (Epic 2) ---
        # TODO: when strategy module is built, add:
        #   from strategy import load_strategy
        #   strategy = load_strategy(config)
        #   assert strategy is not None

        # --- Stage: Backtester (Epic 3) ---
        # TODO: when backtester is built, add:
        #   from backtester import run_backtest
        #   results = run_backtest(strategy, train_data, config)
        #   assert results.trades is not None

        # Each new stage just picks up the output of the last one.
        # No re-downloading. No re-building. Just chain forward.
