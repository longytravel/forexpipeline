# Story Synthesis: 3-2-python-rust-ipc-deterministic-backtesting-research

**Synthesizer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-17
**Story:** Story 3.2: Python-Rust IPC & Deterministic Backtesting Research
**Codex Verdict:** REFINE
**Synthesis Verdict:** IMPROVED

---

## Codex Observations & Decisions

### 1. System Alignment — Overreach for V1
**Codex said:** Story overreaches by pulling in full build planning for 3.3-3.9, D15/live-daemon alignment, exhaustive FR/NFR traceability, and runnable code snippets. Should narrow to minimum V1 needs: decision record for batch IPC, reproducibility rules, checkpoint contract, and memory-budget contract for Stories 3.3-3.5.
**Decision:** PARTIALLY AGREE
**Reasoning:** The build plan for 3.3-3.9 IS in the epics (AC #7 explicitly says "a final build plan for Stories 3.3-3.9 is confirmed"). However, the depth should be differentiated: detailed for 3.3-3.5 (direct consumers of research contracts) and lighter dependency notes for 3.6-3.9. The core research scope (IPC, determinism, checkpoint, memory) is correctly scoped — those are the four V1 pillars.
**Action:** AC #7 rewritten to differentiate depth. Task 7 split into detailed build plan (3.3-3.5) and dependency notes (3.6-3.9). Task 8 research artifact structure updated to match. Story description tightened.

### 2. PRD Challenge — NFR5 Misapplication and Reproducibility Ambiguity
**Codex said:** NFR5 is explicitly about "long-running optimization runs" in the PRD, but this story shifts it to backtests. Also, PRD says "materially identical results within defined tolerance" while Epic 3 Story 3.9 AC #9 hardens to "bit-identical results" — this changes implementation cost and test design.
**Decision:** AGREE on both points
**Reasoning:** NFR5 literally says "long-running optimization runs." The checkpoint concept applies to backtests too (D3 says "within-stage checkpointing handled by Rust batch binary"), but the citation should be precise. The tolerance vs bit-identical tension is CRITICAL — Story 3.2 is the exact right place to resolve it before 3.4/3.5 implement against conflicting assumptions.
**Action:** AC #3 rewritten to correctly cite NFR5 as optimization-focused while noting D3's within-stage checkpoint support for backtests. Added explicit "Reproducibility Contract" to AC #2 requiring resolution of PRD vs Epic 3 tension per output type. New section #4 added to Task 8 research artifact structure.

### 3. Architecture Challenge — Output Location, D15 Scope, Framing
**Codex said:** Architecture says Phase 0 research outputs go to `_bmad-output/planning-artifacts/research/`, not `artifacts/research/`. D15 is out of scope for batch IPC. Framing should be "validate and harden" not "decide from scratch."
**Decision:** AGREE on all three points
**Reasoning:** The architecture literally defines Phase 0 research output location as `_bmad-output/planning-artifacts/research/`. D15 (Named Pipes) is explicitly for live daemon communication — including it in mandatory batch IPC alignment dilutes focus and adds unnecessary scope. D1 is already decided; the comparison matrix provides evidence, not a fresh decision.
**Action:** Output path changed from `artifacts/research/` to `_bmad-output/planning-artifacts/research/` in Task 8, Project Structure Notes, and directory creation note. D15 removed from mandatory alignment in AC #5 (with "confirmed no impact" note), Task 6, and architecture alignment matrix. D1 framing rewritten in Dev Notes to "validates and hardens" language. D15 Dev Notes section explicitly marked OUT OF SCOPE.

### 4. Story Design — Persona, Validation Quality, Runnable Snippets, 3.1 Dependency
**Codex said:** Epic uses "operator" persona but story uses "pipeline architect." Validation only checks presence, not quality. Demands runnable snippets while declaring doc is sole deliverable. 3.1 dependency is fragile with fallback.

**Decision:** AGREE on persona, validation, 3.1 dependency. PARTIALLY AGREE on snippets.

**Reasoning:**
- *Persona:* Epic explicitly says "As the operator" — story must match.
- *Validation:* Presence-only checks (does the matrix exist?) don't verify decision quality. Quality checks (is the recommendation justified with evidence?) are more valuable.
- *Snippets:* Interface examples and code patterns in a research doc ARE useful and standard practice. But demanding "compilable Rust snippets and runnable Python code" hides implementation inside a doc. Changed to "interface examples and code patterns."
- *3.1 dependency:* Both are research stories in the same sprint. Making 3.1 a hard prerequisite is cleaner than a fragile fallback that produces provisional results requiring rework.

**Action:** Persona changed from "pipeline architect" to "operator." Task 9 completely rewritten with 8 quality-focused validation checks replacing 7 presence-only checks. Snippet requirement softened to "interface examples and code patterns." Story 3-1 changed from soft dependency with fallback to hard prerequisite with stop-and-wait.

### 5. Downstream Impact — Need Contracts Not Just Research
**Codex said:** Stories 3.3-3.5 need concrete contracts (CLI contract, checkpoint schema, artifact identity rules, determinism test protocol), not just broad research. The build-plan table is less useful than specific downstream-consumable contracts. Without settled contracts, each downstream story will invent its own interface and drift.
**Decision:** AGREE
**Reasoning:** This is the strongest observation. The research is only valuable if downstream stories can consume it as specific interface contracts. A build-plan table tells stories what to build but not what interface to build against. Adding explicit contract deliverables (batch job CLI contract, checkpoint schema, reproducibility policy, memory budget model) transforms the research from "interesting findings" to "implementation-ready specifications."
**Action:** New section #9 "Downstream Contracts" added to Task 8 research artifact structure with four explicit contracts. New anti-pattern #9 added warning against research without consumable contracts. Task 7 updated to reference "which contracts consumed" for each story. Validation test `test_downstream_contracts_consumable` added to Task 9.

### 6. Operator-Facing Section in Research Artifact
**Codex said:** Add one operator-facing section to the artifact: what guarantees the operator will later see, what divergence will be surfaced, and what failure evidence will be preserved.
**Decision:** DEFER
**Reasoning:** This is a research story consumed by downstream implementation stories (3.3-3.5). The operator-facing guarantees will be surfaced through Story 3.7 (AI Analysis Layer — evidence packs) and Story 3.9 (E2E Pipeline Proof). Adding an operator section here would blur the story's purpose as a technical research deliverable. The reproducibility contract (now added) partially addresses this concern by defining what guarantees exist.
**Action:** None. Noted for Story 3.7 and 3.9 story reviews.

---

## Changes Applied

1. **Persona:** "pipeline architect" → "operator" (matching epic definition)
2. **Story description:** Tightened from broad "research everything" to "validate and define contracts for 3.3-3.5"
3. **AC #2:** Added Reproducibility Contract deliverable resolving PRD vs Epic 3 tension (tolerance vs bit-identical)
4. **AC #3:** Fixed NFR5 context (optimization-focused) and added D3 within-stage checkpoint distinction
5. **AC #5:** Removed D15 from mandatory alignment, added explicit out-of-scope note
6. **AC #7:** Differentiated depth — detailed build plan for 3.3-3.5, dependency notes for 3.6-3.9
7. **Task 6:** Removed D15 from validation list, changed to "confirm D15 unaffected"
8. **Task 7:** Split into detailed build plan (3.3-3.5) and dependency notes (3.6-3.9)
9. **Task 8:** Output path changed to `_bmad-output/planning-artifacts/research/`. Added Reproducibility Contract (section 4), Downstream Contracts (section 9), split build plan sections (10, 11). Snippet requirement softened. D-number scope narrowed to D1-D14.
10. **Task 9:** Completely rewritten — 8 quality-focused checks replacing 7 presence-only checks
11. **Dev Notes D1:** Reframed as "validates and hardens" not "decide from scratch"
12. **Dev Notes D15:** Marked explicitly OUT OF SCOPE
13. **Dev Notes 3-1 dependency:** Changed from soft fallback to hard prerequisite
14. **Project Structure Notes:** Output path and directory updated
15. **Anti-pattern #9:** Added warning against research without consumable contracts

## Deferred Items

- **Operator-facing guarantees section:** Valid concern but belongs in Stories 3.7/3.9, not in this research story. The reproducibility contract partially addresses it.

## Verdict
VERDICT: IMPROVED
