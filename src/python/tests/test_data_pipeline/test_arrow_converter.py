"""Tests for arrow_converter module (Story 1.6)."""
import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.ipc
import pytest

from data_pipeline.arrow_converter import (
    ArrowConverter,
    ConversionResult,
)
from data_pipeline.schema_loader import (
    SchemaValidationError,
    load_allowed_values,
    load_arrow_schema,
)

# --- Fixtures ---

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
  { name = "session", type = "utf8", nullable = false, values = ["asian", "london", "new_york", "london_ny_overlap", "off_hours", "mixed"] },
  { name = "quarantined", type = "bool", nullable = false },
]
"""

SESSION_SCHEMA_TOML = """\
[session_column]
name = "session"
type = "utf8"
nullable = false
values = ["asian", "london", "new_york", "london_ny_overlap", "off_hours"]
"""


def _make_config(tmp_path):
    """Create a test config dict with storage paths pointing to tmp_path."""
    return {
        "data": {"storage_path": str(tmp_path)},
        "data_pipeline": {
            "storage_path": str(tmp_path),
            "storage": {
                "arrow_ipc_path": str(tmp_path / "arrow"),
                "parquet_path": str(tmp_path / "parquet"),
            },
            "parquet": {"compression": "snappy"},
            "download": {
                "pairs": ["EURUSD"],
                "resolution": "M1",
                "start_date": "2020-01-01",
                "end_date": "2020-12-31",
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


def _make_contracts(tmp_path):
    """Create test contracts directory."""
    contracts = tmp_path / "contracts"
    contracts.mkdir(exist_ok=True)
    (contracts / "arrow_schemas.toml").write_text(ARROW_SCHEMAS_TOML)
    (contracts / "session_schema.toml").write_text(SESSION_SCHEMA_TOML)
    return contracts


def _make_validated_df(n: int = 100, with_session: bool = True) -> pd.DataFrame:
    """Create a test DataFrame simulating validated data from Story 1.5."""
    timestamps = pd.date_range("2020-06-01", periods=n, freq="min", tz="UTC")
    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": [1.1000 + i * 0.0001 for i in range(n)],
        "high": [1.1050 + i * 0.0001 for i in range(n)],
        "low": [1.0950 + i * 0.0001 for i in range(n)],
        "close": [1.1010 + i * 0.0001 for i in range(n)],
        "bid": [1.1000 + i * 0.0001 for i in range(n)],
        "ask": [1.1020 + i * 0.0001 for i in range(n)],
        "quarantined": [False] * n,
    })
    if with_session:
        df["session"] = "asian"  # All timestamps are 00:xx UTC
    return df


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """Full test setup: config, contracts, converter."""
    import data_pipeline.arrow_converter as ac_mod
    ac_mod._VALID_SESSIONS_CACHE = None  # Clear cache between tests
    config = _make_config(tmp_path)
    contracts = _make_contracts(tmp_path)
    config["data_pipeline"]["contracts_path"] = str(contracts)
    logger = logging.getLogger("test_arrow_converter")
    converter = ArrowConverter(config, logger)
    schema = load_arrow_schema(contracts, "market_data")
    return converter, config, contracts, schema, tmp_path


# --- Tests: Timestamp conversion (Task 3) ---

class TestTimestampConversion:
    def test_convert_timestamps_to_epoch_micros(self):
        """Verify conversion with known values."""
        # 2026-01-01T00:00:00Z = 1767225600 seconds = 1767225600000000 microseconds
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2026-01-01T00:00:00Z", "2020-06-15T12:30:00Z"])
        })
        result = ArrowConverter._convert_timestamps_to_epoch_micros(df)
        assert result.dtype == "int64"
        # 2026-01-01T00:00:00Z
        assert result.iloc[0] == 1767225600_000_000
        # 2020-06-15T12:30:00Z
        assert result.iloc[1] == 1592224200_000_000

    def test_epoch_micros_no_overflow(self):
        """Verify no overflow for expected date range (1970-2100)."""
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["1970-01-01T00:00:00Z", "2099-12-31T23:59:59Z"])
        })
        result = ArrowConverter._convert_timestamps_to_epoch_micros(df)
        assert result.iloc[0] == 0
        assert result.iloc[1] > 0  # Should be a large positive int64


# --- Tests: Session column stamping (Task 2) ---

class TestSessionStamping:
    def test_session_column_stamping(self, setup):
        """Verify session assignment produces correct values."""
        converter, *_ = setup
        # Create df WITHOUT session column, various timestamps
        timestamps = [
            "2020-06-01T02:00:00Z",  # 02:00 → asian
            "2020-06-01T10:00:00Z",  # 10:00 → london
            "2020-06-01T14:00:00Z",  # 14:00 → london_ny_overlap
            "2020-06-01T18:00:00Z",  # 18:00 → new_york
            "2020-06-01T22:00:00Z",  # 22:00 → off_hours
        ]
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(timestamps),
            "open": [1.1] * 5,
            "high": [1.2] * 5,
            "low": [1.0] * 5,
            "close": [1.15] * 5,
            "bid": [1.14] * 5,
            "ask": [1.16] * 5,
            "quarantined": [False] * 5,
        })
        result = converter._ensure_session_column(df)
        assert result["session"].iloc[0] == "asian"
        assert result["session"].iloc[1] == "london"
        assert result["session"].iloc[2] == "london_ny_overlap"
        assert result["session"].iloc[3] == "new_york"
        assert result["session"].iloc[4] == "off_hours"

    def test_session_overlap_handling(self, setup):
        """Verify 13:00-16:00 UTC produces london_ny_overlap."""
        converter, *_ = setup
        timestamps = pd.to_datetime([
            "2020-06-01T13:00:00Z",
            "2020-06-01T14:30:00Z",
            "2020-06-01T15:59:00Z",
        ])
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": [1.1] * 3,
            "high": [1.2] * 3,
            "low": [1.0] * 3,
            "close": [1.15] * 3,
            "bid": [1.14] * 3,
            "ask": [1.16] * 3,
            "quarantined": [False] * 3,
        })
        result = converter._ensure_session_column(df)
        for i in range(3):
            assert result["session"].iloc[i] == "london_ny_overlap"

    def test_existing_session_validation(self, setup):
        """Verify existing valid session column is accepted."""
        converter, *_ = setup
        df = _make_validated_df(5, with_session=True)
        result = converter._ensure_session_column(df)
        assert "session" in result.columns

    def test_invalid_session_value_rejected(self, setup):
        """Verify invalid session values raise ValueError."""
        converter, *_ = setup
        df = _make_validated_df(5, with_session=True)
        df.loc[0, "session"] = "invalid_session"
        with pytest.raises(ValueError, match="Invalid session values"):
            converter._ensure_session_column(df)

    def test_session_schema_validation(self, setup):
        """Verify session values are validated against contract set."""
        converter, *_ = setup
        df = _make_validated_df(5, with_session=True)
        # All "asian" — valid
        result = converter._ensure_session_column(df)
        unique = set(result["session"].unique())
        contracts_path = Path(__file__).resolve().parents[3] / "contracts"
        if contracts_path.exists():
            valid_sessions = load_allowed_values(contracts_path, "market_data", "session")
        else:
            valid_sessions = frozenset(["asian", "london", "new_york", "london_ny_overlap", "off_hours", "mixed"])
        assert unique.issubset(valid_sessions)


# --- Tests: Arrow Table construction (Task 4) ---

class TestArrowTable:
    def test_arrow_table_schema_exact_match(self, setup):
        """Verify constructed table schema matches contract exactly."""
        converter, _, contracts, schema, _ = setup
        df = _make_validated_df(10)
        table = converter._prepare_arrow_table(df, schema)
        assert table.schema.remove_metadata() == schema

    def test_arrow_table_column_count(self, setup):
        """Verify table has exact number of columns from schema."""
        converter, _, _, schema, _ = setup
        df = _make_validated_df(10)
        table = converter._prepare_arrow_table(df, schema)
        assert table.num_columns == len(schema)

    def test_arrow_table_timestamp_is_int64(self, setup):
        """Verify timestamp column is int64 epoch microseconds."""
        converter, _, _, schema, _ = setup
        df = _make_validated_df(10)
        table = converter._prepare_arrow_table(df, schema)
        assert table.column("timestamp").type == pa.int64()


# --- Tests: Arrow IPC write/read (Task 4) ---

class TestArrowIPC:
    def test_write_arrow_ipc_mmap(self, setup):
        """Write Arrow IPC, reopen via mmap, verify data integrity."""
        converter, _, _, schema, tmp_path = setup
        df = _make_validated_df(50)
        table = converter._prepare_arrow_table(df, schema)

        out_path = tmp_path / "test.arrow"
        converter._write_arrow_ipc(table, out_path)

        assert out_path.exists()
        assert out_path.stat().st_size > 0

        # Verify mmap access works
        mmap = pa.memory_map(str(out_path), "r")
        reader = pa.ipc.open_file(mmap)
        read_table = reader.read_all()
        mmap.close()

        assert read_table.num_rows == 50
        assert read_table.schema.remove_metadata() == schema

    def test_write_arrow_ipc_crash_safe(self, setup):
        """Verify .partial → rename pattern (no .partial left after write)."""
        converter, _, _, schema, tmp_path = setup
        df = _make_validated_df(10)
        table = converter._prepare_arrow_table(df, schema)

        out_path = tmp_path / "safe.arrow"
        converter._write_arrow_ipc(table, out_path)

        # .partial file should NOT exist after successful write
        partial = out_path.with_name(out_path.name + ".partial")
        assert not partial.exists()
        assert out_path.exists()

    def test_verify_arrow_ipc(self, setup):
        """Verify the verification method works on valid files."""
        converter, _, _, schema, tmp_path = setup
        df = _make_validated_df(20)
        table = converter._prepare_arrow_table(df, schema)

        out_path = tmp_path / "verify.arrow"
        converter._write_arrow_ipc(table, out_path)

        assert converter._verify_arrow_ipc(out_path, schema, expected_rows=20)


# --- Tests: Data hash (Task 8) ---

class TestDataHash:
    def test_data_hash_determinism(self, setup):
        """Same input produces identical hash across two runs."""
        converter, _, _, schema, _ = setup
        df = _make_validated_df(20)
        table = converter._prepare_arrow_table(df, schema)

        hash1 = ArrowConverter._compute_data_hash(table)
        hash2 = ArrowConverter._compute_data_hash(table)
        assert hash1 == hash2
        assert hash1.startswith("sha256:")

    def test_session_schedule_hash(self, setup):
        converter, *_ = setup
        schedule = {
            "asian": {"start": "00:00", "end": "08:00"},
            "london": {"start": "08:00", "end": "16:00"},
        }
        h1 = ArrowConverter._compute_session_schedule_hash(schedule)
        h2 = ArrowConverter._compute_session_schedule_hash(schedule)
        assert h1 == h2
        assert h1.startswith("sha256:")


# --- Tests: Full conversion pipeline (Task 6) ---

class TestFullConversion:
    def test_full_conversion_pipeline(self, setup):
        """Run full conversion on test fixture, verify both outputs."""
        converter, config, _, _, tmp_path = setup
        df = _make_validated_df(100)

        result = converter.convert(
            validated_df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2020, 1, 1),
            end_date=date(2020, 12, 31),
            dataset_id="EURUSD_2020-01-01_2020-12-31_M1",
            version="v001",
            quality_score=0.97,
            rating="GREEN",
        )

        assert isinstance(result, ConversionResult)
        assert result.row_count == 100
        assert Path(result.arrow_path).exists()
        assert Path(result.parquet_path).exists()
        assert Path(result.manifest_path).exists()
        assert result.arrow_size_mb > 0
        assert result.parquet_size_mb > 0

    def test_conversion_manifest_completeness(self, setup):
        """Verify manifest contains all required fields."""
        converter, _, _, _, tmp_path = setup
        df = _make_validated_df(50)

        result = converter.convert(
            validated_df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2020, 1, 1),
            end_date=date(2020, 12, 31),
            dataset_id="EURUSD_2020-01-01_2020-12-31_M1",
            version="v001",
            quality_score=0.95,
            rating="GREEN",
        )

        with open(result.manifest_path) as f:
            manifest = json.load(f)

        required_keys = {
            "dataset_id", "version", "pair", "resolution", "date_range",
            "row_count", "arrow_ipc", "parquet", "quality_score",
            "quality_rating", "data_hash", "config_hash",
            "session_schedule_hash", "conversion_timestamp",
            "quarantined_bar_count", "session_distribution",
        }
        assert required_keys.issubset(set(manifest.keys()))
        assert manifest["row_count"] == 50
        assert manifest["arrow_ipc"]["mmap_verified"] is True
        assert manifest["data_hash"].startswith("sha256:")
        assert manifest["config_hash"].startswith("sha256:")
        assert manifest["session_schedule_hash"].startswith("sha256:")

    def test_conversion_output_paths(self, setup):
        """Verify Arrow/Parquet files go to separate directories."""
        converter, _, _, _, tmp_path = setup
        df = _make_validated_df(10)

        result = converter.convert(
            validated_df=df,
            pair="EURUSD",
            resolution="M1",
            start_date=date(2020, 1, 1),
            end_date=date(2020, 12, 31),
            dataset_id="TEST_DS",
            version="v001",
            quality_score=0.9,
            rating="GREEN",
        )

        assert "arrow" in str(result.arrow_path)
        assert "parquet" in str(result.parquet_path)
        # They should be in different directories
        assert str(result.arrow_path).replace("\\", "/") != str(result.parquet_path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Regression tests — Story 1.10 PIR Remediation synthesis
# ---------------------------------------------------------------------------

class TestContractsPathResolution:
    """AC #11: contracts_path must be explicitly set in config.
    Directory walking fallback has been removed."""

    @pytest.mark.regression
    def test_raises_when_contracts_path_not_in_config(self, tmp_path):
        """Missing contracts_path must raise FileNotFoundError (no CWD walking)."""
        import data_pipeline.arrow_converter as ac_mod
        ac_mod._VALID_SESSIONS_CACHE = None

        config = _make_config(tmp_path)
        # Ensure contracts_path is NOT set
        config.get("data_pipeline", {}).pop("contracts_path", None)

        logger = logging.getLogger("test_arrow_converter")
        with pytest.raises(FileNotFoundError, match="contracts_path not set"):
            ArrowConverter(config, logger)

    @pytest.mark.regression
    def test_succeeds_when_contracts_path_set(self, tmp_path):
        """When contracts_path is explicit, initialization succeeds."""
        import data_pipeline.arrow_converter as ac_mod
        ac_mod._VALID_SESSIONS_CACHE = None

        config = _make_config(tmp_path)
        contracts = _make_contracts(tmp_path)
        config["data_pipeline"]["contracts_path"] = str(contracts)

        logger = logging.getLogger("test_arrow_converter")
        converter = ArrowConverter(config, logger)
        assert converter is not None


# --- Regression tests (review synthesis) ---


class TestRegressionStringTimestamps:
    """Regression: string timestamps from CSV deserialization must not crash.

    When converter_cli reads validated CSV via pd.read_csv() without
    parse_dates, timestamps arrive as strings (object dtype).
    _prepare_arrow_table must handle this gracefully.
    """

    @pytest.mark.regression
    def test_string_timestamps_converted_correctly(self, setup):
        """String timestamps (from CSV) are parsed and converted to int64 epoch micros."""
        converter, config, contracts, schema, tmp_path = setup

        # Simulate CSV-deserialized data: timestamps as strings, not datetime64
        df = pd.DataFrame({
            "timestamp": ["2020-06-01 00:00:00+00:00", "2020-06-01 00:01:00+00:00"],
            "open": [1.1000, 1.1001],
            "high": [1.1050, 1.1051],
            "low": [1.0950, 1.0951],
            "close": [1.1010, 1.1011],
            "bid": [1.1000, 1.1001],
            "ask": [1.1020, 1.1021],
            "session": ["asian", "asian"],
            "quarantined": [False, False],
        })

        # Verify timestamps are strings (not datetime64) — simulates pd.read_csv
        assert not pd.api.types.is_datetime64_any_dtype(df["timestamp"])
        assert not pd.api.types.is_numeric_dtype(df["timestamp"])

        # _prepare_arrow_table should handle string timestamps without raising
        table = converter._prepare_arrow_table(df, schema)

        # Verify output has int64 timestamps
        ts_col = table.column("timestamp")
        assert ts_col.type == pa.int64()
        # 2020-06-01T00:00:00Z = 1590969600 seconds = 1590969600000000 micros
        assert ts_col[0].as_py() == 1590969600_000_000
        assert ts_col[1].as_py() == 1590969660_000_000

    @pytest.mark.regression
    def test_int64_timestamps_still_work(self, setup):
        """Int64 epoch microsecond timestamps (already numeric) still convert."""
        converter, config, contracts, schema, tmp_path = setup

        df = pd.DataFrame({
            "timestamp": [1590969600_000_000, 1590969660_000_000],
            "open": [1.1000, 1.1001],
            "high": [1.1050, 1.1051],
            "low": [1.0950, 1.0951],
            "close": [1.1010, 1.1011],
            "bid": [1.1000, 1.1001],
            "ask": [1.1020, 1.1021],
            "session": ["asian", "asian"],
            "quarantined": [False, False],
        })

        table = converter._prepare_arrow_table(df, schema)
        ts_col = table.column("timestamp")
        assert ts_col.type == pa.int64()
        assert ts_col[0].as_py() == 1590969600_000_000
