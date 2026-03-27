# Story Synthesis: 3-6-backtest-results-artifact-storage-sqlite-ingest

## Codex Observations & Decisions

### 1. System Alignment — Story doesn't directly advance operator confidence
**Codex said:** Story materially helps reproducibility but barely touches operator confidence. `run_timestamp` in manifest conflicts with deterministic reruns (Story 3.9). `shutil.move()` is weaker than crash-safe. Parquet archival is over-scoped for V1.
**Decision:** AGREE (partially)
**Reasoning:** The `shutil.move()` concern is valid — it's not atomic across filesystems, violating NFR15. The manifest timestamp concern is valid but solvable by separating deterministic provenance from execution metadata rather than removing timestamps. Parquet archival is DISAGREE — D2 explicitly mandates three-format storage, Epic 3.6 AC#8 requires it, and Story 3.9 AC#4 expects it. Infrastructure stories don't need to directly serve operator confidence; this enables Story 3.7 which does.
**Action:**
- Replaced `shutil.move()` with crash-safe copy pattern (`copy2` → `.partial` → `fsync` → `os.replace()`) in Task 6
- Restructured manifest JSON into `provenance` (deterministic) and `execution` (non-deterministic) sections in Task 4
- Added performance note about crash-safe copy vs shutil.move
- Kept Parquet archival as-is (architecture-mandated)

### 2. PRD Challenge — Under-specifying provenance, over-specifying derived storage
**Codex said:** Manifest records `strategy_spec_version` and `cost_model_version` but not their hashes — FR59/FR61 only partially satisfied. SQLite copies of equity curve and metrics are over-specified for V1.
**Decision:** AGREE
**Reasoning:** The architecture DDL (`contracts/sqlite_ddl.sql`) defines only `trades` and `backtest_runs` — no `equity_curve` or `metrics` tables. Story 3.7 can read equity curves and metrics directly from Arrow IPC. SQLite is a queryable trade-level index per D2. Adding `strategy_spec_hash` and `cost_model_hash` to the manifest strengthens FR59/FR61 traceability.
**Action:**
- Added `strategy_spec_hash` and `cost_model_hash` to manifest `provenance` section
- Removed `equity_curve` and `metrics` SQLite tables from Task 2
- Simplified Task 3 to trade-log-only ingestion
- Added dev note: "Equity curves and metrics are NOT ingested into SQLite — they remain in Arrow IPC and Parquet"

### 3. Architecture Challenge — SQLite schema redefines contracts/sqlite_ddl.sql (CRITICAL)
**Codex said:** Story hardcodes a different schema from architecture: integer timestamps vs ISO 8601, entry_session/exit_session vs single session, version vs backtest_run_id, no backtest_runs table, no candidate_id. Stage model drifts with invented stages. Checkpoint design duplicates D3.
**Decision:** AGREE
**Reasoning:** This is the most impactful finding. The architecture's `contracts/sqlite_ddl.sql` is SSOT. The story was implementing a parallel schema that would create downstream migration debt. The invented pipeline stages (`result-ingestion-running`, `result-ingestion-complete`) aren't in Story 3.3's stage model. The `_processing_checkpoint.json` is acceptable as an internal implementation detail but should not be presented as a pipeline stage.
**Action:**
- Replaced entire Task 2 schema with architecture DDL (`trades` + `backtest_runs`)
- Changed `version INTEGER` → `backtest_run_id TEXT` throughout
- Changed `entry_time INTEGER` → `entry_time TEXT -- ISO 8601` per architecture
- Changed `entry_session`/`exit_session` → single `session TEXT` per architecture
- Changed `entry_spread/exit_spread` → `spread_cost` (aggregated), same for slippage
- Added `lot_size`, `candidate_id`, `FOREIGN KEY` per architecture
- Added `backtest_runs` table creation and lifecycle methods
- Added Arrow→SQLite field mapping documentation in Task 3
- Removed invented pipeline stages from Task 7; result processing now runs as internal step within `backtest-complete` → `review-pending` transition
- Clarified `_processing_checkpoint.json` as implementation detail, not pipeline state
- Updated AC#3 to reference `contracts/sqlite_ddl.sql`
- Added anti-patterns #11 (no redefining contracts/) and #12 (no inventing pipeline stages)

### 4. Story Design — Overpacked, weak ACs, fighting idempotency model
**Codex said:** Story is overpacked. AC5 "all inputs can be retrieved" and AC11 "row counts consistent" are too weak. AUTOINCREMENT + INSERT OR REPLACE fights the schema. Task 7 is state-machine work.
**Decision:** AGREE (partially)
**Reasoning:** AC5 should require hash verification, not just "retrievable." AC11 should check more than row counts — trade_id ordering and timestamp boundaries are cheap deterministic checks. The AUTOINCREMENT issue is resolved by removing equity_curve table (it was the only one using AUTOINCREMENT). Task 7 is appropriately scoped as integration wiring but shouldn't invent new stages. The story is comprehensive but manageable with the simplifications from observations 2-3.
**Action:**
- Tightened AC#5 with "immutable artifact references and hash verification" language
- Enhanced AC#11 to verify `trade_id` ordering and first/last `entry_time` in addition to row counts
- Updated AC#10 to use `backtest_run_id` instead of `strategy_id + version`
- Removed AUTOINCREMENT usage entirely (only `trades` table remains, uses natural `trade_id` PK)
- Simplified Task 7 to wire into existing stage model

### 5. Downstream Impact — Story 3.7 and Epic 5 need stable run identity
**Codex said:** Using `version` instead of `backtest_run_id` will force schema migration when optimization arrives. Missing upstream hashes hurt reconciliation.
**Decision:** AGREE
**Reasoning:** Story 3.7's interface uses `backtest_id` parameter (per Epic AC#8). The architecture DDL uses `backtest_run_id`. Using `version` folders as the relational key would conflate packaging with identity. The `backtest_run_id` from `backtest_runs` table is the correct relational key; version folders are artifact packaging.
**Action:**
- Changed relational identity from `version` to `backtest_run_id` throughout
- Added `backtest_run_id` to manifest structure
- Added `register_backtest_run()` and `complete_backtest_run()` methods to Task 3
- Added `backtest_run_id` generation format in Task 7
- Updated upstream contracts note: "Story 3.7 downstream uses `backtest_run_id` as its `backtest_id` interface parameter"
- Added integration test `test_process_backtest_runs_populated()`

## Changes Applied
- **AC#3:** Added reference to `contracts/sqlite_ddl.sql` SSOT and `backtest_run_id`
- **AC#5:** Tightened with immutable references + hash verification (strategy_spec_hash, cost_model_hash, dataset_hash, config_hash)
- **AC#10:** Changed `strategy_id + version` → `backtest_run_id`
- **AC#11:** Enhanced from row-count-only to include trade_id ordering and timestamp boundary checks
- **Task 2:** Replaced inline schema with architecture DDL (trades + backtest_runs only); removed equity_curve and metrics tables
- **Task 3:** Simplified to trade-log only; added Arrow→SQLite field mapping documentation; added backtest_runs lifecycle methods; replaced version with backtest_run_id
- **Task 4:** Added strategy_spec_hash and cost_model_hash; separated manifest into provenance (deterministic) and execution (non-deterministic) sections
- **Task 6:** Replaced `shutil.move()` with crash-safe copy+rename; updated orchestration steps for backtest_runs; added integration tests
- **Task 7:** Removed invented pipeline stages; wired as internal step within `backtest-complete` → `review-pending` transition
- **Dev Notes:** Updated D2 constraint (SQLite = trades only); updated D3 constraint (no new stages); added crash-safe publish note; added anti-patterns #11 and #12
- **Project structure:** Updated to reflect shared pipeline.db and processing checkpoint
- **Upstream contracts:** Added sqlite_ddl.sql as SSOT alongside arrow_schemas.toml

## Deferred Items
- **Architecture DDL may need updating:** The architecture's `trades` table has fewer fields than the Arrow schema (no `exit_reason`, `holding_duration_bars`, `signal_id`, `entry_price_raw`, `exit_price_raw`). If downstream queries need these fields, `contracts/sqlite_ddl.sql` should be updated in the architecture first — not in this story.
- **lot_size source:** Arrow schema doesn't include `lot_size` per trade. For V1 (single strategy, fixed lot size), this comes from config. For optimization with variable sizing, this needs to be added to the Arrow schema.
- **pnl vs pnl_pips:** Arrow schema has `pnl` (Float64). Architecture DDL has `pnl_pips`. The conversion semantics (is pnl already in pips? needs pip-value division?) should be clarified during implementation.

## Verdict
VERDICT: IMPROVED
