# Epic 3 — Pipeline Proof Fixtures

## Purpose

Reference fixtures produced by `tests/e2e/test_epic3_pipeline_proof.py` (Story 3-9).
These validate the full backtesting pipeline from backtest output through operator review.

## Fixtures

- **test_config_overlay.toml** — Test-local config overlay for pipeline settings. Merged
  with `config/base.toml` at test startup; does NOT mutate global config.

## Runtime-Generated Fixtures

The following are created by the test in a temp directory and verified for correctness:

- **reference_backtest_manifest.json** — Sanitized copy of `manifest.json` with volatile
  fields (`run_id`, `created_at`) replaced by `"<volatile>"`.
- **reference_pipeline_state.json** — Sanitized final pipeline state showing REVIEWED stage.
- **reference_metrics.json** — Key metrics extracted from `metrics.arrow` for quick comparison.
- **fixture_manifest.json** — Index recording SHA-256 hashes of all sanitized fixtures.

## How Epic 4 Should Load These

1. Read `fixture_manifest.json` to discover fixture filenames and hashes.
2. Verify SHA-256 hashes before use (detect stale fixtures).
3. Compare pipeline state shape (field names, stage values) against current schema.
4. Volatile fields are `"<volatile>"` — ignore them in comparisons.

## Dependencies

| Contract | Source |
|----------|--------|
| PipelineState, GateDecision, WithinStageCheckpoint | Story 3-3 (`src/python/orchestrator/`) |
| EvidencePack, NarrativeResult, AnomalyReport | Story 3-7 (`src/python/analysis/`) |
| operator_actions API | Story 3-8 (`src/python/orchestrator/operator_actions.py`) |
| Arrow schemas | `contracts/arrow_schemas.toml` |
| SQLite schema | `contracts/sqlite_ddl.sql` |
