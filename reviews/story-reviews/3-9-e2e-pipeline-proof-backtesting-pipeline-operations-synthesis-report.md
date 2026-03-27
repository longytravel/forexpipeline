# Story Synthesis: 3-9-e2e-pipeline-proof-backtesting-pipeline-operations

**Synthesizer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-18
**Codex Review Verdict:** REFINE
**Synthesis Verdict:** IMPROVED

---

## Codex Observations & Decisions

### 1. Visual Evidence / FR16 Chart-First Review Not Tested
**Codex said:** Story validates JSON artifacts and status calls, not the visual review path. FR16 requires chart-first review, FR62-FR65 require MVP dashboard. Story should add minimal visual-evidence verification or stop claiming FR16.
**Decision:** PARTIALLY AGREE
**Reasoning:** FR16 requires "chart-first presentation with summary narrative" — the *data* for chart-first display is what this proof verifies (equity curve summary, trade distribution, narrative with equity curve shape description). Actual chart *rendering* is dashboard scope (FR62-FR65), which is a separate epic entirely. The evidence pack IS the chart-first data contract. However, the story should explicitly clarify this scope boundary to avoid confusion.
**Action:** Added a "Scope Clarifications" dev note section explaining that FR16 data verification is in scope but visual rendering is dashboard scope (FR62-FR65).

### 2. NFR5 Checkpoint Is Optimization-Specific, Not Backtesting
**Codex said:** PRD states NFR5 specifically for long-running optimization runs, but the story tests checkpoint/resume for backtesting.
**Decision:** AGREE
**Reasoning:** NFR5 literally says "Long-running optimization runs must checkpoint progress incrementally." The epic AC10 references both FR42 (general pipeline resume) and NFR5. FR42 is the correct requirement for general pipeline resume. NFR5 is being tested prematurely if applied to backtesting.
**Action:** Updated AC10 to reference FR42 as the primary requirement and added a clarifying note that NFR5 targets optimization; this proof tests the general pipeline resume infrastructure (FR42) that optimization will later build upon.

### 3. Architecture Mismatch: REST API vs operator_actions Direct Calls
**Codex said:** D9 says skills invoke REST API, but story calls `operator_actions.*` directly while claiming `/pipeline` E2E.
**Decision:** DISAGREE
**Reasoning:** Architecture D9's own "How skills work" diagram shows skills accessing `Pipeline state files (direct read for status)` and `Artifact files (direct read for evidence review)`. The REST API (D4) is the *dashboard-to-backend* boundary, not the *skill-to-pipeline* boundary. Story 3-8 explicitly defines `operator_actions.py` as the skill entry point. For V1 with a single operator, there IS no REST server — Claude Code skills call Python directly. Testing through REST would be testing dashboard integration, not pipeline integration.
**Action:** Added a "Scope Clarifications" dev note explaining that `operator_actions.py` IS the correct boundary for V1 skill testing. REST API testing belongs in dashboard integration tests.

### 4. Determinism Contradiction: AC9 "Same Manifest Hash" vs Task 7.4 Exclusions
**Codex said:** AC9 requires "same manifest hash" but Task 7.4 correctly excludes run_id and timestamps from comparison. This is a contradiction.
**Decision:** AGREE
**Reasoning:** This is a clear internal contradiction. The manifest contains volatile fields (run_id, created_at) that WILL differ between runs by design. AC9 must be precise about what "same" means.
**Action:** Rewrote AC9 to explicitly state "same deterministic manifest fields (dataset_hash, strategy_spec_version, cost_model_version, config_hash)" and note that volatile fields are excluded from comparison.

### 5. Artifact Naming Mismatch Across Stories 3.6, 3.7, 3.9
**Codex said:** Story 3.6 epics say `results.arrow`, `equity-curve.arrow`, `trade-log.arrow`; Story 3.7 epics say `narrative.json`; this story uses different names.
**Decision:** PARTIALLY AGREE
**Reasoning:** Codex compared against the **epic summaries** in `epics.md`, which are high-level and were written before the detailed implementation artifacts. The **implementation artifact** specs (Stories 3-6, 3-7) were subsequently written and reviewed with full contract alignment — these are the SSOT. Story 3-9 was correctly written from the implementation artifacts, not from stale epic summaries. However, the story DID contain hardcoded filenames and "likely" / "if names differ, discover" language, which is discovery work, not delivery work.
**Action:** (a) Added a "Scope Clarifications" dev note establishing implementation artifacts and `contracts/arrow_schemas.toml` as SSOT over epic summaries. (b) Rewrote Tasks 3.3 and 4.1 to read filenames from `contracts/arrow_schemas.toml` at test startup instead of hardcoding them.

### 6. Discovery Language in Tasks ("Likely Filename", "If Names Differ")
**Codex said:** Tasks with "likely filename" and "if section names differ, discover them" are discovery work, not delivery work.
**Decision:** AGREE
**Reasoning:** E2E proof tasks should reference definitive contracts, not speculate about filenames. Fixture manifests exist specifically to provide this mapping.
**Action:** Rewrote Tasks 1.4, 1.5, 3.3, and 4.1 to read filenames from fixture manifests and schema contracts rather than guessing.

### 7. Task 1.7 Mutates config/base.toml — Violates "No Implicit Drift"
**Codex said:** Modifying `config/base.toml` during test setup works against the "explicit config, no implicit drift" principle. Use a test-local overlay instead.
**Decision:** AGREE
**Reasoning:** Tests should be self-contained and not modify global configuration. This is especially important for reproducibility — if the test mutates base.toml, it creates ordering dependencies between test runs. A test-local config overlay is the correct pattern.
**Action:** Rewrote Task 1.7 to create `tests/e2e/fixtures/epic3/test_config_overlay.toml` instead of modifying `config/base.toml`. Updated "Files to create" and "Files to modify" sections accordingly.

### 8. Component-Level Assertions Should Be Trimmed
**Codex said:** Story repeats component-level acceptance detail (exact JSON field lists, SQLite schema shapes) that should be covered by 3.3/3.6/3.7 contract tests.
**Decision:** PARTIALLY AGREE
**Reasoning:** Some field-level verification IS appropriate for E2E proof — you need to verify the integration actually produced the right data shapes. But the E2E test shouldn't re-verify every field that Story 3-6/3-7 unit tests already cover. The current level is acceptable because: (a) it tells the developer exactly what to assert, and (b) the Key Integration Contracts section already exists as a reference, not as redundant spec. Trimming further would make tasks too vague to implement.
**Action:** No structural change. The schema verification tasks (4.1) were updated to read from SSOT rather than hardcoding, which naturally defers the specific field lists to the contracts.

### 9. Reject/Refine Gate Behavior Not Tested
**Codex said:** Story only tests accept-path. Should either test reject/refine or narrow the claim.
**Decision:** PARTIALLY AGREE
**Reasoning:** The E2E proof primarily validates the happy path. However, a minimal reject-path smoke test adds value without significant scope creep — it's one extra assertion. Full reject/refine flow testing belongs in Story 3-8 unit tests.
**Action:** Added Task 6.8: a single reject-path call verifying state doesn't advance and the rejection is recorded. Added note that full reject/refine coverage belongs in Story 3-8 unit tests.

### 10. Downstream Fixtures Should Be Sanitized
**Codex said:** Raw copied runtime artifacts with volatile timestamps and run IDs will force rewrites. Publish sanitized fixtures with volatile fields stripped.
**Decision:** AGREE
**Reasoning:** Downstream epics need stable contract fixtures, not snapshot-in-time runtime dumps. Volatile fields add no value for downstream testing and create false hash mismatches if schema versions change.
**Action:** Updated Task 10.1 to strip volatile fields from fixture copies, replacing them with `"<volatile>"` placeholders. Updated Task 10.2 fixture manifest to include `volatile_fields_stripped: true` flag and `contract_dependencies` mapping.

### Codex Meta-Recommendation: Split Into Multiple Proofs
**Codex said:** Overreach — happy-path E2E, deterministic regression, checkpoint recovery, log audit, and fixture publication are too much for one story. Split into separate proofs.
**Decision:** DISAGREE
**Reasoning:** This follows the established Epic 1-9 and Epic 2-9 pattern — a single E2E proof per epic that validates the full vertical slice. Splitting would fragment the proof and make it harder to verify end-to-end integration. The tasks ARE already logically grouped (happy path = T1-6, determinism = T7, resilience = T8, logging = T9, fixtures = T10). Each task group has independent pass criteria. The story is large but coherent — this is the capstone that proves all components work together.
**Action:** None. Kept as single story with distinct task groups.

---

## Changes Applied
1. **AC9** — Fixed determinism contradiction: specified deterministic manifest fields, excluded volatile fields
2. **AC10** — Corrected requirement reference from NFR5 to FR42 with clarifying note
3. **Task 1.4** — Removed discovery language, reads filenames from fixture manifest
4. **Task 1.5** — Removed "likely" and "discovery step", uses fixture manifest as SSOT
5. **Task 1.7** — Changed from config/base.toml mutation to test-local config overlay
6. **Task 3.3** — Removed hardcoded filenames, reads from arrow_schemas.toml
7. **Task 4.1** — Removed hardcoded field lists and discovery language, reads from schema TOML
8. **Task 6.8** — Added reject-path smoke test with scope note
9. **Task 10.1** — Added volatile field stripping for sanitized fixtures
10. **Task 10.2** — Added volatile_fields_stripped flag and contract_dependencies to fixture manifest
11. **Dev Notes** — Added "Scope Clarifications" section covering FR16, operator boundary, and artifact naming SSOT
12. **Project Structure** — Updated files to create/modify (added test_config_overlay.toml, removed config/base.toml from modify list)

## Deferred Items
- FR16 chart rendering verification — deferred to dashboard epic (FR62-FR65)
- Full reject/refine gate flow testing — belongs in Story 3-8 unit tests
- REST API boundary testing — deferred to dashboard integration tests
- Epic summary (epics.md) filename alignment — implementation artifacts are SSOT; epic summaries are informational

## Verdict
VERDICT: IMPROVED
