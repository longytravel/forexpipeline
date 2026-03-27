# Story Synthesis: 5-4-validation-gauntlet

## Codex Observations & Decisions

### 1. System Alignment — Short-Circuit Conflicts with FR41
**Codex said:** The default "skip remaining stages if OOS Sharpe < 0" logic works against FR41 (allow any strategy to progress without blocking on profitability) and against artifact completeness. It optimizes compute cost, not operator confidence.
**Decision:** AGREE
**Reasoning:** FR41 explicitly states the system must allow any strategy (profitable or not) to progress through the full pipeline. Short-circuiting on negative OOS Sharpe is a profitability gate by another name. V1 is gated on reproducibility and evidence quality, not profitability. A candidate with negative Sharpe still produces valuable evidence proving the pipeline works correctly.
**Action:** Rewrote AC #8 to limit short-circuit to validity failures only (PBO hard gate, DSR hard gate). Updated Task 9 short-circuit logic, `_should_short_circuit` docstring, config key renamed from `short_circuit_enabled` to `short_circuit_on_validity_failure`, and Short-Circuit Logic section rewritten with FR41 rationale. Added anti-pattern #1 explicitly prohibiting profitability gating.

### 2. PRD Challenge — DSR Placement / Total Trial Count
**Codex said:** DSR is defined as a multiple-testing correction and should consume the full optimization trial universe from Story 5.3, not just promoted candidates. Per-candidate PBO is misplaced. Walk-forward semantics are ambiguous.
**Decision:** PARTIALLY AGREE
**Reasoning:**
- **DSR trial count** — AGREE. DSR must correct for ALL candidates explored during optimization (potentially hundreds/thousands), not just the 5-10 promoted ones. Computing DSR over only promoted candidates dramatically understates the correction. Updated AC #10 and Task 8 to source `num_trials` from Story 5.3's optimization manifest.
- **Per-candidate PBO** — DISAGREE. Codex claims PBO is a selection-level metric, not per-candidate. This conflates two uses. Classical PBO from CPCV IS computed per-candidate: it measures whether that specific candidate's IS→OOS performance degrades systematically across different data partitions (Bailey et al.'s original formulation). The selection-level concern is already handled by DSR. The story's per-candidate PBO from CPCV is statistically valid and serves a distinct purpose from DSR.
- **Walk-forward semantics** — AGREE. The story's walk-forward is fixed-candidate rolling OOS evaluation, NOT walk-forward re-optimization. This distinction matters for operator understanding. Added explicit clarification to AC #1 and anti-pattern #3.
**Action:** Updated AC #10 to specify "all candidates explored during optimization." Updated Task 8 with `num_trials` sourcing requirement. Added walk-forward clarification to AC #1. Added anti-patterns #2 and #3.

### 3. Architecture Challenge — Rust vs Python Ownership
**Codex said:** Architecture maps FR29-FR33 to `crates/validator/` as a Rust binary, but the story builds Python orchestration and says "No new Rust crate changes." This creates implicit technical debt.
**Decision:** PARTIALLY AGREE
**Reasoning:** Codex correctly identifies the discrepancy in the architecture's Requirements-to-Structure mapping. However, the story's actual approach (Python gauntlet orchestration + Rust evaluation kernels via BatchDispatcher) IS consistent with D1's "Python orchestrates, Rust computes" topology. The walk-forward, CPCV, and perturbation stages DO dispatch to Rust for all compute-heavy evaluation. Monte Carlo/regime/DSR are correctly Python-only. Creating a separate `forex_validator` binary would be over-engineering — the existing evaluator binary already handles windowed evaluation. The architecture mapping table needs updating, not the story.
**Action:** Added Architecture Reconciliation Note to Dev Notes section explaining the design rationale and flagging that the architecture mapping should be updated to reflect validation reusing the existing evaluator binary.

### 4. Story Design — Too Large, Should Split
**Codex said:** This is at least three stories (gauntlet scaffolding, deterministic statistical methods, pipeline integration). 13 tasks mixing research-determined ACs with hardcoded defaults.
**Decision:** DISAGREE
**Reasoning:** This is a V1 project for a single operator. The 13 tasks are already well-decomposed with clear module boundaries (each validator is a single Python file with 2-3 functions). Splitting would create unnecessary coordination overhead: the gauntlet orchestrator can't be tested without at least one validator, and the pipeline integration is a single executor class. The task count reflects implementation scope, not design complexity. Each task is independently implementable in order. Research-determined constants trace to Brief 5C and are configured in TOML (not hardcoded in code).
**Action:** None. Story size is appropriate for its scope.

### 5. Downstream Impact — Missing Validation Bundle Contract
**Codex said:** Story 5.4 lacks an explicit downstream contract for what Story 5.5 needs: optimization lineage, total trial count, candidate rank, metric IDs, chart-ready data refs, research/config hashes.
**Decision:** AGREE
**Reasoning:** Story 5.5 (Confidence Scoring & Evidence Packs) is a pure aggregation/presentation layer. If it has to recompute selection-level statistics or dig for lineage information, that's a design failure in 5.4's output contract. Making this explicit now prevents rewrite during 5.5 implementation.
**Action:** Added "Downstream Contract (Story 5.5 Interface)" section to Dev Notes with a table specifying all fields the gauntlet manifest must include. Updated Task 10's `write_gauntlet_manifest` function signature and description to include all contract fields.

### 6. Regime Analysis — FR33 Wording Mismatch
**Codex said:** FR33 says "trending, ranging, volatile, quiet" but the story silently replaces this with volatility × session cross-tabulation.
**Decision:** AGREE
**Reasoning:** The story should explicitly acknowledge the deviation rather than silently substituting. Volatility × session is a valid V1 proxy (captures the most actionable regime dimensions for forex), but full trend/range classification would require HMM or similar — inappropriate complexity for V1 MVP.
**Action:** Added V1 scope note to AC #6 explaining the regime model choice and deferring full trend/range classification to Growth phase.

### 7. Stressed-Cost Monte Carlo — Should Reuse Rust Cost Logic
**Codex said:** Stressed-cost Monte Carlo should reuse the same cost/trade logic as the backtester, not a Python-side approximation.
**Decision:** DISAGREE
**Reasoning:** The stress test answers a specific question: "given these already-executed trades, would they still be profitable if costs were higher?" This is correctly answered by recalculating PnL from existing trade entry/exit prices with inflated costs. Re-running the full strategy through Rust with higher costs would produce *different* trades (because different costs could trigger different exits, different position sizing), which changes the question being asked. The Python approach is both simpler and more analytically correct for what Monte Carlo stress testing actually measures. Added anti-pattern #4 to make this design choice explicit.
**Action:** Added anti-pattern #4 explaining why Python-side cost stress is correct.

### 8. Anomaly Threshold Ownership
**Codex said:** Centralize anomaly threshold ownership so 5.4 emits deterministic raw metrics and D11/5.5 own surfaced flags and narratives.
**Decision:** AGREE
**Reasoning:** This is already the story's intent (see D11 dev note: "Evidence pack consumption is Story 5.5's responsibility — this story produces the raw validation artifacts"), but it should be reinforced as an explicit anti-pattern to prevent scope creep during implementation.
**Action:** Added anti-pattern #5 clarifying that validators emit raw metrics only; 5.5/D11 own interpretation.

### 9. Split PBO and DSR Scope Clarification
**Codex said:** Re-decompose the PRD contract — treat DSR and PBO as candidate-universe or selection-stage statistics.
**Decision:** PARTIALLY AGREE (via actions in #2 above)
**Reasoning:** DSR IS a selection-level statistic and should use the full trial universe — agreed and fixed. PBO from CPCV IS a per-candidate validity test — disagreed with reclassification. The decomposition is now explicit in the story.
**Action:** Covered by changes in observation #2.

### 10. Story Should Split (reiterated recommendation)
**Codex said:** Split into: 1. validation scaffold and artifact contract, 2. core validators, 3. pipeline/executor integration.
**Decision:** DISAGREE (same reasoning as #4)
**Reasoning:** The proposed split would create three stories where each depends tightly on the others and none is independently deployable. The current story IS the scaffold + validators + integration — and the tasks are already sequenced for incremental development. A single operator implementing this will benefit more from having the full context in one document.
**Action:** None.

## Changes Applied

1. **AC #1:** Added clarification that walk-forward is fixed-candidate rolling OOS evaluation, not re-optimization
2. **AC #6:** Added V1 scope note about regime model choice (volatility × session vs trending/ranging) with Growth phase deferral
3. **AC #8:** Rewritten to limit short-circuit to validity failures only (FR41 compliance)
4. **AC #10:** Updated to specify total optimization trial count from Story 5.3 manifest
5. **Task 8 (DSR):** Added requirement that `num_trials` must come from optimization manifest
6. **Task 9 (Gauntlet):** Updated short-circuit rules — removed OOS Sharpe < 0 gate, updated `_should_short_circuit` docstring
7. **Task 10 (Results):** Updated `write_gauntlet_manifest` to include downstream contract fields
8. **Config schema:** Renamed `short_circuit_enabled` to `short_circuit_on_validity_failure` with FR41 comment
9. **Dev Notes — Architecture Reconciliation:** New section explaining Python orchestration + Rust evaluation design and flagging architecture mapping update needed
10. **Dev Notes — Downstream Contract:** New section with explicit table of fields 5.5 requires from the gauntlet manifest
11. **Dev Notes — Short-Circuit Logic:** Rewritten with FR41 rationale and 5-point explanation
12. **Dev Notes — Anti-Patterns:** New section with 5 anti-patterns (profitability gating, DSR subset, WF terminology, Python stress test design, threshold ownership)

## Deferred Items

- Architecture Requirements-to-Structure mapping should be updated to reflect that validation reuses the existing evaluator binary (not `crates/validator/` as a separate binary) — this is an architecture document change, not a story change
- Full trend/range regime classification (HMM-based) deferred to Growth phase
- Advanced candidate-universe PBO (across all optimization candidates, not per-candidate CPCV) could be explored in Growth phase as an additional selection-level overfitting metric alongside DSR

## Verdict
VERDICT: IMPROVED
