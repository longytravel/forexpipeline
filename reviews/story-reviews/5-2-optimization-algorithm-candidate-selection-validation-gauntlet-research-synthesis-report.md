# Story Synthesis: 5-2-optimization-algorithm-candidate-selection-validation-gauntlet-research

## Codex Observations & Decisions

### 1. Candidate Selection in MVP Flow
**Codex said:** Story plans candidate-selection implementation (Story 5.6 labeled "MVP-scoped") and E2E path including it, but FR26-FR28 are explicitly Growth-phase in the PRD.
**Decision:** AGREE
**Reasoning:** The PRD (Product Scope section) clearly states MVP uses "manual/simple candidate selection." FR26-FR28 are Growth. Story 5.6 was labeled "MVP-scoped" which directly contradicts this. The E2E proof story (5.7) also implied candidate selection was in scope.
**Action:** Fixed Story 5.6 to "Growth-phase" with explicit PRD reference. Updated Story 5.7 to use V1 simple candidate promotion. Added V1 fallback path requirement to Task 7 and Dev Notes. Updated AC#10 to require V1 fallback definition.

### 2. AC6/AC7 Not Crisply Verifiable + Operator Approval Gate
**Codex said:** "Updated if better" (AC6) and "build plan confirmed" (AC7) are subjective. Architecture/epic edits should require operator approval gate.
**Decision:** PARTIALLY AGREE
**Reasoning:** ACs were indeed vague. However, adding a heavyweight approval gate is over-engineering for a solo operator project — ROG reviews all diffs. The improvement is to make the ACs output-specific and note that amendments are proposals documented in an appendix.
**Action:** Replaced old AC6 with reproducibility AC. Replaced old AC7 with DBSCAN/HDBSCAN resolution AC. Added new AC8 (downstream contracts), AC9 (architecture amendments as proposals), AC10 (build plan with MVP/Growth classification and V1 fallback). Task 9 updated to note amendments go through Appendix C.

### 3. Missing Reproducibility Specification
**Codex said:** No explicit output for RNG seeding, stochastic repeatability, or checkpoint/resume determinism for CMA-ES/DE/Monte Carlo.
**Decision:** AGREE
**Reasoning:** CMA-ES, DE, and Monte Carlo are all stochastic. FR18 requires identical results from identical inputs, and NFR5 requires incremental checkpointing. The research artifact must specify how reproducibility works for each stochastic component.
**Action:** Added new AC#6 for reproducibility specifications. Added reproducibility sub-tasks to Tasks 2 and 4. Added "Reproducibility Requirements" section to Dev Notes. Added Appendix E to research artifact structure.

### 4. Tasks Framed as Validating Preselected Answers
**Codex said:** Tasks 2-4 validate pre-selected answers (CMA-ES, TOPSIS, etc.) rather than deciding among alternatives. Should require documenting rejected alternatives.
**Decision:** PARTIALLY AGREE
**Reasoning:** The "pre-selected" answers come from extensive external research (4 files per brief, including deep research reports and implementation compass artifacts). Re-doing that research would be wasteful. However, the research artifact should document what was considered and why alternatives were rejected — this aids operator confidence and future reviewability.
**Action:** Added "document rejected alternatives with evidence-backed rationale" sub-tasks to Tasks 2, 3, and 4. Added Decision Table (Section 9) to research artifact structure showing chosen method, alternatives, evidence, rationale per major area.

### 5. Missing Downstream Implementation Contracts
**Codex said:** Stories 5.3+ need config keys, score breakdown fields, candidate schemas, checkpoint expectations — not just prose recommendations. Without concrete contracts, later stories will invent their own interpretations.
**Decision:** AGREE
**Reasoning:** This is the strongest Codex observation. Research stories that produce only prose recommendations leave implementation stories guessing at interfaces. Concrete schemas prevent rewrite churn.
**Action:** Added new AC#8 requiring downstream contracts (optimizer I/O schema, per-fold score fields, confidence-score breakdown, candidate artifact schema, config keys, checkpoint format). Added Appendix D to research artifact structure.

### 6. FR23/FR24 Ambiguity
**Codex said:** FR23/FR24 in the PRD read like two different models. Should rewrite intent around parameter dependencies and opaque optimizer control.
**Decision:** DISAGREE
**Reasoning:** The PRD already has 2026-03-18 research updates on both FR23 and FR24 that explicitly clarify the opaque optimizer model. The story's Dev Notes (Architecture Constraints section, FR24 Clarification) already address this directly. The story's anti-pattern #3 explicitly warns against reinforcing the 5-stage model. This is already well-handled.
**Action:** None — already addressed in PRD updates and story dev notes.

### 7. Fix MVP/Growth Contradiction on Story 5.6
**Codex said:** Story 5.6 is labeled "MVP-scoped" but candidate selection (FR26-FR28) is Growth-phase. Internal contradiction.
**Decision:** AGREE
**Reasoning:** Clear contradiction. Story 5.6 covers FR26-FR28 which are explicitly Growth in both PRD and Story 5.1 findings.
**Action:** Changed Story 5.6 from "MVP-scoped" to "Growth-phase" in Task 7. Updated Dev Notes MVP vs Growth section.

### 8. Operator-Confidence Decision Table
**Codex said:** Add a decision table showing chosen method, alternatives considered, evidence source, rationale, and open risks per major area.
**Decision:** AGREE
**Reasoning:** Good research practice. Makes the research artifact self-contained for operator review and aids future revisiting of decisions.
**Action:** Added Section 9 "Decision Table" to research artifact structure in Task 8.

### 9. Elevate DBSCAN vs HDBSCAN Conflict
**Codex said:** Currently buried as anti-pattern note #9. Should be an explicit acceptance criterion with required decision and amendment recommendation.
**Decision:** AGREE
**Reasoning:** This is a real architecture discrepancy (D11 says DBSCAN, research recommends HDBSCAN). It deserves explicit resolution, not just a footnote.
**Action:** Added new AC#7 requiring explicit DBSCAN/HDBSCAN resolution. Added sub-task in Task 3 for resolution. Task 9 updated to include DBSCAN→HDBSCAN amendment if warranted.

### 10. V1 Fallback Path for Candidate Selection
**Codex said:** Define the manual/simple candidate-promotion method so Stories 5.3-5.5 can proceed without Story 5.6.
**Decision:** AGREE
**Reasoning:** PRD explicitly says MVP uses manual/simple candidate selection. If Story 5.6 is Growth, the MVP E2E path needs a defined fallback. Without it, Story 5.7 (E2E proof) has an implicit dependency on a Growth story.
**Action:** Added V1 fallback definition requirement to Task 3, Task 7, AC#10, and Dev Notes. Story 5.7 updated to use V1 simple promotion.

### 11. Story Too Wide — Should Split
**Codex said:** Split into two stories or two gated outputs: research synthesis and planning updates.
**Decision:** DISAGREE
**Reasoning:** For a solo operator project, the overhead of splitting a research story into two separate stories creates more coordination cost than it saves. The tasks are already well-sequenced (research synthesis first, then planning updates). The story is a natural unit of work: "research everything, then plan the implementation." Splitting would require a handoff artifact between the two halves that adds no value.
**Action:** None — kept as single story. The improved ACs and task structure provide sufficient internal gating.

## Changes Applied

1. **ACs expanded from 7 to 10:** Added reproducibility (AC#6), DBSCAN/HDBSCAN resolution (AC#7), downstream contracts (AC#8), architecture amendments as proposals (AC#9), build plan with MVP/Growth + V1 fallback (AC#10)
2. **Task 2:** Added rejected alternatives documentation and reproducibility sub-tasks
3. **Task 3:** Added V1 fallback, DBSCAN/HDBSCAN resolution, and rejected alternatives sub-tasks
4. **Task 4:** Added rejected alternatives and Monte Carlo reproducibility sub-tasks
5. **Task 7:** Fixed Story 5.6 to Growth-phase, Story 5.7 to MVP-only scope, added V1 fallback definition requirement
6. **Task 8:** Research artifact structure expanded with Decision Table (Section 9), Appendix D (downstream contracts), Appendix E (reproducibility specs)
7. **Task 9:** Updated to reference AC#7/#9, include DBSCAN amendment, note amendments documented in Appendix C
8. **Dev Notes:** Added "Reproducibility Requirements" section, updated MVP vs Growth section with V1 fallback path

## Deferred Items

- **PRD FR23/FR24 rewrite:** Codex suggested rewriting these FRs. They already have 2026-03-18 research updates that clarify the intent. If future implementation reveals remaining ambiguity, update then.
- **Story splitting:** If the story proves too large during implementation, it could be split at the Task 5 boundary (research synthesis vs planning updates). Not needed now.

## Verdict
VERDICT: IMPROVED
