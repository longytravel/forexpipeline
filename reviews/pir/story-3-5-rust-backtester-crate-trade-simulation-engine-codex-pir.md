# Story 3-5-rust-backtester-crate-trade-simulation-engine: Story 3.5: Rust Backtester Crate — Trade Simulation Engine — Codex PIR

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-19
**Type:** Post-Implementation Review (alignment analysis)

---

**1. Objective Alignment**

Assessment: `ADEQUATE`

Evidence:
- The story clearly advances artifact completeness: it emits `trade-log.arrow`, `equity-curve.arrow`, `metrics.arrow`, `progress.json`, checkpoints, and `run_metadata.json`, with crash-safe write patterns in both result and progress paths. [output.rs:21](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/output.rs#L21) [output.rs:244](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/output.rs#L244) [progress.rs:25](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/progress.rs#L25) [engine.rs:196](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/engine.rs#L196)
- It advances fidelity on execution-cost attribution: fills use `cost_model.apply_cost()`, and trade outputs retain raw prices plus per-leg spread/slippage/session attribution, which directly supports later reconciliation and evidence-pack work. [trade_simulator.rs:60](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/trade_simulator.rs#L60) [trade_simulator.rs:101](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/trade_simulator.rs#L101) [output.rs:57](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/output.rs#L57) [prd.md:95](\/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L95)
- It advances reproducibility partway: outputs are deterministically ordered, `config_hash` is embedded in metrics/run metadata, and both Rust and Python E2E tests compare reruns for value equality. [engine.rs:398](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/engine.rs#L398) [output.rs:186](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/output.rs#L186) [test_backtest_e2e.rs:232](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/tests/test_backtest_e2e.rs#L232) [test_backtester_e2e.py:237](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_rust_bridge/test_backtester_e2e.py#L237)

Concrete observations:
- The biggest alignment problem is fidelity: architecture says signal fidelity depends on shared evaluation in `strategy_engine`, but this crate still evaluates signals locally in `evaluate_bar_signal()`. That is an understandable implementation stopgap, but it does not fully serve the system’s “same backtest/live signal” objective. [architecture.md:1027](\/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L1027) [architecture.md:1043](\/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L1043) [engine.rs:423](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/engine.rs#L423) [strategy_engine/lib.rs:1](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/strategy_engine/src/lib.rs#L1)
- Operator confidence is helped by persisted artifacts and structured stderr, but hurt by silent degradations: missing precomputed columns merely warn and skip conditions, and `DayOfWeek`/`Volatility` filters warn once and then allow all bars through. For a non-coder, that can look like a valid run while actually weakening fidelity. [engine.rs:446](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/engine.rs#L446) [engine.rs:466](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/engine.rs#L466) [engine.rs:516](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/engine.rs#L516) [prd.md:82](\/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L82)
- It is not generally over-engineered where the architecture explicitly wants reuse: the lib+binary split is justified for optimizer/validator reuse. The overreach is elsewhere: fold/batch/extended-exit surface area was added beyond what V1 actually consumes. [Cargo.toml:6](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/Cargo.toml#L6) [architecture.md:1003](\/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L1003) [3-5-rust-backtester-crate-trade-simulation-engine.md:10](\/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-5-rust-backtester-crate-trade-simulation-engine.md#L10)

**2. Simplification**

Assessment: `CONCERN`

Evidence:
- `--param-batch` is exposed and validated, but never used after argument parsing. [forex_backtester.rs:71](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L71) [forex_backtester.rs:117](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L117)
- `FoldConfig.fold_for_bar()` exists, but nothing in production uses it; fold handling is limited to embargo skipping. [fold.rs:59](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/fold.rs#L59) [engine.rs:213](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/engine.rs#L213)
- Most of `MemoryBudget` is not in the runtime path. The binary only does `new()` plus `check_system_memory()`. The tracking/allocation methods exist mostly as internal complexity and tests. [forex_backtester.rs:129](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L129) [memory.rs:69](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/memory.rs#L69) [memory.rs:90](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/memory.rs#L90)

Concrete observations:
- A simpler V1 would have been: one deterministic trade-simulation engine, three canonical Arrow outputs, checkpoints, and structured errors. That core is the part that actually serves the pipeline.
- The added fold/batch scaffolding does not yet buy downstream value. It increases operator-facing and developer-facing surface area without completing the promised contract.
- The extended `ExitReason` enum is broader than the implemented engine behavior. In practice the live paths emitted here are `StopLoss`, `TakeProfit`, `TrailingStop`, and `EndOfData`; the rest mostly expand conceptual scope without current system benefit. [position.rs:27](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/position.rs#L27) [position.rs:127](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/position.rs#L127) [engine.rs:382](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/engine.rs#L382)

**3. Forward Look**

Assessment: `CONCERN`

Evidence:
- The current output contract is enough for Story 3.6’s basic ingest path and Story 3.7’s evidence-pack inputs: those stories explicitly expect `trade-log.arrow`, `equity-curve.arrow`, and `metrics.arrow`. [3-6-backtest-results-artifact-storage-sqlite-ingest.md:30](\/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L30) [3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md:24](\/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L24) [3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md:120](\/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L120)
- But fold-aware downstreams already expect a separate per-fold artifact (`fold-scores.json`), and this story does not write one. [output_verifier.py:40](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/rust_bridge/output_verifier.py#L40) [output_verifier.py:111](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/rust_bridge/output_verifier.py#L111) [test_batch_runner.py:233](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_rust_bridge/test_batch_runner.py#L233)
- Architecture also frames signal artifacts as part of the evaluation interface, which matters later for reconciliation and backtest/live signal comparison, but this story only emits trades/equity/metrics. [architecture.md:774](\/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L774) [architecture.md:910](\/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L910)

Concrete observations:
- For Story 3.6 and 3.7, the crate is mostly on the right path: the three core artifacts are present and richly attributed enough for SQLite ingest and evidence-pack assembly.
- For optimizer/validation growth, the story is not fully setting the next step up correctly. The code advertises fold-aware and batch evaluation, but the publishable output contract for that path is incomplete.
- The largest scaling assumption is that unsupported filters and locally inferred direction are acceptable for V1. That may hold for a narrow one-family slice, but it will not hold as soon as strategy variety grows or live/backtest fidelity becomes a gate instead of a future fix. [engine.rs:516](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/engine.rs#L516) [engine.rs:538](\/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/engine.rs#L538) [prd.md:119](\/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L119)

**Overall**

Overall assessment: `REVISIT`

The story delivers a useful deterministic trade-simulation core with strong artifact emission and good cost attribution, so it is not off-track. But against the system’s actual V1 success bar, the unresolved fidelity gaps, incomplete fold/batch contract, and silent pass-through behavior are significant enough that I would not treat Story 3.5 as fully aligned to the platform objectives without qualification.

This PIR is based on source/docs inspection in a read-only session; I did not execute the test suite.
