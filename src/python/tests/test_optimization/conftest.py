"""Shared fixtures for optimization tests."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest


@pytest.fixture
def tmp_artifacts(tmp_path: Path) -> Path:
    """Temporary artifacts directory."""
    d = tmp_path / "artifacts"
    d.mkdir()
    return d


@pytest.fixture
def sample_strategy_spec() -> dict:
    """Strategy spec with flat parameter registry (schema v2)."""
    return {
        "metadata": {
            "schema_version": "1",
            "name": "test-strategy",
            "version": "v001",
            "pair": "EURUSD",
            "timeframe": "H1",
            "created_by": "test",
        },
        "optimization_plan": {
            "schema_version": 2,
            "parameters": {
                "entry.sma_fast_period": {
                    "type": "integer",
                    "min": 5,
                    "max": 50,
                    "step": 1,
                },
                "entry.sma_slow_period": {
                    "type": "integer",
                    "min": 20,
                    "max": 200,
                    "step": 1,
                },
                "exit.stop_loss_pips": {
                    "type": "continuous",
                    "min": 10.0,
                    "max": 100.0,
                },
            },
            "objective_function": "sharpe",
        },
        "entry_rules": {"conditions": []},
        "exit_rules": {"stop_loss": {"type": "fixed_pips", "value": 50.0}},
        "position_sizing": {"method": "fixed_risk", "risk_percent": 1.0, "max_lots": 1.0},
        "cost_model_reference": {"version": "v001"},
    }


@pytest.fixture
def branching_strategy_spec() -> dict:
    """Strategy spec with conditional parameters for branch testing."""
    return {
        "metadata": {
            "schema_version": "1",
            "name": "branch-test",
            "version": "v001",
            "pair": "EURUSD",
            "timeframe": "H1",
            "created_by": "test",
        },
        "optimization_plan": {
            "schema_version": 2,
            "parameters": {
                "entry.sma_period": {
                    "type": "integer",
                    "min": 5,
                    "max": 50,
                },
                "exit_type": {
                    "type": "categorical",
                    "choices": ["trailing_stop", "take_profit"],
                },
                "exit.trailing_distance": {
                    "type": "continuous",
                    "min": 10.0,
                    "max": 100.0,
                    "condition": {"parent": "exit_type", "value": "trailing_stop"},
                },
                "exit.tp_pips": {
                    "type": "continuous",
                    "min": 20.0,
                    "max": 200.0,
                    "condition": {"parent": "exit_type", "value": "take_profit"},
                },
            },
            "objective_function": "sharpe",
        },
    }


@pytest.fixture
def sample_config() -> dict:
    """Optimization config dict."""
    return {
        "optimization": {
            "batch_size": 64,
            "max_generations": 5,
            "checkpoint_interval_generations": 2,
            "cv_lambda": 1.5,
            "cv_folds": 3,
            "convergence_tolfun": 1e-3,
            "stagnation_generations": 50,
            "memory_budget_mb": 2048,
            "sobol_fraction": 0.1,
            "ucb1_exploration": 1.414,
            "portfolio": {
                "cmaes_instances": 2,
                "de_instances": 1,
                "cmaes_pop_base": 16,
                "de_pop_base": 16,
                "pop_scaling_factor": 5,
                "min_pop": 16,
            },
        },
        "pipeline": {
            "artifacts_dir": "artifacts",
            "checkpoint_enabled": True,
            "config_hash": "sha256:test",
        },
    }


@pytest.fixture
def small_market_data(tmp_path: Path) -> Path:
    """Small Arrow IPC market data file for testing."""
    n = 10000
    rng = np.random.RandomState(42)
    table = pa.table({
        "timestamp": pa.array(range(n), type=pa.int64()),
        "open": pa.array(rng.uniform(1.1, 1.2, n), type=pa.float64()),
        "high": pa.array(rng.uniform(1.2, 1.3, n), type=pa.float64()),
        "low": pa.array(rng.uniform(1.0, 1.1, n), type=pa.float64()),
        "close": pa.array(rng.uniform(1.1, 1.2, n), type=pa.float64()),
        "bid": pa.array(rng.uniform(1.1, 1.2, n), type=pa.float64()),
        "ask": pa.array(rng.uniform(1.1, 1.2, n), type=pa.float64()),
        "session": pa.array(["london"] * n, type=pa.utf8()),
        "quarantined": pa.array([False] * n, type=pa.bool_()),
    })
    path = tmp_path / "market-data.arrow"
    with pa.ipc.new_file(str(path), table.schema) as writer:
        writer.write_table(table)
    return path


@pytest.fixture
def mock_cost_model(tmp_path: Path) -> Path:
    """Mock cost model JSON file."""
    cost_model = {
        "version": "v001",
        "pair": "EURUSD",
        "sessions": {
            "london": {"spread_pips": 1.0, "slippage_pips": 0.2},
        },
    }
    path = tmp_path / "cost-model.json"
    path.write_text(json.dumps(cost_model), encoding="utf-8")
    return path
