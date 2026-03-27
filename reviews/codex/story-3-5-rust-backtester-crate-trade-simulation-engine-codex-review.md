# Story 3-5-rust-backtester-crate-trade-simulation-engine: Story 3.5: Rust Backtester Crate — Trade Simulation Engine — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-19
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

**HIGH Findings**
- AC4 is not implemented. The backtester does not share signal evaluation with `strategy_engine`; it reimplements evaluation locally in `evaluate_bar_signal()`, ignores confirmations/confidence, and reduces `crosses_above`/`crosses_below` to plain threshold checks. That means backtest and live can diverge materially. [engine.rs#L394](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/engine.rs#L394) [engine.rs#L450](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/engine.rs#L450) [lib.rs#L7](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/lib.rs#L7)
- AC10 is not implemented. Memory budgeting is only a startup pre-check; the engine then reads all Arrow batches into memory, concatenates them, accumulates all trades/equity in `Vec`s, and writes outputs only after the run completes. There is no streaming result writer in the evaluation loop and no budget object in `run_backtest()`. [forex_backtester.rs#L127](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L127) [engine.rs#L93](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/engine.rs#L93) [engine.rs#L136](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/engine.rs#L136) [engine.rs#L378](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/engine.rs#L378)
- AC2 is not met as written. The loop processes exits before entries, not `entry rules -> exit rules -> position management -> record trades`. [engine.rs#L220](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/engine.rs#L220) [engine.rs#L252](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/engine.rs#L252)
- AC6 is only partial because end-of-data closes are missing from the equity curve. The last equity point is recorded before the forced `EndOfData` exit, so final equity/drawdown can disagree with realized trade results. [engine.rs#L306](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/engine.rs#L306) [engine.rs#L342](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/engine.rs#L342)
- AC3 is only partial. Costs are session-aware, but fills bypass `CostModel::apply_cost()` and manually duplicate its math with `get_cost()`. That breaks the explicit contract and creates drift risk if the cost crate changes. [trade_simulator.rs#L60](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/trade_simulator.rs#L60) [trade_simulator.rs#L98](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/trade_simulator.rs#L98) [cost_engine.rs#L22](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/cost_model/src/cost_engine.rs#L22)

**MEDIUM Findings**
- AC1 is only partial because the CLI parses the strategy spec but never validates it with `strategy_engine::validate_spec()`. [forex_backtester.rs#L158](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L158) [parser.rs#L8](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/parser.rs#L8)
- Fold-aware and batch evaluation are mostly stubs despite being marked done in the story: fold handling only skips embargo bars, `fold_for_bar()` is unused, no per-fold scores are returned, and `--param-batch` is parsed but never used. [fold.rs#L48](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/fold.rs#L48) [engine.rs#L206](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/engine.rs#L206) [forex_backtester.rs#L71](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L71)
- Several strategy behaviors are silently unsupported: `DayOfWeek` and `Volatility` filters log a warning and then let all bars pass, and most extended exit reasons are never emitted anywhere in the engine. [engine.rs#L476](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/engine.rs#L476) [position.rs#L27](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/position.rs#L27) [position.rs#L127](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/position.rs#L127)

**Acceptance Criteria Scorecard**

| AC | Status | Notes |
| --- | --- | --- |
| 1 | Partially Met | Crate/binary exists and loads inputs, but spec is parsed, not validated. |
| 2 | Not Met | Loop order is exit-first, not entry-first. |
| 3 | Partially Met | Session costs are applied, but not via `cost_model.apply_cost()`. |
| 4 | Not Met | Backtester reimplements evaluation instead of sharing `strategy_engine` logic. |
| 5 | Fully Met | Trade log includes raw/adjusted prices, per-leg costs, sessions, signal ID, duration, exit reason. |
| 6 | Partially Met | Mark-to-market points are recorded per bar, but final forced close is not reflected in the curve. |
| 7 | Fully Met | Required metrics are computed and written. |
| 8 | Fully Met | Core outputs are deterministic in-process; trades are sorted deterministically. |
| 9 | Fully Met | Quarantined bars suppress new entries while exit checks still run first. |
| 10 | Not Met | No real pre-allocation/streaming enforcement during evaluation; memory can grow with input/output size. |

**Test Coverage Gaps**
- `test_e2e_fold_aware_evaluation` does not verify fold separation, per-fold scores, or embargo correctness; it only checks that some equity exists. [test_backtest_e2e.rs#L388](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/tests/test_backtest_e2e.rs#L388)
- `test_e2e_pre_computed_signals` never asserts that the `sma_20` column actually changes entries/trades; it only checks curve length. [test_backtest_e2e.rs#L421](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/tests/test_backtest_e2e.rs#L421)
- `test_e2e_checkpoint_resume` does not resume from a checkpoint at all. It just runs once and asserts the run completed. [test_backtest_e2e.rs#L547](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/tests/test_backtest_e2e.rs#L547)
- The CLI “successful run” test uses `ARROW_STUB` bytes instead of a real Arrow IPC file, so it cannot validate the real happy path if the fixture is present. [test_bridge_cli.rs#L115](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/tests/test_bridge_cli.rs#L115)
- There are no assertions for same-bar SL/TP precedence, ignored filters, end-of-data equity reconciliation, or memory-budget/streaming behavior.

4 of 10 criteria are fully met, 3 are partially met, and 3 are not met.

Static review only: this workspace is not a git repository here, and shell policy blocked running `cargo test`, so I could not verify story claims against git diffs or execute the suite directly.
