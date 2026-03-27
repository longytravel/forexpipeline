# Story 2-3-strategy-specification-schema-contracts: Story 2.3: Strategy Specification Schema & Contracts — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-15
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

Static review only: the workspace is not a git repo, and test execution was blocked by shell policy.

**HIGH findings**
- AC4 is not met because the validator is not fail-loud on unknown fields; Pydantic is configured with `strict=True` but never `extra="forbid"`, so non-contract fields are silently ignored instead of rejected. That is a direct contract-enforcement/data-integrity problem. See [`specification.py` L37](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L37), [`specification.py` L73](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L73), [`specification.py` L298](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L298).
- AC5 is only partially implemented because indicator contracts are loaded but their required parameters are never enforced. `required_params` exists in the shared registry, but `EntryCondition.parameters` is just an arbitrary dict and semantic validation only checks indicator names. A spec can declare `sma` without `period` and still pass. See [`indicator_registry.toml` L13](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/indicator_registry.toml#L13), [`indicator_registry.toml` L27](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/indicator_registry.toml#L27), [`specification.py` L62](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L62), [`loader.py` L63](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/loader.py#L63), [`loader.py` L86](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/loader.py#L86).
- AC6 is only partially met because versioning updates the filename but not the embedded spec version. `save_strategy_spec()` computes `v002`, `v003`, etc., then dumps the original model unchanged, so `v002.toml` can still contain `metadata.version = "v001"`. That breaks reproducibility and self-consistency of persisted artifacts. See [`storage.py` L53](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/storage.py#L53), [`storage.py` L57](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/storage.py#L57), [`test_storage.py` L79](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_strategy/test_storage.py#L79).
- AC8’s reference implementation is not actually the promised MA crossover spec. The story requires “SMA(20) crosses_above SMA(50)”, but the sample encodes two separate conditions: `sma crosses_above 0` and `sma crosses_below 0`. On top of that, the optimization plan targets `fast_period`/`slow_period`, which do not exist anywhere in the entry conditions, and the loader gathers entry param names but never validates that linkage. See [`v001.toml` L13](/c/Users/ROG/Projects/Forex%20Pipeline/artifacts/strategies/ma-crossover/v001.toml#L13), [`v001.toml` L21](/c/Users/ROG/Projects/Forex%20Pipeline/artifacts/strategies/ma-crossover/v001.toml#L21), [`v001.toml` L61](/c/Users/ROG/Projects/Forex%20Pipeline/artifacts/strategies/ma-crossover/v001.toml#L61), [`strategy_specification.toml` L24](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/strategy_specification.toml#L24), [`loader.py` L86](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/loader.py#L86).

**MEDIUM findings**
- Contract-bound numeric validation is incomplete for nested filter/trailing params. The schema contract requires bounds like volatility `period >= 1` and chandelier `atr_period >= 1`, but the implementation only checks key presence, so nonconforming values can pass validation. See [`strategy_specification.toml` L47](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/strategy_specification.toml#L47), [`strategy_specification.toml` L101](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/strategy_specification.toml#L101), [`specification.py` L95](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L95), [`specification.py` L171](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L171).
- `group_dependencies` is modeled as unchecked free-form strings, so typos or references to nonexistent groups are accepted. That weakens AC3’s “machine-verifiable optimization stages” claim. See [`specification.py` L266](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L266), [`v001.toml` L56](/c/Users/ROG/Projects/Forex%20Pipeline/artifacts/strategies/ma-crossover/v001.toml#L56).

**Acceptance Criteria Scorecard**

| AC | Status | Notes |
|---|---|---|
| 1 | Fully Met | `contracts/strategy_specification.toml` exists and covers the required top-level sections. |
| 2 | Partially Met | Core constructs exist, but the schema/sample do not cleanly represent the promised MA crossover semantics. |
| 3 | Partially Met | `parameter_groups`, `group_dependencies`, and `objective_function` exist, but dependency and parameter-target validation are weak/missing. |
| 4 | Not Met | Non-contract fields can be silently discarded instead of failing loud. |
| 5 | Partially Met | Indicator-name checks, range checks, and version-pattern checks exist, but indicator-required params and some nested contract constraints are not enforced. |
| 6 | Partially Met | Filenames version correctly and old files remain, but persisted `metadata.version` does not auto-increment with the filename. |
| 7 | Fully Met | Save path uses a crash-safe partial-write then replace flow. |
| 8 | Partially Met | A sample file exists, but it is not a faithful MA crossover reference implementation. |

**Test Coverage Gaps**
- No test covers rejection of extra/unknown fields, even though AC4 requires fail-loud behavior. Existing schema tests focus on missing required sections and a few validator errors; see [`test_specification.py` L89](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_strategy/test_specification.py#L89).
- No test checks indicator-required parameter enforcement. Registry tests only assert metadata exists, not that validation uses it; see [`test_indicator_registry.py` L43](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_strategy/test_indicator_registry.py#L43).
- No test covers invalid nested numeric bounds such as volatility `period = 0`, chandelier `atr_period = 0`, or negative `atr_multiplier`; existing trailing test only checks missing keys; see [`test_specification.py` L228](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_strategy/test_specification.py#L228).
- No test verifies that saving `v002.toml` updates `metadata.version` to `v002`; storage tests only assert filenames and returned tuple version; see [`test_storage.py` L53](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_strategy/test_storage.py#L53), [`test_live_strategy.py` L96](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_strategy/test_live_strategy.py#L96).
- No test checks that optimization parameters actually map to fields present in the strategy spec, despite the loader starting to collect those keys; see [`loader.py` L86](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/loader.py#L86).
- No test exercises `validate_or_die_strategy()` exit behavior or its “collect all errors, then exit” path.

**Summary**
2 of 8 criteria are fully met, 5 are partially met, and 1 is not met.

The main problems are contract enforcement gaps and data-integrity drift: unknown fields are silently dropped, indicator-required params are never validated, persisted versions are internally inconsistent, and the sample “MA crossover” artifact does not encode the strategy it claims to represent.
