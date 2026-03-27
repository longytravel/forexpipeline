# Story 5-2b-optimization-search-space-schema-range-proposal: Story 5.2b: Optimization Search Space Schema & Intelligent Range Proposal — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-22
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

**HIGH Findings**
- `validate_strategy_spec()` skips semantic existence checks for every categorical optimization parameter, so invalid keys like `session_filter`, `exit_type`, or any future type-selector can pass unchecked. That undercuts AC7 just as the story expands the search space around categorical/type params. See [loader.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/loader.py#L141), [loader.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/loader.py#L143), [loader.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/loader.py#L147).

- `propose_ranges()` does not build the required conditional/type search space. It extracts numeric indicator params, exit-value params, and one `session_filter`, but never proposes stop-loss type, take-profit type, trailing type/method, or any child params with `condition`. That leaves AC4 and AC8 only partially implemented despite the schema supporting nesting. See [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L272), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L286), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L353), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L417), [v002.toml](/c/Users/ROG/Projects/Forex Pipeline/artifacts/strategies/ma-crossover/v002.toml#L31), [v002.toml](/c/Users/ROG/Projects/Forex Pipeline/artifacts/strategies/ma-crossover/v002.toml#L35), [v002.toml](/c/Users/ROG/Projects/Forex Pipeline/artifacts/strategies/ma-crossover/v002.toml#L39).

- The checked-in reference artifact is not consistent with the engine it claims to come from. `_propose_indicator_param()` clamps H1 period maxima to the timeframe max of `100`, so it cannot produce `slow_period.max = 200` found in v002. The same artifact also omits the required type-selector params. That makes AC8 only partial at best. See [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L323), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L325), [v002.toml](/c/Users/ROG/Projects/Forex Pipeline/artifacts/strategies/ma-crossover/v002.toml#L62), [v002.toml](/c/Users/ROG/Projects/Forex Pipeline/artifacts/strategies/ma-crossover/v002.toml#L63).

- Default-ATR provenance is silently lost in normal proposal output, and the required persisted artifact is not actually produced alongside the strategy. `compute_pair_atr_stats()` warns and falls back, but `propose_ranges()` returns bare `SearchParameter`s with no per-parameter source/default marker; `persist_proposal()` exists but is only exercised by tests, and `artifacts/strategies/ma-crossover/optimization_proposal.json` is absent. This misses AC5’s “not silently accepted” requirement and AC11’s persistence requirement. See [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L129), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L141), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L246), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L491), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L543).

- The range proposal engine silently overwrites computed ranges when different indicators share the same raw parameter name. Proposals are keyed only by `param_name`, so a second `period`, `atr_period`, etc. replaces the first. That is a direct data-integrity bug against the story’s component-prefixed naming convention for complex strategies. See [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L274), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L286), [loader.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/loader.py#L129), [loader.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/loader.py#L135).

**MEDIUM Findings**
- Provenance labeling in the persisted artifact is inaccurate. `_determine_source_layer()` marks any `sl_`, `tp_`, or `trailing_` parameter as `L3`, but `_propose_exit_params()` gives `sl_atr_multiplier` and `tp_rr_ratio` hardcoded constant ranges, not ATR-scaled ones. The artifact therefore overstates how data-driven those ranges are. See [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L363), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L378), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L534), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L561).

- Constraint application drops metadata. `_apply_physical_constraints()` and `apply_cross_parameter_constraints()` rebuild `SearchParameter` objects without preserving `condition`, so any future conditional numeric parameter would lose its activation rule after constraint adjustment. See [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L430), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L443), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L470), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L482).

- `daily_range_median` is documented as a daily high-low statistic, but the implementation computes median per-bar range. That makes the ATR stats contract misleading and weakens reproducibility claims in AC11. See [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L89), [range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/strategy/range_proposal.py#L239).

- The Story 5-3 contract doc and the current optimization consumer are out of sync. The contract defines `shared_params` plus branch maps, while the existing parser still returns a flat list and explicitly branches only on the first categorical. That is an integration risk even though AC10’s documentation exists. See [optimization_space.md](/c/Users/ROG/Projects/Forex Pipeline/contracts/optimization_space.md#L9), [optimization_space.md](/c/Users/ROG/Projects/Forex Pipeline/contracts/optimization_space.md#L28), [parameter_space.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/optimization/parameter_space.py#L48), [parameter_space.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/optimization/parameter_space.py#L80), [parameter_space.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/optimization/parameter_space.py#L154).

**Acceptance Criteria Scorecard**

| AC | Status | Notes |
|---|---|---|
| 1 | Fully Met | Flat `parameters` registry, schema contract, Pydantic model, and v002 all use schema v2. |
| 2 | Fully Met | `SearchParameter.condition` and `OptimizationPlan` DAG validation support arbitrary nesting. |
| 3 | Fully Met | `specification.py` validates type, bounds, parent existence/type, valid choice, and cycles. |
| 4 | Partially Met | Range engine exists, but it does not generate type-selector/conditional branches and only partially uses the five layers. |
| 5 | Partially Met | ATR fallback/warning exists, but affected params are not marked in normal proposal output and no real artifact is emitted beside the strategy. |
| 6 | Partially Met | Direct TOML review/override is possible; pipeline skill support is missing. |
| 7 | Partially Met | Condition parent/choice checks exist and slow/fast warning exists, but categorical param validation and pair-appropriate pip-range validation are incomplete. |
| 8 | Partially Met | `v002.toml` exists in the new format, but it omits required type params and is not fully consistent with the proposal engine. |
| 9 | Not Met | No implementation evidence for `/pipeline` commands; repo search only finds the command names in story docs. |
| 10 | Fully Met | `contracts/optimization_space.md` documents the required parse contract and boundaries. |
| 11 | Not Met | `persist_proposal()` exists, but no persisted proposal artifact is present alongside the reference strategy and operator overrides are not tracked. |
| 12 | Fully Met | `schema_version = 2` is enforced and legacy `parameter_groups` raises `SchemaVersionError`. |

**Test Coverage Gaps**
- [test_regression.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_strategy/test_regression.py#L118) only checks an unknown numeric optimization param. There is no equivalent test proving unknown categorical params are rejected, which is why the categorical skip in `loader.py` went unnoticed.
- [test_range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_strategy/test_range_proposal.py#L136) only asserts value params like `sl_atr_multiplier`, `tp_rr_ratio`, and trailing ATR fields. There is no test for proposed type-selector params or nested `condition` chains.
- [test_range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_strategy/test_range_proposal.py#L38) never compares generated proposals against [v002.toml](/c/Users/ROG/Projects/Forex Pipeline/artifacts/strategies/ma-crossover/v002.toml#L60), so the `slow_period.max = 200` drift escaped.
- [test_range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_strategy/test_range_proposal.py#L66) only compares default ATR constants, not actual pip-range outputs; [test_range_proposal.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_strategy/test_range_proposal.py#L180) only checks `ATRStats.source`, not per-parameter default provenance in the proposal/artifact.
- There is no test for duplicate raw param names across multiple indicators, and no test that constraint application preserves `condition` metadata after rewriting `SearchParameter`s.

**Summary**
5 of 12 criteria are fully met, 5 are partially met, and 2 are not met.

The strongest gaps are around AC4/5/8/9/11: the schema work is solid, but the proposal engine and reference artifact do not yet deliver the conditional/type-rich search space, provenance, or pipeline integration the story promises. Execution note: I could not run `pytest` here because command execution was blocked by policy, so this review is static.
