# Review Synthesis: Story 3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs

## Reviews Analyzed
- BMAD: available
- Codex: unavailable

## Accepted Findings (fixes applied)

### H1 — Unbounded memory in equity curve downsampling (BMAD, HIGH)
**Description:** `_downsample_equity_curve` loaded ALL rows into a Python list before downsampling, violating anti-pattern #2 (no unbounded memory). For 125 MB Arrow IPC files, this would materialize millions of rows as Python dicts.
**Fix:** Rewrote to streaming two-pass approach — Pass 1 counts total rows across batches, Pass 2 extracts only the ~500 needed rows at stride indices. Columns are converted to Python lists per-batch (not per-row access). Never materializes the full dataset.
**Files:** `src/python/analysis/evidence_pack.py:237-310`
**Regression test:** `test_evidence_pack.py::TestRegressionH1StreamingDownsample`

### H2 — Silent wrong-version fallback in `_find_version_dir` (BMAD, HIGH)
**Description:** After failing manifest match, function had two unsafe fallbacks: (1) any version dir with `trade-log.arrow`, (2) latest version dir — both could silently return wrong version's artifacts.
**Fix:** Removed trade-log.arrow fallback. Only falls back to latest version if exactly one version dir exists. Raises `AnalysisError` when multiple versions exist with no manifest match.
**Files:** `src/python/analysis/evidence_pack.py:207-234`
**Regression test:** `test_evidence_pack.py::TestRegressionH2VersionFallback`

### M1 — Redundant third SQLite connection and metrics recomputation (BMAD, MEDIUM)
**Description:** `assemble_evidence_pack` opened its own SQLite connection and called `compute_metrics()` independently, despite `generate_narrative()` having already computed identical metrics via the same shared function.
**Fix:** Reuse `narrative.metrics` directly instead of recomputing. Removed unused `compute_metrics` import from `evidence_pack.py`. The evidence pack still opens one connection for run_meta (path resolution) and trades (distribution), but no longer duplicates the metrics computation.
**Files:** `src/python/analysis/evidence_pack.py:66-86`
**Regression test:** `test_evidence_pack.py::TestRegressionM1MetricsReuse`

### M2 — Inconsistent error handling for missing backtest run (BMAD, MEDIUM)
**Description:** `anomaly_detector._load_run_metadata` returned empty dict `{}` on missing run, while `narrative._load_run_metadata` raised `AnalysisError`. A typo in `backtest_id` would raise in narrative but silently produce an empty anomaly report.
**Fix:** Changed to raise `AnalysisError("anomaly_detector", ...)` consistent with narrative module. The orchestrator's try/except will catch this at the appropriate level.
**Files:** `src/python/analysis/anomaly_detector.py:124-128`
**Regression test:** `test_evidence_pack.py::TestRegressionM2ConsistentErrorHandling`

### L1 — Per-row Arrow column access (BMAD, LOW)
**Description:** `batch.column("timestamp")[row_idx].as_py()` per-row access is O(n) scalar creation.
**Fix:** Addressed as part of H1 — columns are now converted to Python lists once per batch via `.to_pylist()`, then indexed.
**Files:** Same as H1.

### L2 — Missing entry-point exports in `__init__.py` (BMAD, LOW)
**Description:** Module docstring listed `generate_narrative`, `detect_anomalies`, `assemble_evidence_pack` as public interfaces but `__all__` only exported data models and `compute_metrics`.
**Fix:** Added all three entry-point functions to imports and `__all__`.
**Files:** `src/python/analysis/__init__.py`

## Rejected Findings (disagreed)

### M3 — Test only checks import identity, not behavioral (BMAD, MEDIUM)
**Reason:** The test correctly verifies the contract — that both modules reference the same `compute_metrics` function object. This is the right level of abstraction. The M1 fix (reusing `narrative.metrics`) makes behavioral divergence impossible anyway. Integration tests in `test_analysis_integration.py` already verify metrics values match across modules.

## Action Items (deferred)
None — all accepted findings were fixed.

## Test Results
```
47 passed, 3 skipped in 0.75s
```
All 47 unit tests pass. 3 live integration tests skipped (require real artifact tree). 6 new regression tests added and passing.

## Verdict
All 7 acceptance criteria fully met per BMAD scorecard. Both HIGH issues fixed (streaming downsampling, safe version fallback). Both MEDIUM issues fixed (metrics reuse, consistent error handling). Both LOW issues fixed (per-row access, exports). No regressions introduced.

APPROVED
