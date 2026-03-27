"""Structured JSON logging (D6).

Produces JSONL log files with the unified schema:
  {ts, level, runtime, component, stage, strategy_id, msg, ctx}
"""
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import local

_thread_local = local()


class JsonFormatter(logging.Formatter):
    """Formats log records as JSON lines matching the Architecture D6 schema."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc)
        ts_str = ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"

        component = getattr(record, "component", record.name)
        stage = getattr(record, "stage", getattr(_thread_local, "stage", None))
        strategy_id = getattr(record, "strategy_id", getattr(_thread_local, "strategy_id", None))
        ctx = getattr(record, "ctx", {})

        log_entry = {
            "ts": ts_str,
            "level": record.levelname,
            "runtime": "python",
            "component": component,
            "stage": stage,
            "strategy_id": strategy_id,
            "msg": record.getMessage(),
            "ctx": ctx,
        }
        return json.dumps(log_entry, default=str)


class _ComponentLogger(logging.LoggerAdapter):
    """Logger adapter that embeds a component name in every log line."""

    def process(self, msg, kwargs):
        extra = kwargs.get("extra", {})
        extra["component"] = self.extra["component"]
        kwargs["extra"] = extra
        return msg, kwargs


def setup_logging(config: dict) -> None:
    """Configure structured JSON logging from config.

    Creates log directory, sets up file handler with JsonFormatter,
    and configures root logger.
    """
    log_config = config.get("logging", {})
    log_dir = Path(log_config.get("log_dir", "logs"))
    level_str = log_config.get("level", "INFO")

    log_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = log_dir / f"python_{today}.jsonl"

    root = logging.getLogger()
    root.setLevel(getattr(logging, level_str, logging.INFO))

    # Avoid duplicate handlers on repeated calls
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setFormatter(JsonFormatter())
    root.addHandler(file_handler)


def get_logger(component: str) -> logging.LoggerAdapter:
    """Return a logger pre-configured with the component name."""
    base_logger = logging.getLogger(component)
    return _ComponentLogger(base_logger, {"component": component})


@contextmanager
def LogContext(stage: str | None = None, strategy_id: str | None = None):
    """Context manager to set stage and strategy_id on a block of code."""
    old_stage = getattr(_thread_local, "stage", None)
    old_strategy_id = getattr(_thread_local, "strategy_id", None)
    if stage is not None:
        _thread_local.stage = stage
    if strategy_id is not None:
        _thread_local.strategy_id = strategy_id
    try:
        yield
    finally:
        _thread_local.stage = old_stage
        _thread_local.strategy_id = old_strategy_id
