# Story Synthesis: 5-1-claudebacktester-optimizer-validation-pipeline-review

**Synthesized by:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-21
**Codex Review Verdict:** REFINE
**Synthesis Verdict:** IMPROVED

---

## Codex Observations & Decisions

### 1. Reproducibility Gap in System Alignment
**Codex said:** The story barely touches reproducibility despite it being a core system objective. It advances artifact completeness and fidelity but not reproducibility unless it explicitly audits determinism-relevant contracts.
**Decision:** AGREE
**Reasoning:** The PRD marks "Deterministic reproducibility" as a "Fix" priority. FR18 (identical backtest results given identical inputs) and FR42 (resume from checkpoint) are directly relevant. A baseline review that doesn't assess whether the baseline captures enough state to reproduce runs has a real gap.
**Action:** Added AC8 requiring reproducibility/determinism assessment. Added Task 10 with 5 specific subtasks covering config capture, artifact persistence, per-run reproducibility, and validation state. Added `verify_reproducibility_assessment_complete` to Task 9 verification checks.

### 2. Candidate Selection Overreach for MVP
**Codex said:** FR26-FR28 are included as equally central to V1, but the PRD explicitly defers candidate selection pipeline out of MVP. The story should treat candidate selection as a "baseline behavior snapshot" rather than a design driver.
**Decision:** AGREE
**Reasoning:** PRD Phase 1 (MVP) says "Explicitly NOT in MVP: Candidate selection pipeline (research-dependent — use manual/simple selection for MVP)." The story was treating FR26-FR28 at parity with FR29-FR37 (validation gauntlet), which IS MVP scope. Reviewing baseline behavior is appropriate; designing around it for V1 is not.
**Action:** Reframed AC3 to produce "baseline snapshot with MVP disposition (defer/adapt/drop)" instead of full design analysis. Renamed Task 4 to "Snapshot baseline candidate selection logic" and added MVP disposition subtask. Added anti-pattern #11 explicitly calling out FR26-FR28 as Growth-phase.

### 3. FR24 Semantic Confusion
**Codex said:** FR24 ("strategies define their own optimization stages") conflicts with the updated architecture/epic direction that staging is internal and opaque. The story reinforces the superseded fixed-stage mental model.
**Decision:** AGREE
**Reasoning:** FR24's research update (2026-03-18) already clarifies: "the strategy spec defines parameter ranges and conditionals; the optimizer decides internally how to structure the search. 5-stage locking is NOT mandated." The story should review baseline staging to decide what to discard, not to design around it.
**Action:** Added FR24 clarification to Architecture Constraints section. Added anti-pattern #12 about preventing baseline staging assumptions from leaking into new design.

### 4. AC7 Lacks Decision Threshold
**Codex said:** "Findings warrant changes" has no threshold — when does a finding rise to the level of requiring an architecture amendment?
**Decision:** AGREE
**Reasoning:** Without a threshold, AC7 is subjectively testable. The dev could either over-propose changes or skip them without clear guidance.
**Action:** Tightened AC7 to require that findings "contradict D1/D3/D11/D14 assumptions, reveal an incompatible baseline contract, or identify a cheaper compatible path." Added explicit threshold note in the ref line.

### 5. Missing Baseline-to-Target Compatibility Matrix
**Codex said:** Downstream stories need more than keep/adapt/replace verdicts. They need hard answers on per-fold scoring support, checkpoint placement, existing artifacts, D11 feed compatibility, and minimum V1 candidate presentation.
**Decision:** AGREE
**Reasoning:** The verdict table answers "what do we do with this component?" but not "how does the baseline's actual behavior map to our target contracts?" The compatibility matrix is a genuinely different and useful deliverable for implementation stories.
**Action:** Added Appendix E (Baseline-to-Target Compatibility Matrix) to the Research Artifact Structure. Added subtask in Task 7 to produce the matrix. Added `verify_compatibility_matrix_complete` to Task 9.

### 6. Task 8 Overreaches into Optimizer Crate Design
**Codex said:** Task 8 mentions "optimizer crate structure needs design updates" which goes beyond what the architecture permits — D3 says the optimizer crate is an evaluation engine with search in Python.
**Decision:** AGREE
**Reasoning:** The optimizer crate's role is evaluation, per D3. A baseline review should assess contract compatibility with the evaluation-engine model, not propose broader crate design changes.
**Action:** Narrowed Task 8 to contract compatibility only. Reframed D11 comparison as "what baseline outputs can feed D11?" Changed conditions for proposing amendments to match AC7 threshold. Added explicit note not to propose design changes beyond contract compatibility.

### 7. Research Brief 5A/5B/5C Dependency Issue
**Codex said:** Task 7 requires cross-references to research briefs 5A/5B/5C, but those are Story 5.2's domain. Story 5.1 should not depend on 5.2 outputs.
**Decision:** AGREE
**Reasoning:** Story 5.2's AC1 explicitly says "Given Story 5.1's verdict table identifies what needs external research." The dependency flows 5.1 → 5.2, not the reverse. Requiring 5A/5B/5C as cross-references in 5.1 creates a circular dependency.
**Action:** Changed Task 7 to mark research briefs 5A/5B/5C as "optional context" rather than required cross-references. Primary cross-references are now optimization-methodology-research-summary.md and architecture decisions D3/D11.

### 8. Task 9 Pseudo-Tests Validate Checklists Not Usefulness
**Codex said:** Replace pseudo-tests with concrete completion checks tied to downstream usefulness, especially "can Story 5.2 choose research topics without reopening baseline code?"
**Decision:** PARTIALLY AGREE
**Reasoning:** The pseudo-tests are appropriate for a research story — they ensure the artifact is structurally complete. But Codex is right that the downstream handoff check should validate usefulness, not just existence. I refined rather than replaced.
**Action:** Renamed Task 9 to "Verify research completeness for downstream usefulness." Strengthened the handoff check to require Story 5.2 independence. Added two new verification items: reproducibility assessment completeness and compatibility matrix completeness.

### 9. "Do Not Carry Forward" Appendix
**Codex said:** Add an appendix listing baseline concepts structurally incompatible with the new system, especially fixed 5-stage locking.
**Decision:** AGREE
**Reasoning:** This is a smart safeguard against design contamination. Without an explicit exclusion list, flawed baseline patterns could leak into implementation stories through the verdict table's "adapt" verdicts.
**Action:** Added Appendix F ("Do Not Carry Forward" list) to Research Artifact Structure. Added "Do Not Carry Forward" items requirement to Task 7 handoff and Task 9 verification.

### 10. Add System Objectives AC
**Codex said:** Add an acceptance criterion requiring assessment against the four system objectives: reproducibility, operator confidence, artifact completeness, fidelity.
**Decision:** DISAGREE
**Reasoning:** This would add a vague, meta-level AC that's difficult to test. The specific gaps Codex identified (reproducibility) are better addressed through the concrete AC8 already added. The story already advances artifact completeness (verdict table), fidelity (validation review), and operator confidence (evidence assessment) through its existing ACs. Adding a "check all four objectives" AC would be box-ticking, not substance.
**Action:** None — reproducibility gap addressed via AC8/Task 10. Other objectives already covered.

### 11. Minimal Operator-Facing Candidate Review Deliverable
**Codex said:** Add an explicit deliverable for MVP candidate handling — what minimal operator-facing candidate review is enough if full FR26-FR28 remains deferred.
**Decision:** DEFER
**Reasoning:** Valid concern, but the answer depends on Story 5.2's research output (what algorithms and ranking approaches are viable). Story 5.1 can snapshot baseline behavior and mark MVP disposition, but defining the V1 candidate review approach is premature here. The Task 4 MVP disposition subtask captures enough for handoff.
**Action:** None beyond the MVP disposition subtask already added to Task 4.

## Changes Applied

1. **AC3** — Reframed from "document candidate selection" to "baseline snapshot with MVP disposition (defer/adapt/drop)" with Growth-phase note
2. **AC7** — Added concrete threshold: contradicts architecture assumptions, incompatible contract, or cheaper compatible path
3. **AC8** (new) — Reproducibility/determinism assessment of baseline optimization and validation
4. **Task 4** — Renamed to "Snapshot baseline candidate selection logic," added MVP disposition subtask
5. **Task 7** — Research briefs 5A/5B/5C marked as optional context. Added Baseline-to-Target Compatibility Matrix subtask. Strengthened handoff notes requirements
6. **Task 8** — Narrowed to contract compatibility. Reframed D11 question. Added explicit note against proposing optimizer crate design changes
7. **Task 9** — Renamed to "Verify research completeness for downstream usefulness." Strengthened handoff verification. Added reproducibility and compatibility matrix checks
8. **Task 10** (new) — Baseline reproducibility and determinism assessment with 5 subtasks
9. **Research Artifact Structure** — Added Appendix E (Baseline-to-Target Compatibility Matrix) and Appendix F ("Do Not Carry Forward" list)
10. **Architecture Constraints** — Added FR24 updated framing clarification
11. **Anti-patterns** — Added #11 (candidate selection V1 scope) and #12 (preventing baseline staging leak)

## Deferred Items

- **MVP candidate review approach** — Valid concern but premature to define at 5.1 level; depends on 5.2 research output. Task 4 MVP disposition captures enough for handoff.
- **Operator readability of research artifact** — Codex noted ACs optimize for engineering inventory over operator evidence. True but acceptable: this is a research story consumed by the dev implementing Stories 5.3+, not an operator-facing artifact.

## Verdict
VERDICT: IMPROVED
