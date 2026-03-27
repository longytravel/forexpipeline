# Story 3-6-backtest-results-artifact-storage-sqlite-ingest: Story 3.6: Backtest Results — Artifact Storage & SQLite Ingest — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-17
**Type:** Holistic System Alignment Review

---

**1. System Alignment**  
**Assessment:** CONCERN

**Evidence:** The story clearly advances artifact persistence and reproducibility intent through D2-style storage and manifests [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L13), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L33), which aligns with PRD goals for persisted artifacts and deterministic behavior [prd](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L99), [prd](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L551). But it does not directly advance operator confidence, which in V1 comes from chart-first evidence packs and review flows [prd](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L83), [prd](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L155), [epics](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md#L1042).

**Observations:** This story materially helps reproducibility and artifact completeness. It only indirectly helps fidelity by preserving exact outputs. It barely touches operator confidence on its own. It also works against reproducibility in a few places: `run_timestamp` is baked into `manifest.json` [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L196), yet Epic 3.9 expects the same manifest hash on identical reruns [epics](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md#L1114). `shutil.move()` is specified for publishing canonical artifacts [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L241), which is weaker than the architecture’s write-flush-rename crash-safety rule [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L1256). Parquet archival inside the critical path looks over-scoped for V1; it serves storage hygiene more than the stated V1 gate.

**Recommendation:** Keep the story, but trim it to the V1-critical outcome: publish canonical Arrow artifacts, create a reproducibility manifest, and build the minimum SQLite query layer needed by Story 3.7 and the MVP dashboard. Make Parquet archival async or non-gating. Separate deterministic provenance from execution metadata so identical reruns can still prove identity.

**2. PRD Challenge**  
**Assessment:** CONCERN

**Evidence:** The relevant PRD asks for backtest outputs, deterministic reruns, coherent evidence packs, and versioned stage artifacts [prd](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L481), [prd](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L517), [prd](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L551). The story maps mostly to FR58-FR61, but narrows “input changes” to config/data/cost model in implementation tasks [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L76), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L238).

**Observations:** The PRD is right that artifacts and traceability matter. The story is under-specifying the actual provenance needed: it records `dataset_hash` and `config_hash`, but not `strategy_spec_hash` or `cost_model_hash` in the manifest example [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L193). That means FR59/FR61 are only partially satisfied. It is also over-specifying derived storage shape: PRD requires queryability for dashboard/review, not necessarily SQLite copies of equity curve and metrics. That extra duplication looks imagined rather than operator-driven for V1.

**Recommendation:** Reframe the requirement as: “Every backtest run publishes a stable run artifact set with immutable upstream hashes/IDs and a minimal query index.” Explicitly include strategy spec hash and cost model hash in FR59/FR60 traceability for this story. Defer nonessential derived tables unless a downstream query actually needs them.

**3. Architecture Challenge**  
**Assessment:** CRITICAL

**Evidence:** The architecture says cross-runtime schema lives in `contracts/` as SSOT [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L1151), and the canonical SQLite DDL shown there uses `trades` plus `backtest_runs`, with ISO 8601 text times and a single `session` field [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L1418), [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L1421), [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L1197). The story hardcodes a different schema: integer timestamps, `entry_session`/`exit_session`, `equity_curve`, `metrics`, and no `backtest_run_id` [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L92), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L119), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L132).

**Observations:** This is the biggest issue in the story. It is not implementing the architecture; it is redefining it. The stage model also drifts: Story 3.3 defines Epic 3 stages ending at `backtest-complete -> review-pending -> reviewed` [epics](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md#L928), while Story 3.6 invents `result-ingestion-running` and `result-ingestion-complete` [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L261). The checkpoint design adds `_processing_checkpoint.json` micro-state [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L249) even though D3 already centralizes stage state and says within-stage checkpointing is handled deliberately [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L401).

**Recommendation:** Make the story consume `contracts/sqlite_ddl.sql`, not redefine SQL inline. Align timestamp formats, session fields, and run identifiers to the architecture. Either update Story 3.3’s stage model first or keep ingestion internal to `backtest-complete` rather than adding undocumented pipeline states.

**4. Story Design**  
**Assessment:** CONCERN

**Evidence:** The acceptance criteria are mostly concrete, but some are not fully verifiable as written: “all inputs can be retrieved” [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L36) and “row counts are consistent across all three formats” [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L66). The task list is broad, spanning storage, schema, ingestion, manifesting, archival, orchestration, state-machine integration, and fixtures [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L71).

**Observations:** The story is implementable, but it is overpacked. Task 7 is really pipeline-state-machine work, not storage work. AC11 is too weak for fidelity; row counts can match while timestamps, ordering, or values diverge. The anti-patterns are useful, but they miss the real failure mode here: contract drift from architecture. The use of `AUTOINCREMENT` plus `INSERT OR REPLACE` plus “clear version data” is a sign the idempotency model is fighting the schema rather than using a stable natural key.

**Recommendation:** Tighten AC5 to require immutable upstream artifact references and hash verification. Replace AC11 with content-level checks for deterministic fields, not just counts. Split or trim the story boundary: keep storage/manifest/ingest here, move stage-model changes out, and define a stable `backtest_run_id`-based idempotency contract.

**5. Downstream Impact**  
**Assessment:** CONCERN

**Evidence:** Story 3.7 depends on SQLite plus Arrow IPC for analysis and evidence packs [epics](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md#L1042). The architecture’s SQLite contract already anticipates run-level identity and later candidate-level evolution through `backtest_run_id` and `candidate_id` [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L1424), [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L1435). The story omits both and substitutes `version` everywhere [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md#L96).

**Observations:** Downstream, Story 3.7 and later Epic 5 will want stable run identity, not just per-strategy version folders. Using `version` instead of `backtest_run_id` is likely to force a schema migration once optimization and candidate comparison arrive. Missing upstream hashes in manifests will also hurt reconciliation and re-run attribution later. If this story ships as written, later epics will either code against an ad hoc schema or rewrite storage once the real query model appears.

**Recommendation:** Add a stable run identifier now, align the SQLite layer to that run model, and treat version folders as artifact packaging, not the relational primary key. Publish exactly what Story 3.7 and the dashboard need: canonical Arrow paths, immutable provenance, query-safe trade rows, and predictable run metadata.

## Overall Verdict
VERDICT: REFINE

## Recommended Changes
1. Replace the inline SQLite schema in the story with a requirement to implement `contracts/sqlite_ddl.sql` as the SSOT, and update the story to match its field names, time format, and run identifiers.
2. Add `strategy_spec_hash` and `cost_model_hash` to the manifest and to version-change detection; do not rely on version strings alone.
3. Remove `run_timestamp` from any deterministic hash comparison path, or split the manifest into deterministic provenance plus non-deterministic execution metadata.
4. Replace `shutil.move()` publishing with a crash-safe copy/write-rename publish step so canonical artifacts obey NFR15.
5. Change the relational identity model from `strategy_id + version` to a stable `backtest_run_id`, with version folders remaining a packaging concern.
6. Rework AC11 to validate content integrity, ordering, and timestamp normalization across Arrow, SQLite, and Parquet, not just row counts.
7. Either delete Task 7’s new pipeline stages or update Story 3.3 and Epic 3’s stage model first so the state machine remains coherent.
8. Simplify V1 scope by making Parquet archival non-gating or asynchronous unless a concrete downstream story requires it immediately.
9. Tighten AC5 so “inputs can be retrieved” means immutable path or artifact ID plus hash verification for every upstream dependency.
10. Revisit whether SQLite really needs `equity_curve` and `metrics` tables in V1; if not, keep those canonical in Arrow/manifest and only ingest the minimum query layer needed for Story 3.7 and the MVP dashboard.
