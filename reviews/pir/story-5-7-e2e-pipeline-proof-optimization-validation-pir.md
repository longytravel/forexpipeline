# PIR: Story 5-7-e2e-pipeline-proof-optimization-validation — Story 5.7: E2E Pipeline Proof — Optimization & Validation

**Reviewer:** Claude Sonnet 4.6
**Date:** 2026-03-23
**Type:** Post-Implementation Review

---

## Codex Assessment Summary

Codex rated Objective Alignment ADEQUATE, Simplification ADEQUATE, Forward Look CONCERN, Overall OBSERVE.

Key Codex observations and my verdicts:

| Observation | Agree? | Evidence |
|---|---|---|
| Reproducibility well-served; volatile-field stripping thorough | **Agree** | VOLATILE_KEYS covers timestamps, IDs, and all path fields; Arrow volatile-col stripping also present |
| Operator-confidence proof shallow for FR40 (status shows synthetic state, not real stages with timestamps/failure-reasons) | **Agree** | `test_pipeline_status_shows_stage_progression` creates a synthetic state file and asserts only that STRATEGY_ID appears in the list — it does not verify per-stage timestamps, pass/fail, or failure reasons |
| `load_evidence_pack()` allowed to return `None` without failing | **Partially disagree** | After Round 2 fixes, `test_load_evidence_pack_returns_data` was added; the API is now exercised. Returning `None` when the pack is absent is defensible for V1 (no candidates may pass hard gates in a minimal test run) |
| Epic 6 fixture assertion too thin (only top-level keys checked) | **Agree** | `test_epic6_fixture_saved` asserts `source`, `accepted_candidate_ids`, `artifact_dir`, `provenance_hashes` exist at top level, but does not assert per-candidate `rating`, `gate_outcomes`, or `artifact_refs` — AC #13 explicitly requires these |
| Manifest chain omits `cost_model_version` from enforced field list | **Agree with nuance** | The synthesis report rejected this as an executor-side concern, but the E2E proof test is the correct place to enforce what executors must emit; if they don't emit `cost_model_version`, the test should catch it, not tolerate the gap |
| Checkpoint tests prove contract, not live interrupt/resume | **Agree** | Documented known limitation in synthesis report; acceptable deferral until Rust CI available |
| Baseline loader creates synthetic data if Epic 3 absent | **Disagree (as rejected)** | Consistent with Epic 1/2/3 proof patterns; self-contained runability is a feature, not a defect |
| Operator review area over-built for value given | **Partially agree** | Four synthetic-state tests cover accept/reject/refine/status but the entire class operates without live pipeline execution, limiting their gate value |

---

## Objective Alignment

**Rating:** ADEQUATE

**What this story serves:**

- **Reproducibility (D11):** Strong. Two-run determinism comparison with `hash_manifest_deterministic`, VOLATILE_KEYS covering paths + timestamps + IDs, and Arrow IPC volatile-column stripping. The determinism proof is the most rigorous in the entire Epic 5 suite.
- **Artifact completeness (D2):** Strong. `.partial` cleanup verified, crash-safe write pattern checked, manifest chain (optimization → gauntlet → scoring) asserted for chain propagation via `optimization_run_id`.
- **Fidelity (D11):** Adequate. Hard gate application order (DSR → PBO → cost_stress) verified via `decision_trace`. Arrow IPC + JSON dual-format chain verified. D6 schema validation covers all required fields after Round 2 fixes.
- **Operator confidence (FR40):** Weak relative to PRD intent. `test_pipeline_status_shows_stage_progression` proves only that the API returns a list containing the strategy's ID — it does not assert per-stage timestamps, pass/fail status, or failure reasons that FR40 requires. The operator review tests operate entirely against synthetic state, not a live pipeline run.

**What works against an objective:**

The operator review tests (4 tests in `TestOperatorReviewFlow`) create a pipeline state file, call `get_pipeline_status`, and confirm the strategy ID appears. This confirms the API contract but does not prove that real pipeline execution produces the status data that operators need to make triage decisions. It is a hollow proof for FR40.

---

## Simplification

**Rating:** ADEQUATE

The core proof path (optimization → validation → scoring fixture chain via module-scoped fixtures) is clean and well-structured. No abstraction bloat.

Areas worth noting:

- **Baseline loader synthetic fallback:** The `load_epic3_baseline()` synthetic data path is appropriate for environment-portable testing, consistent with Epics 1-3. Not over-engineered.
- **VOLATILE_KEYS infrastructure:** Appropriately complex for the determinism proof goal. There is no simpler correct implementation.
- **Operator review test suite:** Four tests cover accept/reject/refine/status but all use synthetic state. A simpler honest shape would be one contract test documenting that full proof requires live pipeline integration. As implemented, the 4-test suite implies more coverage than it delivers. Not harmful, but slightly misleading.
- **Checkpoint class (3 tests):** Proves contract (file content, resume safety, artifact preservation) but not live interrupt/resume. The class docstring now explicitly documents this limitation (fixed in Round 4) — that's the right shape.

No major over-engineering concerns. 27 tests covering 9 concern areas is proportionate to the story scope.

---

## Forward Look

**Rating:** OBSERVE

**What is correctly set up for Epic 6:**

- `scoring_manifest.json` is the stable downstream contract anchor — correct.
- Epic 6 fixture construction derives from `scoring_manifest` candidates list, filtering by `hard_gates_passed` and `rating` — the logic is right.
- `optimization_run_id` propagation through the manifest chain is verified — chain integrity is confirmed.

**What is not tight enough for downstream:**

1. **Epic 6 fixture assertion gap:** `test_epic6_fixture_saved` asserts only top-level fixture keys (`source`, `accepted_candidate_ids`, `artifact_dir`, `provenance_hashes`). AC #13 requires the fixture to contain "candidate IDs, decisions, ratings, gate outcomes, artifact refs, and provenance hashes." The per-candidate payload (ratings, gate outcomes, artifact refs) is not asserted at fixture read time. Epic 6 stories will consume this fixture and discover the gap when they try to access per-candidate fields.

2. **Provenance field enforcement:** Task 8 states all manifests must contain `dataset_hash`, `strategy_spec_version`, `cost_model_version`, `config_hash`. The `test_manifest_chain_integrity` required_provenance list checks `dataset_hash`, `config_hash`, `strategy_spec_hash` but the synthesis report rejected `cost_model_version` as "upstream executor concern." This creates a gap: if a future executor change drops `cost_model_version` from manifests, no test will catch it until a downstream story breaks.

3. **Rust-skip fragility:** 17/27 tests skip when the Rust binary is absent. The proof's gate value is materially reduced in any environment without compiled Rust. This is documented and acceptable for V1, but Epic 6 should not assume this suite is a reliable gate if CI doesn't include Rust compilation.

4. **Operator status contract:** If Epic 6 or later epics build tooling on top of `get_pipeline_status()` output, the current proof provides no assurance about the shape of that output (timestamp fields, per-stage pass/fail structure, failure message format).

---

## Observations for Future Stories

1. **Epic 6 fixture consumption test:** The first Epic 6 story that reads `optimization_validation_proof_result.json` should assert that each accepted candidate entry contains `rating`, `gate_outcomes`, and `evidence_pack_path`. This enforces the contract that Story 5.7 constructs but doesn't fully validate.

2. **Manifest provenance enforcement pattern:** When a story spec says manifests must contain a set of fields, the E2E proof test must assert ALL of them — not a subset. "Upstream executor concern" is not a valid rejection when the whole point of the E2E proof is to enforce that upstream executors emit the required fields.

3. **Operator status depth:** Any story that adds new pipeline stages should extend `test_pipeline_status_shows_stage_progression` to verify per-stage pass/fail and failure reason fields, not just strategy ID presence. FR40 requires this depth and no current test enforces it.

4. **Avoid synthetic-only operator tests for gate stories:** A test that creates a synthetic pipeline state and calls an API proves the API exists and accepts the schema — it does not prove the pipeline produces that schema. For gate stories, document the limitation explicitly (as done for checkpoint) rather than building multiple tests around the same shallow proof.

5. **Unused import audit rule (from lessons learned):** After each story, grep test files for imported-but-uncalled APIs. Round 3 found `load_evidence_pack` imported but never called — this pattern recurs and warrants a systematic post-implementation check.

---

## Verdict

**VERDICT: OBSERVE**

Story 5.7 is aligned with system objectives. After 4 review rounds, the core proof pillars (determinism, gate ordering, artifact discipline, D6 logging, evidence pack loading) are correctly implemented and properly enforced. The story does exactly what an E2E proof story should: wire the stages together, verify the outputs exist and conform, and anchor the downstream handoff contract.

The observations — shallow operator status proof, thin per-candidate Epic 6 fixture assertions, and the Rust-skip gap — are documented limitations consistent with V1 scope. They are not misalignments: the operator-confidence gap is inherent to testing a CLI tool without simulating a full live run; the Rust gap is inherent to the environment. Both are correctly deferred.

Flag for Epic 6 authors: verify per-candidate payload shape when consuming the Epic 5 fixture, and extend the operator status test depth once live pipeline integration is available.
