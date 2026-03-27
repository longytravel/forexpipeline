"""Tests for schema_loader module (Story 1.6)."""
import tempfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from data_pipeline.schema_loader import (
    SchemaValidationError,
    load_arrow_schema,
    validate_dataframe_against_schema,
)

# --- Fixtures ---

VALID_ARROW_SCHEMAS_TOML = """\
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
"""


@pytest.fixture
def contracts_dir(tmp_path):
    """Create a temp contracts dir with valid arrow_schemas.toml."""
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    (contracts / "arrow_schemas.toml").write_text(VALID_ARROW_SCHEMAS_TOML)
    return contracts


@pytest.fixture
def market_data_schema(contracts_dir):
    """Load the market_data schema from test contracts."""
    return load_arrow_schema(contracts_dir, "market_data")


def _make_valid_df(n: int = 5) -> pd.DataFrame:
    """Create a DataFrame matching the market_data schema."""
    return pd.DataFrame({
        "timestamp": pd.array([1_000_000 * i for i in range(n)], dtype="int64"),
        "open": [1.1] * n,
        "high": [1.2] * n,
        "low": [1.0] * n,
        "close": [1.15] * n,
        "bid": [1.14] * n,
        "ask": [1.16] * n,
        "session": ["asian"] * n,
        "quarantined": [False] * n,
    })


# --- Tests: load_arrow_schema ---

class TestLoadArrowSchema:
    def test_load_arrow_schema(self, contracts_dir):
        """Verify schema loads from contracts TOML and produces correct PyArrow schema."""
        schema = load_arrow_schema(contracts_dir, "market_data")
        assert isinstance(schema, pa.Schema)
        assert len(schema) == 9
        assert schema.field("timestamp").type == pa.int64()
        assert schema.field("open").type == pa.float64()
        assert schema.field("session").type == pa.utf8()
        assert schema.field("quarantined").type == pa.bool_()

    def test_schema_type_mapping(self, contracts_dir):
        """Verify each TOML type string maps to correct PyArrow type."""
        schema = load_arrow_schema(contracts_dir, "market_data")

        expected_types = {
            "timestamp": pa.int64(),
            "open": pa.float64(),
            "high": pa.float64(),
            "low": pa.float64(),
            "close": pa.float64(),
            "bid": pa.float64(),
            "ask": pa.float64(),
            "session": pa.utf8(),
            "quarantined": pa.bool_(),
        }
        for name, expected in expected_types.items():
            assert schema.field(name).type == expected, f"Type mismatch for {name}"

    def test_schema_nullable_flags(self, contracts_dir):
        """Verify nullable flags are set per contract."""
        schema = load_arrow_schema(contracts_dir, "market_data")
        for field in schema:
            assert field.nullable is False, f"{field.name} should be non-nullable"

    def test_missing_toml_file(self, tmp_path):
        """Verify FileNotFoundError when arrow_schemas.toml doesn't exist."""
        with pytest.raises(FileNotFoundError):
            load_arrow_schema(tmp_path, "market_data")

    def test_missing_schema_section(self, contracts_dir):
        """Verify KeyError for unknown schema name."""
        with pytest.raises(KeyError, match="nonexistent"):
            load_arrow_schema(contracts_dir, "nonexistent")

    def test_unknown_type_string(self, tmp_path):
        """Verify ValueError for unknown type in schema definition."""
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        (contracts / "arrow_schemas.toml").write_text(
            '[bad]\ncolumns = [{ name = "x", type = "decimal128", nullable = false }]\n'
        )
        with pytest.raises(ValueError, match="Unknown type 'decimal128'"):
            load_arrow_schema(contracts, "bad")


# --- Tests: validate_dataframe_against_schema ---

class TestValidateDataframeAgainstSchema:
    def test_validate_dataframe_matching_schema(self, market_data_schema):
        """Verify clean DataFrame passes validation."""
        df = _make_valid_df()
        result = validate_dataframe_against_schema(df, market_data_schema)
        assert result == []

    def test_validate_dataframe_missing_column(self, market_data_schema):
        """Verify mismatch detection for missing columns."""
        df = _make_valid_df().drop(columns=["session", "quarantined"])
        with pytest.raises(SchemaValidationError, match="Missing columns"):
            validate_dataframe_against_schema(df, market_data_schema)

    def test_validate_dataframe_extra_column(self, market_data_schema):
        """Verify mismatch detection for extra columns."""
        df = _make_valid_df()
        df["extra_col"] = 42
        with pytest.raises(SchemaValidationError, match="Extra columns"):
            validate_dataframe_against_schema(df, market_data_schema)

    def test_validate_dataframe_wrong_type(self, market_data_schema):
        """Verify mismatch detection for wrong types."""
        df = _make_valid_df()
        df["timestamp"] = df["timestamp"].astype(str)  # Should be int64
        with pytest.raises(SchemaValidationError, match="not compatible"):
            validate_dataframe_against_schema(df, market_data_schema)

    def test_validate_empty_schema_columns(self, tmp_path):
        """Verify ValueError for schema with no columns."""
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        (contracts / "arrow_schemas.toml").write_text(
            '[empty]\ncolumns = []\n'
        )
        with pytest.raises(ValueError, match="no columns"):
            load_arrow_schema(contracts, "empty")
