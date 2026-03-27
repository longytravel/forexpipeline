# Story 1.4: Dukascopy Data Download

Status: done

## Story

As the **operator**,
I want to download historical data from Dukascopy — either M1 bars or tick data — with incremental updates,
So that I have complete, up-to-date market data at the resolution I need for my strategy type.

## Acceptance Criteria

1. **Given** a pair, date range, and data resolution (M1 or tick) are specified in config, with storage path `G:\My Drive\BackTestData` (configurable)
   **When** the data download is executed
   **Then** data is downloaded from Dukascopy at the requested resolution (FR1)

2. **And** M1 mode downloads aggregated M1 bid+ask bars (default, smaller, faster)

3. **And** tick mode downloads individual bid/ask ticks (optional, for scalping strategies)

4. **And** all timestamps are UTC, monotonically increasing

5. **And** if data already exists for part of the requested range, only the missing period is downloaded (incremental update)

6. **And** the incremental data is validated before merging with existing data (no gap between existing and new)

7. **And** a new versioned dataset artifact is created — the previous version is preserved, never overwritten

8. **And** download progress is logged with estimated size and time remaining

9. **And** if Dukascopy is unavailable, the system degrades gracefully — uses cached data if available, alerts on what it couldn't fetch (NFR20)

10. **And** download requests have configurable timeouts (NFR21)

## Tasks / Subtasks

- [x] **Task 1: Define data download config schema in `config/base.toml`** (AC: #1, #2, #3, #10)
  - [x] 1.1 Add `[data_pipeline]` section to `config/base.toml` with keys: `storage_path` (default `"G:\\My Drive\\BackTestData"`), `default_resolution` (default `"M1"`), `download_timeout_seconds` (default `30`), `request_delay_seconds` (default `0.5`), `max_retries` (default `3`), `retry_backoff_factor` (default `2.0`)
  - [x] 1.2 Add `[data_pipeline.download]` section with keys: `pairs` (list, e.g. `["EURUSD"]`), `start_date` (ISO 8601, e.g. `"2015-01-01"`), `end_date` (ISO 8601, e.g. `"2025-12-31"`), `resolution` (`"M1"` or `"tick"`)
  - [x] 1.3 Add schema validation rules in `config/schema.toml` for these keys — `resolution` must be one of `["M1", "tick"]`, `storage_path` must be a valid directory, dates must parse as ISO 8601
  - [x] 1.4 Validate config loads correctly via the config_loader from Story 1.3 — fail loud on invalid values

- [x] **Task 2: Implement Dukascopy download client** (AC: #1, #2, #3, #4, #8, #9, #10)
  - [x] 2.1 Create `src/python/data_pipeline/__init__.py`
  - [x] 2.2 Create `src/python/data_pipeline/downloader.py` with class `DukascopyDownloader`
  - [x] 2.3 Implement `DukascopyDownloader.__init__(self, config: dict, logger: logging.Logger)` — takes loaded config and structured logger
  - [x] 2.4 Implement `DukascopyDownloader._download_year(self, pair: str, year: int, offer_side: str) -> Optional[pd.DataFrame]` — downloads one year of M1 data for a single offer side (bid or ask) using `dukascopy_python.fetch()` with `INTERVAL_MIN_1`. Handles: date range clamping (don't request future dates), retry via library's `max_retries` parameter, configurable timeout. Returns DataFrame or None if no data. Pattern adapted from ClaudeBackTester `download_year()`.
  - [x] 2.5 Implement `DukascopyDownloader._download_year_bidask(self, pair: str, year: int) -> Optional[pd.DataFrame]` — downloads both bid and ask sides for a year, combines into single DataFrame with columns: `timestamp`, `open`, `high`, `low`, `close`, `volume` (from bid side), `bid` (bid-side close), `ask` (ask-side close). Uses configurable delay between bid/ask requests (default 1 second). Adapted from ClaudeBackTester `_add_spread()` pattern but retains separate bid/ask instead of computing spread.
  - [x] 2.6 Implement `DukascopyDownloader._download_tick_data(self, pair: str, start: datetime, end: datetime) -> Optional[pd.DataFrame]` — downloads tick-level data using `dukascopy_python.fetch()` with `INTERVAL_TICK`. Returns DataFrame with columns: `timestamp`, `bid`, `ask`, `bid_volume`, `ask_volume`. Only used when `resolution = "tick"` in config.
  - [x] 2.7 Implement `DukascopyDownloader.download(self, pair: str, start_date: date, end_date: date, resolution: str) -> pd.DataFrame` — main download method. For M1: iterates over each year in the date range, calls `_download_year_bidask()`, saves yearly chunks. For tick: calls `_download_tick_data()` directly. Logs progress with estimated time remaining (AC #8). Returns consolidated DataFrame.
  - [x] 2.8 Implement yearly chunk save and consolidation — adapted from ClaudeBackTester pattern: `save_chunk()` saves each year as `{pair}_M1_chunks/{pair}_M1_{year}.parquet` using crash-safe write (`.partial` → fsync → `os.replace()`). `consolidate_chunks()` merges all years, deduplicates, sorts by timestamp.
  - [x] 2.9 Implement resume support — `get_downloaded_years()` checks which yearly chunks already exist. Skip already-downloaded years except current year (always re-download for incremental updates). Adapted from ClaudeBackTester `download_pair()`.
  - [x] 2.10 Implement graceful degradation (AC #9): if Dukascopy is unreachable after all retries, log WARNING with the failed date range, continue downloading remaining years, return partial data with metadata indicating which periods failed. Emit structured log with error code `EXTERNAL_DUKASCOPY_TIMEOUT`.

- [x] **Task 3: Implement incremental download logic** (AC: #5, #6)
  - [x] 3.1 Implement `DukascopyDownloader._detect_existing_data(self, pair: str, storage_path: Path) -> Optional[Tuple[date, date]]` — scans storage path for existing raw data files for the pair. Returns the date range covered by existing data, or None if no data exists.
  - [x] 3.2 Implement `DukascopyDownloader._compute_missing_ranges(self, requested_start: date, requested_end: date, existing_start: Optional[date], existing_end: Optional[date]) -> List[Tuple[date, date]]` — determines which date ranges need downloading. Only downloads the gaps.
  - [x] 3.3 Implement `DukascopyDownloader._validate_merge_boundary(self, existing_df: pd.DataFrame, new_df: pd.DataFrame) -> bool` — validates no gap exists between the end of existing data and start of new data. Gaps > 5 minutes (excluding known weekend gaps) are flagged. Returns True if merge is clean.
  - [x] 3.4 Implement `DukascopyDownloader._merge_data(self, existing_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame` — merges existing and new data, sorts by timestamp, removes any duplicate timestamps. Verifies monotonically increasing timestamps after merge (AC #4).

- [x] **Task 4: Implement versioned artifact storage** (AC: #7)
  - [x] 4.1 Implement `DukascopyDownloader._generate_dataset_id(self, pair: str, start_date: date, end_date: date, resolution: str) -> str` — generates dataset identifier: `{pair}_{start_date}_{end_date}_{resolution}` (e.g., `EURUSD_2015-01-01_2025-12-31_M1`)
  - [x] 4.2 Implement `DukascopyDownloader._compute_data_hash(self, df: pd.DataFrame) -> str` — computes SHA-256 hash of the DataFrame content for reproducibility verification. Hash the raw bytes of the sorted, deduplicated data.
  - [x] 4.3 Implement `DukascopyDownloader._save_raw_artifact(self, df: pd.DataFrame, pair: str, start_date: date, end_date: date, resolution: str, storage_path: Path) -> Path` — saves raw downloaded data as a versioned CSV artifact at `{storage_path}/raw/{dataset_id}/v{NNN}/{dataset_id}.csv`. Uses crash-safe write pattern: write to `.partial` file, flush, rename. Never overwrites existing versions — increments version number.
  - [x] 4.4 Implement `DukascopyDownloader._write_download_manifest(self, dataset_id: str, version: str, data_hash: str, pair: str, start_date: date, end_date: date, resolution: str, row_count: int, failed_periods: List[str], storage_path: Path) -> Path` — writes a `manifest.json` alongside the data file containing: dataset_id, version, data_hash, pair, date range, resolution, row_count, download_timestamp, failed_periods (for partial downloads), config_hash (from Story 1.3's config hasher).

- [x] **Task 5: Implement download orchestration entry point** (AC: #1, #8)
  - [x] 5.1 Create `src/python/data_pipeline/cli.py` with function `run_download(config: dict) -> dict` — top-level entry point that loads config, instantiates `DukascopyDownloader`, calls download for each configured pair, handles incremental logic, saves artifacts. Returns a summary dict with: pairs downloaded, date ranges, row counts, versions created, any failed periods.
  - [x] 5.2 Log pipeline-stage structured messages: `{"stage": "data_pipeline", "component": "downloader", ...}` per D6 logging schema
  - [x] 5.3 Log download progress at INFO level: pair, current date being downloaded, percentage complete, estimated time remaining

- [x] **Task 6: Write unit and integration tests** (AC: all)
  - [x] 6.1 Create `src/python/tests/test_data_pipeline/__init__.py`
  - [x] 6.2 Create `src/python/tests/test_data_pipeline/test_downloader.py`
  - [x] 6.3 Unit test: `test_download_year_bidask_combines_correctly` — verify bid/ask DataFrames are combined with correct `bid` and `ask` columns
  - [x] 6.4 Unit test: `test_save_chunk_crash_safe` — verify yearly chunk save uses `.partial` → fsync → `os.replace()` pattern
  - [x] 6.5 Unit test: `test_consolidate_chunks` — verify yearly chunks merge correctly with deduplication and sorting
  - [x] 6.6 Unit test: `test_compute_missing_ranges` — verify incremental range calculation for various overlap scenarios
  - [x] 6.7 Unit test: `test_validate_merge_boundary` — verify gap detection between existing and new data
  - [x] 6.8 Unit test: `test_generate_dataset_id` — verify naming convention
  - [x] 6.9 Unit test: `test_compute_data_hash` — verify deterministic hash output
  - [x] 6.10 Integration test: `test_crash_safe_write` — verify .partial → rename pattern works correctly, verify partial file cleanup on startup
  - [x] 6.11 Integration test: `test_incremental_download_mock` — mock Dukascopy responses, verify only missing data is requested
  - [x] 6.12 Integration test: `test_graceful_degradation` — mock timeout responses, verify partial data is saved with failed periods in manifest

## Dev Notes

### Architecture Constraints

**D6 (Logging):** "Each runtime writes structured JSON log lines to `logs/`, one file per runtime per day." All download progress, errors, and retries must use the structured JSON logger established in Story 1.3. Every log line must include `component: "downloader"` and `stage: "data_pipeline"`.

**D7 (Configuration):** "Layered TOML configs validated at startup. Environment variables for secrets only." Download parameters (pairs, date range, resolution, timeouts) MUST come from config, not hardcoded. "Schema validation at startup — fail loud before any stage runs."

**D8 (Error Handling):** "Each runtime catches errors at component boundaries, wraps in structured error type, propagates to orchestrator." Dukascopy failures are `category: "external"` with error code `EXTERNAL_DUKASCOPY_TIMEOUT`. Response is retry with backoff, then alert. "Retry with backoff (NFR19), alert after threshold."

**D2 (Artifact Storage):** "New downloads create new versioned artifacts, never overwrite existing." The raw data artifact must follow the versioning pattern. "Every dataset is identified by `{pair}_{start_date}_{end_date}_{source}_{download_hash}`."

### Technical Requirements

- **Python libraries:** `dukascopy-python>=4.0.1` for Dukascopy data fetching (REST API, handles pagination/retry/JSONP), `pandas` for DataFrame operations, `hashlib` (stdlib) for SHA-256
- **Download mechanism:** The `dukascopy-python` library calls `freeserv.dukascopy.com/2.0/index.php` REST API. It returns pre-aggregated OHLCV DataFrames with UTC timestamps. Use `dk.fetch()` with `INTERVAL_MIN_1` for M1 bars and `INTERVAL_TICK` for tick data. Download bid and ask sides separately using `OFFER_SIDE_BID` and `OFFER_SIDE_ASK`. (Phase 0 research confirmed — Story 1.1/1.2)
- **Bid/Ask columns:** Download both bid-side and ask-side OHLCV. Store bid-side close as `bid` column, ask-side close as `ask` column (per Architecture Arrow IPC schema). The baseline computes spread = avg(ask_open - bid_open, ask_close - bid_close) — retain separate bid/ask instead.
- **Timestamps:** All timestamps stored as UTC datetime64[us] (microsecond precision) per architecture timestamp format spec. Arrow IPC columns use int64 epoch microseconds. The `dukascopy-python` library returns timezone-aware UTC timestamps by default.
- **Weekend handling:** Forex market closes Friday ~22:00 UTC and reopens Sunday ~22:00 UTC. Weekend hours will return empty/no data from Dukascopy — this is expected, not an error. Do NOT flag weekend gaps as missing data.
- **Storage path:** Default `G:\My Drive\BackTestData` is a Google Drive path. Ensure the code handles Windows path separators and Google Drive sync latency (use flush + fsync before considering writes complete).
- **Yearly chunking pattern:** Adopt from ClaudeBackTester — download one year at a time as individual Parquet files, consolidate into a single versioned artifact. This enables download resume (skip already-downloaded years) and incremental updates (re-download current year only).

### What to Reuse from ClaudeBackTester

**CONFIRMED by Story 1.1 review — Verdict: ADAPT**

The baseline at `ClaudeBackTester/backtester/data/downloader.py` (373 lines) has a proven download pipeline. Port the following:

- **Download flow:** `download_year()` → `save_chunk()` → `consolidate_chunks()` pattern. Downloads one year at a time, stores as yearly Parquet chunks, consolidates into single file. Resume by skipping already-downloaded years.
- **Bid+Ask download:** Downloads bid and ask sides separately via `dukascopy-python` library (`dk.fetch()` with `OFFER_SIDE_BID` / `OFFER_SIDE_ASK`). 1-second delay between to avoid rate limiting.
- **Atomic writes:** Uses `.parquet.tmp` → `replace()` pattern (adapt to use `os.replace()` + `os.fsync()` for full crash safety).
- **Rate limiting:** 1-second sleep between bid/ask per year (configurable in new system).
- **25 pairs configured:** `ALL_PAIRS` list in baseline — move to config.

**DO NOT port:**
- Hardcoded `DEFAULT_DATA_DIR`, `DEFAULT_START_YEAR` constants — use TOML config
- `shutil.rmtree()` force delete — never delete data without versioning
- Spread computation — store separate bid/ask columns instead
- `structlog` console renderer — use structured JSON logging

### Anti-Patterns to Avoid

1. **Do NOT hardcode Dukascopy URLs or pair parameters.** Everything must come from config.
2. **Do NOT download all data into memory before saving.** For large date ranges (10 years), this could be gigabytes. Process and save in chunks (e.g., per-month or per-day batches).
3. **Do NOT silently skip failed downloads.** Every failure must be logged with structured JSON and recorded in the manifest's `failed_periods` array.
4. **Do NOT overwrite existing data files.** New versions increment the version counter. This is a hard architectural constraint.
5. **Do NOT use `time.sleep()` for rate limiting without making the delay configurable.** Use the `request_delay_seconds` config value.
6. **Do NOT parse Dukascopy timestamps in local timezone.** All timestamps are UTC. Never use `datetime.now()` — use `datetime.utcnow()` or `datetime.now(timezone.utc)`.
7. **Do NOT create Arrow IPC files in this story.** This story produces raw CSV data. Arrow IPC conversion happens in Story 1.6.
8. **Do NOT perform quality validation in this story.** Raw data is saved as-is. Validation is Story 1.5.

### Project Structure Notes

```
src/python/
  data_pipeline/
    __init__.py
    downloader.py          # DukascopyDownloader class
    cli.py                 # run_download() entry point
  tests/
    test_data_pipeline/
      __init__.py
      test_downloader.py   # Unit + integration tests
      fixtures/            # Synthetic DataFrames for mocked download tests
```

Raw data artifacts go to:
```
{storage_path}/raw/{pair}_{start}_{end}_{resolution}/
  v001/
    {dataset_id}.csv
    manifest.json
  v002/
    ...
```

### References

- [Source: planning-artifacts/epics.md — Story 1.4 acceptance criteria]
- [Source: planning-artifacts/architecture.md — D2 (Artifact Schema & Storage)]
- [Source: planning-artifacts/architecture.md — D6 (Logging & Observability)]
- [Source: planning-artifacts/architecture.md — D7 (Configuration — TOML with Schema Validation)]
- [Source: planning-artifacts/architecture.md — D8 (Error Handling — Fail-Fast at Boundaries)]
- [Source: planning-artifacts/architecture.md — Data Volume Modeling (1 year ~525K bars, 10 years ~5.26M bars)]
- [Source: planning-artifacts/architecture.md — Data Quality Gate Specifications (FR8 — consistent data sourcing)]
- [Source: planning-artifacts/architecture.md — Crash-Safe Write Pattern (write → flush → rename)]
- [Source: planning-artifacts/architecture.md — Implementation Patterns — Naming: snake_case at every boundary]
- [Source: planning-artifacts/prd.md — FR1 (Dukascopy download), NFR20 (graceful degradation), NFR21 (configurable timeouts)]
- [Source: planning-artifacts/baseline-to-architecture-mapping.md — data_pipeline "Exists — documented as mature" → "Keep and adapt"]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Completion Notes List
- **Task 1:** Added `[data_pipeline]` and `[data_pipeline.download]` sections to `config/base.toml` with all required keys (storage_path, default_resolution, download_timeout_seconds, request_delay_seconds, max_retries, retry_backoff_factor, pairs, start_date, end_date, resolution). Added corresponding schema validation rules in `config/schema.toml` (12 new entries). Updated `conftest.py` fixtures to include new config sections.
- **Task 2:** Implemented `DukascopyDownloader` class (380 lines) in `downloader.py`. Adapted ClaudeBackTester yearly chunking pattern: `_download_year()` → `_download_year_bidask()` → `_save_chunk()` → `_consolidate_chunks()`. Bid/ask sides downloaded separately with configurable delay; bid close stored as `bid` column, ask close as `ask` column (no spread computation per architecture). Crash-safe Parquet write using `.partial` → fsync → `os.replace()`. Resume support via `_get_downloaded_years()`. Graceful degradation: failed years logged with `EXTERNAL_DUKASCOPY_TIMEOUT` error code, downloading continues for remaining years. Progress logging with ETA.
- **Task 3:** Incremental download logic: `_detect_existing_data()` scans chunks to determine existing date range; `_compute_missing_ranges()` calculates gaps; `_validate_merge_boundary()` detects gaps > 5 min excluding weekends (Fri 22:00 to Sun 22:00 UTC); `_merge_data()` combines DataFrames with dedup and monotonic timestamp verification.
- **Task 4:** Versioned artifact storage: `_generate_dataset_id()` produces `{pair}_{start}_{end}_{resolution}` IDs; `_compute_data_hash()` uses SHA-256 on sorted CSV bytes; `_save_raw_artifact()` saves versioned CSV at `raw/{dataset_id}/v{NNN}/{dataset_id}.csv` using crash-safe write, auto-incrementing version numbers; `_write_download_manifest()` produces `manifest.json` with full metadata including config_hash and failed_periods.
- **Task 5:** Orchestration entry point `run_download()` in `cli.py` — iterates configured pairs, downloads data, saves versioned artifacts + manifests, returns summary dict. Uses `LogContext(stage="data_pipeline")` for scoped structured logging per D6.
- **Task 6:** 16 mocked tests + 3 live integration tests. Mocked: bid/ask combination, crash-safe chunk save, chunk consolidation, missing range computation (3 scenarios), merge boundary validation (clean/gap/weekend), dataset ID generation, deterministic hashing, versioned artifact write, incremental download mock, graceful degradation. Live (run with `pytest -m live`): M1 download (372K rows/year verified), tick download (2,693 ticks/hour verified), full pipeline end-to-end (download -> chunk -> consolidate -> versioned artifact -> manifest).
- **Dependencies:** Added `dukascopy-python>=4.0.1`, `pandas>=2.0`, `pyarrow>=14.0` to `pyproject.toml`.
- **Pair format fix:** dukascopy-python expects `EUR/USD` (with slash), config stores `EURUSD`. Added `_to_dukascopy_format()` and `_to_filesystem_format()` converters.
- **Tick data fix:** `dk.fetch()` requires `offer_side` even for tick data; tick columns are `bidPrice/askPrice/bidVolume/askVolume` — normalized to `bid/ask/bid_volume/ask_volume`.
- **Index reset:** dukascopy-python returns timestamp as DataFrame index, not column. Added `reset_index()` after fetch to match expected schema.
- **Memory fix:** Large CSV artifact writes (372K+ rows) now stream directly to disk instead of building in-memory string. Hash computation uses 10K-row chunks.
- **Windows fix:** `os.fsync` on Parquet chunks uses `open(path, "r+b")` instead of `os.open(path, os.O_RDONLY)` for Windows compatibility.

### File List
- `config/base.toml` — Modified: added `[data_pipeline]` and `[data_pipeline.download]` sections
- `config/schema.toml` — Modified: added 12 schema validation entries for data_pipeline config
- `src/python/pyproject.toml` — Modified: added dukascopy-python, pandas, pyarrow dependencies
- `src/python/data_pipeline/__init__.py` — Modified: exports DukascopyDownloader and run_download
- `src/python/data_pipeline/downloader.py` — New: DukascopyDownloader class (380 lines)
- `src/python/data_pipeline/cli.py` — New: run_download() orchestration entry point
- `src/python/tests/conftest.py` — Modified: added data_pipeline config to test fixtures
- `src/python/tests/test_data_pipeline/__init__.py` — New: test package init
- `src/python/tests/test_data_pipeline/test_downloader.py` — New: 16 mocked + 3 live integration tests

### Change Log
- 2026-03-14: Story 1.4 implemented — Dukascopy data download pipeline with M1/tick support, incremental updates, crash-safe writes, versioned artifacts, and 19 tests (16 mocked + 3 live). All 47 tests pass (44 mocked + 3 live).
- 2026-03-14: Added live integration tests hitting real Dukascopy API. Fixed pair format (EURUSD -> EUR/USD), tick data offer_side requirement, index-to-column reset, and large CSV memory crash. All live tests verified: M1 (372K rows), tick (2.7K ticks), full pipeline end-to-end.
