# PIR: Story 3-6-backtest-results-artifact-storage-sqlite-ingest — Story 3.6: Backtest Results — Artifact Storage & SQLite Ingest

## Codex Assessment Summary

No Codex PIR was available for this story. Assessment is based solely on independent source code review against story spec, PRD (FR58-FR61, NFR15), and architecture (D2, D3).

## Objective Alignment
**Rating:** STRONG

This story is one of the strongest D2 implementations in the project. Every PRD requirement maps to concrete, verified code:

- **FR58 (versioned artifacts):** `ArtifactStorage` creates `v{NNN}/backtest/` directories. Version numbers auto-increment. `should_create_new_version()` compares input hashes against the latest manifest. Fully implemented.
- **FR59 (traceable/reproducible):** `ManifestBuilder` produces `manifest.json` with a clean `provenance`/`execution` separation — deterministic inputs in `provenance`, non-deterministic metadata in `execution`. `verify_inputs_retrievable()` validates that referenced input files exist and their SHA-256 hashes match. This directly enables Story 3.9 deterministic verification.
- **FR60 (version on input change):** `should_create_new_version()` returns True when any of `config_hash`, `data_hash`, or `cost_model_hash` differs from the latest manifest (storage.py:130-134). Existing artifacts are never overwritten.
- **FR61 (deterministic behavior):** Manifests use `sort_keys=True` for deterministic JSON serialization. Provenance section is content-addressed.
- **NFR15 (crash safety):** Implemented pervasively — `crash_safe_write()` uses `.partial` -> `flush()` -> `fsync()` -> `os.replace()`. SQLite uses WAL mode + `synchronous=NORMAL`. Arrow file publishing uses the same crash-safe copy pattern. `_processing_checkpoint.json` enables resume after interruption at any sub-step.
- **D2 (three-format):** Arrow IPC (canonical) -> SQLite (queryable trade-level index) -> Parquet (zstd archival). All three layers implemented. SQLite is correctly positioned as a derived index (rebuildable from Arrow), not a source of truth.
- **AC #10 (idempotent):** `INSERT OR REPLACE` on `trade_id` PK + `clear_run_data()` before re-ingest ensures no duplicate rows.
- **AC #11 (cross-format consistency):** Post-synthesis fix validates trade counts, `trade_id` ordering, and first/last `entry_time` across all three formats (Arrow <-> SQLite <-> Parquet).

The story does NOT work against any system objective. All anti-patterns listed in the spec are properly avoided (no pandas for ingestion, no JSON for bulk data, no overwriting existing versions, no SQLite as source of truth).

## Simplification
**Rating:** STRONG

The implementation is well-decomposed into five focused modules with clear single responsibilities:

| Module | Responsibility | Lines |
|--------|---------------|-------|
| `storage.py` | Crash-safe write primitives + version directory management | ~177 |
| `sqlite_manager.py` | SQLite lifecycle (WAL, schema from DDL SSOT, close) | ~116 |
| `manifest.py` | Reproducibility manifest build/write/load/verify | ~174 |
| `parquet_archiver.py` | Arrow -> Parquet archival with crash-safe writes | ~89 |
| `result_ingester.py` | Arrow -> SQLite field mapping + batch inserts | ~351 |
| `result_processor.py` | 9-step orchestrator with checkpoint/resume | ~469 |
| `result_executor.py` | StageExecutor protocol adapter | ~138 |

No over-engineering observed:
- The checkpoint system is appropriately scoped as an internal implementation detail, not a pipeline stage (per D3).
- `read_all()` in the ingester is fine for V1 volumes (~50 trades / 80KB). The synthesis report correctly rejected the premature optimization finding.
- Multiple `SQLiteManager` connections per checkpoint boundary is correctly justified for crash isolation — the synthesis report correctly rejected the "single connection" suggestion.
- The `create_indexes()` method in SQLiteManager is technically redundant since `init_schema()` already runs the full DDL (which includes CREATE INDEX), but it's harmless and provides an explicit API for callers who need index creation independently. Not worth refactoring.

One minor simplification opportunity: `_map_trade_row()` accesses columns row-by-row via `table.column("name")[idx].as_py()`. For V1 this is fine (~50 trades). Epic 5 optimization scale (5M trades) will need columnar extraction. This was correctly deferred per synthesis.

## Forward Look
**Rating:** ADEQUATE

**Correctly set up for downstream:**
- **Story 3.7 (AI analysis):** `backtest_run_id` is properly stored and queryable. Equity curves and metrics remain in Arrow IPC (not ingested into SQLite), ready for direct mmap reads. `_read_metrics_summary()` extracts metrics into the manifest for quick access.
- **Story 3.9 (deterministic verification):** The `provenance` section cleanly separates deterministic inputs from non-deterministic `execution` metadata. Two runs with identical inputs will produce identical `provenance` sections.
- **Epic 5 (optimization):** `fold_scores` table and `candidate_id` column are forward-compatible. Schema is in `contracts/sqlite_ddl.sql` SSOT. `ingest_fold_scores()` is implemented and tested.

**Observations:**

1. **`strategy_spec_hash` excluded from version comparison.** `should_create_new_version()` (storage.py:130-134) checks `config_hash`, `data_hash`, and `cost_model_hash` but NOT `strategy_spec_hash`. If a strategy spec changes while config/data/cost model remain the same, no new version directory is created. The story spec's AC#6 only mentions "cost model or dataset changes," so this matches the spec — but it creates a subtle gap: a modified strategy running against the same data would reuse (and potentially overwrite) the previous version's directory. This is only safe if `config_hash` incorporates the strategy spec hash upstream. Future stories should verify this invariant or add `strategy_spec_hash` to the comparison.

2. **`validate_artifact()` checks existence only, not integrity.** `ResultExecutor.validate_artifact()` (result_executor.py:124-137) checks that files exist but does not verify manifest hashes or file integrity. This is the same pattern flagged in the Story 3-3 PIR: "check_preconditions() only checked artifact file existence but never validated manifest hash." The existing `ManifestBuilder.verify_inputs_retrievable()` could be wired in here. Not critical for V1 single-operator usage, but represents incomplete defense-in-depth for the resume path.

3. **Parquet consistency check is conditional.** `_validate_consistency()` (result_processor.py:399-427) only checks Parquet if `parquet_path.exists()`. In the normal flow, Parquet is always created before consistency validation (step 6 before step 7), so this is safe. But if the checkpoint resumes after SQLite ingest but before Parquet archival, the Parquet check would be silently skipped on the first validation pass. The step ordering protects against this, but it's worth noting.

## Observations for Future Stories

1. **Strategy spec hash in version comparison:** Story 3.9 or the E2E proof should add a test verifying that `config_hash` incorporates `strategy_spec_hash`, or `should_create_new_version()` should be extended to include it. Without this, a spec change could silently reuse stale artifacts.

2. **validate_artifact should verify hashes:** This is now the second story where artifact validation stops at existence checks. Consider a project-wide rule: `validate_artifact()` implementations must call `ManifestBuilder.verify_inputs_retrievable()` or equivalent.

3. **Lessons learned from synthesis were well-applied.** The synthesis process caught 2 HIGH and 2 MEDIUM issues, all of which were properly fixed with regression tests. The `checkpoint = {}` initialization before the try block and the three-format cross-verification are both clean fixes. This story demonstrates the value of the adversarial code review pipeline.

4. **Schema SSOT discipline is excellent.** `sqlite_manager.py` reads DDL from `contracts/sqlite_ddl.sql`. `result_ingester.py` validates Arrow schemas against `contracts/arrow_schemas.toml`. Both contract files are the single source of truth. This is a model for how future stories should handle cross-runtime contracts.

## Verdict

**VERDICT: ALIGNED**

Story 3.6 is one of the cleanest implementations in the project. It faithfully implements D2's three-format storage pattern (Arrow IPC canonical -> SQLite queryable -> Parquet archival) with pervasive crash safety (NFR15), proper reproducibility manifests (FR58-FR61), and checkpoint/resume for crash recovery. The synthesis process caught and fixed all significant issues. The two forward-look items (strategy_spec_hash in version comparison, validate_artifact integrity checks) are minor and don't affect V1 correctness. All 11 acceptance criteria are met with 57+ unit and integration tests providing comprehensive coverage.
