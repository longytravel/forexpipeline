# Persistent Worker Architecture Review (Gemini 2.5 Pro)

**Date:** 2026-03-26
**Reviewer:** Gemini 2.5 Pro (via Claude orchestration)
**Validated by:** Claude Opus 4.6 (spot-checked critical findings against source)

## Files Reviewed
1. `src/python/rust_bridge/worker_client.py` -- async Python client
2. `src/python/optimization/batch_dispatch.py` -- PersistentBatchDispatcher integration
3. `src/rust/crates/backtester/src/worker/mod.rs` -- Rust worker module

---

## Critical Issues

### C1. `_path_to_data_key` uses `path.stem` -- cache collision risk
- **File:** `batch_dispatch.py:662-664`
- **Issue:** `_path_to_data_key(path)` returns `path.stem`. Two files in different directories with the same name (e.g., `data/fold1/market.arrow` and `data/fold2/market.arrow`) map to the same key, causing incorrect data in evaluations.
- **Validated:** Confirmed -- function is literally `return path.stem`.
- **Fix:** Use a hash of the relative path or the full path to generate unique keys.

### C2. Rust parse error sends `id: 0` -- Python future hangs
- **File:** `worker/mod.rs:446-453`
- **Issue:** When `serde_json::from_str` fails, the error response uses `id: 0`. The Python client cannot correlate this to any pending request, so the real request hangs until timeout.
- **Validated:** Confirmed -- `Response::err(0, "PARSE_ERROR", ...)` on line 450.
- **Fix:** Pre-extract the `id` field before full deserialization, or use a regex/partial parse to recover the id.

## High-Priority Issues

### H1. CACHE_MISS after worker restart not handled
- **File:** `worker_client.py` (pool restart logic) + `batch_dispatch.py`
- **Issue:** When a worker crashes and restarts, its in-memory data cache is lost. Subsequent `eval` calls will get `CACHE_MISS` errors from Rust. Neither `WorkerPool` nor `PersistentBatchDispatcher` re-issues `load_data` commands after restart.
- **Fix:** Catch `CACHE_MISS` error code and automatically re-issue `load_data` before retrying `eval`.

### H2. stderr drain swallows all exceptions
- **File:** `worker_client.py:436-437`
- **Issue:** `except Exception: pass` silently suppresses all errors in the stderr drain loop.
- **Validated:** Confirmed -- bare `pass` on line 437.
- **Fix:** At minimum, log the exception at DEBUG level.

## Medium-Priority Issues

### M1. Malformed JSON from worker -- reader loop continues but future unresolved
- **File:** `worker_client.py:374-381`
- **Issue:** On `json.JSONDecodeError`, the reader logs a warning and `continue`s. If the malformed line was a response to a pending request, that future is never resolved and hangs until timeout.
- **Validated:** Confirmed -- `continue` on line 381 after logging.
- **Improvement:** Try to extract `id` from the malformed line and fail the corresponding future explicitly.

### M2. Worker routing duplicated in dispatcher
- **File:** `batch_dispatch.py:609`
- **Issue:** `worker_idx = fold_idx % self._pool.n_workers` hard-codes routing logic instead of using the pool's routing method.
- **Fix:** Use `self._pool`'s routing method to keep logic centralized.

### M3. Unnecessary atomic operations in single-threaded Rust worker
- **File:** `worker/mod.rs` (file-wide)
- **Issue:** Uses `Arc`, `AtomicU32`, `Ordering::SeqCst` for a process that runs single-threaded (`RAYON_NUM_THREADS=1`). Adds complexity without benefit.
- **Fix:** Low priority -- simplify if refactoring the module. No correctness issue.

## Low-Priority / Observations

### L1. `check_memory` duplicated between dispatchers
- **File:** `batch_dispatch.py` (two dispatcher classes)
- **Improvement:** Extract to shared utility function.

### L2. Cache eviction could block command processing
- **File:** `worker/mod.rs:200` area (evict_until_free)
- **Note:** Acceptable for current throughput. If cache grows large, the linear scan through LRU entries could slow command processing.

---

## Summary

| Severity | Count | Action Required |
|----------|-------|-----------------|
| Critical | 2     | Fix before production use |
| High     | 2     | Fix in next sprint |
| Medium   | 3     | Improve when touching these files |
| Low      | 2     | Nice-to-have |

The architecture is sound overall -- JSON-lines protocol, async reader/writer split, shared-nothing cache partitioning are all good design choices. The critical issues (C1: cache key collision, C2: id:0 parse error) should be addressed before the persistent worker mode is used in optimization runs.
