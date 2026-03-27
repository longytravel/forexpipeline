# Story 2-1-claudebacktester-strategy-evaluator-review: Story 2.1: ClaudeBackTester Strategy Evaluator Review — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-15
**Type:** Holistic System Alignment Review

---

**1. System Alignment**
- Assessment: `ADEQUATE`
- Evidence: [Story 2.1](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-1-claudebacktester-strategy-evaluator-review.md#L15), [PRD MVP/Phase 0](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L354), [Architecture D10](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L627), [Architecture D14](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L939)
- Observations: This story clearly supports reproducibility and fidelity by validating evaluator determinism, representable constructs, and shared-engine reuse. It also supports artifact completeness by requiring a saved research artifact. It only weakly serves operator confidence: there is no requirement that findings be traceable enough for a non-coder to trust them. It does not materially advance the operator-facing parts of FR11/FR12. It also overreaches slightly by drifting from “baseline evidence” into “format preference” and “superior model” decisions that belong more naturally in Story 2.2.
- Recommendation: Keep the story as a Phase 0 baseline deep-dive, but narrow it to evidence about the baseline and its implications. Do not let it become the place where final strategy-format decisions are made.

**2. PRD Challenge**
- Assessment: `CONCERN`
- Evidence: [PRD FR9-FR13](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L470), [Story 2.1 AC3-AC6](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-1-claudebacktester-strategy-evaluator-review.md#L25), [Epic 2.2](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L652)
- Observations: FR9-FR10 are real drivers here; understanding the baseline authoring gap is necessary. FR12-FR13 are only partially challenged: the story compares current format to the target schema, but it does not explicitly require evidence about versioning, locking, config hashing, group dependencies, or objective functions. FR11 is especially thin; baseline evaluator review will not by itself tell you how to present a trustworthy human-readable strategy summary. The story also duplicates Story 2.2 by asking 2.1 to weigh JSON vs TOML vs DSL.
- Recommendation: Reframe 2.1 to answer “what constraints and opportunities does the baseline create for FR9-FR13?” Move “which format is best?” fully into 2.2. Add explicit comparison points for FR11, FR12, and the full FR13 shape.

**3. Architecture Challenge**
- Assessment: `CONCERN`
- Evidence: [Architecture D10 Phase 0 scope](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L741), [Architecture D14 crate boundary](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L939), [Story 2.1 AC7](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-1-claudebacktester-strategy-evaluator-review.md#L45), [Baseline mapping](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/baseline-to-architecture-mapping.md#L42)
- Observations: The architecture itself is basically right: D10 defines the contract, D14 preserves fidelity by sharing evaluation code. The story’s risk is different: AC7 implies that baseline module boundaries may justify re-opening D14. That is too permissive. The system is contracts-first and wrap-and-extend; baseline boundaries should inform adapters, not automatically reshape the architecture. The story also bleeds into `backtester` and “optimization-related evaluator logic,” which is broader than D14’s evaluator-core concern.
- Recommendation: Add an explicit rule: baseline structure is evidence, not authority. Architecture changes should be proposed only when they improve one of the four system objectives, not merely because the baseline grouped code differently.

**4. Story Design**
- Assessment: `CRITICAL`
- Evidence: [Story 2.1 AC3](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-1-claudebacktester-strategy-evaluator-review.md#L25), [Story 2.1 AC6-AC7](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-1-claudebacktester-strategy-evaluator-review.md#L40), [Story 2.1 Tasks](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-1-claudebacktester-strategy-evaluator-review.md#L52), [Epics conflict](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L650)
- Observations: The ACs are not tight enough for a `ready-for-dev` story. “What was painful, what worked” is not verifiable from source code alone. “Patterns that are superior” has no rubric. There is no requirement to record the baseline repo commit hash, no requirement to cite source files for findings, and no requirement to capture unknowns. There is also a cross-artifact inconsistency: the story correctly says “propose architecture updates only,” while `epics.md` still says the architecture document is updated.
- Recommendation: This story needs stricter acceptance criteria before implementation. Make it evidence-based, traceable, and reviewable. As written, a weak research artifact could satisfy the story while still leaving the operator with low confidence.

**5. Downstream Impact**
- Assessment: `CONCERN`
- Evidence: [Story 2.1 indicator feed to 2.8](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-1-claudebacktester-strategy-evaluator-review.md#L192), [Story 2.8 registry dependency](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L802), [PRD fidelity objective](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L447), [Architecture D14](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L953)
- Observations: The output needs to do more than list indicators. Downstream stories will need canonical names, parameter semantics, warm-up behavior, output arity, price-source mapping, naming differences (`EUR_USD` vs `EURUSD`), and numerical-risk notes. Without representative baseline examples or golden signal cases, later stories will have to rediscover fidelity expectations. The current story also does not explicitly require documenting baseline cost assumptions, which matters for D13 and later reconciliation work.
- Recommendation: Treat 2.1 as the seed for later regression and fidelity work, not just as a prose review. Add structured outputs that later stories can implement against directly.

## Overall Verdict
VERDICT: `REFINE`

## Recommended Changes
1. Add an acceptance criterion requiring the reviewed baseline repo path, branch, and commit hash to be recorded in the research artifact.
2. Add a traceability requirement: every keep/adapt/replace verdict must cite the concrete source files or modules it is based on.
3. Rewrite AC3 so it is evidence-based: “document the current authoring workflow from code/config/docs, and list operator interview questions or unknowns if repo evidence is insufficient.”
4. Add an explicit acceptance criterion for determinism and fidelity risk: statefulness, randomness, time dependence, floating-point sensitivity, and any backtest/live drift risks observed in the evaluator.
5. Add an explicit acceptance criterion for baseline execution-cost assumptions: whether spread/slippage/cost logic exists, where it lives, and whether it conflicts with D13.
6. Narrow Task 6 so Story 2.1 identifies baseline constraints and open questions only; final JSON/TOML/DSL selection stays in Story 2.2.
7. Change “baseline patterns that are superior” to a rubric tied to the four system objectives: reproducibility, operator confidence, artifact completeness, and fidelity.
8. Clarify that baseline module boundaries do not automatically justify D14 changes; they justify architecture updates only if they improve system objectives.
9. Replace “optimization-related evaluator logic” with “evaluator-facing optimization metadata support” to avoid bleeding into optimizer-methodology research.
10. Expand the indicator catalogue output to include canonical indicator name, warm-up/lookback behavior, output shape, supported price sources, dependencies, and naming conversions needed by Story 2.8.
11. Add a required appendix with 1-3 representative baseline strategy examples or signal traces that later stories can use as regression/fidelity seeds.
12. Add a note in the story that it does not modify `architecture.md` directly and that any conflicting wording elsewhere is superseded by this story’s “proposed updates only” rule.
