"""Tests for config_loader.loader."""
import os
from pathlib import Path

import pytest
from config_loader.loader import load_config, _deep_merge


def test_load_base_config(tmp_config_dir):
    config = load_config(config_dir=tmp_config_dir)
    assert config["project"]["name"] == "test-pipeline"
    assert config["project"]["version"] == "0.1.0"
    assert config["data"]["storage_path"] == "test/data"
    assert config["sessions"]["timezone"] == "UTC"


def test_load_with_env_override(tmp_config_dir):
    config = load_config(env="local", config_dir=tmp_config_dir)
    # local.toml overrides logging.level to DEBUG
    assert config["logging"]["level"] == "DEBUG"
    # base values still present
    assert config["project"]["name"] == "test-pipeline"


def test_deep_merge():
    base = {"a": 1, "nested": {"x": 10, "y": 20}, "list": [1, 2]}
    override = {"a": 2, "nested": {"y": 99}, "list": [3]}
    result = _deep_merge(base, override)
    assert result["a"] == 2
    assert result["nested"]["x"] == 10  # preserved from base
    assert result["nested"]["y"] == 99  # overridden
    assert result["list"] == [3]  # lists overwrite, don't merge


def test_missing_base_config_fails(tmp_path):
    empty_dir = tmp_path / "empty_config"
    empty_dir.mkdir()
    with pytest.raises(SystemExit, match="base.toml not found"):
        load_config(config_dir=empty_dir)


def test_missing_env_config_uses_base(tmp_config_dir):
    config = load_config(env="nonexistent", config_dir=tmp_config_dir)
    # Should load base config without error
    assert config["project"]["name"] == "test-pipeline"
    assert config["_env"] == "nonexistent"
