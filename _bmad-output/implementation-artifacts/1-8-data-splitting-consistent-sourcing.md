# Story 1.8: Data Splitting & Consistent Sourcing

Status: review

## Story

As the **operator**,
I want data split chronologically for train/test and identified by hash for reproducibility,
So that backtests use consistent data and results are reproducible.

## Acceptance Criteria

1. **Given** validated, converted data exists (Story 1.7)
   **When** data splitting is configured and executed
   **Then** the system performs chronological train/test splitting at a configurable split point (FR7)

2. **And** no future data leaks into the training set — split is strictly temporal

3. **And** each dataset is identified by `{pair}_{start_date}_{end_date}_{source}_{download_hash}` (FR8)

4. **And** re-runs against the same date range use the identical Arrow IPC file with the same hash (FR8)

5. **And** new downloads create new versioned artifacts, never overwrite existing (FR8)

6. **And** the dataset identifier and hash are recorded in the artifact manifest (FR58, FR59)

7. **And** the manifest includes the config hash used to produce it

## Tasks / Subtasks

- [x] **Task 1: Define splitting config in `config/base.toml`** (AC: #1, #7)
  - [x] Add `[data_pipeline.splitting]` section with:
    - `split_ratio = 0.7` (70% train, 30% test — configurable)
    - `split_mode = "ratio"` (future: could support `"date"` for explicit date boundary)
    - `split_date = ""` (optional: if `split_mode = "date"`, use this date as boundary)
  - [x] Add validation in `config/schema.toml`:
    - `split_ratio` must be between 0.5 and 0.95
    - `split_mode` must be one of `["ratio", "date"]`
    - If `split_mode = "date"`, `split_date` must be a valid ISO 8601 date

- [x] **Task 2: Implement dataset identifier and hashing in `src/python/data_pipeline/dataset_hasher.py`** (AC: #3, #4, #5)
  - [x] Create `dataset_hasher.py` in `src/python/data_pipeline/`
  - [x] Implement `compute_dataset_id(pair: str, start_date: str, end_date: str, source: str, data_hash: str) -> str`
    - Returns `"{pair}_{start_date}_{end_date}_{source}_{data_hash}"` (e.g., `"EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1"`)
    - `source` = "dukascopy" (from download metadata)
    - `data_hash` = first 8 chars of SHA-256 of the Arrow IPC file content
  - [x] Implement `compute_file_hash(file_path: Path) -> str`
    - SHA-256 hash of the entire file content
    - Returns full hex digest (64 chars)
    - For dataset ID, use truncated version (first 8 chars)
  - [x] Implement `check_existing_dataset(dataset_id: str, storage_path: Path) -> Optional[Path]`
    - Check if an Arrow IPC file with this dataset ID already exists
    - If yes, return the path (re-runs use the identical file)
    - If no, return None (new file needed)

- [x] **Task 3: Implement chronological train/test splitter in `src/python/data_pipeline/data_splitter.py`** (AC: #1, #2)
  - [x] Create `data_splitter.py` in `src/python/data_pipeline/`
  - [x] Implement `split_train_test(table: pa.Table, config: dict) -> tuple[pa.Table, pa.Table, dict]`
    - Input: full Arrow IPC table (any timeframe), splitting config
    - Output: (train_table, test_table, split_metadata)
    - `split_metadata` contains: `{split_timestamp_us, split_date_iso, train_bar_count, test_bar_count, split_ratio_actual}`
  - [x] Split logic for `split_mode = "ratio"`:
    - Sort table by timestamp (ascending) — must be sorted before splitting
    - Calculate split index = `floor(total_rows * split_ratio)`
    - Split at that index — train = rows[0:split_index], test = rows[split_index:]
    - Record the actual split timestamp (last timestamp in train set)
  - [x] Split logic for `split_mode = "date"`:
    - Convert `split_date` to epoch microseconds UTC
    - Filter: train = rows where timestamp < split_timestamp, test = rows where timestamp >= split_timestamp
    - Record the actual split ratio achieved
  - [x] **Strict temporal guarantee:** After splitting, verify that `max(train.timestamp) < min(test.timestamp)`. Fail loud if violated.
  - [x] Do NOT shuffle data. Do NOT randomly sample. Chronological order is sacred.

- [x] **Task 4: Implement artifact manifest creation in `src/python/data_pipeline/data_manifest.py`** (AC: #6, #7)
  - [x] Create `data_manifest.py` in `src/python/data_pipeline/` (or extend `src/python/artifacts/manifest.py` if it exists from Story 1.3)
  - [x] Implement `create_data_manifest(dataset_id: str, config_hash: str, split_metadata: dict, file_paths: dict) -> dict`
  - [x] Manifest structure (JSON):
    ```
    {
      "dataset_id": "EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1",
      "pair": "EURUSD",
      "start_date": "2024-01-01",
      "end_date": "2024-12-31",
      "source": "dukascopy",
      "data_hash": "a3b8f2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1",
      "config_hash": "b4c5d6e7f8a9b0c1",
      "created_at": "2026-03-14T10:00:00.000Z",
      "split": {
        "mode": "ratio",
        "configured_ratio": 0.7,
        "actual_ratio": 0.6998,
        "split_timestamp_us": 1719792000000000,
        "split_date_iso": "2024-07-01T00:00:00Z",
        "train_bar_count": 367920,
        "test_bar_count": 157680
      },
      "files": {
        "full": "EURUSD_2024-01-01_2024-12-31_M1.arrow",
        "train": "EURUSD_2024-01-01_2024-12-31_M1_train.arrow",
        "test": "EURUSD_2024-01-01_2024-12-31_M1_test.arrow",
        "full_parquet": "EURUSD_2024-01-01_2024-12-31_M1.parquet",
        "train_parquet": "EURUSD_2024-01-01_2024-12-31_M1_train.parquet",
        "test_parquet": "EURUSD_2024-01-01_2024-12-31_M1_test.parquet"
      },
      "timeframes": {
        "H1": {
          "train": "EURUSD_2024-01-01_2024-12-31_H1_train.arrow",
          "test": "EURUSD_2024-01-01_2024-12-31_H1_test.arrow"
        }
      }
    }
    ```
  - [x] Write manifest using crash-safe write pattern (write to `.partial`, fsync, rename)
  - [x] Manifest file name: `{dataset_id}_manifest.json`
  - [x] Manifest location: same directory as the data files (`{storage_path}/data-pipeline/`)

- [x] **Task 5: Implement versioned artifact storage — never overwrite** (AC: #5)
  - [x] When writing split output files, check if file already exists:
    - If file exists AND hash matches the expected hash: skip writing (idempotent re-run)
    - If file exists AND hash does NOT match: this should never happen for the same dataset ID — log error and fail
    - If file does NOT exist: write normally
  - [x] Each unique download produces a unique `data_hash` in the dataset ID, so different downloads naturally get different file names
  - [x] Implement `ensure_no_overwrite(file_path: Path, expected_hash: Optional[str] = None) -> bool` utility
  - [x] Old versions are never deleted by the pipeline — archival/cleanup is a separate concern

- [x] **Task 6: Write split datasets to Arrow IPC and Parquet** (AC: #1, #4, #6)
  - [x] File naming for split files:
    - Train: `{pair}_{start_date}_{end_date}_{timeframe}_train.arrow`
    - Test: `{pair}_{start_date}_{end_date}_{timeframe}_test.arrow`
    - Plus corresponding `.parquet` files
  - [x] All writes use crash-safe write pattern (`.partial` -> fsync -> rename)
  - [x] Arrow IPC: uncompressed, mmap-friendly (`pyarrow.ipc.new_file()`)
  - [x] Parquet: snappy compression
  - [x] Schema validation against `contracts/arrow_schemas.toml` before writing
  - [x] Split EVERY timeframe that exists (M1, M5, H1, D1, W — all outputs from Story 1.7)
    - Apply the SAME temporal split point across all timeframes
    - For coarser timeframes, the split point may land between bars — always round to the nearest bar boundary that maintains the strict temporal guarantee

- [x] **Task 7: Orchestration entry point** (AC: #1, #3, #4, #6, #7)
  - [x] Add `run_data_splitting(pair: str, storage_path: Path, config: dict) -> dict` function
  - [x] This function:
    1. Loads config including `config_hash` (from Story 1.3 config_loader)
    2. Locates all Arrow IPC files for the pair (M1, M5, H1, D1, W)
    3. Computes dataset hash from the M1 source file
    4. Generates dataset ID: `{pair}_{start_date}_{end_date}_{source}_{download_hash}`
    5. Checks if this dataset already exists (consistent sourcing — re-use if identical)
    6. Splits each timeframe at the same temporal boundary
    7. Writes train/test Arrow IPC + Parquet files
    8. Creates and writes the manifest
    9. Returns manifest dict for downstream use
  - [x] Log each step using structured JSON logging (D6):
    - Component: `data_pipeline`
    - Stage: `data_splitting`
    - Include: dataset_id, pair, split_date, train_bars, test_bars, config_hash

- [x] **Task 8: Unit tests** (AC: #1, #2, #3, #4, #5, #6, #7)
  - [x] Create `src/python/tests/test_data_pipeline/test_data_splitter.py`
  - [x] Test ratio split: 100 bars with ratio 0.7 -> 70 train, 30 test
  - [x] Test date split: bars from 2024-01-01 to 2024-12-31, split at 2024-07-01
  - [x] Test strict temporal guarantee: verify max(train.timestamp) < min(test.timestamp)
  - [x] Test no data leakage: train set contains NO timestamps >= split point
  - [x] Test determinism: split same data twice -> identical output hashes
  - [x] Create `src/python/tests/test_data_pipeline/test_dataset_hasher.py`
  - [x] Test dataset ID generation format
  - [x] Test file hashing produces consistent results
  - [x] Test existing dataset detection (file exists -> returns path)
  - [x] Test re-run consistency: same config + same data -> same dataset ID -> same files used
  - [x] Create `src/python/tests/test_data_pipeline/test_data_manifest.py`
  - [x] Test manifest creation includes all required fields
  - [x] Test manifest includes config_hash
  - [x] Test manifest includes correct file paths for all timeframes
  - [x] Test crash-safe write pattern for manifest file
  - [x] Test that writing never overwrites an existing file with a different hash

## Dev Notes

### Architecture Constraints

**D2 — Artifact Schema & Storage:** "Every dataset is identified by {pair}_{start_date}_{end_date}_{source}_{download_hash}. Re-runs against the same date range MUST use the identical Arrow IPC file (same hash). New downloads create new versioned artifacts, never overwrite existing." This is the core consistent sourcing requirement. The dataset ID + hash system ensures reproducibility.

**D7 — Configuration:** "Config hash embedded in every artifact manifest — reproducibility is verifiable. Config hash + data hash = reproducibility proof." The manifest must include both the config hash and the data hash. Together they prove that any pipeline result is traceable to its inputs.

**D2 — Storage Formats:** "Compute: Arrow IPC (mmap-friendly). Archival: Parquet (compressed)." Both formats must be produced for every split file.

**D3 — Pipeline Orchestration:** "Stages execute sequentially — inherent to the pipeline. Stages are stateless between runs — all state is in artifacts and pipeline-state.json." The splitting stage is a pure function: config + data -> split files + manifest. No internal state between runs.

**D8 — Error Handling:** "Each runtime catches errors at component boundaries, wraps in structured error type, propagates to orchestrator. Orchestrator decides response." Splitting errors (e.g., no data, invalid split point) must use structured error codes.

**Crash-Safe Write Pattern:** "All artifact writes: 1. Write to {filename}.partial, 2. Flush/fsync, 3. Atomic rename. Never overwrite a complete artifact with a partial one. If .partial exists on startup, it's from a crash — delete it and re-run."

**Data Quality Gate — Consistent Sourcing (FR8):** "Every dataset is identified by {pair}_{start_date}_{end_date}_{source}_{download_hash}. Re-runs against the same date range MUST use the identical Arrow IPC file (same hash). New downloads create new versioned artifacts, never overwrite existing." This is the foundational reproducibility guarantee.

### Technical Requirements

- **Language:** Python (orchestration tier)
- **Libraries:** `pyarrow` for Arrow/Parquet, `hashlib` for SHA-256, `tomllib` for TOML, `json` for manifests
- **Hash algorithm:** SHA-256 (standard, deterministic, collision-resistant)
- **File location:** `src/python/data_pipeline/data_splitter.py`, `src/python/data_pipeline/dataset_hasher.py`, `src/python/data_pipeline/data_manifest.py`
- **Test location:** `src/python/tests/test_data_pipeline/test_data_splitter.py`, `test_dataset_hasher.py`, `test_data_manifest.py`
- **Manifest format:** JSON (human-readable, machine-parseable)
- **Timestamp format:** Epoch microseconds int64 in Arrow, ISO 8601 in manifest JSON
- **Config hash:** Obtained from `config_loader/hasher.py` (implemented in Story 1.3)

### What to Reuse from ClaudeBackTester

**CONFIRMED by Story 1.1 review — Verdict: ADAPT split, BUILD NEW hashing/manifest**

The baseline at `ClaudeBackTester/backtester/data/splitting.py` (85 lines) has clean chronological splitting. Port the following:

- **Chronological ratio split** (`split_backforward()`): `split_idx = int(len(df) * back_pct)`, back = `df.iloc[:split_idx]`, forward = `df.iloc[split_idx:]`. Simple, correct, never shuffles. Port the logic.
- **Date-based split** (`split_holdout()`): Reserves last N months as holdout using `pd.DateOffset`. Port as the `split_mode = "date"` option.
- **Empty DataFrame handling**: Graceful return of two empty frames. Port.

**DO NOT port:**
- Pandas-only operation — adapt to use PyArrow `table.slice()` for zero-copy splitting
- No temporal guarantee assertion — add `assert max(train.timestamp) < min(test.timestamp)`
- No minimum set size validation — add configurable minimum (at least 1000 M1 bars)

**Build NEW (not in baseline):**
- Dataset ID: `{pair}_{start_date}_{end_date}_{source}_{download_hash}` (FR8)
- SHA-256 file hashing for consistent sourcing
- Manifest creation (JSON with config_hash, data_hash, split metadata, file paths)
- Versioned artifact storage (never overwrite, idempotent re-runs)
- Multi-timeframe splitting (same temporal split point across M1/M5/H1/D1/W)
- Crash-safe writes for all output files

### Anti-Patterns to Avoid

1. **Do NOT shuffle or randomly sample data.** This is financial time series data. The split MUST be strictly chronological. Any random element destroys temporal validity and introduces look-ahead bias.
2. **Do NOT use pandas for splitting.** Use PyArrow table slicing directly (`table.slice(offset, length)`) for zero-copy performance.
3. **Do NOT overwrite existing files.** The entire consistent sourcing guarantee depends on immutable artifacts. Check before writing.
4. **Do NOT compute the config hash inside this module.** Import and use the `config_loader/hasher.py` from Story 1.3. The config hash must be computed once and consistently.
5. **Do NOT create separate manifest formats for different timeframes.** One manifest per dataset covers all timeframes and splits.
6. **Do NOT split quarantined bars separately.** Quarantined bars remain in the data (they are just marked). The backtester (downstream) handles skipping them. Splitting operates on the full dataset including quarantined bars.
7. **Do NOT use floating-point split ratios for the actual split index.** Use `int(math.floor(total_rows * split_ratio))` — the split must be at a whole row boundary.
8. **Do NOT allow the test set to be empty or trivially small.** Validate that both train and test sets have a minimum number of bars (configurable, but at least 1000 M1 bars for meaningful testing).

### Project Structure Notes

```
src/python/
  data_pipeline/
    __init__.py
    downloader.py              # Story 1.4
    quality_checker.py         # Story 1.5
    arrow_converter.py         # Story 1.6
    parquet_archiver.py        # Story 1.6
    timeframe_converter.py     # Story 1.7
    data_splitter.py           # THIS STORY - new file
    dataset_hasher.py          # THIS STORY - new file
    data_manifest.py           # THIS STORY - new file (or extend artifacts/manifest.py)
  artifacts/
    manifest.py                # Story 1.3 (may already exist — coordinate)
  tests/
    test_data_pipeline/
      test_data_splitter.py    # THIS STORY - new file
      test_dataset_hasher.py   # THIS STORY - new file
      test_data_manifest.py    # THIS STORY - new file
```

Output files:
```
G:\My Drive\BackTestData\    (or configured path)
  data-pipeline/
    EURUSD_2024-01-01_2024-12-31_M1.arrow          # From Story 1.6
    EURUSD_2024-01-01_2024-12-31_M1_train.arrow     # THIS STORY
    EURUSD_2024-01-01_2024-12-31_M1_test.arrow      # THIS STORY
    EURUSD_2024-01-01_2024-12-31_H1.arrow           # From Story 1.7
    EURUSD_2024-01-01_2024-12-31_H1_train.arrow     # THIS STORY
    EURUSD_2024-01-01_2024-12-31_H1_test.arrow      # THIS STORY
    ... (same for M5, D1, W)
    EURUSD_2024-01-01_2024-12-31_dukascopy_a3b8f2c1_manifest.json  # THIS STORY
```

### References

- [Source: planning-artifacts/epics.md#Story 1.8 — Data Splitting & Consistent Sourcing]
- [Source: planning-artifacts/architecture.md#Decision 2 — Artifact Schema & Storage]
- [Source: planning-artifacts/architecture.md#Decision 3 — Pipeline Orchestration]
- [Source: planning-artifacts/architecture.md#Decision 7 — TOML Configuration]
- [Source: planning-artifacts/architecture.md#Decision 8 — Error Handling]
- [Source: planning-artifacts/architecture.md#Crash-Safe Write Pattern]
- [Source: planning-artifacts/architecture.md#Data Quality Gate — Consistent Data Sourcing (FR8)]
- [Source: planning-artifacts/architecture.md#Contracts Directory — arrow_schemas.toml]
- [Source: planning-artifacts/prd.md#FR7 — Chronological train/test splitting]
- [Source: planning-artifacts/prd.md#FR8 — Consistent data sourcing]
- [Source: planning-artifacts/prd.md#FR58 — Versioned artifacts at every stage]
- [Source: planning-artifacts/prd.md#FR59 — Explicit configuration for traceability]
- [Source: planning-artifacts/prd.md#FR61 — Deterministic, consistent behavior]
- [Source: planning-artifacts/baseline-to-architecture-mapping.md#data_pipeline — Keep and adapt]

## Change Log

- 2026-03-14: Story 1.8 implemented — data splitting, dataset hashing, manifest creation, orchestrator, 53 unit tests, 8 live tests. All 226 tests pass (0 regressions).

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Completion Notes List
- **Task 1:** Added `[data_pipeline.splitting]` section to `config/base.toml` (split_ratio, split_mode, split_date) and schema validation in `config/schema.toml` (min/max bounds, allowed values).
- **Task 2:** Created `dataset_hasher.py` with `compute_dataset_id()` (truncated 8-char hash), `compute_file_hash()` (SHA-256 64KB chunks), `check_existing_dataset()` (manifest-based lookup), and `ensure_no_overwrite()` (AC #5 never-overwrite guard).
- **Task 3:** Created `data_splitter.py` with `split_train_test()` supporting ratio mode (PyArrow `table.slice()` zero-copy) and date mode (timestamp filtering via `pyarrow.compute`). Strict temporal guarantee enforced: `max(train.ts) < min(test.ts)`. SplitError for structured error handling (D8). Supports explicit `split_timestamp_us` for multi-timeframe consistency.
- **Task 4:** Created `data_manifest.py` with `create_data_manifest()` (JSON structure matching spec) and `write_manifest()` (crash-safe via `artifacts.storage`). Manifest includes dataset_id, config_hash, data_hash, split metadata, file paths for all timeframes.
- **Task 5:** `ensure_no_overwrite()` in dataset_hasher.py implements the 3-way check: new file → write, existing+matching hash → skip, existing+different hash → raise ValueError. Each paired artifact (Arrow+Parquet) checked independently per lesson from Story 1.7.
- **Task 6:** Crash-safe Arrow IPC (`pyarrow.ipc.new_file()` + `.partial` → fsync → rename) and Parquet (snappy compression) writers. All timeframes split at the same M1-determined temporal boundary. File naming: `{pair}_{start}_{end}_{TF}_{train|test}.{arrow|parquet}`.
- **Task 7:** `run_data_splitting()` orchestrator: finds source files by glob pattern, computes M1 hash → dataset ID, checks for existing manifest (idempotent re-runs), splits all timeframes at same boundary, writes all outputs, creates manifest. Config hash from `config_loader.hasher`. Structured JSON logging at every step.
- **Task 8:** 53 unit tests across 3 test files covering all ACs. Key tests: ratio/date split correctness, temporal guarantee, no data leakage, determinism, empty table guard, ensure_no_overwrite, manifest completeness, crash-safe writes.
- **Live Tests:** 8 `@pytest.mark.live` integration tests: full pipeline end-to-end, Arrow IPC readability via mmap, temporal guarantee on disk, idempotent re-runs, deterministic hashes, crash-safe writes for Arrow/Parquet/manifest.
- **Lessons Applied:** Independent paired-artifact checking (Story 1.7 lesson), empty-table guards before min/max (Story 1.7 lesson).

### File List
**New files:**
- `src/python/data_pipeline/dataset_hasher.py`
- `src/python/data_pipeline/data_splitter.py`
- `src/python/data_pipeline/data_manifest.py`
- `src/python/tests/test_data_pipeline/test_dataset_hasher.py`
- `src/python/tests/test_data_pipeline/test_data_splitter.py`
- `src/python/tests/test_data_pipeline/test_data_manifest.py`
- `src/python/tests/test_data_pipeline/test_data_splitter_live.py`

**Modified files:**
- `config/base.toml` — added `[data_pipeline.splitting]` section
- `config/schema.toml` — added splitting validation rules
- `src/python/data_pipeline/__init__.py` — added exports for new modules
