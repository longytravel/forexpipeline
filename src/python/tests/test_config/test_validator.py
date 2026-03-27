"""Tests for config_loader.validator."""
import pytest
from config_loader.validator import validate_config, validate_or_die


@pytest.fixture
def schema_path(tmp_config_dir):
    return tmp_config_dir / ".." / "schema.toml"


@pytest.fixture
def tmp_schema(tmp_path):
    schema = tmp_path / "schema.toml"
    schema.write_text(
        '[schema.project.name]\ntype = "string"\nrequired = true\n\n'
        '[schema.project.version]\ntype = "string"\nrequired = true\n\n'
        '[schema.data.storage_path]\ntype = "string"\nrequired = true\n\n'
        '[schema.data.download.timeout_seconds]\ntype = "integer"\nrequired = true\nmin = 1\nmax = 300\n\n'
        '[schema.execution.mode]\ntype = "string"\nrequired = true\nallowed = ["practice", "live"]\n',
        encoding="utf-8",
    )
    return schema


def test_valid_config_passes(tmp_schema):
    config = {
        "project": {"name": "test", "version": "0.1.0"},
        "data": {"storage_path": "/tmp/data", "download": {"timeout_seconds": 30}},
        "execution": {"mode": "practice"},
    }
    errors = validate_config(config, schema_path=tmp_schema)
    assert errors == []


def test_missing_required_key_fails(tmp_schema):
    config = {
        "data": {"storage_path": "/tmp/data", "download": {"timeout_seconds": 30}},
        "execution": {"mode": "practice"},
    }
    errors = validate_config(config, schema_path=tmp_schema)
    assert any("project.name" in e for e in errors)


def test_wrong_type_fails(tmp_schema):
    config = {
        "project": {"name": 123, "version": "0.1.0"},
        "data": {"storage_path": "/tmp/data", "download": {"timeout_seconds": 30}},
        "execution": {"mode": "practice"},
    }
    errors = validate_config(config, schema_path=tmp_schema)
    assert any("Wrong type" in e and "project.name" in e for e in errors)


def test_out_of_range_fails(tmp_schema):
    config = {
        "project": {"name": "test", "version": "0.1.0"},
        "data": {"storage_path": "/tmp/data", "download": {"timeout_seconds": 999}},
        "execution": {"mode": "practice"},
    }
    errors = validate_config(config, schema_path=tmp_schema)
    assert any("too high" in e and "timeout_seconds" in e for e in errors)


def test_validate_or_die_exits(tmp_schema):
    config = {}  # Missing all required keys
    with pytest.raises(SystemExit):
        validate_or_die(config, schema_path=tmp_schema)
