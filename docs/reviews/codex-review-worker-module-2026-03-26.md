# Codex Code Review: Rust Worker Module
**Date:** 2026-03-26
**Reviewer:** gpt-5.4 (high reasoning) via Codex
**Files:** `src/rust/crates/backtester/src/worker/mod.rs`, `src/rust/crates/backtester/src/bin/forex_worker.rs`

## Findings

### HIGH

1. **Streaming protocol lacks chunk metadata / terminal envelope** — Large `eval` requests emit repeated `ok_results`/`err` messages for one `id`, but the client resolves exactly one future per id and treats later lines as stray output. Large responses lose data and per-group failures go unnoticed.
   - mod.rs:320, 330, 383, 397, 453
   - worker_client.py:283, 392

2. **Unchecked window_start/window_end causes usize underflow** — `window_start > window_end` underflows `end - start` to a huge capacity in `Vec::with_capacity()`, causing panic or enormous allocation before any useful error.
   - mod.rs:289, 352
   - batch_eval.rs:146, 654, 682

3. **LruCache hard cap (1024) silently evicts without updating used_bytes** — `WorkerCache::new()` hard-codes `LruCache::new(1024)`. Inserting the 1025th key triggers internal eviction without consulting `in_flight`/`strong_count` or adjusting `used_bytes`, breaking memory accounting and eviction safety.
   - mod.rs:145, 147, 162, 269

### MEDIUM

4. **Memory budget enforced after full Arrow load** — `handle_load_data()` calls `engine::load_market_data()` before any eviction. A single oversized dataset can exceed RSS well before `budget_bytes` is checked.
   - mod.rs:245, 257
   - engine.rs:85, 90, 99

5. **Cache hit skips data_path validation** — Reusing a key for a different Arrow file silently serves stale data instead of reloading or rejecting the mismatch.
   - mod.rs:235, 237, 240

6. **Re-init with smaller/zero budget doesn't evict** — After `init(..., memory_budget_mb=0)`, the worker still holds and evaluates previously cached batches under a nominal zero-budget configuration.
   - mod.rs:140, 217, 219, 228

7. **stdin read failures exit with code 0** — I/O errors are logged and the loop breaks, but `run()` returns `Ok(())`. Supervisors get exit code 0 with no machine-readable failure for protocol/input-pipe errors.
   - mod.rs:420, 424, 471
   - forex_worker.rs:17

### LOW

8. **BufWriter neutralized by per-line flush** — Unconditional `flush()` after every response line makes normal handling syscall-heavy. The streaming path is especially expensive because every partial result forces an immediate flush.
   - mod.rs:414, 458, 476, 481

## Assumption
The 1024-entry cache finding relies on standard bounded-capacity `lru::LruCache` semantics for `put()`. The crate source was not inspectable in the sandbox but this is standard behavior for the `lru` crate.
