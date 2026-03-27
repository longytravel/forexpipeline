# Story Synthesis: 2-9-e2e-pipeline-proof-strategy-definition-cost-model

**Synthesized by:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-15
**Codex Verdict:** REFINE → **Synthesis Verdict:** IMPROVED

---

## Codex Observations & Decisions

### 1. System Alignment — Scope Drift (Tasks 7-9 pull in Rust crate work)
**Codex said:** Tasks 7-9 bring in Rust crate builds, parity tests, and "ready for backtesting" checks, creating scope drift from the stated purpose of proving intent capture → spec artifact. Recommends trimming to "operator intent → locked spec → cost artifact → linked manifest."
**Decision:** DISAGREE
**Reasoning:** This is an E2E pipeline proof — its explicit purpose is "verify all artifacts connect" (story line 8). The architecture has both Python and Rust components. Tasks 7-9 verify the Rust side can consume what Python produces, which IS the integration proof doing its job. The scope boundaries section already clearly excludes evaluation/backtesting (Epic 3). Trimming Rust integration out would defeat the purpose. The story tests connectivity, not computation.
**Action:** None. Tasks 7-9 remain as core acceptance criteria.

### 2. PRD Challenge — FR10 "executable code" vs spec-driven architecture
**Codex said:** FR10 says "generate executable strategy code" but architecture is spec-driven. Story should remap emphasis to FR9/11/12/20/21/58/59/61.
**Decision:** DEFER
**Reasoning:** This is a PRD wording issue, not a story issue. The story correctly follows the architecture (D10: strategies are specifications, not code). FR10's wording should be updated in the PRD itself, not worked around in individual stories. The story already references FR10 correctly in context.
**Action:** None at story level. PRD FR10 wording is a separate maintenance task.

### 3. PRD Challenge — FR22 three input modes premature
**Codex said:** FR22 is about automatic updates from live reconciliation, premature for this proof. Drop the assertion.
**Decision:** DISAGREE (partially)
**Reasoning:** The existing assertion is already well-scoped: "only `research` mode is exercised in this proof." This is a lightweight API surface check ensuring the builder's interface contract exists. However, the FR22 attribution is misleading since FR22 is about live calibration.
**Action:** Clarified the assertion as "API surface check only" and noted "FR22 deferred to Epic 4" to prevent confusion.

### 4. Architecture Challenge — D3 state machine not verified
**Codex said:** D3 requires proof to follow real stage transitions with JSON state file, but tasks never verify pipeline-state.json or gate transitions.
**Decision:** DEFER
**Reasoning:** Valid observation, but the D3 state machine orchestrator (pipeline-state.json, gate transitions, resume-after-crash) is infrastructure that may not be fully implemented until later stories. The story does test the conceptual state machine flow (dialogue → spec → review → modify → lock) through Tasks 2-5. Adding a hard requirement for pipeline-state.json verification would block on orchestrator implementation. The manifest assertions added (from observation #8) partially address this by verifying state is recorded.
**Action:** None for explicit state file verification. Manifest history assertions (added below) cover the key state tracking concern.

### 5. Architecture Challenge — Evidence packs at gates not checked
**Codex said:** Architecture expects evidence packs at gates (FR39), but story only checks summary text.
**Decision:** DEFER
**Reasoning:** Evidence packs (FR39) are a broader operator experience feature. This proof story correctly focuses on the artifacts that connect pipeline stages. Evidence pack assembly is a presentation concern that belongs in the operator experience epic or a dedicated story. The review summary check (Task 4) is sufficient for this proof.
**Action:** None. Evidence pack verification is out of scope for pipeline connectivity proof.

### 6. Architecture Challenge — Testing pyramid violation (too many E2E tests)
**Codex said:** Testing pyramid is 70/20/10, but this story expects a large cross-runtime suite.
**Decision:** DISAGREE
**Reasoning:** This IS the E2E proof story — it's supposed to be in the 10% system test bucket. The 70/20/10 ratio is across the entire codebase. Stories 2.3-2.8 each have their own unit and integration tests (70/20%). Story 2.9 exists specifically to be the system-level integration proof. Its test count is appropriate for its purpose.
**Action:** None.

### 7. Story Design — Non-testable ACs ("readable", "suitable for operator")
**Codex said:** "readable summary matching dialogue intent" and "suitable for operator who has never seen code" are not objectively testable.
**Decision:** AGREE (partially)
**Reasoning:** These are inherently subjective, but they serve as intent documentation for the developer. Making them fully machine-testable would over-specify UI details. The compromise: add concrete proxy assertions (summary must contain specific fields, must disclose defaults) while keeping the intent language.
**Action:** Added default disclosure requirement to AC #3 and Task 4.

### 8. Story Design — MA+EMA hardcoded as "correct"
**Codex said:** Dialogue says "moving average crossover" but AC2 hardcodes MA+EMA as correct. Should either specify in fixture or assert defaults are disclosed.
**Decision:** AGREE
**Reasoning:** "Moving average crossover" is ambiguous — could be SMA+SMA, SMA+EMA, etc. The system choosing specific types is a default that must be disclosed per Story 2.4's requirement. The fixture can hardcode specific types, but the review must show what was chosen.
**Action:** Added default disclosure assertion to AC #3, Task 4, and anti-pattern #11.

### 9. Story Design — Vague modification "try wider stops"
**Codex said:** "try wider stops" is too vague for a stable expected diff. Specify exact field change.
**Decision:** AGREE
**Reasoning:** An E2E proof needs deterministic, verifiable outcomes. A vague prompt creates flaky tests. Specifying `atr_multiplier: 3.0 → 4.0` makes the diff assertion precise and the test stable.
**Action:** Changed AC #4 and Task 5 to specify `atr_multiplier: 3.0 → 4.0` as the exact modification.

### 10. Downstream Impact — Missing rerun determinism check
**Codex said:** Story 1.9 required reruns to produce identical hashes, but Story 2.9 does not verify this.
**Decision:** AGREE
**Reasoning:** FR60 and FR61 explicitly require deterministic behavior and reproducibility. The pipeline proof should verify this property. Same inputs → same hashes is a fundamental contract.
**Action:** Added AC #12 (rerun determinism), added rerun test to Task 9, added test method `test_rerun_determinism_identical_hashes()`.

### 11. Downstream Impact — Weak artifact linkage (pair only)
**Codex said:** Task 9 only checks pair matching. Should include timeframe, schema version, cost-model version/hash.
**Decision:** AGREE
**Reasoning:** Downstream backtesting needs complete provenance. Pair-only matching is insufficient — a spec for H1 with a D1 dataset would be a silent error. Schema version tracking prevents fixture/contract drift.
**Action:** Expanded AC #9 and Task 9 linkage assertions to include timeframe, schema version, and cost-model version/hash.

### 12. Downstream Impact — "Canonical fixtures" fragile across schema evolution
**Codex said:** "Canonical fixtures for all subsequent epic pipeline proofs" is risky if schema evolves. Should be schema-versioned.
**Decision:** AGREE
**Reasoning:** Schemas will evolve. Fixtures that claim to be eternal canons will cause confusing test failures when contracts change. Schema-versioned fixtures scoped to Epic 2 are more honest and maintainable.
**Action:** Updated AC #11 and Task 10 to specify schema-versioned reference fixtures scoped to Epic 2.

### 13. Downstream Impact — Missing manifest history from Story 2.5
**Codex said:** Story 2.5 requires manifest to record version history, timestamps, confirmation metadata. Story 2.9 only checks config hash/lock status.
**Decision:** AGREE
**Reasoning:** The manifest is a key artifact for traceability. If Story 2.5 defines the contract (version_history, creation_timestamp, operator_confirmation_timestamp, locked, config_hash), the E2E proof must verify these fields exist.
**Action:** Added manifest field assertions to Task 9 and a dev note documenting required manifest fields.

### 14. Structured logging too vague
**Codex said:** "present and correctly formatted" is not specific enough. Should specify required events/fields/correlation IDs.
**Decision:** AGREE
**Reasoning:** Structured logging needs specific field contracts to be testable. Required fields provide a clear contract for the developer.
**Action:** Updated AC #10 and Task 9 logging assertions to specify required fields: `stage`, `strategy_id`, `timestamp`, `correlation_id`.

### 15. Add anti-patterns for hidden defaults and vague modifications
**Codex said:** Add anti-patterns forbidding hidden defaults and bypassing production orchestrator.
**Decision:** AGREE (hidden defaults), DISAGREE (orchestrator bypass — see observation #4)
**Reasoning:** Hidden defaults are a real risk in spec-driven systems. Vague modification prompts create flaky tests.
**Action:** Added anti-patterns #11 (no hidden defaults) and #12 (no vague modification prompts).

---

## Changes Applied

1. **AC #3** — Added default disclosure requirement (FR11 + Story 2.4 contract)
2. **AC #4** — Changed vague "try wider stops" to deterministic `atr_multiplier: 3.0 → 4.0`
3. **AC #9** — Expanded artifact linkage to include timeframe, schema version, cost-model version/hash
4. **AC #10** — Specified required structured log fields: stage, strategy_id, timestamp, correlation_id
5. **AC #11** — Changed "canonical fixtures for all subsequent epics" to "schema-versioned reference fixtures scoped to Epic 2"
6. **AC #12** — NEW: Rerun determinism check (FR60, FR61)
7. **Task 4** — Added default disclosure assertion
8. **Task 5** — Made modification deterministic (exact field change + exact diff assertion)
9. **Task 6** — Clarified FR22 assertion as API surface check, deferred to Epic 4
10. **Task 9** — Added timeframe/schema/cost-model linkage, manifest history fields, rerun determinism test, tightened logging fields
11. **Task 10** — Added schema version to proof manifest
12. **Anti-patterns** — Added #11 (no hidden defaults) and #12 (no vague modification prompts)
13. **Dev Notes** — Added manifest field contract from Story 2.5, updated expected test count to ~20-24

## Deferred Items

- **PRD FR10 wording:** "generate executable strategy code" should be updated to "generate executable strategy specification" to match D10 architecture. This is a PRD maintenance task, not a story-level fix.
- **D3 state machine verification:** pipeline-state.json and gate transitions should be verified once the orchestrator is implemented. Could be a separate smoke test or part of Epic 3's E2E proof.
- **Evidence pack verification (FR39):** Belongs in operator experience stories, not pipeline connectivity proof.

## Verdict
VERDICT: IMPROVED
