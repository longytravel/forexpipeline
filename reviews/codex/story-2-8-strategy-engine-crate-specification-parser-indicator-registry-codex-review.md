# Story 2-8-strategy-engine-crate-specification-parser-indicator-registry: Story 2.8: Strategy Engine Crate — Specification Parser & Indicator Registry — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-17
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

**HIGH findings**
- AC7’s required public API is not what the crate exports. The story requires `validate_spec(spec: &StrategySpec) -> Result<ValidatedSpec, Vec<ValidationError>>`, but the actual API requires a caller-supplied registry and optional path, which changes the contract and lets callers skip required validation. Refs: [story:44](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L44), [validator.rs:45](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L45), [lib.rs:18](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/lib.rs#L18)
- AC6 is only conditionally enforced. `cost_model_reference` is cross-validated only when `cost_model_path` is `Some(...)`; the main integration path and the so-called “valid” unit test both pass `None`, so a spec can validate without ever proving the referenced artifact loads. Refs: [validator.rs:58](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L58), [validator.rs:480](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L480), [integration_test.rs:29](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/tests/integration_test.rs#L29), [validator.rs:694](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L694)
- AC4 is only partially implemented for exit rules. `validate_exit_rules()` never consults the indicator registry for ATR-based exits; `atr_multiple` stop-loss / take-profit and chandelier trailing are treated as raw numbers, so exit-rule indicators are not validated “in `entry_rules` and `exit_rules`” as required. Refs: [story:30](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L30), [validator.rs:173](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L173), [validator.rs:191](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L191), [validator.rs:225](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L225)
- AC4’s “comparator valid for indicator type” requirement is not implemented. `validate_condition()` only checks membership in a global allowlist, so nonsensical indicator/comparator combinations still pass. Refs: [story:30](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L30), [validator.rs:159](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L159), [types.rs:193](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/types.rs#L193)
- Contract-required metadata/version constraints are missing, so schema-invalid specs can still validate. The contract requires `metadata.version` and `cost_model_reference.version` to match `v\\d{3}` and `pair` to be `EURUSD`, but validation only checks non-empty `pair` and non-empty cost-model version. Refs: [strategy_specification.toml:11](/C:/Users/ROG/Projects/Forex Pipeline/contracts/strategy_specification.toml#L11), [strategy_specification.toml:12](/C:/Users/ROG/Projects/Forex Pipeline/contracts/strategy_specification.toml#L12), [strategy_specification.toml:145](/C:/Users/ROG/Projects/Forex Pipeline/contracts/strategy_specification.toml#L145), [validator.rs:67](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L67), [validator.rs:470](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L470)

**MEDIUM findings**
- `optimization_plan.parameter_groups[*].parameters` is deserialized but effectively ignored. Validation checks only `ranges`, so missing-range / extra-range mismatches can pass silently. Refs: [types.rs:159](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/types.rs#L159), [validator.rs:403](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L403)
- Volatility-filter validation is incomplete. It checks indicator existence and `period > 0`, but it does not reject `min_value > max_value` or a no-op filter with neither bound set. Refs: [types.rs:78](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/types.rs#L78), [validator.rs:298](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L298)
- The story marks Rust/Python parity tests complete, but there is no `tests/parity_test.rs`, and the Python live suite does not compare validation results across runtimes. Refs: [story:145](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L145), [story:315](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L315), [integration_test.rs:1](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/tests/integration_test.rs#L1), [test_live_strategy_engine.py:125](/C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_strategy/test_live_strategy_engine.py#L125)
- `test_validate_cost_model_reference_valid` is a false-positive test name: it never exercises a successful artifact load because it passes `None`. Refs: [validator.rs:694](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L694)

**Acceptance Criteria Scorecard**

| AC | Status | Notes |
|---|---|---|
| 1 | Fully Met | Crate exists and exposes parser/validator API. |
| 2 | Fully Met | All required top-level sections are deserialized. |
| 3 | Fully Met | Registry exists and exposes the 4 V1 indicators with signatures. |
| 4 | Partially Met | Entry-rule indicator checks exist; exit-rule indicator validation and indicator-specific comparator validation are missing. |
| 5 | Partially Met | Session/day-of-week checks exist; volatility-filter config validation is incomplete. |
| 6 | Partially Met | Cross-validation works only when optional path input is supplied. |
| 7 | Partially Met | Collect-all structured errors exist, but the exported function signature does not match the AC. |
| 8 | Fully Met | Workspace and crate dependencies match the required graph. |

**Test Coverage Gaps**
- No automated Rust/Python parity test for valid and invalid fixtures.
- No positive end-to-end test that loads a real cost model artifact through strategy validation.
- No regression tests for contract-only constraints: `schema_version`, `metadata.version` pattern, `pair == EURUSD`, `cost_model_reference.version` pattern.
- No tests for ATR-based exit-rule validation or indicator/comparator compatibility.
- No tests for `parameter_groups.parameters` vs `ranges` consistency.
- No tests for volatility-filter `min_value` / `max_value` edge cases.

**Summary**
4 of 8 criteria are fully met, 4 are partially met, 0 are not met.

Static review only. I could not run `cargo test` in this session because command execution was blocked by the sandbox policy.
