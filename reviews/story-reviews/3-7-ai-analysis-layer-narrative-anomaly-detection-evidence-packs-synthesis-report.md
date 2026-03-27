# Story Synthesis: 3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs

## Codex Observations & Decisions

### 1. Remove `sensitivity_cliff` from Story 3.7
**Codex said:** Parameter sensitivity cliff depends on optimization data and is already marked "skip gracefully if unavailable" — overreach for backtest-stage MVP.
**Decision:** AGREE
**Reasoning:** The optimization_candidates table won't exist at backtest stage. Having a checker that always skips is dead code. However, keeping the enum value and function signature enables forward compatibility without rework.
**Action:** Changed `_check_sensitivity_cliff` to an explicit STUB that always returns `None` with a debug log. Added dev note that real implementation is deferred to Epic 5. Updated test from `test_sensitivity_cliff_skipped_without_optimization_data` to `test_sensitivity_cliff_stub_returns_none`.

### 2. Replace full `equity_curve_data` with bounded/downsampled summary
**Codex said:** Architecture sizes equity curves at ~125 MB Arrow IPC. Serializing full curve into JSON contradicts the "NO unbounded memory" anti-pattern.
**Decision:** AGREE
**Reasoning:** This is a genuine memory/disk concern. A 5.26M-point equity curve as JSON would be hundreds of MB. The operator needs shape, not every data point. Downsampled to 500 points preserves visual fidelity for review while keeping the JSON under 100KB.
**Action:** Replaced `equity_curve_data` with `equity_curve_summary` (max 500 downsampled points) + `equity_curve_full_path` reference to canonical Arrow IPC. Updated AC6 to specify downsampled. Added LTTB/stride sampling guidance in Task 4. Updated JSON example. Added test `test_evidence_pack_equity_curve_downsampled`.

### 3. Fix artifact filename/path contracts to match Story 3.6
**Codex said:** Story references `equity_curve.arrow` and `trades.arrow` but Story 3.6 established `equity-curve.arrow` and `trade-log.arrow` (hyphenated).
**Decision:** AGREE
**Reasoning:** Clear contract drift bug. Story 3.6 is SSOT for artifact filenames.
**Action:** Fixed all references: `equity_curve.arrow` → `equity-curve.arrow`, `trades.arrow` → `trade-log.arrow`. Added test `test_evidence_pack_artifact_filenames` to catch future drift.

### 4. Add explicit provenance fields to ACs and models
**Codex said:** Evidence pack lacks manifest path, config hash, data hash, strategy spec version, cost model version, schema version for provenance.
**Decision:** PARTIALLY AGREE
**Reasoning:** Provenance is important but most of these fields already exist in the Story 3.6 manifest. Duplicating all hashes creates a second source of truth. Better approach: reference the manifest by path and add a schema_version for the evidence pack format itself.
**Action:** Added `manifest_path` and `schema_version` to EvidencePack metadata. Updated AC5 to mention manifest reference. Did NOT duplicate all hash fields — the manifest is the provenance SSOT.

### 5. Change failure semantics for missing evidence packs
**Codex said:** Letting `review-pending` exist without a reviewable artifact breaks the operator gate pattern.
**Decision:** PARTIALLY AGREE
**Reasoning:** Valid concern — a silent missing evidence pack could confuse the operator. However, blocking the pipeline transition contradicts the non-blocking design principle (FR41, anti-pattern #4). Compromise: set a metadata flag so Story 3.8 can surface the missing pack to the operator, who then decides.
**Action:** Updated Task 5 to set `evidence_pack_available: false` in pipeline state metadata on failure, enabling Story 3.8 to warn the operator. Pipeline still transitions — operator maintains full control.

### 6. Rewrite AC6 into measurable criteria
**Codex said:** "Enough information to decide" is vague and untestable.
**Decision:** AGREE
**Reasoning:** AC6 as written couldn't be verified by automated tests. Specifying the required fields makes it testable while preserving the intent.
**Action:** Rewrote AC6 to enumerate ALL required fields: narrative overview, key metrics table (specific metrics named), anomaly flags, downsampled equity curve summary, trade distribution by session, and trade log reference path.

### 7. Demote AC8 from acceptance criteria to dev notes
**Codex said:** AC8 (Python module structure with specific interfaces) is an implementation shape, not user-facing acceptance.
**Decision:** AGREE
**Reasoning:** The operator doesn't care about module structure — they care about results. AC8 is verified via code review, not acceptance testing. The information is already well-covered in Tasks 1-4.
**Action:** Removed AC8 from acceptance criteria. Added equivalent content as "AC8 Implementation Note" in Dev Notes section.

### 8. Add a single shared metrics builder
**Codex said:** `NarrativeResult.metrics` and `EvidencePack.metrics` duplicate the same concept and can drift if computed independently.
**Decision:** AGREE
**Reasoning:** Two independent metric computations is a guaranteed source of inconsistency. Single computation shared by both consumers is the correct pattern.
**Action:** Added `metrics_builder.py` with `compute_metrics()` function to Task 1. Updated Task 2 (narrative) and Task 4 (evidence pack) to call this shared function. Added `test_metrics_builder.py` with 4 tests including `test_narrative_and_pack_use_same_metrics`.

### 9. Specify how `v{NNN}` is resolved from `backtest_id`
**Codex said:** The story uses `v{NNN}` paths but doesn't explain how version is resolved.
**Decision:** AGREE
**Reasoning:** Story 3.6 already defines `resolve_version_dir()` — no need to reinvent. The version should come from pipeline state or Story 3.6's resolver.
**Action:** Added "Version Resolution" dev note section explicitly referencing Story 3.6's `resolve_version_dir()` and pipeline state as the two valid sources.

### 10. Move anomaly thresholds to versioned config
**Codex said:** Thresholds in Markdown prose are architecturally weak for reproducibility.
**Decision:** PARTIALLY AGREE
**Reasoning:** Fully extracting to `contracts/anomaly_thresholds.toml` is valid but adds scope. Pragmatic approach: define thresholds as a config dict in code that can be overridden by config_loader, enabling future extraction without code changes.
**Action:** Added dev note requiring thresholds be loaded from a `ANOMALY_THRESHOLDS` config dict (not hardcoded in checker functions). Added test `test_thresholds_loaded_from_config`. Deferred TOML extraction to when config_loader is fully mature.

### 11. Add chart/recommendation fields per D11
**Codex said:** D11 specifies "chart URLs (dashboard deep links), recommendation (proceed/caution/reject)" but the story doesn't include these.
**Decision:** DISAGREE
**Reasoning:** Dashboard is Epic 4 scope — no URLs exist yet. Adding placeholder chart URL fields is premature. The recommendation field (proceed/caution/reject) sounds useful but risks becoming a soft gate that contradicts FR41 (no blocking on profitability). The operator makes the decision; the system provides evidence. Story 3.8 will handle presenting the decision prompt.
**Action:** None. Chart URLs will be added when the dashboard exists (Epic 4). Recommendation logic is the operator's job per FR41.

### 12. Update planning artifacts for `evidence_pack.json`
**Codex said:** The filename change from `narrative.json` to `evidence_pack.json` should propagate to planning artifacts, not just story notes.
**Decision:** DEFER
**Reasoning:** Valid concern but planning artifact updates are the PM agent's responsibility. The existing dev note about the filename decision (already in the story) is the correct mechanism to flag this for upstream propagation. Editing epics.md from a story synthesis is out of scope.
**Action:** None at story level. The existing "Artifact Filename Decision" dev note already flags this for Story 3.8. PM should propagate to epics during sprint planning.

## Changes Applied
- AC5: Added `manifest_path` reference for provenance
- AC6: Rewritten from vague "enough information" to explicit required field list with downsampled equity curve
- AC7: Unchanged (already correct)
- AC8: Removed from ACs, demoted to Dev Notes section
- Task 1: Added `metrics_builder.py` with shared `compute_metrics()` function
- Task 1: Updated EvidencePack model with `equity_curve_summary` + `equity_curve_full_path` replacing `equity_curve_data`
- Task 2: Updated to use shared `compute_metrics()` instead of independent computation
- Task 3: Changed `_check_sensitivity_cliff` to explicit STUB with debug log
- Task 3: Added `test_thresholds_loaded_from_config` test
- Task 4: Added equity curve downsampling (max 500 points via LTTB/stride)
- Task 4: Fixed artifact filenames to `equity-curve.arrow` and `trade-log.arrow` (matching Story 3.6)
- Task 4: Updated to call shared `compute_metrics()` instead of building metrics dict independently
- Task 4: Added `manifest_path` and `schema_version` to metadata
- Task 5: Updated failure semantics to set `evidence_pack_available: false` flag in pipeline state
- Task 6: Added `test_metrics_builder.py` with 4 tests
- Task 6: Updated evidence pack tests: added downsampling test, artifact filename test, manifest/schema fields
- Task 6: Updated sensitivity cliff test name and added thresholds config test
- Dev Notes: Added "Threshold config dict" guidance (overridable, not hardcoded)
- Dev Notes: Added "Version Resolution" section referencing Story 3.6's resolver
- Dev Notes: Added "AC8 Implementation Note" (demoted from AC)
- Dev Notes: Updated Arrow IPC reads note with equity curve sizing context
- Project Structure: Added `metrics_builder.py` and `test_metrics_builder.py`
- JSON examples: Updated to reflect downsampled curve, correct filenames, provenance metadata

## Deferred Items
- TOML extraction of anomaly thresholds (`contracts/anomaly_thresholds.toml`) — deferred until config_loader is mature
- Planning artifact propagation of `evidence_pack.json` filename — PM responsibility during sprint planning
- Dashboard chart URLs in evidence pack — deferred to Epic 4 when dashboard exists
- Recommendation field (proceed/caution/reject) — operator's decision per FR41, not system's

## Verdict
VERDICT: IMPROVED
