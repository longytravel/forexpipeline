# Story Synthesis: 2-6-execution-cost-model-session-aware-artifact

## Codex Observations & Decisions

### 1. Session boundary mismatch with architecture
**Codex said:** Architecture defines London 08:00-16:00, NY 13:00-21:00, overlap 13:00-16:00. Story hardcodes different partition: London 08:00-12:00, overlap 12:00-16:00, NY 16:00-21:00.
**Decision:** AGREE
**Reasoning:** This is a critical contract mismatch. The architecture (lines 152-181) is authoritative. The story's non-overlapping partition had wrong boundaries — London-only hours should be 08:00-13:00 (not 08:00-12:00), overlap should be 13:00-16:00 (not 12:00-16:00). Additionally, the story lacked clarity on HOW overlapping config sessions resolve to a single label per bar.
**Action:** Fixed session boundaries in Task 3 to match architecture. Added priority resolution documentation (overlap > specific > off_hours). Added dev note in Session Architecture Integration explaining the resolution logic. Added test `test_get_session_overlap_priority`.

### 2. Missing provenance fields in manifest (config_hash, artifact_hash, input_hash)
**Codex said:** Architecture requires config hash in every artifact manifest (D7, line 518). Story lacks config_hash, artifact_hash, and input_hash.
**Decision:** AGREE
**Reasoning:** D7 explicitly says "Config hash embedded in every artifact manifest — reproducibility is verifiable." Story 2.5 already includes config_hash and spec_hash in its manifest entries. Cost model manifests should follow the same pattern. Artifact hash enables integrity verification; input hash enables idempotency awareness.
**Action:** Added config_hash, artifact_hash, and input_hash to manifest version entries in Task 5 storage module. Added new AC #10 requiring these fields. Added test `test_manifest_contains_hashes`.

### 3. Missing approved-version pointer (latest_approved_version)
**Codex said:** Story 2.5 has `latest_confirmed_version` for downstream consumers. Cost model manifest lacks an equivalent, meaning downstream stages would guess which version to load.
**Decision:** AGREE
**Reasoning:** Story 2.5 line 265 is explicit: "Downstream consumers MUST read `latest_confirmed_version` from the manifest to identify the pipeline-approved spec. Never use `current_version` as the pipeline input pointer." The same principle applies to cost models. Without this, Story 2.7 and 2.9 would load raw "latest file" which could be unreviewed.
**Action:** Added `approve_version()` function and `latest_approved_version` pointer to storage module. Added AC #9 requiring this. Updated downstream consumer notes. Added anti-pattern #18. Added tests `test_manifest_latest_approved_version` and `test_approve_version`. Updated Task 6 to auto-approve v001 as baseline.

### 4. Versioning semantics — idempotency for unchanged inputs
**Codex said:** AC4 versions every new artifact. FR60 says versioning should track input changes, not repeated identical runs. New version should only be created when inputs change.
**Decision:** PARTIAL AGREE
**Reasoning:** Valid concern for preventing version proliferation. However, for V1 with manual research-based creation, full idempotency enforcement (refusing to create) is over-engineering. A warning-based approach is proportionate: log a warning when input_hash matches the latest version, but don't block creation.
**Action:** Added anti-pattern #17 warning about unchanged-input version creation. Added input_hash to manifest entries (enables detection). Did NOT add hard blocking — operator may have valid reasons to re-version.

### 5. Split source into build_mode and provenance metadata
**Codex said:** Don't let "research/tick_analysis/live_calibration" stand in for source attribution. Split into build_mode and actual provenance.
**Decision:** DISAGREE
**Reasoning:** Over-engineering for V1. The `source` enum adequately captures build mode. The `metadata` section already supports free-form provenance detail (description, data_points, confidence_level). Splitting into two separate concepts adds schema complexity without V1 benefit. When live calibration arrives in Epic 7, the existing metadata section can carry broker/account provenance.
**Action:** None.

### 6. Operator-readable evidence artifact
**Codex said:** Add a separate operator-readable evidence artifact summarizing session values, data sources, sample sizes, and research-derived assumptions.
**Decision:** DISAGREE
**Reasoning:** The JSON artifact itself IS human-readable evidence for V1. It contains source, calibrated_at, all session values, and metadata with description/confidence_level. The CLI `show` command renders it for operator review. FR39 (evidence packs) is about strategy validation evidence, not cost model evidence. A separate markdown evidence artifact is scope creep for a one-person operator who can read JSON and use `show`.
**Action:** None.

### 7. Clarify V1 consumer semantics for mean/std values
**Codex said:** Define how the Rust consumer must use mean_spread_pips/std_spread/mean_slippage_pips/std_slippage in V1. Is it deterministic mean-only or stochastic sampling?
**Decision:** AGREE
**Reasoning:** Excellent observation. The story defines the schema fields but never specifies how Story 2.7's Rust consumer interprets them. For V1 deterministic backtesting, this must be explicit. Stochastic sampling would require seed management and would complicate reproducibility proofs in Story 2.9.
**Action:** Added explicit V1 consumer semantics in Downstream Consumers section: V1 uses mean values only (deterministic). std values are stored for future stochastic sampling but NOT consumed in V1 backtesting.

### 8. Remove fallback for missing Story 2.2 research
**Codex said:** Remove the fallback that treats missing Story 2.2 research as acceptable, or mark it explicitly as temporary fixture.
**Decision:** DISAGREE
**Reasoning:** The hardcoded defaults ARE reasonable research-based values (typical ECN broker conditions for EURUSD). They're already marked with `confidence_level: "research_estimate"` in metadata. Story 2.2 is dedicated deep research; Story 2.6 provides sensible baseline defaults. This is pragmatic, not sloppy. The pipeline proof (Story 2.9) needs a cost model to exist — blocking on Story 2.2 completion would serialize unnecessarily.
**Action:** None. The existing design is correct.

### 9. De-scope automated analysis and broad CLI
**Codex said:** Split or de-scope tick analysis mode and broad CLI from core schema/default-artifact work.
**Decision:** DISAGREE
**Reasoning:** The tick analysis mode is ONE method in the builder — minimal scope. The CLI is 6 standard argparse commands. This is not over-engineered. The `from_tick_data` method provides genuine value: computing spread distributions from existing Dukascopy data. Splitting this into a separate story would create unnecessary coordination overhead for what amounts to ~50 lines of code.
**Action:** None for de-scoping. Did clarify pyarrow dependency (already a project dependency from Epic 1, not a new dependency).

### 10. Align persistence with shared artifact infrastructure
**Codex said:** Use shared artifact infrastructure already emerging in the repo instead of introducing another local manifest/storage pattern.
**Decision:** DISAGREE
**Reasoning:** The story already follows the Story 2.5 manifest pattern (version entries with status, timestamps, hashes). Codex references `data_manifest.py` as existing infrastructure, but that's data-pipeline-specific (tracking download/validation state), not a generic artifact manifest system. The cost model storage module follows the SAME architectural pattern as Story 2.5. A unified cross-pipeline artifact storage system is premature for V1 — it should emerge naturally when patterns stabilize (Epic 3+), as Story 2.5 dev notes explicitly state.
**Action:** None.

### 11. Slippage in tick analysis is research-estimated, not empirical
**Codex said:** Story overclaims "tick data analysis" while dev notes admit slippage cannot be inferred from bar data.
**Decision:** AGREE
**Reasoning:** Valid — the tick analysis mode genuinely computes spread distributions but estimates slippage from research. The artifact should make this distinction explicit so consumers know which values are empirical vs. estimated.
**Action:** Added note in Tick Data Analysis Mode section requiring artifact metadata to indicate which values are empirical vs. research-estimated (e.g., `"slippage_source": "research_estimate"`).

### 12. Pyarrow dependency conflict with "no new deps" constraint
**Codex said:** Story bans new deps but tick analysis requires Parquet reading.
**Decision:** AGREE
**Reasoning:** Valid catch. pyarrow is already a project dependency from Epic 1 data pipeline — it's not a NEW dependency. The anti-pattern was too broadly stated.
**Action:** Clarified anti-pattern #15 to note the exception for `from_tick_data` using pyarrow. Added dependency note in Tick Data Analysis Mode section.

## Changes Applied
1. **Fixed session boundaries** in Task 3 to match architecture (london 08:00-13:00, overlap 13:00-16:00, new_york 16:00-21:00)
2. **Added session overlap priority resolution** documentation in Task 3 and Session Architecture Integration dev note
3. **Added AC #9** — `latest_approved_version` pointer in manifest for downstream consumers
4. **Added AC #10** — manifest version entries must contain config_hash, artifact_hash, input_hash
5. **Added `approve_version()` function** and `latest_approved_version` pointer to Task 5 storage module
6. **Updated Task 6** to auto-approve v001 and include hashes in manifest
7. **Added V1 consumer semantics** in Downstream Consumers: mean-only (deterministic), std stored for future use
8. **Updated Story 2.9 consumer note** to use `latest_approved_version` from manifest
9. **Added anti-patterns #16, #17, #18** — session divergence, unchanged-input versioning awareness, raw-latest loading
10. **Clarified anti-pattern #15** — pyarrow exception for tick analysis
11. **Added tick analysis transparency** — metadata must indicate empirical vs. research-estimated values
12. **Added 4 new tests** — overlap priority, manifest hashes, approve_version, latest_approved_version

## Deferred Items
- Unified cross-pipeline artifact storage system — should emerge when patterns stabilize (Epic 3+), per Story 2.5 dev notes
- Broker/account provenance fields — relevant when live calibration arrives (Epic 7)
- Stochastic cost sampling with seed management — future enhancement beyond V1
- Full idempotency enforcement (refusing to create duplicate versions) — monitoring via input_hash warnings is sufficient for V1

## Verdict
VERDICT: IMPROVED
