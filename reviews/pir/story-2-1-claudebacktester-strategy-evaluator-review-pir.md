# PIR: Story 2-1-claudebacktester-strategy-evaluator-review — Story 2.1: ClaudeBackTester Strategy Evaluator Review

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-15
**Type:** Post-Implementation Review (final decision)

---

## Codex Assessment Summary

Codex rated all three dimensions as ADEQUATE with an overall OBSERVE verdict. My evaluation of each observation:

### 1. Artifact is implementer-facing, not operator-facing
**Codex:** The PRD promises "review a coherent evidence pack" without code exposure, but this artifact is implementation-facing — useful to builders, not an operator-friendly evidence pack.

**DISAGREE (not applicable to this story type).** Story 2.1 is explicitly a Phase 0 research story — its consumer is downstream stories (especially 2.2, 2.8), not the operator. The PRD's operator-facing evidence packs are produced by later pipeline stages (FR11, FR48-FR51). Research artifacts are builder inputs by definition. Holding a research artifact to the operator-readability standard conflates two different audiences. The Story 1-1 data pipeline review followed the exact same pattern and was not flagged for this.

### 2. Phase 1 Python-indicator arrangement pushes against D14 fidelity goal
**Codex:** Keeping indicators in Python for Phase 1 while D14 expects a shared pure-computation Rust crate creates tension with signal fidelity.

**PARTIALLY AGREE (low severity).** The concern is valid in principle — the architecture's fidelity story depends on identical evaluation code for backtest and live. However, the research artifact's phased migration proposal is consistent with the PRD's "wrap-and-extend default" constraint and explicitly designates Python indicators as test oracles for future Rust ports. The baseline already achieves 200K+ trial throughput with Python indicators, so V1 performance is not at risk. The fidelity concern only materializes if live trading runs a different indicator path than backtesting — which is not the case in the proposed Phase 1 architecture (both use the same Python indicators). The real D14 fidelity requirement is same-code-path for backtest and live, not Rust-only. This observation correctly identifies a future engineering debt, not a current alignment problem.

### 3. Prose-heavy, could be more machine-readable
**Codex:** Highest-value outputs are the verdict table and indicator catalogue. A simpler approach would be machine-readable tables plus short memo.

**PARTIALLY AGREE (minor).** The indicator catalogue (Section 5) and verdict table (Section 3) are already structured and machine-readable. The surrounding prose in Sections 4, 6, 7, 8 provides interpretive context that downstream story authors need — for instance, the precompute-once pattern description (Section 8.3) and its causality constraint are critical for Story 2.8's evaluator design. The synthesis report demonstrates that reviewers read the prose critically enough to catch 11 factual errors across 2 review rounds, which validates its utility. A machine-readable indicator registry seed would be a nice addition but is appropriately deferred to Story 2.8 (which builds the actual registry).

### 4. Document doesn't strongly prioritize the V1 subset
**Codex:** Full baseline catalogued but V1 subset not strongly prioritized, creating risk of "baseline completeness" over "V1 proof."

**DISAGREE.** The story spec explicitly requires a full baseline catalogue (AC2: "all existing indicator implementations are catalogued") precisely because Story 2.8 needs the complete registry input. V1 scoping happens at the story level — Story 2.8 will implement only the indicators needed for the chosen strategy family. A research artifact that pre-filters to V1 would lose information needed for future epics. The gap analysis (Section 8) correctly identifies which capabilities are V1-critical vs future scope.

### 5. Forward contract is prose-only, no machine-readable schema mapping
**Codex:** Downstream contract is good for humans but weaker for implementers — missing machine-readable indicator registry seed and schema-mapping artifact.

**PARTIALLY AGREE (minor).** A TOML/JSON indicator registry seed would reduce transcription effort for Story 2.8. However, the indicator catalogue in Section 5 has well-defined structure (canonical name, parameters, computation, I/O, warm-up, dependencies) that a developer can parse directly. The format for the registry is Story 2.2's decision (JSON vs TOML vs other), so producing a machine-readable seed here would pre-commit to a format the project hasn't chosen yet. This is appropriately deferred.

---

## Objective Alignment
**Rating:** STRONG

This story serves all four system objectives:

- **Reproducibility:** Baseline pinned to specific commit (`2084beb`), branch (`master`), and repo path. Any future reader can reproduce the review against the same code state. The 12 regression tests verify the artifact's factual claims against source code.

- **Fidelity:** The story's most important contribution. It discovered that the baseline is Python-first with Rust acceleration — the opposite of D14's assumption that indicators/filters/exits are Rust modules. This finding fundamentally changes how downstream stories approach signal fidelity. The causality constraint documentation (added in synthesis round 2) preserves a critical safety invariant for the precompute optimization path. Sub-bar resolution and the 7-exit-type inventory give downstream stories accurate fidelity targets.

- **Artifact completeness:** Full 9-section research artifact with indicator catalogue (18 entries with parameter signatures, computation logic, I/O types, warm-up behavior), component verdict table (10 components), gap analysis (8 baseline capabilities + 9 D10 gaps), cost model assessment, and 4 proposed architecture updates. The synthesis report confirms 11 findings were fixed across 2 review rounds, with 12 regression tests verifying correctness.

- **Operator confidence:** Indirect at this stage. The research artifact builds confidence in the system's self-knowledge — the operator can see that the project has done its homework before writing code. The discovery of the Python/Rust structural mismatch is exactly the kind of surprise a Phase 0 research gate is designed to catch, validating the methodology.

The D14 structural mismatch discovery is the single highest-value finding. Without this research story, downstream stories would have attempted to build against a Rust-crate architecture that doesn't exist in the baseline, leading to significant rework. This alone justifies the story's existence.

---

## Simplification
**Rating:** ADEQUATE

The research artifact is appropriately scoped for what it needs to deliver:

- **Not over-engineered:** No code was written. No architecture was directly modified. The 9-section structure follows the proven Story 1-1 pattern. The proposed architecture updates are recommendations, not implementations.

- **Proportionate depth:** The indicator catalogue depth (parameter signatures, computation logic, warm-up behavior) is justified because Story 2.8 explicitly depends on it for the registry. The authoring workflow documentation (Section 6) is justified because FR9/FR10 dialogue flow must solve the pain points identified.

- **Minor simplification opportunity:** Codex correctly notes that Sections 4, 6, 7, and 8 contain overlapping prose interpretations of the same core findings. Some consolidation would reduce the artifact's length without losing information. However, the 9-section structure was specified by the story and follows the Story 1-1 pattern, so deviation would need justification.

- **No wasted work:** Every section maps to at least one AC. The appendices (representative config, fidelity assessment, cost model, naming conventions) all serve documented downstream needs.

---

## Forward Look
**Rating:** STRONG

The output contract serves downstream stories well:

- **Story 2.2 (Spec Format):** Gets baseline constraints — no declarative format exists, checkpoint JSON is the only persisted representation, Python class-based authoring has documented pain points. The artifact explicitly avoids format selection recommendations per story spec anti-pattern #10.

- **Story 2.8 (Strategy Engine Crate):** Gets the indicator catalogue with enough detail to implement the registry — 18 indicators with canonical names, parameter types, computation logic, and dependencies. Gets the component verdict table mapping baseline modules to D14's target structure.

- **Story 2.6/2.7 (Cost Model):** Gets the explicit "Build New" verdict with D13 compatibility assessment. Current cost model is constants-only — no session awareness, no variable spreads, no pair-specific commissions.

- **Story 2.3 (Optimization Plan):** Gets the ParamDef/ParamSpace mapping to D10's optimization_plan structure.

- **Architecture updates:** 4 proposed changes (D14 phased migration, D10 exit type extensions, sub-bar resolution, precompute pattern) are documented for operator review without modifying `architecture.md` directly — exactly as the story spec requires.

The causality constraint documentation is particularly valuable for forward safety. The `SignalCausality` enum and `REQUIRES_TRAIN_FIT` guard are non-obvious correctness invariants that would be easy to lose during the spec-driven redesign. Documenting them here ensures Story 2.8 carries them forward.

The phased Rust migration proposal is pragmatic. It acknowledges engineering debt (indicators remain in Python for Phase 1) while preserving the "wrap-and-extend" approach the PRD mandates. Python test oracles for future Rust parity verification is a sound testing strategy.

---

## Observations for Future Stories

1. **Research stories should include a machine-readable summary appendix.** While the prose is valuable for context, a structured appendix (e.g., TOML/JSON indicator signatures) would reduce transcription effort for consuming stories. This is not a format pre-commitment — it's an intermediate artifact that the consuming story can transform. Consider adding this as an optional deliverable in future research story templates.

2. **The D14 structural mismatch discovery validates Phase 0 research gates.** The architecture assumed Rust crates; reality is Python-first. This is exactly the class of surprise that research stories exist to catch. Future architecture decisions should include a "baseline verification status" field indicating whether the assumption has been validated against the actual codebase.

3. **Regression tests for research artifacts are a valuable innovation.** The 12 tests that verify the artifact's factual claims against source code (indicator counts, field names, computation semantics) caught real errors during the synthesis process. This pattern should be required for all research stories — it prevents factual drift as artifacts are edited during review.

4. **The synthesis process demonstrated strong error-catching.** 11 findings across 2 rounds — including wrong indicator counts (12→18), incorrect ATR computation semantics (EMA vs Wilder's), wrong checkpoint field names, and missing causality documentation — were all caught and fixed before the PIR. This validates the dual-review (BMAD + Codex) synthesis pipeline.

5. **The "precompute-once, filter-many" pattern with causality guard should be tracked as a cross-cutting architectural concern.** It's not just a Story 2.8 implementation detail — it affects how the optimizer, validator, and live daemon interact with the evaluator. Consider elevating this to an architecture decision (or a subsection of D10/D14) after operator review.

---

## Verdict

**VERDICT: ALIGNED**

Story 2.1 is the first Epic 2 story and the first research story since Story 1-1. It delivers exactly what Phase 0 research gates are designed to deliver: ground truth about the baseline before code is written.

The D14 structural mismatch discovery is the single highest-value finding in the entire review process so far. It prevents downstream stories from building against incorrect assumptions — a class of error that would have been expensive to discover later. The indicator catalogue, component verdict table, gap analysis, and proposed architecture updates give downstream stories concrete, verified inputs to build from.

The synthesis process (2 rounds, 11 accepted findings, 12 regression tests) demonstrates that the review pipeline catches real factual errors before they propagate. All prior PIR concerns about factual accuracy in research artifacts are addressed by this testing pattern.

Upgrading from Codex's OBSERVE to ALIGNED because:
- The "implementer-facing" concern is inapplicable — research artifacts serve builders, not operators
- The Phase 1 Python-indicator concern is mitigated — same code path for backtest and live preserves fidelity
- The V1 prioritization concern is addressed — full catalogue is required by AC2; V1 scoping is Story 2.8's job
- The forward contract is strong — every downstream Epic 2 story has documented inputs from this artifact
- The synthesis process caught and fixed all material errors before this review
