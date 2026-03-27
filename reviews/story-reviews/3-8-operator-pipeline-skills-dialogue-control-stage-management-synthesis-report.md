# Story Synthesis: 3-8-operator-pipeline-skills-dialogue-control-stage-management

**Synthesizer:** Claude Opus 4.6
**Date:** 2026-03-18
**Codex Reviewer:** GPT-5.4

---

## Codex Observations & Decisions

### 1. System Alignment — "all strategies" scan premature, CLI text reduces review quality
**Codex said:** Story drifts beyond V1 by scanning "all strategies" before cross-strategy registry exists. Reduces review to CLI text even though MVP requires chart-led visual review.
**Decision:** DISAGREE (scan) / DEFER (chart-led review)
**Reasoning:** V1 has one strategy — scanning `artifacts/` for state files is simple filesystem discovery, not a registry. It works identically for 1 or N strategies and introduces zero complexity. The cross-strategy registry is a growth-phase coordination layer (shared risk state, resource budget), which is unrelated to discovering state files. On chart-led review: the dashboard is Epic 4. Story 3.8 is the final Epic 3 story. CLI evidence pack presentation IS the MVP review interface until the dashboard exists. The evidence pack already includes `equity_curve_full_path` and `trade_log_path` for future dashboard deep links.
**Action:** None for scan. Added `evidence_pack_ref` to status returns for future dashboard linkage.

### 2. PRD Challenge — Over-specifies implementation, under-specifies operator outcomes
**Codex said:** Over-specifies menu numbering and direct Python snippets. Under-specifies lineage, visual evidence, and explicit input refs. `run_backtest()` loads "latest from artifacts" which is weak against FR59-FR61.
**Decision:** PARTIALLY AGREE
**Reasoning:** Menu numbering is useful implementation guidance for the dev agent, not harmful. But Codex is right that `run_backtest()` should use state-driven input refs, not implicit "latest from artifacts" discovery. This is a real reproducibility gap. The status output should also surface `last_outcome`, `blocking_reason`, and `evidence_pack_ref` to satisfy FR40 properly.
**Action:** Updated `run_backtest()` to read strategy spec/dataset from `PipelineState` (state-driven). Added `run_id`, `config_hash`, `last_outcome`, `blocking_reason`, `evidence_pack_ref` to return dicts. Extended status display fields.

### 3. Architecture Challenge — Story bans REST API, architecture requires it (CRITICAL)
**Codex said:** Architecture D9 says skills use REST API for mutations. This story bans REST and invokes Python directly. Creates duplicate control path.
**Decision:** DISAGREE
**Reasoning:** Codex reads D9 too literally without considering implementation sequencing. The architecture's own implementation sequence (line 2135) puts REST API as step 9 and Claude Code skills as step 11. But the epic breakdown puts skills in Epic 3 (this story) and REST API in Epic 4. REST doesn't exist yet when Story 3.8 is implemented. `operator_actions.py` IS the structured mutation surface — REST will be a thin wrapper around it. This is not a "duplicate control path"; it's the layered implementation order: build the logic layer first, add the HTTP wrapper later. The "no REST API" anti-pattern is correctly scoped to "not yet in this story", not "never."
**Action:** Added dev note clarifying `operator_actions.py` as the future REST backing layer. Updated AC#8 to explicitly state this is the single mutation surface designed for REST wrapping.

### 4. Story Design — Missing refine path, unsafe "latest" evidence, artifact name mismatch, weak FR41 test
**Codex said:** Prompts accept/reject/refine but only implements accept/reject. "Latest version on disk" is unsafe. Artifact name inconsistent with Epic 3.7 (`narrative.json` vs `evidence_pack.json`). Grep FR41 test is a weak proxy.
**Decision:** AGREE (refine, latest, FR41 test) / DISAGREE (artifact name)
**Reasoning:**
- **Refine:** `GateDecision` already supports `decision="refine"` but no `refine_stage()` function existed. Added full refine path with new AC#6, Task 1.7, skill operation 14, and test 4.13.
- **Latest evidence:** Codex is right — evidence must be state-driven for reproducibility. Changed `load_evidence_pack()` to accept explicit `evidence_pack_ref` from pipeline state, with fallback to latest for first-run only. Added dev note on state-driven lookup order.
- **Artifact name:** Codex references the epic AC which says `narrative.json`, but the synthesized Story 3-7 implementation (the SSOT) uses `evidence_pack.json`. The story is correct; the epic AC is outdated. No change needed.
- **FR41 test:** Grep is useful as defense-in-depth but insufficient alone. Added behavioral tests: `test_advance_allows_losing_strategy` (negative P&L) and `test_advance_allows_zero_trades_strategy`. These prove the system actually works, not just that it lacks certain strings.
**Action:** Added AC#6 for refine flow. Added `refine_stage()` function (Task 1.7). Added state-driven evidence lookup with fallback. Added 5 new tests (4.11-4.15). Added "State-Driven Evidence Lookup" dev note section.

### 5. Downstream Impact — Missing run_id/config_hash in returns, no dashboard deep links
**Codex said:** Story 3.9 needs manifest-linked, reproducible runs. Missing `run_id`/`config_hash`/artifact refs in operator actions. No dashboard deep links.
**Decision:** AGREE (lineage fields) / DEFER (dashboard links)
**Reasoning:** `run_id` and `config_hash` are already in `PipelineState` but weren't surfaced in `run_backtest()` or `get_pipeline_status()` return dicts. This is a gap — downstream consumers need these for lineage without re-parsing state files. Dashboard deep links are Epic 4 scope; the evidence pack's `metadata` dict already has a slot for them.
**Action:** Added `run_id` and `config_hash` to `run_backtest()` return, `get_pipeline_status()` return, and logging schema. Deferred dashboard deep links.

### Codex Recommendations — Individual Disposition

| # | Recommendation | Decision | Reasoning |
|---|---|---|---|
| 1 | Replace "no REST API" rule | DISAGREE | REST is Epic 4. `operator_actions.py` IS the mutation surface. Added dev note. |
| 2 | Remove single `/pipeline` menu requirement | DISAGREE | Deliberate UX consolidation for single operator. Architecture's separate skills table is a suggestion, not mandate. |
| 3 | Explicit input refs for `run_backtest()` | AGREE | Updated to state-driven refs, not artifact scanning. |
| 4 | State-driven evidence loading | AGREE | Added `evidence_pack_ref` parameter and lookup order. |
| 5 | Full refine support end-to-end | AGREE | Added AC#6, Task 1.7, skill operation 14, test 4.13. |
| 6 | Align evidence-pack artifact contract | DISAGREE | Story already uses `evidence_pack.json` matching synthesized Story 3-7. Epic AC is outdated. |
| 7 | Expand status with last_outcome, blocking_reason | AGREE | Added to `get_pipeline_status()` return dict and skill status display. |
| 8 | Dashboard/chart references in review flow | DEFER | Dashboard is Epic 4. Evidence pack metadata has slots for future URLs. |
| 9 | Behavioral FR41 tests | AGREE | Added tests 4.11 and 4.12 alongside existing grep test. |
| 10 | Integration tests for full flow | PARTIALLY AGREE | Added behavioral tests and state-ref test (4.14). Full integration tests require REST API (Epic 4). |

## Changes Applied

### Acceptance Criteria
- Inserted new AC#6: refine path with `GateDecision(decision="refine")`, strategy returns to `STRATEGY_READY`
- Renumbered ACs 6-9 → 7-10
- Updated AC#8 (was #7): clarified `operator_actions.py` as single mutation surface, future REST backing
- Updated AC#9 (was #8): added "refines" to profitability-gate enforcement list
- Updated AC#10 (was #9): added `run_id` and `config_hash` to log schema

### Task 1 (operator_actions.py)
- Updated AC ref from `#1,#2,#3,#4,#5,#6,#8,#9` to `#1,#2,#3,#4,#5,#6,#7,#9,#10`
- Task 1.2: Changed from "loads from artifacts/" to "reads from PipelineState (state-driven)"; added `run_id`, `config_hash` to return dict
- Task 1.3: Added `config_hash`, `last_outcome`, `blocking_reason`, `evidence_pack_ref` to return dict
- Task 1.4: Added `evidence_pack_ref` parameter with state-driven lookup order and fallback
- NEW Task 1.7: `refine_stage()` function — creates `GateDecision(decision="refine")`, returns strategy to `STRATEGY_READY`
- Renumbered 1.7→1.8, 1.8→1.9

### Task 2 (skill extensions)
- Updated AC ref to include #8
- Task 2.1: Expanded menu from 10-14 to 10-15 (added "Refine Stage" as operation 14)
- Task 2.3: Added last_outcome, blocking_reason, evidence_pack_ref to status display
- Task 2.6: Simplified reject description (removed "suggests re-run" — that's refine's job)
- NEW Task 2.7: "Refine Stage" skill section (operation 14)
- Renumbered 2.7→2.8, 2.8→2.9, 2.9→2.10
- Task 2.9: Updated chaining to distinguish reject (hard stop) from refine (re-submit loop)

### Task 3 (logging)
- Updated AC ref from #9 to #10
- Task 3.2: Added `"refine"` to action types; added `run_id` and `config_hash` to log schema

### Task 4 (tests)
- Updated AC ref to include #7
- NEW 4.11: `test_advance_allows_losing_strategy` (behavioral FR41)
- NEW 4.12: `test_advance_allows_zero_trades_strategy` (behavioral FR41)
- NEW 4.13: `test_refine_stage_creates_refine_gate_decision`
- NEW 4.14: `test_load_evidence_pack_uses_state_ref_when_provided`
- Renumbered 4.11→4.15 (log schema test) with enhanced verification of `run_id`/`config_hash`

### Dev Notes
- Added "Future REST Integration" architecture constraint explaining `operator_actions.py` as the API contract surface
- Added "State-Driven Evidence Lookup" section with explicit lookup order (state ref → fallback to latest)

## Deferred Items

- **Dashboard deep links in evidence pack:** Valid concern, but dashboard is Epic 4. Evidence pack `metadata` dict already supports future URL fields. Will be addressed when dashboard is built.
- **Chart-led visual review:** MVP review is CLI evidence pack until Epic 4 dashboard. The evidence pack's `equity_curve_full_path` and `trade_log_path` fields are designed for dashboard consumption.
- **Full integration tests with REST API surface:** Requires REST API (Epic 4). Behavioral and unit tests cover the `operator_actions.py` surface for now.

## Verdict

VERDICT: IMPROVED

The story was already well-structured with correct integration contracts. The synthesis added 6 meaningful improvements: (1) full refine path end-to-end, (2) state-driven evidence lookup for reproducibility, (3) explicit lineage fields (`run_id`, `config_hash`) in all returns and logs, (4) richer status output satisfying FR40, (5) behavioral FR41 tests alongside existing static analysis, and (6) clarity that `operator_actions.py` is the future REST API backing layer. Codex's CRITICAL rating on the REST API point was overruled — the architecture's implementation sequence supports the layered approach, and the story now explicitly documents this design intent.
