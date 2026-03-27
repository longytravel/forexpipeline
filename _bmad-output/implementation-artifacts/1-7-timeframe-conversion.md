# Story 1.7: Timeframe Conversion

Status: review

## Story

As the **operator**,
I want M1 data converted to higher timeframes (M5, H1, D1, W),
So that strategies targeting different timeframes have correctly aggregated data.

## Acceptance Criteria

1. **Given** validated data exists in Arrow IPC format (Story 1.6)
   **When** timeframe conversion runs for a specified target timeframe
   **Then** M1 data is correctly aggregated to the target timeframe — open from first bar, high/low from max/min, close from last bar (FR6)

2. **And** bid and ask columns are aggregated appropriately

3. **And** if source data is tick-level, it is first aggregated to M1 (open/high/low/close/bid/ask from ticks within each minute), then M1 is aggregated to higher timeframes

4. **And** session column is preserved or recomputed for the target timeframe

5. **And** quarantined bars are excluded from aggregation (bars within quarantined periods are skipped)

6. **And** output is stored in both Arrow IPC and Parquet formats following the same schema contracts

7. **And** conversion is deterministic — same input produces identical output

## Tasks / Subtasks

- [x] **Task 1: Define timeframe conversion config in `config/base.toml`** (AC: #1, #7)
  - [x] Add `[data_pipeline.timeframe_conversion]` section with:
    - `target_timeframes = ["M5", "H1", "D1", "W"]` (list of timeframes to generate)
    - `source_timeframe = "M1"` (default source)
    - `storage_path` reference (inherits from `[data_pipeline.storage_path]`, default `G:\My Drive\BackTestData`)
  - [x] Add timeframe enum/validation to `config/schema.toml` — only M1, M5, H1, D1, W are valid

- [x] **Task 2: Implement timeframe aggregation logic in `src/python/data_pipeline/timeframe_converter.py`** (AC: #1, #2, #5, #7)
  - [x] Create `timeframe_converter.py` in `src/python/data_pipeline/`
  - [x] Implement `convert_timeframe(source_table: pa.Table, source_tf: str, target_tf: str) -> pa.Table`
  - [x] Aggregation rules (OHLC):
    - `open` = first bar's open in the period
    - `high` = max of all highs in the period
    - `low` = min of all lows in the period
    - `close` = last bar's close in the period
  - [x] Aggregation rules (bid/ask):
    - `bid` = last bar's bid in the period (closing bid)
    - `ask` = last bar's ask in the period (closing ask)
  - [x] Implement period boundary computation:
    - M5: group by floor(minute / 5) within each hour
    - H1: group by hour
    - D1: group by date (UTC)
    - W: group by ISO week (Monday-Sunday, aligned to market open Sunday 22:00 UTC)
  - [x] Filter out rows where `quarantined == true` BEFORE aggregation — quarantined bars must not contribute to any aggregated OHLC values
  - [x] If all bars in a period are quarantined, that period is omitted from the output (no empty/NaN rows)
  - [x] Timestamp for aggregated bar = epoch microseconds UTC of the period start (e.g., H1 bar at 14:00 gets timestamp for 14:00:00.000000)
  - [x] All operations must use deterministic ordering — sort by timestamp before grouping, no reliance on insertion order

- [x] **Task 3: Implement tick-to-M1 aggregation** (AC: #3)
  - [x] Create `tick_aggregator.py` in `src/python/data_pipeline/` (or add as a function in `timeframe_converter.py`)
  - [x] Implement `aggregate_ticks_to_m1(tick_table: pa.Table) -> pa.Table`
  - [x] Tick-to-M1 rules:
    - `open` = first tick's mid price in the minute
    - `high` = max mid price in the minute
    - `low` = min mid price in the minute
    - `close` = last tick's mid price in the minute
    - `bid` = last tick's bid in the minute
    - `ask` = last tick's ask in the minute
  - [x] Mid price = (bid + ask) / 2
  - [x] Output M1 table conforms to `contracts/arrow_schemas.toml` `[market_data]` schema
  - [x] If tick data is detected (schema check), run tick-to-M1 first, then proceed with M1-to-target conversion

- [x] **Task 4: Session column handling for aggregated timeframes** (AC: #4)
  - [x] For M5: session = session of the first bar in the 5-minute group (session doesn't change within 5 minutes)
  - [x] For H1: recompute session from the bar's timestamp using session schedule in `config/base.toml` `[sessions]`
    - If the hour spans two sessions (e.g., 13:00-14:00 spans London and NY overlap), assign the session that covers the majority of the hour
    - If tied, assign the session that starts during that hour
  - [x] For D1: session = `"mixed"` (a daily bar spans all sessions) — add `"mixed"` to valid session values only in aggregated timeframe schemas
  - [x] For W: session = `"mixed"`
  - [x] Implement `compute_session_for_timestamp(timestamp_us: int, session_schedule: dict) -> str` as a shared utility (reuse from Story 1.6 if it exists, or create here)

- [x] **Task 5: Output storage — Arrow IPC and Parquet** (AC: #6, #7)
  - [x] Write aggregated data to Arrow IPC using crash-safe write pattern:
    1. Write to `{pair}_{timeframe}.arrow.partial`
    2. Flush/fsync
    3. Rename to `{pair}_{timeframe}.arrow`
  - [x] Write aggregated data to Parquet with snappy compression using crash-safe write pattern
  - [x] File naming convention: `{pair}_{start_date}_{end_date}_{timeframe}.arrow` (e.g., `EURUSD_2024-01-01_2024-12-31_H1.arrow`)
  - [x] Output directory: `{storage_path}/data-pipeline/` alongside the M1 files
  - [x] Validate output schema against `contracts/arrow_schemas.toml` `[market_data]` before writing — fail loud on mismatch
  - [x] Arrow IPC files must be mmap-friendly (use `pyarrow.ipc.new_file()` with default settings, no compression in IPC)

- [x] **Task 6: Orchestration entry point** (AC: #1, #7)
  - [x] Add `run_timeframe_conversion(pair: str, source_path: Path, config: dict) -> dict` function
  - [x] This function:
    1. Loads the M1 Arrow IPC file from `source_path`
    2. If tick data is detected, runs tick-to-M1 first
    3. Iterates over `config.data_pipeline.timeframe_conversion.target_timeframes`
    4. For each target timeframe, calls `convert_timeframe()`
    5. Writes Arrow IPC + Parquet output
    6. Returns a dict of `{timeframe: output_path}` for downstream consumption
  - [x] Log each conversion step using structured JSON logging (D6):
    - Component: `data_pipeline`
    - Stage: `timeframe_conversion`
    - Include: pair, source_tf, target_tf, input_bar_count, output_bar_count, quarantined_bars_excluded

- [x] **Task 7: Unit tests** (AC: #1, #2, #3, #4, #5, #7)
  - [x] Create `src/python/tests/test_data_pipeline/test_timeframe_converter.py`
  - [x] Test M1 to M5: 10 M1 bars (00:00-00:09) -> 2 M5 bars with correct OHLC
  - [x] Test M1 to H1: 60 M1 bars -> 1 H1 bar with correct OHLC
  - [x] Test M1 to D1: verify daily aggregation across session boundaries
  - [x] Test M1 to W: verify weekly aggregation with correct Monday-Sunday alignment
  - [x] Test bid/ask aggregation: verify last bid/last ask per period
  - [x] Test quarantined bar exclusion: mix of quarantined and valid bars, verify quarantined are excluded from OHLC computation
  - [x] Test fully quarantined period: all bars in a period are quarantined, verify period is omitted
  - [x] Test session column recomputation for H1/D1/W
  - [x] Test determinism: run conversion twice on same input, verify output is bit-for-bit identical (compare Arrow IPC file hashes)
  - [x] Test tick-to-M1 aggregation with known tick data
  - [x] Test crash-safe write: verify `.partial` file exists during write, final file has correct name

## Dev Notes

### Architecture Constraints

**D2 — Artifact Schema & Storage:** "Three-format storage strategy, each format doing what it's best at. Compute: Arrow IPC. Query: SQLite. Archival: Parquet." Timeframe-converted data must be in both Arrow IPC (for Rust compute) and Parquet (for archival). Arrow IPC files must be mmap-friendly.

**D7 — Configuration:** "Layered TOML configs validated at startup. Schema validation at startup — fail loud before any stage runs." Timeframe list and conversion parameters must live in `config/base.toml` and be validated against `config/schema.toml`.

**D6 — Logging:** "Each runtime writes structured JSON log lines to logs/, one file per runtime per day." All conversion operations must emit structured logs with the unified schema: `{ts, level, runtime, component, stage, strategy_id, msg, ctx}`.

**D8 — Error Handling:** "Each runtime catches errors at component boundaries, wraps in structured error type, propagates to orchestrator." If conversion fails (e.g., empty input, schema mismatch), emit a structured error with code from `contracts/error_codes.toml` (e.g., `DATA_SCHEMA_MISMATCH`).

**Session-Awareness Architecture:** "Sessions are a first-class architectural dimension. Session label as a computed column during data pipeline stage." The session column must be preserved or recomputed for every timeframe. Session schedule is read from `config/base.toml` `[sessions]`.

**Crash-Safe Write Pattern:** "All artifact writes across all runtimes follow: 1. Write to {filename}.partial, 2. Flush / fsync, 3. Atomic rename to {filename}. Never overwrite a complete artifact with a partial one."

### Technical Requirements

- **Language:** Python (orchestration tier)
- **Libraries:** `pyarrow` for Arrow IPC/Parquet read/write, `tomllib` (Python 3.11+) for TOML config
- **Arrow IPC format:** Use `pyarrow.ipc.new_file()` writer (not stream format) for mmap compatibility
- **Parquet compression:** Snappy (default, good balance of speed vs size)
- **Timestamp format in Arrow:** int64 epoch microseconds UTC (per architecture Format Patterns)
- **File location:** `src/python/data_pipeline/timeframe_converter.py`
- **Test location:** `src/python/tests/test_data_pipeline/test_timeframe_converter.py`
- **Schema contract:** `contracts/arrow_schemas.toml` `[market_data]` section defines the required columns

### What to Reuse from ClaudeBackTester

**CONFIRMED by Story 1.1 review — Verdict: ADAPT**

The baseline at `ClaudeBackTester/backtester/data/timeframes.py` (145 lines) has correct timeframe conversion. Port the following:

- **OHLCV aggregation** (`resample_ohlcv()`): Uses pandas `.resample()` with correct aggregation: `first` open, `max` high, `min` low, `last` close, `sum` volume. Spread handled with `median`. Port the aggregation rules.
- **Timeframe mapping**: `TIMEFRAME_RULES = {"M5": "5min", "H1": "1h", "D": "1D", "W": "W-MON"}`. Port but fix weekly alignment (forex week is Sunday 22:00 to Friday 22:00, not ISO Monday-Sunday).
- **H1-to-M1 mapping** (`build_h1_to_m1_mapping()`): numpy searchsorted O(n log n) mapping. Useful reference for Epic 2 multi-timeframe backtesting.
- **Atomic writes**: `.parquet.tmp` → `replace()`. Adapt to add `os.fsync()`.

**DO NOT port:**
- Pandas-only operation — adapt to work with PyArrow tables for Arrow IPC output
- Spread column handling — new system uses separate bid/ask columns, aggregate as `last` for both

**Build NEW (not in baseline):**
- Quarantined bar exclusion before aggregation
- Session column handling (preserve for M5, recompute for H1/D1/W)
- Tick-to-M1 aggregation (baseline has no tick data support)
- Arrow IPC + Parquet dual output with schema validation
- Config-driven timeframe list from `config/base.toml`

### Anti-Patterns to Avoid

1. **Do NOT use pandas for aggregation.** Use PyArrow compute functions directly or convert to PyArrow Table operations. Pandas introduces unnecessary memory copies and breaks mmap compatibility.
2. **Do NOT generate NaN/null rows for periods where all bars are quarantined.** Omit the period entirely.
3. **Do NOT hardcode session boundaries.** Always read from `config/base.toml` `[sessions]` section. Sessions are config-driven, not code-driven.
4. **Do NOT use `datetime.now()` anywhere.** All timestamps come from the data. Test fixtures use fixed timestamps.
5. **Do NOT compress Arrow IPC files.** Arrow IPC must be uncompressed for mmap zero-copy access. Only Parquet gets compression.
6. **Do NOT overwrite existing converted files.** If a file already exists with the same name, the conversion should either skip (idempotent) or create a new versioned artifact.
7. **Do NOT aggregate in-memory without sorting first.** Ensure data is sorted by timestamp before any grouping operation. Determinism depends on sort order.
8. **Do NOT use weekly boundaries based on calendar week without considering forex market hours.** Forex weeks run Sunday 22:00 UTC to Friday 22:00 UTC. Weekly bars should align to this, not ISO Monday-Sunday.

### Project Structure Notes

```
src/python/
  data_pipeline/
    __init__.py
    downloader.py           # Story 1.4 (exists)
    quality_checker.py      # Story 1.5 (exists)
    arrow_converter.py      # Story 1.6 (exists)
    parquet_archiver.py     # Story 1.6 (exists)
    timeframe_converter.py  # THIS STORY - new file
    tick_aggregator.py      # THIS STORY - new file (if separate)
  tests/
    test_data_pipeline/
      test_timeframe_converter.py  # THIS STORY - new file
```

Output files go to the configured storage path:
```
G:\My Drive\BackTestData\    (or configured path)
  data-pipeline/
    EURUSD_2024-01-01_2024-12-31_M1.arrow     # From Story 1.6
    EURUSD_2024-01-01_2024-12-31_M1.parquet   # From Story 1.6
    EURUSD_2024-01-01_2024-12-31_M5.arrow     # THIS STORY
    EURUSD_2024-01-01_2024-12-31_M5.parquet   # THIS STORY
    EURUSD_2024-01-01_2024-12-31_H1.arrow     # THIS STORY
    EURUSD_2024-01-01_2024-12-31_H1.parquet   # THIS STORY
    EURUSD_2024-01-01_2024-12-31_D1.arrow     # THIS STORY
    EURUSD_2024-01-01_2024-12-31_D1.parquet   # THIS STORY
    EURUSD_2024-01-01_2024-12-31_W.arrow      # THIS STORY
    EURUSD_2024-01-01_2024-12-31_W.parquet    # THIS STORY
```

### References

- [Source: planning-artifacts/epics.md#Story 1.7 — Timeframe Conversion]
- [Source: planning-artifacts/architecture.md#Decision 2 — Arrow IPC / SQLite / Parquet Hybrid]
- [Source: planning-artifacts/architecture.md#Decision 6 — Structured JSON Logging]
- [Source: planning-artifacts/architecture.md#Decision 7 — TOML Configuration]
- [Source: planning-artifacts/architecture.md#Decision 8 — Error Handling]
- [Source: planning-artifacts/architecture.md#Session-Awareness Architecture]
- [Source: planning-artifacts/architecture.md#Crash-Safe Write Pattern]
- [Source: planning-artifacts/architecture.md#Contracts Directory — arrow_schemas.toml]
- [Source: planning-artifacts/architecture.md#Format Patterns — Timestamp Formats]
- [Source: planning-artifacts/prd.md#FR6 — Convert M1 to higher timeframes]
- [Source: planning-artifacts/baseline-to-architecture-mapping.md#data_pipeline — Keep and adapt]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Completion Notes List
- **Task 1:** Added `[data_pipeline.timeframe_conversion]` section to `config/base.toml` with `target_timeframes` and `source_timeframe`. Added schema validation entries in `config/schema.toml`.
- **Task 2:** Implemented `convert_timeframe()` using pure PyArrow compute operations (no pandas). OHLC aggregation: open=first, high=max, low=min, close=last. Bid/ask=last. Quarantined bars filtered before aggregation. Period start computed via floor division for M5/H1/D1 and forex-week-aligned offset for W.
- **Task 3:** Implemented `aggregate_ticks_to_m1()` in the same module. Mid price = (bid+ask)/2. Tick detection via `is_tick_data()` schema check. Orchestrator auto-detects tick data and converts to M1 first.
- **Task 4:** Session handling: M5 preserves first bar's session, H1 uses majority session with deterministic tie-breaking, D1/W use "mixed". Added `compute_session_for_timestamp()` utility.
- **Task 5:** Crash-safe write for both Arrow IPC (uncompressed, mmap-friendly via `pa.ipc.new_file()`) and Parquet (snappy compression). Pattern: write .partial → flush → fsync → os.replace. Schema validation against contracts before write.
- **Task 6:** `run_timeframe_conversion()` orchestrates full pipeline: load source → detect tick data → convert each target timeframe → write dual output. Structured JSON logging with component/stage/pair context. Idempotent skip if output exists.
- **Task 7:** 41 unit tests + 3 live integration tests. Covers all ACs: OHLC aggregation, bid/ask, quarantine exclusion, session handling, determinism, tick-to-M1, crash-safe writes, schema validation, edge cases.

### Change Log
- 2026-03-14: Story 1.7 implemented — timeframe conversion module with all 7 tasks complete
- 2026-03-14: Added "mixed" to valid session values in contracts/arrow_schemas.toml for D1/W aggregated timeframes
- 2026-03-14: All tests verified — 41 unit tests passed, 3 live integration tests passed, 155 total regression suite passed with 0 failures

### File List
- `config/base.toml` — modified (added `[data_pipeline.timeframe_conversion]` section)
- `config/schema.toml` — modified (added timeframe_conversion schema entries)
- `src/python/data_pipeline/timeframe_converter.py` — new (core module: aggregation, tick-to-M1, session handling, output storage, orchestration)
- `src/python/data_pipeline/__init__.py` — modified (exports for new module)
- `contracts/arrow_schemas.toml` — modified (added "mixed" to valid session values for aggregated timeframes)
- `src/python/tests/test_data_pipeline/test_timeframe_converter.py` — new (41 unit tests + 3 live integration tests)
