# Data Pipeline Baseline Review — ClaudeBackTester

**Date:** 2026-03-14
**Reviewer:** Claude Opus 4.6 (1M context)
**Baseline Project:** `C:\Users\ROG\Projects\ClaudeBackTester`
**Architecture Reference:** `_bmad-output/planning-artifacts/architecture.md`

---

## 1. Executive Summary

The ClaudeBackTester data pipeline is a functional, production-used system across five modules: acquisition (Dukascopy download), validation (gap/anomaly detection), splitting (chronological train/test), timeframe conversion (M1→higher TFs), and storage (Parquet on Google Drive). The codebase is well-organized under `backtester/data/` with clean module boundaries and a working test suite.

**Key findings:** The acquisition module is the strongest component — it uses the `dukascopy-python` library for a clean, resumable download flow with atomic writes. Validation has solid gap detection and anomaly checks but uses a different scoring model than the Architecture requires. Splitting and timeframe conversion are simple and correct but lack the Architecture's reproducibility guarantees (hashing, manifests, versioning). Storage is Parquet-only — no Arrow IPC, no schema contracts, no mmap support. The entire pipeline uses `structlog` for logging (good pattern) but not the structured JSON format the Architecture mandates.

**Overall verdict:** Most modules fall in the "adapt" category. The core download/validation/conversion logic is reusable, but every module needs wrapping in the Architecture's config-driven, schema-validated, crash-safe, structured-logging framework. No module can be used as-is.

---

## 2. Module Inventory

| File | Module | Lines | Purpose |
|---|---|---|---|
| `backtester/data/__init__.py` | Package root | 26 | Public API exports |
| `backtester/data/downloader.py` | Acquisition | 373 | Dukascopy M1 bid+ask download, yearly chunking, consolidation, incremental update |
| `backtester/data/validation.py` | Validation | 305 | Gap detection, zero/NaN checks, anomaly detection, quality scoring, data validation |
| `backtester/data/splitting.py` | Splitting | 85 | Chronological back/forward and holdout splitting |
| `backtester/data/timeframes.py` | Timeframe Conversion | 145 | M1→M5/M15/M30/H1/H4/D/W resampling, H1-to-M1 mapping |
| `tests/test_data.py` | Tests | 339 | Unit tests for all data modules |
| `scripts/download_all.py` | Orchestration | 74 | Batch download script for all 25 pairs |
| `.venv/.../dukascopy_python/__init__.py` | External Library | 413 | Dukascopy API client (REST via freeserv.dukascopy.com) |

**Libraries used:**
- `dukascopy-python>=0.3` — Dukascopy data fetching (REST API wrapper)
- `pandas>=2.2` — DataFrame operations
- `pyarrow>=15.0` — Parquet I/O engine (but no direct Arrow IPC usage)
- `numpy>=1.26` — Numeric operations
- `structlog>=24.1` — Structured logging

---

## 3. Component Verdict Table

| Component | Baseline Status | Verdict | Rationale | Effort |
|---|---|---|---|---|
| **Acquisition** (downloader.py) | Mature — resumable yearly-chunk downloads, bid+ask with spread, atomic writes | **Adapt** | Core download flow is solid but uses `dukascopy-python` library (REST API, not raw bi5). Needs: config-driven params, structured JSON logging, crash-safe write with `os.replace()`, versioned artifact output, download manifest. | Medium |
| **Validation** (validation.py) | Functional — gap detection, zero/NaN checks, anomaly detection, quality scoring | **Adapt** | Good gap detection with weekend/holiday awareness. Quality scoring uses different model (0-100 point deduction) vs Architecture's formula (1.0 - penalties). Needs: Architecture's exact formula, session-aware spread checks, quarantine marking, quality report artifact, stale quote detection. | Medium |
| **Splitting** (splitting.py) | Simple — chronological ratio split and holdout | **Adapt** | Correct chronological approach, clean implementation. Needs: dataset ID hashing (FR8), manifest creation, versioned artifact storage, config-driven split params, Arrow IPC table operations (currently pandas-only). | Medium |
| **Timeframe Conversion** (timeframes.py) | Functional — correct OHLCV aggregation via pandas resample | **Adapt** | Correct aggregation logic (first open, max high, min low, last close, sum volume). Needs: quarantined bar exclusion, session column handling, Arrow IPC output, crash-safe writes, config-driven timeframe list. No tick-to-M1 aggregation exists. | Medium |
| **Storage** (Parquet via pyarrow) | Basic — Parquet with snappy compression, atomic writes | **Adapt** | Parquet writing works. Needs: Arrow IPC as primary compute format, schema validation against contracts, mmap verification, three-format strategy (Arrow IPC + Parquet + SQLite), versioned artifact directories. | High |

---

## 4. Detailed Component Analysis

### 4.1 Acquisition Module (`downloader.py`)

**What it does:**
- Downloads M1 bid and ask data separately via `dukascopy-python` library
- Computes per-candle spread as `avg(ask_open - bid_open, ask_close - bid_close)`
- Stores as yearly Parquet chunks: `{pair}_M1_chunks/{pair}_M1_{year}.parquet`
- Consolidates all chunks into a single file: `{pair}_M1.parquet`
- Supports resume (skips downloaded years) and incremental update (re-downloads current year)
- Atomic writes via `.parquet.tmp` → `replace()`

**How it downloads:**
- Uses `dukascopy-python` library which calls `freeserv.dukascopy.com/2.0/index.php` REST API
- This is NOT the raw bi5 binary format — it's a JSON/JSONP API that returns pre-aggregated OHLCV data
- The library handles pagination via cursor-based streaming and JSONP callback extraction
- Rate limiting: 1-second sleep between bid and ask downloads per year; retries up to 7 times with 1-second delay
- Library returns pandas DataFrame with timezone-aware UTC timestamps

**Strengths:**
- Clean resumable download with yearly chunking (skip already-downloaded years)
- Incremental update by re-downloading only the current year
- Atomic writes using `.tmp` → `replace()` pattern
- Spread computation from both bid and ask sides
- Good progress logging with structlog
- Handles partial ask data gracefully (NaN spread where ask is missing)
- 25 pairs configured, 2005-present date range

**Weaknesses:**
- Uses `dukascopy-python` library (third-party, lightweight) rather than direct raw bi5 download
  - Pro: simpler, returns clean DataFrames directly
  - Con: depends on Dukascopy's free web API availability; no raw bi5 tick data support
- No configurable parameters — `DEFAULT_DATA_DIR`, `DEFAULT_START_YEAR`, `ALL_PAIRS` are module-level constants
- No timeout configuration (relies on library defaults)
- No structured JSON logging (uses structlog but in console renderer mode)
- No crash-safe write with `os.fsync()` — uses `.tmp` → `replace()` but no flush/fsync
- No versioned artifacts — consolidation overwrites the single file
- No download manifest or hash computation
- `shutil.rmtree()` in force mode deletes all chunks without backup
- Column format: `open, high, low, close, volume, spread` — no separate bid/ask columns in output (spread is pre-computed)

**Assessment against Architecture requirements:**
- **D7 (Config):** FAILS — hardcoded constants, no TOML config, no schema validation
- **D6 (Logging):** PARTIAL — uses structlog (good) but not structured JSON format with the unified schema
- **D8 (Error):** PARTIAL — logs exceptions but doesn't use structured error codes from `contracts/error_codes.toml`
- **Crash-safe write:** PARTIAL — uses `.tmp` → `replace()` but no `os.fsync()` before rename
- **Consistent sourcing (FR8):** FAILS — no hash-based dataset identification, overwrites on consolidation

### 4.2 Validation Module (`validation.py`)

**What it does:**
- `detect_gaps()`: Finds timestamp gaps > 3x expected interval, classifies as weekend/holiday/unexpected
- `detect_zeros_nans()`: Counts zero and NaN values in OHLC columns
- `detect_anomalies()`: Flags extreme range candles, zero-range candles, OHLC violations (high < low)
- `check_yearly_coverage()`: Identifies missing or sparse years
- `compute_quality_score()`: 0-100 point deduction scoring system
- `validate_data()`: Combines scoring with min_score/min_candles threshold checks

**Strengths:**
- Excellent weekend gap detection with generous windowing (Friday 20:00+ to Monday 01:00)
- Holiday awareness (Christmas Dec 24-26, New Year Dec 31-Jan 2)
- Separate treatment of zero-range M1 candles (correctly identified as normal, not penalized)
- Adaptive extreme range threshold (50x for M1, 20x for M5, 10x for higher TFs)
- Yearly coverage analysis for long-term data completeness
- Clean separation of check types

**Weaknesses:**
- **Quality scoring model is different from Architecture:**
  - Baseline: 100-point scale with point deductions (gaps: -0.5 each up to -20, NaN: -5 each, etc.)
  - Architecture: 0-1 scale with formula `1.0 - (gap_penalty + integrity_penalty + staleness_penalty)`
  - These are fundamentally different approaches — cannot reuse the scoring logic directly
- No session-aware spread outlier detection (Architecture requires per-session median comparison)
- No stale quote detection (Architecture: bid=ask or spread=0 for > 5 consecutive bars)
- No quarantine marking (Architecture: `quarantined: bool` column)
- No quality report artifact output (Architecture: JSON report with all issues)
- No crash-safe write for any output
- Gap threshold is configurable via `gap_multiplier` (default 3x) but Architecture specifies "> 5 consecutive M1 bars" — different metric
- No DST artifact detection in timezone checks
- No per-session analysis at all
- No bid/ask specific checks (baseline data doesn't retain separate bid/ask columns)

**Assessment against Architecture requirements:**
- **Gap detection:** PARTIAL — works but uses different threshold (3x interval vs 5 consecutive bars)
- **Price integrity:** PARTIAL — checks zeros/NaN and OHLC violations, but no bid > 0 / ask > bid / spread within 10x median
- **Timezone alignment:** MISSING — no explicit UTC or monotonicity verification
- **Stale quotes:** MISSING — no bid=ask or spread=0 detection
- **Completeness:** PARTIAL — yearly coverage but not daily weekday verification
- **Quality scoring formula:** INCOMPATIBLE — different model entirely
- **Quarantine:** MISSING
- **Quality report artifact:** MISSING

### 4.3 Splitting Module (`splitting.py`)

**What it does:**
- `split_backforward()`: Chronological split by row count (default 80/20)
- `split_holdout()`: Reserve last N months as pure out-of-sample holdout
- `split_data()`: Dispatcher for split modes

**Strengths:**
- Correctly chronological — never shuffles, never randomly samples
- Simple, clean implementation
- Two useful split modes (ratio-based and date-based)
- Good structlog progress reporting
- Handles empty DataFrames gracefully

**Weaknesses:**
- No dataset ID or hash computation (FR8 consistent sourcing)
- No manifest creation (FR58, FR59 artifact traceability)
- No versioned output files — just returns DataFrames in memory, no persistence
- No config-driven parameters — split ratios are function arguments, not from TOML config
- Operates on pandas DataFrames, not Arrow IPC tables
- No temporal guarantee verification (doesn't assert `max(train.timestamp) < min(test.timestamp)`)
- No minimum set size validation
- No multi-timeframe aware splitting (doesn't apply same split point across timeframes)

**Assessment against Architecture requirements:**
- **FR7 (Chronological split):** PASS — correctly chronological
- **FR8 (Consistent sourcing):** FAILS — no hashing, no dataset ID, no versioning
- **D2 (Artifact storage):** FAILS — no file output, no versioning, no manifest
- **Crash-safe writes:** N/A — no file writes at all (operates in-memory only)

### 4.4 Timeframe Conversion Module (`timeframes.py`)

**What it does:**
- `resample_ohlcv()`: Resamples M1 data to higher timeframes using pandas `.resample()` with correct OHLCV aggregation
- `convert_single_timeframe()`: File-to-file conversion (Parquet → Parquet)
- `convert_timeframes()`: Batch conversion for all configured timeframes
- `build_h1_to_m1_mapping()`: Maps H1 bar indices to M1 sub-bar ranges (numpy searchsorted)

**Strengths:**
- Correct OHLCV aggregation: `first` open, `max` high, `min` low, `last` close, `sum` volume
- Spread column handled with `median` aggregation (reasonable choice)
- Atomic writes for converted files
- Clean pandas resample mapping (M5, M15, M30, H1, H4, D, W)
- Useful H1-to-M1 mapping function for multi-timeframe analysis (numpy O(n log n))
- Drops rows with no data (NaN close)

**Weaknesses:**
- No quarantined bar exclusion (Architecture: quarantined bars must not contribute to OHLC)
- No session column handling (Architecture: session must be preserved or recomputed)
- Parquet-only output (Architecture: Arrow IPC + Parquet)
- No schema validation against contracts
- No config-driven timeframe list
- No bid/ask column aggregation (baseline only has spread, Architecture requires separate bid/ask)
- No tick-to-M1 aggregation capability
- Weekly alignment uses pandas `W-MON` (ISO Monday-Sunday), Architecture notes forex weeks are Sunday 22:00 to Friday 22:00
- No crash-safe write with `os.fsync()`
- No determinism guarantees (pandas resample may produce slightly different results with different pandas versions)

**Assessment against Architecture requirements:**
- **FR6 (Timeframe conversion):** PARTIAL — correct OHLCV aggregation but missing quarantine/session handling
- **D2 (Three-format storage):** FAILS — Parquet only, no Arrow IPC
- **Session-awareness:** MISSING — no session column
- **Crash-safe writes:** PARTIAL — atomic rename but no fsync

### 4.5 Storage Patterns

**What exists:**
- Parquet with snappy compression via pyarrow engine (all modules)
- Atomic writes via `.tmp` → `replace()` in downloader and timeframe converter
- Google Drive storage path (`G:/My Drive/BackTestData`) as default
- Pipeline checkpoint to JSON with atomic write in `pipeline/checkpoint.py`

**What's missing:**
- Arrow IPC format entirely (no mmap-friendly compute files)
- Schema validation against `contracts/arrow_schemas.toml` (contracts don't exist)
- Three-format strategy (Arrow IPC + SQLite + Parquet)
- `os.fsync()` before atomic rename (crash-safety incomplete)
- Versioned artifact directories (overwrites single files)
- Partial file cleanup on startup
- Data hash computation for reproducibility

---

## 5. Undiscovered Capabilities

Capabilities found in ClaudeBackTester that are NOT mentioned in the Forex Pipeline PRD or Architecture:

| Capability | Location | Assessment |
|---|---|---|
| **Multi-pair batch download** (`download_all_pairs()`, `ALL_PAIRS` list of 25 pairs) | `downloader.py` | **Should adopt.** The Architecture focuses on single-pair examples (EURUSD), but the PRD mentions multiple pairs. Having a batch download orchestrator is operationally valuable. Add to Story 1.4 or as a separate utility. |
| **Freshness checking** (`is_stale()`, `ensure_fresh()`) | `downloader.py` | **Should adopt.** Checks data age and auto-updates if stale. Useful for live trading pipeline (Epic 6). Not needed for MVP but worth noting for later. |
| **Yearly chunk storage with consolidation** | `downloader.py` | **Consider adopting.** Storing data as yearly Parquet chunks enables partial re-downloads. The Architecture's versioned artifact approach is better for reproducibility, but the yearly chunking concept could complement it for download resume scenarios. |
| **H1-to-M1 bar mapping** (`build_h1_to_m1_mapping()`) | `timeframes.py` | **Already covered.** This is needed for multi-timeframe strategy execution. The Architecture implies this in the backtester stage but doesn't specify it in the data pipeline. Keep as reference for Epic 2. |
| **Holdout split mode** (`split_holdout()`) | `splitting.py` | **Should adopt.** The Architecture specifies ratio-based splitting, but holdout-by-date is also valuable for validation. Consider adding `split_mode = "date"` support to Story 1.8 (already planned). |
| **Extreme range detection with adaptive thresholds** | `validation.py` | **Consider adopting.** The 50x/20x/10x median range multiplier per timeframe is a practical approach that the Architecture's quality scoring doesn't explicitly address. Could complement the Architecture's quality checks. |

---

## 6. Superior Baseline Patterns

| Pattern | Baseline Approach | Architecture Specification | Recommendation |
|---|---|---|---|
| **Dukascopy access via library** | Uses `dukascopy-python` library — clean Python API, handles pagination, JSONP parsing, retry logic | Story 1.4 plans to build raw bi5 binary decoder from scratch | **Adopt baseline approach.** The `dukascopy-python` library works well, handles the Dukascopy REST API correctly, and returns clean DataFrames. Building a raw bi5 decoder is unnecessary complexity. The library already handles M1 bar data; for tick data, evaluate if the library supports `INTERVAL_TICK`. If not, add tick support to Story 1.4 as an extension. |
| **Yearly chunk + consolidation** | Download one year at a time, store as individual Parquet files, consolidate. Resume by skipping downloaded years. | Architecture specifies versioned artifacts but doesn't detail download chunking strategy | **Adapt.** The yearly chunking is a good download-resume pattern. Combine with the Architecture's versioned artifacts: yearly chunks as intermediate artifacts, consolidated + validated data as the versioned final artifact. |
| **Spread as computed column** | Spread = avg(ask_open - bid_open, ask_close - bid_close), stored as single column | Architecture specifies separate bid/ask columns in Arrow IPC schema | **Follow Architecture.** The Architecture's approach is better — separate bid/ask columns preserve more information. But the spread computation logic is a useful reference for the quality checker's spread outlier detection. |
| **structlog for logging** | All data modules use `structlog.get_logger()` with key-value pairs | Architecture specifies structured JSON to `logs/` with unified schema | **Adapt.** The structlog pattern is good but needs to be switched to JSON output matching the Architecture's exact schema (`ts`, `level`, `runtime`, `component`, `stage`, `strategy_id`, `msg`, `ctx`). Story 1.3 builds this from scratch. |

---

## 7. Weaknesses and Technical Debt

### DO NOT Carry Forward

| Weakness | Location | What the New System Should Do Instead |
|---|---|---|
| **Hardcoded configuration** — `DEFAULT_DATA_DIR`, `DEFAULT_START_YEAR`, `ALL_PAIRS` are module constants, not configurable | `downloader.py:25-34` | All parameters must come from `config/base.toml` per D7. No hardcoded defaults in module code. |
| **No crash-safe fsync** — atomic rename without `os.fsync()` means data could be lost on power failure between OS write cache and disk | All modules | Use the Architecture's full pattern: write to `.partial`, `f.flush()`, `os.fsync(f.fileno())`, `os.replace()` |
| **Overwrites on consolidation** — `consolidate_chunks()` writes to `{pair}_M1.parquet`, destroying the previous version | `downloader.py:174-211` | Never overwrite. New downloads create new versioned artifacts. Dataset ID includes hash for traceability. |
| **No schema contracts** — data format is implicit (whatever pandas DataFrame columns happen to be) | All modules | Arrow IPC schema loaded from `contracts/arrow_schemas.toml`. Validate before every write. Fail loud on mismatch. |
| **Quality scoring model (0-100 point deduction)** — ad hoc, not based on quantitative penalties | `validation.py:197-267` | Use Architecture's explicit formula: `1.0 - (gap_penalty + integrity_penalty + staleness_penalty)` with specific multipliers. |
| **No quarantine system** — bad data is flagged but not marked in the data itself | `validation.py` | Add `quarantined: bool` column. Backtester skips quarantined bars. Quality report lists all quarantined periods. |
| **No session awareness** — no per-session analysis, no session column, no session-aware thresholds | All modules | Sessions are a first-class architectural dimension. Session column computed during data pipeline stage. Quality checks must be session-aware. |
| **Pipeline checkpoint uses `os.rename()` on Windows** — not atomic if destination exists (must remove first) | `checkpoint.py:44-48` | Use `os.replace()` which atomically replaces destination on all platforms. |
| **Mixed logging patterns** — some modules use `structlog`, pipeline modules use stdlib `logging.getLogger()` | `checkpoint.py:29` vs `downloader.py:22` | Unified structured JSON logging per D6. One pattern, one format, everywhere. |
| **No reproducibility guarantees** — no data hashing, no config hashing, no manifest linking inputs to outputs | All modules | Every artifact includes config hash + data hash. Re-runs with same inputs produce identical outputs (FR61). |
| **`shutil.rmtree()` in force download** — silently deletes all chunks without confirmation or backup | `downloader.py:248-250` | Never delete data without operator confirmation. Force re-download should create a new version, not destroy the old one. |
| **No tests for downloader network calls** — test_data.py only tests offline utilities | `tests/test_data.py` | Integration tests with mocked HTTP responses to verify retry logic, error handling, timeout behavior. |

### Architectural Issues

| Issue | Impact | Severity |
|---|---|---|
| No Arrow IPC support anywhere | Rust compute layer cannot mmap data | High — blocks Phase 1 |
| No schema contracts | Data format drift between Python and Rust is invisible | High — blocks Phase 1 |
| No structured JSON logs | Cannot parse logs programmatically for monitoring | Medium |
| No config validation at startup | Invalid config discovered mid-run, not at startup | Medium |
| Single consolidated file per pair | No versioning, no reproducibility, no rollback | High — breaks FR8 |

---

## 8. Proposed Architecture Updates

Based on the review findings, the following Architecture updates are recommended for operator review:

### 8.1 Dukascopy Download Mechanism

**Current Architecture text** (Story 1.4 dev notes): Describes building a raw bi5 binary decoder with URL pattern `https://datafeed.dukascopy.com/datafeed/{PAIR}/{year}/{month}/{day}/{hour}h_ticks.bi5` and 20-byte binary record parsing.

**Finding:** ClaudeBackTester uses the `dukascopy-python` library which calls a different endpoint: `freeserv.dukascopy.com/2.0/index.php` — a REST API that returns pre-aggregated OHLCV data as JSON. This is simpler, returns clean DataFrames directly, and is proven in production.

**Proposed change:** Update Story 1.4's approach to first evaluate `dukascopy-python` for M1 bar data (which it handles well), and only implement raw bi5 decoding if:
- Tick data is needed (verify if `dukascopy-python` supports `INTERVAL_TICK`)
- The library becomes unmaintained or unreliable
- Custom download behavior is needed (e.g., per-hour chunking for resume)

**Section to update:** Story 1.4 Dev Notes → "Technical Requirements" and "What to Reuse from ClaudeBackTester"

### 8.2 Spread Column vs Separate Bid/Ask

**Current Architecture:** Arrow IPC `market_data` schema has separate `bid` and `ask` columns (float64).

**Finding:** The `dukascopy-python` library downloads bid-side and ask-side OHLCV separately. The baseline computes a single `spread` column. To populate the Architecture's `bid` and `ask` columns, Story 1.4 needs to:
1. Download both bid and ask OHLCV
2. Store the close bid and close ask from each side as the `bid` and `ask` columns
3. This is exactly what the baseline does in `_add_spread()` but retains the original values instead of computing a delta

**Proposed change:** No Architecture change needed, but Story 1.4 should explicitly document that `bid` = bid-side close price and `ask` = ask-side close price per candle. This clarification prevents ambiguity.

### 8.3 Extreme Range Detection

**Current Architecture:** Not explicitly mentioned in the quality checks table.

**Finding:** The baseline has useful extreme range detection (50x/20x/10x median by timeframe) and OHLC violation checks (high < low). These are practical data integrity checks.

**Proposed change:** Consider adding to the Data Quality Gate Specifications table:
```
| Extreme range | Flag candles where (high - low) > 50× median range for M1 | WARNING | Log and include in quality report |
| OHLC violation | high < low (inverted candle) | ERROR | Quarantine bar |
```

---

## 9. Impact on Stories 1.3-1.9

| Story | Title | Build Approach | Rationale |
|---|---|---|---|
| **1.3** | Project Structure, Config & Logging | **Build new** | Baseline config is hardcoded constants, not TOML. Baseline logging uses structlog console renderer, not structured JSON. Building fresh per Architecture specs is cleaner than adapting. Reference baseline's structlog usage pattern. |
| **1.4** | Dukascopy Data Download | **Adapt** | Baseline downloader works well. Evaluate `dukascopy-python` library vs raw bi5. Port the download flow (yearly chunks, resume, bid+ask), wrap in config-driven architecture with structured logging, crash-safe writes, versioned artifacts. Key adaptation: retain separate bid/ask values instead of computing spread. |
| **1.5** | Data Validation & Quality Scoring | **Adapt core checks, replace scoring** | Port gap detection (`_is_weekend_gap`, `_is_holiday_gap`), zero/NaN checks, anomaly detection. Replace quality scoring model entirely with Architecture's formula. Add new: session-aware spread checks, stale quote detection, quarantine marking, quality report artifact. |
| **1.6** | Parquet Storage & Arrow IPC | **Build new (Arrow IPC), adapt (Parquet)** | Baseline has Parquet writing with pyarrow — reusable pattern. Arrow IPC is entirely new. Schema loading from contracts is new. mmap verification is new. Session column stamping is new. |
| **1.7** | Timeframe Conversion | **Adapt** | Baseline's `resample_ohlcv()` aggregation logic is correct and reusable. Adapt to: work with Arrow IPC tables, exclude quarantined bars, handle session column, add tick-to-M1 (new), fix weekly boundary alignment (forex week vs ISO week). |
| **1.8** | Data Splitting & Consistent Sourcing | **Adapt split logic, build new hashing/manifest** | Baseline's chronological split is correct. Build new: dataset ID with hash, manifest creation, versioned artifact storage, consistent sourcing verification, multi-timeframe aware splitting. |
| **1.9** | E2E Pipeline Proof | **Build new** | No equivalent exists in baseline. This is the capstone verification that all components work together. Entirely new. |

### Effort Summary

| Approach | Count | Effort |
|---|---|---|
| Build new | 3 stories (1.3, 1.6 Arrow IPC, 1.9) | High |
| Adapt | 4 stories (1.4, 1.5, 1.7, 1.8) | Medium each |
| Keep as-is | 0 stories | — |

**Total estimate:** The baseline saves significant effort in Stories 1.4, 1.5, 1.7, and 1.8 by providing proven logic that can be ported. Stories 1.3 (foundation), 1.6 (Arrow IPC), and 1.9 (E2E proof) are genuinely new work.
