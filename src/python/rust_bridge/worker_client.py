"""Persistent worker client for JSON-line protocol with Rust forex_worker (Phase 1).

Manages long-lived Rust worker subprocesses that stay resident across
evaluations.  Data is loaded once (``load_data``) and reused for many
``eval`` calls, eliminating per-generation Arrow IPC re-read overhead.

Communication uses newline-delimited JSON over stdin/stdout.  Each request
carries a monotonic ``id``; responses are correlated via the same ``id``
through a ``_pending`` future dict.

Design decisions:
- Dedicated stdout read loop (``_reader_loop``) keyed by request ``id``
  -- CANNOT use ``communicate()`` which waits for process exit.
- Separate stderr drain task to prevent pipe buffer deadlock.
- Health check + automatic restart on worker crash (broken pipe / OOM /
  Rust panic).
- Configurable eval timeout with kill-and-restart on expiry.
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import time
from pathlib import Path
from typing import Any, Self

from logging_setup.setup import get_logger

logger = get_logger("pipeline.rust_bridge.worker")


class WorkerError(Exception):
    """Raised when a worker returns an error response."""

    def __init__(self, code: str, message: str, fatal: bool = False):
        self.code = code
        self.fatal = fatal
        super().__init__(f"[{code}] {message}")


class PersistentWorker:
    """JSON-line protocol client for a single ``forex_worker`` process."""

    def __init__(
        self,
        binary_path: Path,
        cost_model_path: Path,
        memory_budget_mb: int = 5632,
        eval_timeout: float = 120.0,
        worker_id: int = 0,
    ):
        self._binary_path = Path(binary_path)
        self._cost_model_path = Path(cost_model_path)
        self._memory_budget_mb = memory_budget_mb
        self._eval_timeout = eval_timeout
        self._worker_id = worker_id

        self._proc: asyncio.subprocess.Process | None = None
        self._next_id: int = 1
        self._pending: dict[int, asyncio.Future[dict]] = {}
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._started: bool = False
        self._shutting_down: bool = False
        # Track loaded data keys so we can replay on restart
        self._loaded_keys: dict[str, Path] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> Self:
        """Spawn the worker process and send the ``init`` command."""
        if self._started:
            return self

        if not self._binary_path.exists():
            raise FileNotFoundError(f"Worker binary not found: {self._binary_path}")

        env = os.environ.copy()
        env["RAYON_NUM_THREADS"] = "1"

        self._proc = await asyncio.create_subprocess_exec(
            str(self._binary_path),
            "--mode", "worker",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        self._reader_task = asyncio.create_task(
            self._reader_loop(), name=f"worker-{self._worker_id}-reader"
        )
        self._stderr_task = asyncio.create_task(
            self._stderr_drain(), name=f"worker-{self._worker_id}-stderr"
        )

        def _norm(p: Path) -> str:
            return str(p).replace("\\", "/")

        # Send init command
        resp = await self._send_request({
            "cmd": "init",
            "cost_model_path": _norm(self._cost_model_path),
            "memory_budget_mb": self._memory_budget_mb,
        })

        if not resp.get("ok"):
            err = resp.get("error", {})
            raise WorkerError(
                err.get("code", "INIT_FAILED"),
                err.get("message", "Worker init failed"),
                fatal=True,
            )

        self._started = True
        logger.info(
            f"Worker {self._worker_id} started (pid={self._proc.pid})",
            extra={
                "component": "pipeline.rust_bridge.worker",
                "ctx": {
                    "worker_id": self._worker_id,
                    "pid": self._proc.pid,
                    "memory_budget_mb": self._memory_budget_mb,
                },
            },
        )
        return self

    async def shutdown(self) -> None:
        """Gracefully shut down the worker process."""
        if not self._started or self._shutting_down:
            return

        self._shutting_down = True

        try:
            # Send shutdown command (best-effort, don't wait too long)
            await asyncio.wait_for(
                self._send_request({"cmd": "shutdown"}),
                timeout=5.0,
            )
        except (asyncio.TimeoutError, BrokenPipeError, OSError, WorkerError):
            pass

        await self._cleanup()
        self._loaded_keys.clear()

        logger.info(
            f"Worker {self._worker_id} shut down",
            extra={
                "component": "pipeline.rust_bridge.worker",
                "ctx": {"worker_id": self._worker_id},
            },
        )

    async def _cleanup(self) -> None:
        """Kill process and cancel background tasks."""
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()
            try:
                await self._stderr_task
            except asyncio.CancelledError:
                pass

        if self._proc is not None:
            try:
                self._proc.terminate()
            except OSError:
                pass
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                try:
                    self._proc.kill()
                except OSError:
                    pass
                try:
                    await asyncio.wait_for(self._proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass

        # Fail all pending futures
        for req_id, fut in list(self._pending.items()):
            if not fut.done():
                fut.set_exception(WorkerError("WORKER_DEAD", "Worker process terminated", fatal=True))
        self._pending.clear()

        self._proc = None
        self._reader_task = None
        self._stderr_task = None
        self._started = False
        self._shutting_down = False

    async def health_check(self) -> bool:
        """Return True if the worker process is still alive."""
        if self._proc is None:
            return False
        return self._proc.returncode is None

    async def _restart(self) -> None:
        """Kill the current worker and start a fresh one, replaying data loads."""
        logger.warning(
            f"Restarting worker {self._worker_id}",
            extra={
                "component": "pipeline.rust_bridge.worker",
                "ctx": {"worker_id": self._worker_id},
            },
        )
        keys_to_replay = dict(self._loaded_keys)
        await self._cleanup()
        self._next_id = 1
        await self.start()

        # Replay previously loaded data into the fresh worker
        for key, data_path in keys_to_replay.items():
            logger.info(
                f"Worker {self._worker_id} replaying load_data for key={key}",
                extra={
                    "component": "pipeline.rust_bridge.worker",
                    "ctx": {"worker_id": self._worker_id, "key": key},
                },
            )
            await self.load_data(key, data_path)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def load_data(self, key: str, data_path: Path) -> int:
        """Load an Arrow IPC file into the worker's memory-mapped cache.

        Returns the number of rows loaded.
        """
        def _norm(p: Path) -> str:
            return str(p).replace("\\", "/")

        resp = await self._send_request({
            "cmd": "load_data",
            "key": key,
            "data_path": _norm(Path(data_path)),
        })

        if not resp.get("ok"):
            err = resp.get("error", {})
            raise WorkerError(
                err.get("code", "LOAD_FAILED"),
                err.get("message", "Data load failed"),
                fatal=err.get("fatal", False),
            )

        rows = resp.get("rows", 0)
        # Track for replay on restart
        self._loaded_keys[key] = Path(data_path)
        logger.info(
            f"Worker {self._worker_id} loaded {key} ({rows} rows)",
            extra={
                "component": "pipeline.rust_bridge.worker",
                "ctx": {
                    "worker_id": self._worker_id,
                    "key": key,
                    "rows": rows,
                },
            },
        )
        return rows

    async def eval(
        self,
        data_key: str,
        groups: list[dict],
        window_start: int,
        window_end: int,
        score_mode: str = "composite",
    ) -> dict[str, list[float]]:
        """Evaluate candidate groups on loaded data.

        Args:
            data_key: Key used in ``load_data`` to reference the dataset.
            groups: List of group dicts with candidates and params.
            window_start: Test window start bar index.
            window_end: Test window end bar index.

        Returns:
            Dict mapping group_id to list of scores.

        Raises:
            WorkerError: On evaluation failure or timeout.
        """
        try:
            resp = await asyncio.wait_for(
                self._send_request({
                    "cmd": "eval",
                    "data_key": data_key,
                    "groups": groups,
                    "window_start": window_start,
                    "window_end": window_end,
                    "scores_only": True,
                    "score_mode": score_mode,
                }),
                timeout=self._eval_timeout,
            )
        except asyncio.TimeoutError:
            logger.error(
                f"Worker {self._worker_id} eval timeout ({self._eval_timeout}s) — restarting",
                extra={
                    "component": "pipeline.rust_bridge.worker",
                    "ctx": {
                        "worker_id": self._worker_id,
                        "data_key": data_key,
                        "timeout_s": self._eval_timeout,
                    },
                },
            )
            await self._restart()
            raise WorkerError("EVAL_TIMEOUT", f"Eval timed out after {self._eval_timeout}s", fatal=True)

        if not resp.get("ok"):
            err = resp.get("error", {})
            error = WorkerError(
                err.get("code", "EVAL_FAILED"),
                err.get("message", "Eval failed"),
                fatal=err.get("fatal", False),
            )
            if error.fatal:
                await self._restart()
            raise error

        return resp.get("results", {})

    # ------------------------------------------------------------------
    # Protocol internals
    # ------------------------------------------------------------------

    def _alloc_id(self) -> int:
        """Allocate a monotonically increasing request ID."""
        req_id = self._next_id
        self._next_id += 1
        return req_id

    async def _send_request(self, payload: dict) -> dict:
        """Send a JSON-line request and wait for the correlated response."""
        if self._proc is None or self._proc.stdin is None:
            raise WorkerError("WORKER_DEAD", "Worker process not running", fatal=True)

        req_id = self._alloc_id()
        payload["id"] = req_id

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict] = loop.create_future()
        self._pending[req_id] = fut

        line = json.dumps(payload, default=str) + "\n"
        try:
            self._proc.stdin.write(line.encode("utf-8"))
            await self._proc.stdin.drain()
        except (BrokenPipeError, OSError, ConnectionResetError) as e:
            self._pending.pop(req_id, None)
            if not fut.done():
                fut.set_exception(WorkerError("BROKEN_PIPE", str(e), fatal=True))
            raise WorkerError("BROKEN_PIPE", str(e), fatal=True)

        try:
            return await fut
        finally:
            self._pending.pop(req_id, None)

    async def _reader_loop(self) -> None:
        """Continuously read JSON-line responses from stdout and dispatch to pending futures."""
        assert self._proc is not None and self._proc.stdout is not None

        try:
            while True:
                raw = await self._proc.stdout.readline()
                if not raw:
                    # EOF — process exited
                    break

                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Worker {self._worker_id} non-JSON stdout: {line[:200]}",
                        extra={"component": "pipeline.rust_bridge.worker"},
                    )
                    continue

                req_id = msg.get("id")
                if req_id is None:
                    # Unsolicited message (e.g. progress); log and skip
                    logger.debug(
                        f"Worker {self._worker_id} unsolicited message: {line[:200]}",
                        extra={"component": "pipeline.rust_bridge.worker"},
                    )
                    continue

                fut = self._pending.get(req_id)
                if fut is not None and not fut.done():
                    fut.set_result(msg)
                else:
                    # Unknown id — likely a parse error response with id:0.
                    # If there is exactly one pending future and the response
                    # indicates an error, resolve it so it doesn't hang until
                    # timeout.
                    logger.warning(
                        f"Worker {self._worker_id} response for unknown id={req_id}: "
                        f"{json.dumps(msg)[:300]}",
                        extra={"component": "pipeline.rust_bridge.worker"},
                    )
                    if not msg.get("ok") and len(self._pending) == 1:
                        sole_fut = next(iter(self._pending.values()))
                        if not sole_fut.done():
                            sole_fut.set_result(msg)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(
                f"Worker {self._worker_id} reader loop crashed: {e}",
                extra={"component": "pipeline.rust_bridge.worker"},
            )
        finally:
            # Process died — fail all pending
            for req_id, fut in list(self._pending.items()):
                if not fut.done():
                    fut.set_exception(
                        WorkerError("WORKER_DEAD", "Worker stdout closed", fatal=True)
                    )

    async def _stderr_drain(self) -> None:
        """Continuously drain stderr to prevent pipe buffer deadlock."""
        assert self._proc is not None and self._proc.stderr is not None

        try:
            while True:
                raw = await self._proc.stderr.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    logger.debug(
                        f"Worker {self._worker_id} stderr: {line}",
                        extra={
                            "component": "pipeline.rust_bridge.worker",
                            "ctx": {"worker_id": self._worker_id, "stream": "stderr"},
                        },
                    )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(
                f"Worker {self._worker_id} stderr drain error: {e}",
                extra={
                    "component": "pipeline.rust_bridge.worker",
                    "ctx": {"worker_id": self._worker_id, "error": str(e)},
                },
            )


class WorkerPool:
    """Manages N persistent workers with shared-nothing cache partitioning.

    ``max_workers`` is configurable and decoupled from ``n_folds`` to
    prevent resource exhaustion when running many folds.
    """

    def __init__(
        self,
        binary_path: Path,
        cost_model_path: Path,
        n_workers: int = 4,
        memory_budget_mb: int = 5632,
        eval_timeout: float = 120.0,
    ):
        self._binary_path = Path(binary_path)
        self._cost_model_path = Path(cost_model_path)
        self._n_workers = n_workers
        self._memory_budget_mb = memory_budget_mb
        self._eval_timeout = eval_timeout
        self._workers: list[PersistentWorker] = []
        self._started: bool = False

    async def start(self) -> None:
        """Spawn all workers in parallel."""
        if self._started:
            return

        per_worker_budget = self._memory_budget_mb // self._n_workers

        self._workers = [
            PersistentWorker(
                binary_path=self._binary_path,
                cost_model_path=self._cost_model_path,
                memory_budget_mb=per_worker_budget,
                eval_timeout=self._eval_timeout,
                worker_id=i,
            )
            for i in range(self._n_workers)
        ]

        results = await asyncio.gather(
            *[w.start() for w in self._workers],
            return_exceptions=True,
        )

        # Check for startup failures
        failed = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                logger.error(
                    f"Worker {i} failed to start: {result}",
                    extra={
                        "component": "pipeline.rust_bridge.worker",
                        "ctx": {"worker_id": i, "error": str(result)},
                    },
                )
                failed.append(i)

        if len(failed) == self._n_workers:
            raise RuntimeError("All workers failed to start")

        self._started = True
        logger.info(
            f"Worker pool started: {self._n_workers - len(failed)}/{self._n_workers} workers",
            extra={
                "component": "pipeline.rust_bridge.worker",
                "ctx": {
                    "total": self._n_workers,
                    "failed": len(failed),
                },
            },
        )

    async def preload_data(self, keys_and_paths: list[tuple[str, Path]]) -> None:
        """Load data files into workers using round-robin assignment.

        Each data key is loaded into exactly one worker (shared-nothing
        partitioning).  Callers must route eval requests to the correct
        worker via ``data_key_to_worker()``.
        """
        tasks = []
        for idx, (key, path) in enumerate(keys_and_paths):
            worker_idx = idx % len(self._workers)
            worker = self._workers[worker_idx]
            tasks.append((worker_idx, worker.load_data(key, path)))

        results = await asyncio.gather(
            *[t for _, t in tasks],
            return_exceptions=True,
        )

        for (worker_idx, _), result in zip(tasks, results):
            if isinstance(result, BaseException):
                logger.error(
                    f"Worker {worker_idx} data preload failed: {result}",
                    extra={
                        "component": "pipeline.rust_bridge.worker",
                        "ctx": {"worker_idx": worker_idx, "error": str(result)},
                    },
                )

    def data_key_to_worker(self, key: str, keys_and_paths: list[tuple[str, Path]]) -> int:
        """Determine which worker owns a data key based on round-robin assignment."""
        for idx, (k, _) in enumerate(keys_and_paths):
            if k == key:
                return idx % len(self._workers)
        raise KeyError(f"Data key not found in preload list: {key}")

    async def eval_on_worker(
        self,
        worker_idx: int,
        data_key: str,
        groups: list[dict],
        window_start: int,
        window_end: int,
    ) -> dict[str, list[float]]:
        """Run eval on a specific worker.

        If the targeted worker is unhealthy, restarts it and retries once.
        """
        if worker_idx >= len(self._workers):
            raise IndexError(f"Worker index {worker_idx} out of range (pool size={len(self._workers)})")

        worker = self._workers[worker_idx]

        if not await worker.health_check():
            logger.warning(
                f"Worker {worker_idx} unhealthy before eval — restarting",
                extra={
                    "component": "pipeline.rust_bridge.worker",
                    "ctx": {"worker_idx": worker_idx},
                },
            )
            await worker._restart()

        try:
            return await worker.eval(data_key, groups, window_start, window_end)
        except WorkerError as e:
            if e.fatal:
                # Already restarted inside eval() on timeout;
                # for other fatal errors, try one more time
                logger.warning(
                    f"Worker {worker_idx} fatal error on eval, retrying: {e}",
                    extra={
                        "component": "pipeline.rust_bridge.worker",
                        "ctx": {"worker_idx": worker_idx, "error": str(e)},
                    },
                )
                if not await worker.health_check():
                    await worker._restart()
                return await worker.eval(data_key, groups, window_start, window_end)
            raise

    async def shutdown_all(self) -> None:
        """Shut down all workers in parallel."""
        if not self._started:
            return

        await asyncio.gather(
            *[w.shutdown() for w in self._workers],
            return_exceptions=True,
        )

        self._workers.clear()
        self._started = False

        logger.info(
            "Worker pool shut down",
            extra={"component": "pipeline.rust_bridge.worker"},
        )

    @property
    def n_workers(self) -> int:
        return len(self._workers)

    @property
    def workers(self) -> list[PersistentWorker]:
        return list(self._workers)
