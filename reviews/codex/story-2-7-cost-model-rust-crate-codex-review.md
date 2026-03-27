# Story 2-7-cost-model-rust-crate: Story 2.7: Cost Model Rust Crate — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-16
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

Static review only: this workspace has no `.git` directory, and `cargo` execution was blocked by policy here, so this report is based on source, test, and story inspection against [2-7-cost-model-rust-crate.md](C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md).

**HIGH findings**
- Version validation is looser than the story contract. [`loader.rs`](C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/loader.rs#L57) only enforces `v` plus at least 3 digits, so `v1000` loads successfully, and [`lib.rs`](C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/lib.rs#L174) explicitly locks that in as expected behavior. Story 2.7 requires `v{NNN}` / `v\\d{3}` fail-loud validation, so AC5 is only partially met.
- AC8 requires coverage of correct session lookup for all 5 sessions, but the tests do not verify correctness of the returned profiles. [`lib.rs`](C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/lib.rs#L289) only checks that returned values are non-negative; [`integration_test.rs`](C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/tests/integration_test.rs#L61) and [`test_rust_crate.py`](C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_cost_model/test_rust_crate.py#L169) only check presence of session names. A swapped asian/london mapping would still pass, so AC8 is only partially met.

**MEDIUM findings**
- Top-level artifact schema drift is silently accepted. [`types.rs`](C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/types.rs#L49) does not use `#[serde(deny_unknown_fields)]` on `CostModelArtifact`, so new top-level fields are ignored even though the story emphasizes fail-loud contract validation. If the Python builder later adds something behaviorally relevant, Rust will quietly drop it.
- Optional `metadata` is loaded but not observable through the public API or CLI. [`types.rs`](C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/types.rs#L59) stores it, but [`cost_engine.rs`](C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/cost_engine.rs#L40) exposes no accessor, [`cost_model_cli.rs`](C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/bin/cost_model_cli.rs#L48) never prints it, and [`lib.rs`](C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/lib.rs#L147) does not verify preservation. That is a data-visibility gap.

**Acceptance Criteria Scorecard**

| AC | Status | Notes |
|---|---|---|
| 1 | Fully Met | Crate exists with public load/query API. |
| 2 | Fully Met | JSON loads into in-memory `HashMap<String, CostProfile>` and lookup is O(1). |
| 3 | Fully Met | `get_cost()` performs direct `HashMap` lookup and returns the session profile. |
| 4 | Fully Met | `apply_cost()` adjusts buys up and sells down by `mean_spread + mean_slippage`. |
| 5 | Partially Met | Validation is broad, but version contract is too permissive (`v1000` accepted). |
| 6 | Fully Met | CLI exposes `validate` and `inspect`, and prints artifact fields plus session profiles. |
| 7 | Fully Met | `backtester` depends on `cost_model` as a library. |
| 8 | Partially Met | Tests exist, but they do not prove correct session-to-profile mapping. |
| 9 | Fully Met | Non-`EURUSD` artifacts fail with a descriptive V1-only error. |
| 10 | Fully Met | `CostProfile` uses `deny_unknown_fields`, and unknown fields are rejected. |

**Test Coverage Gaps**
- No test asserts exact expected values per session for `get_cost()`.
- No test covers rejection of unexpected extra session keys.
- No test covers unknown top-level artifact fields being rejected or accepted.
- No test proves optional `metadata` survives load and is externally inspectable.
- CLI tests do not assert `inspect` output for source/version/calibrated_at beyond incidental pair/session presence.

**Summary**
2 HIGH, 2 MEDIUM.

8 of 10 criteria are fully met, 2 are partially met, 0 are not met.
