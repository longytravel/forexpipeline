# Story 1.9: E2E Pipeline Proof — Market Data Flow

Status: review

## Story

As the **operator**,
I want to run the full data pipeline end-to-end on a reference dataset and verify the complete artifact chain,
So that I know the market data flow works correctly before building on top of it.

## Acceptance Criteria

1. **Given** all data pipeline components are implemented (Stories 1.3-1.8)
   **When** the pipeline proof is executed for EURUSD, 1 year of M1 data
   **Then** data downloads successfully from Dukascopy to `G:\My Drive\BackTestData`

2. **And** validation runs and produces a quality score with GREEN/YELLOW/RED rating

3. **And** quality report artifact is produced

4. **And** data is stored in Parquet and converted to Arrow IPC with correct schema

5. **And** session column is correctly populated on every bar

6. **And** timeframe conversion produces H1 data correctly

7. **And** train/test split produces two datasets with correct temporal boundaries

8. **And** all artifacts are versioned, hash-identified, and linked via manifests

9. **And** re-running the pipeline with the same config produces identical artifacts (same hashes)

10. **And** all structured logs are present and correctly formatted

11. **And** this reference dataset is saved for use in all subsequent epic pipeline proofs

## Tasks / Subtasks

- [x] **Task 1: Create the E2E pipeline proof script `src/python/data_pipeline/pipeline_proof.py`** (AC: #1-#11)
  - [x] Create `pipeline_proof.py` in `src/python/data_pipeline/`
  - [x] This is NOT a test file — it is a runnable script that exercises the full pipeline and verifies outcomes
  - [x] Implement `run_pipeline_proof(config: dict) -> PipelineProofResult`
  - [x] The function orchestrates all stages sequentially:
    1. Download (Story 1.4)
    2. Validate + Score (Story 1.5)
    3. Store Parquet + Convert to Arrow IPC (Story 1.6)
    4. Convert timeframes (Story 1.7)
    5. Split train/test + create manifest (Story 1.8)
    6. Verify all artifacts
    7. Run reproducibility check

- [x] **Task 2: Configure reference dataset parameters** (AC: #1, #11)
  - [x] Add `[data_pipeline.reference_dataset]` section to `config/base.toml`:
    ```toml
    [data_pipeline.reference_dataset]
    pair = "EURUSD"
    start_date = "2024-01-01"
    end_date = "2024-12-31"
    resolution = "M1"
    source = "dukascopy"
    ```
  - [x] These values define the canonical reference dataset used for all subsequent pipeline proofs
  - [x] The script reads these from config — they are not hardcoded in the proof script

- [x] **Task 3: Stage 1 — Download EURUSD 1 year M1** (AC: #1)
  - [x] Call `downloader.download_data()` (from Story 1.4) with reference dataset params
  - [x] Verify: raw data file exists at `{storage_path}/data-pipeline/`
  - [x] Verify: data covers the expected date range (first timestamp >= start_date, last timestamp <= end_date)
  - [x] Verify: data has expected columns (timestamp, open, high, low, close, bid, ask at minimum)
  - [x] Log: pair, date range, bar count, file size, download duration
  - [x] Expected: ~525,600 M1 bars for 1 year (per architecture data volume modeling)

- [x] **Task 4: Stage 2 — Validate + Quality Score** (AC: #2, #3)
  - [x] Call `quality_checker.validate_data()` (from Story 1.5) on the downloaded data
  - [x] Capture quality score and GREEN/YELLOW/RED rating
  - [x] Verify: quality report artifact is produced as JSON
  - [x] Verify: quality report contains gap count, integrity check results, staleness check results
  - [x] Verify: if score >= 0.95, rating is GREEN; if 0.80-0.95, YELLOW; if < 0.80, RED
  - [x] Log: quality_score, rating, gap_count, quarantined_bar_count
  - [x] If RED: log a warning but continue proof (the proof verifies the pipeline works, even if data quality is low — operator decides later)
  - [x] Store the quality report at `{storage_path}/data-pipeline/quality-report.json`

- [x] **Task 5: Stage 3 — Store Parquet + Convert to Arrow IPC** (AC: #4, #5)
  - [x] Call `parquet_archiver.archive_to_parquet()` (from Story 1.6)
  - [x] Call `arrow_converter.convert_to_arrow()` (from Story 1.6)
  - [x] Verify: Parquet file exists with snappy compression
  - [x] Verify: Arrow IPC file exists and is readable via `pyarrow.ipc.open_file()` (mmap-compatible)
  - [x] Verify: Arrow IPC schema matches `contracts/arrow_schemas.toml` `[market_data]` exactly:
    - Columns: timestamp (int64), open (float64), high (float64), low (float64), close (float64), bid (float64), ask (float64), session (utf8), quarantined (bool)
  - [x] Verify session column (AC: #5):
    - Read session schedule from `config/base.toml` `[sessions]`
    - Sample bars at known times and verify session labels:
      - Bar at 03:00 UTC -> "asian"
      - Bar at 10:00 UTC -> "london"
      - Bar at 14:00 UTC -> "london_ny_overlap"
      - Bar at 18:00 UTC -> "new_york"
      - Bar at 22:00 UTC -> "off_hours"
    - Verify: no bar has a null or empty session value
    - Verify: all session values are in the allowed set from `contracts/session_schema.toml`
  - [x] Log: arrow_file_size_mb, parquet_file_size_mb, bar_count, schema_valid

- [x] **Task 6: Stage 4 — Timeframe Conversion** (AC: #6)
  - [x] Call `timeframe_converter.run_timeframe_conversion()` (from Story 1.7) for at least H1 (required by AC), plus M5, D1, W
  - [x] Verify H1 conversion correctness:
    - H1 bar count ~ total_m1_bars / 60 (approximately, accounting for gaps and quarantined bars)
    - Pick a known hour and verify: H1 open = first M1 open, H1 high = max of 60 M1 highs, H1 low = min of 60 M1 lows, H1 close = last M1 close
    - Verify H1 session column is populated
  - [x] Verify M5 conversion: bar count ~ total_m1_bars / 5
  - [x] Verify D1 conversion: bar count ~ 252 trading days for 1 year
  - [x] Verify W conversion: bar count ~ 52 weeks
  - [x] Verify: all converted files exist in both Arrow IPC and Parquet format
  - [x] Verify: all converted files pass schema validation against `contracts/arrow_schemas.toml`
  - [x] Log: per-timeframe bar counts, file sizes

- [x] **Task 7: Stage 5 — Train/Test Split + Manifest** (AC: #7, #8)
  - [x] Call `data_splitter.run_data_splitting()` (from Story 1.8) with default 70/30 ratio
  - [x] Verify train/test split temporal boundary:
    - max(train.timestamp) < min(test.timestamp) for every timeframe
    - train set is approximately 70% of total bars
    - test set is approximately 30% of total bars
  - [x] Verify split files exist for all timeframes (M1, M5, H1, D1, W):
    - `{pair}_{dates}_{tf}_train.arrow` and `{pair}_{dates}_{tf}_test.arrow`
    - Corresponding `.parquet` files
  - [x] Verify manifest:
    - Manifest file exists: `{dataset_id}_manifest.json`
    - Manifest contains: dataset_id, pair, date range, source, data_hash, config_hash
    - Manifest contains: split metadata (split_timestamp, train/test bar counts)
    - Manifest contains: file paths for all timeframes and splits
  - [x] Verify dataset ID format: `{pair}_{start_date}_{end_date}_{source}_{download_hash}`
  - [x] Log: dataset_id, config_hash, split_date, train_bars, test_bars

- [x] **Task 8: Artifact chain verification** (AC: #8)
  - [x] After all stages complete, perform a full artifact inventory:
    - List all files produced in `{storage_path}/data-pipeline/`
    - Verify each file is referenced in the manifest
    - Verify no orphan files exist (files not in manifest)
  - [x] Verify artifact versioning:
    - All files include pair, date range, and timeframe in their name
    - No file has been overwritten (check file creation timestamps or use hash verification)
  - [x] Verify hash chain:
    - Recompute hash of each Arrow IPC file and verify it matches the hash recorded in the manifest
    - Verify config_hash in manifest matches the actual config hash

- [x] **Task 9: Reproducibility verification** (AC: #9)
  - [x] Re-run the ENTIRE pipeline with the same config:
    1. Delete all generated artifacts (keep only the raw download if consistent sourcing re-uses it)
    2. Run stages 2-5 again (validation, conversion, timeframe conversion, splitting)
    3. Compare output hashes with first run
  - [x] Verify: every output file has identical SHA-256 hash between run 1 and run 2
  - [x] If any hash differs, fail the proof and report which file(s) differ
  - [x] This specifically tests:
    - Deterministic validation scoring
    - Deterministic Arrow IPC conversion (same bytes)
    - Deterministic timeframe aggregation
    - Deterministic splitting (same split point, same output)
    - Deterministic manifest content (same JSON, ignoring `created_at` timestamp)
  - [x] For the manifest comparison, ignore the `created_at` field (it will naturally differ) — compare all other fields

- [x] **Task 10: Structured log verification** (AC: #10)
  - [x] After the pipeline run, verify log output:
    - Log file exists at `logs/python_{date}.log` (or equivalent per D6)
    - Each log line is valid JSON
    - Each log line contains required fields: `ts`, `level`, `runtime`, `component`, `stage`, `msg`
    - `runtime` = "python" for all lines
    - `component` values include: "data_pipeline"
    - `stage` values include: "download", "validation", "arrow_conversion", "timeframe_conversion", "data_splitting"
    - No ERROR-level log lines (unless data quality triggered one)
  - [x] Parse and count log lines by component/stage to verify completeness

- [x] **Task 11: Save reference dataset marker** (AC: #11)
  - [x] Write a `reference_dataset.json` file at `{storage_path}/data-pipeline/`:
    ```json
    {
      "dataset_id": "EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1",
      "manifest_path": "EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1_manifest.json",
      "created_at": "2026-03-14T10:00:00.000Z",
      "purpose": "Reference dataset for all subsequent Epic pipeline proofs",
      "proof_result": "PASS",
      "reproducibility_verified": true
    }
    ```
  - [x] This file is the canonical pointer to the reference dataset that Epics 2+ will use
  - [x] Future pipeline proofs (e.g., Epic 2 backtesting proof, Epic 3 optimization proof) will load this file to find their input data

- [x] **Task 12: Pipeline proof result summary** (AC: #1-#11)
  - [x] Implement `PipelineProofResult` dataclass:
    ```python
    @dataclass
    class PipelineProofResult:
        overall_status: str  # "PASS" or "FAIL"
        stages: dict[str, StageResult]  # per-stage results
        dataset_id: str
        config_hash: str
        reproducibility_verified: bool
        total_duration_seconds: float
        artifact_count: int
        errors: list[str]
        warnings: list[str]
    ```
  - [x] Print a human-readable summary to stdout at the end:
    ```
    === Pipeline Proof: Market Data Flow ===
    Status: PASS
    Dataset: EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1
    Config Hash: b4c5d6e7

    Stage Results:
      Download:             PASS (525,600 bars, 42.3 MB)
      Validation:           PASS (score: 0.97, GREEN)
      Storage/Conversion:   PASS (Arrow: 40.1 MB, Parquet: 4.2 MB)
      Timeframe Conversion: PASS (M5: 105,120, H1: 8,760, D1: 252, W: 52)
      Train/Test Split:     PASS (train: 367,920, test: 157,680)
      Artifact Chain:       PASS (18 files, all in manifest)
      Reproducibility:      PASS (all hashes match)
      Logging:              PASS (147 log lines, 0 errors)

    Duration: 45.2 seconds
    Reference dataset saved: reference_dataset.json
    ```
  - [x] Also write the result as JSON: `pipeline_proof_result.json` in `{storage_path}/data-pipeline/`

- [x] **Task 13: CLI entry point** (AC: #1-#11)
  - [x] Add a CLI runner that can be invoked:
    ```
    python -m src.python.data_pipeline.pipeline_proof --env local
    ```
  - [x] Or via the main entry point:
    ```
    python -m src.python.main --stage pipeline-proof --env local
    ```
  - [x] Accepts `--env` flag to load appropriate config overlay (local.toml)
  - [x] Accepts `--skip-download` flag for re-runs where data already exists
  - [x] Accepts `--skip-reproducibility` flag to skip the second run (saves time during development)
  - [x] Returns exit code 0 on PASS, exit code 1 on FAIL

- [x] **Task 14: Integration tests for the proof itself** (AC: #1-#11)
  - [x] Create `src/python/tests/test_data_pipeline/test_pipeline_proof.py`
  - [x] Test with a TINY fixture (e.g., 100 M1 bars of synthetic data) instead of real Dukascopy data:
    - Generate synthetic M1 data with known OHLC values, known gaps, known sessions
    - Mock the downloader to return this synthetic data
    - Run the proof pipeline on the synthetic data
    - Verify all stages pass
    - Verify reproducibility with synthetic data
  - [x] This test must run in CI-like conditions (no network, no external dependencies, no `G:\My Drive\BackTestData`)
  - [x] Use a temp directory for all file outputs
  - [x] Verify the proof result structure and content

## Dev Notes

### Architecture Constraints

**D1 — System Topology:** "Python orchestrates. Rust computes." The pipeline proof is entirely Python-orchestrated at this stage. No Rust binary is involved — this is market data preparation, not compute.

**D2 — Artifact Schema & Storage:** "Three-format storage strategy. Compute: Arrow IPC. Archival: Parquet." The proof must verify both formats are produced correctly. Arrow IPC schema must match `contracts/arrow_schemas.toml` exactly. "Every dataset is identified by {pair}_{start_date}_{end_date}_{source}_{download_hash}. Re-runs against the same date range MUST use the identical Arrow IPC file (same hash). New downloads create new versioned artifacts, never overwrite existing."

**D3 — Pipeline Orchestration:** "Sequential state machine. Stages execute sequentially. Stages are stateless between runs — all state is in artifacts and pipeline-state.json." The proof script exercises the pipeline stages in sequence, verifying the stage contract at each step.

**D6 — Logging:** "Each runtime writes structured JSON log lines to logs/, one file per runtime per day." The proof must verify logging output. Unified log schema: `{ts, level, runtime, component, stage, strategy_id, msg, ctx}`.

**D7 — Configuration:** "Layered TOML configs validated at startup. Config hash embedded in every artifact manifest — reproducibility is verifiable. Config hash + data hash = reproducibility proof." The proof must verify config hash is in the manifest and that same config produces same outputs.

**D8 — Error Handling:** "Each runtime catches errors at component boundaries. Fail-fast at boundaries, orchestrator decides." The proof must verify that errors are properly caught and reported, not silently swallowed.

**Session-Awareness Architecture:** "Sessions are a first-class architectural dimension. Session label as a computed column during data pipeline stage. data_pipeline/arrow_converter.py stamps each M1 bar with its session(s) based on config schedule." The proof must verify session stamping is correct by spot-checking known timestamps.

**Crash-Safe Write Pattern:** "All artifact writes: Write to {filename}.partial, flush/fsync, atomic rename." The proof implicitly verifies this by checking that final files exist with correct names (no `.partial` files remaining).

**Data Volume Modeling:** "1 year EURUSD M1 bid+ask: ~525,600 bars, ~40 MB Arrow IPC, ~4 MB Parquet." The proof should validate that actual data volumes are in the expected range.

**Deterministic Reproducibility (FR18, FR61):** "Same strategy specification + same dataset (identical Arrow IPC file) + same config (identical TOML hash) = identical output." The reproducibility check is the most critical verification in this proof.

### Technical Requirements

- **Language:** Python (orchestration tier)
- **Libraries:** `pyarrow`, `hashlib`, `json`, `tomllib`, `dataclasses`, `argparse`, `pathlib`, `time`
- **File location:** `src/python/data_pipeline/pipeline_proof.py`
- **Test location:** `src/python/tests/test_data_pipeline/test_pipeline_proof.py`
- **Reference dataset storage:** `G:\My Drive\BackTestData\data-pipeline\` (configurable via `config/base.toml`)
- **Expected runtime:** 30-120 seconds depending on download speed (bulk of time is Dukascopy download)
- **Expected disk usage:** ~100 MB total (M1 + all timeframes + train/test splits + Parquet copies)

### What to Reuse from ClaudeBackTester

Per baseline-to-architecture-mapping: "Data pipeline | Keep and adapt | Mature." This proof exercises all the adapted/new pipeline components built in Stories 1.3-1.8. It does not directly reuse any ClaudeBackTester code — it verifies that the NEW pipeline works correctly.

The proof script itself is **entirely new** — ClaudeBackTester had no formal pipeline proof or reproducibility verification. This is one of the key improvements over the baseline.

### Anti-Patterns to Avoid

1. **Do NOT make this a unit test.** This is a system-level proof that exercises real components end-to-end. The integration test in Task 14 uses mocks for CI, but the main proof script runs against real Dukascopy data.
2. **Do NOT hardcode EURUSD, dates, or paths.** Read everything from `config/base.toml` `[data_pipeline.reference_dataset]`. The proof should work for any pair/date range if config is changed.
3. **Do NOT skip the reproducibility check.** This is the most important verification. Two identical runs must produce identical artifacts. If they don't, the entire pipeline's determinism guarantee is broken.
4. **Do NOT ignore the `created_at` timestamp difference when comparing manifests.** This field will naturally differ between runs. Compare all other fields.
5. **Do NOT delete the reference dataset after the proof runs.** The reference dataset is saved for all future Epic pipeline proofs (Epic 2 backtesting proof, etc.).
6. **Do NOT use `assert` for verifications.** Use proper verification functions that collect all failures and report them at the end, rather than stopping at the first failure. The operator needs to see ALL issues, not just the first one.
7. **Do NOT run the proof inside pytest.** The proof is a standalone script. The pytest test in Task 14 is a separate, lightweight test that uses synthetic data and mocks.
8. **Do NOT compare Arrow IPC files by loading them into memory and comparing DataFrames.** Compare file hashes (SHA-256) for determinism verification. This is faster and catches byte-level differences that DataFrame comparison might miss.
9. **Do NOT log to stdout and to log files differently.** The proof summary goes to stdout. All pipeline operations log to `logs/` via the structured logging system. Keep these separate.

### Project Structure Notes

```
src/python/
  data_pipeline/
    __init__.py
    downloader.py              # Story 1.4 — called by proof
    quality_checker.py         # Story 1.5 — called by proof
    arrow_converter.py         # Story 1.6 — called by proof
    parquet_archiver.py        # Story 1.6 — called by proof
    timeframe_converter.py     # Story 1.7 — called by proof
    data_splitter.py           # Story 1.8 — called by proof
    dataset_hasher.py          # Story 1.8 — called by proof
    data_manifest.py           # Story 1.8 — called by proof
    pipeline_proof.py          # THIS STORY - new file (main proof script)
  tests/
    test_data_pipeline/
      test_pipeline_proof.py   # THIS STORY - new file (lightweight integration test)
```

Output files produced by the proof:
```
G:\My Drive\BackTestData\   (or configured path)
  data-pipeline/
    # Raw download (Story 1.4)
    EURUSD_2024-01-01_2024-12-31_raw.csv (or .bin, depending on downloader)

    # Validated + converted (Stories 1.5-1.6)
    EURUSD_2024-01-01_2024-12-31_M1.arrow
    EURUSD_2024-01-01_2024-12-31_M1.parquet
    quality-report.json

    # Timeframe converted (Story 1.7)
    EURUSD_2024-01-01_2024-12-31_M5.arrow
    EURUSD_2024-01-01_2024-12-31_M5.parquet
    EURUSD_2024-01-01_2024-12-31_H1.arrow
    EURUSD_2024-01-01_2024-12-31_H1.parquet
    EURUSD_2024-01-01_2024-12-31_D1.arrow
    EURUSD_2024-01-01_2024-12-31_D1.parquet
    EURUSD_2024-01-01_2024-12-31_W.arrow
    EURUSD_2024-01-01_2024-12-31_W.parquet

    # Train/Test splits (Story 1.8) — for each timeframe
    EURUSD_2024-01-01_2024-12-31_M1_train.arrow
    EURUSD_2024-01-01_2024-12-31_M1_test.arrow
    EURUSD_2024-01-01_2024-12-31_H1_train.arrow
    EURUSD_2024-01-01_2024-12-31_H1_test.arrow
    ... (M5, D1, W)
    ... (corresponding .parquet files)

    # Manifest (Story 1.8)
    EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1_manifest.json

    # Proof artifacts (THIS STORY)
    reference_dataset.json
    pipeline_proof_result.json
```

### Dependencies on Previous Stories

This story depends on ALL of Stories 1.3-1.8. The proof calls into each component:

| Stage | Calls | From Story |
|---|---|---|
| Config loading + validation | `config_loader/loader.py`, `config_loader/validator.py`, `config_loader/hasher.py` | 1.3 |
| Structured logging setup | `logging_setup/setup.py` | 1.3 |
| Contracts schemas | `contracts/arrow_schemas.toml`, `contracts/session_schema.toml` | 1.3 |
| Crash-safe write utility | `artifacts/storage.py` | 1.3 |
| Data download | `data_pipeline/downloader.py` | 1.4 |
| Data validation + scoring | `data_pipeline/quality_checker.py` | 1.5 |
| Parquet archival | `data_pipeline/parquet_archiver.py` | 1.6 |
| Arrow IPC conversion + session stamping | `data_pipeline/arrow_converter.py` | 1.6 |
| Timeframe conversion | `data_pipeline/timeframe_converter.py` | 1.7 |
| Train/test splitting | `data_pipeline/data_splitter.py` | 1.8 |
| Dataset hashing + ID | `data_pipeline/dataset_hasher.py` | 1.8 |
| Manifest creation | `data_pipeline/data_manifest.py` | 1.8 |

If any of these components are not yet implemented, the proof will fail at that stage. The proof is designed to be the capstone verification that all components work together correctly.

### References

- [Source: planning-artifacts/epics.md#Story 1.9 — E2E Pipeline Proof — Market Data Flow]
- [Source: planning-artifacts/architecture.md#Decision 1 — System Topology]
- [Source: planning-artifacts/architecture.md#Decision 2 — Artifact Schema & Storage]
- [Source: planning-artifacts/architecture.md#Decision 3 — Pipeline Orchestration]
- [Source: planning-artifacts/architecture.md#Decision 6 — Structured JSON Logging]
- [Source: planning-artifacts/architecture.md#Decision 7 — TOML Configuration]
- [Source: planning-artifacts/architecture.md#Decision 8 — Error Handling]
- [Source: planning-artifacts/architecture.md#Session-Awareness Architecture]
- [Source: planning-artifacts/architecture.md#Crash-Safe Write Pattern]
- [Source: planning-artifacts/architecture.md#Data Volume Modeling]
- [Source: planning-artifacts/architecture.md#Deterministic Reproducibility Verification]
- [Source: planning-artifacts/architecture.md#Contracts Directory — arrow_schemas.toml, session_schema.toml]
- [Source: planning-artifacts/prd.md#FR1-FR8 — Data Pipeline requirements]
- [Source: planning-artifacts/prd.md#FR58-FR61 — Artifact management and reproducibility]
- [Source: planning-artifacts/prd.md#NFR11 — Crash-safe artifacts]
- [Source: planning-artifacts/prd.md#NFR15 — Data integrity on failure]
- [Source: planning-artifacts/prd.md#Journey 1 — Pipeline Proof (MVP)]
- [Source: planning-artifacts/baseline-to-architecture-mapping.md#data_pipeline — Keep and adapt]
- [Source: planning-artifacts/baseline-to-architecture-mapping.md#Epic Sequencing Implications]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Completion Notes List
- **Task 1-12:** Created `pipeline_proof.py` with PipelineProof class orchestrating 8 stages: download, validation, Arrow IPC + Parquet conversion, timeframe conversion, train/test split, artifact chain verification, reproducibility verification, and structured log verification. Uses verification collector pattern (no asserts) per anti-pattern #6. StageResult and PipelineProofResult dataclasses capture per-stage details, errors, and warnings. Human-readable summary printed to stdout; JSON result saved to `pipeline_proof_result.json`.
- **Task 2:** Added `[data_pipeline.reference_dataset]` config section to `config/base.toml` with EURUSD/2024/M1/dukascopy params. All values read from config, nothing hardcoded.
- **Task 5 (conversion bridge):** ArrowConverter outputs to `{arrow_base}/{dataset_id}/v1/market-data.arrow` but downstream components (timeframe_converter, data_splitter) expect `{pair}_{dates}_{tf}.arrow` in `data-pipeline/`. Solved by copying M1 Arrow/Parquet to `data-pipeline/` with proper naming after ArrowConverter.convert().
- **Task 9 (reproducibility):** Deletes all generated artifacts (keeps raw download), re-runs stages 2-5, compares SHA-256 hashes of all Arrow/Parquet files and manifest content (excluding `created_at`).
- **Task 13:** Added `--stage pipeline-proof` dispatch to `main.py` with argparse. Also supports direct invocation via `python -m data_pipeline.pipeline_proof`.
- **Task 14:** 18 unit tests + 3 @pytest.mark.live tests. Unit tests mock downloader/checker/converter. Live tests verify real file I/O for result JSON and reference dataset marker.
- **Regression:** Full suite 250 passed, 0 failures, 26 skipped (live tests).

### File List
- `src/python/data_pipeline/pipeline_proof.py` — NEW: E2E pipeline proof script
- `src/python/main.py` — MODIFIED: added --stage pipeline-proof CLI dispatch
- `config/base.toml` — MODIFIED: added [data_pipeline.reference_dataset] section
- `src/python/tests/test_data_pipeline/test_pipeline_proof.py` — NEW: unit + live tests

### Change Log
- 2026-03-14: Story 1.9 implemented — E2E pipeline proof with all 14 tasks complete. Created pipeline_proof.py (orchestration + verification), updated main.py CLI, added reference_dataset config, wrote 21 tests (18 unit + 3 live).
