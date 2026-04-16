"""Stage runner — sequential stage execution with pluggable executors (D3).

The runner orchestrates stage progression but does NOT implement actual stage
logic. Concrete executors are registered per stage and injected via the
``StageExecutor`` protocol. Stories 3-4 through 3-7 provide real executors.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from config_loader import compute_config_hash
from logging_setup.setup import get_logger, LogContext
from orchestrator.errors import PipelineError, handle_error
from orchestrator.gate_manager import GateManager, PipelineStatus
from orchestrator.recovery import recover_from_checkpoint, startup_cleanup, verify_last_artifact
from orchestrator.pipeline_state import (
    CompletedStage,
    PipelineStage,
    PipelineState,
    STAGE_GRAPH,
    STAGE_ORDER,
    TransitionType,
)

logger = get_logger("pipeline.orchestrator")


# ---------------------------------------------------------------------------
# StageExecutor protocol
# ---------------------------------------------------------------------------

@dataclass
class StageResult:
    artifact_path: str | None = None
    manifest_ref: str | None = None
    outcome: str = "success"  # "success" | "failed"
    metrics: dict = field(default_factory=dict)
    error: PipelineError | None = None


class StageExecutor(Protocol):
    """Protocol for pluggable stage executors."""

    def execute(self, strategy_id: str, context: dict) -> StageResult:
        """Execute a pipeline stage. Returns typed StageResult."""
        ...

    def validate_artifact(self, artifact_path: Path, manifest_ref: Path) -> bool:
        """Verify artifact integrity via manifest hash after crash."""
        ...


# ---------------------------------------------------------------------------
# NoOp executor for testing
# ---------------------------------------------------------------------------

class NoOpExecutor:
    """Stub executor returning synthetic results for orchestrator testing."""

    def execute(self, strategy_id: str, context: dict) -> StageResult:
        return StageResult(
            artifact_path=None,
            manifest_ref=None,
            outcome="success",
            metrics={"noop": True},
        )

    def validate_artifact(self, artifact_path: Path, manifest_ref: Path) -> bool:
        return True


# ---------------------------------------------------------------------------
# Pipeline config
# ---------------------------------------------------------------------------

@dataclass
class PipelineConfig:
    """Configuration extracted from TOML [pipeline] section (D7)."""
    artifacts_dir: str = "artifacts"
    checkpoint_enabled: bool = True
    retry_max_attempts: int = 3
    retry_backoff_base_s: float = 2.0
    gated_stages: list[str] = field(default_factory=lambda: ["review-pending", "validation-complete"])
    checkpoint_granularity: int = 1000

    @classmethod
    def from_dict(cls, config: dict) -> PipelineConfig:
        """Build from full config dict (expects [pipeline] section)."""
        pipeline = config.get("pipeline", {})
        return cls(
            artifacts_dir=pipeline["artifacts_dir"],
            checkpoint_enabled=pipeline["checkpoint_enabled"],
            retry_max_attempts=pipeline["retry_max_attempts"],
            retry_backoff_base_s=pipeline["retry_backoff_base_s"],
            gated_stages=pipeline["gated_stages"],
            checkpoint_granularity=pipeline["checkpoint_granularity"],
        )


# ---------------------------------------------------------------------------
# StageRunner
# ---------------------------------------------------------------------------

class StageRunner:
    """Orchestrates sequential pipeline execution with checkpoint/resume."""

    def __init__(
        self,
        strategy_id: str,
        artifacts_dir: Path,
        config: PipelineConfig,
        full_config: dict | None = None,
        executors: dict[PipelineStage, StageExecutor] | None = None,
    ):
        self.strategy_id = strategy_id
        self.artifacts_dir = artifacts_dir
        self.config = config
        self.gate_manager = GateManager()
        self._executors: dict[PipelineStage, StageExecutor] = executors or {}
        self._state_path = artifacts_dir / strategy_id / "pipeline-state.json"
        self._full_config = full_config or {}
        self._config_hash = compute_config_hash(self._full_config)

    def run(self) -> PipelineState:
        """Initialize a new pipeline run and execute stages sequentially."""
        now = _now_iso()
        run_id = str(uuid.uuid4())

        state = PipelineState(
            strategy_id=self.strategy_id,
            run_id=run_id,
            current_stage=PipelineStage.DATA_READY.value,
            pending_stages=[s.value for s in STAGE_ORDER[1:]],
            created_at=now,
            last_transition_at=now,
            config_hash=self._config_hash,
        )
        state.save(self._state_path)

        logger.info(
            "Pipeline run started",
            extra={
                "component": "pipeline.orchestrator",
                "stage": state.current_stage,
                "strategy_id": self.strategy_id,
                "ctx": {"run_id": run_id, "config_hash": self._config_hash},
            },
        )

        return self._execute_stages(state)

    def resume(self) -> PipelineState:
        """Resume an interrupted pipeline run.

        Recovery ordering (per recovery.py contract):
        1. Load pipeline state
        2. Run startup cleanup (safe partial file removal)
        3. Verify last completed artifact via executor
        4. Recover within-stage checkpoint
        5. Assign new run_id and continue execution
        """
        state = PipelineState.load(self._state_path)
        old_run_id = state.run_id
        state.run_id = str(uuid.uuid4())

        # Warn if config has changed since last run
        if state.config_hash and state.config_hash != self._config_hash:
            logger.warning(
                "Config hash mismatch on resume — pipeline config has changed",
                extra={
                    "component": "pipeline.orchestrator",
                    "stage": state.current_stage,
                    "strategy_id": self.strategy_id,
                    "ctx": {
                        "old_hash": state.config_hash,
                        "new_hash": self._config_hash,
                        "old_run_id": old_run_id,
                        "new_run_id": state.run_id,
                    },
                },
            )

        # Step 2: Startup cleanup — remove orphaned .partial files
        startup_cleanup(self.strategy_id, self.artifacts_dir, state=state)

        # Step 3: Verify last completed artifact (AC #4)
        # Use the executor for the *last completed* stage (the one that produced
        # the artifact), not the current stage we're about to enter.
        last_completed_stage = None
        if state.completed_stages:
            last_completed_stage = PipelineStage(state.completed_stages[-1].stage)
        executor = self._executors.get(last_completed_stage) if last_completed_stage else None
        if executor is not None and not verify_last_artifact(state, executor):
            logger.error(
                "Last artifact verification failed on resume — cannot continue",
                extra={
                    "component": "pipeline.orchestrator",
                    "stage": state.current_stage,
                    "strategy_id": self.strategy_id,
                    "ctx": {"run_id": state.run_id},
                },
            )
            state.error = PipelineError(
                code="ARTIFACT_VERIFICATION_FAILED",
                category="data_logic",
                severity="error",
                recoverable=False,
                action="stop_checkpoint",
                component="pipeline.recovery",
                msg="Last completed artifact failed integrity verification on resume",
            ).to_dict()
            state.config_hash = self._config_hash
            state.save(self._state_path)
            return state

        # Step 4: Recover within-stage checkpoint (AC #5)
        checkpoint = recover_from_checkpoint(self.strategy_id, self.artifacts_dir)
        if checkpoint is not None:
            state.checkpoint = checkpoint
            logger.info(
                f"Within-stage checkpoint recovered for {checkpoint.stage}",
                extra={
                    "component": "pipeline.orchestrator",
                    "stage": state.current_stage,
                    "strategy_id": self.strategy_id,
                    "ctx": {
                        "progress_pct": checkpoint.progress_pct,
                        "last_batch": checkpoint.last_completed_batch,
                    },
                },
            )

        state.config_hash = self._config_hash
        state.save(self._state_path)

        logger.info(
            "Pipeline run resumed",
            extra={
                "component": "pipeline.orchestrator",
                "stage": state.current_stage,
                "strategy_id": self.strategy_id,
                "ctx": {
                    "old_run_id": old_run_id,
                    "new_run_id": state.run_id,
                },
            },
        )

        return self._execute_stages(state)

    def get_status(self) -> PipelineStatus:
        """Return current pipeline status for operator queries (FR40)."""
        state = PipelineState.load(self._state_path)
        return self.gate_manager.get_status(state)

    # ------------------------------------------------------------------
    # Internal execution
    # ------------------------------------------------------------------

    def _execute_stages(self, state: PipelineState) -> PipelineState:
        """Walk through stages from current_stage to completion."""
        while True:
            current = PipelineStage(state.current_stage)

            # Check if we're at terminal stage
            transition = STAGE_GRAPH.get(current)
            if transition is None:
                logger.info(
                    "Pipeline complete — reached terminal stage",
                    extra={
                        "component": "pipeline.orchestrator",
                        "stage": state.current_stage,
                        "strategy_id": self.strategy_id,
                        "ctx": {"run_id": state.run_id},
                    },
                )
                break

            # Gated transitions stop and wait for operator decision
            if transition.transition_type == TransitionType.GATED:
                logger.info(
                    f"Gated transition at {current.value} — awaiting operator decision",
                    extra={
                        "component": "pipeline.orchestrator",
                        "stage": state.current_stage,
                        "strategy_id": self.strategy_id,
                        "ctx": {"run_id": state.run_id},
                    },
                )
                state.save(self._state_path)
                break

            # Execute the current stage
            state = self._execute_stage(state, current)

            if state.error is not None:
                break

            # Check automatic transition preconditions AFTER execution (AC #2)
            # Preconditions verify: stage completed successfully, artifact valid,
            # no unresolved errors — these gate the transition, not the execution.
            executor = self._executors.get(current)
            met, reason = self.gate_manager.check_preconditions(
                state, current, artifacts_dir=self.artifacts_dir, executor=executor,
            )
            if not met:
                logger.warning(
                    f"Preconditions not met for {current.value}: {reason}",
                    extra={
                        "component": "pipeline.orchestrator",
                        "stage": state.current_stage,
                        "strategy_id": self.strategy_id,
                        "ctx": {"run_id": state.run_id, "reason": reason},
                    },
                )
                state.save(self._state_path)
                break

            # Transition to next stage
            state.current_stage = transition.to_stage.value
            state.last_transition_at = _now_iso()
            state.pending_stages = GateManager.compute_pending(state.current_stage)
            state.checkpoint = None  # Clear within-stage checkpoint on transition
            state.error = None

            logger.info(
                f"Stage transition: {current.value} → {transition.to_stage.value}",
                extra={
                    "component": "pipeline.orchestrator",
                    "stage": state.current_stage,
                    "strategy_id": self.strategy_id,
                    "ctx": {
                        "from_stage": current.value,
                        "to_stage": transition.to_stage.value,
                        "transition_type": transition.transition_type.value,
                    },
                },
            )

            state.save(self._state_path)

        return state

    def _execute_stage(self, state: PipelineState, stage: PipelineStage) -> PipelineState:
        """Execute a single stage via its registered executor.

        Implements D8 behavioral responses:
        - resource_pressure: throttle and continue (retry once)
        - data_logic: stop and checkpoint
        - external_failure: retry with exponential backoff up to max_attempts
        """
        executor = self._executors.get(stage)
        if executor is None:
            logger.warning(
                f"No executor registered for {stage.value} — skipping",
                extra={
                    "component": "pipeline.orchestrator",
                    "stage": stage.value,
                    "strategy_id": self.strategy_id,
                    "ctx": {"run_id": state.run_id},
                },
            )
            state.completed_stages.append(CompletedStage(
                stage=stage.value,
                completed_at=_now_iso(),
                outcome="skipped",
            ))
            return state

        with LogContext(stage=stage.value, strategy_id=self.strategy_id):
            logger.info(
                f"Stage entry: {stage.value}",
                extra={
                    "component": "pipeline.orchestrator",
                    "stage": stage.value,
                    "strategy_id": self.strategy_id,
                    "ctx": {"run_id": state.run_id},
                },
            )

            start = datetime.now(timezone.utc)
            max_attempts = self.config.retry_max_attempts
            save_fn = lambda: state.save(self._state_path)

            result = None
            for attempt in range(max_attempts + 1):
                try:
                    context = self._build_executor_context()
                    context["backtest_run_id"] = state.run_id
                    result = executor.execute(
                        self.strategy_id, context
                    )
                    break  # Success — exit retry loop
                except Exception as exc:
                    error = _classify_exception(exc, stage)
                    state = handle_error(
                        error, state,
                        save_fn=save_fn,
                        retry_max_attempts=max_attempts,
                        retry_backoff_base_s=self.config.retry_backoff_base_s,
                        attempt=attempt,
                        is_last_attempt=(attempt >= max_attempts),
                    )

                    if error.category == "resource_pressure":
                        # D8: throttle and retry once more
                        if attempt < max_attempts:
                            continue
                        return state

                    if error.category == "external_failure":
                        # D8: retry with backoff
                        if attempt < max_attempts:
                            continue
                        # Retries exhausted
                        logger.error(
                            f"External failure: retries exhausted ({max_attempts})",
                            extra={
                                "component": "pipeline.orchestrator",
                                "stage": stage.value,
                                "strategy_id": self.strategy_id,
                                "ctx": {"run_id": state.run_id},
                            },
                        )
                        return state

                    # data_logic or unknown: stop immediately
                    return state

            if result is None:
                return state

            elapsed = (datetime.now(timezone.utc) - start).total_seconds()

            # Handle errors reported via StageResult (executor didn't raise)
            if result.error is not None:
                state = handle_error(
                    result.error, state,
                    save_fn=save_fn,
                    retry_max_attempts=max_attempts,
                    retry_backoff_base_s=self.config.retry_backoff_base_s,
                )
                if result.outcome == "failed":
                    state.completed_stages.append(CompletedStage(
                        stage=stage.value,
                        completed_at=_now_iso(),
                        artifact_path=result.artifact_path,
                        manifest_ref=result.manifest_ref,
                        duration_s=elapsed,
                        outcome="failed",
                    ))
                    # Persist failed stage metadata to disk (Codex H4)
                    state.save(self._state_path)
                return state

            state.completed_stages.append(CompletedStage(
                stage=stage.value,
                completed_at=_now_iso(),
                artifact_path=result.artifact_path,
                manifest_ref=result.manifest_ref,
                duration_s=elapsed,
                outcome=result.outcome,
            ))

            logger.info(
                f"Stage completion: {stage.value}",
                extra={
                    "component": "pipeline.orchestrator",
                    "stage": stage.value,
                    "strategy_id": self.strategy_id,
                    "ctx": {
                        "run_id": state.run_id,
                        "duration_s": elapsed,
                        "outcome": result.outcome,
                    },
                },
            )

            # Post-stage hook: generate evidence pack after result processing
            # (ResultExecutor in BACKTEST_COMPLETE creates the SQLite DB needed)
            if stage == PipelineStage.BACKTEST_COMPLETE and result.outcome == "success":
                self._generate_evidence_pack(state, result)

        return state

    def _build_executor_context(self) -> dict:
        """Build context dict for executor from config and pipeline state.

        Path resolution strategy (in priority order):
        1. Explicit paths from [backtesting] config section (if present)
        2. Convention-based derivation from strategy_id and config:
           - strategy_spec: artifacts/strategies/{strategy_id}/v001.toml
           - cost_model: artifacts/cost_models/{pair}/{version}.json
             (pair and version read from the strategy spec)
           - market_data: {data.storage_path}/arrow/{pair}_2025_full/v1/market-data.arrow
        """
        backtesting = self._full_config.get("backtesting", {})
        pipeline = self._full_config.get("pipeline", {})

        # Resolve output directory — use version-aware path
        strategy_dir = self.artifacts_dir / self.strategy_id
        existing = sorted(
            [d.name for d in strategy_dir.iterdir()
             if d.is_dir() and d.name.startswith("v")]
        ) if strategy_dir.exists() else []
        next_ver = f"v{len(existing) + 1:03d}" if existing else "v001"
        output_dir = strategy_dir / next_ver / "backtest"

        # --- Strategy spec path ---
        strategy_spec_path = backtesting.get("strategy_spec_path", "")
        if not strategy_spec_path:
            strategy_spec_path = str(
                self.artifacts_dir / "strategies" / self.strategy_id / "v001.toml"
            )

        # --- Cost model and market data: derive from strategy spec metadata ---
        cost_model_path = backtesting.get("cost_model_path", "")
        market_data_path = backtesting.get("dataset_path", "")

        if not cost_model_path or not market_data_path:
            # Read pair and cost_model version from the strategy spec
            pair = "EURUSD"  # fallback
            cost_model_version = "v001"  # fallback
            spec_path = Path(strategy_spec_path)
            if spec_path.exists():
                try:
                    import tomllib
                    with open(spec_path, "rb") as f:
                        spec_data = tomllib.load(f)
                    pair = spec_data.get("metadata", {}).get("pair", pair)
                    cost_model_version = (
                        spec_data.get("cost_model_reference", {})
                        .get("version", cost_model_version)
                    )
                except Exception:
                    pass  # Use fallbacks

            if not cost_model_path:
                cost_model_path = str(
                    self.artifacts_dir / "cost_models" / pair / f"{cost_model_version}.json"
                )

            if not market_data_path:
                storage_path = self._full_config.get("data", {}).get(
                    "storage_path", ""
                )
                if storage_path:
                    market_data_path = str(
                        Path(storage_path) / "arrow" / f"{pair}_2025_full" / "v1" / "market-data.arrow"
                    )

        # rust_output_dir: latest existing version's backtest dir
        # (needed by ResultExecutor in BACKTEST_COMPLETE to find Rust output)
        if existing:
            rust_output_dir = str(strategy_dir / existing[-1] / "backtest")
        else:
            rust_output_dir = str(output_dir)

        return {
            "artifacts_dir": str(self.artifacts_dir),
            "strategy_spec_path": strategy_spec_path,
            "market_data_path": market_data_path,
            "cost_model_path": cost_model_path,
            "config_hash": self._config_hash,
            "memory_budget_mb": int(backtesting.get("memory_budget_mb", 4096)),
            "output_directory": backtesting.get(
                "output_directory", str(output_dir)),
            "rust_output_dir": rust_output_dir,
        }

    def _generate_evidence_pack(self, state: PipelineState, result: StageResult | None) -> None:
        """Generate evidence pack after backtest execution (Story 3-7).

        Failure is logged at WARNING and does NOT block pipeline transition.
        Story 3.8 detects availability by checking evidence_pack.json on disk.
        """
        try:
            from analysis.evidence_pack import assemble_evidence_pack

            backtest_id = state.run_id
            # db_path is at strategy level (where ResultProcessor writes it)
            strategy_dir = self.artifacts_dir / self.strategy_id
            db_path = strategy_dir / "pipeline.db"

            # Write a minimal manifest in the backtest output dir so
            # _find_version_dir can locate the correct version among many.
            for cs in reversed(state.completed_stages):
                if cs.stage == "backtest-running" and cs.artifact_path:
                    bt_dir = Path(cs.artifact_path)
                    if not bt_dir.is_absolute():
                        bt_dir = Path.cwd() / bt_dir
                    manifest_file = bt_dir / "manifest.json"
                    if bt_dir.exists() and not manifest_file.exists():
                        manifest_file.write_text(json.dumps({
                            "backtest_run_id": backtest_id,
                            "strategy_id": self.strategy_id,
                        }))
                    break

            pack = assemble_evidence_pack(
                backtest_id=backtest_id,
                db_path=db_path,
                artifacts_root=self.artifacts_dir,
            )

            logger.info(
                "Evidence pack generated after backtest",
                extra={
                    "component": "pipeline.orchestrator",
                    "stage": "backtest-complete",
                    "strategy_id": self.strategy_id,
                    "ctx": {
                        "backtest_id": backtest_id,
                        "anomaly_count": len(pack.anomalies.anomalies),
                    },
                },
            )

        except Exception as exc:
            logger.warning(
                f"Evidence pack generation failed: {exc}",
                extra={
                    "component": "pipeline.orchestrator",
                    "stage": "backtest-complete",
                    "strategy_id": self.strategy_id,
                    "ctx": {"error": str(exc)},
                },
            )


def _classify_exception(exc: Exception, stage: PipelineStage) -> PipelineError:
    """Map an exception to a D8 error category.

    Executors can raise a ``PipelineError`` directly (wrapped in a RuntimeError
    with a ``pipeline_error`` attribute) to signal a specific category.
    Otherwise, network/OS-level exceptions are classified as external_failure
    and everything else defaults to data_logic.
    """
    # If the executor attached a PipelineError, use it directly
    if hasattr(exc, "pipeline_error") and isinstance(exc.pipeline_error, PipelineError):
        return exc.pipeline_error

    # Heuristic classification based on exception type
    if isinstance(exc, (OSError, ConnectionError, TimeoutError)):
        return PipelineError(
            code="EXTERNAL_FAILURE",
            category="external_failure",
            severity="error",
            recoverable=True,
            action="retry_backoff",
            component=f"pipeline.{stage.value}",
            msg=str(exc),
            context={"stage": stage.value, "exception_type": type(exc).__name__},
        )

    if isinstance(exc, MemoryError):
        return PipelineError(
            code="RESOURCE_PRESSURE",
            category="resource_pressure",
            severity="warning",
            recoverable=True,
            action="throttle",
            component=f"pipeline.{stage.value}",
            msg=str(exc),
            context={"stage": stage.value, "exception_type": type(exc).__name__},
        )

    # Default: data/logic error
    return PipelineError(
        code="STAGE_EXECUTION_ERROR",
        category="data_logic",
        severity="error",
        recoverable=False,
        action="stop_checkpoint",
        component=f"pipeline.{stage.value}",
        msg=str(exc),
        context={"stage": stage.value, "exception_type": type(exc).__name__},
    )


def _now_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
