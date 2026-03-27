# Story 5.2b: Optimization Search Space Schema & Intelligent Range Proposal

Status: ready-for-dev

## Story

As the **operator**,
I want the strategy specification's optimization_plan to use a flat parameter registry with D10 taxonomy support (continuous, integer, categorical, conditional) instead of staged parameter groups, and I want the system to intelligently propose sensible parameter ranges based on the indicator registry, pair volatility, timeframe scaling, and actual market data statistics,
So that complex Expert Advisors with 20+ exit types, 40+ parameters, and deeply nested conditional branches can define their optimization search space correctly — and I don't have to hand-tune every range for every new strategy.

## Acceptance Criteria

1. **Given** the strategy specification schema defines an optimization_plan section
   **When** the schema is evaluated against FR24 (no mandated staging or grouping)
   **Then** the `parameter_groups` and `group_dependencies` fields are replaced with a flat `parameters` registry where each parameter declares: type (continuous/integer/categorical), bounds (min/max for numeric, choices for categorical), optional step (for integer rounding/display), and optional condition (parent parameter + value for conditional activation)
   [Source: FR24, D10]

2. **Given** the schema supports deeply nested conditional parameters
   **When** a categorical parameter's choice contains child parameters that are also categorical
   **Then** those children can themselves have conditional children — enabling structures like `exit_type → trailing_method → chandelier → atr_period/atr_multiplier` without depth limits
   [Source: FR24, D10 parameter taxonomy]

3. **Given** the Pydantic v2 validators in specification.py are updated
   **When** an optimization_plan is validated
   **Then** the validators check: parameter type correctness (continuous/integer/categorical), bounds validity (min < max for numeric, non-empty choices for categorical), condition references point to valid categorical parents with valid choice values, no orphaned conditions (parent must exist), no circular dependencies in the condition DAG
   [Source: FR12, D10]

4. **Given** a strategy is being created via intent capture (Story 2-4 flow)
   **When** the system knows the indicator types, pair, and timeframe
   **Then** a range proposal engine proposes optimization bounds for every searchable parameter using five intelligence layers: (L1) indicator registry metadata — parameter types and typical ranges from `contracts/indicator_registry.toml`, (L2) timeframe scaling heuristics — period ranges bounded by `TIMEFRAME_PERIOD_RANGES` lookup (e.g., M1: 5-300, D1: 5-50), (L3) pair volatility from actual market data — ATR(14) statistics from Parquet data scale pip-denominated params, (L4) physical constraints — stop_loss.min > typical spread for the pair, period.max < data_bars / 10, (L5) cross-parameter relationships — slow_period.min > fast_period.min, conditional activation rules
   **Testability:** Each layer produces a deterministic output given the same inputs. Proposed ranges must satisfy: all numeric ranges have min < max, all period ranges fall within the timeframe lookup bounds, all pip-based ranges are scaled by ATR stats (not hardcoded constants).
   [Source: FR24, D10, Epic 1 data]

5. **Given** the range proposal engine runs for a specific pair and timeframe
   **When** pair-specific ATR statistics are needed
   **Then** the engine computes ATR(14) statistics from the actual downloaded Parquet market data (Epic 1) at the strategy's timeframe — using these to scale pip-based parameter ranges proportionally to ATR magnitude (e.g., a pair with 2x higher ATR gets proportionally wider pip-based ranges)
   **When** Parquet data is not available for the requested pair/timeframe
   **Then** the engine falls back to hardcoded default ATR values, logs a WARNING identifying which pair/timeframe used defaults, and marks the affected parameters as `source: "default"` in the proposal output (not silently accepted)
   [Source: Epic 1 data pipeline, D10]

6. **Given** the operator receives proposed ranges
   **When** reviewing the optimization_plan before finalization
   **Then** the operator can review proposed ranges in the TOML file or via pipeline skill "Review search space" command, adjust any range by editing the TOML directly or via "Adjust parameter range" skill command, and override any proposed value — the proposal is an advisory default, not a mandate
   [Source: D9 operator interface]

7. **Given** cross-parameter constraints exist in the optimization space
   **When** the validator runs
   **Then** it verifies: slow_period range min > fast_period range min (ranges don't overlap impossibly), conditional parameters only activate when their parent condition is met, pip-based ranges are pair-appropriate (stop_loss min > typical spread for the pair)
   [Source: FR24, D10]

8. **Given** the reference strategy (ma-crossover) exists at v001
   **When** the schema migration runs
   **Then** a v002 is created at `artifacts/strategies/ma-crossover/v002.toml` with the new flat parameter registry format, expanded to include all searchable parameters (entry indicator periods, stop loss type+value, take profit type+value, trailing stop params, session filter) with ranges proposed by the range proposal engine for EURUSD H1
   [Source: artifacts/strategies/ma-crossover/v001.toml]

9. **Given** the /pipeline skill needs search space commands
   **When** the operator wants to work with optimization spaces
   **Then** the pipeline skill is updated to support: "Propose optimization space" (runs range proposal for current strategy), "Review search space" (shows parameter registry with ranges), "Adjust parameter range" (operator overrides specific ranges)
   [Source: D9]

10. **Given** Story 5-3 needs to consume the new optimization_plan format
    **When** the contract is defined
    **Then** `parse_strategy_params()` is documented with: input = `OptimizationPlan` (new flat format), output = `ParameterSpace` containing shared continuous/integer params plus branches per top-level categorical — the contract defines the data shape only, NOT the optimizer's internal search policy or budget allocation (those are Story 5-3's domain per D3)
    [Source: Story 5-3 AC2, AC14]

11. **Given** the range proposal engine produces proposed ranges
    **When** the proposal is generated
    **Then** a persisted proposal artifact is written alongside the strategy spec containing: proposal timestamp, pair and timeframe, ATR statistics used (with source: "computed" or "default"), indicator registry version hash, per-parameter source layer (L1-L5), and any operator overrides applied after initial proposal
    [Source: D7 reproducibility, D10 provenance]

12. **Given** the optimization_plan schema is being versioned
    **When** the new flat format replaces parameter_groups
    **Then** the TOML contract and Pydantic model include a `schema_version = 2` field, and the loader raises a clear `SchemaVersionError` with migration instructions when it encounters a v1 (parameter_groups) format — enabling historical specs to be identified without ambiguity
    [Source: D7 configuration, backwards compatibility]

## Tasks / Subtasks

- [ ] **Task 1: Update strategy_specification.toml contract** (AC: #1, #2, #12)
  - [ ] Add `schema_version` field (int, required, value=2) to `[optimization_plan]`
  - [ ] Replace `[optimization_plan.parameter_groups]` array-of-tables with `[optimization_plan.parameters]` flat table-of-tables
  - [ ] Define per-parameter fields: `type` (utf8, values=["continuous","integer","categorical"]), `min` (float64, required if numeric), `max` (float64, required if numeric), `step` (float64, optional for integer display rounding), `choices` (array_utf8, required if categorical), `condition` (table with `parent` utf8 + `value` utf8, optional)
  - [ ] Remove `[optimization_plan.parameter_groups.range_fields]` section entirely
  - [ ] Remove `[optimization_plan.group_dependencies]` section entirely
  - [ ] Keep `[optimization_plan.objective_function]` unchanged
  - [ ] Add comment block explaining D10 taxonomy and conditional parameter nesting
  - [ ] File: `contracts/strategy_specification.toml` lines 113-135

- [ ] **Task 2: Update Pydantic v2 models in specification.py** (AC: #1, #2, #3, #7)
  - [ ] Replace `ParameterRange` (lines 251-266) with `SearchParameter` model:
    ```python
    class ParameterCondition(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")
        parent: str = Field(..., min_length=1, description="Parent categorical parameter name")
        value: str = Field(..., min_length=1, description="Parent value that activates this parameter")

    ParameterType = Literal["continuous", "integer", "categorical"]

    class SearchParameter(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: ParameterType
        min: Optional[float] = None  # required for continuous/integer
        max: Optional[float] = None  # required for continuous/integer
        step: Optional[float] = None  # optional, for integer display rounding
        choices: Optional[list[str]] = None  # required for categorical
        condition: Optional[ParameterCondition] = None  # optional, for conditional activation
    ```
  - [ ] Add `@model_validator(mode="after")` to `SearchParameter`:
    - If type == "continuous" or "integer": require min/max, validate min < max, if step: validate step > 0
    - If type == "integer": validate min/max are whole numbers (min == int(min))
    - If type == "categorical": require choices with len >= 2, reject min/max/step
    - If condition is set: no additional structural validation here (cross-param validation in OptimizationPlan)
  - [ ] Remove `ParameterGroup` class (lines 269-295) entirely
  - [ ] Replace `OptimizationPlan` (lines 298-325) with flat version:
    ```python
    class OptimizationPlan(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")
        schema_version: Literal[2] = Field(..., description="Must be 2 for flat parameter format")
        parameters: dict[str, SearchParameter] = Field(..., min_length=1)
        objective_function: ObjectiveFunction
    ```
  - [ ] Add `@model_validator(mode="after")` to `OptimizationPlan`:
    - Validate all condition.parent references point to an existing categorical parameter name in `parameters`
    - Validate all condition.value is a valid choice in the parent's `choices` list
    - Detect circular dependencies: build DAG from condition references, check for cycles using topological sort
    - Validate no orphaned conditions (parent key must exist in parameters dict)
  - [ ] Update `StrategySpecification` to use the updated `OptimizationPlan` (no change needed if class name unchanged)
  - [ ] File: `src/python/strategy/specification.py`

- [ ] **Task 3: Update loader.py semantic validation** (AC: #3, #7)
  - [ ] Update `validate_strategy_spec()` in `loader.py` (lines 116-134):
    - Replace parameter_groups iteration with flat parameters iteration
    - For each parameter in `optimization_plan.parameters`: verify the parameter name exists in the strategy's entry conditions, exit rules, trailing params, or filters
    - For conditional parameters: verify the condition chain resolves to a valid categorical parent
    - Add cross-parameter range validation: if both `fast_period` and `slow_period` exist, warn if `slow_period.min <= fast_period.max` (overlap could produce invalid fast >= slow combinations)
  - [ ] Collect ALL errors before returning (existing pattern — do not change)
  - [ ] File: `src/python/strategy/loader.py` lines 116-134

- [ ] **Task 4: Create range proposal engine** (AC: #4, #5, #6, #7, #11)
  - [ ] Create new file: `src/python/strategy/range_proposal.py`
  - [ ] Implement `ATRStats` dataclass:
    ```python
    @dataclass(frozen=True)
    class ATRStats:
        pair: str
        timeframe: str
        atr_14_median: float  # median ATR(14) in pips
        atr_14_p90: float     # 90th percentile ATR(14)
        daily_range_median: float  # median daily high-low range in pips
        typical_spread: float  # typical spread for pair (from cost model or hardcoded defaults)
        data_bars: int  # total bars in dataset
    ```
  - [ ] Implement pip value lookup per pair:
    ```python
    PIP_VALUES: dict[str, float] = {
        "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001,
        "NZDUSD": 0.0001, "USDCAD": 0.0001, "USDCHF": 0.0001,
        "USDJPY": 0.01, "XAUUSD": 0.01,
    }
    ```
  - [ ] Implement `compute_pair_atr_stats(pair: str, timeframe: str, data_dir: Path) -> ATRStats`:
    - Discover data path: check `data/{pair}/` for Parquet files (Epic 1 output uses `data_manifest.json` for paths — see `src/python/data_pipeline/data_manifest.py`). Alternatively fall back to glob `data/**/{pair}*/**/*.parquet`
    - Parquet schema columns from Epic 1: `timestamp`, `open`, `high`, `low`, `close`, `volume`, `session` (labeled by session_labeler.py)
    - Compute ATR(14): `TR = max(high-low, abs(high-prev_close), abs(low-prev_close))`, then EMA(14) of TR
    - Convert ATR from price units to pips using `PIP_VALUES[pair]`
    - Return median, p90, daily range, bar count
    - If data not found, return sensible hardcoded defaults with warning log:
      ```python
      DEFAULT_ATR_PIPS: dict[str, float] = {
          "EURUSD": 5.0, "GBPUSD": 7.0, "USDJPY": 5.0,
          "AUDUSD": 4.0, "USDCAD": 5.0, "USDCHF": 4.0,
          "NZDUSD": 4.0, "XAUUSD": 150.0,
      }
      ```
  - [ ] Implement timeframe scaling lookup:
    ```python
    TIMEFRAME_PERIOD_RANGES: dict[str, tuple[int, int]] = {
        "M1": (5, 300),    # M1: short periods meaningless, long periods = hours of data
        "M5": (5, 200),
        "M15": (5, 100),
        "H1": (5, 100),
        "H4": (5, 50),
        "D1": (5, 50),     # D1: 50 periods = ~2.5 months lookback
    }
    ```
  - [ ] Implement `propose_ranges(spec: StrategySpecification, data_dir: Path | None = None) -> dict[str, SearchParameter]`:
    - Walk `spec.entry_rules.conditions` → extract indicator parameters (e.g., fast_period, slow_period from sma_crossover)
    - Walk `spec.entry_rules.filters` → extract filter parameters (session choices, volatility params)
    - Walk `spec.exit_rules` → extract stop_loss type/value, take_profit type/value, trailing params
    - For each extracted parameter:
      - Look up indicator in `indicator_registry.toml` for parameter metadata
      - Determine SearchParameter type: period params → integer, multiplier/value params → continuous, type fields → categorical
      - Apply timeframe scaling for period params
      - Apply ATR stats for pip-denominated params (stop_loss value, take_profit value, trailing distance)
      - Apply physical constraints: stop_loss.min > typical_spread, period.max < data_bars / 10
    - Return flat dict of parameter_name → SearchParameter with proposed ranges
  - [ ] Implement `apply_cross_parameter_constraints(params: dict[str, SearchParameter]) -> dict[str, SearchParameter]`:
    - If fast_period and slow_period both exist: ensure slow_period.min >= fast_period.min + fast_period.step
    - If stop_loss and take_profit both exist with numeric ranges: ensure take_profit.min >= stop_loss.min
  - [ ] Implement `persist_proposal(proposal: dict[str, SearchParameter], atr_stats: ATRStats, strategy_name: str, output_dir: Path) -> Path`:
    - Write JSON artifact to `artifacts/strategies/{strategy_name}/optimization_proposal.json`
    - Include: timestamp, pair, timeframe, ATR stats with source ("computed" or "default"), per-parameter source layer (L1-L5), indicator_registry hash, proposal engine version
    - This artifact is advisory/diagnostic — the canonical ranges live in the strategy TOML
  - [ ] File: `src/python/strategy/range_proposal.py`

- [ ] **Task 5: Create reference strategy v002** (AC: #8, #12)
  - [ ] Create `artifacts/strategies/ma-crossover/v002.toml` with new flat format including `schema_version = 2`
  - [ ] Convert v001's 3 grouped params (fast_period, slow_period, atr_multiplier) to flat SearchParameter entries
  - [ ] Expand searchable parameters to include ALL optimizable params:
    - `fast_period`: integer, min=5, max=80, step=5 (scaled for H1)
    - `slow_period`: integer, min=20, max=200, step=10 (scaled for H1)
    - `sl_atr_multiplier`: continuous, min=0.5, max=5.0 (stop loss ATR mult)
    - `tp_rr_ratio`: continuous, min=1.0, max=5.0 (risk:reward ratio)
    - `trailing_atr_period`: integer, min=5, max=50
    - `trailing_atr_multiplier`: continuous, min=1.0, max=5.0
    - `session_filter`: categorical, choices=["asian","london","new_york","london_ny_overlap"]
  - [ ] Validate v002 loads cleanly through updated Pydantic models
  - [ ] File: `artifacts/strategies/ma-crossover/v002.toml`

- [ ] **Task 6: Define parse_strategy_params() contract for Story 5-3** (AC: #10)
  - [ ] Document the **data shape contract** in `contracts/optimization_space.md` (new file):
    ```python
    def parse_strategy_params(optimization_plan: OptimizationPlan) -> ParameterSpace:
        """Parse flat parameter registry into ParameterSpace data shape.

        Args:
            optimization_plan: Validated OptimizationPlan with flat parameters dict.

        Returns:
            ParameterSpace with:
            - shared_params: continuous/integer params with no condition
            - branches: mapping (categorical_param, choice_value) -> child params
            - branch_categoricals: top-level categorical params (no condition)
            - total_dims: max dimensionality across branches

        Note: How the optimizer uses this decomposition (search policy,
        budget allocation) is Story 5-3's domain, not defined here.
        """

    @dataclass
    class ParameterSpace:
        shared_params: dict[str, SearchParameter]
        branches: dict[tuple[str, str], dict[str, SearchParameter]]
        branch_categoricals: list[str]
        total_dims: int  # max dimensionality across branches (shared + largest branch)
    ```
  - [ ] File: `contracts/optimization_space.md`

- [ ] **Task 7: Update /pipeline skill** (AC: #9)
  - [ ] Add three new commands to `.claude/skills/pipeline/` skill definition:
    - "Propose optimization space" — calls `propose_ranges()` for current strategy, displays proposed parameters
    - "Review search space" — loads strategy spec, shows optimization_plan.parameters in readable table
    - "Adjust parameter range" — operator specifies param name + new min/max/step/choices, updates spec file
  - [ ] File: `.claude/skills/pipeline/`

- [ ] **Task 8: Tests** (AC: all)
  - [ ] Create `src/python/tests/test_strategy/test_search_parameter.py`:
    - `test_search_parameter_continuous_valid` — continuous with min/max validates
    - `test_search_parameter_integer_valid` — integer with min/max/step validates, min/max are whole numbers
    - `test_search_parameter_integer_non_whole_fails` — integer with min=5.5 fails
    - `test_search_parameter_categorical_valid` — categorical with choices validates
    - `test_search_parameter_categorical_needs_two_choices` — single choice fails
    - `test_search_parameter_continuous_missing_bounds_fails` — continuous without min/max fails
    - `test_search_parameter_categorical_rejects_bounds` — categorical with min/max fails
    - `test_search_parameter_min_gte_max_fails` — min >= max fails
    - `test_search_parameter_conditional_valid` — condition with valid parent ref structure validates
    - `test_optimization_plan_flat_valid` — full flat plan with mixed types validates
    - `test_optimization_plan_condition_invalid_parent` — condition references nonexistent parent fails
    - `test_optimization_plan_condition_invalid_choice` — condition references choice not in parent's choices fails
    - `test_optimization_plan_circular_dependency` — A conditioned on B conditioned on A fails
    - `test_optimization_plan_nested_three_deep` — A → B → C conditional chain validates
    - `test_v002_loads_and_validates` — load v002.toml through full pipeline, no errors
    - `test_v002_semantic_validation_passes` — v002 passes validate_strategy_spec()
    - `test_schema_version_required` — OptimizationPlan without schema_version fails validation
    - `test_schema_version_1_rejected` — schema_version=1 raises SchemaVersionError with migration message
    - `test_v001_legacy_format_clear_error` — loading v001 optimization_plan raises clear error identifying legacy format
  - [ ] Create `src/python/tests/test_strategy/test_range_proposal.py`:
    - `test_propose_ranges_sma_crossover_eurusd_h1` — propose for ma-crossover on EURUSD H1, check period ranges are H1-appropriate
    - `test_timeframe_scaling_m1_wider_than_d1` — M1 period max > D1 period max
    - `test_pair_atr_scaling_volatile_wider` — pair with higher ATR gets wider pip-based ranges
    - `test_physical_constraint_stop_gt_spread` — stop_loss.min > typical spread
    - `test_physical_constraint_period_lt_data_bars` — period.max < data_bars / 10
    - `test_cross_param_slow_gt_fast` — slow_period.min > fast_period.min
    - `test_propose_with_no_data_uses_defaults` — missing data directory still produces ranges with defaults
    - `test_propose_includes_exit_params` — proposed ranges include stop_loss, take_profit, trailing params
    - `test_proposal_artifact_persisted` — persist_proposal() writes JSON with required provenance fields (timestamp, pair, timeframe, atr_source, per-param source layer)
    - `test_proposal_default_atr_marked` — when data unavailable, affected params have source="default" in artifact
  - [ ] Update existing tests that load v001 with optimization_plan:
    - `src/python/tests/test_strategy/test_regression.py` — update or add v002 test path
    - `src/python/tests/test_strategy/test_live_strategy.py` — update optimization_plan fixtures to new format
    - `src/python/tests/test_strategy/test_regression_2_5.py` — check if optimization_plan fixtures need updating
    - Grep for `parameter_groups` across all test files: any test constructing an `OptimizationPlan` with the old format must be migrated
  - [ ] Run full test suite (`pytest src/python/tests/test_strategy/`) to verify no regressions from schema change

## Dev Notes

### Architecture Constraints

- **D10 (Strategy Execution Model):** Three-layer model: intent → specification → evaluator. This story modifies the specification layer. The Rust evaluator (Story 2-8, crate `strategy_engine`) also parses the TOML contract — but only the entry/exit rules, NOT the optimization_plan. The optimization_plan is Python-only (consumed by Story 5-3 orchestrator). Therefore, no Rust changes needed.
- **D7 (Configuration):** TOML with schema validation at startup. The strategy_specification.toml contract is the single source of truth. Both Python Pydantic models and the contract TOML must stay in sync.
- **D3 (Opaque Optimizer):** The optimizer treats the search space as opaque. Story 5-3 calls `parse_strategy_params()` to convert the flat parameter registry into an optimizer-ready `ParameterSpace`. This story defines the **data shape contract only** — how the optimizer internally decomposes branches, allocates budget, or chooses search policy is Story 5-3's domain. Do NOT leak optimizer internals into this story's schema or contract docs.
- **D1 (Multi-Process):** The range proposal engine is pure Python. ATR computation reads Parquet data via pyarrow. No Rust involvement.
- **D9 (Operator Interface):** Pipeline skill updates enable operator interaction with search spaces. The proposal is advisory — operator always has final say. V1 skill commands operate directly on TOML files via the CLI — API/orchestrator routing is post-V1.

### FR13/FR24 Resolution

The PRD's FR13 (strategy-defined parameter groups) and FR24 (parameter staging) appear to conflict with the flat registry approach. This was resolved by the Story 5.2 optimization research: **the strategy spec defines searchable parameters with bounds and conditional structure; the optimizer owns grouping/staging/search policy internally.** The flat `parameters` dict in `optimization_plan` is the spec's declaration of "what is searchable." Parameters NOT listed in the dict are fixed at their spec values and are not searched.

### Parameter Naming Convention

The flat `parameters` dict uses parameter names as keys. To avoid collisions when a strategy has parameters with the same name across different components (e.g., `period` in both entry and exit indicators), use component-prefixed names: `fast_period`, `slow_period`, `sl_atr_multiplier`, `tp_rr_ratio`, `trailing_atr_period`. The reference strategy v002 demonstrates this convention. For V1, the naming convention is sufficient — canonical dotted paths (e.g., `entry.fast_ma.period`) are deferred to post-V1 if needed for complex multi-indicator strategies.

### Technical Requirements

- **Python 3.11+** (uses `tomllib` from stdlib)
- **Pydantic v2** with strict mode and `extra="forbid"` (existing pattern — follow exactly)
- **pyarrow** for reading Parquet data (already a project dependency from Epic 1)
- **No new dependencies** — ATR computation uses numpy (already installed) or pure Python
- The condition DAG cycle detection can use a simple DFS/topological sort — no need for external graph library
- **pyarrow** compute functions preferred for ATR: `pyarrow.compute.max_element_wise()`, `pyarrow.compute.abs()`, etc. — avoids loading entire dataset into memory

### Integration Points

- **spec_generator.py** (`src/python/strategy/spec_generator.py`): This module generates strategy specs from intent capture (Story 2-4). The range proposal engine should be callable FROM spec_generator after a spec is generated — but do NOT modify spec_generator.py in this story. Just ensure `propose_ranges()` accepts a `StrategySpecification` as input so spec_generator can call it later.
- **data_manifest.py** (`src/python/data_pipeline/data_manifest.py`): Use `DataManifest` to discover data file paths if available. The manifest tracks what data Epic 1 downloaded and where it lives. Fall back to direct directory glob if manifest is unavailable.
- **cost_model sessions** (`src/python/cost_model/sessions.py`): Contains session time definitions (asian, london, new_york, etc.) and potentially spread data that could inform `typical_spread` in ATRStats. Check if usable before hardcoding spread defaults.

### Breaking Change: v001 Optimization Plan Format

The `OptimizationPlan` Pydantic model changes from `parameter_groups: list[ParameterGroup]` to `parameters: dict[str, SearchParameter]`. This means v001.toml's `optimization_plan` section will NOT validate against the new models.

**Resolution:** v001 remains as historical artifact (it was the Epic 2-3 E2E proof reference). v002 becomes the canonical reference. Tests that loaded v001's optimization_plan must be updated to use v002 or updated fixtures. If the loader encounters the old format, it should raise a clear error: "optimization_plan uses legacy parameter_groups format — migrate to flat parameters (schema v2)".

### parse_strategy_params() Contract Summary

This is the bridge between Story 5-2b (schema) and Story 5-3 (orchestrator). This story defines the **data shape contract only** — how 5-3 internally decomposes branches, allocates batch budget, or implements search policy is 5-3's domain (per D3 opaque optimizer):

```
Input:  OptimizationPlan.parameters (flat dict[str, SearchParameter])
Output: ParameterSpace (shared params + categorical branches)

Data shape:
1. Identify top-level categoricals (no condition) → these become branch axes
2. For each top-level categorical, for each choice:
   - Collect all params conditioned on (categorical, choice)
   - Recursively collect nested conditionals
3. Shared params = all non-conditional continuous/integer params
4. total_dims = max dimensionality across branches (shared + largest branch)

Note: How the optimizer uses this decomposition (sub-portfolios, budget
allocation, search strategy) is defined in Story 5-3, not here.
```

### Performance Considerations

- ATR computation from Parquet is fast (pyarrow reads columnar data efficiently). For EURUSD M1 with ~5M bars, ATR(14) computation takes <2 seconds.
- Range proposal is a one-time operation per strategy creation — not on the hot path.
- Condition DAG validation is O(V+E) where V = parameter count, E = condition count. Even for 100+ parameters, this is instant.

## What to Reuse from ClaudeBackTester

- **ClaudeBackTester's 5-stage parameter locking model** — this is what we're REPLACING. Do NOT copy its staged approach. The flat registry is the explicit FR24 replacement for staged groups.
- **ClaudeBackTester's parameter range definitions** — review `ClaudeBackTester/optimizer/` for how it currently defines ranges. Use as reference for what reasonable ranges look like, but implement the new flat schema.
- **Do NOT reuse** ClaudeBackTester's optimization_groups or group_dependencies patterns.

## Anti-Patterns to Avoid

1. **Do NOT re-introduce staged parameter groups.** FR24 explicitly eliminates mandatory staging. The flat registry is the design. If you find yourself creating a `ParameterGroup` or `group_dependencies`, stop — you're reverting to the old design.

2. **Do NOT hardcode strategy parameter ranges in Python code.** All strategy-specific ranges come from the TOML contract or the range proposal engine. The engine computes ranges dynamically from data and registry metadata. Note: engine metadata (timeframe period bounds, pip value lookups, default ATR fallbacks) ARE hardcoded in the engine — these are infrastructure constants, not strategy-specific ranges. The distinction: "EURUSD stop_loss min=10 pips" is a strategy range (must not be hardcoded); "M1 period range is 5-300" is engine metadata (acceptable as a constant).

3. **Do NOT make the range proposal engine mandatory.** It proposes defaults. The operator can skip it entirely and hand-specify all ranges in the TOML file. The engine is a convenience, not a gate.

4. **Do NOT create a separate "v2" Pydantic model alongside v1.** Replace the existing models in-place. `ParameterGroup` and the old `OptimizationPlan` are removed. One model, one format.

5. **Do NOT compute ATR from CSV files.** Epic 1 stores data as Parquet. Use pyarrow to read Parquet directly. Check `data/` directory structure from the data pipeline.

6. **Do NOT add pandas as a dependency for ATR computation.** Use pyarrow compute functions or numpy. pandas is heavy and not needed for simple rolling calculations.

7. **Do NOT validate cross-parameter constraints at schema level.** Cross-parameter constraints (slow > fast) are warnings in `validate_strategy_spec()`, not Pydantic model validation. The optimizer can handle overlapping ranges — it just wastes search budget.

8. **Do NOT modify the Rust strategy_engine crate.** The optimization_plan is consumed only by Python (Story 5-3 orchestrator). Rust parses entry/exit rules only.

## Project Structure Notes

### Files to Modify

| File | Change |
|------|--------|
| `contracts/strategy_specification.toml` | Replace optimization_plan.parameter_groups with flat parameters registry |
| `src/python/strategy/specification.py` | Replace ParameterRange, ParameterGroup, OptimizationPlan models |
| `src/python/strategy/loader.py` | Update validate_strategy_spec() for flat schema |
| `src/python/tests/test_strategy/test_regression.py` | Update optimization_plan fixtures to new format |
| `src/python/tests/test_strategy/test_live_strategy.py` | Update optimization_plan fixtures to new format |

### Files to Create

| File | Purpose |
|------|---------|
| `src/python/strategy/range_proposal.py` | Range proposal engine (ATR stats, timeframe scaling, physical constraints) |
| `src/python/tests/test_strategy/test_search_parameter.py` | Tests for new SearchParameter/OptimizationPlan models |
| `src/python/tests/test_strategy/test_range_proposal.py` | Tests for range proposal engine |
| `artifacts/strategies/ma-crossover/v002.toml` | Reference strategy with new flat parameter format |
| `contracts/optimization_space.md` | parse_strategy_params() contract for Story 5-3 |
| `artifacts/strategies/ma-crossover/optimization_proposal.json` | Persisted proposal artifact with provenance (generated by engine) |

### Files NOT to Modify

| File | Reason |
|------|--------|
| `contracts/indicator_registry.toml` | Read-only input to range proposal engine — no changes |
| `src/python/strategy/indicator_registry.py` | Read-only — use `get_registry()` and `get_indicator_params()` as-is |
| `src/rust/crates/strategy_engine/` | Rust doesn't parse optimization_plan |
| `artifacts/strategies/ma-crossover/v001.toml` | Historical artifact — do not modify |

### Directory Layout

```
contracts/
  strategy_specification.toml          # MODIFY: flat parameters schema
  indicator_registry.toml              # READ ONLY
  optimization_space.md                # CREATE: 5-3 contract doc
src/python/strategy/
  specification.py                     # MODIFY: new Pydantic models
  loader.py                            # MODIFY: new validation
  range_proposal.py                    # CREATE: range proposal engine
  indicator_registry.py                # READ ONLY
src/python/tests/test_strategy/
  test_search_parameter.py             # CREATE: model tests
  test_range_proposal.py               # CREATE: engine tests
  test_regression.py                   # MODIFY: update fixtures
  test_live_strategy.py                # MODIFY: update fixtures
artifacts/strategies/ma-crossover/
  v001.toml                            # READ ONLY (historical)
  v002.toml                            # CREATE: new format reference
```

## References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 5, Story 5.2b]
- [Source: _bmad-output/planning-artifacts/architecture.md — D3 Opaque Optimizer, D7 Configuration, D9 Operator Interface, D10 Strategy Execution Model]
- [Source: _bmad-output/planning-artifacts/prd.md — FR12, FR13, FR24]
- [Source: contracts/strategy_specification.toml — Current optimization_plan schema, lines 113-141]
- [Source: src/python/strategy/specification.py — ParameterRange (251-266), ParameterGroup (269-295), OptimizationPlan (298-325)]
- [Source: src/python/strategy/loader.py — validate_strategy_spec() lines 116-134]
- [Source: src/python/strategy/indicator_registry.py — get_registry(), get_indicator_params() API]
- [Source: contracts/indicator_registry.toml — 21 indicators with required_params/optional_params metadata]
- [Source: artifacts/strategies/ma-crossover/v001.toml — Current reference strategy with staged optimization_plan]
- [Source: _bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md — parse_strategy_params contract consumer, AC2, AC14 branch decomposition]
- [Source: _bmad-output/implementation-artifacts/5-2-optimization-algorithm-candidate-selection-validation-gauntlet-research.md — CMA-ES CatCMAwM supports mixed parameter types natively]

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### Change Log

### File List
