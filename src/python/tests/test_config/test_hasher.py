"""Tests for config_loader.hasher."""
from config_loader.hasher import compute_config_hash


def test_same_config_same_hash():
    config = {"a": 1, "b": {"c": 2}}
    hash1 = compute_config_hash(config)
    hash2 = compute_config_hash(config)
    assert hash1 == hash2


def test_different_config_different_hash():
    config1 = {"a": 1, "b": {"c": 2}}
    config2 = {"a": 1, "b": {"c": 3}}
    assert compute_config_hash(config1) != compute_config_hash(config2)


def test_key_order_independent():
    config1 = {"a": 1, "b": 2, "c": 3}
    config2 = {"c": 3, "a": 1, "b": 2}
    assert compute_config_hash(config1) == compute_config_hash(config2)


def test_internal_keys_stripped():
    config_with_env = {"a": 1, "_env": "local"}
    config_without_env = {"a": 1}
    assert compute_config_hash(config_with_env) == compute_config_hash(config_without_env)
