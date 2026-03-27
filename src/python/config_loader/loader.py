"""Layered TOML config loader (D7).

Loads base.toml, deep-merges environment overlay, returns frozen dict.
"""
import os
import sys
import tomllib
from pathlib import Path


def _find_config_dir() -> Path:
    """Walk up from CWD to find the config/ directory."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        candidate = parent / "config"
        if candidate.is_dir() and (candidate / "base.toml").exists():
            return candidate
    raise SystemExit("Config validation failed at startup: cannot locate config/base.toml")


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge override into base. Nested dicts merge recursively; scalars and lists overwrite."""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(env: str | None = None, config_dir: Path | None = None) -> dict:
    """Load layered TOML config.

    1. Load config/base.toml
    2. Determine environment (param > env var > "local")
    3. Deep-merge config/environments/{env}.toml over base
    4. Store resolved env name in config["_env"]
    """
    if config_dir is None:
        config_dir = _find_config_dir()

    base_path = config_dir / "base.toml"
    if not base_path.exists():
        raise SystemExit(f"Config validation failed at startup: {base_path} not found")

    with open(base_path, "rb") as f:
        config = tomllib.load(f)

    resolved_env = env or os.environ.get("FOREX_PIPELINE_ENV", "local")

    env_path = config_dir / "environments" / f"{resolved_env}.toml"
    if env_path.exists():
        with open(env_path, "rb") as f:
            env_config = tomllib.load(f)
        config = _deep_merge(config, env_config)

    config["_env"] = resolved_env
    return config
