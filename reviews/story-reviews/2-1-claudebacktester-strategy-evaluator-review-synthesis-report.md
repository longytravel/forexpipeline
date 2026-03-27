# Story Synthesis: 2-1-claudebacktester-strategy-evaluator-review

**Synthesizer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-15
**Codex Reviewer:** GPT-5.4 (holistic system review)

## Codex Observations & Decisions

### 1. System Alignment — Operator Confidence Gap
**Codex said:** Story weakly serves operator confidence. Overreaches by drifting into "format preference" decisions that belong in Story 2.2.
**Decision:** AGREE
**Reasoning:** Story 2.2 explicitly owns format selection (DSL vs TOML vs JSON comparison). Story 2.1 should produce baseline evidence and constraints, not recommendations on format choice. The operator confidence concern is valid — verdicts need source-file traceability to be trustworthy.
**Action:** (1) Added source-file citation requirement to AC1 verdict table. (2) Narrowed Task 6 format subtask to "constraints from baseline evidence" with explicit note that format selection is 2.2's scope. (3) Added anti-pattern #10 prohibiting format selection recommendations.

### 2. PRD Challenge — FR11/FR12/FR13 Partially Addressed
**Codex said:** FR12-FR13 only partially challenged. FR11 is thin. Story duplicates 2.2 by weighing format options.
**Decision:** AGREE (partially)
**Reasoning:** FR11 (operator review of strategy summary) is legitimately thin here because this story reviews the *baseline evaluator*, not the new dialogue/summary system. That's expected. However, FR12 (versioning/locking) and FR13 (optimization grouping) should be compared against baseline capabilities to identify constraints. The format duplication with 2.2 is a real problem.
**Action:** (1) Narrowed Task 6 to remove format recommendation. (2) AC5 already covers "capabilities NOT covered by D10 or FR9-FR13" which implicitly includes FR12/FR13 comparison. No additional AC needed — the existing coverage is appropriate for a baseline review story. FR11 gap is expected and acceptable.

### 3. Architecture Challenge — AC7 Too Permissive on D14 Reopening
**Codex said:** AC7 implies baseline module boundaries may justify re-opening D14. Too permissive. Story also bleeds into backtester and optimizer scope.
**Decision:** AGREE
**Reasoning:** Architecture is contracts-first, wrap-and-extend. Baseline structure is evidence, not authority. Optimizer methodology is out of scope for a strategy *evaluator* review.
**Action:** (1) Modified AC7 criterion (c) to require that D14 mismatch "would harm a system objective" before triggering a proposal. (2) Added "system objective justification" requirement to AC7 output. (3) Added anti-pattern #9 explicitly stating baseline boundaries are evidence, not blueprints. (4) Replaced "optimization-related evaluator logic" in Task 7 with "evaluator-facing optimization metadata support."

### 4. Story Design — ACs Not Tight Enough for Ready-for-Dev
**Codex said:** CRITICAL. "What was painful, what worked" not verifiable from source code. "Superior" has no rubric. No commit hash requirement. No source-file citation. No unknowns capture. Cross-artifact inconsistency with epics.md.
**Decision:** AGREE
**Reasoning:** This is the strongest observation. A research story's value is in the rigor and traceability of its findings. The original AC3 assumed operator interview data would be available from code review — it won't always be. The "superior" judgment needs the four system objectives as its rubric. The epics inconsistency is real and must be documented.
**Action:** (1) Rewrote AC3 to be evidence-based with explicit unknowns. (2) Replaced "superior" in AC6 with rubric tied to four system objectives. (3) Added AC8: baseline repo path, branch, commit hash. (4) Added Task 1 subtask to record provenance. (5) Added cross-artifact note documenting that epics.md AC6 wording is superseded by this story's AC7.

### 5. Downstream Impact — Indicator Catalogue Too Shallow, No Fidelity Seeds
**Codex said:** Catalogue needs canonical names, warm-up behavior, output arity, price-source mapping, naming differences. No golden signal cases for regression. No baseline cost assumptions documented.
**Decision:** AGREE
**Reasoning:** Story 2.8 (indicator registry) will implement directly from this catalogue. Shallow documentation forces 2.8 to re-discover everything. Cost model presence/absence matters for D13 planning. Representative strategy examples as fidelity seeds are high value at low cost.
**Action:** (1) Expanded AC2 to require: canonical name, output shape, warm-up/lookback, supported price sources, dependencies, naming convention notes. (2) Added AC9: determinism/fidelity risk assessment (statefulness, randomness, floating-point sensitivity). (3) Added AC10: baseline cost model presence/absence and D13 compatibility. (4) Added Task 3 subtask for fidelity risk assessment. (5) Added Task 8 subtasks for representative strategy examples and cost model documentation.

## Changes Applied

### Acceptance Criteria
- **AC1:** Added "citing specific source files/modules for each verdict"
- **AC2:** Expanded from "parameter signatures, computation logic, input/output types" to include canonical name, output shape, warm-up/lookback, price sources, dependencies, naming conventions
- **AC3:** Rewritten from "what was painful, what worked" to evidence-based with explicit unknowns
- **AC6:** Replaced "superior" with rubric: "demonstrably improve one or more system objectives (reproducibility, operator confidence, artifact completeness, fidelity)"
- **AC7:** Modified criterion (c) to require system objective harm; added "system objective justification" to output; added "baseline structure is evidence, not authority" to ref note
- **AC8 (NEW):** Baseline repo path, branch, commit hash traceability
- **AC9 (NEW):** Determinism/fidelity risk documentation (statefulness, randomness, FP sensitivity, drift)
- **AC10 (NEW):** Baseline cost model presence/absence and D13 compatibility

### Tasks
- **Task 1:** Added subtask to record baseline provenance (AC #8)
- **Task 3:** Added subtask for fidelity risk assessment (AC #9)
- **Task 6:** Narrowed format subtask from "preference" to "constraints from evidence" with 2.2 scope note
- **Task 7:** Replaced "optimization-related evaluator logic" with "evaluator-facing optimization metadata support"
- **Task 8:** Added subtasks for representative strategy examples and cost model documentation

### Dev Notes
- **Anti-patterns #9-#10 (NEW):** Baseline boundaries are evidence not blueprints; no format selection recommendations
- **Cross-Artifact Note (NEW):** Documents that epics.md AC6 wording is superseded by this story's AC7

## Deferred Items
- **FR11 depth:** Codex noted FR11 (operator review of human-readable summary) is thin in this story. This is expected — FR11 is primarily addressed by Story 2.2+ when the dialogue/summary system is designed. No action needed in 2.1.
- **Epics.md fix:** The cross-artifact inconsistency (epics.md says "architecture document is updated" vs story says "propose only") should be corrected in epics.md during next epics maintenance pass.

## Verdict
VERDICT: IMPROVED
