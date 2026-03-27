# PIR: Story 3-5-rust-backtester-crate-trade-simulation-engine — Story 3.5: Rust Backtester Crate — Trade Simulation Engine

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-19
**Type:** Post-Implementation Review (final alignment assessment)

---

## Codex Assessment Summary

Codex rated Objective Alignment ADEQUATE, Simplification CONCERN, Forward Look CONCERN, overall REVISIT. Key observations and my responses:

1. **Signal evaluation local instead of strategy_engine::Evaluator (AC #4 gap)** — **AGREE on the gap, DISAGREE on severity.** The `strategy_engine` crate exports parser, validator, types, and registry — but no `Evaluator` implementation exists. The backtester correctly built local `evaluate_bar_signal()` because the upstream type doesn't exist. Architecture D14 Phase 1 explicitly keeps indicators in Python with pre-computed signals via Arrow IPC; the shared Evaluator is Phase 2+ work. This is a known deferral, not an oversight. The synthesis report documents this rejection with evidence (strategy_engine/src/lib.rs exports confirmed).

2. **Silent filter degradation (DayOfWeek/Volatility warn once, then pass all bars)** — **AGREE.** This is a genuine operator-confidence concern. A run with missing filter columns looks like a valid run while actually weakening signal fidelity. Mitigated by stderr warnings and synthesis-pass deduplication, but for a non-coder operator this is a subtle failure mode. Acceptable for V1's single-strategy scope but should be tracked.

3. **`--param-batch` parsed but never consumed** — **AGREE on the dead code, DISAGREE it rises to CONCERN.** The CLI arg exists for interface compatibility with Story 3-4's bridge contract. The synthesis report explicitly defers batch parameter evaluation to Epic 5. This is documented scaffolding, not a broken feature. The lessons-learned file already captures the rule: "An accepted-but-ignored argument is worse than a missing one."

4. **`fold_for_bar()` unused in production** — **AGREE** the method is unused. However, `FoldConfig::is_embargo_bar()` IS used in the engine's main loop for embargo bar handling, and the synthesis pass fixed a real bug where embargo bars skipped exit checks. The fold module (~80 lines) provides genuine functionality.

5. **MemoryBudget tracking methods mostly unused** — **PARTIALLY AGREE.** `new()`, `check_system_memory()`, `compute_batch_size()`, and `allocate()` are all used. The `pre_allocate_pools` concept doesn't exist as a method — engine uses `Vec::with_capacity()` instead. The module is from Story 3-4, not new code here. Minor dead code, not concerning.

6. **Extended ExitReason enum broader than implemented behavior** — **AGREE but ACCEPTABLE.** Only `StopLoss`, `TakeProfit`, `TrailingStop`, and `EndOfData` are triggered in practice. The remaining 7 variants (ChandelierExit, SignalReversal, SubBarM1Exit, StaleExit, PartialClose, BreakevenWithOffset, MaxBarsExit) exist for D10's extended exit types. An enum is zero-cost at runtime and prevents Arrow schema breaks when those exits are implemented. This is forward-compatible typing, not over-engineering.

7. **`fold-scores.json` not produced despite downstream expectations** — **PARTIALLY AGREE.** `output_verifier.py` references it, but the story spec describes fold-aware evaluation as returning per-fold scores alongside aggregate metrics — the engine does track fold boundaries for embargo. Full per-fold score output is part of the Epic 5 optimization work. Story 3-6/3-7 do not depend on fold-scores.json.

8. **Signal artifacts not emitted for reconciliation** — **AGREE this is a gap** for future reconciliation (architecture D14 mentions signal artifacts). However, this is out of scope for Story 3.5 which is the trade simulation engine. Signal artifact emission is reconciliation-layer work (Story 3.7+).

**Codex missed:**
- The synthesis pass fixed a real bug where embargo bars skipped exit checks entirely, leaving open positions unprotected during fold boundary embargo zones. This was a correctness fix that Codex didn't flag.
- The synthesis pass also fixed crossover detection (`crosses_above` was `value > threshold` instead of proper `prev <= threshold AND current > threshold`), which would have produced orders-of-magnitude more false signals.
- The `apply_cost()` migration was completed in synthesis, closing the most impactful fidelity gap.

## Objective Alignment
**Rating:** ADEQUATE

The story delivers the core trade simulation engine serving all four system objectives:

- **Artifact completeness:** Produces `trade-log.arrow` (20 columns), `equity-curve.arrow` (5 columns), `metrics.arrow` (19 columns) — all matching `contracts/arrow_schemas.toml`. Plus `run_metadata.json`, `progress.json`, and crash-safe checkpoint support. This is the full artifact set that Stories 3.6 and 3.7 expect.

- **Fidelity:** Session-aware cost application via `cost_model.apply_cost()` (fixed in synthesis from manual calculation). Per-leg spread/slippage breakdown in trade records enables downstream reconciliation. Fill model uses correct bid/ask sides (ask for long entry, bid for short entry). No look-ahead in bar data.

- **Reproducibility:** Deterministic bar ordering, `config_hash` embedded in metrics and metadata, value-level comparison tests (not file-hash). Both Rust E2E and Python E2E tests verify rerun equality.

- **Operator confidence:** Structured JSON errors on stderr, progress reporting every 10K bars, graceful cancellation with checkpoint. Weakened by silent filter degradation (warn-once for missing filter columns).

The signal evaluation gap (AC #4) is the largest alignment concern, but it is caused by an upstream dependency absence (strategy_engine::Evaluator does not exist), not by an implementation choice in this story. Architecture D14 Phase 1 explicitly defers Rust indicator computation.

## Simplification
**Rating:** ADEQUATE

I disagree with Codex's CONCERN rating. The production code path is clean and minimal:

**Core path (used):** Load Arrow IPC → iterate bars chronologically → check exits → update trailing stops → skip quarantined/embargo bars → evaluate pre-computed signal columns → manage position → record equity → periodic checkpoint → write three Arrow outputs with crash-safe semantics.

**Scaffolding (unused but justified):**
- `--param-batch` CLI arg: Required for Story 3-4 bridge contract compatibility (~10 lines)
- Extended `ExitReason` enum: Zero-cost type definition, prevents schema breaks (~30 lines)
- `fold_for_bar()`: One unused method in an otherwise active module (~15 lines)

The engine.rs main loop is ~200 lines of straightforward bar iteration. The output writer is schema-driven. The trade simulator is two fill functions plus PnL computation. There is no abstraction layer beyond what's needed. A simpler V1 would essentially be what was built minus ~55 lines of scaffolding.

## Forward Look
**Rating:** ADEQUATE

**Story 3.6 (Artifact Storage & SQLite Ingest):** The three Arrow output files (`trade-log.arrow`, `equity-curve.arrow`, `metrics.arrow`) are exactly what 3.6 expects to ingest. Schemas match `contracts/arrow_schemas.toml`. Cost attribution columns (raw prices, spread, slippage, sessions) are present for breakdown queries. ✓

**Story 3.7 (AI Analysis Layer):** Trade records have enough data for evidence-pack assembly without re-simulation. Equity curve includes unrealized PnL component for drawdown analysis. Metrics include unannualized Sharpe, R-squared, max drawdown (amount + pct + duration) for AI narrative generation. ✓

**Epic 5 (Optimization):** The library-with-binary split enables the optimizer to call `run_backtest()` directly. Fold boundary handling works (embargo bars tested). Batch parameter evaluation is scaffolded but unimplemented — this is explicitly deferred. The `fold-scores.json` gap needs to be addressed when Epic 5 stories are written.

**Signal fidelity scaling:** The local `evaluate_bar_signal()` works for V1's single-strategy-family scope with pre-computed signals. When strategy variety grows or backtest/live signal comparison becomes a gate, the shared Evaluator in strategy_engine will need to be built. This is a known architectural boundary, not a surprise.

## Observations for Future Stories

1. **Track the silent filter degradation pattern.** When writing optimizer or multi-strategy stories, ensure that missing filter columns cause a hard failure (or at minimum, a prominent warning in output metadata), not silent pass-through. The current warn-once-to-stderr approach risks producing misleading optimization results at scale.

2. **`--param-batch` must be connected or removed.** Epic 5 stories should either implement batch parameter evaluation (reading the JSON, iterating parameter sets, producing per-set results) or remove the CLI arg. The current "accepted-but-ignored" state is explicitly documented in lessons-learned as an anti-pattern.

3. **`fold-scores.json` contract gap.** `output_verifier.py` references fold-scores verification, but the backtester doesn't produce this artifact. Epic 5 stories must either add this output to the backtester or update the verifier to not expect it.

4. **Strategy engine Evaluator is the largest deferred dependency.** When the Evaluator is built (likely Epic 4+), the backtester's local `evaluate_bar_signal()` must be replaced. The current implementation is ~70 lines of condition matching that should map cleanly to an Evaluator API, but this migration needs to be an explicit story task, not assumed.

5. **Crossover detection quality.** The synthesis pass fixed `crosses_above`/`crosses_below` to properly track previous-bar values. Future stories adding new comparator types should follow this pattern (maintain `prev_bar_values` HashMap) and add dedicated unit tests for each comparator.

## Verdict
**VERDICT: OBSERVE**

The story delivers a solid, functional trade simulation engine that serves the system's core objectives. The three canonical Arrow artifacts are correctly structured, cost attribution is realistic via `apply_cost()`, output is deterministic, and the crash-safe write pattern protects against data loss. The synthesis process caught and fixed real bugs (embargo exit checks, crossover detection, apply_cost migration, schema sync, breakeven classification).

The signal evaluation gap (AC #4) is real but caused by upstream dependency absence, not implementation error — architecture D14 Phase 1 explicitly defers shared evaluation. The silent filter degradation and param-batch dead code are genuine observations worth tracking but do not undermine V1's single-strategy-family scope.

I disagree with Codex's REVISIT verdict. The unresolved items are either (a) blocked on upstream work that doesn't exist yet, (b) explicitly deferred to Epic 5, or (c) acceptable for V1 scope. The core trade simulation engine — the load-bearing deliverable of this story — is aligned with system objectives. OBSERVE is appropriate: the story works, the observations are noted, and future stories have clear guidance on what to address.
