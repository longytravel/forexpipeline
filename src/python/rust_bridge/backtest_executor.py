"""StageExecutor implementation for the BACKTEST_RUNNING pipeline stage (AC #1, #4, #8).

Bridges the async BatchRunner with the sync StageExecutor protocol from
Story 3-3. Registered with StageRunner for ``PipelineStage.BACKTEST_RUNNING``.

D14: Calls signal precompute before dispatching to Rust binary so that
all indicator columns are pre-computed in the Arrow IPC file.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from logging_setup.setup import get_logger
from orchestrator.errors import PipelineError
from orchestrator.signal_precompute import precompute_signals
from orchestrator.stage_runner import StageResult

from rust_bridge.batch_runner import BacktestJob, BatchRunner
from rust_bridge.error_parser import map_to_pipeline_error, parse_rust_error
from rust_bridge.output_verifier import BacktestOutputRef, validate_schemas, verify_output

logger = get_logger("pipeline.rust_bridge")


class BacktestExecutor:
    """StageExecutor for the backtest-running pipeline stage.

    Implements the ``StageExecutor`` protocol from Story 3-3:
    - ``execute(strategy_id, context)`` → ``StageResult``
    - ``validate_artifact(artifact_path, manifest_ref)`` → ``bool``

    The executor builds a ``BacktestJob`` from the pipeline context,
    dispatches it via ``BatchRunner``, verifies output files, and
    returns a ``StageResult``.
    """

    def __init__(self, runner: BatchRunner, verifier_fn=verify_output, session_schedule: dict | None = None):
        self._runner = runner
        self._verify = verifier_fn
        self._session_schedule = session_schedule

    def execute(self, strategy_id: str, context: dict) -> StageResult:
        """Build BacktestJob from context, dispatch, verify output, return StageResult.

        Expected context keys (populated by prior stages):
        - strategy_spec_path: Path to strategy TOML
        - market_data_path: Path to Arrow IPC market data
        - cost_model_path: Path to cost model JSON
        - config_hash: Pipeline config hash
        - memory_budget_mb: Memory budget for the Rust binary
        - output_directory: Where results should be written

        Optional context keys (fold-aware evaluation):
        - fold_boundaries: list of (start, end) pairs
        - embargo_bars: int
        - window_start: int
        - window_end: int
        - parameter_batch: list of dicts
        """
        # D14: Pre-compute indicator signals before dispatching to Rust
        try:
            enriched_path = self._precompute_signals(context)
            if enriched_path is not None:
                context = {**context, "market_data_path": str(enriched_path)}
        except Exception as e:
            logger.error(
                f"Signal precompute failed: {e}",
                extra={
                    "component": "pipeline.rust_bridge",
                    "ctx": {"strategy_id": strategy_id, "error": str(e)},
                },
            )
            return StageResult(
                outcome="failed",
                error=PipelineError(
                    code="SIGNAL_PRECOMPUTE_FAILED",
                    category="data_logic",
                    severity="error",
                    recoverable=False,
                    action="stop_checkpoint",
                    component="pipeline.signal_precompute",
                    msg=f"Signal pre-computation failed: {e}",
                    context={"strategy_id": strategy_id},
                ),
            )

        try:
            job = self._build_job(strategy_id, context)
        except (KeyError, TypeError, ValueError) as e:
            return StageResult(
                outcome="failed",
                error=PipelineError(
                    code="BACKTEST_JOB_BUILD_ERROR",
                    category="data_logic",
                    severity="error",
                    recoverable=False,
                    action="stop_checkpoint",
                    component="pipeline.rust_bridge",
                    msg=f"Failed to build backtest job: {e}",
                    context={"strategy_id": strategy_id},
                ),
            )

        # Bridge async/sync boundary: BatchRunner.dispatch() is async,
        # StageExecutor.execute() is sync per Story 3-3 protocol.
        try:
            # Check if we're already inside a running event loop
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Already in an event loop — run dispatch in a separate thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    lambda: asyncio.run(self._runner.dispatch(job))
                ).result()
        else:
            # No running loop — safe to use asyncio.run()
            result = asyncio.run(self._runner.dispatch(job))

        # Handle failure
        if result.exit_code != 0:
            rust_error = parse_rust_error(result.stderr)
            if rust_error is not None:
                pipeline_error = map_to_pipeline_error(rust_error)
            else:
                pipeline_error = PipelineError(
                    code="BACKTEST_PROCESS_FAILED",
                    category="data_logic",
                    severity="error",
                    recoverable=False,
                    action="stop_checkpoint",
                    component="pipeline.rust_bridge",
                    msg=f"Rust binary exited with code {result.exit_code}",
                    context={
                        "exit_code": result.exit_code,
                        "stderr": result.stderr[:500] if result.stderr else "",
                    },
                )

            return StageResult(
                outcome="failed",
                error=pipeline_error,
                metrics={"elapsed_seconds": result.elapsed_seconds},
            )

        # Verify output files
        try:
            output_ref = self._verify(job.output_directory, job.config_hash)
        except FileNotFoundError as e:
            return StageResult(
                outcome="failed",
                error=PipelineError(
                    code="BACKTEST_OUTPUT_VERIFICATION_FAILED",
                    category="data_logic",
                    severity="error",
                    recoverable=False,
                    action="stop_checkpoint",
                    component="pipeline.rust_bridge",
                    msg=str(e),
                    context={"output_dir": str(job.output_directory)},
                ),
                metrics={"elapsed_seconds": result.elapsed_seconds},
            )

        return StageResult(
            artifact_path=str(output_ref.output_dir),
            manifest_ref=None,  # Manifest creation is Story 3.6
            outcome="success",
            metrics={
                "elapsed_seconds": result.elapsed_seconds,
                "config_hash": job.config_hash,
            },
        )

    def validate_artifact(self, artifact_path: Path, manifest_ref: Path) -> bool:
        """Verify artifact file exists and Arrow schema matches contracts.

        Note: Full manifest-based hash validation is Story 3.6's responsibility.
        Returns True if valid.
        """
        artifact_path = Path(artifact_path)

        if not artifact_path.exists():
            return False

        # If artifact_path is a directory, validate schemas within it
        if artifact_path.is_dir():
            return validate_schemas(artifact_path)

        # If it's a file, just check existence and non-empty
        return artifact_path.stat().st_size > 0

    def _precompute_signals(self, context: dict) -> Path | None:
        """Run D14 signal pre-computation, returning enriched data path.

        Returns None if no pre-computation needed (e.g., no conditions).
        The enriched file is written alongside the output directory.
        """
        spec_path = context.get("strategy_spec_path", "")
        data_path = context.get("market_data_path", "")

        if not spec_path or not data_path:
            return None

        if not Path(spec_path).exists() or not Path(data_path).exists():
            return None

        # Write enriched file into the output directory
        output_dir = Path(context.get("output_directory", "artifacts/backtest"))
        output_dir.mkdir(parents=True, exist_ok=True)
        enriched_path = output_dir / "market-data-enriched.arrow"

        logger.info(
            "Running signal pre-computation (D14)",
            extra={
                "component": "pipeline.rust_bridge",
                "ctx": {
                    "spec": spec_path,
                    "data": data_path,
                    "enriched": str(enriched_path),
                },
            },
        )

        return precompute_signals(
            strategy_spec_path=spec_path,
            market_data_path=data_path,
            output_path=enriched_path,
            session_schedule=self._session_schedule,
        )

    def _build_job(self, strategy_id: str, context: dict) -> BacktestJob:
        """Extract job parameters from pipeline context dict."""
        return BacktestJob(
            strategy_spec_path=Path(context["strategy_spec_path"]),
            market_data_path=Path(context["market_data_path"]),
            cost_model_path=Path(context["cost_model_path"]),
            output_directory=Path(context.get(
                "output_directory",
                f"artifacts/{strategy_id}/backtest",
            )),
            config_hash=context["config_hash"],
            memory_budget_mb=int(context.get("memory_budget_mb", 512)),
            checkpoint_path=(
                Path(context["checkpoint_path"])
                if context.get("checkpoint_path") else None
            ),
            fold_boundaries=context.get("fold_boundaries"),
            embargo_bars=context.get("embargo_bars"),
            window_start=context.get("window_start"),
            window_end=context.get("window_end"),
            parameter_batch=context.get("parameter_batch"),
        )
