"""Unit tests for PersistentWorker and WorkerPool (Phase 1).

Tests use a mock subprocess that echoes JSON-line responses so we can
validate the protocol without a real Rust binary.

Uses ``asyncio.run()`` wrappers (no pytest-asyncio dependency required).
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src/python to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PYTHON = PROJECT_ROOT / "src" / "python"
if str(SRC_PYTHON) not in sys.path:
    sys.path.insert(0, str(SRC_PYTHON))

from rust_bridge.worker_client import PersistentWorker, WorkerError, WorkerPool


# ---------------------------------------------------------------------------
# Helpers: mock subprocess that speaks JSON-line protocol
# ---------------------------------------------------------------------------

MOCK_BINARY = Path("fake_worker.exe")


def _make_mock_proc(responses: list[dict] | None = None):
    """Create a mock asyncio.subprocess.Process that responds with JSON lines.

    ``responses`` is a list of dicts; each time the mock's stdout.readline
    is called it returns the next response as a JSON line.  The ``id`` field
    in the response is patched to match the request ``id`` sent to stdin.
    """
    if responses is None:
        responses = []

    proc = MagicMock()
    proc.pid = 12345
    proc.returncode = None  # alive

    # --- stdin ---
    # NOTE: stdin.write() is synchronous in asyncio.subprocess.Process.
    #       Only stdin.drain() is a coroutine.
    written_lines: list[str] = []
    request_ids: list[int] = []

    def _write(data: bytes):
        line = data.decode("utf-8").strip()
        written_lines.append(line)
        try:
            msg = json.loads(line)
            request_ids.append(msg.get("id", 0))
        except json.JSONDecodeError:
            pass

    async def _drain():
        pass

    proc.stdin = MagicMock()
    proc.stdin.write = _write
    proc.stdin.drain = _drain
    proc._written_lines = written_lines
    proc._request_ids = request_ids

    # --- stdout (reader loop reads from this) ---
    response_idx = [0]

    async def _readline():
        # Small yield to let the event loop process writes
        await asyncio.sleep(0.01)

        idx = response_idx[0]
        if idx >= len(responses):
            # Block indefinitely (simulate idle worker) until cancelled
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                return b""
            return b""

        resp = dict(responses[idx])
        response_idx[0] += 1

        # Match the request id if available
        if request_ids and len(request_ids) > idx:
            resp["id"] = request_ids[idx]

        return (json.dumps(resp) + "\n").encode("utf-8")

    proc.stdout = MagicMock()
    proc.stdout.readline = _readline

    # --- stderr ---
    async def _stderr_readline():
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            return b""
        return b""

    proc.stderr = MagicMock()
    proc.stderr.readline = _stderr_readline

    # --- lifecycle ---
    async def _wait():
        return 0

    proc.wait = _wait
    proc.terminate = MagicMock()
    proc.kill = MagicMock()

    return proc


def _run(coro):
    """Run an async coroutine synchronously for pytest (no pytest-asyncio needed)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# PersistentWorker tests
# ---------------------------------------------------------------------------

class TestPersistentWorker:
    """Tests for the PersistentWorker JSON-line client."""

    def test_start_sends_init(self):
        """Worker.start() sends an init command and processes the ok response."""
        async def _test():
            mock_proc = _make_mock_proc([{"ok": True}])

            with patch("rust_bridge.worker_client.asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch.object(Path, "exists", return_value=True):
                    worker = PersistentWorker(
                        binary_path=MOCK_BINARY,
                        cost_model_path=Path("cost.json"),
                        memory_budget_mb=1024,
                        worker_id=0,
                    )
                    await worker.start()

                    assert worker._started is True
                    assert len(mock_proc._written_lines) >= 1

                    init_msg = json.loads(mock_proc._written_lines[0])
                    assert init_msg["cmd"] == "init"
                    assert init_msg["memory_budget_mb"] == 1024

                    await worker.shutdown()

        _run(_test())

    def test_load_data_returns_row_count(self):
        """load_data sends the right command and returns row count."""
        async def _test():
            mock_proc = _make_mock_proc([
                {"ok": True},                # init response
                {"ok": True, "rows": 5000},  # load_data response
            ])

            with patch("rust_bridge.worker_client.asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch.object(Path, "exists", return_value=True):
                    worker = PersistentWorker(
                        binary_path=MOCK_BINARY,
                        cost_model_path=Path("cost.json"),
                        worker_id=0,
                    )
                    await worker.start()

                    rows = await worker.load_data("signal_abc", Path("data.arrow"))
                    assert rows == 5000

                    load_msg = json.loads(mock_proc._written_lines[1])
                    assert load_msg["cmd"] == "load_data"
                    assert load_msg["key"] == "signal_abc"

                    await worker.shutdown()

        _run(_test())

    def test_eval_returns_results(self):
        """eval sends command and returns group scores."""
        async def _test():
            expected_results = {"grp_abc": [0.23, -0.1, 0.45]}
            mock_proc = _make_mock_proc([
                {"ok": True},                              # init
                {"ok": True, "results": expected_results},  # eval
            ])

            with patch("rust_bridge.worker_client.asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch.object(Path, "exists", return_value=True):
                    worker = PersistentWorker(
                        binary_path=MOCK_BINARY,
                        cost_model_path=Path("cost.json"),
                        worker_id=0,
                    )
                    await worker.start()

                    results = await worker.eval(
                        data_key="signal_abc",
                        groups=[{"group_id": "grp_abc", "candidates": [{}]}],
                        window_start=0,
                        window_end=1000,
                    )
                    assert results == expected_results

                    eval_msg = json.loads(mock_proc._written_lines[1])
                    assert eval_msg["cmd"] == "eval"
                    assert eval_msg["data_key"] == "signal_abc"
                    assert eval_msg["scores_only"] is True

                    await worker.shutdown()

        _run(_test())

    def test_eval_error_raises_worker_error(self):
        """eval raises WorkerError on non-ok response."""
        async def _test():
            mock_proc = _make_mock_proc([
                {"ok": True},  # init
                {"ok": False, "error": {"code": "CACHE_MISS", "message": "key not loaded"}, "fatal": False},
            ])

            with patch("rust_bridge.worker_client.asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch.object(Path, "exists", return_value=True):
                    worker = PersistentWorker(
                        binary_path=MOCK_BINARY,
                        cost_model_path=Path("cost.json"),
                        worker_id=0,
                    )
                    await worker.start()

                    with pytest.raises(WorkerError, match="CACHE_MISS"):
                        await worker.eval("missing_key", [], 0, 100)

                    await worker.shutdown()

        _run(_test())

    def test_health_check_alive(self):
        """health_check returns True for a running worker."""
        async def _test():
            mock_proc = _make_mock_proc([{"ok": True}])

            with patch("rust_bridge.worker_client.asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch.object(Path, "exists", return_value=True):
                    worker = PersistentWorker(
                        binary_path=MOCK_BINARY,
                        cost_model_path=Path("cost.json"),
                        worker_id=0,
                    )
                    await worker.start()

                    assert await worker.health_check() is True

                    await worker.shutdown()

        _run(_test())

    def test_health_check_dead(self):
        """health_check returns False when process is not running."""
        async def _test():
            worker = PersistentWorker(
                binary_path=MOCK_BINARY,
                cost_model_path=Path("cost.json"),
                worker_id=0,
            )
            assert await worker.health_check() is False

        _run(_test())

    def test_binary_not_found_raises(self):
        """start() raises FileNotFoundError when binary does not exist."""
        async def _test():
            worker = PersistentWorker(
                binary_path=Path("nonexistent_binary"),
                cost_model_path=Path("cost.json"),
                worker_id=0,
            )
            with pytest.raises(FileNotFoundError, match="nonexistent_binary"):
                await worker.start()

        _run(_test())

    def test_eval_timeout_triggers_restart(self):
        """Eval timeout kills worker and raises WorkerError."""
        async def _test():
            # First response is init ok, second response never comes (timeout)
            mock_proc = _make_mock_proc([{"ok": True}])

            restart_called = False

            async def mock_restart(self_inner):
                nonlocal restart_called
                restart_called = True
                # Just clean up without actually restarting
                await self_inner._cleanup()

            with patch("rust_bridge.worker_client.asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch.object(Path, "exists", return_value=True):
                    worker = PersistentWorker(
                        binary_path=MOCK_BINARY,
                        cost_model_path=Path("cost.json"),
                        eval_timeout=0.1,  # very short timeout
                        worker_id=0,
                    )
                    await worker.start()

                    with patch.object(PersistentWorker, "_restart", mock_restart):
                        with pytest.raises(WorkerError, match="EVAL_TIMEOUT"):
                            await worker.eval("key", [], 0, 100)

                    assert restart_called

        _run(_test())


# ---------------------------------------------------------------------------
# WorkerPool tests
# ---------------------------------------------------------------------------

class TestWorkerPool:
    """Tests for the WorkerPool manager."""

    def test_pool_starts_n_workers(self):
        """Pool starts the requested number of workers."""
        async def _test():
            mock_proc = _make_mock_proc([{"ok": True}])

            with patch("rust_bridge.worker_client.asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch.object(Path, "exists", return_value=True):
                    pool = WorkerPool(
                        binary_path=MOCK_BINARY,
                        cost_model_path=Path("cost.json"),
                        n_workers=3,
                        memory_budget_mb=3000,
                    )
                    await pool.start()

                    assert pool.n_workers == 3
                    assert len(pool.workers) == 3

                    await pool.shutdown_all()

        _run(_test())

    def test_pool_distributes_data_round_robin(self):
        """preload_data assigns keys to workers via round-robin."""
        async def _test():
            mock_proc = _make_mock_proc([
                {"ok": True},              # init
                {"ok": True, "rows": 100}, # load_data
            ])

            with patch("rust_bridge.worker_client.asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch.object(Path, "exists", return_value=True):
                    pool = WorkerPool(
                        binary_path=MOCK_BINARY,
                        cost_model_path=Path("cost.json"),
                        n_workers=2,
                    )
                    await pool.start()

                    keys = [
                        ("key_0", Path("data0.arrow")),
                        ("key_1", Path("data1.arrow")),
                        ("key_2", Path("data2.arrow")),
                    ]
                    await pool.preload_data(keys)

                    # key_0 -> worker 0, key_1 -> worker 1, key_2 -> worker 0
                    assert pool.data_key_to_worker("key_0", keys) == 0
                    assert pool.data_key_to_worker("key_1", keys) == 1
                    assert pool.data_key_to_worker("key_2", keys) == 0

                    await pool.shutdown_all()

        _run(_test())

    def test_pool_shutdown_clears_workers(self):
        """shutdown_all empties the worker list."""
        async def _test():
            mock_proc = _make_mock_proc([{"ok": True}])

            with patch("rust_bridge.worker_client.asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch.object(Path, "exists", return_value=True):
                    pool = WorkerPool(
                        binary_path=MOCK_BINARY,
                        cost_model_path=Path("cost.json"),
                        n_workers=2,
                    )
                    await pool.start()
                    assert pool.n_workers == 2

                    await pool.shutdown_all()
                    assert pool.n_workers == 0

        _run(_test())

    def test_pool_memory_budget_split(self):
        """Each worker gets memory_budget / n_workers."""
        async def _test():
            mock_proc = _make_mock_proc([{"ok": True}])

            with patch("rust_bridge.worker_client.asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch.object(Path, "exists", return_value=True):
                    pool = WorkerPool(
                        binary_path=MOCK_BINARY,
                        cost_model_path=Path("cost.json"),
                        n_workers=4,
                        memory_budget_mb=8000,
                    )
                    await pool.start()

                    for w in pool.workers:
                        assert w._memory_budget_mb == 2000

                    await pool.shutdown_all()

        _run(_test())

    def test_pool_worker_idx_out_of_range(self):
        """eval_on_worker raises IndexError for bad worker index."""
        async def _test():
            mock_proc = _make_mock_proc([{"ok": True}])

            with patch("rust_bridge.worker_client.asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch.object(Path, "exists", return_value=True):
                    pool = WorkerPool(
                        binary_path=MOCK_BINARY,
                        cost_model_path=Path("cost.json"),
                        n_workers=2,
                    )
                    await pool.start()

                    with pytest.raises(IndexError, match="out of range"):
                        await pool.eval_on_worker(5, "key", [], 0, 100)

                    await pool.shutdown_all()

        _run(_test())

    def test_data_key_not_found_raises(self):
        """data_key_to_worker raises KeyError for unknown key."""
        pool = WorkerPool(
            binary_path=MOCK_BINARY,
            cost_model_path=Path("cost.json"),
            n_workers=1,
        )
        with pytest.raises(KeyError, match="unknown_key"):
            pool.data_key_to_worker("unknown_key", [("other", Path("x"))])


# ---------------------------------------------------------------------------
# PersistentBatchDispatcher tests
# ---------------------------------------------------------------------------

class TestPersistentBatchDispatcher:
    """Tests for the PersistentBatchDispatcher integration."""

    def test_check_memory_passthrough(self):
        """check_memory returns (True, batch_size) when memory is sufficient."""
        from optimization.batch_dispatch import PersistentBatchDispatcher

        mock_pool = MagicMock()
        dispatcher = PersistentBatchDispatcher(
            worker_pool=mock_pool,
            artifacts_dir=Path("artifacts"),
            config={"optimization": {"memory_budget_mb": 8000}},
        )

        with patch("optimization.batch_dispatch._get_available_memory_mb", return_value=16000):
            ok, batch = dispatcher.check_memory(2048, 5)
            assert ok is True
            assert batch == 2048

    def test_check_memory_reduces_batch(self):
        """check_memory reduces batch size when memory is tight."""
        from optimization.batch_dispatch import PersistentBatchDispatcher

        mock_pool = MagicMock()
        dispatcher = PersistentBatchDispatcher(
            worker_pool=mock_pool,
            artifacts_dir=Path("artifacts"),
            config={"optimization": {"memory_budget_mb": 100}},
        )

        # Very low memory forces batch reduction
        with patch("optimization.batch_dispatch._get_available_memory_mb", return_value=2200):
            ok, batch = dispatcher.check_memory(999999, 5)
            assert ok is False
            assert batch < 999999
