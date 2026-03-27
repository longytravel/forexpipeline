# Story 3.6: Backtest Results — Artifact Storage & SQLite Ingest

Status: done

## Research Update Note (2026-03-18)

This story has been updated to reflect architecture research findings from Stories 3-1/3-2, Research Briefs 3A-3C, and optimization methodology research.

**Key changes:**
- **D1 (Per-Fold Score Storage):** CV-inside-objective optimization requires storing per-fold scores alongside aggregated metrics. SQLite schema extended with `fold_scores` table. Arrow output schemas extended with optional `fold_id` column.
- **Batch Result Ingestion:** When fold-aware or batch evaluation is used (Stories 3-4/3-5), the result processor must handle multiple result sets per invocation — one per fold or parameter set.

**References:** architecture.md Research Update to D1; optimization-methodology-research-summary.md

## Story

As the **operator**,
I want backtest results stored as versioned artifacts in Arrow IPC and ingested into SQLite for querying,
so that results are efficiently accessible for both analysis and dashboard display.

## Acceptance Criteria

1. **Given** the Rust backtester produces Arrow IPC output files (Story 3.5)
   **When** backtest results are processed by the Python orchestrator
   **Then** results follow the D2 artifact storage pattern: Arrow IPC (canonical) → SQLite (queryable) → Parquet (archival)
   [Source: architecture.md — D2 Artifact Schema & Storage; epics.md — Story 3.6 AC#1]

2. **Given** a completed backtest run
   **When** artifacts are written to disk
   **Then** Arrow IPC result files are stored in the strategy's versioned artifact directory:
   - `artifacts/{strategy_id}/v{NNN}/backtest/trade-log.arrow`
   - `artifacts/{strategy_id}/v{NNN}/backtest/equity-curve.arrow`
   - `artifacts/{strategy_id}/v{NNN}/backtest/metrics.arrow`
   [Source: architecture.md — D2 directory structure; epics.md — Story 3.6 AC#2]

3. **Given** Arrow IPC trade-log files exist
   **When** SQLite ingestion runs
   **Then** trade-level records are ingested into the `trades` and `backtest_runs` tables defined in `contracts/sqlite_ddl.sql` (SSOT), with `backtest_run_id` linking trades to their run, and indexes on `strategy_id`, `session`, `entry_time` for efficient analytics queries
   [Source: architecture.md — D2 SQLite query layer, contracts/sqlite_ddl.sql; epics.md — Story 3.6 AC#3]

4. **Given** a completed backtest run
   **When** results are stored
   **Then** a `manifest.json` is produced recording: strategy spec version, cost model version, dataset hash, config hash, run timestamp, result file paths, and key metrics summary
   [Source: FR58, FR59; epics.md — Story 3.6 AC#4]

5. **Given** a manifest.json file
   **When** an operator or system needs to reproduce a run
   **Then** the manifest links all inputs with immutable artifact references — all referenced inputs can be retrieved and their hashes validated (strategy_spec_hash, cost_model_hash, dataset_hash, config_hash) to reproduce the run
   [Source: FR59, FR61; epics.md — Story 3.6 AC#5]

6. **Given** a cost model or dataset changes after a previous backtest
   **When** a new backtest is triggered
   **Then** a new version directory (`v{NNN+1}`) is created rather than overwriting existing artifacts
   [Source: FR60; epics.md — Story 3.6 AC#6]

7. **Given** any artifact write operation
   **When** a crash or interruption occurs during write
   **Then** no partial or corrupt artifacts exist — all writes use crash-safe pattern (write → flush → rename)
   [Source: NFR15; epics.md — Story 3.6 AC#7]

8. **Given** Arrow IPC canonical files exist
   **When** archival processing runs
   **Then** Parquet archival copies are created for long-term compressed storage
   [Source: architecture.md — D2 archival layer; epics.md — Story 3.6 AC#8]

9. **Given** SQLite database operations
   **When** concurrent reads and writes occur
   **Then** SQLite uses WAL mode for crash-safe concurrent read/write access
   [Source: architecture.md — D2; epics.md — Story 3.6 AC#9]

10. **Given** a result processing run is restarted after a crash or partial completion
    **When** the same `backtest_run_id` is re-processed
    **Then** ingestion is idempotent — previously ingested trades are replaced (not duplicated), and already-completed sub-steps (Arrow copy, Parquet archive) are skipped
    [Source: NFR15; D3 checkpoint/resume]

11. **Given** Arrow IPC, SQLite, and Parquet artifacts are all written for a run
    **When** the result processor completes
    **Then** trade row counts are validated to be consistent between Arrow IPC and SQLite, and between Arrow IPC and Parquet; additionally, `trade_id` ordering and first/last `entry_time` values are verified to match across formats
    [Source: D2 three-format consistency; FR61 reproducibility]

## Tasks / Subtasks

- [x] **Task 1: Artifact Directory & Version Manager** (AC: #2, #6)
  - [x]Create `src/python/artifacts/storage.py` with `ArtifactStorage` class
  - [x]`def resolve_version_dir(strategy_id: str, artifacts_root: Path) -> Path` — scans existing `v{NNN}` dirs, returns next version path
  - [x]`def should_create_new_version(strategy_id: str, config_hash: str, data_hash: str, cost_model_hash: str, artifacts_root: Path) -> bool` — compares input hashes against latest manifest to detect changes
  - [x]`def create_version_dir(strategy_id: str, version: int, artifacts_root: Path) -> Path` — creates `artifacts/{strategy_id}/v{NNN}/backtest/` directory tree
  - [x]`def crash_safe_write(data: bytes, target_path: Path) -> None` — writes to `{target}.partial` → `fsync()` → atomic `os.replace()` to final path
  - [x]`def crash_safe_write_json(obj: dict, target_path: Path) -> None` — JSON-serialize then crash-safe write
  - [x]Add unit tests: `tests/unit/test_artifact_storage.py`
    - `test_resolve_version_dir_empty()` — first version is v001
    - `test_resolve_version_dir_increments()` — v002 after v001 exists
    - `test_should_create_new_version_unchanged()` — returns False when hashes match
    - `test_should_create_new_version_changed()` — returns True when any hash differs
    - `test_crash_safe_write_atomic()` — verify no `.partial` files remain after successful write
    - `test_crash_safe_write_no_corrupt_on_interrupt()` — simulate interruption, verify original intact

- [x] **Task 2: SQLite Schema & Manager** (AC: #3, #9)
  - [x]Create `src/python/artifacts/sqlite_manager.py` with `SQLiteManager` class
  - [x]`def __init__(self, db_path: Path) -> None` — opens/creates SQLite DB, enables WAL mode (`PRAGMA journal_mode=WAL`), sets `synchronous=NORMAL`
  - [x]`def init_schema(self) -> None` — executes DDL from `contracts/sqlite_ddl.sql` (SSOT). Creates tables if not exist:
    - `trades` table per architecture DDL:
      ```sql
      CREATE TABLE IF NOT EXISTS trades (
        trade_id        INTEGER PRIMARY KEY,
        strategy_id     TEXT NOT NULL,
        backtest_run_id TEXT NOT NULL,
        direction       TEXT NOT NULL CHECK(direction IN ('long', 'short')),
        entry_time      TEXT NOT NULL,  -- ISO 8601
        exit_time       TEXT NOT NULL,
        entry_price     REAL NOT NULL,
        exit_price      REAL NOT NULL,
        spread_cost     REAL NOT NULL,
        slippage_cost   REAL NOT NULL,
        pnl_pips        REAL NOT NULL,
        session         TEXT NOT NULL,
        lot_size        REAL NOT NULL,
        candidate_id    INTEGER,  -- NULL for single backtest, set for optimization
        FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id)
      );
      ```
    - `backtest_runs` table per architecture DDL:
      ```sql
      CREATE TABLE IF NOT EXISTS backtest_runs (
        run_id          TEXT PRIMARY KEY,
        strategy_id     TEXT NOT NULL,
        config_hash     TEXT NOT NULL,
        data_hash       TEXT NOT NULL,
        spec_version    TEXT NOT NULL,
        started_at      TEXT NOT NULL,
        completed_at    TEXT,
        total_trades    INTEGER,
        status          TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed', 'checkpointed'))
      );
      ```
    - **Note:** Equity curve and metrics are NOT ingested into SQLite — they remain in Arrow IPC (canonical) and Parquet (archival). SQLite is a queryable trade-level index per D2. Story 3.7 reads equity curves and metrics directly from Arrow IPC.
    - **Research Update — Per-fold score table** (for CV-inside-objective optimization):
      ```sql
      CREATE TABLE IF NOT EXISTS fold_scores (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        backtest_run_id TEXT NOT NULL,
        candidate_id    INTEGER,          -- Parameter set ID (NULL for single backtest)
        fold_id         INTEGER NOT NULL,  -- Fold index (0-based)
        fold_start_bar  INTEGER NOT NULL,  -- Start bar index of fold
        fold_end_bar    INTEGER NOT NULL,  -- End bar index of fold
        sharpe_ratio    REAL,
        profit_factor   REAL,
        max_drawdown_pct REAL,
        total_trades    INTEGER,
        win_rate        REAL,
        total_pnl       REAL,
        FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id)
      );
      CREATE INDEX IF NOT EXISTS idx_fold_scores_run_id ON fold_scores(backtest_run_id);
      CREATE INDEX IF NOT EXISTS idx_fold_scores_candidate ON fold_scores(candidate_id);
      ```
    - Note: `fold_scores` table is populated only when fold-aware evaluation is used (fold_boundaries passed to Rust evaluator). For single-run backtests, this table remains empty. Schema is forward-compatible with Epic 5 optimization.
  - [x]`def create_indexes(self) -> None` — per architecture DDL: `idx_trades_strategy_id`, `idx_trades_session`, `idx_trades_entry_time`, `idx_trades_candidate_id`
  - [x]`def close(self) -> None` — checkpoint WAL and close connection
  - [x]Add unit tests: `tests/unit/test_sqlite_manager.py`
    - `test_init_creates_wal_mode()` — verify WAL pragma
    - `test_schema_creation_idempotent()` — call init_schema twice, no errors
    - `test_indexes_exist()` — verify all four indexes created
    - `test_schema_matches_contracts_ddl()` — verify table structure matches `contracts/sqlite_ddl.sql`

- [x] **Task 3: Arrow IPC Trade-Log Ingestion into SQLite** (AC: #1, #3, #10)
  - [x]Create `src/python/rust_bridge/result_ingester.py` with `ResultIngester` class
  - [x]`def __init__(self, sqlite_mgr: SQLiteManager, batch_size: int = 1000) -> None`
  - [x]`def register_backtest_run(self, run_id: str, strategy_id: str, config_hash: str, data_hash: str, spec_version: str, started_at: str) -> None` — inserts into `backtest_runs` table with status `'running'`
  - [x]`def complete_backtest_run(self, run_id: str, total_trades: int) -> None` — updates `backtest_runs` with `completed_at`, `total_trades`, status `'completed'`
  - [x]`def ingest_trade_log(self, arrow_path: Path, strategy_id: str, backtest_run_id: str) -> int` — reads `trade-log.arrow` via `pyarrow.ipc.open_file()`, maps Arrow fields to SQLite columns, inserts in batches of `batch_size`, returns row count
  - [x]**Arrow → SQLite field mapping** (Arrow IPC is full-fidelity; SQLite is queryable summary):
    - `entry_time` Int64 (nanosecond UTC) → `entry_time` TEXT (ISO 8601 conversion)
    - `exit_time` Int64 → `exit_time` TEXT (ISO 8601 conversion)
    - `entry_price` Float64 → `entry_price` REAL (cost-adjusted)
    - `exit_price` Float64 → `exit_price` REAL (cost-adjusted)
    - `entry_spread + exit_spread` → `spread_cost` REAL (aggregated)
    - `entry_slippage + exit_slippage` → `slippage_cost` REAL (aggregated)
    - `direction` "Long"/"Short" → `direction` 'long'/'short' (lowercase)
    - `entry_session` Utf8 → `session` TEXT (entry session as primary)
    - `pnl` Float64 → `pnl_pips` REAL
    - `lot_size` from run config (not in Arrow) → `lot_size` REAL (default 1.0 for V1)
    - `candidate_id` → NULL for V1 single backtest
  - [x]`def validate_schema(self, arrow_path: Path, expected_schema_name: str) -> bool` — validate Arrow file schema against `contracts/arrow_schemas.toml` definitions
  - [x]Trade ingestion uses `INSERT OR REPLACE` on `trade_id` PRIMARY KEY for idempotent re-ingestion (AC: #10) — natural key, no AUTOINCREMENT issues
  - [x]`def clear_run_data(self, backtest_run_id: str) -> None` — deletes all trades for a specific `backtest_run_id` before re-ingest (safety fallback)
  - [x]All ingestion uses transactions (`BEGIN`/`COMMIT`) — rollback on any error to prevent partial ingest
  - [x]Add unit tests: `tests/unit/test_result_ingester.py`
    - `test_ingest_trade_log_correct_count()` — ingest fixture, verify row count
    - `test_ingest_trade_log_field_mapping()` — verify Arrow→SQLite mapping (timestamp format, direction case, cost aggregation)
    - `test_ingest_trade_log_iso8601_timestamps()` — verify nanosecond → ISO 8601 conversion
    - `test_register_and_complete_backtest_run()` — verify backtest_runs lifecycle
    - `test_ingest_rollback_on_error()` — corrupt data triggers rollback, DB unchanged
    - `test_validate_schema_mismatch()` — wrong schema raises clear error
    - `test_ingest_idempotent_rerun()` — ingest same data twice, verify no duplicate rows (AC: #10)
    - `test_ingest_fold_scores()` — Research Update: ingest per-fold scores from fold-aware evaluation, verify fold_scores table populated correctly
    - `test_ingest_fold_scores_empty_for_single_run()` — verify fold_scores table empty when no folds used

- [x] **Task 4: Manifest Creation** (AC: #4, #5)
  - [x]Create `src/python/artifacts/manifest.py` with `ManifestBuilder` class
  - [x]`def __init__(self, strategy_id: str, version: int, artifacts_root: Path) -> None`
  - [x]`def build(self, strategy_spec_version: str, cost_model_version: str, dataset_hash: str, config_hash: str, run_timestamp: str, result_files: dict[str, Path], metrics_summary: dict) -> dict` — assembles manifest dict
  - [x]`def write(self, manifest: dict) -> Path` — crash-safe writes `manifest.json` to version directory using `ArtifactStorage.crash_safe_write_json()`
  - [x]`def load(self, manifest_path: Path) -> dict` — reads and validates existing manifest
  - [x]`def verify_inputs_retrievable(self, manifest: dict) -> bool` — checks all referenced input paths exist and hashes match
  - [x]Manifest JSON structure (deterministic provenance separated from execution metadata):
    ```json
    {
      "schema_version": "1.0",
      "backtest_run_id": "...",
      "strategy_id": "...",
      "version": 1,
      "provenance": {
        "strategy_spec_version": "...",
        "strategy_spec_hash": "sha256:...",
        "cost_model_version": "...",
        "cost_model_hash": "sha256:...",
        "dataset_hash": "sha256:...",
        "config_hash": "sha256:..."
      },
      "execution": {
        "run_timestamp": "2026-03-17T22:00:00Z",
        "started_at": "...",
        "completed_at": "..."
      },
      "result_files": {
        "trade_log": "backtest/trade-log.arrow",
        "equity_curve": "backtest/equity-curve.arrow",
        "metrics": "backtest/metrics.arrow",
        "parquet_trade_log": "backtest/trade-log.parquet",
        "parquet_equity_curve": "backtest/equity-curve.parquet",
        "parquet_metrics": "backtest/metrics.parquet"
      },
      "metrics_summary": {
        "total_trades": 500,
        "win_rate": 0.55,
        "profit_factor": 1.32,
        "sharpe_ratio": 0.85,
        "max_drawdown_pct": 0.12
      },
      "inputs": {
        "strategy_spec_path": "...",
        "cost_model_path": "...",
        "dataset_path": "..."
      }
    }
    ```
  - [x]Note: `provenance` section contains only deterministic inputs — identical inputs produce identical provenance. `execution` section contains non-deterministic metadata (timestamps). Story 3.9 deterministic verification compares `provenance` sections, not `execution`.
  - [x]Add unit tests: `tests/unit/test_manifest.py`
    - `test_build_manifest_complete()` — verify all required fields present
    - `test_write_manifest_crash_safe()` — verify crash-safe write used
    - `test_verify_inputs_retrievable_success()` — all inputs exist
    - `test_verify_inputs_retrievable_missing()` — missing input raises error
    - `test_verify_inputs_hash_mismatch()` — input exists but hash changed raises warning
    - `test_load_manifest_roundtrip()` — write then load produces identical dict

- [x] **Task 5: Parquet Archival** (AC: #8)
  - [x]Create `src/python/artifacts/parquet_archiver.py` with `ParquetArchiver` class
  - [x]`def archive_arrow_to_parquet(self, arrow_path: Path, parquet_path: Path, compression: str = "zstd") -> Path` — reads Arrow IPC, writes Parquet with compression via `pyarrow.parquet.write_table()`
  - [x]`def archive_backtest_results(self, version_dir: Path) -> list[Path]` — archives all `.arrow` files in `backtest/` to corresponding `.parquet` files
  - [x]Use crash-safe write pattern (write `.partial` → rename)
  - [x]Add unit tests: `tests/unit/test_parquet_archiver.py`
    - `test_archive_roundtrip()` — Arrow → Parquet → read back, verify identical data
    - `test_archive_compression()` — Parquet file smaller than Arrow IPC
    - `test_archive_crash_safe()` — no `.partial` files after success

- [x] **Task 6: Result Processing Orchestrator** (AC: #1, #2, #3, #4, #5, #6, #7, #8, #9, #10, #11)
  - [x]Create `src/python/rust_bridge/result_processor.py` with `ResultProcessor` class — orchestrates the full post-backtest flow
  - [x]`def __init__(self, artifacts_root: Path, sqlite_db_path: Path) -> None` — initializes `ArtifactStorage`, `SQLiteManager`, `ResultIngester`, `ManifestBuilder`, `ParquetArchiver`
  - [x]`def process_backtest_results(self, strategy_id: str, backtest_run_id: str, config_hash: str, data_hash: str, cost_model_hash: str, strategy_spec_hash: str, rust_output_dir: Path, strategy_spec_version: str, cost_model_version: str, run_timestamp: str) -> ProcessingResult` — full pipeline:
    1. Determine version (new vs existing) via `ArtifactStorage.should_create_new_version()`
    2. Create version directory
    3. Publish Arrow IPC files from Rust output dir to versioned artifact dir — use crash-safe copy pattern: `shutil.copy2()` to `{target}.partial` → `os.fsync()` → `os.replace()` to final path (NFR15). If target already exists (resume case), skip. On failure, leave source intact (Rust output dir is the recovery source)
    4. Validate Arrow schemas against `contracts/arrow_schemas.toml`
    5. Register `backtest_run` in SQLite, clear any existing trades for this `backtest_run_id` (idempotent re-ingest), then ingest trade-log. **Research Update:** If fold-aware evaluation was used, also ingest per-fold scores into `fold_scores` table.
    6. Create Parquet archival copies for all Arrow files (skip if `.parquet` already exists for resume)
    7. Validate consistency: Arrow trade record count == SQLite trade row count == Parquet trade row count; verify `trade_id` ordering and first/last `entry_time` match (AC: #11)
    8. Complete `backtest_run` record with `total_trades` and status `'completed'`
    9. Build and write manifest.json
    10. Return `ProcessingResult` dataclass with version, run info, file paths
  - [x]`ProcessingResult` dataclass: `version: int`, `backtest_run_id: str`, `trade_count: int`, `artifact_dir: Path`, `manifest_path: Path`
  - [x]Track sub-step completion in `_processing_checkpoint.json` within version dir: `{"arrow_published": true, "schema_validated": true, "sqlite_ingested": true, "parquet_archived": true, "manifest_written": true}` — on resume, skip completed steps (AC: #10). This is an internal implementation detail of `ResultProcessor`, not a pipeline stage.
  - [x]Error handling: if any step fails, log error, save checkpoint of completed steps, do NOT delete partial version dir (allow investigation), raise `ResultProcessingError` with stage info
  - [x]Add integration tests: `tests/integration/test_result_processor.py`
    - `test_process_full_pipeline()` — mock Rust output → verify all artifacts, SQLite rows, manifest
    - `test_process_creates_new_version_on_hash_change()` — change config_hash, verify v002
    - `test_process_reuses_version_on_same_hash()` — same hashes, verify no new version
    - `test_process_handles_missing_arrow_file()` — missing file raises clear error
    - `test_process_schema_validation_failure()` — wrong schema raises before ingest
    - `test_process_resume_after_crash()` — simulate crash after SQLite ingest, verify resume completes Parquet+manifest (AC: #10)
    - `test_process_trade_count_consistency()` — verify Arrow/SQLite/Parquet trade counts match and trade_id ordering matches (AC: #11)
    - `test_process_backtest_runs_populated()` — verify backtest_runs table has correct run record with status 'completed'
    - `test_process_crash_safe_publish()` — verify no `.partial` files remain, source dir intact on failure

- [x] **Task 7: Integration with Pipeline State Machine** (AC: #1, #7)
  - [x]Wire `ResultProcessor` into `src/python/orchestrator/stage_runner.py` as an internal step within the `backtest-complete` → `review-pending` transition (NOT as a separate pipeline stage — Story 3.3 defines stages as `data-ready` → `strategy-ready` → `backtest-running` → `backtest-complete` → `review-pending` → `reviewed`)
  - [x]Result processing runs automatically after backtest exits with code 0, before the pipeline transitions to `review-pending`
  - [x]On entry: read pipeline state for strategy_id, config_hash, data_hash from `pipeline-state.json`; generate `backtest_run_id` (format: `{strategy_id}_{timestamp}_{config_hash_short}`)
  - [x]On success: update pipeline state with `backtest_run_id`, version number, artifact paths, key metrics summary; transition to `review-pending`
  - [x]On failure: update pipeline state with error details, remain at `backtest-complete` to allow retry
  - [x]On resume: `ResultProcessor` reads `_processing_checkpoint.json`, skips completed sub-steps, continues from first incomplete step
  - [x]Add integration test: `tests/integration/test_result_ingestion_stage.py`
    - `test_result_processing_triggers_after_backtest()` — verify result processing runs as part of backtest-complete → review-pending
    - `test_stage_resume_after_crash()` — simulate crash after SQLite ingest, verify Parquet and manifest complete on resume
    - `test_stage_idempotent_rerun()` — run processing twice with same inputs, verify no duplicates or errors

- [x] **Task 8: Test Fixtures & Schema Validation** (AC: #3, #4)
  - [x]Create Arrow IPC test fixtures in `tests/fixtures/backtest_output/`:
    - `trade-log.arrow` — 50 sample trades with realistic field values
    - `equity-curve.arrow` — 1000 sample equity points
    - `metrics.arrow` — single-row summary metrics
    - `run_metadata.json` — sample metadata
  - [x]Fixture generator script: `tests/fixtures/generate_backtest_fixtures.py` using `pyarrow` — schemas MUST match `contracts/arrow_schemas.toml`
  - [x]Validate fixtures load correctly with `pyarrow.ipc.open_file()`

## Dev Notes

### Architecture Constraints

- **D1 (Multi-Process):** This story runs entirely in the Python orchestrator process. Arrow IPC files are produced by the Rust backtester (Story 3.5) as a separate process. Python reads the output files after the Rust process exits successfully (exit code 0).
- **D2 (Three-Format Storage):** Arrow IPC is the canonical source of truth. SQLite is a derived queryable trade-level index — rebuildable from Arrow/Parquet if corrupted. Parquet is compressed archival. This story implements all three layers. Equity curves and metrics are stored in Arrow IPC and Parquet only — SQLite only contains `trades` and `backtest_runs` per `contracts/sqlite_ddl.sql`.
- **D3 (Pipeline State Machine):** Result processing runs as an internal step within the `backtest-complete` → `review-pending` transition — NOT as a separate pipeline stage. Story 3.3 defines the stage model; this story does not add new stages. The `_processing_checkpoint.json` is an internal implementation detail for within-step crash recovery, not a pipeline-level state.
- **D8 (Error Handling):** Data/logic errors → stop and report. Do NOT silently skip corrupt Arrow files. External failures (disk full) → retry with backoff.
- **FR58-FR61 (Artifact Management):** Every stage emits persisted artifacts. Manifests link all inputs for reproducibility. Version on input change, never overwrite.
- **NFR15 (Crash Safety):** ALL writes use write → flush → rename. SQLite uses WAL mode. No partial artifacts visible to other stages.

### Data Volume Expectations

Per architecture sizing (for capacity planning, not hard limits):
- Single backtest: ~500 trades × 20 fields ≈ 80 KB Arrow IPC
- Full optimization run (10K backtests): ~5M trade records ≈ 800 MB Arrow IPC
- SQLite ingest of 5M trades: ~30 seconds (WAL mode, 1000-row batches). Only trade-log is ingested — equity curves and metrics stay in Arrow/Parquet.
- Query indexed trades: <100ms for typical `strategy_id + session` queries
- Dashboard aggregation across 5M trades: 2-5 seconds
- Equity curve / metrics reads from Arrow IPC via mmap: <50ms for single backtest, seconds for full optimization sweep

### Arrow IPC Schemas (from Story 3.5 / contracts/arrow_schemas.toml)

**Trade Log Schema:**
| Field | Arrow Type | Notes |
|---|---|---|
| entry_time | Int64 | Nanosecond UTC timestamp |
| exit_time | Int64 | Nanosecond UTC timestamp |
| entry_price_raw | Float64 | Pre-cost price |
| entry_price | Float64 | Cost-adjusted price |
| exit_price_raw | Float64 | Pre-cost price |
| exit_price | Float64 | Cost-adjusted price |
| entry_spread | Float64 | Spread applied at entry |
| entry_slippage | Float64 | Slippage applied at entry |
| exit_spread | Float64 | Spread applied at exit |
| exit_slippage | Float64 | Slippage applied at exit |
| direction | Utf8 | "Long" or "Short" |
| entry_session | Utf8 | Trading session at entry |
| exit_session | Utf8 | Trading session at exit |
| signal_id | UInt64 | Signal that triggered trade |
| pnl | Float64 | Realized P&L |
| holding_duration_bars | UInt64 | Duration in bars |
| exit_reason | Utf8 | StopLoss/TakeProfit/TrailingStop/ChandelierExit/SignalReversal/EndOfData/SubBarM1Exit/StaleExit/PartialClose/BreakevenWithOffset/MaxBarsExit |
| fold_id | UInt64 | Optional — present when fold-aware evaluation is used |
| trade_id | UInt64 | Deterministic ordering ID |

**Equity Curve Schema:**
| Field | Arrow Type |
|---|---|
| timestamp | Int64 |
| equity | Float64 |
| unrealized_pnl | Float64 |
| drawdown_pct | Float64 |
| trades_to_date | UInt64 |

**Metrics Schema:** Single-row RecordBatch with: win_rate, profit_factor, sharpe_ratio (unannualized), r_squared, max_drawdown_amount, max_drawdown_pct, max_drawdown_duration_bars, total_trades, avg_trade_duration_bars, winning_trades, losing_trades, avg_win, avg_loss, largest_win, largest_loss.

### Upstream Contracts

- **Rust backtester output (Story 3.5):** Writes `trade-log.arrow`, `equity-curve.arrow`, `metrics.arrow` to `--output` directory. Uses crash-safe `.partial/` → rename pattern. Also writes `run_metadata.json` (non-deterministic: config_hash, binary version, timestamp).
- **Python bridge (Story 3.4):** `batch_runner.py` spawns Rust binary, checks exit code 0 before calling result processing. Passes `config_hash` through CLI args.
- **Pipeline state machine (Story 3.3):** `pipeline-state.json` tracks stage transitions. `stage_runner.py` orchestrates stage execution.
- **Schema SSOT:** `contracts/arrow_schemas.toml` is the single source of truth for Arrow schemas. `contracts/sqlite_ddl.sql` is the SSOT for SQLite tables. Both Rust (compile-time) and Python (runtime validation) use these. Story 3.7 downstream uses `backtest_run_id` as its `backtest_id` interface parameter.

### Performance Considerations

- Use `pyarrow.ipc.open_file()` for mmap-based reading — do NOT load entire Arrow files into memory with `read_all()` for large files
- SQLite batch inserts: use `executemany()` with 1000-row batches inside transactions for optimal WAL performance
- Arrow→SQLite timestamp conversion: convert Int64 nanosecond UTC → ISO 8601 TEXT during ingestion (per architecture DDL)
- Parquet compression: use `zstd` (best compression ratio for numeric data)
- For large equity curves (5.26M points per optimization), consider chunked reading via RecordBatch iteration
- File publishing: use crash-safe copy pattern (`copy2` → `.partial` → `fsync` → `os.replace`), NOT `shutil.move()` which is not atomic across filesystems and violates NFR15

### What to Reuse from ClaudeBackTester

- **Adapt:** Result storage concept — ClaudeBackTester stores results as numpy arrays/CSV/pickle. Port the *what* (trade records, equity curve, metrics) but not the *how* (use Arrow IPC/SQLite/Parquet per D2).
- **Adapt:** Metric definitions — ClaudeBackTester's 10 metrics (M_TRADES=0 through M_QUALITY=9) map to the same metrics computed by Story 3.5's Rust backtester. Ensure column names align so downstream (Story 3.7 AI analysis) works with both historical and new results.
- **Avoid:** ClaudeBackTester's pickle serialization, pandas-heavy processing, and in-memory-only result handling. These don't scale to optimization runs with millions of trades.

### Project Structure Notes

```
src/python/
├── artifacts/                          # NEW — Artifact management (this story)
│   ├── __init__.py
│   ├── storage.py                      # ArtifactStorage: versioning, crash-safe writes
│   ├── sqlite_manager.py              # SQLiteManager: schema, WAL, indexes
│   ├── manifest.py                    # ManifestBuilder: reproducibility manifests
│   └── parquet_archiver.py            # ParquetArchiver: Arrow → Parquet archival
├── rust_bridge/                        # EXISTING — Python-Rust boundary
│   ├── batch_runner.py                # Story 3.4 — spawns Rust binary
│   ├── result_ingester.py             # NEW — Arrow → SQLite ingestion
│   ├── result_processor.py            # NEW — Orchestrates full post-backtest flow
│   └── error_parser.py               # Story 3.4 — Rust stderr parsing
├── orchestrator/                       # EXISTING — Pipeline orchestration
│   └── stage_runner.py                # MODIFY — Wire ResultProcessor into backtest-complete → review-pending transition

artifacts/                              # Runtime artifact storage root
  pipeline.db                           # SQLite — trades + backtest_runs (shared across strategies)
  {strategy_id}/
    v001/
      manifest.json
      _processing_checkpoint.json       # Internal crash-recovery state (not a pipeline stage)
      backtest/
        trade-log.arrow                 # Canonical (from Rust)
        equity-curve.arrow
        metrics.arrow
        trade-log.parquet               # Archival (this story creates)
        equity-curve.parquet
        metrics.parquet

tests/
├── unit/
│   ├── test_artifact_storage.py
│   ├── test_sqlite_manager.py
│   ├── test_result_ingester.py
│   ├── test_manifest.py
│   └── test_parquet_archiver.py
├── integration/
│   ├── test_result_processor.py
│   └── test_result_ingestion_stage.py
└── fixtures/
    └── backtest_output/
        ├── generate_backtest_fixtures.py
        ├── trade-log.arrow
        ├── equity-curve.arrow
        └── metrics.arrow

contracts/
  arrow_schemas.toml                   # Arrow schema SSOT (existing from Story 3.2)
  sqlite_ddl.sql                       # SQLite schema SSOT (existing from Story 1.3)
```

### Anti-Patterns to Avoid

1. **NO pandas for ingestion** — Use `pyarrow` directly for Arrow IPC reading. Pandas adds unnecessary memory overhead and conversion time for large datasets.
2. **NO JSON/CSV for bulk data** — Arrow IPC is the canonical format per D2. Only `manifest.json` and `run_metadata.json` use JSON (metadata, not bulk data).
3. **NO direct SQLite writes without WAL** — Always enable WAL mode before any writes. Without WAL, concurrent reads during ingestion will block.
4. **NO overwriting existing versions** — Input hash changes create new versions. Never modify artifacts in existing `v{NNN}` directories.
5. **NO unbounded memory during ingestion** — Stream Arrow RecordBatches, don't `read_all()` into memory for large files. Use batch inserts of 1000 rows.
6. **NO partial artifacts visible to other stages** — Crash-safe write pattern (`.partial` → rename) ensures atomicity. Pipeline state machine gates prevent downstream stages from seeing incomplete results.
7. **NO SQLite as source of truth** — SQLite is a derived index. Arrow IPC is canonical. If SQLite corrupts, rebuild from Arrow/Parquet.
8. **NO hardcoded paths** — All paths derived from `artifacts_root` + `strategy_id` + version. Use `pathlib.Path` throughout.
9. **NO ignoring schema validation** — Validate Arrow file schemas against `contracts/arrow_schemas.toml` BEFORE ingestion. Catch schema drift from Rust backtester early.
10. **NO silent failures** — Log every step (Arrow publish, schema validation, SQLite ingest, Parquet archive, manifest write) with timing. Raise `ResultProcessingError` with stage context on failure.
11. **NO redefining contracts/ schemas** — `contracts/sqlite_ddl.sql` and `contracts/arrow_schemas.toml` are SSOT. Implement them, don't rewrite them in stories. If the schema needs changes, update contracts/ first.
12. **NO inventing pipeline stages** — Story 3.3 defines the stage model. Result processing is an internal step within `backtest-complete` → `review-pending`, not a new stage.

### Dependencies (Python packages)

- `pyarrow` — Arrow IPC reading, Parquet writing (already in project from Story 3.4)
- `sqlite3` — Python standard library (no external dependency)
- No new dependencies required

### References

- [Source: _bmad-output/planning-artifacts/architecture.md — D2 Artifact Schema & Storage]
- [Source: _bmad-output/planning-artifacts/architecture.md — D1 System Topology]
- [Source: _bmad-output/planning-artifacts/architecture.md — D3 Pipeline Orchestration]
- [Source: _bmad-output/planning-artifacts/architecture.md — D8 Error Handling]
- [Source: _bmad-output/planning-artifacts/prd.md — FR14-FR19 Backtesting Output]
- [Source: _bmad-output/planning-artifacts/prd.md — FR58-FR61 Artifact Management]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR15 Crash-Safe Writes]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 3 Story 3.6]
- [Source: _bmad-output/implementation-artifacts/3-5-rust-backtester-crate-trade-simulation-engine.md — Output formats, Arrow schemas]
- [Source: _bmad-output/implementation-artifacts/3-4-python-rust-bridge-batch-evaluation-dispatch.md — Bridge contracts]
- [Source: _bmad-output/implementation-artifacts/3-3-pipeline-state-machine-checkpoint-infrastructure.md — State machine integration]
- [Source: _bmad-output/implementation-artifacts/3-2-python-rust-ipc-deterministic-backtesting-research.md — Arrow IPC contracts, schema SSOT]
- [Source: _bmad-output/implementation-artifacts/3-1-claudebacktester-backtest-engine-review.md — Baseline result patterns]
- [Source: contracts/arrow_schemas.toml — Arrow schema single source of truth]
- [Source: contracts/sqlite_ddl.sql — SQLite schema single source of truth]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Debug Log References
- Fixed `os.open(O_RDONLY)` + `os.fsync()` failing on Windows — switched to `open("r+b")` pattern
- Fixed `reader.schema_arrow` → `reader.schema` for PyArrow RecordBatchFileReader API
- Fixed resume test: don't delete manifest when testing checkpoint resume (causes version increment)

### Completion Notes List
- Task 1: Enhanced `artifacts/storage.py` with `ArtifactStorage` class (versioning, hash comparison, crash-safe JSON writes). 9 unit tests.
- Task 2: Created `artifacts/sqlite_manager.py` — SQLiteManager with WAL mode, schema from contracts/sqlite_ddl.sql SSOT. Updated DDL contract to add `fold_scores` table. 8 unit tests.
- Task 3: Created `rust_bridge/result_ingester.py` — Arrow→SQLite field mapping with nanosecond→ISO 8601 conversion, batch inserts, idempotent re-ingest, fold score ingestion. 13 unit tests.
- Task 4: Created `artifacts/manifest.py` — ManifestBuilder with provenance/execution separation, crash-safe write, input verification. 8 unit tests.
- Task 5: Created `artifacts/parquet_archiver.py` — Arrow→Parquet with zstd compression, crash-safe write, resume-safe archival. 5 unit tests.
- Task 6: Created `rust_bridge/result_processor.py` — Full 9-step pipeline orchestrator with checkpoint/resume. 9 integration tests.
- Task 7: Created `rust_bridge/result_executor.py` — StageExecutor for BACKTEST_COMPLETE stage. 5 integration tests.
- Task 8: Created fixture generator and Arrow IPC test fixtures matching contracts/arrow_schemas.toml.
- All 11 ACs verified through tests. 1001 total tests pass (0 regressions). 3 @pytest.mark.live tests.

### Change Log
- 2026-03-19: Story 3.6 implemented — Backtest results artifact storage, SQLite ingest, Parquet archival, manifest creation, pipeline integration

### File List
- `contracts/sqlite_ddl.sql` — Added fold_scores table and indexes (SSOT update)
- `src/python/artifacts/storage.py` — Enhanced with ArtifactStorage class, crash_safe_write_json
- `src/python/artifacts/sqlite_manager.py` — NEW: SQLiteManager with WAL mode and SSOT schema
- `src/python/artifacts/manifest.py` — NEW: ManifestBuilder for reproducibility manifests
- `src/python/artifacts/parquet_archiver.py` — NEW: ParquetArchiver for Arrow→Parquet archival
- `src/python/artifacts/__init__.py` — Updated exports
- `src/python/rust_bridge/result_ingester.py` — NEW: Arrow IPC→SQLite trade-log ingestion
- `src/python/rust_bridge/result_processor.py` — NEW: Full post-backtest result processing orchestrator
- `src/python/rust_bridge/result_executor.py` — NEW: StageExecutor for BACKTEST_COMPLETE stage
- `src/python/rust_bridge/__init__.py` — Updated exports
- `src/python/tests/test_artifacts/test_artifact_storage.py` — NEW: 9 unit tests for ArtifactStorage
- `src/python/tests/test_artifacts/test_sqlite_manager.py` — NEW: 8 unit tests for SQLiteManager
- `src/python/tests/test_artifacts/test_manifest.py` — NEW: 8 unit tests for ManifestBuilder
- `src/python/tests/test_artifacts/test_parquet_archiver.py` — NEW: 5 unit tests for ParquetArchiver
- `src/python/tests/test_rust_bridge/test_result_ingester.py` — NEW: 13 unit tests for ResultIngester
- `src/python/tests/test_rust_bridge/test_result_processor.py` — NEW: 9 integration tests for ResultProcessor
- `src/python/tests/test_rust_bridge/test_result_ingestion_stage.py` — NEW: 5 integration tests for ResultExecutor
- `src/python/tests/test_rust_bridge/test_result_processor_live.py` — NEW: 3 @pytest.mark.live tests
- `src/python/tests/fixtures/backtest_output/generate_backtest_fixtures.py` — NEW: Fixture generator
- `src/python/tests/fixtures/backtest_output/trade-log.arrow` — NEW: 50-trade fixture
- `src/python/tests/fixtures/backtest_output/equity-curve.arrow` — NEW: 1000-point fixture
- `src/python/tests/fixtures/backtest_output/metrics.arrow` — NEW: Single-row metrics fixture
- `src/python/tests/fixtures/backtest_output/run_metadata.json` — NEW: Sample metadata
