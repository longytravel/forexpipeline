# PIR: Story 3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs — Story 3.7: AI Analysis Layer — Narrative, Anomaly Detection & Evidence Packs

## Codex Assessment Summary

No Codex PIR was available for this story. Assessment is based on independent source code review against the story spec, PRD (FR16, FR17, FR39, FR41, FR58), architecture (D2, D3, D11), synthesis report, and lessons learned.

## Objective Alignment
**Rating:** STRONG

This story is the first implementation of the AI Analysis Layer (D11) and directly serves the PRD's core promise: operator confidence through evidence-based review. Every PRD requirement maps to concrete, verified code:

- **FR16 (narrative summary):** `generate_narrative()` produces a chart-first structured narrative: equity curve shape description, drawdown profile, trade distribution, then key metrics table, strengths/weaknesses, session breakdown, and risk assessment. Template-driven via `_generate_overview()`, `_identify_strengths()`, `_identify_weaknesses()`, `_assess_risk()` — no LLM or stochastic components, exactly per D11's deterministic-first mandate.

- **FR17 (anomaly detection):** All 7 architecture D11 anomaly checks implemented with correct thresholds: low trade count (<30 → WARNING), zero trade windows (2-year → ERROR), perfect equity (DD <1% with >100 trades → ERROR), extreme profit factor (>5.0 → WARNING), trade clustering (>50% in single month → WARNING), win rate extremes (>90% or <20% with >50 trades → WARNING). Three Epic 5 stubs (sensitivity_cliff, DSR, PBO) return None with debug logging — appropriate forward compatibility.

- **FR39 (evidence pack for operator review):** `EvidencePack` contains all required fields per AC#6: narrative overview, key metrics table (win_rate, profit_factor, sharpe_ratio, max_drawdown_pct, total_trades), anomaly flags, downsampled equity curve (max 500 points), trade distribution by session and month, trade log reference path, manifest_path for provenance — sufficient for accept/reject/refine without inspecting raw data.

- **FR41 (non-blocking anomalies):** Anomaly flags are strictly informational. `detect_anomalies()` returns an `AnomalyReport` with possibly-empty list. The orchestrator's `_generate_evidence_pack()` catches all exceptions at WARNING level and does not block pipeline transition.

- **FR58 (versioned artifacts):** Evidence pack persisted to `artifacts/{strategy_id}/v{NNN}/backtest/evidence_pack.json` with crash-safe write pattern (`.partial` → `fsync()` → `os.replace()`), reusing the Story 3.6 safety pattern.

- **D11 (deterministic-first):** All computation is pure Python. Metrics computed via shared `compute_metrics()` function. Narratives are template-driven from deterministic statistics. No stochastic components anywhere in the analysis pipeline.

- **D11 (two-pass design):** Epic 3 correctly assembles the full evidence pack in a single call. The data model naturally supports future `TriageSummary` extraction from the metrics + anomalies subset for Epic 5.

- **D2 (three-layer storage):** Reads from SQLite for trade queries and run metadata; reads Arrow IPC for equity curve data via `pyarrow.ipc.open_file()` with streaming record batches. No format confusion.

- **D3 (pipeline orchestration):** Evidence pack generation hooks into `stage_runner.py` as a post-`BACKTEST_COMPLETE` action. Failure is logged at WARNING, never blocks pipeline, and Story 3.8 detects availability by checking `evidence_pack.json` on disk.

The story does NOT work against any system objective. All 10 anti-patterns listed in the spec are properly avoided (no pandas for bulk data, no unbounded memory, no LLM for narrative, no blocking on anomalies, no schema drift, no hardcoded paths, no silent failures, no redefining contracts, no candidate compression, no REST endpoints).

## Simplification
**Rating:** STRONG

The implementation is cleanly decomposed into five focused modules:

| Module | Responsibility | Approx Lines |
|--------|---------------|-------------|
| `models.py` | Dataclasses + enums + JSON serialization | ~182 |
| `metrics_builder.py` | Shared metrics computation (SSOT) | ~149 |
| `narrative.py` | Template-driven chart-first narrative | ~250 |
| `anomaly_detector.py` | 9 checkers with configurable thresholds | ~300 |
| `evidence_pack.py` | Assembly, downsampling, persistence | ~350 |

No over-engineering observed:

- **Epic 5 stubs are minimal** — `_check_sensitivity_cliff()`, `_check_dsr_below_threshold()`, `_check_pbo_high_probability()` each return `None` with a debug log. Proper forward compatibility without premature implementation.
- **`ANOMALY_THRESHOLDS` dict** is the right abstraction level — configurable via parameter override now, extractable to `contracts/anomaly_thresholds.toml` later without code changes.
- **Two-pass design** is acknowledged in the docstring and data model but not prematurely implemented for Epic 3.
- **Post-synthesis metrics reuse** (`narrative.metrics` instead of recomputing) eliminates the redundant third computation correctly.

One minor structural observation: narrative and anomaly_detector each open their own SQLite connection, and evidence_pack opens a third for metadata/distribution — totaling 3 sequential connections per evidence pack assembly. For V1 volumes (~50 trades), this is negligible. A connection-passing pattern would couple the interfaces unnecessarily. Correctly deferred.

## Forward Look
**Rating:** STRONG

**Correctly set up for downstream:**

- **Story 3.8 (operator review):** Evidence pack JSON at a predictable path contains all fields for display. The `pipeline_stage: "backtest"` field and `manifest_path` reference enable Story 3.8 to present provenance. Stage runner's docstring explicitly says "Story 3.8 detects availability by checking evidence_pack.json on disk."
- **Story 3.9 (deterministic verification):** Evidence pack references `manifest_path` for provenance chain. All metrics are deterministic. `generated_at` is the only non-deterministic field, correctly isolated in metadata.
- **Epic 5 (optimization):** Forward-compatible enum values (`DSR_BELOW_THRESHOLD`, `PBO_HIGH_PROBABILITY`, `SENSITIVITY_CLIFF`) and stubs. `ANOMALY_THRESHOLDS` dict supports override. Evidence pack data model supports triage extraction.
- **Anomaly threshold evolution:** The `detect_anomalies(thresholds=)` parameter enables Epic 5 to pass optimization-specific thresholds without modifying the module.

**Output contract completeness:** The `EvidencePack.to_json()` output matches the spec's JSON structure exactly — all 12 top-level fields present (backtest_id, strategy_id, version, pipeline_stage, generated_at, narrative, anomalies, metrics, equity_curve_summary, equity_curve_full_path, trade_distribution, trade_log_path, metadata).

## Observations for Future Stories

1. **Session values hardcoded (third occurrence).** `_SESSIONS = ["asian", "london", "new_york", "london_ny_overlap", "off_hours"]` is hardcoded in both `narrative.py` and `evidence_pack.py` with a comment claiming "loaded from contracts/session_schema.toml" — but they are not actually loaded from the file. This is the same defect class flagged in Stories 1-6 and 1-9 lessons learned. Future stories should load from the TOML contract or define a single shared constant in a `contracts_loader` module.

2. **Three sequential SQLite connections per evidence pack.** `assemble_evidence_pack()` triggers 3 separate connection open/close cycles (narrative, anomaly_detector, evidence_pack). For V1 this is fine, but Epic 5's batch processing of 10K optimization candidates would benefit from connection pooling or a shared connection pattern. Consider refactoring when Epic 5 stories are scoped.

3. **Evidence pack JSON field duplication.** `pipeline_stage` and `generated_at` appear both at the top level of the JSON output and inside the `metadata` dict. Story 3.8 should document which location is canonical for downstream consumers.

4. **Sharpe ratio formula uses trade-level Sharpe** (`mean / stdev * sqrt(N)`), not the standard annualized Sharpe ratio. This is acceptable for intra-pipeline comparison but should be clearly labeled in Story 3.8's operator-facing display to avoid misinterpretation as annualized Sharpe.

5. **Synthesis process effectiveness.** The review process caught 2 HIGH (unbounded memory, wrong-version fallback), 2 MEDIUM (redundant metrics computation, inconsistent error handling), and 2 LOW (per-row Arrow access, missing exports) issues — all fixed with regression tests (6 new tests). This continues the pattern of the synthesis pipeline catching real production-quality issues before they ship.

## Verdict

**VERDICT: ALIGNED**

Story 3.7 faithfully implements the AI Analysis Layer scoped for Epic 3. It serves all relevant PRD requirements (FR16, FR17, FR39, FR41, FR58), adheres to architecture decisions (D2, D3, D11), and produces a complete operator-review artifact. The deterministic-first principle is rigorously followed — no LLM, no stochastic components, pure template-driven computation. The synthesis process caught and fixed all significant issues with regression coverage. Forward compatibility for Epic 5 is properly scoped via enum values and stubs without premature implementation. The session values hardcoding (observation #1) is a known recurring defect class that should be addressed project-wide, but does not affect V1 correctness or alignment. All 7 acceptance criteria are met with 47 unit tests and 3 live integration tests providing comprehensive coverage.
