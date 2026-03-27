# Story 5-3-python-optimization-orchestrator: Story 5.3: Python Optimization Orchestrator — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-22
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

**HIGH Findings**
- Resume is not actually resumable. Checkpoints only persist summary counters, not the internal CMA-ES/DE optimizer state or RNG state, and `load_state()` restores only metadata. A resumed run will diverge from the pre-crash search immediately, so AC8, AC9, and AC16 are not satisfied. Refs: [portfolio.py#L188](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L188), [portfolio.py#L200](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L200), [portfolio.py#L278](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L278), [portfolio.py#L288](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L288), [orchestrator.py#L140](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/orchestrator.py#L140), [checkpoint.py#L33](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/checkpoint.py#L33)
- Resume loses prior evaluated data. `run()` always opens a fresh `StreamingResultsWriter` for the fixed results path and resets `best_candidates`/`best_score` instead of rehydrating them from checkpointed state, so a resumed run can overwrite prior generations and violate “resume without data loss”. Refs: [orchestrator.py#L158](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/orchestrator.py#L158), [orchestrator.py#L166](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/orchestrator.py#L166), [orchestrator.py#L170](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/orchestrator.py#L170), [orchestrator.py#L267](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/orchestrator.py#L267)
- Result provenance is wrong for `instance_type`. The code repeats the branch’s instance-type list across all candidates instead of using the actual per-candidate allocation recorded by `PortfolioManager`, so the Arrow artifact can silently mislabel which algorithm produced each candidate. Refs: [portfolio.py#L445](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L445), [branch_manager.py#L145](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/branch_manager.py#L145), [orchestrator.py#L219](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/orchestrator.py#L219)
- The Rust dispatch path is brittle to the point of likely failure. The orchestrator does not accept the real strategy-spec path; it guesses one, and if missing, writes JSON to a `.toml` file even though the bridge contract expects a TOML spec. That can break AC3 execution in normal pipeline runs. Refs: [orchestrator.py#L162](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/orchestrator.py#L162), [orchestrator.py#L360](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/orchestrator.py#L360), [batch_runner.py#L25](/C:/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/batch_runner.py#L25)
- AC1/AC2’s mixed-parameter optimizer requirement is not implemented as specified. `CMAESInstance` wraps plain `cmaes.CMA`, not CatCMAwM/CMAwM, while categorical parameters are just scalar-encoded bounds. That is not the requested optimizer portfolio for mixed continuous/integer/categorical search. Refs: [portfolio.py#L63](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L63), [parameter_space.py#L191](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/parameter_space.py#L191), [parameter_space.py#L210](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/parameter_space.py#L210)
- Portfolio convergence is effectively unreachable with the default DE instances. `DEInstance.converged()` always returns `_converged`, but `_converged` is never set to `True`, while portfolio convergence requires every non-Sobol instance to converge. That means AC7’s convergence behavior never happens unless DE is removed. Refs: [portfolio.py#L223](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L223), [portfolio.py#L275](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L275), [portfolio.py#L474](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L474), [config/base.toml#L123](/C:/Users/ROG/Projects/Forex Pipeline/config/base.toml#L123)
- Missing score output is silently converted into zeros. If Rust exits 0 but produces no score file, `_read_fold_scores()` fabricates `0.0` scores instead of failing the fold, which corrupts objective values and hides dispatcher/evaluator faults. Refs: [batch_dispatch.py#L159](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/batch_dispatch.py#L159)

**MEDIUM Findings**
- Batch capacity is not actually filled, and `sobol_fraction=0` still forces one Sobol candidate. `ask_batch()` floor-divides the algorithm budget and drops the remainder, while `max(1, ...)` guarantees Sobol participation even when config disables it. Refs: [portfolio.py#L426](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L426), [portfolio.py#L428](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L428), [portfolio.py#L432](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L432), [test_portfolio.py#L24](/C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_optimization/test_portfolio.py#L24)
- Conditional branching only handles the first top-level categorical parent. The contract explicitly allows deeper conditional chains, but `detect_branches()` stops at the first branching categorical, so multi-level/multi-parent conditionals are only partially supported. Refs: [parameter_space.py#L154](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/parameter_space.py#L154), [strategy_specification.toml#L118](/C:/Users/ROG/Projects/Forex Pipeline/contracts/strategy_specification.toml#L118)
- Branched candidates are written without the branch-defining categorical in `params_json`. Because the branch parent is removed from the branch subspace, `decode_candidate()` serializes incomplete parameter vectors and downstream consumers must reconstruct state from the separate `branch` string. Refs: [parameter_space.py#L160](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/parameter_space.py#L160), [orchestrator.py#L215](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/orchestrator.py#L215)
- Embargo handling can silently degrade into no embargo at all. When the dataset is too short, `_compute_folds()` drops the embargo instead of failing or recomputing splits, reopening leakage risk in edge cases. Refs: [fold_manager.py#L75](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/fold_manager.py#L75)
- Logging is only partially compliant with AC12. The JSON logging infrastructure exists, and generation/diversity are logged, but instance-level status is missing from the emitted optimizer log context. Refs: [orchestrator.py#L251](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/orchestrator.py#L251), [logging_setup/setup.py#L29](/C:/Users/ROG/Projects/Forex Pipeline/src/python/logging_setup/setup.py#L29)

**Acceptance Criteria Scorecard**

| AC | Status | Notes |
|---|---|---|
| 1 | Partially Met | Config-driven portfolio exists, but uses plain `CMA` and underfills batches. |
| 2 | Partially Met | Basic types parse, but conditional support is only single-level/partial. |
| 3 | Partially Met | Ask/tell loop exists, but dispatch path is fragile and not fully D1-compliant. |
| 4 | Fully Met | K-fold score aggregation uses configurable `mean - lambda * std`. |
| 5 | Partially Met | Fold metadata is passed, but as one-fold-per-job rather than a true fold-aware batch. |
| 6 | Partially Met | Population sizing and restart ideas exist, but the implementation is simplified. |
| 7 | Partially Met | CMA-ES tolerances/restarts exist, but portfolio convergence is blocked by DE. |
| 8 | Not Met | Checkpoints do not persist actual optimizer populations/state. |
| 9 | Not Met | Resume can overwrite prior results and cannot restore exact search state. |
| 10 | Fully Met | Sobol explorer runs alongside algorithm instances. |
| 11 | Partially Met | Preflight exists, but the budget model is coarse and incomplete. |
| 12 | Partially Met | Structured JSON logging exists, but instance-level status is missing. |
| 13 | Partially Met | Arrow results and manifest are written, but provenance fields are incomplete/incorrect. |
| 14 | Partially Met | Branch decomposition and UCB1 exist, but only for the first top-level branch. |
| 15 | Fully Met | Top-N promotion artifact is written with stable candidate IDs. |
| 16 | Not Met | Per-instance seeds are not recorded/restored, so deterministic replay is not guaranteed. |

**Test Coverage Gaps**
- `src/python/tests/test_optimization/test_orchestrator.py` is missing entirely, so `OptimizationOrchestrator.run()` is not directly tested despite the story claiming those tests.
- `test_batch_dispatch.py` only exercises `check_memory`; it never calls `dispatch_generation()`, never verifies Arrow input generation, and never covers missing-score behavior.
- No test proves checkpoint resume preserves the exact candidate sequence after restoring a checkpointed portfolio; the deterministic-seed test only compares two fresh managers.
- No test checks that per-candidate `instance_type` in the results artifact matches the true source allocation.
- No test covers the strategy-spec-path resolution/fallback path in `OptimizationOrchestrator`.
- No test covers multi-level conditional branching or multiple branching parents.
- The story-promised config-loading tests (`test_optimization_config_loads_defaults`, `test_optimization_config_env_override`) are absent.

**Summary**
4 of 16 criteria are fully met, 9 are partially met, and 3 are not met.

I could not run `pytest` in this sandbox because command execution was blocked by policy, so the coverage assessment is based on static inspection of the checked-in tests and source.
