"""Unit tests for operator_actions.py — Story 3.8 Tasks 4.1-4.15.

Tests use mocks for BacktestExecutor, BatchRunner, GateManager, and
StageRunner since this module is a thin composition layer. The tests
verify correct delegation, return structure, and behavioral constraints.
"""
from __future__ import annotations

import ast
import json
import re
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.gate_manager import GateManager, PipelineStatus
from orchestrator.pipeline_state import (
    CompletedStage,
    GateDecision,
    PipelineStage,
    PipelineState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(
    strategy_id: str = "test-strategy",
    stage: str = "review-pending",
    run_id: str | None = None,
    config_hash: str = "abc123",
    error: dict | None = None,
    checkpoint: dict | None = None,
    gate_decisions: list | None = None,
    completed_stages: list | None = None,
) -> PipelineState:
    """Create a PipelineState for testing."""
    return PipelineState(
        strategy_id=strategy_id,
        run_id=run_id or str(uuid.uuid4()),
        current_stage=stage,
        completed_stages=completed_stages or [],
        pending_stages=[],
        gate_decisions=gate_decisions or [],
        created_at="2026-03-19T00:00:00.000Z",
        last_transition_at="2026-03-19T00:00:00.000Z",
        checkpoint=checkpoint,
        error=error,
        config_hash=config_hash,
    )


def _write_state(state: PipelineState, artifacts_dir: Path) -> Path:
    """Write a pipeline state to disk and return the state file path."""
    strategy_dir = artifacts_dir / state.strategy_id
    strategy_dir.mkdir(parents=True, exist_ok=True)
    state_path = strategy_dir / "pipeline-state.json"
    state.save(state_path)
    return state_path


def _write_evidence_pack(
    strategy_id: str,
    artifacts_dir: Path,
    version: str = "v001",
    anomaly_count: int = 0,
    metrics: dict | None = None,
) -> Path:
    """Write a minimal evidence pack JSON to disk."""
    backtest_dir = artifacts_dir / strategy_id / version / "backtest"
    backtest_dir.mkdir(parents=True, exist_ok=True)
    pack_path = backtest_dir / "evidence_pack.json"

    if metrics is None:
        metrics = {
            "total_trades": 100,
            "win_rate": 0.55,
            "profit_factor": 1.2,
            "max_drawdown": 0.15,
            "sharpe": 0.8,
        }

    anomalies = []
    for i in range(anomaly_count):
        anomalies.append({
            "type": "LOW_TRADE_COUNT",
            "severity": "WARNING",
            "description": f"Test anomaly {i}",
            "evidence": {},
            "recommendation": "Review",
        })

    pack_data = {
        "backtest_id": "run-001",
        "strategy_id": strategy_id,
        "version": version,
        "pipeline_stage": "backtest",
        "generated_at": "2026-03-19T00:00:00Z",
        "narrative": {
            "overview": "Test overview",
            "metrics": metrics,
            "strengths": ["Good win rate"],
            "weaknesses": ["High drawdown"],
            "session_breakdown": {"london": {"trades": 50}},
            "risk_assessment": "Moderate risk",
        },
        "anomalies": {
            "backtest_id": "run-001",
            "anomalies": anomalies,
            "run_timestamp": "2026-03-19T00:00:00Z",
        },
        "metrics": metrics,
        "equity_curve_summary": [],
        "equity_curve_full_path": f"artifacts/{strategy_id}/{version}/backtest/equity-curve.arrow",
        "trade_distribution": {"by_session": {"london": 50}, "by_month": {}},
        "trade_log_path": f"artifacts/{strategy_id}/{version}/backtest/trade-log.arrow",
        "metadata": {
            "generated_at": "2026-03-19T00:00:00Z",
            "backtest_run_id": "run-001",
            "strategy_id": strategy_id,
            "version": version,
            "pipeline_stage": "backtest",
            "manifest_path": f"artifacts/{strategy_id}/{version}/backtest/manifest.json",
            "schema_version": "1.0",
        },
    }

    pack_path.write_text(json.dumps(pack_data, indent=2), encoding="utf-8")
    return pack_path


def _make_config(artifacts_dir: Path) -> dict:
    """Create a minimal config dict for testing."""
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


# ---------------------------------------------------------------------------
# Test 4.2: test_run_backtest_invokes_executor_and_assembles_evidence
# ---------------------------------------------------------------------------

class TestRunBacktest:

    @patch("orchestrator.operator_actions.StageRunner")
    @patch("rust_bridge.batch_runner.BatchRunner", autospec=True)
    @patch("rust_bridge.backtest_executor.BacktestExecutor", autospec=True)
    def test_run_backtest_invokes_executor_and_assembles_evidence(
        self, mock_executor_cls, mock_runner_cls, mock_stage_runner_cls, tmp_path,
    ):
        """Task 4.2: Verify StageRunner is called and evidence pack is found."""
        config = _make_config(tmp_path)
        strategy_id = "test-strategy"

        # Write evidence pack so it's found after run
        _write_evidence_pack(strategy_id, tmp_path)

        # Mock StageRunner.run() to return a successful state
        mock_runner = MagicMock()
        mock_runner.run.return_value = _make_state(
            strategy_id=strategy_id,
            stage="review-pending",
            run_id="run-001",
            config_hash="abc123",
        )
        mock_stage_runner_cls.return_value = mock_runner

        from orchestrator.operator_actions import run_backtest
        result = run_backtest(strategy_id, config)

        assert result["status"] == "success"
        assert result["backtest_id"] == "run-001"
        assert result["evidence_pack_path"] is not None
        assert result["error"] is None
        mock_runner.run.assert_called_once()

    @patch("orchestrator.operator_actions.StageRunner")
    @patch("rust_bridge.batch_runner.BatchRunner", autospec=True)
    @patch("rust_bridge.backtest_executor.BacktestExecutor", autospec=True)
    def test_run_backtest_returns_error_on_executor_failure(
        self, mock_executor_cls, mock_runner_cls, mock_stage_runner_cls, tmp_path,
    ):
        """Task 4.3: Verify error dict returned on executor failure."""
        config = _make_config(tmp_path)

        mock_runner = MagicMock()
        mock_runner.run.return_value = _make_state(
            stage="backtest-running",
            error={"code": "EXEC_FAIL", "msg": "Rust crash"},
        )
        mock_stage_runner_cls.return_value = mock_runner

        from orchestrator.operator_actions import run_backtest
        result = run_backtest("test-strategy", config)

        assert result["status"] == "failed"
        assert "Rust crash" in result["error"]


# ---------------------------------------------------------------------------
# Tests 4.4-4.5: get_pipeline_status
# ---------------------------------------------------------------------------

class TestGetPipelineStatus:

    def test_aggregates_all_strategies(self, tmp_path):
        """Task 4.4: Create 2 pipeline-state.json files, verify both returned."""
        config = _make_config(tmp_path)

        state1 = _make_state(strategy_id="strat-a", stage="backtest-running")
        state2 = _make_state(strategy_id="strat-b", stage="review-pending")
        _write_state(state1, tmp_path)
        _write_state(state2, tmp_path)

        from orchestrator.operator_actions import get_pipeline_status
        result = get_pipeline_status(config)

        assert len(result) == 2
        strategy_ids = {r["strategy_id"] for r in result}
        assert strategy_ids == {"strat-a", "strat-b"}

        # Verify all required fields present
        for r in result:
            assert "strategy_id" in r
            assert "stage" in r
            assert "progress_pct" in r
            assert "last_transition_at" in r
            assert "gate_status" in r
            assert "decision_required" in r
            assert "anomaly_count" in r
            assert "run_id" in r
            assert "config_hash" in r
            assert "last_outcome" in r
            assert "blocking_reason" in r
            assert "evidence_pack_ref" in r

    def test_empty_when_no_strategies(self, tmp_path):
        """Task 4.5: Verify empty list when no state files exist."""
        config = _make_config(tmp_path)

        from orchestrator.operator_actions import get_pipeline_status
        result = get_pipeline_status(config)

        assert result == []

    def test_counts_anomalies_from_evidence_pack(self, tmp_path):
        """Verify anomaly count is read from evidence pack on disk."""
        config = _make_config(tmp_path)

        state = _make_state(strategy_id="strat-c", stage="review-pending")
        _write_state(state, tmp_path)
        _write_evidence_pack("strat-c", tmp_path, anomaly_count=3)

        from orchestrator.operator_actions import get_pipeline_status
        result = get_pipeline_status(config)

        assert len(result) == 1
        assert result[0]["anomaly_count"] == 3


# ---------------------------------------------------------------------------
# Test 4.6: load_evidence_pack
# ---------------------------------------------------------------------------

class TestLoadEvidencePack:

    def test_deserializes_correctly(self, tmp_path):
        """Task 4.6: Write evidence_pack.json, verify all 11 fields."""
        config = _make_config(tmp_path)
        strategy_id = "test-strategy"
        _write_evidence_pack(strategy_id, tmp_path)

        from orchestrator.operator_actions import load_evidence_pack
        result = load_evidence_pack(strategy_id, config)

        assert result is not None
        # Verify all 11 EvidencePack fields
        assert result["backtest_id"] == "run-001"
        assert result["strategy_id"] == strategy_id
        assert result["version"] == "v001"
        assert "overview" in result["narrative"]
        assert "risk_assessment" in result["narrative"]
        assert "backtest_id" in result["anomalies"]
        assert isinstance(result["anomalies"]["anomalies"], list)
        assert isinstance(result["metrics"], dict)
        assert isinstance(result["equity_curve_summary"], list)
        assert isinstance(result["equity_curve_full_path"], str)
        assert isinstance(result["trade_distribution"], dict)
        assert isinstance(result["trade_log_path"], str)
        assert isinstance(result["metadata"], dict)

    def test_returns_none_when_no_pack(self, tmp_path):
        """Verify None returned when no evidence pack exists."""
        config = _make_config(tmp_path)

        from orchestrator.operator_actions import load_evidence_pack
        result = load_evidence_pack("nonexistent", config)

        assert result is None

    def test_uses_state_ref_when_provided(self, tmp_path):
        """Task 4.14: Verify explicit evidence_pack_ref path is loaded."""
        config = _make_config(tmp_path)
        strategy_id = "test-strategy"

        # Write pack at a specific path
        pack_path = _write_evidence_pack(strategy_id, tmp_path, version="v002")

        from orchestrator.operator_actions import load_evidence_pack
        result = load_evidence_pack(
            strategy_id, config, evidence_pack_ref=str(pack_path),
        )

        assert result is not None
        assert result["version"] == "v002"


# ---------------------------------------------------------------------------
# Tests 4.7-4.8: advance_stage, reject_stage
# ---------------------------------------------------------------------------

class TestAdvanceStage:

    def test_creates_accept_gate_decision(self, tmp_path):
        """Task 4.7: Verify GateDecision(decision='accept') with correct fields."""
        config = _make_config(tmp_path)
        strategy_id = "test-strategy"

        state = _make_state(strategy_id=strategy_id, stage="review-pending")
        _write_state(state, tmp_path)
        _write_evidence_pack(strategy_id, tmp_path)

        from orchestrator.operator_actions import advance_stage
        result = advance_stage(strategy_id, "Looks good", config)

        assert result["strategy_id"] == strategy_id
        assert result["from_stage"] == "review-pending"
        assert result["to_stage"] == "reviewed"
        assert "decided_at" in result

        # Verify state was persisted with the gate decision
        reloaded = PipelineState.load(tmp_path / strategy_id / "pipeline-state.json")
        assert len(reloaded.gate_decisions) == 1
        assert reloaded.gate_decisions[0].decision == "accept"
        assert reloaded.gate_decisions[0].reason == "Looks good"
        assert reloaded.gate_decisions[0].evidence_pack_ref is not None


class TestRejectStage:

    def test_creates_reject_gate_decision_with_reason(self, tmp_path):
        """Task 4.8: Verify reason propagated in rejection."""
        config = _make_config(tmp_path)
        strategy_id = "test-strategy"

        state = _make_state(strategy_id=strategy_id, stage="review-pending")
        _write_state(state, tmp_path)

        from orchestrator.operator_actions import reject_stage
        result = reject_stage(strategy_id, "Too risky", config)

        assert result["strategy_id"] == strategy_id
        assert result["stage"] == "review-pending"
        assert result["decision"] == "reject"
        assert result["reason"] == "Too risky"

        # Verify state was persisted
        reloaded = PipelineState.load(tmp_path / strategy_id / "pipeline-state.json")
        assert len(reloaded.gate_decisions) == 1
        assert reloaded.gate_decisions[0].decision == "reject"
        assert reloaded.gate_decisions[0].reason == "Too risky"


# ---------------------------------------------------------------------------
# Test 4.13: refine_stage
# ---------------------------------------------------------------------------

class TestRefineStage:

    def test_creates_refine_gate_decision(self, tmp_path):
        """Task 4.13: Verify refine returns to strategy-ready (AC #6)."""
        config = _make_config(tmp_path)
        strategy_id = "test-strategy"

        state = _make_state(strategy_id=strategy_id, stage="review-pending")
        _write_state(state, tmp_path)

        from orchestrator.operator_actions import refine_stage
        result = refine_stage(strategy_id, "Adjust SL to 30 pips", config)

        assert result["strategy_id"] == strategy_id
        assert result["from_stage"] == "review-pending"
        assert result["to_stage"] == "strategy-ready"
        assert result["decision"] == "refine"
        assert result["reason"] == "Adjust SL to 30 pips"

        reloaded = PipelineState.load(tmp_path / strategy_id / "pipeline-state.json")
        assert reloaded.current_stage == "strategy-ready"
        assert len(reloaded.gate_decisions) == 1
        assert reloaded.gate_decisions[0].decision == "refine"


# ---------------------------------------------------------------------------
# Test 4.9: resume_pipeline
# ---------------------------------------------------------------------------

class TestResumePipeline:

    @patch("orchestrator.operator_actions.StageRunner")
    def test_detects_and_resumes_interrupted(self, mock_runner_cls, tmp_path):
        """Task 4.9: Verify resume called for interrupted strategy."""
        config = _make_config(tmp_path)

        # Create a state with an error (interrupted)
        state = _make_state(
            strategy_id="interrupted-strat",
            stage="backtest-running",
            error={"code": "TIMEOUT", "msg": "Process killed"},
        )
        _write_state(state, tmp_path)

        mock_runner = MagicMock()
        mock_runner.resume.return_value = _make_state(
            strategy_id="interrupted-strat",
            stage="backtest-complete",
        )
        mock_runner_cls.return_value = mock_runner

        from orchestrator.operator_actions import resume_pipeline
        results = resume_pipeline(None, config)

        assert len(results) == 1
        assert results[0]["strategy_id"] == "interrupted-strat"
        assert results[0]["resumed_from_stage"] == "backtest-running"
        mock_runner.resume.assert_called_once()


# ---------------------------------------------------------------------------
# Tests 4.10-4.12: No-profitability-gate enforcement (FR41)
# ---------------------------------------------------------------------------

class TestNoProfitabilityGate:

    def test_no_profitability_gate_in_any_function(self):
        """Task 4.10: Static analysis — no P&L checks in conditionals."""
        source_path = Path(__file__).resolve().parent.parent.parent / "orchestrator" / "operator_actions.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # Patterns that would indicate profitability gating
        gate_patterns = re.compile(
            r"\b(profit_factor|sharpe|pnl|equity_curve|win_rate|profit)\b",
            re.IGNORECASE,
        )

        violations = []
        for node in ast.walk(tree):
            # Check if/while/assert conditions
            if isinstance(node, (ast.If, ast.While)):
                test_source = ast.get_source_segment(source, node.test)
                if test_source and gate_patterns.search(test_source):
                    violations.append(
                        f"Line {node.lineno}: profitability check in conditional: {test_source[:80]}"
                    )
            elif isinstance(node, ast.Assert):
                test_source = ast.get_source_segment(source, node.test)
                if test_source and gate_patterns.search(test_source):
                    violations.append(
                        f"Line {node.lineno}: profitability check in assert: {test_source[:80]}"
                    )

        assert not violations, (
            f"FR41 violation: profitability checks found in conditionals:\n"
            + "\n".join(violations)
        )

    def test_advance_allows_losing_strategy(self, tmp_path):
        """Task 4.11: Advance succeeds with negative P&L evidence pack."""
        config = _make_config(tmp_path)
        strategy_id = "losing-strategy"

        state = _make_state(strategy_id=strategy_id, stage="review-pending")
        _write_state(state, tmp_path)

        # Create evidence pack with bad metrics
        _write_evidence_pack(
            strategy_id, tmp_path,
            metrics={
                "total_trades": 50,
                "win_rate": 0.30,
                "profit_factor": 0.5,
                "max_drawdown": 0.45,
                "sharpe": -1.2,
            },
        )

        from orchestrator.operator_actions import advance_stage
        result = advance_stage(strategy_id, "Advancing despite losses", config)

        # Must succeed — no profitability gate
        assert result["from_stage"] == "review-pending"
        assert result["to_stage"] == "reviewed"

    def test_advance_allows_zero_trades_strategy(self, tmp_path):
        """Task 4.12: Advance succeeds with zero trades evidence pack."""
        config = _make_config(tmp_path)
        strategy_id = "zero-trades"

        state = _make_state(strategy_id=strategy_id, stage="review-pending")
        _write_state(state, tmp_path)

        _write_evidence_pack(
            strategy_id, tmp_path,
            metrics={
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "max_drawdown": 0.0,
                "sharpe": 0.0,
            },
        )

        from orchestrator.operator_actions import advance_stage
        result = advance_stage(strategy_id, "Testing with zero trades", config)

        assert result["from_stage"] == "review-pending"
        assert result["to_stage"] == "reviewed"


# ---------------------------------------------------------------------------
# Test 4.15: Structured logging with unified schema
# ---------------------------------------------------------------------------

class TestOperatorLogging:

    def test_log_with_unified_schema(self, tmp_path, caplog):
        """Task 4.15: Verify JSON log structure includes D6 fields."""
        import logging
        caplog.set_level(logging.INFO)

        config = _make_config(tmp_path)
        strategy_id = "log-test"

        state = _make_state(strategy_id=strategy_id, stage="review-pending")
        _write_state(state, tmp_path)

        from orchestrator.operator_actions import advance_stage
        advance_stage(strategy_id, "Log test", config)

        # Find log records from pipeline.operator
        operator_records = [
            r for r in caplog.records
            if hasattr(r, "component") and "pipeline.operator" in str(getattr(r, "component", ""))
            or "Operator action" in r.getMessage()
        ]

        # At least one operator action log should exist
        assert len(operator_records) > 0, (
            f"No operator action logs found. All records: "
            f"{[(r.name, r.getMessage()) for r in caplog.records]}"
        )

        # Check that the log contains structured context with all D6 fields
        for record in operator_records:
            if hasattr(record, "ctx"):
                ctx = record.ctx
                # Verify all D6 schema fields per AC #10
                assert "action" in ctx, f"Missing 'action' in D6 log: {ctx}"
                assert "strategy_id" in ctx, f"Missing 'strategy_id' in D6 log: {ctx}"
                assert "timestamp" in ctx, f"Missing 'timestamp' in D6 log: {ctx}"
                assert "run_id" in ctx, f"Missing 'run_id' in D6 log: {ctx}"
                assert "config_hash" in ctx, f"Missing 'config_hash' in D6 log: {ctx}"
                # Verify values are non-empty
                assert ctx["run_id"], "run_id must not be empty"
                assert ctx["config_hash"], "config_hash must not be empty"
                break
        else:
            pytest.fail(
                "No structured D6 log record with 'ctx' attribute found. "
                f"Records: {[(r.name, r.getMessage()) for r in caplog.records]}"
            )


# ---------------------------------------------------------------------------
# Regression tests — written during review synthesis to prevent recurrence
# ---------------------------------------------------------------------------

class TestRegressions:

    @pytest.mark.regression
    def test_refine_returns_to_strategy_ready_not_backtest_running(self, tmp_path):
        """H1 regression: AC #6 requires refine → STRATEGY_READY, not BACKTEST_RUNNING.

        The original implementation returned to BACKTEST_RUNNING, violating AC #6
        which states 'the strategy returns to STRATEGY_READY for modification
        and re-submission'.
        """
        config = _make_config(tmp_path)
        strategy_id = "refine-regression"

        state = _make_state(strategy_id=strategy_id, stage="review-pending")
        _write_state(state, tmp_path)

        from orchestrator.operator_actions import refine_stage
        result = refine_stage(strategy_id, "Need to adjust parameters", config)

        assert result["to_stage"] == "strategy-ready", (
            f"Refine must return to strategy-ready (AC #6), got {result['to_stage']}"
        )

        # Also verify at gate_manager level
        from orchestrator.gate_manager import GateManager
        gm = GateManager()
        state2 = _make_state(strategy_id="gm-refine", stage="review-pending")
        decision = GateDecision(
            stage="review-pending",
            decision="refine",
            reason="test",
            decided_at="2026-01-01T00:00:00.000Z",
        )
        gm.advance(state2, decision)
        assert state2.current_stage == "strategy-ready"

    @pytest.mark.regression
    def test_no_dead_import_assemble_evidence_pack(self):
        """M1 regression: assemble_evidence_pack should not be imported if unused."""
        source_path = (
            Path(__file__).resolve().parent.parent.parent
            / "orchestrator" / "operator_actions.py"
        )
        source = source_path.read_text(encoding="utf-8")
        assert "from analysis.evidence_pack import assemble_evidence_pack" not in source, (
            "Dead import 'assemble_evidence_pack' should not be in operator_actions.py"
        )

    @pytest.mark.regression
    def test_run_backtest_error_path_has_valid_run_id(self, tmp_path):
        """L2 regression: error path must generate a UUID run_id, not empty string."""
        from unittest.mock import patch, MagicMock

        config = _make_config(tmp_path)

        with patch("orchestrator.operator_actions.StageRunner") as mock_cls, \
             patch("rust_bridge.batch_runner.BatchRunner", autospec=True), \
             patch("rust_bridge.backtest_executor.BacktestExecutor", autospec=True):
            mock_runner = MagicMock()
            mock_runner.run.side_effect = RuntimeError("Simulated crash")
            mock_cls.return_value = mock_runner

            from orchestrator.operator_actions import run_backtest
            result = run_backtest("crash-test", config)

        assert result["status"] == "failed"
        assert result["run_id"], "run_id must not be empty on error path"
        # Verify it looks like a UUID (36 chars with dashes)
        assert len(result["run_id"]) == 36, (
            f"run_id should be a UUID, got: {result['run_id']}"
        )

    @pytest.mark.regression
    def test_d6_log_schema_requires_all_fields(self, tmp_path, caplog):
        """M3 regression: D6 log must include run_id and config_hash, not just action."""
        import logging
        caplog.set_level(logging.INFO)

        config = _make_config(tmp_path)
        strategy_id = "d6-regression"

        state = _make_state(strategy_id=strategy_id, stage="review-pending")
        _write_state(state, tmp_path)

        from orchestrator.operator_actions import advance_stage
        advance_stage(strategy_id, "D6 test", config)

        d6_fields = {"action", "strategy_id", "timestamp", "run_id", "config_hash"}
        for record in caplog.records:
            if hasattr(record, "ctx") and isinstance(record.ctx, dict):
                ctx = record.ctx
                if "action" in ctx:
                    missing = d6_fields - set(ctx.keys())
                    assert not missing, (
                        f"D6 log missing required fields: {missing}. Got: {set(ctx.keys())}"
                    )
                    for field in d6_fields:
                        assert ctx[field], f"D6 field '{field}' must not be empty"
                    return

        pytest.fail("No D6-compliant log record found in caplog")
