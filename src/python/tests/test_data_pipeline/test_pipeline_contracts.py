"""Pipeline contract tests — schema compatibility between stages.

Fast unit tests (no network, no real data) that verify:
- Each stage's output schema is compatible with the next stage's input
- Quality report includes all computed fields
- Arrow schema has all columns the timeframe converter needs
- Type consistency across stage boundaries

Run with: pytest (no -m live needed — these are fast)
"""
import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

from data_pipeline.arrow_converter import ArrowConverter
from data_pipeline.quality_checker import DataQualityChecker
from data_pipeline.schema_loader import load_arrow_schema
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


def _make_synthetic_downloader_output(n: int = 20) -> pd.DataFrame:
    """Minimal DataFrame matching what DukascopyDownloader.download() returns."""
    rng = np.random.default_rng(99)
    timestamps = pd.date_range("2024-06-05 08:00", periods=n, freq="min", tz="UTC")
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


# ---------------------------------------------------------------------------
# Contract: Downloader (1-4) → Quality Checker (1-5)
# ---------------------------------------------------------------------------


class TestDownloaderToValidatorContract:
    """Verify downloader output has all columns the quality checker needs."""

    def test_downloader_output_has_required_columns(self):
        """Quality checker accesses specific columns — downloader must provide them."""
        df = _make_synthetic_downloader_output()

        # Columns the quality checker accesses (from quality_checker.py source)
        validator_required = {"timestamp", "bid", "ask"}

        # OHLC columns the checker uses for integrity validation
        ohlc_columns = {"open", "high", "low", "close"}

        actual = set(df.columns)
        missing_required = validator_required - actual
        missing_ohlc = ohlc_columns - actual

        assert not missing_required, f"Downloader missing validator-required columns: {missing_required}"
        assert not missing_ohlc, f"Downloader missing OHLC columns: {missing_ohlc}"

    def test_timestamp_type_compatible(self):
        """Quality checker expects datetime-like timestamps."""
        df = _make_synthetic_downloader_output()
        assert pd.api.types.is_datetime64_any_dtype(df["timestamp"]), (
            "Downloader timestamps must be datetime64 for quality checker"
        )

    def test_price_columns_are_numeric(self):
        """Quality checker does numeric comparisons on price columns."""
        df = _make_synthetic_downloader_output()
        for col in ["open", "high", "low", "close", "bid", "ask"]:
            assert pd.api.types.is_numeric_dtype(df[col]), (
                f"Column '{col}' must be numeric, got {df[col].dtype}"
            )


# ---------------------------------------------------------------------------
# Contract: Quality Checker (1-5) → Arrow Converter (1-6)
# ---------------------------------------------------------------------------


class TestValidatorToStorageContract:
    """Verify validated_df has all columns ArrowConverter expects."""

    def test_validated_df_has_quarantined_column(self, tmp_path):
        """ArrowConverter expects quarantined column from validator."""
        config = _load_real_config()
        logger = logging.getLogger("contract_test")

        df = _make_synthetic_downloader_output()
        checker = DataQualityChecker(config, logger)
        result = checker.validate(
            df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2024, 6, 5),
            end_date=date(2024, 6, 5),
            storage_path=tmp_path,
            dataset_id="contract_test",
            version="v001",
        )

        assert "quarantined" in result.validated_df.columns, (
            "Validator must add 'quarantined' column — ArrowConverter depends on it"
        )

    def test_validated_df_preserves_price_columns(self, tmp_path):
        """Validator must not drop columns that ArrowConverter needs."""
        config = _load_real_config()
        logger = logging.getLogger("contract_test")

        df = _make_synthetic_downloader_output()
        checker = DataQualityChecker(config, logger)
        result = checker.validate(
            df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2024, 6, 5),
            end_date=date(2024, 6, 5),
            storage_path=tmp_path,
            dataset_id="contract_test",
            version="v001",
        )

        # ArrowConverter needs these columns
        converter_required = {"timestamp", "open", "high", "low", "close", "bid", "ask"}
        actual = set(result.validated_df.columns)
        missing = converter_required - actual
        assert not missing, f"Validator dropped columns ArrowConverter needs: {missing}"

    def test_validated_df_row_count_preserved(self, tmp_path):
        """Validator must not silently drop rows."""
        config = _load_real_config()
        logger = logging.getLogger("contract_test")

        df = _make_synthetic_downloader_output(50)
        checker = DataQualityChecker(config, logger)
        result = checker.validate(
            df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2024, 6, 5),
            end_date=date(2024, 6, 5),
            storage_path=tmp_path,
            dataset_id="contract_test",
            version="v001",
        )

        assert len(result.validated_df) == 50, (
            f"Validator changed row count: {len(result.validated_df)} != 50"
        )


# ---------------------------------------------------------------------------
# Contract: Arrow Converter (1-6) → Timeframe Converter (1-7)
# ---------------------------------------------------------------------------


class TestStorageToTimeframeContract:
    """Verify Arrow IPC schema has all columns timeframe converter needs."""

    def test_arrow_schema_has_timeframe_required_columns(self):
        """Timeframe converter reads specific columns from Arrow tables."""
        try:
            schema = load_arrow_schema(CONTRACTS_PATH, "market_data")
        except (FileNotFoundError, KeyError):
            pytest.skip("contracts/arrow_schemas.toml not available")

        schema_columns = set(schema.names) if hasattr(schema, "names") else set()

        # Columns that convert_timeframe() accesses
        tf_required = {"timestamp", "open", "high", "low", "close", "bid", "ask", "session"}

        missing = tf_required - schema_columns
        assert not missing, (
            f"Arrow schema missing columns timeframe converter needs: {missing}"
        )

    def test_arrow_schema_timestamp_is_int64(self):
        """Timeframe converter does integer arithmetic on timestamps."""
        try:
            schema = load_arrow_schema(CONTRACTS_PATH, "market_data")
        except (FileNotFoundError, KeyError):
            pytest.skip("contracts/arrow_schemas.toml not available")

        ts_field = schema.field("timestamp")
        assert ts_field.type == pa.int64(), (
            f"Timestamp must be int64 (epoch us) for timeframe converter, got {ts_field.type}"
        )

    def test_arrow_table_accepted_by_timeframe_converter(self, tmp_path):
        """Build a minimal Arrow table from the schema and run convert_timeframe."""
        config = _load_real_config()

        # Build a small Arrow table matching the market_data schema
        n = 60  # 1 hour of M1 bars
        rng = np.random.default_rng(42)
        base = 1.1000
        prices = base + rng.standard_normal(n).cumsum() * 0.0001

        # Timestamps as epoch microseconds (what Arrow converter produces)
        start_us = 1717545600_000000  # 2024-06-05 00:00 UTC
        timestamps = [start_us + i * 60_000000 for i in range(n)]

        table = pa.table(
            {
                "timestamp": pa.array(timestamps, type=pa.int64()),
                "open": pa.array(prices, type=pa.float64()),
                "high": pa.array(prices + 0.001, type=pa.float64()),
                "low": pa.array(prices - 0.001, type=pa.float64()),
                "close": pa.array(prices + rng.standard_normal(n) * 0.0002, type=pa.float64()),
                "bid": pa.array(prices, type=pa.float64()),
                "ask": pa.array(prices + 0.0003, type=pa.float64()),
                "session": pa.array(["london"] * n, type=pa.utf8()),
                "quarantined": pa.array([False] * n, type=pa.bool_()),
            }
        )

        session_schedule = config.get("sessions", {})

        # This must not raise — if it does, the schema contract is broken
        m5_table = convert_timeframe(table, "M1", "M5", session_schedule)
        assert m5_table.num_rows > 0, "Timeframe converter rejected Arrow table from storage schema"
        assert m5_table.num_rows == 12, f"60 M1 bars should produce 12 M5 bars, got {m5_table.num_rows}"


# ---------------------------------------------------------------------------
# Contract: Quality Report completeness
# ---------------------------------------------------------------------------


class TestQualityReportContract:
    """Verify quality report JSON includes all computed fields."""

    def test_quality_report_has_gap_analysis(self, tmp_path):
        """Report must include gap analysis with penalty breakdown."""
        config = _load_real_config()
        logger = logging.getLogger("contract_test")

        df = _make_synthetic_downloader_output(100)
        checker = DataQualityChecker(config, logger)
        result = checker.validate(
            df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2024, 6, 5),
            end_date=date(2024, 6, 5),
            storage_path=tmp_path,
            dataset_id="report_contract_test",
            version="v001",
        )

        report = json.loads(result.report_path.read_text())

        # Gap analysis must feed into penalty breakdown (not be silently discarded)
        assert "penalty_breakdown" in report, "Report must include penalty_breakdown"
        assert "gap_penalty" in report["penalty_breakdown"], (
            "Gap analysis must contribute to penalty_breakdown — "
            "regression guard for gap_severity being computed then discarded"
        )
        assert "gaps" in report, "Report must include gap details"

    def test_quality_report_has_all_required_fields(self, tmp_path):
        """Quality report must include all sections for downstream decision-making."""
        config = _load_real_config()
        logger = logging.getLogger("contract_test")

        df = _make_synthetic_downloader_output(100)
        checker = DataQualityChecker(config, logger)
        result = checker.validate(
            df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2024, 6, 5),
            end_date=date(2024, 6, 5),
            storage_path=tmp_path,
            dataset_id="report_fields_test",
            version="v001",
        )

        report = json.loads(result.report_path.read_text())

        # These fields must exist for the pipeline to make proceed/halt decisions
        required_fields = {"quality_score", "rating", "penalty_breakdown"}
        actual_fields = set(report.keys())
        missing = required_fields - actual_fields
        assert not missing, f"Quality report missing required fields: {missing}"

        # Score must be a usable number
        assert isinstance(report["quality_score"], (int, float))
        assert 0.0 <= report["quality_score"] <= 1.0

        # Rating must be a known value
        assert report["rating"] in ("GREEN", "YELLOW", "RED")

        # Report must include all analysis sections
        for section in ["gaps", "integrity_issues", "stale_periods", "completeness_issues"]:
            assert section in report, f"Report missing analysis section: {section}"

    def test_validation_result_fields_consistent_with_report(self, tmp_path):
        """ValidationResult namedtuple must match the report JSON."""
        config = _load_real_config()
        logger = logging.getLogger("contract_test")

        df = _make_synthetic_downloader_output(50)
        checker = DataQualityChecker(config, logger)
        result = checker.validate(
            df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2024, 6, 5),
            end_date=date(2024, 6, 5),
            storage_path=tmp_path,
            dataset_id="consistency_test",
            version="v001",
        )

        report = json.loads(result.report_path.read_text())

        # The namedtuple and JSON report must agree on score and rating
        assert abs(result.quality_score - report["quality_score"]) < 1e-5, (
            "ValidationResult.quality_score != report JSON quality_score"
        )
        assert result.rating == report["rating"], (
            "ValidationResult.rating != report JSON rating"
        )

        # can_proceed is derived from rating — verify it's consistent
        if result.rating == "RED":
            assert result.can_proceed is False, "RED rating must mean can_proceed=False"
        elif result.rating == "GREEN":
            assert result.can_proceed is True, "GREEN rating must mean can_proceed=True"
