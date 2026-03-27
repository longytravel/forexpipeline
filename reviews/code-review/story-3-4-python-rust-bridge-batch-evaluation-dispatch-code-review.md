# Code Review: Story 3-4 — Python-Rust Bridge Batch Evaluation Dispatch

**Reviewer:** Claude Opus 4.6 (Adversarial Code Review)
**Date:** 2026-03-18
**Story File:** `_bmad-output/implementation-artifacts/3-4-python-rust-bridge-batch-evaluation-dispatch.md`
**Mode:** Single Reviewer

---

## Summary

**Issues Found:** 3 Critical, 4 High, 3 Medium, 2 Low

The Python-Rust bridge implementation is architecturally sound — subprocess dispatch via `asyncio.create_subprocess_exec`, structured D8 error propagation, crash-safe writes, and signal handling are all correctly implemented. However, there are contract violations, a missing dependency marked as done, and several incomplete AC implementations that need attention before this story can be marked done.

---

## CRITICAL Issues

### C1: Task 12 marked [x] but `arrow` crate dependency not added to Cargo.toml

**Severity:** CRITICAL (task completion audit failure)
**File:** `src/rust/crates/backtester/Cargo.toml`
**Evidence:** Task 12 explicitly lists `arrow = "53"` as a required dependency. The task is marked `[x]` complete. The actual Cargo.toml contains clap, serde, serde_json, sha2, ctrlc, common, cost_model, strategy_engine — but NO `arrow` crate.
**Impact:** Story 3-5 will be unable to write actual Arrow IPC output without adding this dependency. Marking this done when it isn't will mislead downstream story authors.
**Correct behavior:** Either add `arrow = "53"` now, or un-mark this subtask and document it as deferred to Story 3-5. The story spec was explicit that this dependency should be present.

### C2: Contracts missing `equity_curve` and `metrics` schemas — Rust schemas invented without contract SSOT

**Severity:** CRITICAL (contract violation)
**Files:**
- `contracts/arrow_schemas.toml` — only defines `[market_data]`, `[tick_data]`, `[backtest_trades]`, `[optimization_candidates]`
- `src/rust/crates/common/src/arrow_schemas.rs` — defines `EQUITY_CURVE_COLUMNS` (timestamp, equity_pips, drawdown_pips, open_trades) and `METRICS_COLUMNS` (total_trades, winning_trades, losing_trades, sharpe_ratio, max_drawdown_pips, net_pnl_pips, avg_trade_pips, strategy_id, config_hash)

**Evidence:** The story spec Task 8 says "Arrow schemas in Rust MUST match `contracts/arrow_schemas.toml` — add a build-time or startup validation check." The Rust code defines schemas for two tables that have NO corresponding contract entry. These schemas were invented by the implementation.
**Impact:** The contract is the cross-runtime SSOT (D2). Python's `output_verifier.py` and any future consumers have no authoritative reference for equity_curve or metrics schemas. If Story 3-5 or 3-6 implements their own version of these schemas, there's no contract to catch drift.
**Correct behavior:** Add `[equity_curve]` and `[backtest_metrics]` sections to `contracts/arrow_schemas.toml` matching the Rust-defined columns, then validate alignment in the Rust test.

### C3: Checkpoint filename `checkpoint.json` doesn't match contract pattern `checkpoint-{stage}.json`

**Severity:** CRITICAL (contract violation)
**Files:**
- `contracts/pipeline_checkpoint.toml:8` — `file_pattern = "checkpoint-{stage}.json"`
- `src/rust/crates/backtester/src/bin/forex_backtester.rs:248` — `output_dir.join("checkpoint.json")`

**Evidence:** The contract specifies the filename pattern includes the stage name (e.g., `checkpoint-backtest-running.json`). The implementation writes `checkpoint.json` with no stage in the filename. The Python orchestrator's `recover_from_checkpoint()` in Story 3-3 presumably looks for files matching the contract pattern.
**Correct behavior:** Change to `output_dir.join("checkpoint-backtest-running.json")` to match the contract `file_pattern`.

---

## HIGH Issues

### H1: Stub output files are JSON, NOT valid Arrow IPC — misleading code comment

**Severity:** HIGH
**File:** `src/rust/crates/backtester/src/output.rs:50-63`
**Evidence:** The `write_stub_arrow()` function writes a JSON object (`serde_json::json!({...})`) to `.arrow` files. The code comment at line 51 says "Arrow IPC File format: MAGIC + Schema + RecordBatch(es) + Footer + MAGIC" then says "For the stub, we write a JSON marker." The comment at line 55 says "This allows Python `pyarrow.ipc.open_file()` to open the file" — this is FALSE. pyarrow cannot open JSON as Arrow IPC.
**Impact:** AC #3 says results should be "Arrow IPC files... schemas match contracts." The stub approach is acceptable for the bridge round-trip, but the misleading comments will cause confusion for Story 3-5 implementers.
**Correct behavior:** Fix the comment to honestly state these are JSON stubs that pyarrow CANNOT open. Alternatively, write a minimal valid Arrow IPC file using a 0-row RecordBatch (the `arrow` crate would be needed for this — see C1).

### H2: `asyncio.get_event_loop()` deprecated pattern in BacktestExecutor

**Severity:** HIGH
**File:** `src/python/rust_bridge/backtest_executor.py:76`
**Evidence:** Code calls `asyncio.get_event_loop()` which is deprecated since Python 3.10 and emits DeprecationWarning. In Python 3.12+ calling this when no loop is running will eventually error.
**Correct behavior:** Replace with:
```python
try:
    loop = asyncio.get_running_loop()
    # Already in an event loop — bridge to sync
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        result = pool.submit(
            lambda: asyncio.run(self._runner.dispatch(job))
        ).result()
except RuntimeError:
    # No event loop — create one
    result = asyncio.run(self._runner.dispatch(job))
```

### H3: Memory pre-check inconsistency between Python and Rust

**Severity:** HIGH
**Files:**
- `src/python/rust_bridge/batch_runner.py:108` — `job.memory_budget_mb > available_mb`
- `src/rust/crates/backtester/src/memory.rs:52-54` — `usable_mb = available_mb.saturating_sub(OS_RESERVE_MB)` where `OS_RESERVE_MB = 2048`

**Evidence:** Python checks raw available memory without subtracting the 2GB OS reserve. Rust correctly subtracts it. A budget of 3000MB on a system with 4000MB available would pass Python's check but fail Rust's check (4000 - 2048 = 1952 < 3000), producing a confusing structured error from the Rust binary after Python already "validated" the memory.
**Correct behavior:** Python pre-check should subtract the same OS_RESERVE_MB (2048) or at minimum document the intentional discrepancy. Define the reserve constant once and share it.

### H4: AC #2 (mmap) not implemented — log says "mmap-ready" but no mmap occurs

**Severity:** HIGH
**File:** `src/rust/crates/backtester/src/bin/forex_backtester.rs:173-179`
**Evidence:** AC #2 says: "opens the market data file via memory-mapped I/O, verified by a startup log entry recording the mmap file path and size." The code only reads metadata (`std::fs::metadata`) and logs `"mmap-ready"`. No actual mmap call occurs. The log message is misleading — it implies mmap happened when it didn't.
**Correct behavior:** Either implement actual mmap (requires `arrow` or `memmap2` crate) or honestly log `"Market data validated (mmap deferred to Story 3-5)"`. Don't claim mmap-readiness in the log.

---

## MEDIUM Issues

### M1: `validate_schemas()` doesn't validate schemas — just checks file existence

**Severity:** MEDIUM
**File:** `src/python/rust_bridge/output_verifier.py:93-107`
**Evidence:** The function docstring says "Validate Arrow schemas against contracts/arrow_schemas.toml." The implementation just checks `path.exists() and path.stat().st_size > 0` — identical to what `verify_output()` already does. No pyarrow import, no schema reading, no contract comparison.
**Impact:** Story Task 3 says "Verify Arrow schemas match contracts defined in `contracts/arrow_schemas.toml`". This function provides zero schema validation. It's a renamed existence check.
**Correct behavior:** Acceptable as a stub (since files are JSON not Arrow), but add a `# TODO(3-5)` comment explaining the deferral and rename the function or add a clear docstring noting it's an existence check only.

### M2: `verify_output()` docstring claims fold score verification but doesn't call it

**Severity:** MEDIUM
**File:** `src/python/rust_bridge/output_verifier.py:40`
**Evidence:** Docstring says "If fold-aware evaluation was used, also verifies per-fold score files via `verify_fold_scores()`." The function body never calls `verify_fold_scores()`. The `BacktestExecutor.execute()` also doesn't call it after dispatch.
**Impact:** When fold-aware evaluation is used, per-fold score files won't be verified in the pipeline flow.
**Correct behavior:** Either call `verify_fold_scores()` from within `verify_output()` (checking if `fold-scores.json` exists) or remove the docstring claim. The BacktestExecutor should also verify fold scores when fold_boundaries are provided.

### M3: `MemoryBudget.allocate()` has TOCTOU race condition

**Severity:** MEDIUM
**File:** `src/rust/crates/backtester/src/memory.rs:90-103`
**Evidence:** The method loads `allocated` with `Relaxed` ordering, checks if `new_total_mb > total_mb`, then does `fetch_add` with `Relaxed` ordering. Two concurrent threads could both pass the check and both succeed, exceeding the budget. The `AtomicU64` type signals thread-safety intent but the load-check-add pattern is not atomic.
**Impact:** Current usage is single-threaded (the binary processes bars sequentially), so this is a latent bug. If Rayon parallelism is added in Story 3-5, this becomes a real race.
**Correct behavior:** Use `compare_exchange` loop:
```rust
loop {
    let current = self.allocated.load(Ordering::Acquire);
    if (current + bytes) / (1024 * 1024) > self.total_mb {
        return Err(...);
    }
    if self.allocated.compare_exchange(current, current + bytes, Ordering::Release, Ordering::Relaxed).is_ok() {
        break;
    }
}
```

---

## LOW Issues

### L1: Manual `now_iso()` date calculation without chrono/time crate

**Severity:** LOW
**File:** `src/rust/crates/backtester/src/bin/forex_backtester.rs:263-278`
**Evidence:** Manual epoch-to-date conversion using a `days_to_date()` function. This is fragile for leap year edge cases and non-standard date scenarios.
**Correct behavior:** Consider adding `chrono` or `time` crate. Current implementation works for timestamps but is a maintenance risk.

### L2: Misleading Arrow IPC format comment contradicts JSON stub implementation

**Severity:** LOW
**File:** `src/rust/crates/backtester/src/output.rs:51-53`
**Evidence:** Comment describes Arrow IPC wire format then immediately writes JSON. Should state "For the stub, we write a JSON marker that output_verifier checks by file existence only."

---

## Acceptance Criteria Scorecard

| AC | Description | Status | Evidence |
|----|-------------|--------|----------|
| AC #1 | Python invokes Rust binary via subprocess with structured job parameters | **Fully Met** | `batch_runner.py:140` uses `asyncio.create_subprocess_exec`, `_build_args()` passes all CLI parameters including fold/window/batch |
| AC #2 | Arrow IPC market data opened via mmap, verified by startup log | **Partially Met** | `forex_backtester.rs:174` reads `std::fs::metadata` and logs size, but does NOT perform actual mmap. Log says "mmap-ready" misleadingly (H4) |
| AC #3 | Results written as Arrow IPC with crash-safe semantics | **Partially Met** | Crash-safe write pattern (partial → fsync → rename) correctly implemented in `output.rs:92-111`. But files are JSON stubs, not Arrow IPC (H1). Schema validation is existence-only (M1) |
| AC #4 | Structured JSON error on stderr matching D8 schema | **Fully Met** | `error_types.rs` StructuredError with error_type/category/message/context. `error_parser.py` parses and maps all 3 categories correctly. Panic hook installed. |
| AC #5 | Graceful cancellation with checkpoint within 5 seconds | **Fully Met** | `forex_backtester.rs:151-160` ctrlc handler, AtomicBool flag, checkpoint write. `batch_runner.py:276-295` terminate → 5s wait → kill escalation |
| AC #6 | Periodic progress updates to progress file | **Fully Met** | `progress.rs` ProgressReport + crash-safe write + should_report throttling. `batch_runner.py:211-230` get_progress polling |
| AC #7 | Memory budget logged and enforced at startup | **Fully Met** | `memory.rs` MemoryBudget with system memory check, batch size computation, startup logging at `forex_backtester.rs:138-141` |
| AC #8 | Python detects crash, captures stderr, continues running | **Fully Met** | `batch_runner.py:164-170` captures exit code + stderr. `error_parser.py` handles structured, malformed, and empty stderr. Process isolation via subprocess |
| AC #9 | Deterministic output files byte-identical | **Partially Met** | JSON stubs are deterministic for same inputs. Sort-by-timestamp/trade_id documented but deferred to Story 3-5. Real Arrow IPC determinism untested |

---

## Task Completion Audit

| Task | Marked | Actually Done | Finding |
|------|--------|---------------|---------|
| Task 1: BatchRunner class | [x] | Yes | — |
| Task 2: ErrorParser module | [x] | Yes | — |
| Task 3: OutputVerifier module | [x] | Partially | Schema validation is existence-only (M1), fold score verification not wired (M2) |
| Task 4: StageExecutor implementation | [x] | Yes | Deprecated asyncio pattern (H2) |
| Task 5: Rust CLI argument parser | [x] | Yes | — |
| Task 6: Common crate infrastructure | [x] | Yes | — |
| Task 7: Progress reporting | [x] | Yes | — |
| Task 8: Arrow schema validation + crash-safe output | [x] | Partially | Schemas written to contracts SSOT but equity_curve/metrics contracts don't exist (C2). Output is JSON stub, not Arrow IPC (H1) |
| Task 9: Graceful cancellation | [x] | Yes | Checkpoint filename doesn't match contract (C3) |
| Task 10: Memory budget enforcement | [x] | Yes | Race condition in allocate (M3) |
| Task 11: Integration tests | [x] | Yes | — |
| Task 12: Wire modules + dependencies | [x] | Partially | `arrow = "53"` dependency not added (C1) |

---

## Git vs Story Discrepancies

Not a git repository — cannot verify file-level discrepancies via git.

---

## Review Follow-ups (AI)

- [ ] [AI-Review][CRITICAL] Add `[equity_curve]` and `[backtest_metrics]` sections to `contracts/arrow_schemas.toml` matching Rust-defined columns [`contracts/arrow_schemas.toml`]
- [ ] [AI-Review][CRITICAL] Fix checkpoint filename to `checkpoint-backtest-running.json` per `contracts/pipeline_checkpoint.toml` pattern [`src/rust/crates/backtester/src/bin/forex_backtester.rs:248`]
- [ ] [AI-Review][CRITICAL] Either add `arrow = "53"` to `Cargo.toml` or un-mark Task 12 and document deferral [`src/rust/crates/backtester/Cargo.toml`]
- [ ] [AI-Review][HIGH] Fix misleading comment in `write_stub_arrow()` — pyarrow cannot open JSON stubs [`src/rust/crates/backtester/src/output.rs:51-55`]
- [ ] [AI-Review][HIGH] Replace deprecated `asyncio.get_event_loop()` with `asyncio.get_running_loop()` pattern [`src/python/rust_bridge/backtest_executor.py:76`]
- [ ] [AI-Review][HIGH] Align Python memory pre-check with Rust OS reserve (2048MB) [`src/python/rust_bridge/batch_runner.py:108`]
- [ ] [AI-Review][HIGH] Fix misleading "mmap-ready" log — either implement mmap or log honestly [`src/rust/crates/backtester/src/bin/forex_backtester.rs:177`]
- [ ] [AI-Review][MEDIUM] Add TODO comment to `validate_schemas()` explaining it's an existence-only stub [`src/python/rust_bridge/output_verifier.py:93`]
- [ ] [AI-Review][MEDIUM] Either call `verify_fold_scores()` from `verify_output()` or remove docstring claim [`src/python/rust_bridge/output_verifier.py:40`]
- [ ] [AI-Review][MEDIUM] Fix TOCTOU race in `MemoryBudget.allocate()` using `compare_exchange` [`src/rust/crates/backtester/src/memory.rs:90-103`]
