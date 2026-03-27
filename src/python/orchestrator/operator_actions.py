"""Operator pipeline actions — single mutation surface for all pipeline operations (D9).

Thin composition layer over existing orchestrator, analysis, and artifact modules.
Each function is a structured operation invoked by the /pipeline skill and designed
as the backing implementation for future REST API endpoints (Epic 4).

No profitability gating (FR41): no function inspects P&L, profit_factor, Sharpe,
or any performance metric to gate progression.
"""
from __future__ import annotations

import json
import platform
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analysis.models import EvidencePack
from config_loader import compute_config_hash, load_config
from logging_setup.setup import get_logger
from orchestrator.errors import PipelineError
from orchestrator.gate_manager import GateManager
from orchestrator.pipeline_state import (
    GateDecision,
    PipelineStage,
    PipelineState,
)
from orchestrator.stage_runner import PipelineConfig, StageRunner

logger = get_logger("pipeline.operator")


def _now_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _resolve_artifacts_dir(config: dict) -> Path:
    """Resolve artifacts directory from config."""
    pipeline = config.get("pipeline", {})
    return Path(pipeline.get("artifacts_dir", "artifacts"))


def _resolve_binary_path(config: dict) -> Path:
    """Resolve Rust backtester binary path from config or default."""
    backtesting = config.get("backtesting", {})
    explicit = backtesting.get("binary_path")
    if explicit:
        return Path(explicit)
    # Default: project root / src/rust/target/debug/forex_backtester[.exe]
    project_root = Path(__file__).resolve().parents[3]
    name = "forex_backtester.exe" if platform.system() == "Windows" else "forex_backtester"
    return project_root / "src" / "rust" / "target" / "debug" / name


def _load_state(strategy_id: str, artifacts_dir: Path) -> PipelineState:
    """Load pipeline state for a strategy."""
    state_path = artifacts_dir / strategy_id / "pipeline-state.json"
    if not state_path.exists():
        raise FileNotFoundError(
            f"No pipeline state found for strategy '{strategy_id}' "
            f"at {state_path}"
        )
    return PipelineState.load(state_path)


def _state_path(strategy_id: str, artifacts_dir: Path) -> Path:
    return artifacts_dir / strategy_id / "pipeline-state.json"


def _find_latest_evidence_pack(
    strategy_id: str, artifacts_dir: Path,
) -> str | None:
    """Find the latest evidence pack path for a strategy by scanning versions."""
    strategy_dir = artifacts_dir / strategy_id
    if not strategy_dir.exists():
        return None

    version_dirs = sorted(
        [d for d in strategy_dir.iterdir() if d.is_dir() and d.name.startswith("v")],
        reverse=True,
    )

    for vdir in version_dirs:
        pack_path = vdir / "backtest" / "evidence_pack.json"
        if pack_path.exists():
            return str(pack_path)

    return None


def _log_action(
    action: str,
    strategy_id: str,
    run_id: str,
    config_hash: str,
    decision: str | None = None,
    reason: str | None = None,
    **extra: Any,
) -> None:
    """Log operator action with unified D6 schema."""
    log_data = {
        "action": action,
        "strategy_id": strategy_id,
        "run_id": run_id,
        "config_hash": config_hash,
        "timestamp": _now_iso(),
    }
    if decision is not None:
        log_data["decision"] = decision
    if reason is not None:
        log_data["reason"] = reason
    log_data.update(extra)

    logger.info(
        f"Operator action: {action}",
        extra={
            "component": "pipeline.operator",
            "strategy_id": strategy_id,
            "ctx": log_data,
        },
    )


# ---------------------------------------------------------------------------
# Public API — operator actions
# ---------------------------------------------------------------------------


def run_backtest(strategy_id: str, config: dict) -> dict:
    """Run a backtest for a strategy through the pipeline.

    Creates a PipelineState if none exists (new run), otherwise resumes.
    Invokes StageRunner with BacktestExecutor registered for BACKTEST_RUNNING.
    On success, triggers evidence pack assembly.

    Returns:
        dict with status, output_dir, evidence_pack_path, backtest_id, run_id,
        config_hash, and error fields.
    """
    artifacts_dir = _resolve_artifacts_dir(config)
    config_hash = compute_config_hash(config)
    pipeline_config = PipelineConfig.from_dict(config)
    error_run_id = str(uuid.uuid4())

    # Import BacktestExecutor lazily to avoid circular imports
    from rust_bridge.backtest_executor import BacktestExecutor
    from rust_bridge.batch_runner import BatchRunner

    binary_path = _resolve_binary_path(config)
    timeout = config.get("backtesting", {}).get("timeout_s", 300)
    runner_instance = BatchRunner(binary_path=binary_path, timeout=timeout)
    session_schedule = config.get("sessions", {})
    executor = BacktestExecutor(
        runner=runner_instance,
        session_schedule=session_schedule if session_schedule else None,
    )

    executors = {PipelineStage.BACKTEST_RUNNING: executor}

    runner = StageRunner(
        strategy_id=strategy_id,
        artifacts_dir=artifacts_dir,
        config=pipeline_config,
        full_config=config,
        executors=executors,
    )

    state_path = _state_path(strategy_id, artifacts_dir)

    try:
        if state_path.exists():
            state = runner.resume()
        else:
            state = runner.run()
    except Exception as exc:
        _log_action(
            "run_backtest", strategy_id,
            run_id=error_run_id, config_hash=config_hash,
            error=str(exc),
        )
        return {
            "status": "failed",
            "output_dir": str(artifacts_dir / strategy_id),
            "evidence_pack_path": None,
            "backtest_id": None,
            "run_id": error_run_id,
            "config_hash": config_hash,
            "error": str(exc),
        }

    # Check for errors in state
    if state.error is not None:
        _log_action(
            "run_backtest", strategy_id,
            run_id=state.run_id, config_hash=state.config_hash,
            error=state.error.get("msg", "unknown"),
        )
        return {
            "status": "failed",
            "output_dir": str(artifacts_dir / strategy_id),
            "evidence_pack_path": None,
            "backtest_id": state.run_id,
            "run_id": state.run_id,
            "config_hash": state.config_hash,
            "error": state.error.get("msg", "unknown"),
        }

    # Try to find evidence pack
    evidence_pack_path = _find_latest_evidence_pack(strategy_id, artifacts_dir)

    _log_action(
        "run_backtest", strategy_id,
        run_id=state.run_id, config_hash=state.config_hash,
    )

    return {
        "status": "success",
        "output_dir": str(artifacts_dir / strategy_id),
        "evidence_pack_path": evidence_pack_path,
        "backtest_id": state.run_id,
        "run_id": state.run_id,
        "config_hash": state.config_hash,
        "error": None,
    }


def get_pipeline_status(config: dict) -> list[dict]:
    """Get pipeline status for all strategies.

    Scans the artifacts directory for pipeline-state.json files and
    builds a status snapshot for each.

    Returns:
        List of status dicts, one per strategy.
    """
    artifacts_dir = _resolve_artifacts_dir(config)

    if not artifacts_dir.exists():
        return []

    results: list[dict] = []
    gate_manager = GateManager()

    for strategy_dir in sorted(artifacts_dir.iterdir()):
        if not strategy_dir.is_dir():
            continue

        state_file = strategy_dir / "pipeline-state.json"
        if not state_file.exists():
            continue

        try:
            state = PipelineState.load(state_file)
            status = gate_manager.get_status(state)

            # Count anomalies from evidence pack if available
            anomaly_count = 0
            evidence_pack_ref = _find_latest_evidence_pack(
                state.strategy_id, artifacts_dir,
            )
            if evidence_pack_ref:
                try:
                    pack_data = json.loads(
                        Path(evidence_pack_ref).read_text(encoding="utf-8")
                    )
                    anomaly_count = len(
                        pack_data.get("anomalies", {}).get("anomalies", [])
                    )
                except (json.JSONDecodeError, OSError, KeyError):
                    pass

            results.append({
                "strategy_id": state.strategy_id,
                "stage": status.stage,
                "progress_pct": status.progress_pct,
                "last_transition_at": status.last_transition_at,
                "gate_status": status.gate_status,
                "decision_required": status.decision_required,
                "anomaly_count": anomaly_count,
                "run_id": status.run_id,
                "config_hash": status.config_hash,
                "last_outcome": status.last_outcome,
                "blocking_reason": status.blocking_reason,
                "evidence_pack_ref": evidence_pack_ref,
            })

        except Exception as exc:
            logger.warning(
                f"Failed to load status for {strategy_dir.name}: {exc}",
                extra={
                    "component": "pipeline.operator",
                    "ctx": {"strategy_dir": str(strategy_dir), "error": str(exc)},
                },
            )

    return results


def load_evidence_pack(
    strategy_id: str,
    config: dict,
    evidence_pack_ref: str | None = None,
) -> dict | None:
    """Load evidence pack for a strategy.

    State-driven lookup: if evidence_pack_ref is provided, loads from that
    exact path. Otherwise falls back to scanning for the latest version.

    Returns:
        Dict with all 11 EvidencePack fields, or None if no evidence pack exists.
    """
    artifacts_dir = _resolve_artifacts_dir(config)

    # Determine path to load from
    if evidence_pack_ref is not None:
        pack_path = Path(evidence_pack_ref)
        if not pack_path.is_absolute():
            pack_path = artifacts_dir / pack_path
    else:
        ref = _find_latest_evidence_pack(strategy_id, artifacts_dir)
        if ref is None:
            return None
        pack_path = Path(ref)

    if not pack_path.exists():
        return None

    try:
        pack_data = json.loads(pack_path.read_text(encoding="utf-8"))
        pack = EvidencePack.from_json(pack_data)

        _log_action(
            "load_evidence_pack", strategy_id,
            run_id=pack.backtest_id,
            config_hash=pack.metadata.get("config_hash", ""),
            evidence_pack_path=str(pack_path),
        )

        return pack.to_json()

    except (json.JSONDecodeError, OSError, KeyError, TypeError) as exc:
        logger.error(
            f"Failed to load evidence pack: {exc}",
            extra={
                "component": "pipeline.operator",
                "strategy_id": strategy_id,
                "ctx": {"path": str(pack_path), "error": str(exc)},
            },
        )
        return None


def advance_stage(strategy_id: str, reason: str, config: dict) -> dict:
    """Accept and advance strategy to the next pipeline stage.

    Creates a GateDecision(decision="accept") and applies it via GateManager.
    Never inspects P&L metrics (FR41).

    Returns:
        dict with strategy_id, from_stage, to_stage, decided_at.
    """
    artifacts_dir = _resolve_artifacts_dir(config)
    state = _load_state(strategy_id, artifacts_dir)
    sp = _state_path(strategy_id, artifacts_dir)

    from_stage = state.current_stage
    now = _now_iso()

    # Find latest evidence pack reference for the decision record
    evidence_ref = _find_latest_evidence_pack(strategy_id, artifacts_dir)

    decision = GateDecision(
        stage=state.current_stage,
        decision="accept",
        reason=reason,
        decided_at=now,
        evidence_pack_ref=evidence_ref,
    )

    gate_manager = GateManager()
    state = gate_manager.advance(state, decision, state_path=sp)

    _log_action(
        "advance", strategy_id,
        run_id=state.run_id, config_hash=state.config_hash,
        decision="accept", reason=reason,
        from_stage=from_stage, to_stage=state.current_stage,
    )

    return {
        "strategy_id": strategy_id,
        "from_stage": from_stage,
        "to_stage": state.current_stage,
        "decided_at": now,
    }


def reject_stage(strategy_id: str, reason: str, config: dict) -> dict:
    """Reject strategy at current gate with operator-provided reason.

    Creates a GateDecision(decision="reject"). Strategy stays at current stage.

    Returns:
        dict with strategy_id, stage, decision, reason, decided_at.
    """
    artifacts_dir = _resolve_artifacts_dir(config)
    state = _load_state(strategy_id, artifacts_dir)
    sp = _state_path(strategy_id, artifacts_dir)

    now = _now_iso()

    evidence_ref = _find_latest_evidence_pack(strategy_id, artifacts_dir)

    decision = GateDecision(
        stage=state.current_stage,
        decision="reject",
        reason=reason,
        decided_at=now,
        evidence_pack_ref=evidence_ref,
    )

    gate_manager = GateManager()
    gate_manager.advance(state, decision, state_path=sp)

    _log_action(
        "reject", strategy_id,
        run_id=state.run_id, config_hash=state.config_hash,
        decision="reject", reason=reason,
    )

    return {
        "strategy_id": strategy_id,
        "stage": state.current_stage,
        "decision": "reject",
        "reason": reason,
        "decided_at": now,
    }


def refine_stage(strategy_id: str, reason: str, config: dict) -> dict:
    """Refine strategy — return to STRATEGY_READY for modification and re-submission.

    Creates a GateDecision(decision="refine"). Strategy returns to
    STRATEGY_READY stage without losing prior run history.

    Returns:
        dict with strategy_id, from_stage, to_stage, decision, reason, decided_at.
    """
    artifacts_dir = _resolve_artifacts_dir(config)
    state = _load_state(strategy_id, artifacts_dir)
    sp = _state_path(strategy_id, artifacts_dir)

    from_stage = state.current_stage
    now = _now_iso()

    evidence_ref = _find_latest_evidence_pack(strategy_id, artifacts_dir)

    decision = GateDecision(
        stage=state.current_stage,
        decision="refine",
        reason=reason,
        decided_at=now,
        evidence_pack_ref=evidence_ref,
    )

    gate_manager = GateManager()
    state = gate_manager.advance(state, decision, state_path=sp)

    _log_action(
        "refine", strategy_id,
        run_id=state.run_id, config_hash=state.config_hash,
        decision="refine", reason=reason,
        from_stage=from_stage, to_stage=state.current_stage,
    )

    return {
        "strategy_id": strategy_id,
        "from_stage": from_stage,
        "to_stage": state.current_stage,
        "decision": "refine",
        "reason": reason,
        "decided_at": now,
    }


def resume_pipeline(
    strategy_id: str | None, config: dict,
) -> list[dict]:
    """Resume interrupted pipeline runs.

    If strategy_id is None, scans artifacts dir for all strategies with
    interrupted runs (checkpoint or error present in state).

    Returns:
        List of dicts with strategy_id, resumed_from_stage, checkpoint_found.
    """
    artifacts_dir = _resolve_artifacts_dir(config)
    pipeline_config = PipelineConfig.from_dict(config)

    if not artifacts_dir.exists():
        return []

    # Determine which strategies to resume
    if strategy_id is not None:
        strategy_ids = [strategy_id]
    else:
        strategy_ids = []
        for strategy_dir in sorted(artifacts_dir.iterdir()):
            if not strategy_dir.is_dir():
                continue
            state_file = strategy_dir / "pipeline-state.json"
            if not state_file.exists():
                continue
            try:
                state = PipelineState.load(state_file)
                if state.checkpoint is not None or state.error is not None:
                    strategy_ids.append(state.strategy_id)
            except Exception:
                continue

    results: list[dict] = []

    for sid in strategy_ids:
        try:
            state_file = artifacts_dir / sid / "pipeline-state.json"
            if not state_file.exists():
                continue

            state = PipelineState.load(state_file)
            resumed_from = state.current_stage
            has_checkpoint = state.checkpoint is not None

            runner = StageRunner(
                strategy_id=sid,
                artifacts_dir=artifacts_dir,
                config=pipeline_config,
                full_config=config,
            )
            runner.resume()

            _log_action(
                "resume", sid,
                run_id=state.run_id, config_hash=state.config_hash,
                resumed_from_stage=resumed_from,
                checkpoint_found=has_checkpoint,
            )

            results.append({
                "strategy_id": sid,
                "resumed_from_stage": resumed_from,
                "checkpoint_found": has_checkpoint,
            })

        except Exception as exc:
            logger.error(
                f"Failed to resume pipeline for {sid}: {exc}",
                extra={
                    "component": "pipeline.operator",
                    "strategy_id": sid,
                    "ctx": {"error": str(exc)},
                },
            )

    return results
