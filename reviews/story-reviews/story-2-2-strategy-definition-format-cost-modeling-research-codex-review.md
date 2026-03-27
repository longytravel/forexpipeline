# Story 2-2-strategy-definition-format-cost-modeling-research: Story 2.2: Strategy Definition Format & Cost Modeling Research — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-15
**Type:** Holistic System Alignment Review

---

## 1. System Alignment
**Assessment:** ADEQUATE

**Evidence:**
- The story clearly advances reproducibility and fidelity by researching a constrained strategy format and researched cost assumptions before backtesting, which matches the PRD’s technical success criteria for reproducibility, execution cost modeling, and pipeline completeness in [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md:93).
- It also advances artifact completeness by producing a dedicated research artifact and a downstream build plan in [2-2-strategy-definition-format-cost-modeling-research.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-2-strategy-definition-format-cost-modeling-research.md:103).
- It touches operator confidence only indirectly. The comparison criteria emphasize expressiveness, tooling, AI suitability, and Rust parseability, but not human reviewability/diffability, even though FR11 is core in [2-2-strategy-definition-format-cost-modeling-research.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-2-strategy-definition-format-cost-modeling-research.md:26) and [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md:474).

**Observations:**
- The story is aligned on “research before build,” which is right for V1.
- It works against system simplicity in two places: the optional hybrid expression-language path reintroduces interpreter-like complexity, which pushes against D10’s constrained rule-engine model, in [2-2 story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-2-strategy-definition-format-cost-modeling-research.md:73) and [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md:625).
- The story also starts to overreach into growth concerns: FR22/live calibration and multi-pair hints show up here even though V1 is one pair/timeframe and FR22 is mapped later.

**Recommendation:**
- Keep the story’s core purpose.
- Add operator-reviewability, diffability, and error explainability as first-class evaluation criteria.
- Treat DSL or hybrid-expression options as exception paths requiring explicit architecture-change justification, not equal default candidates.

## 2. PRD Challenge
**Assessment:** CONCERN

**Evidence:**
- FR9-FR13 and FR20-FR21 are the right requirements for this story in [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md:470) and [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md:487).
- FR22 is mapped at epic level to a later reconciliation epic in [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md:259), and Story 2.6 explicitly limits FR22 to an interface-only hook in [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md:764).
- Story 2.2 still pulls FR22 directly into the research scope in [2-2 story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-2-strategy-definition-format-cost-modeling-research.md:21).

**Observations:**
- The PRD is asking for the right high-level problem to be solved.
- The decomposition is slightly wrong: “initial researched cost model” and “live auto-update methodology” are not the same requirement and should not be treated as one research bundle.
- FR11 is underrepresented in the story despite being central to non-coder operator confidence.
- FR10’s wording in the PRD says “generate executable strategy code,” but D10 is really steering the system toward executable specifications, not free-form code generation.

**Recommendation:**
- Narrow Story 2.2 to: format decision, initial cost-model decision, and future calibration hooks.
- Move any real FR22 methodology design to the later reconciliation/calibration epic.
- Add an explicit PRD trace note that this story optimizes for spec generation and review, not arbitrary code generation.

## 3. Architecture Challenge
**Assessment:** CONCERN

**Evidence:**
- D10 already narrows the spec path to JSON/TOML artifacts and a constrained rule-engine model in [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md:627) and [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md:637).
- D7 strongly biases toward TOML for deterministic parsing and config hashing in [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md:518).
- Downstream stories already hard-code TOML-based contracts for strategy and cost-model schemas in [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md:686) and [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md:768).
- D13’s artifact format currently assumes mean/std per session only in [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md:918).

**Observations:**
- The Rust library decisions in D13/D14 are appropriate.
- The architecture is not actually format-neutral anymore, but Story 2.2 pretends it is. That creates fake optionality.
- The hybrid-expression option is the clearest source of unnecessary complexity.
- D13 may be under-specified for fidelity: Story 2.2 asks whether extra fields are needed, but it does not force a decision on whether mean/std is even the right model shape.

**Recommendation:**
- Either make the research genuinely architecture-neutral by removing downstream TOML assumptions, or narrow the research to “validate TOML-first unless disproven.”
- Add a required decision on cost-model representation sufficiency: mean/std vs quantiles/tails vs explicit limitations.
- Keep D13/D14, but reduce speculative format branching.

## 4. Story Design
**Assessment:** CRITICAL

**Evidence:**
- The story’s primary prerequisite points to a non-existent research artifact path in [2-2 story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-2-strategy-definition-format-cost-modeling-research.md:60), while the only available 2.1 file in the repo is [2-1-claudebacktester-strategy-evaluator-review.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-1-claudebacktester-strategy-evaluator-review.md).
- ACs mostly verify topic coverage, not decision quality or evidence quality, in [2-2 story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-2-strategy-definition-format-cost-modeling-research.md:16).
- The story also caps the artifact at 2000-3000 words in [2-2 story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-2-strategy-definition-format-cost-modeling-research.md:230) while demanding two major research domains, architecture refinements, and a build plan.

**Observations:**
- As written, the story is not implementation-ready because its required input is unavailable or misaddressed.
- The story is too broad for one acceptance envelope. Strategy-format research and cost-model research are related, but they block different downstream stories.
- The acceptance criteria are not strong enough to stop shallow research.
- The word-count cap incentivizes superficial output and undermines operator confidence.

**Recommendation:**
- Mark the story blocked until the 2.1 artifact path is corrected or the actual output exists.
- Split this into two stories or two independently sign-off-able artifacts.
- Replace “covers/includes” AC language with decision-record ACs: chosen option, rejected options, evidence quality, unresolved assumptions, and downstream contract impact.

## 5. Downstream Impact
**Assessment:** CONCERN

**Evidence:**
- Story 2.2 is declared as the source for Stories 2.3-2.9 build direction in [2-2 story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-2-strategy-definition-format-cost-modeling-research.md:114).
- The story lists downstream consumers, but omits Story 2.5 even though review/diffability depend on the format choice in [2-2 story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-2-strategy-definition-format-cost-modeling-research.md:311).
- Story 2.3, 2.6, 2.7, and 2.8 already expect concrete contract and crate outcomes in [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md:686), [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md:768), [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md:786), and [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md:812).

**Observations:**
- The outputs needed downstream are more specific than the story currently guarantees: parser constraints, schema invariants, summary/diff requirements, artifact provenance rules, and cost-model field decisions.
- If the story chooses a format that downstream stories are not written to consume, you will force rewrites immediately in 2.3/2.4/2.8.
- If the cost-model research does not produce provenance and limitation notes, 2.6/2.7 will encode false precision and reconciliation will be harder later.

**Recommendation:**
- Make the required outputs explicit: canonical format decision, schema invariants, example artifact, parser assumptions, operator-summary implications, cost-model fields, calibration hooks, and known limitations.
- Add Story 2.5 as an explicit downstream consumer.
- Require a short “rewrite risk” section in the research artifact.

## Overall Verdict
VERDICT: REFINE

## Recommended Changes
1. Fix the Story 2.1 dependency path and block Story 2.2 until the actual 2.1 research artifact exists.
2. Split Story 2.2 into separate strategy-format and cost-model research stories, or require two separately sign-off-able sections/artifacts.
3. Add FR11-aligned evaluation criteria: operator readability, diffability, summary generation, and error explainability.
4. Reframe FR22 here as “define artifact/calibration hooks for later live update,” not full auto-update methodology design.
5. Either narrow the format decision to a TOML-first assumption or rewrite downstream stories to be truly format-agnostic.
6. Treat custom DSL and hybrid-expression options as architecture-exception paths requiring explicit system-objective justification.
7. Add a mandatory decision record: chosen option, rejected options, evidence sources, unresolved assumptions, and downstream implications.
8. Replace “research includes/covers” ACs with testable quality gates, including minimum evidence provenance and source attribution requirements.
9. Add an explicit decision on whether D13’s mean/std session model is sufficient for V1 fidelity, and document limitations if retained.
10. Add required provenance fields for cost research: broker/account type, sample window, timezone/session mapping, and calibration method.
11. Add Story 2.5 to downstream consumers and require the artifact to specify how summaries and diffs will be generated from the chosen format.
12. Remove or relax the 2000-3000 word cap; if brevity matters, keep an executive summary but allow the evidence appendix to grow.
