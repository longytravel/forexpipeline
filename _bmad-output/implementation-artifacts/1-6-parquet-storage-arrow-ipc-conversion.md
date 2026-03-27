# Story 1.6: Parquet Storage & Arrow IPC Conversion

Status: review

## Story

As the **operator**,
I want validated data stored in Parquet for archival and converted to Arrow IPC for compute,
So that data is efficiently accessible for both long-term storage and high-performance backtesting.

## Acceptance Criteria

1. **Given** data has been validated and scored (Story 1.5)
   **When** storage conversion runs
   **Then** validated data is stored in Parquet format with compression (FR5)

2. **And** data is converted to Arrow IPC format with the schema defined in `contracts/arrow_schemas.toml` — including session column computed from config schedule and quarantined column

3. **And** the session column is correctly stamped on every bar (or tick) based on the session schedule in `config/base.toml` (Architecture: session-awareness)

4. **And** Arrow IPC files are mmap-friendly for zero-copy access by Rust

5. **And** both Parquet and Arrow IPC files use crash-safe write pattern (NFR15)

6. **And** the Arrow IPC schema matches the contract definition exactly — any mismatch fails loud

7. **And** files are written to the configured storage path (`G:\My Drive\BackTestData`)

## Tasks / Subtasks

- [x] **Task 1: Implement Arrow schema loader from contracts** (AC: #2, #6)
  - [x] 1.1 Create `src/python/data_pipeline/schema_loader.py` with function `load_arrow_schema(contracts_path: Path, schema_name: str) -> pa.Schema`:
    - Reads `contracts/arrow_schemas.toml`
    - Parses the `[market_data]` section (or specified schema_name)
    - Maps TOML type strings to PyArrow types: `"int64"` → `pa.int64()`, `"float64"` → `pa.float64()`, `"utf8"` → `pa.utf8()`, `"bool"` → `pa.bool_()`
    - Constructs and returns a `pyarrow.Schema` object with nullable flags set per contract
  - [x] 1.2 Implement `validate_dataframe_against_schema(df: pd.DataFrame, schema: pa.Schema) -> List[str]`:
    - Verifies that the DataFrame has exactly the columns specified in the schema
    - Verifies column types are compatible (or can be safely cast)
    - Returns list of mismatches. Empty list = valid. Any mismatch MUST fail loud — raise `SchemaValidationError` with detailed message.
  - [x] 1.3 The `[market_data]` schema from `contracts/arrow_schemas.toml` defines these columns:
    ```
    timestamp    int64     (epoch microseconds UTC, not nullable)
    open         float64   (not nullable)
    high         float64   (not nullable)
    low          float64   (not nullable)
    close        float64   (not nullable)
    bid          float64   (not nullable)
    ask          float64   (not nullable)
    session      utf8      (not nullable, values: asian/london/new_york/london_ny_overlap/off_hours)
    quarantined  bool      (not nullable, default false)
    ```

- [x] **Task 2: Implement session column stamping** (AC: #3)
  - [x] 2.1 Reuse the `session_labeler.py` from Story 1.5 — import `assign_sessions_bulk(df, session_schedule)`
  - [x] 2.2 In the conversion pipeline, if the validated DataFrame from Story 1.5 already has a `session` column, verify it matches the expected values from `contracts/session_schema.toml`. If no session column exists, compute it using `assign_sessions_bulk()`.
  - [x] 2.3 Validate session values are within the allowed set: `["asian", "london", "new_york", "london_ny_overlap", "off_hours"]` per `contracts/session_schema.toml`. Fail loud on any unknown session value.

- [x] **Task 3: Implement timestamp conversion** (AC: #2)
  - [x] 3.1 Implement `src/python/data_pipeline/arrow_converter.py` with class `ArrowConverter`
  - [x] 3.2 Implement `ArrowConverter.__init__(self, config: dict, logger: logging.Logger)` — loads session schedule, schema, and storage path from config
  - [x] 3.3 Implement `ArrowConverter._convert_timestamps_to_epoch_micros(self, df: pd.DataFrame) -> pd.Series`:
    - Convert pandas datetime64 timestamps to int64 epoch microseconds (microseconds since 1970-01-01 UTC)
    - Per architecture: "Arrow IPC columns use int64 epoch microseconds"
    - Formula: `(timestamp - pd.Timestamp('1970-01-01', tz='UTC')).total_seconds() * 1_000_000` — vectorized
    - Verify no overflow for expected date ranges (1970-2100 fits comfortably in int64)

- [x] **Task 4: Implement Arrow IPC file writer** (AC: #2, #4, #5, #6)
  - [x] 4.1 Implement `ArrowConverter._prepare_arrow_table(self, df: pd.DataFrame, schema: pa.Schema) -> pa.Table`:
    - Convert validated DataFrame to PyArrow Table
    - Ensure timestamp column is int64 epoch microseconds (from Task 3)
    - Ensure session column is utf8 string
    - Ensure quarantined column is bool
    - Cast all numeric columns to float64
    - Apply the exact schema from contracts — `pa.Table.from_pandas(df, schema=schema, preserve_index=False)`
    - Validate the resulting table's schema matches the contract schema exactly
  - [x] 4.2 Implement `ArrowConverter._write_arrow_ipc(self, table: pa.Table, output_path: Path) -> Path`:
    - Write Arrow IPC file using `pyarrow.ipc.new_file()` writer
    - Use IPC file format (not stream format) for mmap compatibility — `pa.ipc.new_file(sink, schema)` produces a file that can be mmap'd
    - Use crash-safe write pattern:
      1. Write to `{output_path}.partial`
      2. Flush and close the writer
      3. `os.fsync()` the file descriptor
      4. `os.rename('{output_path}.partial', output_path)`
    - Log file size after write at INFO level
  - [x] 4.3 Implement `ArrowConverter._verify_arrow_ipc(self, path: Path, expected_schema: pa.Schema) -> bool`:
    - Re-read the written Arrow IPC file using `pa.ipc.open_file(pa.memory_map(str(path), 'r'))`
    - Verify schema matches expected schema exactly
    - Verify row count matches expected count
    - Verify the file can be memory-mapped (mmap access works)
    - Return True if all checks pass, raise on failure
    - This verification step is critical — it proves the file is mmap-friendly and schema-correct

- [x] **Task 5: Implement Parquet archival writer** (AC: #1, #5)
  - [x] 5.1 Create `src/python/data_pipeline/parquet_archiver.py` with class `ParquetArchiver`
  - [x] 5.2 Implement `ParquetArchiver.__init__(self, config: dict, logger: logging.Logger)`
  - [x] 5.3 Implement `ParquetArchiver.write_parquet(self, table: pa.Table, output_path: Path, compression: str = "snappy") -> Path`:
    - Write Parquet file using `pyarrow.parquet.write_table(table, path, compression=compression)`
    - Use crash-safe write pattern: write to `.partial`, fsync, rename
    - Supported compression: `"snappy"` (fast, good for local), `"zstd"` (better ratio for archival)
    - Default to `"snappy"` — configurable via `config.data_pipeline.parquet_compression`
    - Log compression ratio and file size at INFO level
  - [x] 5.4 Implement `ParquetArchiver._verify_parquet(self, path: Path, expected_schema: pa.Schema, expected_rows: int) -> bool`:
    - Re-read Parquet file and verify schema and row count
    - Return True on success, raise on failure

- [x] **Task 6: Implement conversion orchestration** (AC: all)
  - [x] 6.1 Implement `ArrowConverter.convert(self, validated_df: pd.DataFrame, pair: str, resolution: str, start_date: date, end_date: date, dataset_id: str, version: str, quality_score: float, rating: str) -> ConversionResult` where `ConversionResult = namedtuple('ConversionResult', ['arrow_path', 'parquet_path', 'manifest_path', 'row_count', 'arrow_size_mb', 'parquet_size_mb'])`:
    - Full conversion pipeline:
      1. Load schema from `contracts/arrow_schemas.toml`
      2. Ensure session column exists and is correct (stamp if needed)
      3. Ensure quarantined column exists (from Story 1.5)
      4. Convert timestamps to epoch microseconds
      5. Build PyArrow Table with contract schema
      6. Validate schema match — fail loud on mismatch
      7. Write Arrow IPC file to `{storage_path}/arrow/{dataset_id}/{version}/market-data.arrow`
      8. Write Parquet file to `{storage_path}/parquet/{dataset_id}/{version}/market-data.parquet`
      9. Verify both files
      10. Write conversion manifest
    - Log summary: row count, Arrow IPC size, Parquet size, compression ratio
  - [x] 6.2 Implement `ArrowConverter._write_conversion_manifest(self, ...) -> Path`:
    - Write `manifest.json` at `{storage_path}/arrow/{dataset_id}/{version}/manifest.json`
    - Contents:
      ```python
      {
        "dataset_id": "EURUSD_2015-01-01_2025-12-31_M1",
        "version": "v001",
        "pair": "EURUSD",
        "resolution": "M1",
        "date_range": {"start": "2015-01-01", "end": "2025-12-31"},
        "row_count": 5260000,
        "arrow_ipc": {
          "path": "market-data.arrow",
          "size_bytes": 41943040,
          "schema_contract": "contracts/arrow_schemas.toml#market_data",
          "mmap_verified": true
        },
        "parquet": {
          "path": "../../parquet/EURUSD_2015-01-01_2025-12-31_M1/v001/market-data.parquet",
          "size_bytes": 4194304,
          "compression": "snappy"
        },
        "quality_score": 0.97,
        "quality_rating": "GREEN",
        "data_hash": "sha256:abc123...",
        "config_hash": "sha256:def456...",
        "session_schedule_hash": "sha256:789...",
        "conversion_timestamp": "2026-03-14T10:45:00Z",
        "quarantined_bar_count": 42,
        "session_distribution": {
          "asian": 1200000,
          "london": 1400000,
          "new_york": 1300000,
          "london_ny_overlap": 560000,
          "off_hours": 800000
        }
      }
      ```
    - Use crash-safe write pattern
  - [x] 6.3 Create `src/python/data_pipeline/converter_cli.py` with function `run_conversion(config: dict) -> dict`:
    - Entry point: load validated data from Story 1.5 output, run conversion, return summary
    - Log at INFO level: "Conversion complete: {pair} {resolution} → Arrow IPC ({size}MB) + Parquet ({size}MB)"

- [x] **Task 7: Add data pipeline config for storage and conversion** (AC: #7)
  - [x] 7.1 Add to `config/base.toml` under `[data_pipeline]`:
    ```toml
    [data_pipeline.storage]
    arrow_ipc_path = "G:\\My Drive\\BackTestData\\arrow"
    parquet_path = "G:\\My Drive\\BackTestData\\parquet"

    [data_pipeline.parquet]
    compression = "snappy"  # options: snappy, zstd, gzip, none
    ```
  - [x] 7.2 Add schema validation for these config keys

- [x] **Task 8: Implement data hash computation** (AC: #6 — manifest integrity)
  - [x] 8.1 Implement `ArrowConverter._compute_data_hash(self, table: pa.Table) -> str`:
    - Serialize the Arrow Table to bytes (using `pa.ipc.serialize_schema()` + record batch serialization)
    - Compute SHA-256 hash
    - Return as `"sha256:{hex_digest}"`
    - This hash is stored in the manifest for reproducibility verification (FR8)
  - [x] 8.2 Implement `ArrowConverter._compute_session_schedule_hash(self, session_schedule: dict) -> str`:
    - Hash the session schedule config used for session column computation
    - If session schedule changes, downstream data must be regenerated

- [x] **Task 9: Write unit and integration tests** (AC: all)
  - [x] 9.1 Create `src/python/tests/test_data_pipeline/test_arrow_converter.py`
  - [x] 9.2 Create `src/python/tests/test_data_pipeline/test_parquet_archiver.py`
  - [x] 9.3 Create `src/python/tests/test_data_pipeline/test_schema_loader.py`
  - [x] 9.4 Unit test: `test_load_arrow_schema` — verify schema loads from contracts TOML and produces correct PyArrow schema
  - [x] 9.5 Unit test: `test_schema_type_mapping` — verify each TOML type string maps to correct PyArrow type
  - [x] 9.6 Unit test: `test_validate_dataframe_matching_schema` — verify clean DataFrame passes validation
  - [x] 9.7 Unit test: `test_validate_dataframe_missing_column` — verify mismatch detection for missing columns
  - [x] 9.8 Unit test: `test_validate_dataframe_wrong_type` — verify mismatch detection for wrong types
  - [x] 9.9 Unit test: `test_convert_timestamps_to_epoch_micros` — verify conversion with known values (e.g., `2026-01-01T00:00:00Z` → known epoch microseconds)
  - [x] 9.10 Unit test: `test_session_column_stamping` — verify session assignment produces correct values for timestamps in each session
  - [x] 9.11 Unit test: `test_session_overlap_handling` — verify 13:00-16:00 UTC produces `"london_ny_overlap"`
  - [x] 9.12 Unit test: `test_arrow_table_schema_exact_match` — verify constructed table schema matches contract exactly
  - [x] 9.13 Integration test: `test_write_arrow_ipc_mmap` — write Arrow IPC file, reopen via mmap, verify data integrity
  - [x] 9.14 Integration test: `test_write_arrow_ipc_crash_safe` — verify .partial → rename pattern
  - [x] 9.15 Integration test: `test_write_parquet_roundtrip` — write Parquet, read back, verify data and schema match
  - [x] 9.16 Integration test: `test_parquet_compression` — verify compressed file is smaller than uncompressed
  - [x] 9.17 Integration test: `test_full_conversion_pipeline` — run full conversion on a small test fixture, verify both Arrow IPC and Parquet outputs, verify manifest contents
  - [x] 9.18 Integration test: `test_conversion_manifest_completeness` — verify manifest contains all required fields
  - [x] 9.19 Integration test: `test_data_hash_determinism` — same input produces identical hash across two conversion runs
  - [x] 9.20 Unit test: `test_session_schema_validation` — verify session values are validated against contract

## Dev Notes

### Architecture Constraints

**D1 (System Topology — Multi-Process with Arrow IPC):** "Arrow IPC files are the IPC mechanism for batch compute — no serialization, both runtimes mmap the same files." The Arrow IPC files produced here MUST be mmap-friendly. Use `pyarrow.ipc.new_file()` (file format, not stream format). Verify with `pa.memory_map()`.

**D2 (Artifact Schema & Storage — Arrow IPC / SQLite / Parquet Hybrid):** "Three-format storage strategy, each format doing what it's best at."
- "Compute: Arrow IPC — Rust batch binary writes results at full SIMD speed. mmap-friendly, bulk, immutable"
- "Archival: Parquet — Long-term compressed cold storage. SQLite is rebuildable from Arrow/Parquet"
- Data flow: "Rust batch → Arrow IPC (fast, bulk, canonical) → Python ingest → SQLite (queryable) → Archival → Parquet (compressed, cold storage)"

**D7 (Configuration):** Session schedule is in `config/base.toml [sessions]`. Storage paths are configurable. "Config hash embedded in every artifact manifest — reproducibility is verifiable."

**Architecture — Contracts Directory:** "`contracts/` directory is the single source of truth for cross-runtime type definitions. Each file defines schemas that all runtimes must conform to." The Arrow IPC schema MUST be loaded from `contracts/arrow_schemas.toml`, not hardcoded. "Runtime-specific types are generated or manually aligned from these."

**Architecture — Crash-Safe Write Pattern:** "All artifact writes across all runtimes follow: 1. Write to `{filename}.partial` 2. Flush / fsync 3. Atomic rename to `{filename}`." Both Arrow IPC and Parquet files MUST use this pattern.

**Architecture — Timestamp Formats:** "Arrow IPC columns: int64 epoch microseconds" — `1741875720123000`. This is a hard requirement. Pandas datetime64 must be converted to epoch microseconds before writing to Arrow.

**Architecture — Session-Awareness:** "`data_pipeline/arrow_converter.py` stamps each M1 bar with its session(s) based on config schedule." This is the exact file where session stamping happens.

**Architecture — Data Volume Modeling:** "1 year EURUSD M1 bid+ask: ~525,600 bars, ~40 MB Arrow IPC, ~4 MB Parquet." "10 years: ~5.26M bars, ~400 MB Arrow IPC, ~40 MB Parquet." These are the expected sizes — verify output is in the right ballpark.

### Technical Requirements

- **Python libraries:** `pyarrow` for Arrow IPC and Parquet operations, `pandas` for DataFrame manipulation, `tomllib` (Python 3.11+ stdlib) or `tomli` for TOML parsing
- **PyArrow version:** Must support IPC file format with mmap. Any recent version (>= 10.0) works.
- **Arrow IPC file format vs stream format:** Use `pa.ipc.new_file()` — NOT `pa.ipc.new_stream()`. File format supports random access and mmap. Stream format does not support mmap.
- **mmap verification:** After writing, verify the file works with `pa.memory_map(str(path), 'r')` followed by `pa.ipc.open_file()`. This is how Rust will access the data.
- **Parquet compression options:** `snappy` (default, fast), `zstd` (better ratio), `gzip` (widely compatible), `none` (no compression). Configure via `config.data_pipeline.parquet.compression`.
- **Schema enforcement:** Use `pa.Table.from_pandas(df, schema=schema, preserve_index=False)` to ensure exact schema match. If types don't match, this will raise — which is the desired behavior (fail loud).
- **File sizes:** 10 years of M1 data → ~400 MB Arrow IPC, ~40 MB Parquet. Ensure the code handles files of this size without running out of memory. PyArrow handles this well natively.

### What to Reuse from ClaudeBackTester

**CONFIRMED by Story 1.1 review — Verdict: BUILD NEW (Arrow IPC), ADAPT (Parquet)**

The baseline stores data in Parquet on Google Drive using `pyarrow` engine with snappy compression. Reviewed at `ClaudeBackTester/backtester/data/downloader.py` (`save_chunk()`, `consolidate_chunks()`).

- **Parquet writing pattern** — reusable: `df.to_parquet(path, engine="pyarrow", compression="snappy")` with atomic `.tmp` → `replace()`. Adapt to add `os.fsync()` and schema validation.
- **No Arrow IPC usage** anywhere in baseline — entirely new.
- **No schema contracts** — data format is implicit (whatever columns pandas produces). Build schema loading from `contracts/arrow_schemas.toml` from scratch.
- **No session column** — entirely new. Session labeler from Story 1.5 stamps this.
- **No mmap verification** — entirely new. Critical for Rust compute layer.

**Build NEW:**
- Arrow IPC file writer with mmap verification (`pa.ipc.new_file()`, not stream format)
- Schema loader from `contracts/arrow_schemas.toml`
- Schema validation (fail loud on mismatch)
- Conversion manifest with hashes (data_hash, config_hash, session_schedule_hash)
- Timestamp conversion to int64 epoch microseconds

### Anti-Patterns to Avoid

1. **Do NOT use Arrow IPC stream format.** Use file format (`pa.ipc.new_file()`) — stream format cannot be mmap'd. The Rust compute layer depends on mmap access.
2. **Do NOT hardcode the Arrow schema.** Load it from `contracts/arrow_schemas.toml`. The contracts directory is the single source of truth. If a dev hardcodes the schema, it will drift from the Rust side.
3. **Do NOT write timestamps as datetime objects in Arrow.** They must be `int64` epoch microseconds. Rust reads `int64` and interprets as epoch micros — not Arrow's native timestamp type, because that introduces timezone handling complexity at the Rust boundary.
4. **Do NOT skip mmap verification.** If the Arrow IPC file can't be mmap'd, the entire Rust compute layer breaks. Verify after every write.
5. **Do NOT write Parquet without compression.** The architecture explicitly specifies compressed Parquet for archival. Default to snappy.
6. **Do NOT omit the session column or quarantined column.** The contract schema requires both. Downstream stories (backtester, analytics) depend on them.
7. **Do NOT compute session labels differently than Story 1.5.** Reuse `session_labeler.py` — same function, same logic. If you reimplement it, session labels may differ between quality checking and Arrow IPC stamping.
8. **Do NOT skip crash-safe writes for "small" files like manifests.** ALL artifact writes use the pattern. No exceptions.
9. **Do NOT store Arrow IPC and Parquet in the same directory.** They have separate paths: `{storage_path}/arrow/...` and `{storage_path}/parquet/...` per the architecture's directory structure.

### Project Structure Notes

```
src/python/
  data_pipeline/
    __init__.py              # (from Story 1.4)
    downloader.py            # (from Story 1.4)
    cli.py                   # (from Story 1.4)
    quality_checker.py       # (from Story 1.5)
    session_labeler.py       # (from Story 1.5 — reused here)
    validator_cli.py         # (from Story 1.5)
    schema_loader.py         # NEW — loads Arrow schemas from contracts/
    arrow_converter.py       # NEW — ArrowConverter class
    parquet_archiver.py      # NEW — ParquetArchiver class
    converter_cli.py         # NEW — run_conversion() entry point
  tests/
    test_data_pipeline/
      __init__.py
      test_arrow_converter.py    # NEW
      test_parquet_archiver.py   # NEW
      test_schema_loader.py      # NEW
```

Output artifacts:
```
{storage_path}/
  arrow/
    {dataset_id}/
      v001/
        market-data.arrow        # Arrow IPC file (mmap-friendly)
        manifest.json            # Conversion manifest with hashes
  parquet/
    {dataset_id}/
      v001/
        market-data.parquet      # Compressed Parquet archival
```

The `contracts/arrow_schemas.toml` file should already exist from Story 1.3 with the `[market_data]` schema. This story reads it — does not create it.

### References

- [Source: planning-artifacts/epics.md — Story 1.6 acceptance criteria]
- [Source: planning-artifacts/architecture.md — D1 (Multi-Process with Arrow IPC — "both runtimes mmap the same files")]
- [Source: planning-artifacts/architecture.md — D2 (Artifact Schema & Storage — three-format strategy, directory structure)]
- [Source: planning-artifacts/architecture.md — D7 (Configuration — config hash in manifests)]
- [Source: planning-artifacts/architecture.md — Session-Awareness Architecture ("data_pipeline/arrow_converter.py stamps each M1 bar")]
- [Source: planning-artifacts/architecture.md — Contracts Directory Content (arrow_schemas.toml market_data schema)]
- [Source: planning-artifacts/architecture.md — Crash-Safe Write Pattern]
- [Source: planning-artifacts/architecture.md — Format Patterns — Timestamp Formats ("Arrow IPC columns: int64 epoch microseconds")]
- [Source: planning-artifacts/architecture.md — Data Volume Modeling (sizing expectations)]
- [Source: planning-artifacts/architecture.md — Implementation Patterns — Enforcement Guidelines ("Use contracts/ schema definitions as source of truth")]
- [Source: planning-artifacts/architecture.md — contracts/session_schema.toml (session column spec)]
- [Source: planning-artifacts/prd.md — FR5 (Parquet storage), FR8 (consistent data sourcing with hash identification)]
- [Source: planning-artifacts/prd.md — NFR15 (crash-safe write semantics)]
- [Source: planning-artifacts/prd.md — Hardware Context (data stored on Google Drive G:\My Drive\BackTestData)]
- [Source: planning-artifacts/baseline-to-architecture-mapping.md — data_pipeline "Keep and adapt"]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Completion Notes List
- **Task 1**: Created `schema_loader.py` — loads Arrow schemas from `contracts/arrow_schemas.toml`, maps TOML type strings to PyArrow types, validates DataFrames against schema with fail-loud `SchemaValidationError`. 11 unit tests pass.
- **Task 2**: Session column stamping in `ArrowConverter._ensure_session_column()` — reuses `session_labeler.py` `assign_sessions_bulk()`. Validates existing session values against allowed set, computes if missing. Fail-loud on unknown values.
- **Task 3**: Timestamp conversion `_convert_timestamps_to_epoch_micros()` — handles both pandas 3.0 (datetime64[us]) and older (datetime64[ns]) resolutions. Verified with known epoch values.
- **Task 4**: Arrow IPC writer — `_prepare_arrow_table()` enforces exact contract schema via `pa.Table.from_pandas(schema=...)`. `_write_arrow_ipc()` uses `pa.ipc.new_file()` (file format, NOT stream) with crash-safe .partial→rename pattern. `_verify_arrow_ipc()` re-reads via `pa.memory_map()` to prove mmap-friendly.
- **Task 5**: `ParquetArchiver` — crash-safe Parquet writes with configurable compression (snappy/zstd/gzip/none). Logs compression ratio. Verification via re-read.
- **Task 6**: `ArrowConverter.convert()` orchestrates full pipeline: schema load → session stamp → quarantine ensure → timestamp convert → Arrow Table build → Arrow IPC write → Parquet write → verify both → manifest write. Returns `ConversionResult` namedtuple. `converter_cli.py` provides `run_conversion()` entry point.
- **Task 7**: Added `[data_pipeline.storage]` and `[data_pipeline.parquet]` sections to `config/base.toml` with arrow/parquet paths and compression config.
- **Task 8**: `_compute_data_hash()` serializes Arrow Table to IPC stream bytes → SHA-256. `_compute_session_schedule_hash()` hashes canonical JSON of session schedule. Both stored in manifest for reproducibility (FR8).
- **Task 9**: 36 unit/integration tests across 3 test files + 3 `@pytest.mark.live` tests. All pass. 98 total tests pass with zero regressions.
- **Bug fix**: Pandas 3.0 uses datetime64[us] (not [ns]), so `_convert_timestamps_to_epoch_micros` detects resolution and adjusts accordingly.

### Implementation Plan
- Built new: schema_loader, arrow_converter (IPC writer + mmap verify), parquet_archiver, converter_cli
- Reused: session_labeler.py (assign_sessions_bulk), artifacts/storage.py (crash_safe_write), config_loader/hasher.py (compute_config_hash)
- Architecture compliance: D1 (mmap-friendly IPC file format), D2 (three-format storage), D7 (config hash in manifests), crash-safe writes, int64 epoch microseconds timestamps, schema loaded from contracts/ (not hardcoded)

### Change Log
- 2026-03-14: Story 1.6 implemented — Parquet storage + Arrow IPC conversion with full test coverage
- 2026-03-14: Fixed pythonpath in pyproject.toml so pytest discovers packages (was blocking all test collection)

### File List
- `src/python/data_pipeline/schema_loader.py` — NEW: Arrow schema loader from contracts
- `src/python/data_pipeline/arrow_converter.py` — NEW: ArrowConverter class (IPC writer, mmap verify, session stamp, timestamp convert, hash, manifest, orchestration)
- `src/python/data_pipeline/parquet_archiver.py` — NEW: ParquetArchiver class (crash-safe Parquet writes)
- `src/python/data_pipeline/converter_cli.py` — NEW: run_conversion() entry point
- `src/python/data_pipeline/__init__.py` — MODIFIED: added exports for new modules
- `config/base.toml` — MODIFIED: added [data_pipeline.storage] and [data_pipeline.parquet] sections
- `src/python/tests/test_data_pipeline/test_schema_loader.py` — NEW: 11 unit tests
- `src/python/tests/test_data_pipeline/test_arrow_converter.py` — NEW: 18 unit/integration tests
- `src/python/tests/test_data_pipeline/test_parquet_archiver.py` — NEW: 7 unit/integration tests
- `src/python/tests/test_data_pipeline/test_arrow_converter_live.py` — NEW: 3 @pytest.mark.live integration tests
- `src/python/pyproject.toml` — MODIFIED: added [build-system], [tool.setuptools.packages.find], and pythonpath for pytest
