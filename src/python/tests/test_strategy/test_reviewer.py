"""Tests for strategy reviewer module (Story 2.5, AC #1)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from strategy.reviewer import (
    StrategySummary,
    format_summary_text,
    generate_summary,
    save_summary_artifact,
)
from strategy.specification import StrategySpecification


def _make_spec(**overrides) -> StrategySpecification:
    """Build a minimal valid StrategySpecification for testing."""
    base = {
        "metadata": {
            "schema_version": "1",
            "name": "test-strategy",
            "version": "v001",
            "pair": "EURUSD",
            "timeframe": "H1",
            "created_by": "test",
            "status": "draft",
        },
        "entry_rules": {
            "conditions": [
                {
                    "indicator": "sma_crossover",
                    "parameters": {"fast_period": 20, "slow_period": 50},
                    "threshold": 0.0,
                    "comparator": "crosses_above",
                }
            ],
            "filters": [],
            "confirmation": [],
        },
        "exit_rules": {
            "stop_loss": {"type": "atr_multiple", "value": 1.5},
            "take_profit": {"type": "risk_reward", "value": 3.0},
        },
        "position_sizing": {
            "method": "fixed_risk",
            "risk_percent": 1.0,
            "max_lots": 1.0,
        },
    }
    # Apply overrides
    for key, val in overrides.items():
        if "." in key:
            parts = key.split(".")
            d = base
            for p in parts[:-1]:
                d = d[p]
            d[parts[-1]] = val
        else:
            base[key] = val
    return StrategySpecification.model_validate(base)


class TestGenerateSummary:
    """Tests for generate_summary()."""

    def test_summary_includes_indicators(self):
        spec = _make_spec()
        summary = generate_summary(spec)
        assert len(summary.indicators) >= 1
        # Should contain human-readable indicator name, not raw type
        assert any("SMA Crossover" in ind for ind in summary.indicators)

    def test_summary_includes_entry_logic(self):
        spec = _make_spec()
        summary = generate_summary(spec)
        assert "crosses above" in summary.entry_logic.lower()

    def test_summary_includes_exit_logic(self):
        spec = _make_spec()
        summary = generate_summary(spec)
        assert "ATR" in summary.exit_logic or "atr" in summary.exit_logic.lower()
        assert "1.5" in summary.exit_logic

    def test_summary_includes_filters(self):
        spec = _make_spec(**{
            "entry_rules": {
                "conditions": [
                    {
                        "indicator": "sma_crossover",
                        "parameters": {"fast_period": 20, "slow_period": 50},
                        "threshold": 0.0,
                        "comparator": "crosses_above",
                    }
                ],
                "filters": [
                    {"type": "session", "params": {"include": ["london"]}}
                ],
                "confirmation": [],
            }
        })
        summary = generate_summary(spec)
        assert len(summary.filters) >= 1
        assert any("London" in f for f in summary.filters)

    def test_summary_includes_position_sizing(self):
        spec = _make_spec()
        summary = generate_summary(spec)
        assert "1.0" in summary.position_sizing or "1%" in summary.position_sizing
        assert "risk" in summary.position_sizing.lower()

    def test_summary_includes_pair_timeframe(self):
        spec = _make_spec()
        summary = generate_summary(spec)
        assert summary.pair == "EURUSD"
        assert summary.timeframe == "H1"

    def test_summary_no_raw_spec_format(self):
        """Output must not contain TOML, JSON, or dict syntax."""
        spec = _make_spec()
        summary = generate_summary(spec)
        text = format_summary_text(summary)
        # No raw dict/JSON/TOML syntax
        assert "{'" not in text
        assert '{"' not in text
        assert "[metadata]" not in text
        assert "model_dump" not in text
        assert "BaseModel" not in text

    def test_summary_complex_strategy(self):
        """Bollinger + RSI + filters should render correctly."""
        spec = _make_spec(**{
            "entry_rules": {
                "conditions": [
                    {
                        "indicator": "bollinger",
                        "parameters": {"period": 20, "std_dev": 2.0},
                        "threshold": 0.0,
                        "comparator": "crosses_below",
                    }
                ],
                "filters": [
                    {"type": "session", "params": {"include": ["london"]}},
                    {
                        "type": "volatility",
                        "params": {"indicator": "atr", "period": 14},
                    },
                ],
                "confirmation": [
                    {
                        "indicator": "rsi",
                        "parameters": {"period": 14},
                        "threshold": 30.0,
                        "comparator": "<",
                    }
                ],
            }
        })
        summary = generate_summary(spec)
        assert any("Bollinger" in ind for ind in summary.indicators)
        assert any("RSI" in ind or "Relative Strength" in ind for ind in summary.indicators)
        assert len(summary.filters) == 2

    def test_summary_artifact_persisted(self, tmp_path):
        """save_summary_artifact() writes file to expected path."""
        text = "Test summary content"
        path = save_summary_artifact(text, "test-slug", "v001", tmp_path)
        assert path.exists()
        assert path.read_text() == text
        assert "reviews" in str(path)
        assert "v001_summary.txt" in path.name


class TestFormatSummaryText:
    """Tests for format_summary_text()."""

    def test_deterministic_output(self):
        """Identical summaries produce identical output."""
        spec = _make_spec()
        s1 = generate_summary(spec)
        s2 = generate_summary(spec)
        t1 = format_summary_text(s1)
        t2 = format_summary_text(s2)
        assert t1 == t2

    def test_includes_section_headers(self):
        spec = _make_spec()
        summary = generate_summary(spec)
        text = format_summary_text(summary)
        assert "Strategy Review:" in text
        assert "Indicators:" in text
        assert "Entry Logic:" in text
        assert "Exit Rules:" in text
        assert "Position Sizing:" in text
