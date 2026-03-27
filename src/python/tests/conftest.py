"""Shared test fixtures for forex-pipeline."""
import os
import tempfile
from pathlib import Path

import pytest


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests marked @pytest.mark.live unless -m live is passed."""
    if config.getoption("-m") and "live" in config.getoption("-m"):
        return  # User explicitly requested live tests
    skip_live = pytest.mark.skip(reason="Live test — run with: pytest -m live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture
def tmp_config_dir(tmp_path):
    """Create a temporary directory with base.toml and environment files."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    env_dir = config_dir / "environments"
    env_dir.mkdir()

    base_toml = config_dir / "base.toml"
    base_toml.write_text(
        '[project]\nname = "test-pipeline"\nversion = "0.1.0"\n\n'
        '[data]\nstorage_path = "test/data"\ndefault_pair = "EURUSD"\n'
        'default_timeframe = "M1"\nsupported_timeframes = ["M1", "M5", "H1", "D1", "W"]\n\n'
        '[data.download]\nsource = "dukascopy"\ntimeout_seconds = 30\n'
        'max_retries = 3\nretry_delay_seconds = 5\n\n'
        '[data.quality]\ngap_threshold_bars = 5\ngap_warning_per_year = 10\n'
        'gap_error_per_year = 50\ngap_error_minutes = 30\n'
        'spread_multiplier_threshold = 10.0\nstale_consecutive_bars = 5\n'
        'score_green_threshold = 0.95\nscore_yellow_threshold = 0.80\n\n'
        '[sessions]\ntimezone = "UTC"\n\n'
        '[sessions.asian]\nstart = "00:00"\nend = "08:00"\nlabel = "Asian"\n\n'
        '[sessions.london]\nstart = "08:00"\nend = "16:00"\nlabel = "London"\n\n'
        '[sessions.new_york]\nstart = "13:00"\nend = "21:00"\nlabel = "New York"\n\n'
        '[sessions.london_ny_overlap]\nstart = "13:00"\nend = "16:00"\nlabel = "London/NY Overlap"\n\n'
        '[sessions.off_hours]\nstart = "21:00"\nend = "00:00"\nlabel = "Off Hours"\n\n'
        '[logging]\nlevel = "INFO"\nlog_dir = "logs"\nmax_file_size_mb = 50\nretention_days = 30\n\n'
        '[pipeline]\nartifacts_dir = "artifacts"\ncheckpoint_enabled = true\n\n'
        '[monitoring]\nheartbeat_interval_ms = 5000\nalert_on_disconnect = true\n\n'
        '[data_pipeline]\nstorage_path = "test/data"\ndefault_resolution = "M1"\n'
        'request_delay_seconds = 0.5\n'
        'max_retries = 3\n\n'
        '[data_pipeline.download]\npairs = ["EURUSD"]\nstart_date = "2015-01-01"\n'
        'end_date = "2025-12-31"\nresolution = "M1"\n\n'
        '[execution]\nenabled = false\nmode = "practice"\n',
        encoding="utf-8",
    )

    local_toml = env_dir / "local.toml"
    local_toml.write_text(
        '[execution]\nenabled = false\nmode = "practice"\n\n'
        '[logging]\nlevel = "DEBUG"\n',
        encoding="utf-8",
    )

    return config_dir


@pytest.fixture
def sample_config():
    """Return a valid config dict matching base.toml structure."""
    return {
        "project": {"name": "test-pipeline", "version": "0.1.0"},
        "data": {
            "storage_path": "test/data",
            "default_pair": "EURUSD",
            "default_timeframe": "M1",
            "supported_timeframes": ["M1", "M5", "H1", "D1", "W"],
            "download": {
                "source": "dukascopy",
                "timeout_seconds": 30,
                "max_retries": 3,
                "retry_delay_seconds": 5,
            },
            "quality": {
                "gap_threshold_bars": 5,
                "gap_warning_per_year": 10,
                "gap_error_per_year": 50,
                "gap_error_minutes": 30,
                "spread_multiplier_threshold": 10.0,
                "stale_consecutive_bars": 5,
                "score_green_threshold": 0.95,
                "score_yellow_threshold": 0.80,
            },
        },
        "sessions": {
            "timezone": "UTC",
            "asian": {"start": "00:00", "end": "08:00", "label": "Asian"},
            "london": {"start": "08:00", "end": "16:00", "label": "London"},
            "new_york": {"start": "13:00", "end": "21:00", "label": "New York"},
            "london_ny_overlap": {"start": "13:00", "end": "16:00", "label": "London/NY Overlap"},
            "off_hours": {"start": "21:00", "end": "00:00", "label": "Off Hours"},
        },
        "logging": {
            "level": "INFO",
            "log_dir": "logs",
            "max_file_size_mb": 50,
            "retention_days": 30,
        },
        "pipeline": {"artifacts_dir": "artifacts", "checkpoint_enabled": True},
        "monitoring": {"heartbeat_interval_ms": 5000, "alert_on_disconnect": True},
        "data_pipeline": {
            "storage_path": "test/data",
            "default_resolution": "M1",
            "request_delay_seconds": 0.5,
            "max_retries": 3,
            "download": {
                "pairs": ["EURUSD"],
                "start_date": "2015-01-01",
                "end_date": "2025-12-31",
                "resolution": "M1",
            },
        },
        "execution": {"enabled": False, "mode": "practice"},
    }
