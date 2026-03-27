# Story 2-6-execution-cost-model-session-aware-artifact: Story 2.6: Execution Cost Model — Session-Aware Artifact — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-16
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

**HIGH Findings**
- Schema validation does not enforce the declared `calibrated_at` ISO-8601 UTC format, so malformed artifacts can still pass “schema validation” and be saved. The contract declares `format = "iso8601_utc"` in [cost_model_schema.toml:23](C:/Users/ROG/Projects/Forex%20Pipeline/contracts/cost_model_schema.toml#L23), but [validate_cost_model()](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/schema.py#L91) never checks that field before [save_cost_model()](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/storage.py#L74). This is an AC5 compliance gap.
- The default artifact flow does not populate reproducibility hashes. `cmd_create_default()` and `cmd_create()` pass `config_hash=None` and `input_hash=None` to [save_manifest()](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/__main__.py#L54), and the generated manifest confirms both are `null` in [manifest.json:10](C:/Users/ROG/Projects/Forex%20Pipeline/artifacts/cost_models/EURUSD/manifest.json#L10). AC10 requires those fields for reproducibility verification, so the default baseline is not actually reproducible.
- The code still exposes and uses raw “latest version” loading instead of the manifest’s approved pointer. [load_latest_cost_model()](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/storage.py#L143) returns the highest numbered file, and both CLI `show` and `validate` use it when `--version` is omitted in [__main__.py:104](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/__main__.py#L104) and [__main__.py:144](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/__main__.py#L144). That violates AC9’s “use `latest_approved_version`, not raw latest file” requirement.
- Tick-analysis hardcodes `spread * 10000` for pip conversion in [builder.py:170](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/builder.py#L170). That is only correct for 0.0001-pip pairs; JPY pairs would be off by 100x. AC3 says the builder supports historical tick-data analysis for a currency pair, but this implementation is only correct for a subset of pairs.

**MEDIUM Findings**
- Session logic is hardcoded instead of being derived from config. `_LABEL_BOUNDARIES` is fixed in [sessions.py:17](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/sessions.py#L17), `validate_session_coverage()` ignores the actual provided boundaries in [sessions.py:67](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/sessions.py#L67), and `get_session_for_time()` ignores `session_defs` in [sessions.py:96](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/sessions.py#L96). That contradicts the story’s “config is authoritative” rule and makes config changes silently ineffective.
- The schema contract allows optional per-session fields such as `description`, `data_points`, and `confidence_level` in [cost_model_schema.toml:63](C:/Users/ROG/Projects/Forex%20Pipeline/contracts/cost_model_schema.toml#L63), but `CostModelArtifact.from_dict()` blindly passes each session dict into `SessionProfile(**profile_data)` in [schema.py:68](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/schema.py#L68). Any artifact that legally includes those optional session fields will fail to load.
- Storage-level schema enforcement is optional, not mandatory. [save_cost_model()](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/storage.py#L46) only validates when `schema_path` is passed, so callers can persist invalid artifacts by omission. That is weaker than AC5’s “validated against it before saving.”
- Tick-analysis falls back to `_EURUSD_DEFAULTS` for any session with no data in [builder.py:189](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/builder.py#L189). For non-EURUSD pairs, that silently injects EURUSD spreads/slippage into another pair’s artifact.

**Acceptance Criteria Scorecard**

| AC | Status | Assessment |
|---|---|---|
| 1 | Fully Met | Artifacts include `pair`, `version`, `source`, `calibrated_at`, and the 5 per-session profiles. |
| 2 | Fully Met | Each session profile carries `mean_spread_pips`, `std_spread`, `mean_slippage_pips`, and `std_slippage`. |
| 3 | Partially Met | All 3 builder modes exist, but tick-analysis is not pair-correct because pip conversion is hardcoded to `0.0001`. |
| 4 | Fully Met | Versioned storage increments versions and rejects collisions, preserving prior files. |
| 5 | Partially Met | The schema file exists, but validation is incomplete and only conditionally enforced before save. |
| 6 | Fully Met | A default EURUSD artifact is produced from research defaults and present on disk. |
| 7 | Fully Met | Storage writes use `crash_safe_write()` with the expected crash-safe pattern. |
| 8 | Fully Met | Builder/storage emit structured log events for build, validation, save, and load boundaries. |
| 9 | Partially Met | Manifest includes `latest_approved_version`, but load helpers and CLI still use raw latest-version semantics. |
| 10 | Partially Met | Manifest entries include the required keys, but the default flow leaves `config_hash` and `input_hash` null, so reproducibility verification is incomplete. |

**Test Coverage Gaps**
- No test checks that invalid `calibrated_at` values are rejected. The invalid-schema test in [test_schema.py:139](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_cost_model/test_schema.py#L139) only asserts a minimum error count from other fields.
- No test covers non-EURUSD tick-analysis behavior. The only tick-analysis test uses EURUSD in [test_builder.py:55](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_cost_model/test_builder.py#L55), so the pip-scaling bug is invisible.
- No test verifies consumers resolve via `latest_approved_version` rather than highest file version. Current storage tests explicitly exercise [load_latest_cost_model()](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_cost_model/test_storage.py#L89), which bakes in the wrong semantic for AC9.
- No test verifies `validate_session_coverage()` catches incorrect boundaries or hour gaps from the provided config-derived definitions. The current gap test in [test_sessions.py:58](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_cost_model/test_sessions.py#L58) only checks missing session names.
- No test verifies the CLI/default baseline writes non-null `config_hash` and `input_hash`. The only hash test manually injects them in [test_storage.py:208](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_cost_model/test_storage.py#L208), while CLI tests in [test_e2e.py:98](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_cost_model/test_e2e.py#L98) and [test_live.py:156](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_cost_model/test_live.py#L156) never inspect those fields.

**Summary**
4 HIGH findings, 4 MEDIUM findings.

6 of 10 criteria are fully met, 4 are partially met, 0 are not met.

I could not do the git-vs-story diff audit because this workspace is not exposed as a git repository in the current environment.
