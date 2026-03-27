"""Optimization stage executor (Story 5.3, AC #1, #3).

Implements StageExecutor protocol from orchestrator/stage_runner.py
to integrate optimization into the pipeline state machine.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pyarrow.ipc

from logging_setup.setup import get_logger
from orchestrator.stage_runner import StageResult

logger = get_logger("optimization.executor")


class OptimizationExecutor:
    """StageExecutor for the OPTIMIZING pipeline stage.

    Instantiates OptimizationOrchestrator and runs the optimization loop.
    """

    def execute(self, strategy_id: str, context: dict) -> StageResult:
        """Execute optimization stage.

        Args:
            strategy_id: Strategy identifier.
            context: Dict with artifacts_dir, strategy_spec_path,
                     market_data_path, cost_model_path, config_hash,
                     memory_budget_mb, output_directory.

        Returns:
            StageResult with optimization artifact paths.
        """
        from optimization.orchestrator import OptimizationOrchestrator
        from rust_bridge.batch_runner import BatchRunner

        artifacts_dir = Path(context["artifacts_dir"]) / strategy_id / "optimization"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Load strategy spec
        spec_path = Path(context["strategy_spec_path"])
        try:
            import tomllib
            with open(spec_path, "rb") as f:
                strategy_spec = tomllib.load(f)
        except Exception:
            # Fallback: try JSON
            strategy_spec = json.loads(spec_path.read_text(encoding="utf-8"))

        # Load full config
        try:
            from config_loader import load_config
            config = load_config()
        except Exception as e:
            logger.warning(
                f"Config loading failed, using defaults: {e}",
                extra={"component": "optimization.executor"},
            )
            config = {"optimization": {}, "pipeline": {}}

        # Check for existing checkpoint (resume support)
        checkpoint_path = artifacts_dir / "optimization-checkpoint.json"
        resume_from = checkpoint_path if checkpoint_path.exists() else None

        # Create batch runner
        # Look for Rust binary in standard locations
        rust_binary = self._find_rust_binary()
        batch_runner = BatchRunner(binary_path=rust_binary)

        # Create and run orchestrator
        orchestrator = OptimizationOrchestrator(
            strategy_spec=strategy_spec,
            market_data_path=Path(context["market_data_path"]),
            cost_model_path=Path(context["cost_model_path"]),
            config=config,
            artifacts_dir=artifacts_dir,
            batch_runner=batch_runner,
        )

        # Run async orchestrator — prefer asyncio.run(), fall back to thread
        try:
            result = asyncio.run(orchestrator.run(resume_from=resume_from))
        except RuntimeError:
            # Already inside an event loop — run in a dedicated thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run, orchestrator.run(resume_from=resume_from)
                )
                result = future.result()

        if result.all_candidates_path is not None:
            return StageResult(
                artifact_path=str(result.all_candidates_path),
                manifest_ref=str(result.run_manifest_path) if result.run_manifest_path else None,
                outcome="success",
                metrics={
                    "generations_run": result.generations_run,
                    "total_evaluations": result.total_evaluations,
                    "convergence_reached": result.convergence_reached,
                    "stop_reason": result.stop_reason,
                },
            )

        return StageResult(
            outcome="failed",
            metrics={"stop_reason": result.stop_reason},
        )

    def validate_artifact(self, artifact_path: Path, manifest_ref: Path) -> bool:
        """Verify optimization results Arrow IPC exists and is readable."""
        try:
            if not artifact_path.exists():
                return False
            reader = pyarrow.ipc.open_file(str(artifact_path))
            table = reader.read_all()
            return table.num_rows > 0
        except Exception:
            return False

    def _find_rust_binary(self) -> Path:
        """Locate the Rust backtester binary."""
        candidates = [
            Path("target/release/forex_backtester"),
            Path("target/release/forex_backtester.exe"),
            Path("target/debug/forex_backtester"),
            Path("target/debug/forex_backtester.exe"),
            Path("src/rust/target/release/forex_backtester"),
            Path("src/rust/target/release/forex_backtester.exe"),
            Path("src/rust/target/debug/forex_backtester"),
            Path("src/rust/target/debug/forex_backtester.exe"),
        ]
        for p in candidates:
            if p.exists():
                return p
        # Fallback: assume it's on PATH
        return Path("forex_backtester")
