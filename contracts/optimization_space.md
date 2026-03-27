# Optimization Space Contract — parse_strategy_params() (Story 5-2b → 5-3)

This document defines the **data shape contract** between the optimization search
space schema (Story 5-2b) and the optimization orchestrator (Story 5-3).

## Contract: parse_strategy_params()

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

## Data Shape Decomposition Algorithm

1. **Identify top-level categoricals** — categorical parameters with `condition = None`
   → these become branch axes stored in `branch_categoricals`

2. **For each top-level categorical, for each choice:**
   - Collect all parameters conditioned on `(categorical, choice)`
   - Recursively collect nested conditionals (parameters conditioned on
     child categoricals of this branch)
   - Store in `branches[(categorical_name, choice_value)]`

3. **Shared parameters** — all continuous/integer parameters with `condition = None`
   → stored in `shared_params`

4. **total_dims** = len(shared_params) + max branch size across all branches

## Boundary: What This Contract Does NOT Define

Per D3 (Opaque Optimizer), the following are **Story 5-3's domain**:

- How the optimizer internally decomposes branches into sub-portfolios
- Budget allocation across branches (equal split, proportional, adaptive)
- Search strategy within each branch (CMA-ES, grid, random)
- Whether branches are searched sequentially or in parallel
- Evaluation batch sizing and parallelism

This contract defines the **data shape only** — the structured input that
Story 5-3's orchestrator consumes.

## Input Format

```toml
[optimization_plan]
schema_version = 2
objective_function = "sharpe"

[optimization_plan.parameters.fast_period]
type = "integer"
min = 5.0
max = 80.0
step = 5.0

[optimization_plan.parameters.slow_period]
type = "integer"
min = 20.0
max = 200.0
step = 10.0

[optimization_plan.parameters.session_filter]
type = "categorical"
choices = ["asian", "london", "new_york", "london_ny_overlap"]
```

## References

- Source: `src/python/strategy/specification.py` — `OptimizationPlan`, `SearchParameter`
- Source: `contracts/strategy_specification.toml` — Schema contract
- Consumer: Story 5-3 AC2, AC14 — `parse_strategy_params()` implementation
- Architecture: D3 (Opaque Optimizer), D10 (Strategy Execution Model)
