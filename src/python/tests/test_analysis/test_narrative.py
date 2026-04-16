"""Tests for analysis.narrative — template-driven narrative generation."""
from __future__ import annotations

import sqlite3

import pytest

from analysis.narrative import generate_narrative
from tests.test_analysis.conftest import (
    BACKTEST_ID,
    create_test_db,
    generate_default_trades,
)


class TestGenerateNarrative:

    def test_generate_narrative_basic_backtest(self, tmp_path):
        """Standard backtest with mixed results."""
        db_path = create_test_db(tmp_path / "test.db")
        result = generate_narrative(BACKTEST_ID, db_path)

        assert result.overview != ""
        assert result.metrics["total_trades"] == 50
        assert 0 <= result.metrics["win_rate"] <= 1.0
        assert result.metrics["profit_factor"] >= 0
        assert result.risk_assessment != ""
        assert isinstance(result.strengths, list)
        assert isinstance(result.weaknesses, list)
        assert len(result.strengths) >= 1
        assert len(result.weaknesses) >= 1

    def test_generate_narrative_session_breakdown(self, tmp_path):
        """Verifies per-session metrics computed correctly."""
        db_path = create_test_db(tmp_path / "test.db")
        result = generate_narrative(BACKTEST_ID, db_path)

        # All 5 sessions should be present in breakdown
        expected_sessions = {"asian", "london", "new_york", "london_ny_overlap", "off_hours"}
        assert set(result.session_breakdown.keys()) == expected_sessions

        # Each session should have trades, win_rate, avg_pnl
        for session, stats in result.session_breakdown.items():
            assert "trades" in stats
            assert "win_rate" in stats
            assert "avg_pnl" in stats
            assert stats["trades"] >= 0

        # Default fixtures distribute evenly: each session gets 10 trades
        total_from_sessions = sum(v["trades"] for v in result.session_breakdown.values())
        assert total_from_sessions == 50

    def test_generate_narrative_chart_first_structure(self, tmp_path):
        """Overview comes before metrics — chart-first structure."""
        db_path = create_test_db(tmp_path / "test.db")
        result = generate_narrative(BACKTEST_ID, db_path)

        # Overview should describe equity curve shape first
        assert "equity curve" in result.overview.lower()
        # Metrics dict should contain all required keys
        required_keys = {"win_rate", "profit_factor", "sharpe_ratio",
                         "max_drawdown_pips", "total_trades"}
        assert required_keys.issubset(result.metrics.keys())

    def test_generate_narrative_empty_trades(self, tmp_path):
        """Handles zero-trade edge case."""
        db_path = create_test_db(tmp_path / "test.db", trades=[])

        # Update the run metadata to reflect 0 trades
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE backtest_runs SET total_trades = 0 WHERE run_id = ?",
            (BACKTEST_ID,),
        )
        conn.commit()
        conn.close()

        result = generate_narrative(BACKTEST_ID, db_path)

        assert result.metrics["total_trades"] == 0
        assert "no trades" in result.overview.lower()
        assert "insufficient" in result.risk_assessment.lower()

    def test_generate_narrative_not_found(self, tmp_path):
        """AnalysisError raised when backtest_id doesn't exist."""
        from analysis.models import AnalysisError

        db_path = create_test_db(tmp_path / "test.db")

        with pytest.raises(AnalysisError, match="not found"):
            generate_narrative("nonexistent-id", db_path)

    def test_narrative_json_roundtrip(self, tmp_path):
        """NarrativeResult round-trips to/from JSON."""
        db_path = create_test_db(tmp_path / "test.db")
        result = generate_narrative(BACKTEST_ID, db_path)

        from analysis.models import NarrativeResult
        json_data = result.to_json()
        restored = NarrativeResult.from_json(json_data)

        assert restored.overview == result.overview
        assert restored.metrics == result.metrics
        assert restored.strengths == result.strengths
        assert restored.weaknesses == result.weaknesses
        assert restored.session_breakdown == result.session_breakdown
        assert restored.risk_assessment == result.risk_assessment
