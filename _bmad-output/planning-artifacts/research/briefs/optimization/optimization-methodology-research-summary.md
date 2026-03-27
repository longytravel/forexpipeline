# Optimization Methodology Research Summary

**Date:** 2026-03-18
**Status:** Research Complete — Algorithm Selection Pending
**Feeds into:** Epic 5 (Optimization & Validation Gauntlet) story creation
**Source artifacts:** See bottom of document

---

## Key Findings

### 1. CV-Inside-Objective Is the Primary Defense Against Overfitting

**Current problem:** The optimizer maximizes `quality(params, single_IS_block)`. Any optimizer that's good at this WILL overfit. The March 2026 testing proved this — the broken CMA-ES (effectively random search) produced the best OOS results because it couldn't overfit effectively.

**Solution:** Replace the single-block objective with a cross-validated objective:
```
objective = mean(quality(params, fold_k)) - λ·std(quality(params, fold_k))
```

**Theoretical backing:**
- Duchi & Namkoong (2019, JMLR): DRO with χ²-divergence is asymptotically equivalent to mean-variance regularization. This IS the provably optimal objective for distribution shift robustness.
- GT-Score (Sheppert, 2026, JRFM): 98% improvement in generalization ratio vs optimizing net profit.
- Holland (2024, AISTATS): mean-λ·std outperformed both CVaR and χ²-DRO on 3 of 4 benchmarks.

**Recommended aggregation:** `mean(fold_scores) - 1.0·std(fold_scores)` with hard floor: `min(fold_scores) > threshold`. Start with λ=1.0, tune in {0.5, 1.0, 1.5, 2.0}.

**Computational cost:** NOT 5x. With early stopping across folds and shared indicator computation: 1.3-2.5x baseline cost. At 750 evals/sec baseline → 350-500 effective evals/sec with 5-fold CV.

### 2. Staged (5-Group) Parameter Optimization Is Architecturally Flawed

**Current design (from ClaudeBackTester):** Signal → Time → Risk → Management → Refinement (5 stages, parameters locked after each).

**Problem:** This is Block Coordinate Descent. It cannot discover cross-group parameter interactions. SL size affects whether trailing matters; TP size affects whether partial close matters. These interactions are invisible to the staged approach.

**Evidence:**
- No major quant shop uses 5-stage parameter locking for rule-based strategies
- The GA result (IS quality 35.72, OOS Sharpe -5.13, population collapsed) shows staged optimization finding deeper local optima that don't generalize
- Signal + Time separation is defensible (genuinely separable questions: "what pattern?" vs "when?")
- Risk + Management separation is NOT defensible (deeply coupled parameters)

**Architecture implication:** The architecture must NOT prescribe a staging structure. The optimizer manages its own internal state — whether it uses 2 phases, 5 stages, or full joint optimization is a methodology decision behind a pluggable interface.

### 3. Conditional Parameters Reduce Effective Search Space

The naive combinatorial explosion (20^12 ≈ 4×10^15 for 12 risk/trade params) is misleading. Many parameters are conditional:

- trailing_mode = none → trailing_activation and trailing_step are irrelevant
- breakeven_enabled = false → breakeven_offset is irrelevant
- partial_close_enabled = false → partial_close_pct is irrelevant

**Effective space with conditionals: ~30-70M combinations**, not 4×10^15. This is searchable by population-based optimizers (CMA-ES, DE) with 200-400K trials.

The optimizer MUST understand conditional parameter structure. Wasting trials on irrelevant parameter combinations is a significant efficiency loss.

### 4. Fold Design for H1 Forex Data

**Recommended:** 5 blocked time-series folds with 1% embargo (~960 bars / 40 trading days) at each boundary.

Example for 96K H1 bars (2007-2026):
- Fold 1: 2007-2010
- Fold 2: 2011-2014
- Fold 3: 2015-2018
- Fold 4: 2019-2022
- Fold 5: 2023-2026

**Purging:** Remove training observations within 120 bars (5 days) of test fold boundaries.

**CPCV vs blocked CV:** Use simple blocked CV inside the optimizer (cheap). Reserve CPCV for final validation of top candidates (expensive but more statistically rigorous).

### 5. The Optimization Pipeline Is Three Complementary Tools

| Tool | Question It Answers | When Used |
|------|-------------------|-----------|
| **CV-inside-objective** | "Which parameter set generalizes best across diverse market conditions?" | During optimization (parameter search) |
| **Walk-forward optimization** | "How would periodic re-optimization have performed?" | Post-optimization validation |
| **CPCV** | "What's the probability this result is overfitted?" | Final statistical validation |

These are complementary, not competing. The strongest pipeline uses all three.

### 6. Quality Formula Differentiation

There is a theoretical advantage to using a **simpler quality formula** for the optimizer's objective than for the final validation pipeline:

- **Optimizer objective:** Simple, low-variance metric (e.g., Sharpe Ratio or Profit Factor). Provides smoother fitness landscape for the search algorithm.
- **Validation scoring:** Full composite quality formula (Sortino, R², PF, Ulcer, DD, trade ramp). Used post-hoc for candidate ranking.

This separation prevents the optimizer from "gaming" complex quality metrics with multiple local optima.

---

## Architecture Requirements (Infrastructure, Not Methodology)

These are interface requirements that Epic 3 must build, regardless of which optimization algorithm is selected:

1. **Rust evaluator accepts fold boundaries** — bar indices + embargo size as input parameters
2. **Rust evaluator returns per-fold scores** — not just aggregated scores
3. **Shared indicator computation** — compute indicators once on full dataset, slice per fold
4. **Batch evaluation interface** — accept N parameter sets, return N × K fold scores
5. **Conditional parameter support** — strategy spec defines parameter conditionals; optimizer respects them
6. **Optimizer state is opaque to pipeline state machine** — optimizer manages its own checkpoints
7. **Pluggable optimizer interface** — ask(N) → evaluate → tell(scores) pattern

---

## Pending Decisions (Epic 5 Research)

| Decision | Options | Criteria |
|----------|---------|----------|
| Optimization algorithm | CMA-ES (CMAwM), Differential Evolution, TPE, hybrid | Must be batch-native, handle mixed integer/categorical, 10-25D |
| Staging strategy | Full joint, 2-phase (signal → trade), automatic based on param count | Must discover parameter interactions; system decides, not operator |
| λ value for mean-std | {0.5, 1.0, 1.5, 2.0} | Tune on development dataset; compare OOS generalization ratio |
| Fold count | {3, 5, 7} | Trade-off: regime coverage vs data sufficiency per fold |
| Quality formula for optimizer | Sharpe vs composite vs simplified composite | Test: which produces highest WFO pass rate? |

---

## Source Artifacts

| File | Description |
|------|-------------|
| `c:\Users\ROG\Downloads\compass_artifact_wf-e81f1f5c-*.md` | CV-inside-objective: implementation plan, computational feasibility, mean-λ·std recommendation |
| `c:\Users\ROG\Downloads\cv_objective_optimization.txt` | Research brief: system context, March 2026 testing results, CMA-ES bug discovery, staged interaction question |
| `c:\Users\ROG\Downloads\Trading Strategy Optimization Research Questions.md` | Comprehensive framework: aggregation functions, institutional standards, fold design, computational efficiency, staged vs joint |
| `c:\Users\ROG\Downloads\Trading Strategy Optimization Research Questions (1).md` | Duplicate/variant of above with additional references |
| `research/briefs/3A/` | Competitive backtesting engine architecture (VectorBT, Nautilus, QuantConnect, etc.) |
| `research/briefs/3B/` | Deterministic backtesting validation methodology (DSR, PBO, tiered reproducibility) |
| `research/briefs/3C/` | Results analysis, AI narratives, operator experience design |
| `research/backtest-engine-baseline-review.md` | Story 3-1: ClaudeBackTester baseline — 18 component verdicts, 4 architectural shifts |
| `research/3-2-ipc-determinism-research.md` | Story 3-2: IPC mechanism, determinism strategy, checkpoint/resume, memory budget |
| `research/strategy-evaluator-baseline-review.md` | Story 2-1: Strategy evaluator — D14 mismatch, phased indicator migration |
