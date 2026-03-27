# Story 3-4-python-rust-bridge-batch-evaluation-dispatch: Story 3.4: Python-Rust Bridge — Batch Evaluation Dispatch — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-18
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

**HIGH findings**
- AC2 is not implemented. The Rust binary never memory-maps the Arrow IPC input; it only reads file metadata and prints a `"mmap-ready"` log line. There is also no `arrow` dependency in the backtester crate, so the required `arrow::io::ipc::read::FileReader` path is absent. See [forex_backtester.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L173), [forex_backtester.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L176), [Cargo.toml](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/Cargo.toml#L6).

- AC3 is not implemented. The `.arrow` outputs are JSON stubs written by `serde_json`, not Arrow IPC files, and Python “schema validation” only checks existence/non-empty size. The SSOT contract also does not define `equity_curve` or `metrics`, so there is nothing real to validate those files against. See [output.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/output.rs#L24), [output.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/output.rs#L57), [output_verifier.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/output_verifier.py#L93), [arrow_schemas.toml](/c/Users/ROG/Projects/Forex Pipeline/contracts/arrow_schemas.toml#L27).

- AC5 is not implemented. On Windows, `BatchRunner.cancel()` uses `proc.terminate()`/`kill()`, which is forceful termination rather than the story-required `CTRL_BREAK` path, and the Rust binary only checks the cancellation flag once before writing outputs, not during execution. It also turns cancellation into an error exit instead of a graceful checkpointed completion. See [batch_runner.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/batch_runner.py#L199), [batch_runner.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/batch_runner.py#L276), [forex_backtester.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L151), [forex_backtester.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L199), [error_types.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/common/src/error_types.rs#L127).

- AC6 is only stubbed. The binary writes `progress.json` only at start and end, with `total_bars = 1` and `estimated_seconds_remaining = 0.0`; the periodic reporting helper is never used. That means the file is not suitable for real long-running status display. See [forex_backtester.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L184), [forex_backtester.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L218), [progress.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/progress.rs#L45).

- AC7 is only partially implemented, and the most important computed value is discarded. `compute_batch_size()` is logged but never used to size work, throttle concurrency, or pre-allocate buffers; `MemoryBudget::allocate()` is never called. The code therefore does not actually enforce the selected batch size or pre-allocation contract. See [forex_backtester.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L134), [forex_backtester.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L139), [memory.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/memory.rs#L71), [memory.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/memory.rs#L90).

- The claimed StageRunner integration is broken. `StageRunner` calls executors with only `{"artifacts_dir": ...}`, but `BacktestExecutor` requires `strategy_spec_path`, `market_data_path`, `cost_model_path`, and `config_hash`, so a real `BACKTEST_RUNNING` stage cannot build a job. Also, `StageRunner` skips stages with no registered executor, and I found no registration code in the reviewed files. See [stage_runner.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L117), [stage_runner.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L355), [stage_runner.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L391), [backtest_executor.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/backtest_executor.py#L56), [backtest_executor.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/backtest_executor.py#L163).

**MEDIUM findings**
- Rust errors are parsed and wrapped, but they are not really routed through the orchestrator’s D8 recovery behavior. `BacktestExecutor` returns a failed `StageResult`; `StageRunner` logs/checkpoints it, then returns immediately instead of retrying `external_failure` or throttling `resource_pressure`. See [backtest_executor.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/backtest_executor.py#L91), [stage_runner.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L437), [stage_runner.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L444).

- Fold/window/batch dispatch support is mostly argument plumbing only. Rust parses `fold_boundaries` JSON and validates `param_batch` exists, but does not use fold/window/batch inputs, does not emit per-fold outputs, and Python never calls `verify_fold_scores()` from `verify_output()`. See [forex_backtester.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L124), [forex_backtester.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L209), [output_verifier.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/output_verifier.py#L34), [output_verifier.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/output_verifier.py#L110).

- Active subprocess tracking is keyed only by `config_hash`, so dispatching two identical jobs concurrently will overwrite the first process handle and make cancellation/progress targeting ambiguous. See [batch_runner.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/batch_runner.py#L75), [batch_runner.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/batch_runner.py#L148), [batch_runner.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/batch_runner.py#L206).

**Acceptance Criteria Scorecard**

| AC | Status | Notes |
|---|---|---|
| 1 | Fully Met | Python builds and passes the required CLI args. |
| 2 | Not Met | No actual mmap or Arrow reader usage. |
| 3 | Not Met | Outputs are JSON stubs, not Arrow IPC; schema validation is a no-op. |
| 4 | Partially Met | Structured JSON errors exist and Python parses them, but real orchestrator routing/recovery is incomplete. |
| 5 | Not Met | Cancellation is forceful on Windows, not graceful/checkpointed. |
| 6 | Partially Met | `progress.json` exists, but updates are not periodic and values are dummy. |
| 7 | Partially Met | Budget is checked/logged, but no pre-allocation or enforcement uses the computed batch size. |
| 8 | Fully Met | Subprocess isolation keeps Python alive on Rust failures. |
| 9 | Partially Met | Determinism is shown only for placeholder stub files, not compliant backtest Arrow outputs. |

**Test Coverage Gaps**
- No test proves the output files are valid Arrow IPC or match the contract with `pyarrow`; the current live tests only check file existence. See [test_batch_runner.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_rust_bridge/test_batch_runner.py#L441), [test_bridge_cli.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/tests/test_bridge_cli.rs#L103).
- No integration test covers cancellation, checkpoint creation, and 5-second graceful exit, despite that being a core AC. I found no such case in [test_batch_runner.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_rust_bridge/test_batch_runner.py#L1) or [test_bridge_cli.rs](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/tests/test_bridge_cli.rs#L1).
- No test exercises actual `StageRunner` registration/execution for `BACKTEST_RUNNING`, so the broken context handoff is currently invisible. See [stage_runner.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L391) and the isolated executor-only tests at [test_batch_runner.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_rust_bridge/test_batch_runner.py#L340).
- No test verifies true mmap behavior or even asserts the startup log contains a real mmap open event.
- No live test covers fold-aware outputs, window bounds, or parameter batches; the current tests stop at arg serialization for those features. See [test_batch_runner.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_rust_bridge/test_batch_runner.py#L272).

Summary: 2 of 9 criteria are fully met, 4 are partially met, and 3 are not met.

No git repository metadata was available in this workspace, so I could not do the workflow’s git-vs-story discrepancy audit.
