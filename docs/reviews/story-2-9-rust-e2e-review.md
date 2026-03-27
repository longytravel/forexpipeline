# Story 2-9 Rust E2E Integration Tests -- Adversarial Code Review

**Reviewer:** Claude Opus 4.6 (adversarial)
**Date:** 2026-03-17
**Scope:** E2E integration tests only (cost_model + strategy_engine), cross-referenced against lib code

---

## CRITICAL

None found.

---

## HIGH

### H1. `CostModelArtifact.sessions` uses `HashMap`, not `BTreeMap`
- **File:** `src/rust/crates/cost_model/src/types.rs:57`
- **What:** `sessions: HashMap<String, CostProfile>` -- the artifact struct uses `HashMap` for session storage while the strategy_engine correctly uses `BTreeMap` everywhere (types, registry, optimization ranges). This is an architectural inconsistency.
- **Impact:** Non-deterministic iteration order when serializing or logging sessions. The E2E test at `e2e_integration.rs:39-47` calls `model.sessions()` which returns `&HashMap` -- iteration order in any future diff/snapshot test would be flaky.
- **AC:** Architecture compliance (BTreeMap convention).

### H2. `validate_spec()` returns `Ok(ValidatedSpec)` when there are warnings-only errors, but warnings are silently dropped
- **File:** `src/rust/crates/strategy_engine/src/validator.rs:60-64`
- **What:** When `errors` contains only `Severity::Warning` items, the function returns `Ok(ValidatedSpec(...))` and the warnings are discarded. The E2E test at `strategy_engine/tests/e2e_integration.rs:95-118` handles both `Ok` and `Err` branches but never inspects warnings from the `Ok` path.
- **Impact:** If the real artifact produces warnings (e.g., future deprecation notices), they are silently swallowed. The `ValidatedSpec` newtype has no way to carry warnings.
- **AC:** Proper validation semantics -- `ValidatedSpec` should carry warnings.

### H3. Cost model path format mismatch is documented but not tested
- **File:** `strategy_engine/tests/e2e_integration.rs:164-168`
- **What:** The comment documents that the validator constructs `EURUSD_v001.json` but the real layout is `EURUSD/v001.json`. However, the test passes `None` for the cost model path to skip this validation entirely. There is no test that actually exercises `validate_spec()` with a real `cost_model_path` to prove the mismatch exists (or has been fixed).
- **Impact:** The path format bug in `validator.rs:564` (`format!("EURUSD_{}.json", ...)`) is untested in E2E. If someone "fixes" the validator path construction, no E2E test would catch the change.
- **AC:** AC #8 says "cross-validate spec's cost_model_reference matches cost model version" -- done manually, but the validator's built-in cross-validation path is never exercised with real artifacts.

---

## MEDIUM

### M1. E2E test `project_root()` uses fragile ancestor count
- **File:** `cost_model/tests/e2e_integration.rs:13-16` and `strategy_engine/tests/e2e_integration.rs:22-27`
- **What:** `PathBuf::from(env!("CARGO_MANIFEST_DIR")).ancestors().nth(4)` assumes exactly 4 levels of nesting (`src/rust/crates/cost_model/`). If the crate is moved or a workspace restructure occurs, the test silently points to the wrong directory.
- **Impact:** Brittle path resolution. A better pattern would be to search upward for a sentinel file (e.g., `Cargo.toml` with `[workspace]`, or `artifacts/` directory).

### M2. Strategy engine E2E filters `group_dependencies` errors inconsistently
- **File:** `strategy_engine/tests/e2e_integration.rs:105-111` vs `172-178`
- **What:** `test_e2e_validate_spec_all_indicators_registered` filters on `e.field == "group_dependencies" || e.reason.contains("->")` while `test_e2e_cost_model_reference_valid` only filters on `e.reason.contains("->")`. The filter logic is duplicated and divergent -- if the validator changes the error message format, one test might start failing while the other doesn't.
- **Impact:** Fragile gap-filtering. Should be a shared helper function with a single source of truth for known-gap patterns.

### M3. `test_e2e_validate_spec_all_indicators_registered` indicator check is vacuously true for composites
- **File:** `strategy_engine/tests/e2e_integration.rs:121-132`
- **What:** The loop checks `known || known_composite` where `known_composite` is true if `cond.indicator.contains("crossover")`. This means ANY indicator containing "crossover" in its name (e.g., a hypothetical "macd_crossover") would pass without being in the registry. The check does not validate that the *base components* (sma, ema) are actually in the registry -- it just short-circuits.
- **Impact:** The assertion provides false confidence. It cannot distinguish "known composite whose base types are registered" from "totally unknown indicator that happens to contain 'crossover' in its name."

### M4. No negative-path E2E test for cost model artifact corruption
- **What:** All three cost model E2E tests assume the artifact file is valid. There is no E2E test that verifies graceful error handling when the real artifact is malformed (e.g., truncated JSON, missing fields). The unit tests cover this, but AC #7 implies the E2E proof should demonstrate end-to-end robustness.
- **Impact:** Low-risk since unit tests cover it, but the E2E story is incomplete for the "load artifact" acceptance criterion.

### M5. `test_e2e_session_cost_lookup` hardcodes expected values that could drift from artifact
- **File:** `cost_model/tests/e2e_integration.rs:86-95`
- **What:** London spread is hardcoded as `~0.8` and slippage as `~0.05`. If the artifact is recalibrated (e.g., v002), these assertions fail. The tolerance of `0.01` is tight enough to catch drift but the test gives no indication of which artifact version it expects.
- **Impact:** Maintenance burden. Consider asserting the version first and documenting that these values correspond to v001.

---

## LOW

### L1. E2E tests use `unwrap()` / `expect()` extensively (acceptable in tests)
- **Files:** Both E2E test files throughout.
- **What:** Heavy use of `.unwrap()`, `.expect()`, and `unwrap_or_else(|e| panic!(...))`. This is standard Rust test practice and not a defect, but noted for completeness.
- **Note:** The library code (`cost_engine.rs`, `loader.rs`, `parser.rs`, `validator.rs`) correctly uses `Result` throughout with zero unwrap calls. One `.unwrap()` exists in `registry.rs:121` inside `validate_params` (`def.params.iter().find(...).unwrap()`) but it is guarded by a prior `known_param_names.contains()` check, so it cannot panic.

### L2. `test_e2e_apply_cost_buy_sell` discards return values with `let _ = `
- **File:** `cost_model/tests/e2e_integration.rs:147-153`
- **What:** The "all 5 sessions" loop uses `let _ = model.apply_cost(...)` which discards the adjusted price. It only verifies no panic/error occurs but doesn't assert anything about the returned value (e.g., buy > fill, sell < fill).
- **Impact:** Weaker assertion than the london-specific test above. Should at minimum assert directional correctness for all sessions.

### L3. `Severity` derives `PartialEq, Eq` but `ValidationError` does not
- **File:** `src/rust/crates/strategy_engine/src/validator.rs:9-23`
- **What:** The E2E test compares `e.severity == Severity::Error` which works because `Severity` derives `PartialEq`. But `ValidationError` itself has no `PartialEq`, so tests cannot directly compare full error structs -- they must match on individual fields with string contains.
- **Impact:** Minor ergonomic issue making test assertions more verbose than necessary.

### L4. `CostModelArtifact` has `deny_unknown_fields` but allows arbitrary `metadata: Option<serde_json::Value>`
- **File:** `src/rust/crates/cost_model/src/types.rs:49-61`
- **What:** The `metadata` field accepts any JSON value, which means unknown data can enter through this field even though `deny_unknown_fields` blocks unknown top-level keys. This is documented as intentional ("opaque metadata from the Python builder") but the E2E tests don't verify that malicious/unexpected metadata shapes are handled safely.
- **Impact:** Minimal -- metadata is stored but not interpreted by Rust code.

---

## Summary

| Severity | Count | Key Theme |
|----------|-------|-----------|
| CRITICAL | 0     | --        |
| HIGH     | 3     | HashMap vs BTreeMap, warning swallowing, untested path mismatch |
| MEDIUM   | 5     | Fragile path resolution, inconsistent gap filters, vacuous composite check |
| LOW      | 4     | Test ergonomics, minor assertion gaps |

**Overall assessment:** The E2E tests are substantive and exercise real artifacts against real code paths. Assertions are genuine (not placeholders). The three HIGH findings are the most actionable: H1 is a data structure choice that violates the project's own BTreeMap convention, H2 is a design gap in the validation return type, and H3 represents untested code in the validator's cross-crate path.
