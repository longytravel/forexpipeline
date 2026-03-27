# Code Review: Story 2-1 — ClaudeBackTester Strategy Evaluator Review

**Reviewer:** Claude Opus 4.6 (Adversarial Code Review)
**Date:** 2026-03-15
**Story File:** `_bmad-output/implementation-artifacts/2-1-claudebacktester-strategy-evaluator-review.md`
**Story Type:** Research (documentation deliverable only, no production code)
**Deliverable:** `_bmad-output/planning-artifacts/research/strategy-evaluator-baseline-review.md`

---

## Git vs Story Discrepancies

**Git repository not detected** in Forex Pipeline project. File change claims in the story's File List cannot be cross-referenced against git. The research artifact file was confirmed to exist at the claimed path via filesystem glob.

- Files claimed in story File List: 2 (1 new, 1 modified)
- Git discrepancies: N/A (no git repository)

---

## Findings Summary

**Issues Found:** 0 Critical, 0 High, 2 Medium, 2 Low

---

## MEDIUM Issues

### M1: AC3 "Explicit Unknowns" Requirement — Partially Met

**Severity:** MEDIUM
**File:** `_bmad-output/planning-artifacts/research/strategy-evaluator-baseline-review.md` — Section 6
**AC Reference:** AC #3

AC3 requires the authoring workflow document to describe the workflow "as evidenced by code, config files, and repo documentation — **listing explicit unknowns where repo evidence is insufficient for operator follow-up**."

Section 6 thoroughly documents the workflow, pain points (5 items: high barrier, encoding complexity, dual-language sync, no validation, no versioning), and what worked well. However, there is no visible "Explicit Unknowns" subsection or statement. The AC specifically asks for unknowns to be listed — things that could NOT be determined from code alone and require operator clarification.

**Expected behavior:** Either a dedicated "Unknowns" subsection listing items that require operator follow-up (e.g., "How frequently are new strategies created?", "Are there undocumented strategies outside the repo?", "What's the typical iteration cycle?"), OR an explicit statement that no unknowns were identified (all workflow aspects were determinable from source code evidence).

### M2: Completion Notes Verdict Count Arithmetic Error

**Severity:** MEDIUM
**File:** `_bmad-output/implementation-artifacts/2-1-claudebacktester-strategy-evaluator-review.md:298`

Task 7 completion note states: "**10 components assessed: 2 Keep (metrics, verification), 7 Adapt (indicators, signal gen, filters, exits, sizing, optimization metadata), 1 Replace (strategy loading/parsing), 1 Build New (cost modeling).**"

The parenthetical for "Adapt" lists **6** components (indicators, signal gen, filters, exits, sizing, optimization metadata) but the count says **7 Adapt**. Additionally, 2 + 7 + 1 + 1 = 11, but the note claims 10 components. The actual verdict table in Section 3 of the research artifact shows: 2 Keep + 6 Adapt + 1 Replace + 1 Build New = 10, which is internally consistent. The error is only in the completion notes text, not the research artifact itself.

**Expected behavior:** Completion notes should state "6 Adapt" to match both the parenthetical listing and the Section 3 verdict table.

---

## LOW Issues

### L1: No Git Repository for Change Provenance

**Severity:** LOW
**Context:** Project-level configuration

The Forex Pipeline project is not a git repository. This means:
- File change claims in the Dev Agent Record File List cannot be audited via git
- No commit hash to pin the review to a reproducible state of the Forex Pipeline project
- The baseline ClaudeBackTester repo IS pinned (commit `2084beb` on `master` branch), which is the important traceability — but the output artifact's provenance within Forex Pipeline is unauditable

**Note:** This is a project infrastructure issue, not a story implementation issue.

### L2: Story AC1 Assumption Disproven by Findings (Informational)

**Severity:** LOW (informational — not a defect)
**File:** `_bmad-output/implementation-artifacts/2-1-claudebacktester-strategy-evaluator-review.md:15-17`

AC1 states: "the **Rust** evaluator modules are reviewed (indicator implementations, strategy logic, signal generation, filter chains, exit rules)." The review correctly discovered that the evaluator is **Python-first** — indicators, strategy logic, signal generation, and filter chains are all Python. Only the trade simulation hot loop is Rust.

This is actually a strength of the review — it caught a foundational assumption error in the story itself. The review still covered all components and produced the required verdict table. However, the story's AC text now reads as factually incorrect with respect to its own findings. Future references to this story should note that "Rust evaluator" was the hypothesis; "Python evaluator with Rust acceleration layer" was the finding.

---

## Acceptance Criteria Scorecard

| AC | Description | Status | Evidence |
|---|---|---|---|
| **AC1** | Component verdict table with keep/adapt/replace per component, rationale citing source files | **Fully Met** | Section 3: 10 components assessed with Baseline Location (specific files), Status, Verdict, Rationale, Effort, Notes |
| **AC2** | Indicator catalogue with canonical name, param signatures, computation logic, I/O types, warm-up, price sources, dependencies | **Fully Met** | Section 5: 12 indicators catalogued (SMA, EMA, True Range, ATR, RSI, MACD, Bollinger, Stochastic, ADX, Donchian, rolling_max, rolling_min) with all required fields in standardized tables |
| **AC3** | Strategy authoring workflow documented with pain points, what worked, explicit unknowns | **Partially Met** | Section 6: Workflow (create 6 steps, modify 4 steps), 5 pain points, what-worked-well section present. **Missing:** Explicit unknowns subsection or "no unknowns" declaration (see M1) |
| **AC4** | Strategy representation format documented — definition, storage, loading | **Fully Met** | Section 7: Documents code-based-only format (Python classes), checkpoint JSON as only persisted representation, no declarative format, no schema validation |
| **AC5** | Capabilities NOT covered by D10/FR9-FR13 documented | **Fully Met** | Section 8.1: 8 baseline capabilities not in D10 (sub-bar resolution, stale exit, partial close, breakeven, max bars, MAP-Elites, parameter widening, Hidden Smash Day) with recommendations |
| **AC6** | Baseline patterns improving system objectives flagged with recommendation | **Fully Met** | Section 8.3: Three-layer model assessment; Section 9: Precompute pattern proposed for adoption with system objective justification (operator confidence, artifact completeness) |
| **AC7** | Proposed Architecture Updates section if findings warrant | **Fully Met** | Section 9: 4 proposed updates (D14 phased Rust migration, D10 exit type extensions, sub-bar resolution, precompute pattern) with specific change descriptions and system objective rationale. Architecture.md NOT modified directly (correct per Anti-Pattern #2) |
| **AC8** | Baseline repo path, branch, commit hash recorded | **Fully Met** | Baseline Traceability header: `C:\Users\ROG\Projects\ClaudeBackTester`, branch `master`, commit `2084beb0683547de3efa1702f49319d30938b851`, date 2026-03-15 |
| **AC9** | Fidelity risks documented with severity and mitigation | **Fully Met** | Appendix B: Determinism verification table (5 components verified) + Fidelity risks table (6 risks with severity Low/Medium and mitigation notes including EMA floating-point, M1 resolution, spread data quality, Python/Rust parity drift) |
| **AC10** | Cost model presence/absence and D13 compatibility documented | **Fully Met** | Appendix C: Current cost logic table (6 locations documented), D13 compatibility assessment (no session-aware modeling), integration path recommendation |

**Summary:** 9 of 10 ACs Fully Met, 1 Partially Met (AC3)

---

## Task Completion Audit

| Task | Marked | Actually Done? | Evidence |
|---|---|---|---|
| Task 1: Access and inventory | [x] | Yes | Section 2 module inventory, baseline traceability header |
| Task 2: Catalogue indicators | [x] | Yes | Section 5 with 12 indicators, all required fields |
| Task 3: Review strategy logic | [x] | Yes | Sections 3-4, Appendix B fidelity assessment |
| Task 4: Document authoring workflow | [x] | Partial | Section 6 has workflow + pain points; missing explicit unknowns (AC3) |
| Task 5: Document representation format | [x] | Yes | Section 7 documents code-based format, checkpoint JSON |
| Task 6: Gap analysis | [x] | Yes | Section 8 with 8.1 (baseline extras), 8.2 (gaps to build), 8.3 (three-layer), 8.4 (Phase 0) |
| Task 7: Component verdict table | [x] | Yes | Section 3 with 10 components, all required columns |
| Task 8: Write research artifact | [x] | Yes | 9-section structure + 4 appendices, proposed architecture updates in Section 9 |

---

## Anti-Pattern Compliance

| Anti-Pattern | Compliant? | Notes |
|---|---|---|
| #1: No code written | Yes | Only documentation files in File List |
| #2: Architecture.md not modified | Yes | Changes proposed in Section 9 only |
| #3: Indicator catalogue not skipped | Yes | Full catalogue in Section 5 |
| #4: No "keep as-is" assumptions | Yes | 2 Keep, 6 Adapt, 1 Replace, 1 Build New — each justified |
| #5: Authoring pain points documented | Yes | Section 6 with 5 pain points |
| #6: Cost model documented | Yes | Appendix C with D13 compatibility |
| #7: Deep analysis, not superficial | Yes | Computation logic, parameter signatures, source code references |
| #8: Quality assessed, not just presence | Yes | Verdicts assess Architecture compliance and adaptation needs |
| #9: Baseline not treated as authority | Yes | Section 9 proposes D14 structural revision based on evidence |
| #10: No format selection made | Yes | Format questions deferred to Story 2.2 |

---

## Overall Assessment

This is a **strong research story execution**. The research artifact is comprehensive (9 sections + 4 appendices), deeply technical (computation logic documented, not just function signatures), and architecturally aware (4 proposed updates with system objective justification).

The critical finding — that the baseline is Python-first with a Rust acceleration layer, not a Rust-crate architecture as D14 assumed — is well-documented and the proposed phased migration path is pragmatic.

The only substantive gap is the missing "explicit unknowns" in the authoring workflow (AC3), which is a documentation completeness issue, not a content quality issue.

**Recommendation:** Address M1 (add unknowns subsection to Section 6) and M2 (fix count in completion notes), then mark as done.
