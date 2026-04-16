"""Integration and live tests for the analysis layer.

Integration tests verify the full analysis pipeline:
Arrow IPC → SQLite ingest → narrative + anomalies + evidence pack.

Live tests (marked @pytest.mark.live) exercise real system behavior
with actual file I/O and verify output artifacts on disk.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.anomaly_detector import detect_anomalies
from analysis.evidence_pack import assemble_evidence_pack
from analysis.metrics_builder import compute_metrics
from analysis.models import EvidencePack, NarrativeResult, AnomalyReport
from analysis.narrative import generate_narrative
from tests.test_analysis.conftest import (
    BACKTEST_ID,
    STRATEGY_ID,
    create_full_artifact_tree,
    create_test_db,
    generate_default_trades,
)


class TestFullAnalysisPipeline:
    """Integration: full analysis pipeline from fixtures to evidence pack."""

    def test_full_analysis_pipeline(self, tmp_path):
        """Arrow IPC fixture → SQLite ingest → narrative + anomalies + evidence pack."""
        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(tmp_path)

        # Step 1: Generate narrative
        narrative = generate_narrative(BACKTEST_ID, db_path)
        assert isinstance(narrative, NarrativeResult)
        assert narrative.metrics["total_trades"] == 50
        assert narrative.overview != ""

        # Step 2: Detect anomalies
        anomalies = detect_anomalies(BACKTEST_ID, db_path)
        assert isinstance(anomalies, AnomalyReport)
        assert anomalies.backtest_id == BACKTEST_ID

        # Step 3: Assemble evidence pack
        pack = assemble_evidence_pack(BACKTEST_ID, db_path, artifacts_root)
        assert isinstance(pack, EvidencePack)
        assert pack.backtest_id == BACKTEST_ID
        assert pack.strategy_id == STRATEGY_ID

        # Step 4: Verify evidence pack JSON on disk
        ep_path = backtest_dir / "evidence_pack.json"
        assert ep_path.exists()

        disk_data = json.loads(ep_path.read_text(encoding="utf-8"))
        assert disk_data["backtest_id"] == BACKTEST_ID
        assert "narrative" in disk_data
        assert "anomalies" in disk_data
        assert "metrics" in disk_data
        assert disk_data["metadata"]["schema_version"] == "1.0"

    def test_evidence_pack_reads_story_3_6_output(self, tmp_path):
        """Uses Story 3-6 artifact structure as input."""
        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(tmp_path)

        # Verify Story 3-6 artifacts exist
        assert (backtest_dir / "trade-log.arrow").exists()
        assert (backtest_dir / "equity-curve.arrow").exists()
        assert (backtest_dir / "manifest.json").exists()

        pack = assemble_evidence_pack(BACKTEST_ID, db_path, artifacts_root)

        # Verify pack references correct Story 3-6 paths
        assert "trade-log.arrow" in pack.trade_log_path
        assert "equity-curve.arrow" in pack.equity_curve_full_path
        assert "manifest.json" in pack.metadata["manifest_path"]

    def test_metrics_consistency_across_modules(self, tmp_path):
        """Verify narrative and evidence pack produce identical metrics."""
        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(tmp_path)

        narrative = generate_narrative(BACKTEST_ID, db_path)
        pack = assemble_evidence_pack(BACKTEST_ID, db_path, artifacts_root)

        # Metrics should be identical since both use compute_metrics()
        assert narrative.metrics == pack.metrics

    def test_evidence_pack_json_round_trip(self, tmp_path):
        """Full round-trip: assemble → persist → load → verify."""
        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(tmp_path)

        pack = assemble_evidence_pack(BACKTEST_ID, db_path, artifacts_root)

        # Load from disk
        ep_path = backtest_dir / "evidence_pack.json"
        disk_data = json.loads(ep_path.read_text(encoding="utf-8"))

        # Deserialize
        restored = EvidencePack.from_json(disk_data)

        assert restored.backtest_id == pack.backtest_id
        assert restored.strategy_id == pack.strategy_id
        assert restored.version == pack.version
        assert restored.metrics == pack.metrics
        assert restored.narrative.overview == pack.narrative.overview
        assert len(restored.anomalies.anomalies) == len(pack.anomalies.anomalies)


# ---------------------------------------------------------------------------
# Live tests — exercise REAL system behavior
# ---------------------------------------------------------------------------


@pytest.mark.live
class TestLiveFullAnalysisPipeline:
    """Live tests that exercise real file I/O and verify artifacts on disk."""

    def test_live_full_evidence_pack_generation(self, tmp_path):
        """Generate a complete evidence pack from scratch and verify output.

        Creates real SQLite database, real Arrow IPC files, runs the full
        analysis pipeline, and verifies every output artifact exists on disk
        with correct content.
        """
        # Create real artifact tree
        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(
            tmp_path, num_equity_points=1500,
        )

        # Run full pipeline
        pack = assemble_evidence_pack(BACKTEST_ID, db_path, artifacts_root)

        # Verify evidence pack file exists on disk
        ep_path = backtest_dir / "evidence_pack.json"
        assert ep_path.exists(), f"Evidence pack not found at {ep_path}"

        # Verify file content is valid JSON with all required fields
        disk_data = json.loads(ep_path.read_text(encoding="utf-8"))

        # Required top-level fields
        required_fields = {
            "backtest_id", "strategy_id", "version", "pipeline_stage",
            "generated_at", "narrative", "anomalies", "metrics",
            "equity_curve_summary", "equity_curve_full_path",
            "trade_distribution", "trade_log_path", "metadata",
        }
        assert required_fields.issubset(disk_data.keys()), (
            f"Missing fields: {required_fields - set(disk_data.keys())}"
        )

        # Verify metrics content
        metrics = disk_data["metrics"]
        assert metrics["total_trades"] == 50
        assert 0 <= metrics["win_rate"] <= 1.0
        assert metrics["profit_factor"] >= 0
        assert "sharpe_ratio" in metrics
        assert "max_drawdown_pips" in metrics

        # Verify equity curve downsampled
        assert len(disk_data["equity_curve_summary"]) <= 500
        assert len(disk_data["equity_curve_summary"]) > 0

        # Verify trade distribution
        dist = disk_data["trade_distribution"]
        assert sum(dist["by_session"].values()) == 50
        assert sum(dist["by_month"].values()) == 50

        # Verify narrative structure
        narrative = disk_data["narrative"]
        assert narrative["overview"] != ""
        assert isinstance(narrative["strengths"], list)
        assert isinstance(narrative["weaknesses"], list)

        # Verify metadata
        assert disk_data["metadata"]["schema_version"] == "1.0"
        assert disk_data["metadata"]["pipeline_stage"] == "backtest"

        # Verify no .partial files remain
        partial_files = list(backtest_dir.glob("*.partial"))
        assert len(partial_files) == 0, f"Partial files remain: {partial_files}"

    def test_live_anomaly_detection_produces_valid_report(self, tmp_path):
        """Anomaly detection on real data produces a valid report on disk.

        Exercises real SQLite queries and verifies each anomaly flag
        has proper structure.
        """
        # Create deliberately anomalous data: low trade count
        trades = []
        for i in range(15):
            trades.append({
                "trade_id": i + 1,
                "direction": "long",
                "entry_time": f"2020-01-{(i % 28) + 1:02d}T10:00:00+00:00",
                "exit_time": f"2020-01-{(i % 28) + 1:02d}T12:00:00+00:00",
                "pnl_pips": 5.0 if i < 14 else -2.0,
                "session": "london",
                "lot_size": 0.1,
            })

        db_path = create_test_db(tmp_path / "test.db", trades)

        report = detect_anomalies(BACKTEST_ID, db_path)

        # Should detect at least LOW_TRADE_COUNT
        assert len(report.anomalies) >= 1

        # Verify each anomaly has proper structure
        for anomaly in report.anomalies:
            assert anomaly.type is not None
            assert anomaly.severity is not None
            assert anomaly.description != ""
            assert isinstance(anomaly.evidence, dict)
            assert anomaly.recommendation != ""

        # Serialize and verify it's valid JSON
        json_data = report.to_json()
        json_str = json.dumps(json_data, default=str)
        parsed = json.loads(json_str)
        assert parsed["backtest_id"] == BACKTEST_ID

    def test_live_narrative_with_session_breakdown(self, tmp_path):
        """Narrative generation on real data produces correct session breakdown.

        Exercises real SQLite queries and verifies session-level metrics.
        """
        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(tmp_path)

        result = generate_narrative(BACKTEST_ID, db_path)

        # Verify narrative is substantive
        assert len(result.overview) > 50, "Overview too short"
        assert result.metrics["total_trades"] == 50

        # Verify all sessions are represented
        expected_sessions = {"asian", "london", "new_york", "london_ny_overlap", "off_hours"}
        assert set(result.session_breakdown.keys()) == expected_sessions

        # Verify session data is correct
        total = sum(v["trades"] for v in result.session_breakdown.values())
        assert total == 50

        # Each session with trades should have valid win_rate
        for session, data in result.session_breakdown.items():
            if data["trades"] > 0:
                assert 0.0 <= data["win_rate"] <= 1.0
                assert isinstance(data["avg_pnl"], float)

        # Verify strengths and weaknesses are non-empty lists
        assert len(result.strengths) >= 1
        assert len(result.weaknesses) >= 1
