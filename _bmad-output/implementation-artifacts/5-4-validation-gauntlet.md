# Story 5.4: Validation Gauntlet

Status: ready-for-dev

## Story

As the operator,
I want optimized candidates run through an independent validation gauntlet — walk-forward, CPCV, parameter perturbation, Monte Carlo, and regime analysis — each producing reviewable artifacts,
so that I can distinguish genuinely robust strategies from overfit ones.

## Acceptance Criteria

1. **Walk-Forward Validation (FR29)**
   - **Given** a promoted candidate from Story 5.3's optimization output
   - **When** walk-forward validation runs with rolling windows sized per Brief 5C research for forex M1 data
   - **Then** train-past/test-future temporal ordering is enforced, purge/embargo gaps prevent train-test leakage, and per-window metrics are produced as Arrow IPC artifact + human-readable summary
   - **Clarification:** This is fixed-candidate rolling OOS evaluation (candidate parameters are held constant across all windows), NOT walk-forward re-optimization. It serves as an independent temporal validation layer distinct from the CV-inside-objective used during optimization (Story 5.3).

2. **CPCV Configuration (FR30)**
   - **Given** a promoted candidate requiring cross-validation
   - **When** Combinatorial Purged Cross-Validation runs with research-determined N groups, k test groups, purge/embargo sizing
   - **Then** PBO (Probability of Backtest Overfitting) is computed, per-combination results are produced, and PBO > 0.40 triggers hard RED gate per D11

3. **CPCV Results Artifact (D2, FR39)**
   - **Given** CPCV has completed
   - **Then** Arrow IPC artifact contains per-combination results with summary metrics, and a human-readable summary is generated for evidence pack consumption by Story 5.5

4. **Parameter Perturbation (FR31)**
   - **Given** a candidate's parameter vector
   - **When** perturbation analysis runs at +/-5%, +/-10%, +/-20% of parameter ranges
   - **Then** each perturbed variant is re-evaluated via Rust dispatcher, and a sensitivity artifact shows performance impact per parameter per perturbation level (integer/categorical parameters use scaled-equivalent perturbation)

5. **Monte Carlo Simulation (FR32)**
   - **Given** a candidate's trade results from walk-forward evaluation
   - **When** Monte Carlo simulation runs bootstrap (resample with replacement), permutation (shuffle returns), and stress testing (widen spreads/slippage to 1.5x, 2x, 3x cost model)
   - **Then** distribution artifacts show confidence intervals for key metrics, and stress-test results show survival under adverse cost conditions

6. **Regime Analysis (FR33)**
   - **Given** a candidate's trade results and market data
   - **When** regime analysis runs
   - **Then** performance is broken down across volatility terciles crossed with forex sessions (asian, london, new_york, london_ny_overlap), with minimum trade count thresholds per bucket for statistical validity, and empty/insufficient buckets are flagged rather than fabricated
   - **V1 scope note:** FR33 describes "trending, ranging, volatile, quiet". V1 implements the volatility × session cross-tabulation as a tractable proxy. Full trend/range regime classification (requiring HMM or similar) is deferred to Growth phase. The V1 model captures session-dependent behavior and volatility sensitivity, which are the most actionable regime dimensions for a single-pair forex strategy.

7. **Gauntlet Artifact Pipeline (FR39)**
   - **Given** any validation stage completes
   - **Then** that stage produces Arrow IPC artifact with structured results AND a human-readable markdown summary, both persisted via crash-safe write pattern

8. **Optimized Stage Order (FR41-aware)**
   - **Given** a candidate entering the gauntlet
   - **When** the gauntlet orchestrator sequences validation stages
   - **Then** stages run cheapest-first: perturbation -> walk-forward -> CPCV -> Monte Carlo -> regime, with short-circuit logic limited to **validity failures only** (PBO hard gate, DSR hard gate) — performance-based metrics (e.g., negative OOS Sharpe) are recorded but do NOT short-circuit, preserving full evidence generation per FR41

9. **Suspicious Performance Flagging (FR35)**
   - **Given** a candidate with both in-sample and out-of-sample results
   - **When** in-sample performance significantly exceeds out-of-sample performance
   - **Then** the candidate is automatically flagged with quantified divergence metrics (ratio of IS to OOS Sharpe, IS to OOS profit factor)

10. **DSR Mandatory (D11)**
    - **Given** a validation run with >10 evaluated candidates
    - **When** Deflated Sharpe Ratio is computed
    - **Then** DSR accounts for multiple testing bias across **all candidates explored during optimization** (total trial count from Story 5.3 optimization manifest, not just promoted candidates), and DSR failure is a hard gate preventing promotion

11. **Gauntlet Checkpointing (NFR5)**
    - **Given** a gauntlet run is interrupted mid-execution
    - **When** the run resumes
    - **Then** it resumes from the last completed stage per candidate (no rerun of expensive stages), using crash-safe checkpoint files

12. **Visualization Data (FR36, FR37)**
    - **Given** validation completes
    - **Then** in-sample vs out-of-sample vs forward-test periods are marked with temporal split timestamps, and walk-forward window individual results are available for per-window visualization

13. **Deterministic Results (FR18)**
    - **Given** the same candidate + same data + same config + same RNG seeds
    - **When** the gauntlet runs twice
    - **Then** results are identical (all stochastic components seeded deterministically)

## Tasks / Subtasks

- [ ] **Task 1: Extend pipeline state machine with VALIDATING stages** (AC: #7, #8, #11)
  - [ ] Add `VALIDATING = "validating"` and `VALIDATION_COMPLETE = "validation-complete"` to `PipelineStage` enum in `src/python/orchestrator/pipeline_state.py`
  - [ ] Add transitions: `OPTIMIZATION_COMPLETE -> VALIDATING` (automatic), `VALIDATING -> VALIDATION_COMPLETE` (automatic), `VALIDATION_COMPLETE -> next_stage` (gated)
  - [ ] Update `STAGE_ORDER` list and `STAGE_GRAPH` dict
  - [ ] Update `gated_stages` default to include validation-complete
  - [ ] Test: `test_pipeline_state_validating_stages()` — verify new stages in order and transitions work

- [ ] **Task 2: Create validation configuration schema** (AC: #1, #2, #4, #5, #6, #8)
  - [ ] Add `[validation]` section to `config/base.toml` with subsections:
    ```toml
    [validation]
    stage_order = ["perturbation", "walk_forward", "cpcv", "monte_carlo", "regime"]
    short_circuit_on_validity_failure = true  # Only PBO/DSR hard gates, NOT performance metrics (FR41)
    checkpoint_interval = 1  # checkpoint after each stage per candidate
    deterministic_seed_base = 42

    [validation.walk_forward]
    n_windows = 5           # Brief 5C: 5-10 for forex M1
    train_ratio = 0.80
    purge_bars = 1440       # 1 day of M1 bars
    embargo_bars = 720      # 12 hours of M1 bars

    [validation.cpcv]
    n_groups = 10           # Brief 5C recommendation
    k_test_groups = 3       # Brief 5C recommendation
    purge_bars = 1440
    embargo_bars = 720
    pbo_red_threshold = 0.40  # D11 hard gate

    [validation.perturbation]
    levels = [0.05, 0.10, 0.20]  # +/- 5%, 10%, 20%
    min_performance_retention = 0.70  # flag if <70% of base performance

    [validation.monte_carlo]
    n_bootstrap = 1000
    n_permutation = 1000
    stress_multipliers = [1.5, 2.0, 3.0]
    confidence_level = 0.95

    [validation.regime]
    volatility_quantiles = [0.333, 0.667]  # terciles
    min_trades_per_bucket = 30
    sessions = ["asian", "london", "new_york", "london_ny_overlap"]

    [validation.dsr]
    significance_level = 0.05
    ```
  - [ ] Add schema validation in `config/schema.toml`
  - [ ] Create `src/python/validation/config.py` with typed dataclasses: `ValidationConfig`, `WalkForwardConfig`, `CPCVConfig`, `PerturbationConfig`, `MonteCarloConfig`, `RegimeConfig`, `DSRConfig`
    - `ValidationConfig.from_dict(config: dict) -> ValidationConfig`
  - [ ] Test: `test_validation_config_loads()`, `test_validation_config_defaults()`

- [ ] **Task 3: Implement walk-forward validator** (AC: #1, #12, #13)
  - [ ] Create `src/python/validation/walk_forward.py`
  - [ ] Function: `generate_walk_forward_windows(data_length: int, config: WalkForwardConfig) -> list[WindowSpec]` — computes train/test boundaries with purge/embargo
  - [ ] Dataclass: `WindowSpec(train_start: int, train_end: int, test_start: int, test_end: int, purge_start: int, purge_end: int, window_id: int)`
  - [ ] Function: `run_walk_forward(candidate: dict, market_data_path: Path, strategy_spec: dict, cost_model: dict, config: WalkForwardConfig, dispatcher: BatchDispatcher, seed: int) -> WalkForwardResult`
    - Dispatches each window's test segment to Rust evaluator via `dispatcher` (reuse Story 5.3's `batch_dispatch.py` `BatchDispatcher`)
    - Enforces temporal ordering: train window is ALWAYS before test window
    - Returns per-window metrics (Sharpe, PF, drawdown, trade count) + aggregate
  - [ ] Dataclass: `WalkForwardResult(windows: list[WindowResult], aggregate_sharpe: float, aggregate_pf: float, is_oos_divergence: float, artifact_path: Path)`
  - [ ] Suspicious performance flagging: compute IS vs OOS ratio per AC #9
  - [ ] Test: `test_walk_forward_window_generation()`, `test_walk_forward_purge_embargo()`, `test_walk_forward_temporal_ordering()`, `test_walk_forward_deterministic()`

- [ ] **Task 4: Implement CPCV validator** (AC: #2, #3, #10)
  - [ ] Create `src/python/validation/cpcv.py`
  - [ ] Function: `generate_cpcv_combinations(n_groups: int, k_test: int) -> list[tuple[list[int], list[int]]]` — generates all C(n, k) train/test group combinations
  - [ ] Function: `run_cpcv(candidate: dict, market_data_path: Path, strategy_spec: dict, cost_model: dict, config: CPCVConfig, dispatcher: BatchDispatcher, seed: int) -> CPCVResult`
    - Dispatches each combination to Rust evaluator
    - Applies purge/embargo between adjacent train/test groups
    - Computes PBO from distribution of OOS returns across all combinations
  - [ ] Function: `compute_pbo(oos_returns: list[float], is_returns: list[float]) -> float` — Probability of Backtest Overfitting per Bailey et al.
  - [ ] Dataclass: `CPCVResult(combinations: list[CombinationResult], pbo: float, pbo_gate_passed: bool, mean_oos_sharpe: float, artifact_path: Path)`
  - [ ] PBO > 0.40 = hard RED gate (D11)
  - [ ] Test: `test_cpcv_combination_count()`, `test_cpcv_purge_application()`, `test_pbo_computation()`, `test_cpcv_red_gate_threshold()`

- [ ] **Task 5: Implement parameter perturbation analyzer** (AC: #4, #13)
  - [ ] Create `src/python/validation/perturbation.py`
  - [ ] Function: `generate_perturbations(candidate: dict, param_ranges: dict, levels: list[float]) -> list[dict]` — creates perturbed variants for each parameter at each level
    - Continuous params: multiply range by level, add/subtract
    - Integer params: round to nearest int after perturbation
    - Categorical params: skip (not perturbable) or cycle to adjacent values
    - Conditional params: perturb only within active branch
  - [ ] Function: `run_perturbation(candidate: dict, market_data_path: Path, strategy_spec: dict, cost_model: dict, config: PerturbationConfig, dispatcher: BatchDispatcher, seed: int) -> PerturbationResult`
    - Batch-dispatches all perturbed variants to Rust evaluator
    - Computes sensitivity: `(metric_perturbed - metric_base) / metric_base` per param per level
  - [ ] Dataclass: `PerturbationResult(sensitivities: dict[str, dict[float, float]], max_sensitivity: float, fragile_params: list[str], artifact_path: Path)`
  - [ ] Flag parameters where small perturbation (5%) causes >30% performance drop
  - [ ] Test: `test_perturbation_generation()`, `test_perturbation_integer_rounding()`, `test_perturbation_sensitivity_calc()`, `test_perturbation_deterministic()`

- [ ] **Task 6: Implement Monte Carlo simulator** (AC: #5, #13)
  - [ ] Create `src/python/validation/monte_carlo.py`
  - [ ] Function: `run_monte_carlo(trade_results: pa.Table, equity_curve: pa.Table, cost_model: dict, config: MonteCarloConfig, seed: int) -> MonteCarloResult`
    - **Input:** trade results from walk-forward OOS windows (walk-forward runs FIRST and produces per-window trade tables; Monte Carlo resamples from these OOS trades)
    - **Bootstrap**: resample trade sequence with replacement N times, rebuild equity curves, compute confidence intervals for Sharpe, max drawdown, net PnL
    - **Permutation**: shuffle trade returns N times, test if observed Sharpe exceeds random (p-value)
    - **Stress test**: re-evaluate with widened spreads/slippage at 1.5x, 2x, 3x multipliers via cost model adjustment (NO Rust dispatch — recalculate PnL from existing trade entry/exit prices with inflated costs)
  - [ ] Function: `bootstrap_equity_curves(trades: pa.Table, n_samples: int, rng: np.random.Generator) -> BootstrapResult`
  - [ ] Function: `permutation_test(returns: np.ndarray, observed_sharpe: float, n_permutations: int, rng: np.random.Generator) -> PermutationResult`
  - [ ] Function: `stress_test_costs(trades: pa.Table, multipliers: list[float], cost_model: dict) -> StressResult`
  - [ ] Dataclass: `MonteCarloResult(bootstrap: BootstrapResult, permutation: PermutationResult, stress: StressResult, artifact_path: Path)`
  - [ ] NOTE: Monte Carlo is Python-only — operates on trade results, NO Rust dispatch needed
  - [ ] Test: `test_bootstrap_confidence_intervals()`, `test_permutation_pvalue()`, `test_stress_cost_multipliers()`, `test_monte_carlo_deterministic()`

- [ ] **Task 7: Implement regime analyzer** (AC: #6)
  - [ ] Create `src/python/validation/regime_analysis.py`
  - [ ] Function: `classify_regimes(market_data: pa.Table, config: RegimeConfig) -> pa.Table` — adds volatility_tercile and session columns, computes ATR-based volatility classification
  - [ ] Function: `run_regime_analysis(trade_results: pa.Table, market_data: pa.Table, config: RegimeConfig) -> RegimeResult`
    - Cross-tabulate: volatility tercile x session
    - Compute per-bucket: trade count, win rate, avg PnL, Sharpe, PF
    - Flag buckets with trade count < `min_trades_per_bucket` as statistically insufficient
  - [ ] Dataclass: `RegimeResult(buckets: list[RegimeBucket], sufficient_buckets: int, total_buckets: int, weakest_regime: str, artifact_path: Path)`
  - [ ] Dataclass: `RegimeBucket(volatility: str, session: str, trade_count: int, win_rate: float, avg_pnl: float, sharpe: float, sufficient: bool)`
  - [ ] NOTE: Regime analysis is Python-only — operates on trade results + market data
  - [ ] Test: `test_regime_classification()`, `test_regime_min_trade_threshold()`, `test_regime_cross_tabulation()`, `test_regime_insufficient_bucket_flagging()`

- [ ] **Task 8: Implement DSR calculator** (AC: #10)
  - [ ] Create `src/python/validation/dsr.py`
  - [ ] Function: `compute_dsr(observed_sharpe: float, num_trials: int, sharpe_variance: float, skewness: float, kurtosis: float) -> DSRResult` — implements Bailey & Lopez de Prado Deflated Sharpe Ratio
  - [ ] Function: `compute_expected_max_sharpe(num_trials: int, sharpe_std: float, skew: float, kurt: float) -> float` — E[max(SR)] under multiple testing
  - [ ] Dataclass: `DSRResult(dsr: float, p_value: float, passed: bool, num_trials: int, expected_max_sharpe: float)`
  - [ ] `num_trials` MUST be sourced from Story 5.3's optimization manifest (total candidates explored during optimization, not just promoted ones) — DSR corrects for the full multiple-testing universe
  - [ ] DSR failure = hard gate (same weight as PBO gate per D11)
  - [ ] Only computed when >10 candidates evaluated (AC #10 condition)
  - [ ] Test: `test_dsr_known_values()`, `test_dsr_multiple_testing_correction()`, `test_dsr_threshold()`

- [ ] **Task 9: Implement gauntlet orchestrator with checkpointing** (AC: #7, #8, #9, #11, #12, #13)
  - [ ] Create `src/python/validation/gauntlet.py`
  - [ ] Class: `ValidationGauntlet`
    ```python
    class ValidationGauntlet:
        def __init__(self, config: ValidationConfig, dispatcher: BatchDispatcher):
            ...

        def run(
            self,
            candidates: list[dict],
            market_data_path: Path,
            strategy_spec: dict,
            cost_model: dict,
            optimization_manifest: dict,
        ) -> GauntletResults:
            """Run all candidates through validation stages in configured order."""

        def resume(self, checkpoint_path: Path) -> GauntletResults:
            """Resume interrupted gauntlet from last checkpoint."""

        def _run_stage(
            self, stage_name: str, candidate: dict, context: GauntletContext
        ) -> StageOutput:
            """Dispatch to appropriate validator based on stage name."""

        def _should_short_circuit(
            self, candidate_id: int, completed_stages: dict[str, StageOutput]
        ) -> bool:
            """Check if candidate has failed validity gates (PBO, DSR). Performance-based metrics do NOT trigger short-circuit per FR41."""

        def _checkpoint(self, state: GauntletState) -> None:
            """Persist gauntlet state via crash_safe_write_json."""
    ```
  - [ ] Dataclass: `GauntletState(candidates_progress: dict[int, dict[str, str]], completed_results: dict, rng_state: dict, run_id: str)`
  - [ ] Dataclass: `GauntletResults(candidates: list[CandidateValidation], dsr: DSRResult | None, run_manifest: dict)`
  - [ ] Dataclass: `CandidateValidation(candidate_id: int, stages: dict[str, Any], short_circuited: bool, hard_gate_failures: list[str], is_oos_divergence: float)`
  - [ ] Stage order from config (default: perturbation -> walk_forward -> cpcv -> monte_carlo -> regime)
  - [ ] Short-circuit on validity gates ONLY (FR41 compliance): if PBO > 0.40 after CPCV, skip Monte Carlo + regime (hard RED gate)
  - [ ] Negative OOS Sharpe is RECORDED as a warning flag but does NOT short-circuit — full evidence generation is preserved per FR41
  - [ ] Checkpoint after each (candidate, stage) pair completes
  - [ ] DSR computed once after all candidates complete walk-forward (needs cross-candidate statistics)
  - [ ] Deterministic seeding: `seed = config.deterministic_seed_base + candidate_id * 1000 + stage_index`
  - [ ] Test: `test_gauntlet_stage_ordering()`, `test_gauntlet_short_circuit()`, `test_gauntlet_checkpoint_resume()`, `test_gauntlet_deterministic_seeding()`

- [ ] **Task 10: Implement validation results writer** (AC: #7, #12)
  - [ ] Create `src/python/validation/results.py`
  - [ ] Function: `write_stage_artifact(stage_name: str, result: Any, output_dir: Path) -> Path` — writes Arrow IPC artifact per stage using `crash_safe_write_bytes` from `artifacts.storage`
  - [ ] Function: `write_stage_summary(stage_name: str, result: Any, output_dir: Path) -> Path` — writes human-readable markdown summary per stage
  - [ ] Function: `write_gauntlet_manifest(results: GauntletResults, optimization_manifest: dict, output_dir: Path) -> Path` — writes JSON manifest linking all artifacts with: dataset_hash, strategy_spec_hash, config_hash, validation_config_hash, optimization_run_id, total_optimization_trials, candidate_ranks, per_stage_metric_ids, gate_results, chart_data_refs, research_brief_versions (see Downstream Contract section)
  - [ ] Add validation Arrow schemas to `contracts/arrow_schemas.toml`:
    - `[walk_forward_results]`: window_id, train_start, train_end, test_start, test_end, oos_sharpe, oos_pf, oos_drawdown, oos_trades, oos_pnl
    - `[cpcv_results]`: combination_id, train_groups, test_groups, oos_sharpe, oos_pf, oos_pnl
    - `[perturbation_results]`: param_name, perturbation_level, base_metric, perturbed_metric, sensitivity
    - `[monte_carlo_results]`: simulation_type, iteration, metric_name, metric_value
    - `[regime_results]`: volatility_tercile, session, trade_count, win_rate, avg_pnl, sharpe, sufficient
    - `[validation_summary]`: candidate_id, walk_forward_sharpe, pbo, dsr, perturbation_max_sensitivity, mc_bootstrap_ci_lower, mc_stress_survived, regime_weakest_sharpe, hard_gate_failures, short_circuited
  - [ ] Test: `test_stage_artifact_roundtrip()`, `test_gauntlet_manifest_completeness()`, `test_arrow_schema_compliance()`

- [ ] **Task 11: Implement ValidationExecutor (StageExecutor protocol)** (AC: #7, #8, #11)
  - [ ] Create `src/python/validation/executor.py`
  - [ ] Class: `ValidationExecutor` implementing `StageExecutor` protocol from `orchestrator.stage_runner`
    ```python
    class ValidationExecutor:
        """StageExecutor for the VALIDATING pipeline stage.

        Implements the StageExecutor protocol from Story 3-3:
        - execute(strategy_id, context) -> StageResult
        - validate_artifact(artifact_path, manifest_ref) -> bool
        """

        def __init__(self, config: dict):
            self._config = ValidationConfig.from_dict(config)

        def execute(self, strategy_id: str, context: dict) -> StageResult:
            """Load promoted candidates from context, run gauntlet, write results."""

        def validate_artifact(self, artifact_path: Path, manifest_ref: Path) -> bool:
            """Verify validation artifacts via manifest hash."""
    ```
  - [ ] `context` dict expected keys: `optimization_artifact_path`, `market_data_path`, `strategy_spec`, `cost_model`, `config`
  - [ ] Register `ValidationExecutor` for `PipelineStage.VALIDATING` in pipeline executor registry
  - [ ] Test: `test_validation_executor_protocol()`, `test_validation_executor_e2e()`

- [ ] **Task 12: Write integration tests** (AC: #1-#13)
  - [ ] Create `tests/test_validation/test_e2e_validation.py`
  - [ ] `test_e2e_single_candidate_full_gauntlet()` — one candidate through all 5 stages, verify all artifacts produced
  - [ ] `test_e2e_short_circuit_on_pbo_failure()` — candidate with PBO > 0.40 skips Monte Carlo + regime
  - [ ] `test_e2e_gauntlet_resume_after_interrupt()` — simulate crash after walk-forward, verify resume skips completed stages
  - [ ] `test_e2e_deterministic_reproducibility()` — same inputs twice produce identical outputs
  - [ ] `test_e2e_dsr_gate_with_multiple_candidates()` — 15+ candidates, verify DSR computed and applied
  - [ ] `test_e2e_suspicious_performance_flagging()` — candidate with IS >> OOS gets flagged
  - [ ] Use mock Rust dispatcher returning synthetic but realistic trade results (same pattern as Story 5.3 tests)
  - [ ] Fixtures: `conftest.py` with `mock_dispatcher`, `sample_candidate`, `sample_market_data`, `sample_cost_model`

- [ ] **Task 13: Update dependencies** (AC: all)
  - [ ] Add to `src/python/pyproject.toml`: `scipy>=1.11` (for `scipy.stats.norm.cdf` in DSR, `scipy.special.comb` in CPCV combination generation), `pyarrow` (already present)
  - [ ] Verify `numpy` already available (required for Monte Carlo `np.random.Generator(PCG64)`, perturbation, regime analysis)
  - [ ] No new Rust crate changes — validation dispatches to existing Rust evaluator via Story 5.3's BatchDispatcher

## Dev Notes

### Architecture Constraints

- **D1 (System Topology):** Walk-forward, CPCV, and perturbation stages dispatch evaluations to the Rust evaluator via Story 5.3's `BatchDispatcher` (`src/python/optimization/batch_dispatch.py` once Story 5.3 is implemented). Monte Carlo, regime analysis, and DSR are Python-only computations operating on trade results.
- **Architecture Reconciliation Note:** The Requirements-to-Structure mapping in the architecture assigns FR29-FR33 to `crates/validator/` as a Rust binary. This story implements Python gauntlet orchestration + Rust evaluation kernels (via BatchDispatcher), which is architecturally consistent with D1's "Python orchestrates, Rust computes" model but does NOT create a separate `crates/validator/` binary. The existing Rust evaluator binary handles all compute-heavy evaluation; the Python gauntlet handles orchestration, statistical analysis, and artifact assembly. If this design is confirmed during implementation, the architecture's Requirements-to-Structure mapping should be updated to reflect that validation reuses the existing evaluator binary rather than creating a new `forex_validator` binary.
- **D2 (Storage):** All artifacts written as Arrow IPC via `crash_safe_write_bytes` from `artifacts.storage`. Human-readable summaries as markdown. Manifests as JSON via `crash_safe_write_json`.
- **D3 (Pipeline Orchestration):** Validation is a distinct pipeline stage (VALIDATING). The gauntlet orchestrator manages its own internal complexity (stage ordering, short-circuit, checkpointing) — the pipeline state machine only sees VALIDATING -> VALIDATION_COMPLETE.
- **D6 (Logging):** Structured JSON logging via `logging_setup.setup.get_logger()`. Log: stage start/complete, candidate progress, gate pass/fail, short-circuit decisions, checkpoint saves.
- **D11 (AI Analysis Layer):** DSR is mandatory for >10 candidates. PBO <= 0.40 is a hard RED gate. Every metric must be traceable to a specific computation. Evidence pack consumption is Story 5.5's responsibility — this story produces the raw validation artifacts.
- **NFR4 (Memory):** Validation operates on one candidate at a time through stages. Walk-forward windows are sequential, not parallel. Monte Carlo bootstrap streams results, does not hold all N iterations in memory. Target: validation adds <500MB to base memory budget.
- **NFR5 (Checkpointing):** Gauntlet checkpoint after each (candidate, stage) pair. Crash-safe write pattern: `.partial` -> `flush` -> `fsync` -> `os.replace`.
- **FR18 (Determinism):** All stochastic components (Monte Carlo bootstrap, permutation) use deterministic seeding. Seed formula: `base_seed + candidate_id * 1000 + stage_index`. Same inputs = identical outputs.

### Downstream Contract (Story 5.5 Interface)

Story 5.5 (Confidence Scoring & Evidence Packs) consumes 5.4's output. The gauntlet manifest (Task 10) MUST include:

| Field | Source | Why 5.5 Needs It |
|-------|--------|-------------------|
| `optimization_run_id` | Story 5.3 manifest | Lineage tracing back to optimization |
| `total_optimization_trials` | Story 5.3 manifest | DSR context for evidence narrative |
| `candidate_rank` | Story 5.3 promoted list | Composite score weighting |
| `per_stage_metric_ids` | Each validator output | Cited references in evidence narrative |
| `gate_results` | Gauntlet orchestrator | Hard gate pass/fail for RED/YELLOW/GREEN |
| `chart_data_refs` | Arrow IPC artifact paths | Chart-ready data for visualization |
| `config_hash` | Validation config | Reproducibility proof |
| `research_brief_versions` | Config provenance | Traceability to research decisions |

Story 5.5 should be a pure aggregation/presentation layer — it should NOT need to recompute any selection-level statistics. If 5.5 finds itself recomputing, that is a signal this contract is incomplete.

### Rust Dispatch vs Python-Only Stages

| Stage | Needs Rust? | Why |
|-------|-------------|-----|
| Walk-forward | YES | Re-evaluates candidate on each window's test segment |
| CPCV | YES | Re-evaluates candidate on each group combination |
| Perturbation | YES | Re-evaluates perturbed parameter variants |
| Monte Carlo | NO | Resamples/permutes existing trade results |
| Regime | NO | Analyzes existing trade results by market condition |
| DSR | NO | Pure statistical computation |

### Key Data Flow

```
Story 5.3 output (optimization_candidates Arrow IPC + promoted_candidates)
    |
    v
ValidationExecutor.execute() loads promoted candidates
    |
    v
ValidationGauntlet.run() iterates candidates x stages
    |
    +-- perturbation.run_perturbation() -> Arrow IPC + summary
    +-- walk_forward.run_walk_forward() -> Arrow IPC + summary
    +-- cpcv.run_cpcv() -> Arrow IPC + summary + PBO gate check
    +-- monte_carlo.run_monte_carlo() -> Arrow IPC + summary
    +-- regime.run_regime_analysis() -> Arrow IPC + summary
    |
    v (after all candidates complete walk-forward)
    +-- dsr.compute_dsr() -> DSR gate check
    |
    v
GauntletResults -> validation_summary Arrow IPC + gauntlet manifest JSON
    |
    v
Story 5.5 consumes for confidence scoring + evidence packs
```

### Short-Circuit Logic (FR41-Compliant)

Short-circuiting is limited to **validity failures**, not performance-based metrics. FR41 requires any strategy (profitable or not) to progress through the full pipeline. The gauntlet respects this by generating complete evidence even for underperforming candidates.

1. **After perturbation:** If max sensitivity > configurable threshold (default: performance drops >50% at 5% perturbation), flag but continue (soft warning, not gate)
2. **After walk-forward:** Negative OOS Sharpe is recorded as a warning flag but does NOT short-circuit — all remaining stages still run to produce complete evidence
3. **After CPCV:** If PBO > 0.40, short-circuit — skip Monte Carlo, regime (hard RED gate per D11 — this is a validity failure, not a profitability gate)
4. Short-circuit on validity failures saves compute while still recording the failure reason in the candidate's validation record
5. **Rationale:** V1 centers on evidence quality and reproducibility. A candidate with negative Sharpe still produces valuable evidence about the pipeline's analytical capabilities and helps the operator understand what "the pipeline works correctly" means independently of "this strategy is profitable."

### Performance Considerations

- Walk-forward dispatches N windows (default 5) to Rust — each window is a full backtest evaluation
- CPCV dispatches C(n,k) combinations (C(10,3) = 120 combinations) — significant compute
- Perturbation dispatches `n_params * 2 * n_levels` evaluations (e.g., 20 params * 2 * 3 = 120 evaluations)
- Monte Carlo is Python-only: 1000 bootstrap + 1000 permutation iterations per candidate — fast
- Regime analysis is Python-only: single pass over trade results — fast
- Total Rust dispatches per candidate: ~5 (WF) + ~120 (CPCV) + ~120 (perturbation) = ~245 evaluations
- Batch dispatching: group all perturbation variants into single batch, all CPCV combinations into single batch

### Windows Compatibility

- Use `pathlib.Path` for all paths (handles / on Windows)
- Strip `\r` from any Rust evaluator output (line ending compatibility)
- Use venv Python (not conda)
- `os.replace()` for atomic file moves (works on Windows with same-volume)
- Avoid `((x++))` in any bash helper scripts — use explicit increments

### What to Reuse from ClaudeBackTester

**Adapt (review patterns, implement fresh to match new architecture):**
- `walk_forward.py` — ClaudeBackTester has walk-forward logic; adapt window generation and purge/embargo patterns but implement fresh with Rust dispatch integration
- `monte_carlo.py` — ClaudeBackTester has bootstrap and permutation; adapt statistical methodology but implement fresh with Arrow IPC output
- Confidence scoring formula — extracted in Story 5.1; gauntlet produces raw data, Story 5.5 applies scoring

**Do NOT Carry Forward:**
- Any 5-stage parameter locking assumptions
- Aggregated score patterns (use per-fold/per-window granular results)
- Any fixed parameter grouping logic
- Any non-deterministic random state management

### What to Reuse from Existing Codebase

| Component | Location | How to Reuse |
|-----------|----------|-------------|
| `crash_safe_write` | `src/python/artifacts/storage.py` | Direct import for checkpoint + artifact writes |
| `crash_safe_write_bytes` | `src/python/artifacts/storage.py` | Direct import for Arrow IPC writes |
| `crash_safe_write_json` | `src/python/artifacts/storage.py` | Direct import for manifest writes |
| `StageExecutor` protocol | `src/python/orchestrator/stage_runner.py` | Implement for `ValidationExecutor` |
| `StageResult` dataclass | `src/python/orchestrator/stage_runner.py` | Return type from executor |
| `PipelineStage` enum | `src/python/orchestrator/pipeline_state.py` | Extend with VALIDATING stages |
| `get_logger` | `src/python/logging_setup/setup.py` | Import for structured JSON logging |
| `BatchDispatcher` | `src/python/optimization/batch_dispatch.py` | Import from Story 5.3 for Rust dispatch (walk-forward, CPCV, perturbation) |
| Arrow schemas | `contracts/arrow_schemas.toml` | Extend with validation schemas |
| `compute_config_hash` | `src/python/config_loader/__init__.py` | Import for manifest hash computation |
| `ResultExecutor` pattern | `src/python/rust_bridge/result_executor.py` | Reference pattern for executor implementation |

### Anti-Patterns to Avoid

1. **Profitability gating disguised as validation gates:** Short-circuiting on negative OOS Sharpe, low profit factor, or similar performance metrics violates FR41. Only validity failures (PBO hard gate, DSR hard gate) justify short-circuit. Negative performance is a finding, not a stop condition.
2. **DSR on promoted subset only:** DSR must use total optimization trial count from Story 5.3 manifest. Computing DSR only over the 5-10 promoted candidates dramatically understates the multiple-testing correction. The whole point is correcting for having explored hundreds/thousands of candidates during optimization.
3. **Calling fixed-candidate OOS evaluation "walk-forward optimization":** This story evaluates a fixed parameter set across rolling windows. It is NOT re-optimizing per window. Documentation and variable names must reflect this distinction to avoid misleading the operator.
4. **Python-side trade simulation approximations:** The stress test (Monte Carlo Task 6) recalculates PnL from existing trades with inflated costs. This is correct — it answers "would these trades survive higher costs?" It does NOT re-run the strategy through Rust, which would produce different trades entirely.
5. **Anomaly threshold ownership leakage:** This story emits deterministic raw metrics. Story 5.5 / D11 own the interpretation layer (surfaced flags, narrative claims, anomaly thresholds). Do not embed threshold-based narrative logic in the validators themselves.
| `BacktestExecutor` pattern | `src/python/rust_bridge/backtest_executor.py` | Reference pattern for Rust dispatch integration |

### Anti-Patterns to Avoid

1. **Do NOT re-implement batch dispatch** — reuse Story 5.3's `BatchDispatcher` for all Rust evaluations
2. **Do NOT aggregate per-window results prematurely** — keep granular per-window/per-combination data for Story 5.5 evidence packs
3. **Do NOT hold all Monte Carlo iterations in memory** — stream bootstrap results, compute running statistics
4. **Do NOT skip purge/embargo gaps** — data leakage between train/test invalidates all walk-forward and CPCV results
5. **Do NOT hardcode PBO threshold** — load from config (default 0.40 per D11)
6. **Do NOT compute DSR per-candidate** — DSR is a cross-candidate correction for multiple testing; compute once after all candidates
7. **Do NOT fabricate regime buckets with insufficient trades** — flag as "insufficient" with actual trade count, not fake metrics
8. **Do NOT implement confidence scoring** — that is Story 5.5's responsibility; this story produces raw validation artifacts
9. **Do NOT use non-deterministic random** — every stochastic component must accept explicit seed; use `np.random.Generator(np.random.PCG64(seed))`
10. **Do NOT checkpoint with pickle** — use JSON for checkpoint state (crash-safe, human-readable, debuggable)
11. **Do NOT assume single candidate** — gauntlet processes multiple promoted candidates from Story 5.3
12. **Do NOT skip short-circuit logging** — when a candidate is short-circuited, log exactly which gate failed and at which stage

### Project Structure Notes

**New files to create:**
```
src/python/validation/
    __init__.py
    config.py               # Task 2: Configuration dataclasses
    walk_forward.py          # Task 3: Walk-forward validator
    cpcv.py                  # Task 4: CPCV validator + PBO
    perturbation.py          # Task 5: Parameter perturbation
    monte_carlo.py           # Task 6: Monte Carlo simulator
    regime_analysis.py       # Task 7: Regime analyzer
    dsr.py                   # Task 8: Deflated Sharpe Ratio
    gauntlet.py              # Task 9: Gauntlet orchestrator
    results.py               # Task 10: Results writer
    executor.py              # Task 11: StageExecutor

tests/test_validation/
    __init__.py
    conftest.py              # Shared fixtures
    test_config.py           # Task 2 tests
    test_walk_forward.py     # Task 3 tests
    test_cpcv.py             # Task 4 tests
    test_perturbation.py     # Task 5 tests
    test_monte_carlo.py      # Task 6 tests
    test_regime_analysis.py  # Task 7 tests
    test_dsr.py              # Task 8 tests
    test_gauntlet.py         # Task 9 tests
    test_results.py          # Task 10 tests
    test_executor.py         # Task 11 tests
    test_e2e_validation.py   # Task 12 integration tests
```

**Files to modify:**
```
src/python/orchestrator/pipeline_state.py   # Task 1: Add VALIDATING + VALIDATION_COMPLETE
config/base.toml                             # Task 2: Add [validation] section
config/schema.toml                           # Task 2: Add validation schema
contracts/arrow_schemas.toml                 # Task 10: Add validation schemas
src/python/pyproject.toml                    # Task 13: Add scipy dependency
```

### References

- [Source: _bmad-output/planning-artifacts/architecture.md — D1 System Topology (fold-aware batch evaluation)]
- [Source: _bmad-output/planning-artifacts/architecture.md — D2 Storage (Arrow IPC artifacts)]
- [Source: _bmad-output/planning-artifacts/architecture.md — D3 Pipeline Orchestration (opaque optimizer, stage transitions)]
- [Source: _bmad-output/planning-artifacts/architecture.md — D6 Logging (structured JSON)]
- [Source: _bmad-output/planning-artifacts/architecture.md — D11 AI Analysis Layer (DSR mandatory, PBO gate, evidence packs)]
- [Source: _bmad-output/planning-artifacts/architecture.md — NFR4 Memory Budget (~5.5GB peak)]
- [Source: _bmad-output/planning-artifacts/architecture.md — NFR5 Checkpointing]
- [Source: _bmad-output/planning-artifacts/prd.md — FR29-FR33 (validation stages)]
- [Source: _bmad-output/planning-artifacts/prd.md — FR34-FR37 (confidence + visualization)]
- [Source: _bmad-output/planning-artifacts/prd.md — FR18 (deterministic results)]
- [Source: _bmad-output/planning-artifacts/prd.md — FR39 (evidence packs)]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 5 Story 5.4 (acceptance criteria)]
- [Source: _bmad-output/planning-artifacts/research/briefs/5C/ — Validation gauntlet configuration]
- [Source: _bmad-output/planning-artifacts/research/briefs/5A/ — CV-objective interaction with walk-forward]
- [Source: _bmad-output/planning-artifacts/research/briefs/3B/ — Deterministic backtesting & validation methodology]
- [Source: _bmad-output/planning-artifacts/research/briefs/3C/ — Results analysis, anomaly detection, evidence packs]
- [Source: _bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md — BatchDispatcher, checkpoint patterns]
- [Source: src/python/orchestrator/stage_runner.py — StageExecutor protocol]
- [Source: src/python/orchestrator/pipeline_state.py — PipelineStage enum, STAGE_GRAPH]
- [Source: src/python/artifacts/storage.py — crash_safe_write, crash_safe_write_bytes, crash_safe_write_json]
- [Source: contracts/arrow_schemas.toml — existing schemas for market_data, backtest_trades, optimization_candidates]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### Change Log

### File List
