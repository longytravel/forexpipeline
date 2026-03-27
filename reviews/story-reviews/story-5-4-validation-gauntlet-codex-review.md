# Story 5-4-validation-gauntlet: Story 5.4: Validation Gauntlet — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-22
**Type:** Holistic System Alignment Review

---

**1. System Alignment**
**Assessment:** CONCERN

**Evidence:** The story clearly advances reproducibility, artifact persistence, and some fidelity through deterministic seeding, per-stage artifacts, purge/embargo, and stressed-cost testing in [story 5.4#L42](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L42), [story 5.4#L70](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L70), and [story 5.4#L306](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L306). It is weaker on operator confidence, because V1 centers on evidence quality and non-coder review in [prd.md#L82](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L82), [prd.md#L117](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L117), and [prd.md#L517](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L517), while this story mostly emits raw summaries and adds performance-based short-circuiting in [story 5.4#L49](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L49) and [story 5.4#L356](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L356).

**Observations:** The gauntlet concept fits V1, but the default “skip remaining stages if OOS Sharpe < 0” logic is working against FR41 and against artifact completeness. It optimizes compute cost, not operator confidence.

**Recommendation:** Keep the gauntlet, but remove profitability-like short-circuiting as a default hard stop. For V1, prefer full evidence generation unless there is a validity failure, resource emergency, or explicit operator opt-out.

**2. PRD Challenge**
**Assessment:** CRITICAL

**Evidence:** FR29-FR33 are the right problem set in [prd.md#L504](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L504), but the story appears to misplace two key statistics. DSR is defined as a multiple-testing correction in architecture D11 in [architecture.md#L885](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L885), yet the story computes it after gauntlet progress in [story 5.4#L56](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L56) and [story 5.4#L202](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L202). PBO is treated as a per-candidate CPCV output in [story 5.4#L144](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L144), but classical PBO is a selection-level overfitting measure, not a single-candidate score.

**Observations:** This story is solving real problems with CPCV, perturbation, and stress analysis. But it is likely solving imagined certainty with per-candidate PBO and late-stage DSR. Also, the story’s “walk-forward” does not clearly say whether parameters are re-selected on each train window; as written, it looks like segmented OOS replay of a fixed candidate, which is not full walk-forward optimization.

**Recommendation:** Re-decompose the PRD contract. Treat DSR and PBO as candidate-universe or selection-stage statistics sourced from the optimization manifest. Explicitly define whether FR29 means true re-optimization per window or just rolling OOS segmentation. Also reconcile FR33’s “trending/ranging/volatile/quiet” language with the story’s volatility-by-session design.

**3. Architecture Challenge**
**Assessment:** CRITICAL

**Evidence:** Architecture says validation is Rust-owned batch compute in [architecture.md#L314](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L314), [architecture.md#L412](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L412), [architecture.md#L1805](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L1805), and [architecture.md#L1958](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L1958). The story instead builds `src/python/validation/*`, adds Python orchestration, and explicitly says “No new Rust crate changes” in [story 5.4#L300](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L300). It also recalculates stressed PnL in Python in [story 5.4#L173](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L173), which cuts across the shared cost/simulation ownership in [architecture.md#L991](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L991) and [architecture.md#L1027](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L1027).

**Observations:** The story is not implementing the documented architecture; it is proposing a different one. Worse, it does so implicitly. That creates technical debt before code exists.

**Recommendation:** Pick one architecture and make it explicit. For V1, the simpler model is probably Python gauntlet orchestration plus Rust evaluation kernels. If that is the intended direction, update the architecture now. If not, rewrite the story around `crates/validator` and Rust-owned within-stage checkpointing.

**4. Story Design**
**Assessment:** CRITICAL

**Evidence:** The acceptance criteria in [epics.md#L1243](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md#L1243) are reasonable at a capability level, but the implementation story explodes into 13 tasks, multiple new modules, pipeline-state changes, executor integration, schemas, manifests, and full E2E coverage in [story 5.4#L75](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L75). It also mixes “research-determined” acceptance criteria with hardcoded defaults in [story 5.4#L83](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L83).

**Observations:** This is not one implementation story. It is at least three: gauntlet scaffolding, deterministic statistical methods, and pipeline integration. The anti-patterns are decent, but they miss the biggest failure modes: wrong DSR/PBO scope, false walk-forward semantics, and FR41 conflict from short-circuit gating.

**Recommendation:** Split the story. At minimum: 1. validation scaffold and artifact contract, 2. core validators, 3. pipeline/executor integration. Also make every research-derived constant trace to a named brief version or move it out of the acceptance criteria.

**5. Downstream Impact**
**Assessment:** CONCERN

**Evidence:** Story 5.5 assumes 5.4 emits clean inputs for composite scoring, evidence packs, and cited narratives in [epics.md#L1287](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md#L1287). Architecture D11 also expects the analysis layer to assemble operator-facing evidence in [architecture.md#L804](C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L804). But 5.4 currently lacks an explicit downstream contract for optimization lineage, total trial count, candidate rank, research-version provenance, and metric IDs.

**Observations:** If 5.4 emits only per-candidate stage outputs plus markdown, 5.5 will either recompute selection-level stats or inherit statistically wrong ones. That is rewrite bait. The DSR/PBO placement problem will leak forward immediately.

**Recommendation:** Add a `validation_bundle` contract now. It should include candidate lineage back to optimization, total evaluated-trial count, gate rationale, metric IDs, chart-ready data refs, and research/config hashes so Story 5.5 can remain a pure aggregation/presentation layer.

## Overall Verdict
VERDICT: RETHINK

## Recommended Changes
1. Move DSR out of per-candidate gauntlet logic and make it consume the full optimization trial universe from Story 5.3 artifacts.
2. Remove per-candidate PBO as currently defined, or rename it to a stability metric unless the story uses a true candidate cohort required for classical PBO.
3. Clarify FR29 semantics: either implement true walk-forward re-selection on each train window or stop calling the fixed-candidate replay “walk-forward.”
4. Resolve runtime ownership explicitly: either rewrite the story to target `crates/validator` or update architecture to endorse Python-orchestrated validation.
5. Remove negative-OOS-performance short-circuiting as a default gate in V1; preserve evidence completeness unless the failure is about validity, not attractiveness.
6. Align regime analysis wording with the PRD by explicitly declaring the V1 regime model, instead of silently replacing it with volatility x session.
7. Split the story into smaller units so checkpointing, executor registration, and five different validation methods do not all land in one spec.
8. Add a downstream `validation_bundle` manifest with optimization run ID, candidate rank, total trials, source cohort, gate results, metric IDs, and chart data references.
9. Centralize anomaly threshold ownership so 5.4 emits deterministic raw metrics and D11/5.5 own surfaced flags and narratives.
10. Rework stressed-cost Monte Carlo so it reuses the same cost/trade logic as the backtester, not a Python-side approximation.
