# Story 3.7: AI Analysis Layer — Narrative, Anomaly Detection & Evidence Packs

Status: review

## Research Update Note (2026-03-18)

This story has been updated to reflect architecture research findings from Stories 3-1/3-2, Research Briefs 3A-3C, and optimization methodology research.

**Key changes:**
- **D11 (Deterministic-First Architecture):** All analysis follows deterministic computation first, narrative second. Metrics, anomaly detection, and evidence assembly are pure deterministic Python — no stochastic or LLM-dependent components. This is already the design intent (template-driven narratives), but the principle is now explicitly stated in architecture D11.
- **D11 (Two-Pass Evidence Pack Design):** Evidence packs support a two-pass review workflow: Phase 1 triage (~60s, automated anomaly flags + key metrics) and Phase 2 deep review (5-15min, full narrative + session breakdown + equity analysis). Epic 3 implements both passes in a single `assemble_evidence_pack()` call; the triage/deep distinction becomes operationally relevant in Epic 5 when processing thousands of optimization candidates.
- **D11 (DSR/PBO Validation Methodology):** Architecture D11 now references Deflated Sharpe Ratio (DSR) and Probability of Backtest Overfitting (PBO) as validation gates. These are Epic 5 scope — this story adds forward-compatible anomaly types but does NOT implement DSR/PBO computation.

**References:** architecture.md Research Update to D11; Research Brief 3B (overfitting detection); Research Brief 3C (deterministic-first AI)

## Story

As the **operator**,
I want **backtest results presented with a summary narrative, anomaly flags, and a coherent evidence pack**,
So that **I can quickly understand what happened, spot problems, and make informed decisions about pipeline progression**.

## Acceptance Criteria

1. **Given** backtest results exist in SQLite and Arrow IPC (Story 3.6 output),
   **When** the AI analysis layer processes the results,
   **Then** a summary narrative is generated presenting results chart-first: equity curve shape, drawdown profile, trade distribution — followed by key metrics and interpretation.
   [FR16, D11]

2. **Given** a completed backtest run,
   **When** anomaly detection runs automatically,
   **Then** it checks for ALL of the following conditions using architecture D11 thresholds:
   - Low trade count: < 30 trades over backtest period → WARNING
   - Zero trades: 0 trades in any 2-year window → ERROR
   - Suspiciously perfect equity curve: max drawdown < 1% with > 100 trades → ERROR
   - Parameter sensitivity cliff: > 50% performance change from ±1 step in any parameter → WARNING
   - Extreme profit factor: profit factor > 5.0 → WARNING
   - Trade clustering: > 50% of trades in single calendar month → WARNING
   - Win rate extremes: win rate > 90% or < 20% with > 50 trades → WARNING
   [FR17, D11]

3. **Given** an anomaly is detected,
   **When** flagged,
   **Then** each anomaly includes: `type` (enum), `severity` (WARNING | ERROR), `description` (human-readable), `evidence` (supporting data), and `recommendation` (suggested action).
   [D11]

4. **Given** narrative and anomaly detection are complete,
   **When** the evidence pack is assembled,
   **Then** it contains: narrative summary, key metrics table, anomaly flags (if any), downsampled equity curve summary, trade distribution by session, and a reference path to the full trade log.
   [FR39, D11]

5. **Given** a complete evidence pack,
   **When** it is persisted,
   **Then** it is saved as a versioned artifact at: `artifacts/{strategy_id}/v{NNN}/backtest/evidence_pack.json` containing narrative text, anomaly flags, metrics, evidence pack metadata, and a `manifest_path` referencing the Story 3.6 manifest for full provenance.
   [FR58, D11]

6. **Given** an evidence pack is assembled,
   **When** the operator reviews it,
   **Then** it contains ALL of the following fields: narrative overview, key metrics table (win rate, profit factor, Sharpe, max DD, total trades), anomaly flags (possibly empty), downsampled equity curve summary (max 500 points), trade distribution by session, and a reference path to the full trade log Arrow IPC artifact — sufficient for an accept/reject/refine decision without inspecting raw data.
   [FR39]

7. **Given** anomaly flags exist on a backtest run,
   **When** the operator considers pipeline progression,
   **Then** anomaly flags do NOT block progression — they inform the operator's decision but the system allows any strategy to advance.
   [FR41]

## Tasks / Subtasks

- [x] **Task 1: Define analysis data models and interfaces** (AC: #3)
  - [x] Create `src/python/analysis/metrics_builder.py`:
    - `compute_metrics(trades_df, run_meta) -> dict` — single shared function that computes `{win_rate, profit_factor, sharpe_ratio, max_drawdown_pct, total_trades, avg_trade_pnl, total_pnl, avg_trade_duration}` from trade data. Both narrative generator and evidence pack assembler MUST call this — never compute metrics independently.
  - [x] Create `src/python/analysis/models.py` with dataclasses:
    - `NarrativeResult(overview: str, metrics: dict, strengths: list[str], weaknesses: list[str], session_breakdown: dict, risk_assessment: str)`
    - `AnomalyFlag(type: AnomalyType, severity: Severity, description: str, evidence: dict, recommendation: str)`
    - `AnomalyReport(backtest_id: str, anomalies: list[AnomalyFlag], run_timestamp: str)`
    - `EvidencePack(backtest_id: str, strategy_id: str, version: str, narrative: NarrativeResult, anomalies: AnomalyReport, metrics: dict, equity_curve_summary: list[dict], equity_curve_full_path: str, trade_distribution: dict, trade_log_path: str, metadata: dict)`
    - `AnomalyType` enum: `LOW_TRADE_COUNT`, `ZERO_TRADES`, `PERFECT_EQUITY`, `SENSITIVITY_CLIFF`, `EXTREME_PROFIT_FACTOR`, `TRADE_CLUSTERING`, `WIN_RATE_EXTREME`, `DSR_BELOW_THRESHOLD` (Research Update: forward-compatible, Epic 5 implementation), `PBO_HIGH_PROBABILITY` (Research Update: forward-compatible, Epic 5 implementation)
    - `Severity` enum: `WARNING`, `ERROR`
  - [x] Define `to_json()` / `from_json()` serialization on each dataclass
  - [x] Update `src/python/analysis/__init__.py` to export public interfaces

- [x] **Task 2: Implement narrative generator** (AC: #1)
  - [x] Create `src/python/analysis/narrative.py`
  - [x]Implement `generate_narrative(backtest_id: str, db_path: Path | None = None) -> NarrativeResult`
  - [x]Query SQLite `backtest_runs` table for run metadata (strategy_id, total_trades, started_at, completed_at)
  - [x]Query SQLite `trades` table for trade-level data (pnl_pips, session, direction, entry_time, exit_time, spread_cost, slippage_cost)
  - [x]Compute summary statistics via shared `compute_metrics()` from `metrics_builder.py`: win rate, profit factor, total pnl, avg win/loss, max drawdown, Sharpe ratio, trade count
  - [x]Compute session breakdown: per-session trade count, win rate, avg pnl (GROUP BY session — values from `contracts/session_schema.toml`: asian, london, new_york, london_ny_overlap, off_hours)
  - [x]Generate chart-first narrative structure:
    1. **Overview**: equity curve shape description (trending up/down/sideways, volatility), drawdown profile (max DD, recovery), trade distribution pattern
    2. **Key Metrics**: win rate, profit factor, Sharpe, max DD, total trades, avg trade duration
    3. **Strengths**: identified from metrics (e.g., consistent session performance, low drawdown)
    4. **Weaknesses**: identified from metrics (e.g., high drawdown, clustered losses)
    5. **Session Breakdown**: per-session performance table
    6. **Risk Assessment**: overall risk characterization based on metrics
  - [x]Return structured `NarrativeResult` (not free-text — template-driven sections)

- [x] **Task 3: Implement anomaly detector** (AC: #2, #3, #7)
  - [x]Create `src/python/analysis/anomaly_detector.py`
  - [x]Implement `detect_anomalies(backtest_id: str, db_path: Path | None = None) -> AnomalyReport`
  - [x]Query SQLite for trade data and run metadata
  - [x]Implement each anomaly check as a separate private function:
    - `_check_low_trade_count(trades_df, run_meta) -> AnomalyFlag | None` — < 30 trades → WARNING
    - `_check_zero_trade_windows(trades_df, run_meta) -> AnomalyFlag | None` — 0 trades in any 2-year window → ERROR
    - `_check_perfect_equity(trades_df) -> AnomalyFlag | None` — max DD < 1% with > 100 trades → ERROR
    - `_check_sensitivity_cliff(backtest_id, db_path) -> AnomalyFlag | None` — STUB: always returns `None` with a debug log. Requires optimization_candidates data that doesn't exist at backtest stage. Real implementation deferred to optimization stories (Epic 5). Keep enum value and function signature for forward compatibility.
    - `_check_dsr_below_threshold(backtest_id, db_path) -> AnomalyFlag | None` — **Research Update:** STUB: always returns `None`. DSR (Deflated Sharpe Ratio) computation requires trial count context from optimization. Epic 5 implementation. Forward-compatible enum value `DSR_BELOW_THRESHOLD` defined.
    - `_check_pbo_high_probability(backtest_id, db_path) -> AnomalyFlag | None` — **Research Update:** STUB: always returns `None`. PBO (Probability of Backtest Overfitting) requires combinatorial validation across folds. Epic 5 implementation. Forward-compatible enum value `PBO_HIGH_PROBABILITY` defined.
    - `_check_extreme_profit_factor(trades_df) -> AnomalyFlag | None` — PF > 5.0 → WARNING
    - `_check_trade_clustering(trades_df) -> AnomalyFlag | None` — > 50% trades in single calendar month → WARNING
    - `_check_win_rate_extremes(trades_df) -> AnomalyFlag | None` — > 90% or < 20% with > 50 trades → WARNING
  - [x]Each checker returns `None` if no anomaly, or an `AnomalyFlag` with populated evidence dict
  - [x]Collect all flags into `AnomalyReport`; anomalies list may be empty (healthy result)
  - [x]CRITICAL: anomaly flags are informational ONLY — never raise exceptions or return error codes that could block pipeline

- [x] **Task 4: Implement evidence pack assembler** (AC: #4, #5, #6)
  - [x]Create `src/python/analysis/evidence_pack.py`
  - [x]Implement `assemble_evidence_pack(backtest_id: str, db_path: Path | None = None, artifacts_root: Path | None = None) -> EvidencePack`
  - [x]**Research Update (Two-Pass Design):** Epic 3 assembles the full evidence pack in a single pass. The two-pass distinction (Phase 1: ~60s triage with anomaly flags + key metrics; Phase 2: 5-15min deep review with full narrative + session analysis) becomes operationally relevant in Epic 5 for processing optimization candidate batches. The data model supports both passes — `EvidencePack` contains all fields for deep review; a future `TriageSummary` can be derived from the metrics + anomalies subset.
  - [x]Call `generate_narrative(backtest_id)` and `detect_anomalies(backtest_id)` internally
  - [x]Query equity curve data points from Arrow IPC file (read via pyarrow, NOT pandas): `artifacts/{strategy_id}/v{NNN}/backtest/equity-curve.arrow`
  - [x]Downsample equity curve to max 500 representative points using LTTB (Largest Triangle Three Buckets) or simple stride sampling. Store downsampled points in evidence pack JSON; reference canonical Arrow IPC path for full-resolution data.
  - [x]Compute trade distribution by session from SQLite trades table
  - [x]Call shared `compute_metrics()` from `metrics_builder.py` (same function used by narrative generator) — do NOT recompute independently
  - [x]Set `trade_log_path` to relative path: `artifacts/{strategy_id}/v{NNN}/backtest/trade-log.arrow`
  - [x]Populate metadata: `{generated_at, backtest_run_id, strategy_id, version, pipeline_stage: "backtest", manifest_path: "artifacts/{strategy_id}/v{NNN}/backtest/manifest.json", schema_version: "1.0"}`
  - [x]Persist evidence pack JSON to: `artifacts/{strategy_id}/v{NNN}/backtest/evidence_pack.json`
    - Use crash-safe write pattern from Story 3-6: write to `.partial` → `fsync()` → `os.replace()`
  - [x]Return populated `EvidencePack` dataclass

- [x] **Task 5: Integrate with orchestrator post-stage hook** (AC: #1, #2, #4)
  - [x]Modify `src/python/orchestrator/stage_runner.py`:
    - After backtest-complete → review-pending transition (wired in Story 3-6)
    - Call `assemble_evidence_pack(backtest_id)` automatically
    - Log evidence pack path and anomaly count
    - If evidence pack fails: log error at WARNING level, set `evidence_pack_available: false` in pipeline state metadata so Story 3.8 can surface this to the operator. Do NOT block pipeline transition — the operator can re-trigger analysis or inspect raw artifacts manually.
  - [x]Evidence pack generation is automatic — no manual invocation needed

- [x] **Task 6: Write unit tests** (AC: #1–#8)
  - [x]Create `src/python/tests/test_analysis/__init__.py`
  - [x]Create `src/python/tests/test_analysis/test_narrative.py`:
    - `test_generate_narrative_basic_backtest` — standard backtest with mixed results
    - `test_generate_narrative_session_breakdown` — verifies per-session metrics computed correctly
    - `test_generate_narrative_chart_first_structure` — verifies overview comes before metrics
    - `test_generate_narrative_empty_trades` — handles zero-trade edge case
  - [x]Create `src/python/tests/test_analysis/test_anomaly_detector.py`:
    - `test_detect_anomalies_healthy_run` — no anomalies flagged on normal data
    - `test_detect_low_trade_count` — < 30 trades triggers WARNING
    - `test_detect_zero_trade_window` — 2-year gap triggers ERROR
    - `test_detect_perfect_equity` — DD < 1% with > 100 trades triggers ERROR
    - `test_detect_extreme_profit_factor` — PF > 5.0 triggers WARNING
    - `test_detect_trade_clustering` — > 50% in one month triggers WARNING
    - `test_detect_win_rate_extremes` — > 90% or < 20% with > 50 trades triggers WARNING
    - `test_anomalies_do_not_block` — verify report is informational, no exceptions raised
    - `test_sensitivity_cliff_stub_returns_none` — always returns None at backtest stage with debug log
    - `test_thresholds_loaded_from_config` — verify thresholds are read from config dict, not hardcoded
  - [x]Create `src/python/tests/test_analysis/test_metrics_builder.py`:
    - `test_compute_metrics_basic` — standard trade set produces expected values
    - `test_compute_metrics_empty_trades` — zero trades handled gracefully
    - `test_compute_metrics_single_trade` — edge case with one trade
    - `test_narrative_and_pack_use_same_metrics` — verify both call shared builder, not independent computation
  - [x]Create `src/python/tests/test_analysis/test_evidence_pack.py`:
    - `test_assemble_evidence_pack_complete` — all fields populated including manifest_path and schema_version
    - `test_evidence_pack_json_serialization` — round-trip to/from JSON
    - `test_evidence_pack_crash_safe_write` — partial file pattern verified
    - `test_evidence_pack_versioned_path` — correct artifact path structure using Story 3.6 conventions
    - `test_evidence_pack_equity_curve_downsampled` — verify equity curve summary has max 500 points even when source has thousands
    - `test_evidence_pack_artifact_filenames` — verify `trade-log.arrow` and `equity-curve.arrow` (hyphenated, matching Story 3.6)

- [x] **Task 7: Write integration test** (AC: #4, #5)
  - [x]Create `src/python/tests/test_analysis/test_analysis_integration.py`:
    - `test_full_analysis_pipeline` — Arrow IPC fixture → SQLite ingest → narrative + anomalies + evidence pack
    - `test_evidence_pack_reads_story_3_6_output` — uses Story 3-6 artifact structure as input
  - [x]Use test fixtures from `tests/fixtures/backtest_output/` (created in Story 3-6)

## Dev Notes

### Architecture Constraints

- **D11 (AI Analysis Layer)**: This story implements three of five D11 components. `candidate_compressor` is Epic 5 scope. `refinement_suggester` is Epic 8 (Growth) scope. Do NOT implement them here. **Research Update:** D11 now mandates deterministic computation first, LLM narration second (though V1 uses template-driven narration, not LLM). Two-pass evidence pack design (triage + deep review) is architecturally defined but both passes execute in single call for Epic 3. DSR and PBO validation gates are Epic 5 scope — add forward-compatible enum values only.
- **D2 (Three-Layer Storage)**: Arrow IPC is canonical, SQLite is queryable index. Read from both: SQLite for trade queries, Arrow IPC for equity curve data.
- **D3 (Pipeline Orchestration)**: Evidence pack generation hooks into stage_runner.py post-backtest transition. Failure must not block pipeline.
- **Python-only**: No Rust boundary for analysis. All modules are pure Python reading SQLite + Arrow IPC.

### Artifact Filename Decision

The epics document specifies `narrative.json` as the evidence pack filename. This story uses `evidence_pack.json` instead because the artifact contains narrative + anomalies + metrics + equity data + trade distribution — not just the narrative. The filename `evidence_pack.json` accurately describes contents and avoids confusion with a hypothetical narrative-only file. Story 3.8 should reference `evidence_pack.json` when loading for operator review.

### Default Path Resolution

All analysis functions accept optional `db_path` and `artifacts_root` parameters. When `None`, resolve defaults from the project config:
- `db_path`: Load from `config_loader.get("sqlite_db_path")` or derive from `artifacts_root / strategy_id / "backtest.db"`
- `artifacts_root`: Load from `config_loader.get("artifacts_root")` or default to `Path("artifacts")`
- Import `from src.python.config_loader import get_config` for path resolution

### Threshold Source of Truth

The architecture D11 anomaly thresholds table is SSOT — not the simplified examples in the epics AC. The epics AC mentions "< 10 trades per year" and "R² > 0.99" as examples; architecture specifies "< 30 trades over period" and "max DD < 1% with > 100 trades". **Use architecture D11 thresholds.**

Thresholds MUST be loaded from a config dict (not hardcoded in checker functions). Define default thresholds as a `ANOMALY_THRESHOLDS` dict in `anomaly_detector.py` that can be overridden by `config_loader`. This enables future extraction to `contracts/anomaly_thresholds.toml` without code changes.

### Version Resolution

Use Story 3.6's `resolve_version_dir()` from `src/python/artifacts/storage.py` to resolve `v{NNN}` paths. Alternatively, read the version from pipeline state (set during Story 3.6 processing). Do NOT implement independent version resolution.

### AC8 Implementation Note

The analysis layer MUST be implemented as Python modules under `src/python/analysis/` with three primary interfaces: `generate_narrative(backtest_id)`, `detect_anomalies(backtest_id)`, `assemble_evidence_pack(backtest_id)` [D11]. This was AC8 in the epics but is an implementation constraint, not user-facing acceptance — verified via code review, not AC testing.

### Data Access Patterns

- **SQLite queries**: Use `sqlite3` module directly with parameterized queries. WAL mode is already enabled by `SQLiteManager` (Story 3-6). Access tables: `backtest_runs`, `trades`.
- **Arrow IPC reads**: Use `pyarrow.ipc.open_file()` to read equity curve data. Stream `RecordBatch`es — do NOT call `read_all()` on large files. Architecture sizes equity curves at ~125 MB Arrow IPC — evidence pack JSON embeds only a downsampled summary (max 500 points), not the full curve.
- **backtest_run_id format**: `{strategy_id}_{timestamp}_{config_hash_short}` — this is the `backtest_id` parameter passed to all analysis functions.
- **Session values**: `["asian", "london", "new_york", "london_ny_overlap", "off_hours"]` from `contracts/session_schema.toml`.

### SQLite Schema (from contracts/sqlite_ddl.sql)

Key tables the analysis layer queries:
- **backtest_runs**: `run_id` (PK), `strategy_id`, `config_hash`, `data_hash`, `spec_version`, `started_at`, `completed_at`, `total_trades`, `status`
- **trades**: `trade_id` (PK), `strategy_id`, `backtest_run_id` (FK), `direction`, `entry_time`, `exit_time`, `entry_price`, `exit_price`, `spread_cost`, `slippage_cost`, `pnl_pips`, `session`, `lot_size`, `candidate_id`
  - Indexes: `idx_trades_session`, `idx_trades_strategy_id`, `idx_trades_entry_time`, `idx_trades_candidate_id`

### Narrative JSON Output Structure (from D11)

```json
{
  "overview": "string — chart-first equity/drawdown/distribution description",
  "metrics": {"win_rate": 0.55, "profit_factor": 1.8, "sharpe_ratio": 1.2, "max_drawdown_pct": 12.3, "total_trades": 450, "avg_trade_pnl": 2.1, "total_pnl": 945.0},
  "strengths": ["Consistent London session performance", "Low max drawdown"],
  "weaknesses": ["Poor Asian session results", "Trade clustering in Q1"],
  "session_breakdown": {"asian": {"trades": 50, "win_rate": 0.40, "avg_pnl": -1.2}, "london": {"trades": 200, "win_rate": 0.62, "avg_pnl": 3.5}},
  "risk_assessment": "string — overall risk characterization"
}
```

### Anomaly Flag JSON Structure (from D11)

```json
{
  "type": "LOW_TRADE_COUNT",
  "severity": "WARNING",
  "description": "Only 25 trades over 5-year backtest period (< 30 threshold)",
  "evidence": {"trade_count": 25, "period_years": 5, "threshold": 30},
  "recommendation": "Consider whether strategy filters are too restrictive or data coverage is insufficient"
}
```

### Evidence Pack JSON Structure

```json
{
  "backtest_id": "ma-cross-v3_20260317_abc123",
  "strategy_id": "ma-cross-v3",
  "version": "v001",
  "pipeline_stage": "backtest",
  "generated_at": "2026-03-17T22:30:00Z",
  "narrative": { "...NarrativeResult..." },
  "anomalies": { "...AnomalyReport..." },
  "metrics": { "win_rate": 0.55, "..." },
  "equity_curve_summary": [{"timestamp": "...", "equity": 10000.0, "drawdown_pct": 0.0}, "... (max 500 downsampled points)"],
  "equity_curve_full_path": "artifacts/ma-cross-v3/v001/backtest/equity-curve.arrow",
  "trade_distribution": {"by_session": {"asian": 50, "london": 200, "..."}, "by_month": {"2025-01": 15, "..."}},
  "trade_log_path": "artifacts/ma-cross-v3/v001/backtest/trade-log.arrow",
  "metadata": {"config_hash": "abc123", "data_hash": "def456", "manifest_path": "artifacts/ma-cross-v3/v001/backtest/manifest.json", "schema_version": "1.0"}
}
```

### What to Reuse from Story 3-6

- **Crash-safe write pattern**: `.partial` → `fsync()` → `os.replace()` from `src/python/artifacts/storage.py`
- **Path derivation**: All paths from `artifacts_root` + `strategy_id` + version using `pathlib.Path`
- **SQLite access**: WAL mode, parameterized queries, batch reads
- **Test fixtures**: Reuse `tests/fixtures/backtest_output/` Arrow IPC sample data
- **Error pattern**: `ResultProcessingError` with stage context

### What to Reuse from ClaudeBackTester

- **Metric calculations**: ClaudeBackTester's `BacktestResult` class has win rate, profit factor, Sharpe ratio, max drawdown calculations. Port the math (not the code) — our schemas differ.
- **Equity curve analysis**: ClaudeBackTester computes equity curve statistics. Use same formulas adapted to our Arrow IPC equity curve schema.

### Anti-Patterns to Avoid

1. **NO pandas for bulk data** — Use `pyarrow` directly for Arrow IPC reads and `sqlite3` for queries. Pandas is acceptable only for small in-memory computation (< 1000 rows).
2. **NO unbounded memory** — Stream Arrow RecordBatches. Don't load entire equity curves into memory for large backtests.
3. **NO LLM/AI for narrative generation** — "AI Analysis Layer" is a naming convention. Narratives are template-driven from computed statistics, NOT generated by an LLM. **Research Update (D11):** This aligns with the deterministic-first architecture principle — all metrics computation and anomaly detection must be deterministic Python code. Narrative text is derived from deterministic metrics via templates. No stochastic components in the analysis pipeline.
4. **NO blocking on anomalies** — Anomaly flags are strictly informational. Never raise exceptions, return error codes, or set pipeline states that could prevent progression.
5. **NO schema drift** — Query exact column names from `contracts/sqlite_ddl.sql`. If schema needs changes, update contracts first.
6. **NO hardcoded paths** — Derive all artifact paths programmatically from `artifacts_root` + `strategy_id` + version.
7. **NO silent failures** — Log all analysis steps with timing. Raise `AnalysisError` (new exception) with context on failures, but catch at orchestrator level.
8. **NO redefining data contracts** — Use existing `contracts/arrow_schemas.toml` and `contracts/sqlite_ddl.sql` as-is.
9. **NO candidate compression logic** — That's `candidate_compressor.py` in Epic 5. This story handles single-backtest analysis only.
10. **NO REST API endpoints** — API exposure is Epic 4 scope. This story creates Python modules with direct function call interfaces.

### Project Structure Notes

**Files to CREATE:**
```
src/python/analysis/
├── models.py              # Data models: NarrativeResult, AnomalyFlag, AnomalyReport, EvidencePack
├── metrics_builder.py     # Shared compute_metrics() — single source for all metric calculations
├── narrative.py           # generate_narrative(backtest_id) → NarrativeResult
├── anomaly_detector.py    # detect_anomalies(backtest_id) → AnomalyReport
└── evidence_pack.py       # assemble_evidence_pack(backtest_id) → EvidencePack

src/python/tests/test_analysis/
├── __init__.py
├── test_metrics_builder.py
├── test_narrative.py
├── test_anomaly_detector.py
├── test_evidence_pack.py
└── test_analysis_integration.py
```

**Files to MODIFY:**
```
src/python/analysis/__init__.py    # Export public interfaces
src/python/orchestrator/stage_runner.py  # Add post-backtest evidence pack hook
```

**Existing files referenced (READ-ONLY):**
```
contracts/sqlite_ddl.sql           # SQLite schema SSOT
contracts/arrow_schemas.toml       # Arrow IPC schema SSOT
contracts/session_schema.toml      # Session values
src/python/artifacts/storage.py    # Crash-safe write pattern to reuse
```

### References

- [Source: _bmad-output/planning-artifacts/architecture.md — Decision 11: AI Analysis Layer]
- [Source: _bmad-output/planning-artifacts/architecture.md — Project Structure]
- [Source: _bmad-output/planning-artifacts/architecture.md — Naming Patterns]
- [Source: _bmad-output/planning-artifacts/architecture.md — Testing Strategy]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 3, Story 3.7]
- [Source: _bmad-output/planning-artifacts/prd.md — FR16, FR17, FR34, FR35, FR39, FR41, FR58]
- [Source: _bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md — Dev Notes, Anti-Patterns]
- [Source: contracts/sqlite_ddl.sql — trades, backtest_runs tables]
- [Source: contracts/arrow_schemas.toml — backtest_trades, optimization_candidates schemas]
- [Source: contracts/session_schema.toml — session column values]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Debug Log References
- All 41 unit/integration tests pass, 3 live tests pass
- Full regression suite: 1046 passed, 113 skipped, 0 failures

### Completion Notes List
- **Task 1**: Created `models.py` (AnomalyType, Severity, AnomalyFlag, AnomalyReport, NarrativeResult, EvidencePack with to_json/from_json), `metrics_builder.py` (shared compute_metrics), updated `__init__.py` exports
- **Task 2**: Created `narrative.py` with generate_narrative() — chart-first overview, session breakdown, strengths/weaknesses identification, risk assessment. Template-driven, no LLM.
- **Task 3**: Created `anomaly_detector.py` with detect_anomalies() — 9 checkers (7 implemented, 3 Epic 5 stubs). Thresholds loaded from config dict (ANOMALY_THRESHOLDS), not hardcoded in checkers. Breakeven trades use strict inequality. Anomalies are informational only.
- **Task 4**: Created `evidence_pack.py` with assemble_evidence_pack() — calls narrative+anomaly+metrics via shared builder, downsamples equity curve to max 500 points, crash-safe write pattern, versioned artifact path.
- **Task 5**: Added _generate_evidence_pack() hook in stage_runner.py after BACKTEST_COMPLETE stage. Failure logged at WARNING, does NOT block pipeline.
- **Task 6**: Created 4 test files with 41 unit tests covering all ACs.
- **Task 7**: Created 3 @pytest.mark.live integration tests exercising real file I/O.

### Change Log
- 2026-03-19: Story 3-7 implemented — AI analysis layer with narrative, anomaly detection, and evidence packs

### File List

**New files:**
- `src/python/analysis/models.py`
- `src/python/analysis/metrics_builder.py`
- `src/python/analysis/narrative.py`
- `src/python/analysis/anomaly_detector.py`
- `src/python/analysis/evidence_pack.py`
- `src/python/tests/test_analysis/__init__.py`
- `src/python/tests/test_analysis/conftest.py`
- `src/python/tests/test_analysis/test_metrics_builder.py`
- `src/python/tests/test_analysis/test_narrative.py`
- `src/python/tests/test_analysis/test_anomaly_detector.py`
- `src/python/tests/test_analysis/test_evidence_pack.py`
- `src/python/tests/test_analysis/test_analysis_integration.py`

**Modified files:**
- `src/python/analysis/__init__.py` — updated exports
- `src/python/orchestrator/stage_runner.py` — added post-backtest evidence pack hook
