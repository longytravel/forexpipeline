# Review Synthesis: Story 3-6-backtest-results-artifact-storage-sqlite-ingest

## Reviews Analyzed
- BMAD: available
- Codex: unavailable

## Accepted Findings (fixes applied)

### H1 — SQLite trade_id/entry_time not cross-verified (BMAD, HIGH)
AC #11 requires consistency "across formats" (all three: Arrow, SQLite, Parquet). `_validate_consistency` only verified Arrow↔Parquet ordering, never querying SQLite for trade_id ordering or first/last entry_time.

**Fix:** Extended `_validate_consistency` to query SQLite for `SELECT trade_id, entry_time FROM trades WHERE backtest_run_id=? ORDER BY trade_id` and verify trade_id ordering + first/last entry_time match against Arrow values (with nanosecond→ISO 8601 conversion). Also added `backtest_run_id` parameter to correctly identify which run's trades to verify.

**Files:** `src/python/rust_bridge/result_processor.py` (lines 343-410)

### H2 — Unreliable checkpoint variable in error handler (BMAD, HIGH)
`checkpoint if 'checkpoint' in dir() else {}` in the except block was unreliable. If the exception fired before `checkpoint = self._load_checkpoint(...)`, `checkpoint` would be unbound.

**Fix:** Initialized `checkpoint: dict = {}` before the `try` block (line 103). Simplified error handler to just use `checkpoint` directly (always safe).

**Files:** `src/python/rust_bridge/result_processor.py` (lines 103, 232)

### M2 — validate_schema creates unnecessary SQLiteManager connection (BMAD, MEDIUM)
`_validate_schemas` opened a `SQLiteManager` just to create a `ResultIngester` to call `validate_schema()`, but `validate_schema()` never touches SQLite.

**Fix:** Added `validate_schema_static()` as a `@staticmethod` on `ResultIngester`. Updated `_validate_schemas` in `ResultProcessor` to call it directly without opening a database connection. Kept original `validate_schema()` as a thin wrapper for backward compatibility.

**Files:** `src/python/rust_bridge/result_ingester.py` (lines 243-302), `src/python/rust_bridge/result_processor.py` (lines 291-298)

### M4 — Schema validation only checks column names, not types (BMAD, MEDIUM)
`validate_schema` checked column presence but never validated types. An Arrow file with `entry_time` as `Utf8` instead of `Int64` would pass validation silently.

**Fix:** Added type validation to `validate_schema_static()` that maps TOML type strings (`int64`, `float64`, `utf8`, `uint64`, `bool`) to PyArrow types and verifies each column's actual type matches the contract.

**Files:** `src/python/rust_bridge/result_ingester.py` (lines 275-302)

### L4 — Misleading direction case docstring (BMAD, LOW)
Docstring said "direction utf8 → TEXT (already lowercase per contract)" but code correctly calls `.lower()` because Rust outputs "Long"/"Short".

**Fix:** Updated docstring to "direction utf8 → TEXT (lowercased from Rust 'Long'/'Short')".

**Files:** `src/python/rust_bridge/result_ingester.py` (line 121)

## Rejected Findings (disagreed)

### M1 — `read_all()` violates anti-pattern for large files (BMAD, MEDIUM)
**Rejected.** V1 handles ~50 trades / 80KB. Anti-pattern #5 says "for large files." The same `read_all()` pattern is used in `_validate_consistency` and `_read_metrics_summary`. Premature optimization; will be addressed in Epic 5 when optimization-scale data (5M trades) becomes relevant.

### M3 — Multiple sequential SQLiteManager connections (BMAD, MEDIUM)
**Rejected.** Each step is independently checkpointed for crash recovery. A single connection spanning all steps would mean a connection failure corrupts all steps. The current design correctly isolates database interactions per checkpoint boundary. The overhead of 3 connection opens is negligible compared to the safety benefit.

## Action Items (deferred)

- **L1 (LOW):** Story doc field name `pnl` vs `pnl_pips` — doc-only, no code impact
- **L2 (LOW):** Story doc says `lot_size` not in Arrow — doc-only, no code impact
- **L3 (LOW):** Row-by-row `_map_trade_row` access pattern — fine for V1 (~50 trades), defer columnar optimization to Epic 5

## Regression Tests Added

4 regression tests added with `@pytest.mark.regression`:

1. `test_sqlite_consistency_validates_trade_ids_and_times` — Verifies SQLite trade_id ordering matches Arrow (catches H1)
2. `test_checkpoint_variable_initialized_before_try` — Verifies error handler doesn't hit NameError (catches H2)
3. `test_validate_schema_static_no_connection` — Verifies schema validation works without SQLite connection (catches M2)
4. `test_validate_schema_type_mismatch` — Verifies wrong column types are rejected (catches M4)

## Test Results

```
1005 passed, 107 skipped in 4.59s
```

All 1005 tests pass (0 failures, 0 regressions). 107 skipped tests are platform/environment-specific (live tests, Rust binary tests).

## Verdict

All HIGH findings fixed with regression tests. Both MEDIUM accepted findings fixed. Core architecture is solid — crash-safe writes, idempotent ingestion, checkpoint/resume, and WAL mode all correctly implemented. AC #11 is now fully met with three-format cross-verification.

VERDICT: APPROVED
