# Story 1-10-epic1-pir-remediation: Story 1.10: Epic 1 PIR Remediation — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-15
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

**HIGH findings**

- The Story 1.5 → Story 1.6 CLI chain is still broken in real execution. `quality_checker` writes timestamps as strings to the validated CSV, `converter_cli` reloads that CSV without date parsing, and `ArrowConverter` then tries to cast those strings directly to `int64`, which will fail before conversion completes. The story’s supposed AC #1 integration tests mock `ArrowConverter`, so they never exercise the real failure path. Refs: [converter_cli.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/converter_cli.py#L55), [quality_checker.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/quality_checker.py#L795), [arrow_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/arrow_converter.py#L177), [test_converter_cli.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_data_pipeline/test_converter_cli.py#L94), [test_pir_remediation_live.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_data_pipeline/test_pir_remediation_live.py#L115)

- Timezone findings are surfaced in the JSON report, but they are not surfaced through the API the orchestrator actually receives. `ValidationResult` contains no timezone field, and `can_proceed` is derived only from the score rating, so a dataset with fatal timezone errors can still return `can_proceed=True` or `"operator_review"` unless callers reopen and inspect the JSON manually. That is only a partial fix for AC #2. Refs: [quality_checker.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/quality_checker.py#L32), [quality_checker.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/quality_checker.py#L868), [quality_checker.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/quality_checker.py#L955), [test_quality_checker.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_data_pipeline/test_quality_checker.py#L330)

- AC #7 is only half-implemented. `ArrowConverter` loads session enums from `arrow_schemas.toml`, but `timeframe_converter` never does; its schema validation only checks column names/types and its conversion logic still emits hardcoded session literals like `"mixed"` and `"off_hours"`. A bad session value in timeframe output would pass this story’s validation path. Refs: [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L249), [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L340), [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L474), [timeframe_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/timeframe_converter.py#L553)

- AC #11 is still only partial. `ArrowConverter` removed directory walking for `contracts_path`, but it still resolves storage from multiple config locations and treats `contracts_path` as a raw filesystem path, so a relative configured value remains CWD-dependent instead of canonical. Refs: [arrow_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/arrow_converter.py#L64), [arrow_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/arrow_converter.py#L75)

**MEDIUM findings**

- Gap detection has an off-by-one threshold. The code flags any M1 timestamp diff greater than `gap_threshold_bars` minutes, which means exactly 5 missing bars already trip the default threshold of 5 even though the spec says “more than” 5 consecutive missing bars. Refs: [quality_checker.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/quality_checker.py#L83)

- Weekend-gap classification is too permissive by about two hours on both boundaries. The implementation exempts gaps starting Friday 20:00+ and ending Sunday 21:00+, while the architecture says Friday 22:00 to Sunday 22:00 UTC. That can suppress genuine missing-data alerts around market open/close. Refs: [quality_checker.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/quality_checker.py#L123)

- Session enum caching in `ArrowConverter` is global and not keyed by `contracts_path`. In a long-lived process, switching configs/contracts can leave validation using stale allowed values from the first-loaded contract file. Refs: [arrow_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/arrow_converter.py#L41), [arrow_converter.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/data_pipeline/arrow_converter.py#L86)

**Acceptance Criteria Scorecard**

| AC | Status | Notes |
| --- | --- | --- |
| 1 | Partially Met | Path fixed, but real CLI-to-converter chain still breaks on timestamp deserialization. |
| 2 | Partially Met | `timezone_issues` added to report, but not exposed in `ValidationResult`/gating. |
| 3 | Fully Met | Split reuse now includes `config_hash`. |
| 4 | Fully Met | Shared safe-write module is used by 1-5/1-6/1-7 paths. |
| 5 | Fully Met | Integrity-error quarantines included; unique-count percentage logic is present. |
| 6 | Fully Met | Quality report `config_hash` is populated and auto-computed. |
| 7 | Partially Met | Arrow conversion is contract-driven; timeframe conversion still is not. |
| 8 | Fully Met | The named dead downloader helpers are absent. |
| 9 | Fully Met | `gap_severity` is wired into the quality report. |
| 10 | Fully Met | Dead timeout/backoff config usage was removed rather than silently ignored. |
| 11 | Partially Met | Contracts discovery cleanup is done, but path resolution is not yet canonical/CWD-independent. |

**Test Coverage Gaps**

- No real end-to-end test runs `quality_checker` output through the actual `converter_cli` and real `ArrowConverter`; both AC #1 tests mock the converter.
- No test proves timezone errors alter orchestration behavior or are exposed via `ValidationResult`.
- No listed story test verifies contract-driven session enum validation in `timeframe_converter`.
- No boundary tests cover exactly-5-missing-bars or the Friday 22:00 / Sunday 22:00 weekend cutoff behavior.
- No test covers relative `contracts_path` resolution outside the repo root.

**Summary**

7 of 11 criteria are fully met, 4 are partially met, 0 are not met.

I could not perform the workflow’s git-vs-story diff audit because this workspace is not a git repository.
