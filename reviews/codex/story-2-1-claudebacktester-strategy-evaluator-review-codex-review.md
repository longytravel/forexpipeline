# Story 2-1-claudebacktester-strategy-evaluator-review: Story 2.1: ClaudeBackTester Strategy Evaluator Review — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-15
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

**High Findings**
- The research artifact misdocuments the persisted strategy/checkpoint schema, which makes AC4 only partial. Its JSON examples use nonexistent external fields like `partial_enabled`, `partial_pct`, `hours_start`, `hours_end`, and `days_bitmask` in [strategy-evaluator-baseline-review.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/research/strategy-evaluator-baseline-review.md:638) and [strategy-evaluator-baseline-review.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/research/strategy-evaluator-baseline-review.md:810). The real checkpoints store `partial_close_enabled`, `partial_close_pct`, `partial_close_trigger_pips`, `allowed_hours_start`, `allowed_hours_end`, and `allowed_days` in [checkpoint.json](/c/Users/ROG/Projects/ClaudeBackTester/results/ema_eur_usd_h1/checkpoint.json:33) and [checkpoint.json](/c/Users/ROG/Projects/ClaudeBackTester/results/ema_eur_usd_h1/checkpoint.json:40), with day bitmask conversion only happening internally in [encoding.py](/c/Users/ROG/Projects/ClaudeBackTester/backtester/core/encoding.py:74). Downstream stories would build against the wrong schema if they follow this document.
- The signal-generation review gets entry timing wrong, which weakens AC1 and AC9. The artifact says `Signal.entry_price` is “price at signal bar close” in [strategy-evaluator-baseline-review.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/research/strategy-evaluator-baseline-review.md:176) and says backtest uses signal-bar close while live uses next-bar open in [strategy-evaluator-baseline-review.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/research/strategy-evaluator-baseline-review.md:855). But the concrete strategies mostly compute entry at next-bar open already, with close only as last-bar fallback, as shown in [ema_crossover.py](/c/Users/ROG/Projects/ClaudeBackTester/backtester/strategies/ema_crossover.py:158), [rsi_mean_reversion.py](/c/Users/ROG/Projects/ClaudeBackTester/backtester/strategies/rsi_mean_reversion.py:135), and [bollinger_reversion.py](/c/Users/ROG/Projects/ClaudeBackTester/backtester/strategies/bollinger_reversion.py:140).
- The artifact recommends “precompute-once, filter-many” as a D10 pattern without carrying forward the causality constraint that makes that optimization safe. It promotes the pattern in [strategy-evaluator-baseline-review.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/research/strategy-evaluator-baseline-review.md:713), but the baseline explicitly models causal vs. train-fit strategies in [base.py](/c/Users/ROG/Projects/ClaudeBackTester/backtester/strategies/base.py:87) and rejects `REQUIRES_TRAIN_FIT` strategies in the shared engine in [engine.py](/c/Users/ROG/Projects/ClaudeBackTester/backtester/core/engine.py:212). That contract is also enforced by [test_causality.py](/c/Users/ROG/Projects/ClaudeBackTester/tests/test_causality.py:1). Because the doc omits this, AC5, AC6, and AC9 are only partially met, and the proposed architecture updates miss a needed D10/D14 guardrail.

**Medium Findings**
- The authoring-workflow section documents only the legacy `generate_signals()` / `filter_signals()` / `calc_sl_tp()` path in [strategy-evaluator-baseline-review.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/research/strategy-evaluator-baseline-review.md:544), but current authoring also relies on `generate_signals_vectorized()`, custom `optimization_stages()`, `management_modules()`, and sometimes expanded signal-slot mappings. That surface is documented in [CLAUDE.md](/c/Users/ROG/Projects/ClaudeBackTester/CLAUDE.md:61), implemented in [base.py](/c/Users/ROG/Projects/ClaudeBackTester/backtester/strategies/base.py:295) and [base.py](/c/Users/ROG/Projects/ClaudeBackTester/backtester/strategies/base.py:357), and used by real strategies such as [ema_crossover.py](/c/Users/ROG/Projects/ClaudeBackTester/backtester/strategies/ema_crossover.py:76) and [verification_test.py](/c/Users/ROG/Projects/ClaudeBackTester/backtester/strategies/verification_test.py:252). That leaves AC3 only partially satisfied.

**Acceptance Criteria Scorecard**

| AC | Status | Notes |
|---|---|---|
| 1 | Partially Met | Verdict table exists, but signal-generation behavior is misdescribed. |
| 2 | Fully Met | Indicator catalogue is comprehensive and structured enough for downstream registry work. |
| 3 | Partially Met | Workflow write-up omits the current vectorized authoring path and related hooks. |
| 4 | Partially Met | Representation/storage section uses incorrect persisted field names and mixes in internal encoding concepts. |
| 5 | Partially Met | Gap analysis exists, but it misses the causality contract as a baseline capability/constraint. |
| 6 | Partially Met | It flags the precompute pattern, but not the correctness guard required to adopt it safely. |
| 7 | Fully Met | Proposed Architecture Updates section is present and concrete. |
| 8 | Fully Met | Repo path, branch, and commit hash are recorded. |
| 9 | Partially Met | Fidelity appendix exists, but timing semantics are wrong and the non-causal/precompute risk is omitted. |
| 10 | Fully Met | Cost logic location, approach, and D13 compatibility are documented. |

**Test Coverage Gaps**
- There is no story-level check that the research artifact’s checkpoint/schema examples match the real persisted checkpoints. Existing baseline tests already use the true field names in [test_engine.py](/c/Users/ROG/Projects/ClaudeBackTester/tests/test_engine.py:173) and [test_walk_forward.py](/c/Users/ROG/Projects/ClaudeBackTester/tests/test_walk_forward.py:189), but nothing validates the document against them.
- There is no regression check that the research artifact stays aligned with the actual authoring API, especially `generate_signals_vectorized()`, `management_modules()`, and `optimization_stages()`.
- There is no acceptance test tying the architecture recommendations back to the causality contract enforced by [test_causality.py](/c/Users/ROG/Projects/ClaudeBackTester/tests/test_causality.py:1).

4 of 10 criteria are fully met, 6 are partially met, and 0 are not met.

`src/python/data_pipeline/pipeline_proof.py` did not affect this story’s ACs; Story 2.1 is a research-only deliverable, so the review outcome is driven by the research artifact and the ClaudeBackTester baseline evidence.
