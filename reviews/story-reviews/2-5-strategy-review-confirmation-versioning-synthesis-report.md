# Story Synthesis: 2-5-strategy-review-confirmation-versioning

## Codex Observations & Decisions

### 1. System Alignment — FR73 modification scope creep
**Codex said:** The NL modification flow and skill wiring is broader than minimum V1 outcome. Defer FR73 unless essential for Epic 2 proof.
**Decision:** PARTIALLY AGREE
**Reasoning:** FR73 is Growth phase in the PRD. However, the *deterministic structured modification primitives* (Task 5: `modifier.py`) are essential for versioning to function — you can't have v002 without modifications. The NL interpretation lives in the Claude Code skill, not Python. The Python code is deterministic and testable. What's Growth-scope is the full NL orchestration pipeline, not the primitives.
**Action:** Added dev note clarifying FR73 scope boundary: deterministic modifier primitives are V1, full NL orchestration is Growth. No code removed.

### 2. PRD Challenge — FR73 mapped to Epic 8 but implemented here
**Codex said:** FR73 is Growth in PRD and mapped to Epic 8, yet this story implements it. Reframe around "operator approval gate."
**Decision:** PARTIALLY AGREE
**Reasoning:** Same as #1. The modifier primitives serve versioning (FR12), not the full Growth-scope FR73 refinement loop. The story is already framed around review/confirmation/versioning — modification is the mechanism that creates versions. Removing it would leave versioning as a dead feature (only v001 ever exists).
**Action:** Added FR73 scope note to Dev Notes. No structural change to story scope.

### 3. Architecture Challenge — D9 REST vs direct Python
**Codex said:** D9 says skills use REST for mutations, but story calls Python directly. This creates rewrite debt.
**Decision:** PARTIALLY AGREE
**Reasoning:** The REST API layer doesn't exist yet. Building it for one story would be over-engineering. The story already had TODO notes. However, the temporary exception should be explicit rather than just a TODO comment. Added CLI entrypoints (`__main__.py`) as the formal contract that skills depend on — this is a cleaner migration target than ad-hoc `python -m` calls.
**Action:** Added `__main__.py` CLI dispatcher (Task 6). Strengthened D9 boundary note as "deliberate V1 temporary exception." Skills now call a defined CLI interface.

### 4. Architecture Challenge — D6 log schema mismatch
**Codex said:** Story invents `{"event": "...", "timestamp": "...", "component": "strategy"}` instead of following D6's shared schema.
**Decision:** AGREE
**Reasoning:** The story should use `get_logger()` which handles D6 formatting. The event list describes *what* to log, not *how* to format it. The original wording implied manual JSON construction.
**Action:** Updated Task 7 logging to clarify: all logging goes through `get_logger()` with `extra` kwargs. Removed manual JSON format specification.

### 5. Architecture Challenge — Manifest in strategy/versioner.py vs artifacts/manifest.py
**Codex said:** Architecture places manifest responsibility in `artifacts/manifest.py`, but story puts it in `strategy/versioner.py`.
**Decision:** PARTIALLY AGREE
**Reasoning:** The `artifacts/` shared infrastructure doesn't exist yet. Creating it for a single consumer (strategy versioning) would be premature. However, the migration path should be documented so it doesn't become forgotten tech debt.
**Action:** Added dev note documenting the V1 exception and the migration path to `artifacts/manifest.py` when other stages need manifests (Epic 3+).

### 6. Architecture Challenge — Skill filenames use hyphens, not snake_case
**Codex said:** Architecture requires `snake_case` naming but story uses `strategy-review.md` and `strategy-update.md`.
**Decision:** AGREE
**Reasoning:** Clear architecture naming convention. No reason to deviate.
**Action:** Renamed to `strategy_review.md` and `strategy_update.md` in Task 6 and Project Structure Notes.

### 7. Story Design — `current_version` ambiguity
**Codex said:** After modification, `current_version` may point to a draft. Need `latest_confirmed_version` or `pipeline_version`.
**Decision:** AGREE
**Reasoning:** This is a real downstream contract issue. Epic 3 backtesting needs to know which spec is pipeline-approved. `current_version` tracking the latest (possibly draft) version is useful, but a separate `latest_confirmed_version` pointer is essential for safe downstream consumption.
**Action:** Added `latest_confirmed_version: str | None` to `SpecificationManifest` dataclass, manifest JSON schema, confirmer flow (step 9), and downstream contract dev note. Added tests for the new field.

### 8. Story Design — Confirmation idempotency contradiction
**Codex said:** Story says "reject if already confirmed (idempotency: return existing confirmation)" — contradictory.
**Decision:** AGREE
**Reasoning:** The parenthetical contradicts the main clause. The correct semantics: re-confirming the same version is idempotent (return existing result, no side effects).
**Action:** Rewrote Task 4 step 2 to remove contradiction. Clear semantics: already confirmed → return existing `ConfirmationResult`.

### 9. Story Design — No CLI entrypoints defined
**Codex said:** Skills expect `python -m ...` entrypoints but no CLI modules are defined.
**Decision:** AGREE
**Reasoning:** Skills can't call Python without a defined entrypoint contract. The `__main__.py` dispatcher is the missing piece.
**Action:** Added `src/python/strategy/__main__.py` CLI dispatcher with `argparse` subcommands (review, confirm, modify, manifest) to Task 6.

### 10. Story Design — Review/diff artifacts not persisted
**Codex said:** Review summaries and diffs are rendered to console but not persisted. This loses the evidence trail.
**Decision:** AGREE
**Reasoning:** FR39's operator gate pattern expects persisted evidence. Transient console output doesn't satisfy audit trail requirements. Lightweight text files alongside specs are sufficient — no need for a full "evidence pack" at this stage.
**Action:** Added `save_summary_artifact()` to reviewer module (Task 2). Added `save_diff_artifact()` to versioner module (Task 3). Added AC #8 for persisted artifacts. Updated version file layout to show `reviews/` and `diffs/` directories. Added test for summary persistence.

### 11. Downstream Impact — Persisted confirmation record artifact
**Codex said:** Persist a confirmation record artifact, not just `confirmed_at` in the manifest.
**Decision:** DISAGREE
**Reasoning:** The manifest already records `confirmed_at`, `config_hash`, `spec_hash`, and `latest_confirmed_version`. The spec file itself is updated with `status: confirmed`. A separate confirmation record artifact is redundant for a one-person operator system. This is enterprise-grade audit trail thinking that the project feedback explicitly warns against.
**Action:** None.

### 12. Downstream Impact — Config traceability on every version, not just confirmed
**Codex said:** Apply config traceability to every created spec version artifact, not only confirmed ones.
**Decision:** DISAGREE
**Reasoning:** Config hash at draft creation time is meaningless. The pipeline config may change between draft creation and confirmation. The whole point of `config_hash` is to lock the pipeline infrastructure state at the moment the operator commits to using the spec. Hashing config at draft time creates a false sense of traceability.
**Action:** None.

### 13. Downstream Impact — Add defaults and cost_model_reference to review
**Codex said:** Add defaults and `cost_model_reference` to the human-readable review so the operator sees execution assumptions.
**Decision:** DEFER
**Reasoning:** Cost model is Story 2.6 scope and doesn't exist yet at Story 2.5 execution time. The reviewer can't display cost model assumptions that haven't been created. When Story 2.6 lands, the reviewer can be extended to include cost model reference in the summary.
**Action:** None now. Valid enhancement for post-2.6 integration.

## Changes Applied

1. Added `latest_confirmed_version: str | None` to `SpecificationManifest` dataclass and manifest JSON schema
2. Added `save_summary_artifact()` to reviewer module (Task 2) for persisting review evidence
3. Added `save_diff_artifact()` to versioner module (Task 3) for persisting diff evidence
4. Added AC #8 for persisted review/diff artifacts (FR39, FR58)
5. Clarified confirmation idempotency: re-confirm same version → return existing result
6. Updated confirmer (Task 4 step 9) to set `latest_confirmed_version` on confirmation
7. Added `src/python/strategy/__main__.py` CLI dispatcher with argparse subcommands (Task 6)
8. Renamed skill files to snake_case: `strategy_review.md`, `strategy_update.md`
9. Clarified logging (Task 7) uses `get_logger()` with `extra` kwargs, not manual JSON
10. Added dev notes: FR73 scope boundary, manifest migration path, downstream contract, D9 temporary exception
11. Updated version file layout to show `reviews/` and `diffs/` directories
12. Added tests: `test_manifest_latest_confirmed_version`, `test_confirm_sets_latest_confirmed_version`, `test_summary_artifact_persisted`
13. Updated Project Structure Notes with `__main__.py` and corrected skill filenames

## Deferred Items

- **Cost model in review summary:** Valid enhancement once Story 2.6 (execution cost model) is complete. Reviewer should be extended to include cost model reference and execution assumptions.
- **Manifest migration to `artifacts/manifest.py`:** When Epic 3+ stages need manifest management, refactor from `strategy/versioner.py` to shared `artifacts/manifest.py` per architecture.
- **REST API migration:** When orchestrator/API layer lands, migrate skill calls from Python CLI to REST endpoints per D9.

## Verdict
VERDICT: IMPROVED
