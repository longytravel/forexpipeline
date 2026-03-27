# Story Synthesis: 3-5-rust-backtester-crate-trade-simulation-engine

**Synthesizer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-17
**Story:** Story 3.5: Rust Backtester Crate — Trade Simulation Engine
**Codex Reviewer:** GPT-5.4 (high effort, read-only sandbox)

---

## Codex Observations & Decisions

### 1. Story Boundary Too Broad — Checkpoint/Progress Mixed with Simulation
**Codex said:** Story mixes core simulation with checkpointing, progress files, metadata writing, CLI/runtime concerns. Recommends moving checkpoint/progress to 3.3/3.4/3.6.
**Decision:** DISAGREE
**Reasoning:** The backtester is a standalone binary (D1 subprocess isolation). Only the Rust process knows its internal state — checkpoint writing, progress reporting, and graceful cancellation MUST live in the binary. Python cannot checkpoint Rust state. These are unavoidable runtime hooks, not misplaced orchestration. Moving them to other stories would create an unimplementable gap. The architecture tree explicitly shows these modules in the backtester crate.
**Action:** None — story boundary is correct. Tasks 9 and 10 stay.

### 2. PRD Challenge — Sharpe Annualization, return_pct, max_drawdown_amount
**Codex said:** Sharpe with sqrt(252) on variable-duration trade returns is misleading for M1 backtesting. `return_pct` has no defined capital base. AC #7 says "max drawdown amount" but metrics struct only carries percentage.
**Decision:** AGREE (all three sub-points)
**Reasoning:** (a) sqrt(252) annualization assumes daily sampling — trade returns have variable durations, so annualizing is actively misleading. Unannualized Sharpe is honest; downstream 3.7 can annualize with context. (b) `return_pct` implies a capital base the system doesn't define — removed to prevent misleading metrics. (c) AC #7 explicitly says "amount and duration" but the struct lacked `max_drawdown_amount` — added.
**Action:**
- Sharpe changed to unannualized with documentation of why
- `return_pct` removed from metrics struct and Arrow schema
- `max_drawdown_amount: f64` added to metrics struct
- Max drawdown computation updated to produce both absolute and percentage values

### 3. Architecture Challenge — Exit Logic Ownership Duplication
**Codex said:** Architecture has `strategy_engine/src/exits.rs` with stop loss, take profit, trailing stop, chandelier exit. Story also implements these in `position.rs`. Direct duplication risk.
**Decision:** PARTIALLY AGREE
**Reasoning:** Codex correctly identified the naming collision. However, there's a legitimate separation: `strategy_engine::exits` defines exit **rule specifications** (chandelier formula, trailing stop parameters) as pure computation. The backtester's `position.rs` executes **price-level triggers** (did the bar's high/low hit the stop?). This is the standard separation between rule definition and rule execution. The `Evaluator::evaluate_bar()` returns exit signals; `position.rs` checks mechanical price triggers. The confusion was in the story's wording, not in actual duplication.
**Action:**
- `check_exit_conditions` docs rewritten to clarify it handles price-level triggers, NOT rule logic
- New "Exit Logic Ownership Boundary" dev note added explaining the D14 separation
- Architecture reference chain made explicit

### 4. Story Design — AC #2 vs Loop Order, Fill Timing Ambiguity
**Codex said:** CRITICAL. AC #2 says "entry → exit → management → record" but loop opens positions before exit checks. Fill timing ambiguous (same-bar vs next-bar-open "if configured").
**Decision:** PARTIALLY AGREE
**Reasoning:** (a) The original loop order was actually defensible — evaluate signal, then act on entry, then check exits on existing positions. But the order was confusing: it checked exits AFTER opening new positions, meaning a new position could exit same-bar. The revised loop order is clearer: check exits on existing positions FIRST, then evaluate new signals. This prevents same-bar open+close confusion. (b) Fill timing ambiguity was a real gap — "if configured" introduces undefined V1 behavior. Fixed to single model.
**Action:**
- Main loop reordered: exit checks → trailing stop update → quarantine gate → signal evaluation → entry
- Fill timing locked to same-bar fills for V1 with explicit dev note
- "If configured" language removed

### 5. Downstream Impact — Output Contract Too Thin for Forensics
**Codex said:** Trade records lack raw prices, spread/slippage applied, separate entry/exit sessions. Downstream 3.7 and PRD reconciliation need cost attribution without re-simulating.
**Decision:** AGREE
**Reasoning:** PRD technical success requires "reconciliation attribution by spread, slippage, fill timing." If we only store cost-adjusted prices, downstream analysis cannot decompose cost impact without re-running the backtest. Adding raw prices and cost breakdown is ~6 extra Float64 columns — trivial cost, prevents a rewrite. Separate entry/exit sessions are needed because trades can span session boundaries (enter London, exit New York).
**Action:**
- TradeRecord expanded: `entry_price_raw`, `exit_price_raw`, `entry_spread`, `entry_slippage`, `exit_spread`, `exit_slippage`, `entry_session`, `exit_session`, `signal_id`
- Arrow trade log schema updated to match
- `return_pct` removed (no capital base)
- New "Downstream Contract" dev note section added listing exact outputs 3.6/3.7 depend on

### 6. Determinism Contract Inconsistency
**Codex said:** AC #8 says bit-identical but tests warn Arrow may vary, and run_metadata.json has timestamp.
**Decision:** AGREE
**Reasoning:** Internal contradiction — AC says bit-identical, test says don't rely on file hash. The right contract is canonical-value equality (data content), not byte-identity (serialization format). run_metadata.json with timestamps is obviously non-deterministic.
**Action:**
- AC #8 rewritten: "canonical data values are identical across runs. Metadata files excluded from determinism contract."
- New "Determinism Scope" dev note section defining exactly what is and isn't deterministic
- run_metadata.json write task annotated as excluded from determinism
- Integration test updated to specify field-by-field comparison with explicit metadata exclusion

### 7. Quarantine Policy for Open Positions
**Codex said:** No explicit policy for open positions during quarantined bars. "Skip the bar" could suppress exits and distort drawdown.
**Decision:** AGREE
**Reasoning:** This is a real gap with safety implications. If a position is open and quarantined bars begin, suppressing exit checks means the position has no protection. Stop losses must continue firing during quarantine — the data quality concern affects signal generation, not position risk management.
**Action:**
- AC #9 rewritten: "no new entry signals during quarantine; exit checks continue for open positions"
- Main loop reordered so exit checks run BEFORE quarantine gate (exit checks on all bars, including quarantined)
- Quarantine gate only blocks new signal evaluation and entries

### 8. Fix Metric Contract — max_drawdown_amount
**Codex said:** AC says "amount and duration" but metrics struct only has percentage and duration.
**Decision:** AGREE (covered in #2)
**Action:** `max_drawdown_amount: f64` added to metrics struct.

### 9. Replace Sharpe Calculation
**Codex said:** Replace sqrt(252) with documented method aligned to system's timeframe.
**Decision:** AGREE (covered in #2)
**Action:** Unannualized Sharpe = mean(trade_pnl) / std(trade_pnl), with dev note explaining why.

### 10. Replace Heuristic Memory Sizing
**Codex said:** "1 trade per 100 bars" is not defensible. Use bounded streaming + startup preflight.
**Decision:** PARTIALLY AGREE
**Reasoning:** The heuristic is just initial sizing, not a hard capacity plan. The real safeguard is streaming flush to disk, which the story already requires (AC #10). The heuristic only determines initial buffer allocation. Made this explicit.
**Action:** Task 3 pre_allocate_pools comment clarified: heuristic is initial sizing, grows within budget if needed, streaming flush is the real safeguard.

### 11. Equity Curve — Realized-Only vs Mark-to-Market
**Codex said:** Realized-only equity understates drawdown. Consider mark-to-market.
**Decision:** AGREE
**Reasoning:** A realized-only curve shows flat lines during trades, masking intra-trade drawdowns. A position down 500 pips wouldn't show any drawdown until closed. This produces misleading evidence packs in Story 3.7. Mark-to-market is a small addition (equity = closed_pnl + unrealized_pnl) and produces dramatically more accurate drawdown data.
**Action:**
- AC #6 changed to mark-to-market
- Equity curve point recording changed from closed-trade P&L to mark-to-market
- `unrealized_pnl` field added to equity curve Arrow schema
- Max drawdown computation updated to note it captures unrealized losses
- New "Equity Curve Definition" dev note explaining the choice

### 12. Add Downstream Contract Section
**Codex said:** State exactly what 3.6 and 3.7 may rely on from this story's outputs.
**Decision:** AGREE
**Reasoning:** Prevents contract drift between stories. Downstream stories need to know exact file paths, schemas, and what's guaranteed.
**Action:** New "Downstream Contract" section added to dev notes listing exact output files, schema contract references, and cost attribution guarantee.

## Changes Applied

### Acceptance Criteria (5 changes)
1. AC #5: Expanded trade record fields — added raw prices, cost breakdown, entry/exit sessions, signal ID
2. AC #6: Changed equity curve from realized-only to mark-to-market
3. AC #8: Rewritten determinism contract — canonical-value equality, metadata excluded
4. AC #9: Added open-position quarantine policy — exit checks continue, only entries suppressed

### Tasks (12 changes)
5. Task 3: Memory heuristic clarified as initial sizing with streaming as real safeguard
6. Task 4: `check_exit_conditions` docs rewritten — price-level triggers only, exit rules from strategy_engine
7. Task 5: TradeRecord expanded with 9 new fields for cost attribution and session tracking
8. Task 5: Fill timing locked to same-bar V1 model, "if configured" removed
9. Task 6: Main loop reordered — exit checks before quarantine gate, mark-to-market equity, step numbering fixed
10. Task 7: Metrics struct — removed `return_pct`, added `max_drawdown_amount`, Sharpe unannualized
11. Task 7: Sharpe computation changed to unannualized with rationale
12. Task 7: Max drawdown now produces both absolute amount and percentage
13. Task 8: Trade log Arrow schema expanded to match new TradeRecord
14. Task 8: Equity curve schema gains `unrealized_pnl` column
15. Task 8: run_metadata.json annotated as excluded from determinism
16. Task 11: Deterministic output test clarified — field-by-field comparison, exclude metadata

### Dev Notes (5 additions)
17. New section: "Exit Logic Ownership Boundary" — clarifies D14 strategy_engine vs position.rs split
18. New section: "V1 Fill Timing Model" — documents same-bar fill decision
19. New section: "Equity Curve Definition" — documents mark-to-market choice
20. New section: "Determinism Scope" — defines exactly what is/isn't deterministic
21. New section: "Downstream Contract" — lists exact outputs 3.6/3.7 depend on

## Deferred Items
- **Mark-to-market vs dual equity curves:** Codex suggested emitting both realized-only and mark-to-market. For V1, mark-to-market alone is sufficient. The `unrealized_pnl` field allows downstream to reconstruct realized-only if needed. Revisit if evidence packs need both views.
- **Story boundary simplification:** Codex wanted checkpoint/progress moved to other stories. Deferred because these are unavoidable binary-internal operations. May revisit if story proves too large during implementation — could split into 3.5a (simulation) and 3.5b (runtime hooks).
- **Configurable fill timing:** Codex flagged same-bar vs next-bar ambiguity. V1 locked to same-bar. Future epic may add configurability if live-parity requires it.

## Verdict
VERDICT: IMPROVED
