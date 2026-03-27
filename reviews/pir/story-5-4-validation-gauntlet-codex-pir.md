# Story 5-4-validation-gauntlet: Story 5.4: Validation Gauntlet — Codex PIR

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-23
**Type:** Post-Implementation Review (alignment analysis)

---

**1. Objective Alignment**  
Assessment: `CONCERN`

Specific evidence:
- The story is aimed squarely at V1’s trust goals: reproducibility, reviewable evidence, and non-profitability gating ([prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L82), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L99), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L517), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L551))
- The implementation does advance those objectives in isolation: deterministic seeding and ordering are explicit ([gauntlet.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L93), [gauntlet.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L167), [base.toml](/c/Users/ROG/Projects/Forex%20Pipeline/config/base.toml#L131)); hard-gate short-circuiting is limited to validity failures, not profitability ([gauntlet.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L428), [gauntlet.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L322), [gauntlet.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L450)); each realized result can be written as Arrow + markdown ([results.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/results.py#L25), [results.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/results.py#L46)).
- It also fits V1 scope well on regime analysis: the code implements the documented volatility x session proxy, not a larger trend/range classifier ([5-4-validation-gauntlet.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L41), [5-4-validation-gauntlet.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L42), [regime_analysis.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/regime_analysis.py#L81)).

Concrete observations:
- The main problem is that the integrated stage does not actually deliver the full evidence path the objectives require. `ValidationExecutor` calls the gauntlet without `trade_results` or `market_data_table` ([executor.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/executor.py#L64)), so Monte Carlo and regime analysis are skipped by design ([gauntlet.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L351), [gauntlet.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L385)). Because skipped stages have `result=None`, the executor writes no artifact or summary for them ([executor.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/executor.py#L78)). That works directly against artifact completeness and operator confidence.
- The pipeline handoff is also misaligned with the “non-coder drives the workflow” goal. `StageRunner` provides `strategy_spec_path`, `cost_model_path`, and `output_directory` ([stage_runner.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/stage_runner.py#L554)), but `ValidationExecutor` expects in-memory `strategy_spec`, in-memory `cost_model`, `output_dir`, and an `optimization_artifact_path` key the runner never supplies ([executor.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/executor.py#L37), [executor.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/executor.py#L45)).
- Net: the module design is aligned; the stage as actually wired into the system is not yet trustworthy enough for V1’s end-to-end proof.

**2. Simplification**  
Assessment: `ADEQUATE`

Specific evidence:
- The five-stage gauntlet itself is not over-engineered relative to the story; it is the story ([5-4-validation-gauntlet.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L8), [5-4-validation-gauntlet.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L33), [5-4-validation-gauntlet.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L44)).
- Some internal surfaces are broader than what is actually used: `GauntletState.completed_results` and `rng_state` are defined but not meaningfully populated/consumed ([gauntlet.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L50), [gauntlet.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L217), [gauntlet.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L272)).
- The result dataclasses carry `artifact_path` fields, but artifact writing happens externally and I found no assignment into those fields ([walk_forward.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/walk_forward.py#L50), [cpcv.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/cpcv.py#L37), [regime_analysis.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/regime_analysis.py#L38)).
- A `validation_summary` contract exists, but there is no writer for it ([arrow_schemas.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/arrow_schemas.toml#L163), [results.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/results.py#L67)).

Concrete observations:
- I do not think the story is fundamentally over-built for V1. The bigger issue is not “too much gauntlet,” it is “too much scaffolding around a gauntlet that is not fully fed by the real pipeline.”
- A simpler and stronger V1 would have been: fixed stage order, strict validation of stage names, one real promoted-candidate handoff, explicit walk-forward trade-table output, then Monte Carlo/regime consuming that output. That would reduce moving parts while serving the objectives better.

**3. Forward Look**  
Assessment: `CONCERN`

Specific evidence:
- The downstream contract in the story explicitly requires `dataset_hash`, `strategy_spec_hash`, `config_hash`, `validation_config_hash`, candidate ranks, chart refs, and research brief provenance ([5-4-validation-gauntlet.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L254), [5-4-validation-gauntlet.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L319)). The implemented manifest omits `dataset_hash`, `strategy_spec_hash`, and `validation_config_hash` ([results.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/results.py#L132)).
- Optimization-to-validation lineage is weak. Optimization writes `promoted-candidates.arrow` and `run-manifest.json` ([optimization/results.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/optimization/results.py#L163), [optimization/results.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/optimization/results.py#L210)), while validation looks for `promoted_candidates.arrow` and `optimization_manifest.json` ([executor.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/executor.py#L169)). It also discards upstream `candidate_id` and `rank`, loading only `params_json` ([executor.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/executor.py#L178)).
- Monte Carlo is supposed to consume walk-forward OOS trades ([5-4-validation-gauntlet.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-4-validation-gauntlet.md#L172)), but `WalkForwardResult` contains only summary/window metrics, not trade tables ([walk_forward.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/walk_forward.py#L43)). The gauntlet therefore depends on an external `trade_results` injection instead of its own prior stage output ([gauntlet.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L190)).
- The run identity is deterministic, but only from seed base and candidate count ([gauntlet.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/validation/gauntlet.py#L93)); that is not enough lineage once multiple validation runs differ by candidate content, data slice, or spec.

Concrete observations:
- Downstream Story 5.5 will not get a robust lineage chain unless this stage preserves real optimization IDs/ranks and real dataset/spec hashes.
- As the pipeline grows, the current assumption that later validators can be fed ad hoc tables from outside the gauntlet will become brittle. The gauntlet needs its own explicit internal artifact handoff, especially from walk-forward into Monte Carlo/regime.
- The system is close to the right contract shape, but not yet to the right contract substance.

**Overall**  
Assessment: `REVISIT`

The story is directionally aligned and scoped correctly for V1, but the integrated pipeline path does not yet reliably produce the complete, traceable validation evidence that BMAD Backtester’s objectives require. The biggest concerns are incomplete end-to-end handoff, missing lineage fields, and the fact that Monte Carlo/regime are effectively optional in the real executor path rather than guaranteed review artifacts.
