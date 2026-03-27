"""Tests for strategy specification storage and versioning (AC #6, #7)."""

import tomllib
from pathlib import Path

import pytest

from strategy.indicator_registry import reset_registry
from strategy.loader import load_strategy_spec
from strategy.storage import (
    is_version_immutable,
    list_versions,
    load_latest_version,
    save_strategy_spec,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _clear_registry():
    reset_registry()
    yield
    reset_registry()


@pytest.fixture
def strategy_dir(tmp_path):
    """Provide a temporary strategy directory."""
    d = tmp_path / "strategies" / "test-strategy"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def valid_spec():
    """Load the valid MA crossover fixture."""
    return load_strategy_spec(FIXTURES / "valid_ma_crossover.toml")


def test_save_creates_v001_first_time(strategy_dir, valid_spec):
    """First save -> v001.toml."""
    path = save_strategy_spec(valid_spec, strategy_dir)
    assert path.name == "v001.toml"
    assert path.exists()

    # Verify file content is valid TOML
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    assert raw["metadata"]["name"] == "ma-crossover"


def test_save_increments_version(strategy_dir, valid_spec):
    """Second save -> v002.toml."""
    p1 = save_strategy_spec(valid_spec, strategy_dir)
    p2 = save_strategy_spec(valid_spec, strategy_dir)
    assert p1.name == "v001.toml"
    assert p2.name == "v002.toml"
    assert p2.exists()


def test_previous_versions_immutable(strategy_dir, valid_spec):
    """v001 unchanged after v002 save."""
    p1 = save_strategy_spec(valid_spec, strategy_dir)
    content1 = p1.read_text(encoding="utf-8")

    save_strategy_spec(valid_spec, strategy_dir)

    content1_after = p1.read_text(encoding="utf-8")
    assert content1 == content1_after


def test_load_latest_version(strategy_dir, valid_spec):
    """Returns highest version."""
    save_strategy_spec(valid_spec, strategy_dir)
    save_strategy_spec(valid_spec, strategy_dir)
    save_strategy_spec(valid_spec, strategy_dir)

    spec, version = load_latest_version(strategy_dir)
    assert version == "v003"
    assert spec.metadata.name == "ma-crossover"


def test_list_versions_ordered(strategy_dir, valid_spec):
    """Returns sorted list."""
    save_strategy_spec(valid_spec, strategy_dir)
    save_strategy_spec(valid_spec, strategy_dir)
    save_strategy_spec(valid_spec, strategy_dir)

    versions = list_versions(strategy_dir)
    assert versions == ["v001", "v002", "v003"]


def test_list_versions_empty_dir(tmp_path):
    """Empty dir returns empty list."""
    assert list_versions(tmp_path) == []


def test_list_versions_nonexistent_dir(tmp_path):
    """Nonexistent dir returns empty list."""
    assert list_versions(tmp_path / "nonexistent") == []


def test_is_version_immutable(strategy_dir, valid_spec):
    """Saved version is immutable (exists)."""
    save_strategy_spec(valid_spec, strategy_dir)
    assert is_version_immutable(strategy_dir, "v001") is True
    assert is_version_immutable(strategy_dir, "v999") is False


def test_load_latest_version_no_versions(tmp_path):
    """No versions -> FileNotFoundError."""
    d = tmp_path / "empty-strategy"
    d.mkdir()
    with pytest.raises(FileNotFoundError, match="No specification versions"):
        load_latest_version(d)


def test_crash_safe_write_partial_cleanup(strategy_dir, valid_spec):
    """Leftover .partial file cleaned on next save."""
    # Create a fake .partial file
    partial = strategy_dir / "v001.toml.partial"
    partial.write_text("garbage", encoding="utf-8")

    # Save should clean it up
    path = save_strategy_spec(valid_spec, strategy_dir)
    assert path.name == "v001.toml"
    assert not partial.exists()
