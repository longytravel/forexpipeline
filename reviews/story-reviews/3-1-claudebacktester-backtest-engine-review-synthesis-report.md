# Story Synthesis: 3-1-claudebacktester-backtest-engine-review

**Synthesizer:** Claude Opus 4.6
**Date:** 2026-03-17
**Story file:** `_bmad-output/implementation-artifacts/3-1-claudebacktester-backtest-engine-review.md`
**Codex review:** `reviews/story-reviews/story-3-1-claudebacktester-backtest-engine-review-codex-review.md`

---

## Codex Observations & Decisions

### 1. System Alignment — Story scope drift from epic-level definition
**Codex said:** Story overreaches V1 by expanding from a backtest-engine review into optimizer, validator, checkpoint, storage, and architecture-governance. Barely advances operator confidence — no ACs for FR16, FR17, or FR39. Either narrow to backtester core or rename as Epic 3 baseline systems review.

**Decision:** AGREE (rename, not narrow)

**Reasoning:** The scope expansion is justified — no other Epic 3 story provides a review venue for the optimizer (91K lines), validation pipeline (92K lines), or pipeline orchestration. Stories 3.2–3.9 all depend on findings from this review. Narrowing would orphan those reviews. However, the title and narrative must match the actual scope. FR16 (chart-led results) and FR17 (anomaly detection) are implementation concerns for Story 3-7 (AI Analysis Layer), not review concerns — adding them here would be scope creep on a research story. FR39 (operator dialogue control) is completely outside scope.

**Action:** Renamed story from "ClaudeBackTester Backtest Engine Review" to "ClaudeBackTester Baseline Systems Review". Added scope note explaining why breadth was expanded beyond epic-level AC. Updated narrative to include V1 port boundaries and downstream handoff. Did NOT add FR16/FR17/FR39 ACs.

### 2. PRD Challenge — Misallocated review depth across FR requirements
**Codex said:** Story spends major effort on FR25-FR28 (visualization, candidate selection — partly post-MVP) and FR36-FR37 (post-MVP research areas) while under-specifying operator-facing outcomes. Recompose into MVP-critical, operator evidence, and later sophistication buckets.

**Decision:** AGREE

**Reasoning:** V1 is gated on reproducibility and evidence quality, not optimization sophistication or visualization. FR25-FR28 and FR36-FR37 are post-V1 concerns that should be catalogued at gap level, not deep-dived. The three-bucket approach (deep / moderate / gap-level) aligns with our "V1 is NOT gated on profitability" principle.

**Action:** Added V1 Scope Filtering table to Dev Notes with explicit depth levels. Updated AC #4 (optimization) to specify "gap-level assessment against FR25-FR28" with note that deep focus should be on core mechanics reusable in V1. Updated AC #5 (validation) to specify "light assessment against FR36-FR37" as growth-phase visualization.

### 3. Architecture Challenge — NFR9 misinterpretation + missing V1 port boundary
**Codex said:** NFR9 is misframed as "thread-safe concurrent backtests from same Rust process" when the PRD defines it as resource management strategy (memory pooling, result streaming, worker pool sizing). Story should also test whether V1 should port only backtester core to Rust and keep optimizer/validator in Python.

**Decision:** AGREE

**Reasoning:** PRD NFR9 explicitly says "The resource management strategy (memory pooling, result streaming, worker pool sizing) is a Phase 0 research output." The story had it wrong. The V1 port boundary question is critical — the baseline is Python-first (15K lines Python, 1.6K Rust), and blindly porting everything to Rust would be massive scope creep for a one-person operator.

**Action:** Fixed NFR9 reference in AC #2 and Task 2 to correctly describe resource management scope. Added V1 Port Boundary column to the component verdict table (AC #8). Added V1 Port Boundary summary as a mandatory output in Task 9.

### 4. Story Design — ACs too soft, governance inconsistency
**Codex said:** (CRITICAL) Story is too big and too soft. ACs are "a document describes..." which isn't a crisp done condition. Governance inconsistency: epic says update architecture directly, story says proposals only.

**Decision:** PARTIALLY AGREE

**Reasoning:**
- **AC wording:** Agreed — "a document describes" is soft. Changed to specify named research artifact sections (e.g., "the research artifact includes a PyO3 Bridge & Data Flow specification documenting:"). This makes the artifact structure a verifiable done condition.
- **Story size:** Disagree with splitting. This is a one-person operator project. One comprehensive research artifact is more useful than 3-4 fragmented review stories that would create coordination overhead. The story IS bounded — it produces one artifact document, no code.
- **Governance:** Agreed the inconsistency exists. The epic says "Architecture document is updated if findings warrant changes" (AC #7), while the story says "Do NOT modify architecture.md directly." Resolution: research artifact proposes changes, operator approval gates the actual architecture.md update. This preserves the BMAD research→gate→lock workflow while aligning with the epic.

**Action:** Replaced all "a document describes" AC phrasing with named artifact section references. Updated AC #10 to explicitly state that operator-approved changes trigger architecture.md updates (aligning with epic AC #7). Did NOT split the story.

### 5. Downstream Impact — Output precision gap
**Codex said:** (ADEQUATE) Story is downstream-aware but later stories need extracted contracts, migration boundaries, and "do not port yet" decisions, not just prose. Without this, Stories 3.3-3.6 will re-litigate D1/D2/D3/D14.

**Decision:** AGREE

**Reasoning:** This is the most actionable observation. Without mandatory handoff artifacts, each downstream story will re-open the same questions this review is supposed to close. A structured handoff section prevents re-litigation and saves significant effort across 8 downstream stories.

**Action:** Added new AC #11 requiring a Downstream Handoff section with per-story subsections (3.2–3.9) listing interface candidates, migration boundaries, V1 port decisions, deferred items, and open questions. Added corresponding task in Task 9.

### 6. (From Recommended Changes) Reduce line count emphasis
**Codex said:** Reduce emphasis on raw file inventories and line counts; prioritize capability seams, fidelity risks, and migration effort.

**Decision:** PARTIALLY AGREE

**Reasoning:** Line counts ARE useful for the dev agent to scope effort and plan work. They helped accurately in Stories 1-1 and 2-1. But they should not be the review focus. Added a note that line counts are effort indicators, not the review focus.

**Action:** Added note in V1 Scope Filtering section: "Line counts in module inventories are effort indicators for the dev agent, not the review focus. Prioritize capability seams, fidelity risks, and migration effort over raw inventory."

### 7. (From Recommended Changes) Replace "a document describes" wording
**Codex said:** Replace with required outputs: module matrix, migration matrix, risk register, contract candidates, decision log.

**Decision:** AGREE (adapted)

**Reasoning:** Agreed on the principle. Adapted to name specific research artifact sections rather than introducing new artifact types (risk register, decision log) that would add overhead for a one-person operator. The research artifact structure in Dev Notes already defines 9 sections + appendices — the AC wording now references these sections explicitly.

**Action:** Already covered in Decision #4 above.

---

## Changes Applied

1. **Title renamed:** "ClaudeBackTester Backtest Engine Review" → "ClaudeBackTester Baseline Systems Review"
2. **Scope note added:** HTML comment explaining why scope was broadened beyond epic-level definition
3. **Narrative updated:** Added "with clear V1 port boundaries and downstream handoff artifacts for Stories 3.2–3.9"
4. **AC #2:** Tightened to "research artifact includes a PyO3 Bridge & Data Flow specification"; fixed NFR9 from "thread-safe concurrent backtests" to "resource management strategy: memory pooling, result streaming, worker pool sizing"
5. **AC #3:** Tightened to "research artifact includes a lifecycle specification"
6. **AC #4:** Tightened to "research artifact includes an optimization engine specification"; added V1 scope filter — FR25-FR28 at gap level
7. **AC #5:** Tightened to "research artifact includes a validation pipeline specification"; split FR29-FR35 (deep) from FR36-FR37 (light)
8. **AC #6:** Tightened to "research artifact includes a pipeline orchestration specification"
9. **AC #7:** Tightened to "research artifact includes a metrics and storage specification"
10. **AC #8:** Added "V1 Port Boundary (port-now / wrap-for-V1 / defer / do-not-port)" column to verdict table
11. **AC #10:** Added governance alignment — operator-approved changes trigger architecture.md updates per epic AC #7
12. **AC #11 (NEW):** Downstream Handoff section mandatory — per-story subsections for 3.2–3.9
13. **Task 2:** Split NFR1/NFR9 assessment into separate subtasks with correct NFR9 scope
14. **Task 8:** Updated verdict table columns to match AC #8
15. **Task 9:** Added downstream handoff and V1 port boundary as mandatory deliverables; aligned governance note
16. **Dev Notes:** Added V1 Scope Filtering section with depth-level table and line-count guidance

## Deferred Items

- **FR16/FR17/FR39 ACs:** Codex suggested adding these. Deferred — FR16 (chart-led results) and FR17 (anomaly detection) belong in Story 3-7 (AI Analysis Layer). FR39 (operator dialogue) is outside scope entirely. The downstream handoff for 3-7 should include relevant findings about result presentation capabilities.
- **Story splitting:** Codex flagged the story as too big. Deferred — splitting creates coordination overhead for a one-person operator. The story produces one artifact document; its size is proportional to the baseline codebase being reviewed.

## Verdict

VERDICT: IMPROVED
