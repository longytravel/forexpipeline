"""Arrow schema loader from contracts (Story 1.6).

Loads Arrow IPC schemas from contracts/arrow_schemas.toml and validates
DataFrames against them. The contracts directory is the single source of
truth for cross-runtime type definitions.
"""
import tomllib
from pathlib import Path
from typing import List

import pyarrow as pa


class SchemaValidationError(Exception):
    """Raised when a DataFrame does not match the expected Arrow schema."""


# Map TOML type strings to PyArrow types
_TYPE_MAP = {
    "int64": pa.int64(),
    "float64": pa.float64(),
    "utf8": pa.utf8(),
    "bool": pa.bool_(),
}


def load_arrow_schema(contracts_path: Path, schema_name: str = "market_data") -> pa.Schema:
    """Load an Arrow schema from contracts/arrow_schemas.toml.

    Args:
        contracts_path: Path to the contracts/ directory.
        schema_name: Section name in arrow_schemas.toml (e.g. "market_data").

    Returns:
        A pyarrow.Schema matching the contract definition.

    Raises:
        FileNotFoundError: If arrow_schemas.toml does not exist.
        KeyError: If schema_name section is not found in the TOML.
        ValueError: If an unknown type string is encountered.
    """
    toml_path = contracts_path / "arrow_schemas.toml"
    if not toml_path.exists():
        raise FileNotFoundError(f"Arrow schema contract not found: {toml_path}")

    with open(toml_path, "rb") as f:
        schemas = tomllib.load(f)

    if schema_name not in schemas:
        raise KeyError(
            f"Schema '{schema_name}' not found in {toml_path}. "
            f"Available: {list(schemas.keys())}"
        )

    section = schemas[schema_name]
    columns = section.get("columns", [])
    if not columns:
        raise ValueError(f"Schema '{schema_name}' has no columns defined")

    fields = []
    for col in columns:
        name = col["name"]
        type_str = col["type"]
        nullable = col.get("nullable", True)

        if type_str not in _TYPE_MAP:
            raise ValueError(
                f"Unknown type '{type_str}' for column '{name}'. "
                f"Supported: {list(_TYPE_MAP.keys())}"
            )

        pa_type = _TYPE_MAP[type_str]
        fields.append(pa.field(name, pa_type, nullable=nullable))

    return pa.schema(fields)


def load_allowed_values(
    contracts_path: Path, schema_name: str, column_name: str
) -> frozenset[str]:
    """Load allowed enum values for a column from contracts/arrow_schemas.toml.

    Args:
        contracts_path: Path to the contracts/ directory.
        schema_name: Section name (e.g. "market_data").
        column_name: Column name whose "values" list to load.

    Returns:
        Frozenset of allowed string values.

    Raises:
        FileNotFoundError: If arrow_schemas.toml does not exist.
        KeyError: If schema or column not found, or column has no values.
    """
    toml_path = contracts_path / "arrow_schemas.toml"
    if not toml_path.exists():
        raise FileNotFoundError(f"Arrow schema contract not found: {toml_path}")

    with open(toml_path, "rb") as f:
        schemas = tomllib.load(f)

    if schema_name not in schemas:
        raise KeyError(f"Schema '{schema_name}' not found in {toml_path}")

    columns = schemas[schema_name].get("columns", [])
    for col in columns:
        if col["name"] == column_name:
            values = col.get("values")
            if values is None:
                raise KeyError(
                    f"Column '{column_name}' in schema '{schema_name}' "
                    f"has no 'values' list defined"
                )
            return frozenset(values)

    raise KeyError(
        f"Column '{column_name}' not found in schema '{schema_name}'"
    )


def validate_dataframe_against_schema(
    df, schema: pa.Schema
) -> List[str]:
    """Validate that a DataFrame matches the expected Arrow schema.

    Checks column names and type compatibility. Returns a list of
    mismatch descriptions. Empty list means valid.

    Raises:
        SchemaValidationError: If any mismatches are found (fail loud).
    """
    mismatches: List[str] = []

    schema_cols = {f.name for f in schema}
    df_cols = set(df.columns)

    # Check for missing columns
    missing = schema_cols - df_cols
    if missing:
        mismatches.append(f"Missing columns: {sorted(missing)}")

    # Check for extra columns
    extra = df_cols - schema_cols
    if extra:
        mismatches.append(f"Extra columns not in schema: {sorted(extra)}")

    # Check type compatibility for present columns
    for field in schema:
        if field.name not in df_cols:
            continue
        col_dtype = str(df[field.name].dtype)
        expected_type = field.type

        if not _is_type_compatible(col_dtype, expected_type):
            mismatches.append(
                f"Column '{field.name}': dtype '{col_dtype}' "
                f"not compatible with Arrow type '{expected_type}'"
            )

    if mismatches:
        msg = "Schema validation failed:\n" + "\n".join(f"  - {m}" for m in mismatches)
        raise SchemaValidationError(msg)

    return mismatches


def _is_type_compatible(pandas_dtype: str, arrow_type: pa.DataType) -> bool:
    """Check if a pandas dtype is compatible with an Arrow type."""
    if arrow_type == pa.int64():
        return pandas_dtype in ("int64", "Int64")
    elif arrow_type == pa.float64():
        return pandas_dtype in ("float64", "Float64")
    elif arrow_type == pa.utf8():
        return pandas_dtype in ("object", "string", "str")
    elif arrow_type == pa.bool_():
        return pandas_dtype in ("bool", "boolean")
    return False
