"""Tests for analysis.evidence_pack — evidence pack assembler."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysis.evidence_pack import (
    _downsample_equity_curve,
    _find_version_dir,
    assemble_evidence_pack,
)
from analysis.models import AnalysisError, EvidencePack
from tests.test_analysis.conftest import (
    BACKTEST_ID,
    STRATEGY_ID,
    create_equity_curve_arrow,
    create_full_artifact_tree,
)


class TestAssembleEvidencePack:

    def test_assemble_evidence_pack_complete(self, tmp_path):
        """All fields populated including manifest_path and schema_version."""
        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(tmp_path)

        pack = assemble_evidence_pack(BACKTEST_ID, db_path, artifacts_root)

        assert pack.backtest_id == BACKTEST_ID
        assert pack.strategy_id == STRATEGY_ID
        assert pack.version == "v001"
        assert pack.narrative is not None
        assert pack.anomalies is not None
        assert pack.metrics["total_trades"] == 50
        assert len(pack.equity_curve_summary) > 0
        assert "trade-log.arrow" in pack.trade_log_path
        assert "equity-curve.arrow" in pack.equity_curve_full_path
        assert pack.metadata["schema_version"] == "1.0"
        assert pack.metadata["pipeline_stage"] == "backtest"
        assert "manifest.json" in pack.metadata["manifest_path"]
        assert pack.metadata["generated_at"] != ""

    def test_evidence_pack_json_serialization(self, tmp_path):
        """Round-trip to/from JSON."""
        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(tmp_path)

        pack = assemble_evidence_pack(BACKTEST_ID, db_path, artifacts_root)

        # Serialize
        json_data = pack.to_json()
        json_str = json.dumps(json_data, default=str)

        # Deserialize
        parsed = json.loads(json_str)
        restored = EvidencePack.from_json(parsed)

        assert restored.backtest_id == pack.backtest_id
        assert restored.strategy_id == pack.strategy_id
        assert restored.version == pack.version
        assert restored.metrics == pack.metrics
        assert len(restored.equity_curve_summary) == len(pack.equity_curve_summary)
        assert restored.trade_distribution == pack.trade_distribution

    def test_evidence_pack_crash_safe_write(self, tmp_path):
        """Partial file pattern verified — no .partial files after success."""
        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(tmp_path)

        assemble_evidence_pack(BACKTEST_ID, db_path, artifacts_root)

        # Verify evidence_pack.json exists
        ep_path = backtest_dir / "evidence_pack.json"
        assert ep_path.exists()

        # Verify no .partial files remain
        partial_files = list(backtest_dir.glob("*.partial"))
        assert len(partial_files) == 0

        # Verify JSON is valid
        data = json.loads(ep_path.read_text(encoding="utf-8"))
        assert data["backtest_id"] == BACKTEST_ID

    def test_evidence_pack_versioned_path(self, tmp_path):
        """Correct artifact path structure using Story 3.6 conventions."""
        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(tmp_path)

        pack = assemble_evidence_pack(BACKTEST_ID, db_path, artifacts_root)

        # Paths should use relative format: artifacts/{strategy_id}/v{NNN}/backtest/...
        assert pack.trade_log_path == f"artifacts/{STRATEGY_ID}/v001/backtest/trade-log.arrow"
        assert pack.equity_curve_full_path == f"artifacts/{STRATEGY_ID}/v001/backtest/equity-curve.arrow"
        assert pack.metadata["manifest_path"] == f"artifacts/{STRATEGY_ID}/v001/backtest/manifest.json"

    def test_evidence_pack_equity_curve_downsampled(self, tmp_path):
        """Verify equity curve summary has max 500 points even when source has thousands."""
        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(
            tmp_path, num_equity_points=2000,
        )

        pack = assemble_evidence_pack(BACKTEST_ID, db_path, artifacts_root)

        assert len(pack.equity_curve_summary) <= 500
        # Each point should have required fields
        if pack.equity_curve_summary:
            point = pack.equity_curve_summary[0]
            assert "timestamp" in point
            assert "equity" in point
            assert "drawdown_pips" in point

    def test_evidence_pack_artifact_filenames(self, tmp_path):
        """Verify trade-log.arrow and equity-curve.arrow (hyphenated)."""
        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(tmp_path)

        pack = assemble_evidence_pack(BACKTEST_ID, db_path, artifacts_root)

        # Filenames must be hyphenated per Story 3.6 convention
        assert "trade-log.arrow" in pack.trade_log_path
        assert "equity-curve.arrow" in pack.equity_curve_full_path

    def test_evidence_pack_trade_distribution(self, tmp_path):
        """Trade distribution includes by_session and by_month."""
        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(tmp_path)

        pack = assemble_evidence_pack(BACKTEST_ID, db_path, artifacts_root)

        assert "by_session" in pack.trade_distribution
        assert "by_month" in pack.trade_distribution
        assert isinstance(pack.trade_distribution["by_session"], dict)
        assert isinstance(pack.trade_distribution["by_month"], dict)

        # Sessions should have counts
        total_session = sum(pack.trade_distribution["by_session"].values())
        total_month = sum(pack.trade_distribution["by_month"].values())
        assert total_session == 50
        assert total_month == 50

    def test_evidence_pack_missing_equity_curve(self, tmp_path):
        """Gracefully handles missing equity curve file."""
        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(tmp_path)

        # Remove equity curve file
        (backtest_dir / "equity-curve.arrow").unlink()

        pack = assemble_evidence_pack(BACKTEST_ID, db_path, artifacts_root)

        # Should return empty equity curve summary
        assert pack.equity_curve_summary == []
        # Rest of the pack should still be populated
        assert pack.metrics["total_trades"] == 50

    def test_evidence_pack_persisted_to_disk(self, tmp_path):
        """Evidence pack JSON is persisted as a versioned artifact."""
        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(tmp_path)

        pack = assemble_evidence_pack(BACKTEST_ID, db_path, artifacts_root)

        ep_path = backtest_dir / "evidence_pack.json"
        assert ep_path.exists()

        disk_data = json.loads(ep_path.read_text(encoding="utf-8"))
        assert disk_data["backtest_id"] == BACKTEST_ID
        assert disk_data["strategy_id"] == STRATEGY_ID
        assert disk_data["version"] == "v001"
        assert "narrative" in disk_data
        assert "anomalies" in disk_data
        assert "metrics" in disk_data


# ---------------------------------------------------------------------------
# Regression tests for code review findings
# ---------------------------------------------------------------------------


class TestRegressionH1StreamingDownsample:
    """Regression: H1 — equity curve downsampling must NOT load all rows into
    memory. Verifies two-pass streaming approach works correctly."""

    @pytest.mark.regression
    def test_downsample_does_not_load_all_rows(self, tmp_path):
        """Large equity curve is downsampled without materializing all rows.

        We can't directly test memory, but we verify the output is correct
        and capped at max_points for a large input.
        """
        arrow_path = create_equity_curve_arrow(tmp_path / "big.arrow", num_points=5000)

        result = _downsample_equity_curve(arrow_path, max_points=500)

        assert len(result) == 500
        # First point should be from the beginning, last from the end
        assert result[0]["timestamp"] is not None
        assert result[-1]["timestamp"] is not None
        # Points should have all required fields
        for p in result:
            assert "timestamp" in p
            assert "equity" in p
            assert "drawdown_pips" in p

    @pytest.mark.regression
    def test_downsample_small_curve_returns_all(self, tmp_path):
        """Curves smaller than max_points are returned in full."""
        arrow_path = create_equity_curve_arrow(tmp_path / "small.arrow", num_points=100)

        result = _downsample_equity_curve(arrow_path, max_points=500)

        assert len(result) == 100


class TestRegressionH2VersionFallback:
    """Regression: H2 — _find_version_dir must NOT silently return a wrong
    version when multiple versions exist with no manifest match."""

    @pytest.mark.regression
    def test_multiple_versions_no_manifest_match_raises(self, tmp_path):
        """Multiple version dirs with no matching manifest must raise."""
        strategy_dir = tmp_path / "test-strategy"

        # Create two version dirs with manifests for different backtest IDs
        for v, run_id in [("v001", "other-run-1"), ("v002", "other-run-2")]:
            bt_dir = strategy_dir / v / "backtest"
            bt_dir.mkdir(parents=True)
            manifest = {"backtest_run_id": run_id}
            (bt_dir / "manifest.json").write_text(json.dumps(manifest))
            (bt_dir / "trade-log.arrow").write_text("dummy")

        with pytest.raises(AnalysisError, match="Multiple version directories"):
            _find_version_dir("test-strategy", "nonexistent-run", tmp_path)

    @pytest.mark.regression
    def test_single_version_no_manifest_falls_back_safely(self, tmp_path):
        """Single version dir with no manifest match is safe to fall back to."""
        strategy_dir = tmp_path / "test-strategy"
        bt_dir = strategy_dir / "v001" / "backtest"
        bt_dir.mkdir(parents=True)
        # Manifest for a different run — but only one version exists
        manifest = {"backtest_run_id": "other-run"}
        (bt_dir / "manifest.json").write_text(json.dumps(manifest))

        result = _find_version_dir("test-strategy", "my-run", tmp_path)
        assert result == bt_dir


class TestRegressionM1MetricsReuse:
    """Regression: M1 — evidence pack must reuse narrative.metrics rather
    than opening a redundant SQLite connection and recomputing."""

    @pytest.mark.regression
    def test_pack_metrics_match_narrative_metrics(self, tmp_path):
        """Evidence pack metrics must equal narrative metrics (same source)."""
        from analysis.narrative import generate_narrative

        db_path, artifacts_root, backtest_dir = create_full_artifact_tree(tmp_path)

        # Get narrative metrics independently
        narrative = generate_narrative(BACKTEST_ID, db_path)

        # Get evidence pack
        pack = assemble_evidence_pack(BACKTEST_ID, db_path, artifacts_root)

        # They must be identical (same object reused, not recomputed)
        assert pack.metrics == narrative.metrics


class TestRegressionM2ConsistentErrorHandling:
    """Regression: M2 — anomaly_detector._load_run_metadata must raise
    AnalysisError on missing run, consistent with narrative module."""

    @pytest.mark.regression
    def test_anomaly_detector_raises_on_missing_run(self, tmp_path):
        """Anomaly detector must raise AnalysisError for nonexistent backtest ID."""
        from analysis.anomaly_detector import detect_anomalies
        from tests.test_analysis.conftest import create_test_db

        db_path = create_test_db(tmp_path / "test.db")

        with pytest.raises(AnalysisError, match="Backtest run not found"):
            detect_anomalies("nonexistent-run-id", db_path)
