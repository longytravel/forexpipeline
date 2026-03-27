"""Python-Rust bridge: BatchRunner for dispatching backtest jobs (D1, AC#1, #5, #6, #8, #9).

Spawns the Rust ``forex_backtester`` binary as a subprocess using
``asyncio.create_subprocess_exec``.  All data exchange is via Arrow IPC files
and CLI arguments — NO PyO3/FFI.
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import signal
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from logging_setup.setup import get_logger

logger = get_logger("pipeline.rust_bridge")


@dataclass
class BacktestJob:
    """Parameters for a single backtest dispatch to the Rust binary."""

    strategy_spec_path: Path       # TOML file
    market_data_path: Path         # Arrow IPC file (mmap-ready)
    cost_model_path: Path          # JSON file
    output_directory: Path         # Results written here
    config_hash: str               # For artifact tracing
    memory_budget_mb: int          # Pre-allocation constraint
    checkpoint_path: Path | None = None  # Resume from checkpoint if set
    # Fold-aware batch evaluation support (Research Update)
    fold_boundaries: list[tuple[int, int]] | None = None
    embargo_bars: int | None = None
    window_start: int | None = None
    window_end: int | None = None
    parameter_batch: list[dict] | None = None


@dataclass
class BatchResult:
    """Result from a completed backtest dispatch."""

    exit_code: int
    output_directory: Path
    elapsed_seconds: float
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


@dataclass
class ProgressReport:
    """Progress data read from the Rust binary's progress.json file."""

    bars_processed: int = 0
    total_bars: int = 0
    estimated_seconds_remaining: float = 0.0
    memory_used_mb: int = 0
    updated_at: str = ""


class BatchRunner:
    """Dispatches backtest jobs to the Rust binary via subprocess (D1).

    Uses ``asyncio.create_subprocess_exec`` for non-blocking dispatch.
    Handles Windows-specific subprocess semantics (CTRL_BREAK instead of SIGTERM).
    """

    def __init__(self, binary_path: Path, timeout: int | None = None):
        self._binary_path = Path(binary_path)
        self._timeout = timeout
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def dispatch(self, job: BacktestJob, n_concurrent: int = 1) -> BatchResult:
        """Spawn Rust binary as subprocess, return result.

        Args:
            n_concurrent: Number of processes being dispatched concurrently
                (e.g. number of folds). Used to set RAYON_NUM_THREADS so
                Rayon thread pools don't oversubscribe the CPU.

        Pre-checks system memory before spawning.
        Normalizes all file paths to forward slashes (Windows compatibility).
        """
        # Pre-check: binary exists
        if not self._binary_path.exists():
            return BatchResult(
                exit_code=-1,
                output_directory=job.output_directory,
                elapsed_seconds=0.0,
                error=f"Binary not found: {self._binary_path}",
            )

        # Pre-check: input files exist
        for label, path in [
            ("strategy spec", job.strategy_spec_path),
            ("market data", job.market_data_path),
            ("cost model", job.cost_model_path),
        ]:
            if not Path(path).exists():
                return BatchResult(
                    exit_code=-1,
                    output_directory=job.output_directory,
                    elapsed_seconds=0.0,
                    error=f"{label} not found: {path}",
                )

        # Pre-check: system memory (best-effort)
        # Subtract 2GB OS reserve to match Rust-side MemoryBudget.check_system_memory()
        OS_RESERVE_MB = 2048
        available_mb = _get_available_memory_mb()
        if available_mb > OS_RESERVE_MB:
            available_mb -= OS_RESERVE_MB
        if available_mb > 0 and job.memory_budget_mb > available_mb:
            return BatchResult(
                exit_code=-1,
                output_directory=job.output_directory,
                elapsed_seconds=0.0,
                error=(
                    f"Insufficient memory: requested {job.memory_budget_mb}MB, "
                    f"available {available_mb}MB"
                ),
            )

        # Build CLI arguments — normalize paths to forward slashes
        args = self._build_args(job)

        logger.info(
            "Dispatching backtest job",
            extra={
                "component": "pipeline.rust_bridge",
                "ctx": {
                    "config_hash": job.config_hash,
                    "memory_budget_mb": job.memory_budget_mb,
                    "binary": str(self._binary_path),
                },
            },
        )

        # Ensure output directory exists
        job.output_directory.mkdir(parents=True, exist_ok=True)

        start = time.monotonic()

        try:
            # Vectorized batch evaluator is single-threaded (one pass through
            # bars scoring all candidates). Set RAYON_NUM_THREADS=1 to avoid
            # Rayon thread pool overhead. Parallelism comes from running many
            # concurrent subprocesses (one per group*fold) across all CPU cores.
            env = os.environ.copy()
            env["RAYON_NUM_THREADS"] = "1"

            proc = await asyncio.create_subprocess_exec(
                str(self._binary_path),
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            # Track process for cancellation — use unique key to avoid collision
            # when two jobs share the same config_hash
            job_key = f"{job.config_hash}_{uuid.uuid4().hex[:8]}"
            self._processes[job_key] = proc

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self._timeout,
                )
            except asyncio.TimeoutError:
                # Timeout — attempt graceful cancellation
                await self._terminate_process(proc)
                stdout_bytes, stderr_bytes = b"", b"timeout"

            elapsed = time.monotonic() - start
            stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

            result = BatchResult(
                exit_code=proc.returncode or 0,
                output_directory=job.output_directory,
                elapsed_seconds=elapsed,
                stdout=stdout,
                stderr=stderr,
                error=stderr if proc.returncode != 0 else None,
            )

        except OSError as e:
            elapsed = time.monotonic() - start
            result = BatchResult(
                exit_code=-1,
                output_directory=job.output_directory,
                elapsed_seconds=elapsed,
                error=f"Failed to spawn process: {e}",
            )
        finally:
            self._processes.pop(job_key, None)

        log_level = "info" if result.exit_code == 0 else "error"
        getattr(logger, log_level)(
            f"Backtest job completed (exit={result.exit_code}, {result.elapsed_seconds:.2f}s)",
            extra={
                "component": "pipeline.rust_bridge",
                "ctx": {
                    "config_hash": job.config_hash,
                    "exit_code": result.exit_code,
                    "elapsed_s": result.elapsed_seconds,
                },
            },
        )

        return result

    async def dispatch_manifest(
        self,
        manifest_path: Path,
        memory_budget_mb: int = 5632,
        timeout: int | None = None,
    ) -> BatchResult:
        """Dispatch a multi-group manifest to the Rust binary.

        The manifest JSON contains all groups, fold boundaries, and candidate
        params. The binary processes all groups in a single invocation.

        Args:
            manifest_path: Path to the manifest JSON file.
            memory_budget_mb: Memory budget passed as --memory-budget CLI arg.
            timeout: Override instance timeout if provided.
        """
        manifest_path = Path(manifest_path)

        if not self._binary_path.exists():
            return BatchResult(
                exit_code=-1,
                output_directory=manifest_path.parent,
                elapsed_seconds=0.0,
                error=f"Binary not found: {self._binary_path}",
            )

        if not manifest_path.exists():
            return BatchResult(
                exit_code=-1,
                output_directory=manifest_path.parent,
                elapsed_seconds=0.0,
                error=f"Manifest not found: {manifest_path}",
            )

        def norm(p: Path) -> str:
            return str(p).replace("\\", "/")

        args = [
            "--manifest", norm(manifest_path),
            "--memory-budget", str(memory_budget_mb),
        ]

        logger.info(
            "Dispatching manifest",
            extra={
                "component": "pipeline.rust_bridge",
                "ctx": {"manifest": str(manifest_path)},
            },
        )

        start = time.monotonic()
        effective_timeout = timeout if timeout is not None else self._timeout

        try:
            env = os.environ.copy()
            env["RAYON_NUM_THREADS"] = "1"

            proc = await asyncio.create_subprocess_exec(
                str(self._binary_path),
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            job_key = f"manifest_{uuid.uuid4().hex[:8]}"
            self._processes[job_key] = proc

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=effective_timeout,
                )
            except asyncio.TimeoutError:
                await self._terminate_process(proc)
                stdout_bytes, stderr_bytes = b"", b"timeout"

            elapsed = time.monotonic() - start
            stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

            result = BatchResult(
                exit_code=proc.returncode or 0,
                output_directory=manifest_path.parent,
                elapsed_seconds=elapsed,
                stdout=stdout,
                stderr=stderr,
                error=stderr if proc.returncode != 0 else None,
            )

        except OSError as e:
            elapsed = time.monotonic() - start
            result = BatchResult(
                exit_code=-1,
                output_directory=manifest_path.parent,
                elapsed_seconds=elapsed,
                error=f"Failed to spawn process: {e}",
            )
        finally:
            self._processes.pop(job_key, None)

        log_level = "info" if result.exit_code == 0 else "error"
        getattr(logger, log_level)(
            f"Manifest dispatch completed (exit={result.exit_code}, {result.elapsed_seconds:.2f}s)",
            extra={
                "component": "pipeline.rust_bridge",
                "ctx": {
                    "manifest": str(manifest_path),
                    "exit_code": result.exit_code,
                    "elapsed_s": result.elapsed_seconds,
                },
            },
        )

        return result

    async def cancel(self, job_id: str) -> None:
        """Signal Rust process to checkpoint and exit (AC #5).

        Cancels the first active process whose key starts with ``job_id``
        (typically the config_hash). On Windows: sends CTRL_BREAK via
        process.terminate(). On Unix: sends SIGTERM.
        Falls back to kill after 5-second timeout.
        """
        # Find matching process — keys are "{config_hash}_{uuid}"
        for key, proc in list(self._processes.items()):
            if key.startswith(job_id):
                await self._terminate_process(proc)
                self._processes.pop(key, None)
                return

    def get_progress(self, job: BacktestJob) -> ProgressReport | None:
        """Read progress file for status display (AC #6).

        Returns None if no progress file exists yet.
        """
        progress_path = job.output_directory / "progress.json"
        if not progress_path.exists():
            return None

        try:
            data = json.loads(progress_path.read_text(encoding="utf-8"))
            return ProgressReport(
                bars_processed=data.get("bars_processed", 0),
                total_bars=data.get("total_bars", 0),
                estimated_seconds_remaining=data.get("estimated_seconds_remaining", 0.0),
                memory_used_mb=data.get("memory_used_mb", 0),
                updated_at=data.get("updated_at", ""),
            )
        except (json.JSONDecodeError, OSError):
            return None

    def _build_args(self, job: BacktestJob) -> list[str]:
        """Build CLI arguments for the Rust binary.

        Normalizes all paths to forward slashes for Windows compatibility.
        """
        def norm(p: Path) -> str:
            return str(p).replace("\\", "/")

        args = [
            "--spec", norm(job.strategy_spec_path),
            "--data", norm(job.market_data_path),
            "--cost-model", norm(job.cost_model_path),
            "--output", norm(job.output_directory),
            "--config-hash", job.config_hash,
            "--memory-budget", str(job.memory_budget_mb),
        ]

        if job.checkpoint_path is not None:
            args.extend(["--checkpoint", norm(job.checkpoint_path)])

        if job.fold_boundaries is not None:
            # Serialize as JSON array of [start, end] pairs
            args.extend(["--fold-boundaries", json.dumps(job.fold_boundaries)])

        if job.embargo_bars is not None:
            args.extend(["--embargo-bars", str(job.embargo_bars)])

        if job.window_start is not None:
            args.extend(["--window-start", str(job.window_start)])

        if job.window_end is not None:
            args.extend(["--window-end", str(job.window_end)])

        if job.parameter_batch is not None:
            # Write parameter batch to a temp JSON file in the output dir
            batch_path = job.output_directory / "param_batch.json"
            job.output_directory.mkdir(parents=True, exist_ok=True)
            batch_path.write_text(
                json.dumps(job.parameter_batch), encoding="utf-8"
            )
            args.extend(["--param-batch", norm(batch_path)])

        return args

    async def _terminate_process(self, proc: asyncio.subprocess.Process) -> None:
        """Gracefully terminate a process with 5-second timeout before kill."""
        try:
            proc.terminate()
        except OSError:
            pass

        # Wait up to 5 seconds for graceful exit
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            # Escalate to kill
            try:
                proc.kill()
            except OSError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass


def _get_available_memory_mb() -> int:
    """Best-effort query of available system memory in MB."""
    try:
        if platform.system() == "Windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return int(stat.ullAvailPhys / (1024 * 1024))
        else:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 0
