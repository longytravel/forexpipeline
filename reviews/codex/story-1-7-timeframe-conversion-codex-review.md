# Story 1-7-timeframe-conversion: Story 1.7: Timeframe Conversion — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-14
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

**HIGH Findings**
- AC4 is only partially implemented. H1 session handling never recomputes from `config/base.toml`; it just counts the incoming `session` labels, and the required tie-break rule ("session that starts during that hour") is not implemented. `compute_session_for_timestamp()` exists but is never wired into conversion, so config-driven session logic is effectively dead code. See [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L225), [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L251), [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L278), [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L599).
- AC6 is only partially implemented because schema validation is weaker than the contract. Both aggregation paths build tables with `pa.table(...)` instead of the non-nullable contract schema, and `validate_output_schema()` checks only column order and types, not field nullability or allowed values. That means contract mismatches can pass validation and still be written to Arrow/Parquet. See [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L210), [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L425), [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L507), [arrow_schemas.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/arrow_schemas.toml#L11).

**MEDIUM Findings**
- `target_timeframes` is not actually enum-validated at startup. The schema defines it as a generic array, while only `source_timeframe` gets an allowed list. That falls short of Task 1's "only M1, M5, H1, D1, W are valid" requirement. See [schema.toml](/c/Users/ROG/Projects/Forex%20Pipeline/config/schema.toml#L199), [schema.toml](/c/Users/ROG/Projects/Forex%20Pipeline/config/schema.toml#L204).
- `run_timeframe_conversion()` only skips when both output files already exist. If one exists and the other does not, it rewrites the existing complete artifact via the normal write path, which conflicts with the story's idempotent/no-overwrite behavior. See [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L693), [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L704), [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L451).
- Empty-input handling is missing in orchestration. `run_timeframe_conversion()` always calls `_extract_date_range()`, and `_extract_date_range()` assumes `pc.min/max()` return real timestamps. An empty but readable source file would fail with an unstructured exception instead of a boundary error. See [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L560), [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L656).

**Acceptance Criteria Scorecard**
| AC | Status | Assessment |
| --- | --- | --- |
| 1 | Fully Met | OHLC aggregation, pre-sort, quarantine filtering, and timeframe grouping are implemented in `convert_timeframe()` / `_aggregate_by_period()`. |
| 2 | Fully Met | `bid` and `ask` use the last bar in the period. |
| 3 | Fully Met | Tick input is detected and routed through `aggregate_ticks_to_m1()` before higher-timeframe conversion. |
| 4 | Partially Met | M5 and D1/W behavior is implemented, but H1 is not recomputed from config schedule and the tie-break rule is wrong. |
| 5 | Fully Met | Quarantined bars are filtered before aggregation; fully quarantined periods are omitted. |
| 6 | Partially Met | Dual output exists, but contract enforcement is incomplete, so schema compliance is not guaranteed. |
| 7 | Fully Met | Conversion sorts by timestamp and builds deterministic outputs for normal bar input. |

**Test Coverage Gaps**
- No end-to-end test for tick input through `run_timeframe_conversion()`. The suite tests tick aggregation in isolation and orchestration from M1 only. See [test_timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_data_pipeline/test_timeframe_converter.py#L468), [test_timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_data_pipeline/test_timeframe_converter.py#L697).
- No test for H1 session recomputation from config or the required tie-break rule. The current H1 test only checks majority on pre-labeled source rows, which would not catch the AC4 bug. See [test_timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_data_pipeline/test_timeframe_converter.py#L333), [test_timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_data_pipeline/test_timeframe_converter.py#L361), [test_timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_data_pipeline/test_timeframe_converter.py#L401).
- Crash-safe write tests do not verify that `.partial` exists during the write, only that it is gone afterwards. See [test_timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_data_pipeline/test_timeframe_converter.py#L562).
- No test asserts exact schema-contract fidelity for nullability / allowed session values. Current validation tests only cover column mismatch. See [test_timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_data_pipeline/test_timeframe_converter.py#L614).
- No weekly-boundary crossing test around Sunday 22:00 UTC; current weekly tests start exactly on the boundary, which would miss off-by-one alignment bugs. See [test_timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_data_pipeline/test_timeframe_converter.py#L247).
- No test for partial-existing outputs to verify the no-overwrite/idempotent behavior.

**Summary**
5 of 7 criteria are fully met, 2 are partially met, 0 are not met.

No git repository was present in the workspace, so I could not perform the workflow’s git-vs-story discrepancy audit.
