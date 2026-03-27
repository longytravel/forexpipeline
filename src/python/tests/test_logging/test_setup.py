"""Tests for logging_setup.setup."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from logging_setup.setup import setup_logging, get_logger, LogContext


def test_log_output_is_json(tmp_path):
    config = {"logging": {"level": "DEBUG", "log_dir": str(tmp_path / "logs")}}
    setup_logging(config)
    logger = get_logger("test_component")
    logger.info("test message")

    log_files = list((tmp_path / "logs").glob("*.jsonl"))
    assert len(log_files) == 1

    lines = log_files[0].read_text(encoding="utf-8").strip().split("\n")
    for line in lines:
        parsed = json.loads(line)
        assert isinstance(parsed, dict)


def test_log_schema_fields(tmp_path):
    config = {"logging": {"level": "DEBUG", "log_dir": str(tmp_path / "logs")}}
    setup_logging(config)
    logger = get_logger("test_component")
    logger.info("schema test")

    log_files = list((tmp_path / "logs").glob("*.jsonl"))
    lines = log_files[0].read_text(encoding="utf-8").strip().split("\n")
    entry = json.loads(lines[-1])

    required_fields = {"ts", "level", "runtime", "component", "stage", "strategy_id", "msg", "ctx"}
    assert required_fields == set(entry.keys())


def test_log_file_created(tmp_path):
    config = {"logging": {"level": "INFO", "log_dir": str(tmp_path / "logs")}}
    setup_logging(config)
    logger = get_logger("test")
    logger.info("create check")

    log_files = list((tmp_path / "logs").glob("*.jsonl"))
    assert len(log_files) == 1
    assert "python_" in log_files[0].name


def test_log_timestamp_is_utc(tmp_path):
    config = {"logging": {"level": "DEBUG", "log_dir": str(tmp_path / "logs")}}
    setup_logging(config)
    logger = get_logger("test")
    logger.info("utc test")

    log_files = list((tmp_path / "logs").glob("*.jsonl"))
    lines = log_files[0].read_text(encoding="utf-8").strip().split("\n")
    entry = json.loads(lines[-1])

    assert entry["ts"].endswith("Z")
    # Verify it parses as a valid ISO 8601 timestamp
    ts = entry["ts"].replace("Z", "+00:00")
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None


def test_component_name_in_logs(tmp_path):
    config = {"logging": {"level": "DEBUG", "log_dir": str(tmp_path / "logs")}}
    setup_logging(config)
    logger = get_logger("my_component")
    logger.info("component test")

    log_files = list((tmp_path / "logs").glob("*.jsonl"))
    lines = log_files[0].read_text(encoding="utf-8").strip().split("\n")
    entry = json.loads(lines[-1])

    assert entry["component"] == "my_component"


def test_log_context_sets_stage(tmp_path):
    config = {"logging": {"level": "DEBUG", "log_dir": str(tmp_path / "logs")}}
    setup_logging(config)
    logger = get_logger("test")

    with LogContext(stage="data_pipeline", strategy_id="strat_001"):
        logger.info("inside context")

    logger.info("outside context")

    log_files = list((tmp_path / "logs").glob("*.jsonl"))
    lines = log_files[0].read_text(encoding="utf-8").strip().split("\n")

    inside = json.loads(lines[-2])
    outside = json.loads(lines[-1])

    assert inside["stage"] == "data_pipeline"
    assert inside["strategy_id"] == "strat_001"
    assert outside["stage"] is None
    assert outside["strategy_id"] is None
