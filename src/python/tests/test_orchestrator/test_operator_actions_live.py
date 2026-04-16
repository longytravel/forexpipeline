"""Live integration tests for operator_actions.py — Story 3.8.

These tests exercise REAL system behavior: writing pipeline state files,
evidence packs, and making gate decisions on disk. No mocks for the system
under test.

Run with: pytest -m live
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from orchestrator.gate_manager import GateManager
from orchestrator.pipeline_state import (
    CompletedStage,
    GateDecision,
    PipelineStage,
    PipelineState,
)


def _make_config(artifacts_dir: Path) -> dict:
    """Create a config dict pointing to the test artifacts dir."""
    return {
        "pipeline": {
            "artifacts_dir": str(artifacts_dir),
            "checkpoint_enabled": True,
            "retry_max_attempts": 3,
            "retry_backoff_base_s": 0.01,
            "gated_stages": ["review-pending"],
            "checkpoint_granularity": 1000,
        },
    }


def _create_full_pipeline_state(
    strategy_id: str,
    artifacts_dir: Path,
    stage: str = "review-pending",
    with_evidence_pack: bool = True,
    evidence_metrics: dict | None = None,
) -> PipelineState:
    """Create a realistic pipeline state at a given stage with artifacts on disk."""
    run_id = str(uuid.uuid4())

    # Build completed stages up to the current stage
    completed = []
    stage_order = [s.value for s in PipelineStage]
    current_idx = stage_order.index(stage)

    for i, s in enumerate(stage_order[:current_idx]):
        completed.append(CompletedStage(
            stage=s,
            completed_at=f"2026-03-19T{i:02d}:00:00.000Z",
            outcome="success",
            duration_s=float(i * 10 + 5),
        ))

    pending = stage_order[current_idx + 1:]

    state = PipelineState(
        strategy_id=strategy_id,
        run_id=run_id,
        current_stage=stage,
        completed_stages=completed,
        pending_stages=pending,
        gate_decisions=[],
        created_at="2026-03-19T00:00:00.000Z",
        last_transition_at=f"2026-03-19T{current_idx:02d}:00:00.000Z",
        config_hash="live-test-hash",
    )

    # Save state to disk
    strategy_dir = artifacts_dir / strategy_id
    strategy_dir.mkdir(parents=True, exist_ok=True)
    state.save(strategy_dir / "pipeline-state.json")

    # Write evidence pack if requested
    if with_evidence_pack:
        if evidence_metrics is None:
            evidence_metrics = {
                "total_trades": 250,
                "win_rate": 0.52,
                "profit_factor": 1.15,
                "max_drawdown": 0.18,
                "sharpe": 0.65,
            }

        backtest_dir = strategy_dir / "v001" / "backtest"
        backtest_dir.mkdir(parents=True, exist_ok=True)

        pack_data = {
            "backtest_id": run_id,
            "strategy_id": strategy_id,
            "version": "v001",
            "pipeline_stage": "backtest",
            "generated_at": "2026-03-19T00:00:00Z",
            "narrative": {
                "overview": "Strategy shows moderate performance with consistent trade generation.",
                "metrics": evidence_metrics,
                "strengths": ["Consistent trade frequency", "Reasonable drawdown"],
                "weaknesses": ["Low profit factor", "Below-average Sharpe"],
                "session_breakdown": {
                    "london": {"trades": 100, "win_rate": 0.55},
                    "new_york": {"trades": 80, "win_rate": 0.50},
                    "asian": {"trades": 70, "win_rate": 0.48},
                },
                "risk_assessment": "Moderate risk. Strategy shows stability but limited edge.",
            },
            "anomalies": {
                "backtest_id": run_id,
                "anomalies": [
                    {
                        "type": "LOW_TRADE_COUNT",
                        "severity": "WARNING",
                        "description": "Trade count below recommended minimum for statistical significance",
                        "evidence": {"total_trades": 250, "threshold": 500},
                        "recommendation": "Consider extending backtest period",
                    },
                ],
                "run_timestamp": "2026-03-19T00:00:00Z",
            },
            "metrics": evidence_metrics,
            "equity_curve_summary": [
                {"timestamp": 1000000, "equity": 0.0, "drawdown_pips": 0.0},
                {"timestamp": 2000000, "equity": 15.5, "drawdown_pips": 0.02},
            ],
            "equity_curve_full_path": f"artifacts/{strategy_id}/v001/backtest/equity-curve.arrow",
            "trade_distribution": {
                "by_session": {"london": 100, "new_york": 80, "asian": 70},
                "by_month": {"2025-01": 20, "2025-02": 22, "2025-03": 18},
            },
            "trade_log_path": f"artifacts/{strategy_id}/v001/backtest/trade-log.arrow",
            "metadata": {
                "generated_at": "2026-03-19T00:00:00Z",
                "backtest_run_id": run_id,
                "strategy_id": strategy_id,
                "version": "v001",
                "pipeline_stage": "backtest",
                "manifest_path": f"artifacts/{strategy_id}/v001/backtest/manifest.json",
                "schema_version": "1.0",
            },
        }

        pack_path = backtest_dir / "evidence_pack.json"
        pack_path.write_text(json.dumps(pack_data, indent=2), encoding="utf-8")

    return state


@pytest.mark.live
class TestLiveFullPipelineFlow:
    """End-to-end test: status -> review -> advance/reject/refine cycle."""

    def test_live_full_gate_decision_cycle(self, tmp_path):
        """Test the full accept->reject->refine cycle with real files."""
        from orchestrator.operator_actions import (
            advance_stage,
            get_pipeline_status,
            load_evidence_pack,
            refine_stage,
            reject_stage,
        )

        config = _make_config(tmp_path)

        # --- Setup: 3 strategies at review-pending ---
        _create_full_pipeline_state("strat-accept", tmp_path)
        _create_full_pipeline_state("strat-reject", tmp_path)
        _create_full_pipeline_state("strat-refine", tmp_path)

        # --- Step 1: Get status for all strategies ---
        statuses = get_pipeline_status(config)
        assert len(statuses) == 3
        for s in statuses:
            assert s["stage"] == "review-pending"
            assert s["decision_required"] is True
            assert s["anomaly_count"] == 1  # We wrote 1 anomaly each

        # --- Step 2: Load evidence pack for one strategy ---
        pack = load_evidence_pack("strat-accept", config)
        assert pack is not None
        assert pack["strategy_id"] == "strat-accept"
        assert pack["narrative"]["overview"] != ""
        assert len(pack["anomalies"]["anomalies"]) == 1

        # --- Step 3: Accept strategy ---
        result = advance_stage("strat-accept", "Metrics acceptable for V1", config)
        assert result["from_stage"] == "review-pending"
        assert result["to_stage"] == "reviewed"

        # Verify state file on disk
        state_path = tmp_path / "strat-accept" / "pipeline-state.json"
        assert state_path.exists()
        reloaded = PipelineState.load(state_path)
        assert reloaded.current_stage == "reviewed"
        assert len(reloaded.gate_decisions) == 1
        assert reloaded.gate_decisions[0].decision == "accept"
        assert reloaded.gate_decisions[0].evidence_pack_ref is not None

        # --- Step 4: Reject strategy ---
        result = reject_stage("strat-reject", "Drawdown too high for production", config)
        assert result["decision"] == "reject"
        assert result["reason"] == "Drawdown too high for production"

        reloaded = PipelineState.load(tmp_path / "strat-reject" / "pipeline-state.json")
        assert reloaded.current_stage == "review-pending"  # Stays at gate
        assert reloaded.gate_decisions[0].decision == "reject"

        # --- Step 5: Refine strategy ---
        result = refine_stage("strat-refine", "Tighten SL to 25 pips", config)
        assert result["from_stage"] == "review-pending"
        assert result["to_stage"] == "strategy-ready"
        assert result["decision"] == "refine"

        reloaded = PipelineState.load(tmp_path / "strat-refine" / "pipeline-state.json")
        assert reloaded.current_stage == "strategy-ready"
        assert reloaded.gate_decisions[0].decision == "refine"

        # --- Step 6: Verify status after decisions ---
        statuses = get_pipeline_status(config)
        status_map = {s["strategy_id"]: s for s in statuses}

        assert status_map["strat-accept"]["stage"] == "reviewed"
        assert status_map["strat-accept"]["decision_required"] is False

        assert status_map["strat-reject"]["stage"] == "review-pending"
        assert status_map["strat-reject"]["gate_status"] == "rejected"

        assert status_map["strat-refine"]["stage"] == "strategy-ready"


@pytest.mark.live
class TestLiveEvidencePackOutput:
    """Verify evidence pack loading produces correct output artifacts."""

    def test_live_evidence_pack_all_fields(self, tmp_path):
        """Verify evidence pack loaded from disk has all required fields."""
        from orchestrator.operator_actions import load_evidence_pack

        config = _make_config(tmp_path)
        strategy_id = "evidence-test"

        _create_full_pipeline_state(strategy_id, tmp_path)

        pack = load_evidence_pack(strategy_id, config)
        assert pack is not None

        # All 11 EvidencePack top-level fields
        assert "backtest_id" in pack
        assert "strategy_id" in pack
        assert "version" in pack
        assert "narrative" in pack
        assert "anomalies" in pack
        assert "metrics" in pack
        assert "equity_curve_summary" in pack
        assert "equity_curve_full_path" in pack
        assert "trade_distribution" in pack
        assert "trade_log_path" in pack
        assert "metadata" in pack

        # NarrativeResult fields (verify correct field names per Story 3-7)
        narrative = pack["narrative"]
        assert "overview" in narrative  # Not "summary"
        assert "risk_assessment" in narrative  # Not "interpretation"
        assert "metrics" in narrative
        assert "strengths" in narrative
        assert "weaknesses" in narrative
        assert "session_breakdown" in narrative

        # AnomalyReport wrapper (not bare list)
        anomalies = pack["anomalies"]
        assert "backtest_id" in anomalies
        assert "anomalies" in anomalies
        assert isinstance(anomalies["anomalies"], list)

        # Verify evidence pack file exists on disk
        pack_path = tmp_path / strategy_id / "v001" / "backtest" / "evidence_pack.json"
        assert pack_path.exists()

    def test_live_no_profitability_gate_losing_advance(self, tmp_path):
        """FR41: Advance a strategy with terrible metrics — must succeed."""
        from orchestrator.operator_actions import advance_stage

        config = _make_config(tmp_path)
        strategy_id = "terrible-strategy"

        _create_full_pipeline_state(
            strategy_id, tmp_path,
            evidence_metrics={
                "total_trades": 10,
                "win_rate": 0.10,
                "profit_factor": 0.2,
                "max_drawdown": 0.85,
                "sharpe": -3.5,
            },
        )

        result = advance_stage(strategy_id, "Advancing despite terrible metrics", config)
        assert result["to_stage"] == "reviewed"

        # State file should show reviewed
        state = PipelineState.load(tmp_path / strategy_id / "pipeline-state.json")
        assert state.current_stage == "reviewed"


@pytest.mark.live
class TestLiveResumeDetection:
    """Verify resume_pipeline correctly detects interrupted runs."""

    def test_live_resume_detects_error_state(self, tmp_path):
        """Verify interrupted runs with error state are detected."""
        from orchestrator.operator_actions import get_pipeline_status

        config = _make_config(tmp_path)

        # Create a strategy with an error
        state = PipelineState(
            strategy_id="crashed-strat",
            run_id=str(uuid.uuid4()),
            current_stage="backtest-running",
            completed_stages=[
                CompletedStage(
                    stage="data-ready",
                    completed_at="2026-03-19T00:00:00.000Z",
                    outcome="success",
                ),
            ],
            pending_stages=["backtest-complete", "review-pending", "reviewed"],
            gate_decisions=[],
            created_at="2026-03-19T00:00:00.000Z",
            last_transition_at="2026-03-19T01:00:00.000Z",
            error={"code": "TIMEOUT", "msg": "Process killed", "category": "external_failure"},
            config_hash="crash-hash",
        )
        strategy_dir = tmp_path / "crashed-strat"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        state.save(strategy_dir / "pipeline-state.json")

        # Also create a healthy strategy
        _create_full_pipeline_state("healthy-strat", tmp_path)

        statuses = get_pipeline_status(config)
        assert len(statuses) == 2

        status_map = {s["strategy_id"]: s for s in statuses}

        # Crashed strategy should show blocking reason
        crashed = status_map["crashed-strat"]
        assert crashed["stage"] == "backtest-running"
        assert crashed["blocking_reason"] is not None
        assert "Process killed" in crashed["blocking_reason"]

        # Healthy strategy at review-pending
        healthy = status_map["healthy-strat"]
        assert healthy["stage"] == "review-pending"
        assert healthy["decision_required"] is True
