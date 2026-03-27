# Story 1.5: Data Validation & Quality Scoring

Status: done

## Story

As the **operator**,
I want ingested data validated for integrity and assigned a quality score,
So that I know the data is trustworthy before backtesting against it.

## Acceptance Criteria

1. **Given** raw data has been downloaded (Story 1.4) — M1 bars or tick data
   **When** data validation runs
   **Then** gap detection flags gaps > 5 consecutive M1 bars (or equivalent tick gap), WARNING if < 10 gaps/year, ERROR if > 50 gaps/year or any gap > 30 min (FR2)

2. **And** price integrity checks verify bid > 0, ask > bid, spread within 10x median for session (FR2)

3. **And** timezone alignment verifies all timestamps are UTC with no DST artifacts (FR2)

4. **And** stale quote detection flags periods where bid=ask or spread=0 for > 5 consecutive bars (FR2)

5. **And** completeness checks verify no unexpected missing weekday data (FR2)

6. **And** a quality score is computed using the Architecture's formula: `1.0 - (gap_penalty + integrity_penalty + staleness_penalty)` (FR3)

7. **And** score ranges produce correct ratings: GREEN (>= 0.95), YELLOW (0.80-0.95), RED (< 0.80) (FR3)

8. **And** suspect data periods are quarantined — marked in data with a `quarantined: bool` column (FR4)

9. **And** a quality report artifact is produced listing all issues, quarantined periods, and overall score (FR4)

10. **And** data with RED score blocks pipeline progression; YELLOW requires operator review

11. **And** all validation results are written using crash-safe write pattern (NFR15)

## Tasks / Subtasks

- [x] **Task 1: Implement gap detection** (AC: #1)
  - [x] 1.1 Create `src/python/data_pipeline/quality_checker.py` with class `DataQualityChecker`
  - [x] 1.2 Implement `DataQualityChecker.__init__(self, config: dict, logger: logging.Logger)` — loads session schedule from config, initializes checker with thresholds from config or architecture defaults
  - [x] 1.3 Implement `DataQualityChecker._detect_gaps(self, df: pd.DataFrame, resolution: str) -> List[GapRecord]` where `GapRecord = namedtuple('GapRecord', ['start', 'end', 'duration_minutes', 'is_weekend'])`:
    - For M1 data: expected interval is 1 minute. Flag sequences of > 5 consecutive missing M1 bars
    - For tick data: flag gaps > 5 minutes with no ticks (equivalent threshold)
    - Exclude weekend gaps (Friday 22:00 UTC to Sunday 22:00 UTC) — these are expected
    - Exclude known market holidays if configured
    - Return list of `GapRecord` with start/end timestamps and duration
  - [x] 1.4 Implement `DataQualityChecker._classify_gap_severity(self, gaps: List[GapRecord], total_years: float) -> str`:
    - Count non-weekend gaps per year
    - WARNING if < 10 gaps/year
    - ERROR if > 50 gaps/year OR any single gap > 30 minutes
    - Return severity level: `"ok"`, `"warning"`, or `"error"`

- [x] **Task 2: Implement price integrity checks** (AC: #2)
  - [x] 2.1 Implement `DataQualityChecker._check_price_integrity(self, df: pd.DataFrame, session_schedule: dict) -> List[IntegrityIssue]` where `IntegrityIssue = namedtuple('IntegrityIssue', ['timestamp', 'issue_type', 'detail', 'severity'])`:
    - Check `bid > 0` for all rows — ERROR on any non-positive bid
    - Check `ask > bid` for all rows — ERROR on any inverted or equal spread (bid >= ask)
    - Check `open > 0`, `high > 0`, `low > 0`, `close > 0` for M1 data — ERROR on any non-positive price
    - Check `high >= low` for M1 data — ERROR on inverted high/low
    - Check `high >= open` and `high >= close` — ERROR on OHLC violation
    - Check `low <= open` and `low <= close` — ERROR on OHLC violation
  - [x] 2.2 Implement `DataQualityChecker._check_spread_outliers(self, df: pd.DataFrame, session_schedule: dict) -> List[IntegrityIssue]`:
    - Compute `spread = ask - bid` for each row
    - Group bars by session using the session schedule from config
    - Compute median spread per session
    - Flag any bar where `spread > 10 * median_spread_for_session` — severity ERROR
    - Return list of flagged bars with their timestamps, session, and spread value

- [x] **Task 3: Implement timezone alignment verification** (AC: #3)
  - [x] 3.1 Implement `DataQualityChecker._verify_timezone_alignment(self, df: pd.DataFrame) -> List[IntegrityIssue]`:
    - Verify all timestamps are timezone-naive (assumed UTC) or explicitly UTC — ERROR on any non-UTC timezone info
    - Verify timestamps are monotonically increasing — ERROR on any out-of-order or duplicate timestamps
    - Check for DST artifacts: look for 1-hour jumps or gaps at known DST transition dates (second Sunday of March, first Sunday of November for US; last Sunday of March/October for EU). Flag as WARNING if suspicious patterns found near these dates
    - Verify no timestamps fall on future dates — ERROR

- [x] **Task 4: Implement stale quote detection** (AC: #4)
  - [x] 4.1 Implement `DataQualityChecker._detect_stale_quotes(self, df: pd.DataFrame) -> List[StaleRecord]` where `StaleRecord = namedtuple('StaleRecord', ['start', 'end', 'duration_bars', 'stale_type'])`:
    - Flag consecutive runs where `bid == ask` (zero spread) for > 5 bars — `stale_type: "zero_spread"`
    - Flag consecutive runs where `spread == 0` for > 5 bars — `stale_type: "zero_spread"`
    - Flag consecutive runs where all prices (open, high, low, close) are identical for > 5 bars — `stale_type: "frozen_price"`
    - Exclude weekend and off-hours periods from stale detection (low-volume periods are expected to have wider gaps between ticks)
    - Return list of stale periods with start/end timestamps and duration

- [x] **Task 5: Implement completeness checks** (AC: #5)
  - [x] 5.1 Implement `DataQualityChecker._check_completeness(self, df: pd.DataFrame, start_date: date, end_date: date) -> List[CompletenessIssue]` where `CompletenessIssue = namedtuple('CompletenessIssue', ['date', 'issue_type', 'detail'])`:
    - Generate expected trading days (weekdays excluding weekends: Friday 22:00 UTC to Sunday 22:00 UTC)
    - For each expected trading day, verify at least some data exists
    - Flag any completely missing weekday as ERROR with `issue_type: "missing_weekday"`
    - Flag any day with < 50% expected bars (e.g., < 720 M1 bars for a full trading day) as WARNING with `issue_type: "incomplete_day"`

- [x] **Task 6: Implement quality scoring** (AC: #6, #7)
  - [x] 6.1 Implement `DataQualityChecker._compute_quality_score(self, df: pd.DataFrame, gaps: List[GapRecord], integrity_issues: List[IntegrityIssue], stale_records: List[StaleRecord]) -> Tuple[float, dict]`:
    - Compute penalties using the architecture-specified formula:
      ```python
      total_expected_minutes = total_trading_minutes_in_range  # excluding weekends
      total_gap_minutes = sum(g.duration_minutes for g in gaps if not g.is_weekend)
      gap_penalty = min(1.0, total_gap_minutes / total_expected_minutes * 10)

      bad_price_bars = len([i for i in integrity_issues if i.severity == "error"])
      total_bars = len(df)
      integrity_penalty = min(1.0, bad_price_bars / total_bars * 100)

      stale_bars = sum(s.duration_bars for s in stale_records)
      staleness_penalty = min(1.0, stale_bars / total_bars * 50)

      quality_score = 1.0 - (gap_penalty + integrity_penalty + staleness_penalty)
      quality_score = max(0.0, quality_score)  # floor at 0
      ```
    - Return `(quality_score, {"gap_penalty": ..., "integrity_penalty": ..., "staleness_penalty": ...})`
  - [x] 6.2 Implement `DataQualityChecker._classify_score(self, score: float) -> str`:
    - `score >= 0.95` → `"GREEN"`
    - `0.80 <= score < 0.95` → `"YELLOW"`
    - `score < 0.80` → `"RED"`

- [x] **Task 7: Implement quarantine marking** (AC: #8)
  - [x] 7.1 Implement `DataQualityChecker._mark_quarantined(self, df: pd.DataFrame, gaps: List[GapRecord], integrity_issues: List[IntegrityIssue], stale_records: List[StaleRecord]) -> pd.DataFrame`:
    - Add `quarantined` boolean column to DataFrame, default `False`
    - Mark `quarantined = True` for:
      - All bars within gap periods (the bars adjacent to gaps that may be unreliable)
      - All bars flagged with price integrity ERROR issues
      - All bars within stale quote periods
    - Return the modified DataFrame with quarantine column
  - [x] 7.2 Log summary of quarantined periods: count, total duration, percentage of dataset

- [x] **Task 8: Implement quality report artifact** (AC: #9, #11)
  - [x] 8.1 Implement `DataQualityChecker._generate_quality_report(self, pair: str, resolution: str, start_date: date, end_date: date, quality_score: float, rating: str, penalty_breakdown: dict, gaps: List, integrity_issues: List, stale_records: List, completeness_issues: List, quarantined_periods: List[dict]) -> dict`:
    - Build a structured quality report dict:
      ```python
      {
        "dataset_id": "EURUSD_2015-01-01_2025-12-31_M1",
        "pair": "EURUSD",
        "resolution": "M1",
        "date_range": {"start": "2015-01-01", "end": "2025-12-31"},
        "total_bars": 5260000,
        "quality_score": 0.97,
        "rating": "GREEN",
        "penalty_breakdown": {
          "gap_penalty": 0.01,
          "integrity_penalty": 0.00,
          "staleness_penalty": 0.02
        },
        "gaps": [{"start": "...", "end": "...", "duration_minutes": 15}],
        "integrity_issues": [{"timestamp": "...", "issue_type": "...", "detail": "..."}],
        "stale_periods": [{"start": "...", "end": "...", "duration_bars": 8}],
        "completeness_issues": [{"date": "...", "issue_type": "...", "detail": "..."}],
        "quarantined_periods": [{"start": "...", "end": "...", "reason": "..."}],
        "quarantined_bar_count": 42,
        "quarantined_percentage": 0.0008,
        "validation_timestamp": "2026-03-14T10:30:00Z",
        "config_hash": "abc123..."
      }
      ```
  - [x] 8.2 Implement `DataQualityChecker._save_quality_report(self, report: dict, storage_path: Path, dataset_id: str, version: str) -> Path`:
    - Save as `{storage_path}/raw/{dataset_id}/{version}/quality-report.json`
    - Use crash-safe write pattern: write to `.partial`, flush, rename
  - [x] 8.3 Save the quarantine-marked DataFrame back alongside the raw data (or as a separate validated artifact):
    - Save as `{storage_path}/validated/{dataset_id}/{version}/{dataset_id}_validated.csv`
    - Use crash-safe write pattern

- [x] **Task 9: Implement validation orchestration** (AC: #10)
  - [x] 9.1 Implement `DataQualityChecker.validate(self, df: pd.DataFrame, pair: str, resolution: str, start_date: date, end_date: date, storage_path: Path, dataset_id: str, version: str) -> ValidationResult` where `ValidationResult = namedtuple('ValidationResult', ['quality_score', 'rating', 'report_path', 'validated_df', 'can_proceed'])`:
    - Run all checks in sequence: gaps → price integrity → spread outliers → timezone → stale quotes → completeness
    - Compute quality score
    - Mark quarantined periods
    - Generate and save quality report
    - Determine `can_proceed`: `True` for GREEN, `"operator_review"` for YELLOW, `False` for RED
    - Log overall result at INFO level with score and rating
  - [x] 9.2 Create `src/python/data_pipeline/validator_cli.py` with function `run_validation(config: dict) -> dict`:
    - Entry point that loads raw data from Story 1.4 output, runs validation, returns summary
    - For RED: log ERROR with explanation, return `can_proceed=False`
    - For YELLOW: log WARNING with "operator review required", return `can_proceed="operator_review"`
    - For GREEN: log INFO, return `can_proceed=True`

- [x] **Task 10: Implement session assignment utility** (AC: #2 — needed for per-session median spread)
  - [x] 10.1 Create `src/python/data_pipeline/session_labeler.py` with function `assign_session(timestamp: datetime, session_schedule: dict) -> str`:
    - Takes a UTC timestamp and the session schedule from `config/base.toml`
    - Returns the session label (`"asian"`, `"london"`, `"new_york"`, `"london_ny_overlap"`, `"off_hours"`)
    - Handle overlapping sessions: if a timestamp falls in both `london` and `new_york`, return `"london_ny_overlap"`
    - This utility is reused in Story 1.6 for Arrow IPC session column stamping
  - [x] 10.2 Implement `assign_sessions_bulk(df: pd.DataFrame, session_schedule: dict) -> pd.Series`:
    - Vectorized version for DataFrame operations
    - Returns a Series of session labels for each row

- [x] **Task 11: Write unit and integration tests** (AC: all)
  - [x] 11.1 Create `src/python/tests/test_data_pipeline/test_quality_checker.py`
  - [x] 11.2 Create test fixtures: small DataFrames with known gaps, bad prices, stale quotes, completeness issues
  - [x] 11.3 Unit test: `test_detect_gaps_identifies_gaps` — DataFrame with 3 gaps of different sizes, verify correct detection
  - [x] 11.4 Unit test: `test_detect_gaps_excludes_weekends` — verify Friday-to-Sunday gaps are NOT flagged
  - [x] 11.5 Unit test: `test_gap_severity_warning` — verify WARNING for < 10 gaps/year
  - [x] 11.6 Unit test: `test_gap_severity_error_count` — verify ERROR for > 50 gaps/year
  - [x] 11.7 Unit test: `test_gap_severity_error_duration` — verify ERROR for any gap > 30 min
  - [x] 11.8 Unit test: `test_price_integrity_positive_bid` — verify ERROR on bid <= 0
  - [x] 11.9 Unit test: `test_price_integrity_ask_gt_bid` — verify ERROR on ask <= bid
  - [x] 11.10 Unit test: `test_price_integrity_ohlc_consistency` — verify ERROR on high < low, etc.
  - [x] 11.11 Unit test: `test_spread_outlier_detection` — verify 10x median flagging per session
  - [x] 11.12 Unit test: `test_timezone_monotonic` — verify ERROR on non-monotonic timestamps
  - [x] 11.13 Unit test: `test_stale_quote_detection` — verify zero-spread runs > 5 bars are flagged
  - [x] 11.14 Unit test: `test_completeness_missing_weekday` — verify missing weekday is ERROR
  - [x] 11.15 Unit test: `test_quality_score_green` — verify score >= 0.95 → GREEN
  - [x] 11.16 Unit test: `test_quality_score_yellow` — verify 0.80 <= score < 0.95 → YELLOW
  - [x] 11.17 Unit test: `test_quality_score_red` — verify score < 0.80 → RED
  - [x] 11.18 Unit test: `test_quality_score_formula` — verify exact penalty calculation with known inputs
  - [x] 11.19 Unit test: `test_quarantine_marking` — verify correct bars are marked quarantined
  - [x] 11.20 Integration test: `test_full_validation_clean_data` — run full validation on clean fixture, verify GREEN
  - [x] 11.21 Integration test: `test_full_validation_bad_data` — run full validation on fixture with multiple issues, verify RED and correct report
  - [x] 11.22 Integration test: `test_quality_report_crash_safe` — verify .partial write pattern
  - [x] 11.23 Unit test: `test_assign_session` — verify session labeling for timestamps in each session window
  - [x] 11.24 Unit test: `test_assign_session_overlap` — verify london_ny_overlap is correctly identified

## Dev Notes

### Architecture Constraints

**D2 (Artifact Storage):** "Quarantined periods are marked in the Arrow IPC with a `quarantined: bool` column." The validated DataFrame must include this column for downstream consumption. "Backtester skips quarantined bars (no signals generated during quarantined periods)."

**D6 (Logging):** All validation results must be logged with structured JSON. Log each check type's result summary. Include `component: "quality_checker"` and `stage: "data_pipeline"` in every log line.

**D7 (Configuration):** Session schedule comes from `config/base.toml [sessions]` section. The quality checker must read session definitions from config, not hardcode them.

**D8 (Error Handling):** Quality validation failures are `category: "data"` errors. "DATA_QUALITY_FAILED = { severity = 'warning', recoverable = true, action = 'alert' }". RED scores should emit this error code. The orchestrator decides whether to halt.

**Architecture — Data Quality Gate Specifications:** The architecture document specifies exact thresholds, formulas, and behaviors:
- "Gap detection: Expected bar count vs actual per hour; flag gaps > 5 consecutive M1 bars"
- "Price integrity: Bid > 0, Ask > Bid, spread within 10x median for that session"
- "Timezone alignment: Verify all timestamps are UTC, no DST artifacts, monotonically increasing"
- "Stale quotes: Flag periods where bid=ask or spread=0 for > 5 consecutive bars"
- "Completeness: Weekend gaps expected (Fri 22:00 - Sun 22:00 UTC); flag unexpected missing days"
- "quality_score = 1.0 - (gap_penalty + integrity_penalty + staleness_penalty)"
- "gap_penalty = min(1.0, total_gap_minutes / total_expected_minutes x 10)"
- "integrity_penalty = min(1.0, bad_price_bars / total_bars x 100)"
- "staleness_penalty = min(1.0, stale_bars / total_bars x 50)"

**Architecture — Session-Awareness:** "Session label as a computed column during data pipeline stage." Sessions are defined in config:
- Asian: 00:00-08:00 UTC
- London: 08:00-16:00 UTC
- New York: 13:00-21:00 UTC
- London/NY Overlap: 13:00-16:00 UTC
- Off Hours: 21:00-00:00 UTC

The session labeler built here is reused in Story 1.6 for Arrow IPC session column stamping.

### Technical Requirements

- **Python libraries:** `pandas` for DataFrame operations, `json` (stdlib) for report output, `pathlib` (stdlib) for file operations
- **No external validation libraries.** All checks are implemented from scratch per architecture spec — the formulas and thresholds are explicit.
- **Performance consideration:** For 10-year M1 data (~5.26M rows), vectorized pandas operations are essential. Do NOT iterate row-by-row for gap detection or price checks. Use `df['timestamp'].diff()` for gap detection, boolean masking for price checks.
- **Crash-safe writes:** Use the shared utility from Story 1.3 for all file writes (write to `.partial`, flush, atomic rename).
- **Quarantine column type:** `bool` (Python) / `bool` (Arrow). Default `False`. Set `True` for quarantined bars.

### What to Reuse from ClaudeBackTester

**CONFIRMED by Story 1.1 review — Verdict: ADAPT checks, REPLACE scoring**

The baseline at `ClaudeBackTester/backtester/data/validation.py` (305 lines) has useful validation logic. Port the following:

- **Gap detection** (`detect_gaps()`): Finds gaps > 3× expected interval, classifies as weekend/holiday/unexpected. Port the `_is_weekend_gap()` and `_is_holiday_gap()` helper functions — they have well-tested windowing logic (Friday 20:00+ through Monday 01:00, Christmas Dec 24-26, New Year Dec 31-Jan 2). Adapt threshold from 3× interval to > 5 consecutive M1 bars per Architecture.
- **Zero/NaN detection** (`detect_zeros_nans()`): Counts zero and NaN values in OHLC columns. Port as-is — clean vectorized implementation.
- **Anomaly detection** (`detect_anomalies()`): Extreme range detection with adaptive multipliers (50×/20×/10× by timeframe), OHLC violation checks (high < low). Port as-is — now confirmed as Architecture quality checks (added in Phase 0 research update).
- **Yearly coverage** (`check_yearly_coverage()`): Missing/sparse year detection. Port for completeness checks.

**DO NOT port:**
- Quality scoring model (`compute_quality_score()`) — uses 0-100 point deduction, INCOMPATIBLE with Architecture's `1.0 - penalties` formula. Build new per Architecture spec.
- `validate_data()` orchestration — has different threshold model (min_score, min_candles). Build new with GREEN/YELLOW/RED system.

**Build NEW (not in baseline):**
- Quality scoring with Architecture's formula (gap_penalty + integrity_penalty + staleness_penalty)
- Session-aware spread outlier detection (per-session median, 10× threshold)
- Stale quote detection (bid=ask or spread=0 for > 5 consecutive bars)
- Quarantine marking (`quarantined: bool` column)
- Quality report JSON artifact with crash-safe write
- Session labeler utility (reused in Story 1.6)

### Anti-Patterns to Avoid

1. **Do NOT use row-by-row iteration for validation checks.** With 5M+ rows, this would be extremely slow. Use vectorized pandas operations (boolean indexing, `.diff()`, `.rolling()`, `.shift()`).
2. **Do NOT hardcode session times.** Read from `config/base.toml [sessions]` section.
3. **Do NOT interpolate or fix bad data.** The architecture explicitly states: "Quarantine gap periods, interpolation NOT allowed." Mark bad data, do not attempt to repair it.
4. **Do NOT conflate weekend gaps with data quality gaps.** Weekend gaps (Fri 22:00 - Sun 22:00 UTC) are expected. Only flag gaps during expected trading hours.
5. **Do NOT produce quality reports without the crash-safe write pattern.** Every file write must go through `.partial` → flush → rename.
6. **Do NOT skip the quarantine column.** Downstream stories (1.6, 1.7) depend on this column existing. The backtester will use it to skip quarantined bars.
7. **Do NOT clamp quality_score above 1.0.** The formula naturally produces values <= 1.0 due to `min(1.0, ...)` on each penalty. But DO clamp to >= 0.0 in case penalties exceed 1.0 combined.
8. **Do NOT perform Arrow IPC or Parquet conversion in this story.** Output is a validated CSV + quality report JSON. Conversion is Story 1.6.

### Project Structure Notes

```
src/python/
  data_pipeline/
    __init__.py            # (from Story 1.4)
    downloader.py          # (from Story 1.4)
    cli.py                 # (from Story 1.4)
    quality_checker.py     # NEW — DataQualityChecker class
    session_labeler.py     # NEW — session assignment utility (reused in Story 1.6)
    validator_cli.py       # NEW — run_validation() entry point
  tests/
    test_data_pipeline/
      __init__.py          # (from Story 1.4)
      test_downloader.py   # (from Story 1.4)
      test_quality_checker.py  # NEW
      test_session_labeler.py  # NEW
      fixtures/
        clean_m1_data.csv      # NEW — test fixture, ~100 rows of clean data
        gapped_m1_data.csv     # NEW — test fixture with gaps
        bad_prices_data.csv    # NEW — test fixture with integrity issues
```

Quality report artifacts go to:
```
{storage_path}/raw/{dataset_id}/{version}/
  quality-report.json       # Quality report artifact

{storage_path}/validated/{dataset_id}/{version}/
  {dataset_id}_validated.csv  # Data with quarantined column
```

### References

- [Source: planning-artifacts/epics.md — Story 1.5 acceptance criteria]
- [Source: planning-artifacts/architecture.md — Data Quality Gate Specifications (full section)]
- [Source: planning-artifacts/architecture.md — D2 (quarantined column in Arrow IPC, backtester skips quarantined bars)]
- [Source: planning-artifacts/architecture.md — D6 (Logging — structured JSON)]
- [Source: planning-artifacts/architecture.md — D7 (Configuration — session schedule in config/base.toml)]
- [Source: planning-artifacts/architecture.md — D8 (Error Handling — DATA_QUALITY_FAILED error code)]
- [Source: planning-artifacts/architecture.md — Session-Awareness Architecture (session definitions, data flow)]
- [Source: planning-artifacts/architecture.md — Crash-Safe Write Pattern]
- [Source: planning-artifacts/architecture.md — contracts/arrow_schemas.toml — market_data schema with quarantined and session columns]
- [Source: planning-artifacts/architecture.md — contracts/session_schema.toml — session column spec]
- [Source: planning-artifacts/prd.md — FR2 (data validation), FR3 (quality scoring), FR4 (quarantine and reporting)]
- [Source: planning-artifacts/prd.md — Domain: Market Data Integrity section]
- [Source: planning-artifacts/baseline-to-architecture-mapping.md — data_pipeline "Keep and adapt"]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Completion Notes List
- Implemented `DataQualityChecker` class with all 6 validation checks: gap detection, price integrity, spread outliers, timezone alignment, stale quote detection, completeness checks
- Quality scoring uses Architecture-specified formula: `1.0 - (gap_penalty + integrity_penalty + staleness_penalty)` with GREEN/YELLOW/RED classification
- Quarantine marking adds `quarantined: bool` column to DataFrame for downstream consumption (Story 1.6, backtester)
- Quality report JSON artifact saved via crash-safe write pattern (`.partial` -> flush -> rename)
- Validated CSV with quarantine column saved to `{storage_path}/validated/` directory
- Session labeler utility (`assign_session`, `assign_sessions_bulk`) built for reuse in Story 1.6
- `validator_cli.py` provides `run_validation()` entry point that loads raw data and runs full validation
- All thresholds read from config (`data.quality` section), not hardcoded
- Session schedule read from config (`sessions` section) per Architecture D7
- All logging uses structured JSON with `component: "quality_checker"` and `stage: "data_pipeline"` per D6
- Vectorized pandas operations used throughout for 5M+ row performance
- Gap detection ported weekend-gap logic from ClaudeBackTester baseline; scoring built new per Architecture
- 33 unit tests + 3 integration tests + 2 live tests = 38 total tests, all passing
- Full regression suite: 77 passed, 3 skipped (live downloader tests), 0 failures

### Change Log
- 2026-03-14: Story 1.5 implementation complete — all 11 tasks and 24+ subtasks done

### File List
- `src/python/data_pipeline/quality_checker.py` — NEW: DataQualityChecker class (gap detection, price integrity, spread outliers, timezone, stale quotes, completeness, scoring, quarantine, report, orchestration)
- `src/python/data_pipeline/session_labeler.py` — NEW: assign_session() and assign_sessions_bulk() for session labeling
- `src/python/data_pipeline/validator_cli.py` — NEW: run_validation() entry point
- `src/python/data_pipeline/__init__.py` — MODIFIED: added exports for new modules
- `src/python/tests/test_data_pipeline/test_quality_checker.py` — NEW: 24 unit tests + 3 integration tests + 2 live tests
- `src/python/tests/test_data_pipeline/test_session_labeler.py` — NEW: 9 unit tests for session labeling
