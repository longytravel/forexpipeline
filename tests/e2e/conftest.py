"""E2E test configuration and shared fixtures for Epic 2 pipeline proof."""
import json
import logging
import shutil
import sys
from pathlib import Path

import pytest

# Add src/python to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PYTHON = PROJECT_ROOT / "src" / "python"
if str(SRC_PYTHON) not in sys.path:
    sys.path.insert(0, str(SRC_PYTHON))

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def pytest_collection_modifyitems(config, items):
    """Auto-skip live/e2e tests unless explicitly requested."""
    requested = config.getoption("-m", default="")
    if requested and ("live" in requested or "e2e" in requested):
        return
    skip_marker = pytest.mark.skip(reason="E2E/live test — run with: pytest -m live")
    for item in items:
        if ("live" in item.keywords or "e2e" in item.keywords) and "regression" not in item.keywords:
            item.add_marker(skip_marker)


class StructuredLogCapture(logging.Handler):
    """Captures structured log records for E2E verification."""

    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)

    def get_ctx_events(self) -> list[dict]:
        """Extract ctx dicts from all captured records."""
        events = []
        for r in self.records:
            ctx = getattr(r, "ctx", None)
            if ctx is None and hasattr(r, "args") and isinstance(r.args, dict):
                ctx = r.args.get("ctx")
            if ctx is None:
                # Check extra dict
                extra = getattr(r, "__dict__", {})
                if "ctx" in extra:
                    ctx = extra["ctx"]
            if ctx:
                events.append(ctx)
        return events


@pytest.fixture(scope="module")
def log_capture():
    """Capture structured logs emitted during pipeline execution.

    Attaches handler to both root and all named loggers used by strategy/cost_model
    modules, since they may have propagate=False.
    """
    handler = StructuredLogCapture()
    handler.setLevel(logging.DEBUG)

    # Attach to root and all relevant named loggers
    target_loggers = [
        logging.getLogger(),  # root
        logging.getLogger("strategy"),
        logging.getLogger("strategy.intent_capture"),
        logging.getLogger("strategy.confirmer"),
        logging.getLogger("strategy.modifier"),
        logging.getLogger("strategy.reviewer"),
        logging.getLogger("cost_model"),
    ]
    for lgr in target_loggers:
        lgr.addHandler(handler)
        lgr.setLevel(logging.DEBUG)

    yield handler

    for lgr in target_loggers:
        lgr.removeHandler(handler)


@pytest.fixture(scope="module")
def e2e_workspace(tmp_path_factory):
    """Create isolated workspace for E2E pipeline proof.

    Returns dict with paths for all E2E operations.
    """
    workspace = tmp_path_factory.mktemp("e2e_proof")

    # Root artifacts dir (confirmer/modifier/cost_model use this)
    root_artifacts = workspace / "artifacts"
    root_artifacts.mkdir()

    # Strategy artifacts dir (intent_capture uses this — no "strategies" prefix)
    strategy_artifacts = root_artifacts / "strategies"
    strategy_artifacts.mkdir()

    # Config directory with base.toml
    config_dir = workspace / "config"
    config_dir.mkdir()
    env_dir = config_dir / "environments"
    env_dir.mkdir()

    real_config = PROJECT_ROOT / "config"
    if (real_config / "base.toml").exists():
        shutil.copy2(real_config / "base.toml", config_dir / "base.toml")
    real_env = real_config / "environments"
    if real_env.exists():
        for f in real_env.iterdir():
            if f.is_file():
                shutil.copy2(f, env_dir / f.name)

    # Copy cost model artifacts to workspace
    cm_src = PROJECT_ROOT / "artifacts" / "cost_models" / "EURUSD"
    cm_dest = root_artifacts / "cost_models" / "EURUSD"
    cm_dest.mkdir(parents=True)
    if cm_src.exists():
        for f in cm_src.iterdir():
            if f.is_file():
                shutil.copy2(f, cm_dest / f.name)

    # Copy strategy defaults if they exist
    defaults_src = PROJECT_ROOT / "config" / "strategies" / "defaults.toml"
    defaults_dest = None
    if defaults_src.exists():
        strat_config = config_dir / "strategies"
        strat_config.mkdir(exist_ok=True)
        shutil.copy2(defaults_src, strat_config / "defaults.toml")
        defaults_dest = strat_config / "defaults.toml"

    return {
        "workspace": workspace,
        "root_artifacts_dir": root_artifacts,
        "strategy_artifacts_dir": strategy_artifacts,
        "config_dir": config_dir,
        "contracts_dir": PROJECT_ROOT / "contracts",
        "defaults_path": defaults_dest,
        "project_root": PROJECT_ROOT,
        "fixtures_dir": FIXTURES_DIR,
    }


@pytest.fixture(scope="module")
def dialogue_input():
    """Load the canonical dialogue fixture."""
    fixture_path = FIXTURES_DIR / "ma_crossover_dialogue.json"
    with open(fixture_path, encoding="utf-8") as f:
        return json.load(f)
