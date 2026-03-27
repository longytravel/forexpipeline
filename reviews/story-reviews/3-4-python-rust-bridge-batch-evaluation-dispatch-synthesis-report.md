# Story Synthesis: 3-4-python-rust-bridge-batch-evaluation-dispatch

**Synthesizer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-17
**Codex Review Verdict:** REFINE
**Synthesis Verdict:** IMPROVED

---

## Codex Observations & Decisions

### 1. System Alignment — Scope Creep Beyond "Bridge"
**Codex said:** Story expands beyond bridge into result ingestion, manifest creation, checkpoint design, memory enforcement, and stage wiring. Recommends keeping only subprocess/Arrow/error/progress/cancel contract.
**Decision:** PARTIALLY AGREE
**Reasoning:** Memory budget passing and enforcement ARE part of the bridge contract — the Rust binary needs to accept and enforce its budget as a CLI parameter. Stage wiring (BacktestExecutor) is necessary because the bridge must integrate with the orchestrator from Story 3-3. However, Codex is right that full result ingestion and manifest creation overstep into Story 3.6's territory. I simplified ResultIngester → OutputVerifier (verify files exist + schemas match, return references — not materialized tables). Manifest creation removed from Rust entirely.
**Action:** Task 3 rewritten as OutputVerifier. Task 8 manifest removed. Task 4 updated to return path references. New "Published Outputs vs Runtime Working Files" section added.

### 2. PRD Challenge — NFR5 Scope and Dual Memory Admission
**Codex said:** NFR5 targets long-running optimization, not single backtest dispatch. Dual memory admission (Python pre-check + Rust enforcement) is over-specified. "No copying" is an implementation constraint, not a testable AC.
**Decision:** PARTIALLY AGREE
**Reasoning:** NFR5's primary target is optimization, but within-stage checkpointing for backtests is still valuable for large datasets (millions of bars). The cancellation AC (#5) is legitimate. However, I agree AC#2 ("no data copying") was untestable and AC#7 lacked observable verification. I rewrote both to be externally verifiable via log output. I kept the Python pre-check in Task 1 as a nice-to-have subtask (not an AC) and removed D3 from the AC#7 citation since D3 is pipeline orchestration, not resource management.
**Action:** AC#2 rewritten to verify mmap via startup log. AC#7 rewritten with logged allocation/batch-size. D3 removed from AC#7 citation.

### 3. Architecture Challenge — Miscited Decisions (CRITICAL)
**Codex said:** D3 labeled as "Resource Management" (actually Pipeline Orchestration). D14 labeled as "Multi-Crate Workspace" (actually Strategy Engine Shared Crate). `arrow_schemas.rs` cited as SSOT (architecture says `contracts/arrow_schemas.toml`). Manifest creation assigned to Rust (architecture places it in Python's artifact layer).
**Decision:** AGREE on all four points
**Reasoning:** Verified each claim against the architecture document:
- D3 (line 392): "Pipeline Orchestration — Sequential State Machine Per Strategy" — confirmed.
- D14 (line 937): "Strategy Engine Shared Crate" — confirmed. The story conflated workspace layout with D14.
- `contracts/arrow_schemas.toml` (lines 1371-1373): Explicitly stated as cross-runtime SSOT — confirmed.
- `src/python/artifacts/manifest.py` (line 1617): Manifest creation lives in Python's artifact layer — confirmed.
These are factual errors that would cause downstream implementation drift.
**Action:** All four references corrected throughout the story. D3 dev note rewritten. D14 references updated. Task 8 changed to validate against `contracts/arrow_schemas.toml`. Manifest creation removed from Rust. References section updated.

### 4. Story Design — Untestable ACs and Async/Sync Mismatch (CRITICAL)
**Codex said:** ACs #2, #7, #9 are not cleanly testable. Async BatchRunner vs sync StageExecutor interface mismatch. Task 9 checkpoint.json contradicts Story 3-2's contract.
**Decision:** AGREE on testability and checkpoint contract. PARTIALLY AGREE on async/sync.
**Reasoning:**
- Testability: AC#2 ("no data copying"), AC#7 ("pre-allocates within budget"), and AC#9 (deterministic but writing timestamps) were indeed not externally verifiable. Fixed all three.
- Async/sync: This is a real implementation concern but not a design flaw — `asyncio.run()` bridges it cleanly. Added a dev note rather than restructuring.
- Checkpoint: Task 9 invented `checkpoint.json` with `{last_completed_bar, partial_results_path}` while Story 3-2 defines a within-stage checkpoint contract with `{stage, progress_pct, last_completed_batch, total_batches, partial_artifact_path, checkpoint_at}`. Aligned to the upstream contract.
**Action:** AC#2, AC#7, AC#9 rewritten. Async/sync bridging note added to Task 4. Task 9 checkpoint aligned to Story 3-2 contract.

### 5. Downstream Impact — Overlap with Stories 3.5 and 3.6 (CRITICAL)
**Codex said:** Story 3.6 expects Python to process Rust outputs into D2 storage pattern, but 3.4 already pulls in result ingestion and manifest writing. If implemented as-is, 3.5/3.6 will be hollowed out or forced to refactor. Missing distinction between deterministic published artifacts and ephemeral runtime files.
**Decision:** AGREE
**Reasoning:** Verified against epics (lines 1006-1031): Story 3.6 AC#1 says "results follow the D2 artifact storage pattern: Arrow IPC (canonical) → SQLite (queryable) → Parquet (archival)". Story 3.6 AC#4 says "a manifest.json is produced". If 3.4 does full ingestion and manifest creation, 3.6 has nothing to do. The published-vs-ephemeral distinction is essential for FR18/FR61 compliance — timestamps in progress/checkpoint files must not break the reproducibility contract.
**Action:** ResultIngester → OutputVerifier (returns path references only). Manifest creation removed from Rust. New "Published Outputs vs Runtime Working Files" table added to dev notes. Test cases updated to explicitly test only deterministic files for byte-identity.

### 6. Codex Recommendation: Split Story
**Codex said:** Story is not implementation-small enough. Contains four boundaries. Recommends splitting.
**Decision:** DISAGREE
**Reasoning:** The story is large but coherent — it IS the bridge. The four boundaries (subprocess, Rust binary shell, output schema, orchestration) are all part of establishing the Python-Rust process boundary. Splitting would create half-functional intermediate states (e.g., a bridge that can dispatch but can't read results, or a binary that can run but can't report errors). The scope trimming from observations 1 and 5 (removing manifest creation, simplifying ingestion to verification) brings the story back to a reasonable size. V1 scope is further reduced by Anti-pattern #9 (stub backtester acceptable).
**Action:** None — kept as single story with trimmed scope.

### 7. Codex Recommendation: Move ResultIngester to 3.6
**Codex said:** Move ResultIngester and any SQLite-facing behavior out of 3.4 unless strictly limited to validating expected output files exist.
**Decision:** AGREE (with nuance)
**Reasoning:** The bridge needs SOME way to verify Rust succeeded — checking exit code alone is insufficient (Rust could exit 0 with missing files). Renamed to OutputVerifier and scoped to: verify files exist, validate schemas against `contracts/arrow_schemas.toml`, return path references. No table materialization, no SQLite, no manifest. This is the "strictly limited to validating expected output files exist" that Codex suggested.
**Action:** Task 3 completely rewritten. Downstream references updated.

---

## Changes Applied

1. **AC#2** — Rewrote from untestable "no data copying" to verifiable "startup log entry recording mmap file path and size"
2. **AC#7** — Added testable observation ("logs allocated MB and chosen batch size"), removed incorrect D3 citation
3. **AC#9** — Clarified deterministic scope: only `.arrow` files are byte-identical; ephemeral files excluded
4. **Task 3** — Renamed `ResultIngester` → `OutputVerifier`; returns `BacktestOutputRef` (path references), not materialized `pa.Table`s; validates against `contracts/arrow_schemas.toml`
5. **Task 4** — Updated to use `OutputVerifier`; `validate_artifact` docstring corrected (schema check, not manifest hash); async/sync bridging note added; `StageResult.manifest_ref` documented as None (Story 3.6)
6. **Task 8** — Removed `manifest.json` creation from Rust; changed SSOT from `arrow_schemas.rs` to `contracts/arrow_schemas.toml`; added build-time/startup validation note; added ephemeral `run_metadata.json` for traceability
7. **Task 9** — Checkpoint aligned to Story 3-2 within-stage contract (`contracts/pipeline_checkpoint.toml`) with required fields
8. **Task 11** — Updated test descriptions: schema validation against contracts, deterministic test ignores ephemeral files
9. **Task 12** — Updated exports list: `OutputVerifier`, `BacktestOutputRef` replace `ResultIngester`
10. **Dev Notes D3** — Corrected from "Resource Management" to "Pipeline Orchestration" with accurate description
11. **Dev Notes D2** — Added `contracts/arrow_schemas.toml` as schema SSOT
12. **Dev Notes D14** — All "multi-crate workspace" references corrected to "Strategy Engine Shared Crate" or "Rust workspace layout"
13. **New section** — "Published Outputs vs Runtime Working Files" table distinguishing deterministic, ephemeral, and artifact metadata
14. **Project Structure** — File paths updated (`output_verifier.py`), `arrow_schemas.rs` description corrected, `common/` crate description updated
15. **References** — D14 label fixed, `error_types.rs` noted as "to be created", `contracts/arrow_schemas.toml` reference added

## Deferred Items

- **Memory admission orchestrator-side logic**: Codex noted dual admission control. The Python pre-check in Task 1 stays as a subtask (not AC-level). Orchestrator-level memory admission across concurrent strategies is a Growth-phase concern (architecture D3 growth extension).
- **Story splitting**: Declined for now. If implementation reveals the story is too large for a single sprint, it can be split at the Python/Rust boundary (Tasks 1-4 vs Tasks 5-10).

## Verdict
VERDICT: IMPROVED
