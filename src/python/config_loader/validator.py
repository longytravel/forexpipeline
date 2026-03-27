"""Config schema validator (D7).

Validates a config dict against config/schema.toml definitions.
Fails loud at startup on invalid config.
"""
import sys
import tomllib
from pathlib import Path


_TYPE_CHECKERS = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "table": lambda v: isinstance(v, dict),
}


def _get_nested(d: dict, dotted_key: str):
    """Traverse a dict by dotted key path. Returns (value, True) or (None, False)."""
    parts = dotted_key.split(".")
    current = d
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None, False
        current = current[part]
    return current, True


def validate_config(config: dict, schema_path: str | Path = "config/schema.toml") -> list[str]:
    """Validate config dict against schema. Returns list of error strings (empty = valid)."""
    schema_path = Path(schema_path)
    if not schema_path.is_absolute():
        # Try to find relative to CWD or walking up
        for parent in [Path.cwd(), *Path.cwd().parents]:
            candidate = parent / schema_path
            if candidate.exists():
                schema_path = candidate
                break

    if not schema_path.exists():
        return [f"Schema file not found: {schema_path}"]

    with open(schema_path, "rb") as f:
        schema_doc = tomllib.load(f)

    schema_entries = schema_doc.get("schema", {})
    errors = []

    def walk_schema(entries: dict, prefix: str = ""):
        for key, rule in entries.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(rule, dict) and "type" not in rule:
                # Nested grouping, recurse
                walk_schema(rule, full_key)
                continue

            if not isinstance(rule, dict):
                continue

            value, found = _get_nested(config, full_key)

            # Required check
            if rule.get("required", False) and not found:
                errors.append(f"Missing required key: {full_key}")
                continue

            if not found:
                continue

            # Type for "table" means we just check it's a dict — session sub-tables are okay
            expected_type = rule.get("type")
            if expected_type == "table":
                if not isinstance(value, dict):
                    errors.append(f"Wrong type for {full_key}: expected table, got {type(value).__name__}")
                continue

            # Type check
            if expected_type and expected_type in _TYPE_CHECKERS:
                if not _TYPE_CHECKERS[expected_type](value):
                    errors.append(
                        f"Wrong type for {full_key}: expected {expected_type}, got {type(value).__name__}"
                    )
                    continue

            # Allowed values
            allowed = rule.get("allowed")
            if allowed is not None and value not in allowed:
                errors.append(f"Invalid value for {full_key}: {value!r} not in {allowed}")

            # Min/max for numbers
            min_val = rule.get("min")
            max_val = rule.get("max")
            if min_val is not None and isinstance(value, (int, float)) and value < min_val:
                errors.append(f"Value too low for {full_key}: {value} < {min_val}")
            if max_val is not None and isinstance(value, (int, float)) and value > max_val:
                errors.append(f"Value too high for {full_key}: {value} > {max_val}")

    walk_schema(schema_entries)
    return errors


def validate_or_die(config: dict, schema_path: str | Path = "config/schema.toml") -> None:
    """Validate config and exit(1) with clear message on failure (D7: fail loud at startup)."""
    errors = validate_config(config, schema_path)
    if errors:
        sys.stderr.write("Config validation failed at startup:\n")
        for err in errors:
            sys.stderr.write(f"  - {err}\n")
        raise SystemExit(1)
