# Story 5.3: Python Optimization Orchestrator

Status: review

## Story

As the **operator**,
I want a Python optimization orchestrator that manages a portfolio of algorithm instances via ask/tell, dispatches batch evaluations to the Rust evaluator with CV-inside-objective fold management, and tracks candidates with checkpointing,
So that optimization runs are robust, resumable, and exploit the full batch throughput of the Rust evaluator — with a configurable portfolio that adapts to parameter count for Growth-phase scalability.

## Acceptance Criteria

1. **Given** a strategy specification and market data exist from Epic 2 and Epic 1
   **When** an optimization run is started via the pipeline
   **Then** the orchestrator initializes a portfolio of algorithm instances: CMA-ES (CatCMAwM) via `cmaes` library + DE (TwoPointsDE) via Nevergrad, filling the configured batch capacity per generation (D3, FR23). Batch size (default 2048) and portfolio composition are config-driven, not hardcoded
   [Ref: D3 opaque optimizer contract, FR23, Brief 5A algorithm selection]

2. **Given** the strategy specification defines parameters with the D10 taxonomy
   **When** the orchestrator parses the parameter space
   **Then** it handles continuous, integer, categorical, and conditional parameters — without mandated staging or grouping (FR23, FR24 research update)
   [Ref: D10 parameter taxonomy, contracts/strategy_specification.toml]

3. **Given** algorithm instances have been initialized
   **When** each generation executes
   **Then** it follows ask/tell: ask N candidates from all instances → dispatch batch to Rust evaluator via the Epic 3 bridge (D1) → receive per-fold scores → tell scores back to each instance
   [Ref: D1 fold-aware batch evaluation, existing BatchRunner in rust_bridge/batch_runner.py]

4. **Given** a candidate batch is dispatched for evaluation
   **When** fold-aware CV scoring is computed
   **Then** each candidate is evaluated across K folds, producing score = mean - lambda * std where lambda is configurable (default ~1.0-2.0 per optimization research)
   [Ref: CV-inside-objective framework from optimization research, Brief 5A]

5. **Given** fold boundaries are defined for the dataset
   **When** the orchestrator dispatches a batch to Rust
   **Then** fold boundaries are passed as part of the batch dispatch, enabling fold-aware evaluation without duplicating data (D1 fold-aware batch evaluation)
   [Ref: D1, existing BacktestJob dataclass in rust_bridge/batch_runner.py]

6. **Given** the strategy has N parameters
   **When** population sizing is computed
   **Then** `pop = max(128, 5 * N_params)` as baseline, with BIPOP/IPOP restart strategy for multi-basin exploration. Instance count adjusts inversely (fewer instances with larger populations for high-D spaces)
   [Ref: Brief 5A population sizing, FR23]

7. **Given** optimization is running with noisy CV objectives
   **When** convergence is checked
   **Then** relaxed tolerances (tolfun >= 1e-3) are used, with stagnation detection triggering restarts rather than premature termination
   [Ref: Brief 5A convergence detection]

8. **Given** optimization is in progress
   **When** the configurable checkpoint interval is reached
   **Then** optimizer state (all instance populations, generation count, best candidates) is persisted using crash-safe write pattern (.partial → fsync → os.replace) (NFR5, NFR15)
   [Ref: existing crash_safe_write in data_pipeline/utils/safe_write.py and artifacts/storage.py]

9. **Given** an optimization run was interrupted
   **When** the operator resumes
   **Then** it resumes from the last checkpoint without data loss (FR42)
   [Ref: existing recovery.py pattern in orchestrator/recovery.py]

10. **Given** the orchestrator is running algorithm instances
    **When** exploration coverage is assessed
    **Then** a quasi-random sampling component (Sobol/Halton) runs alongside algorithm instances to ensure exploration of unexplored regions
    [Ref: Brief 5A quasi-random exploration recommendation]

11. **Given** the system has a configurable memory budget
    **When** optimization is about to start
    **Then** a preflight budget check validates the planned run (batch size × candidate size × fold count) fits in available memory minus OS reserve; if not, batch size is reduced automatically before starting — not mid-run (NFR4). During execution, bounded worker pools and streaming-to-disk results prevent accumulation (NFR1-NFR4)
    [Ref: NFR4 deterministic memory budgeting, existing memory check pattern in BatchRunner]

12. **Given** optimization is progressing through generations
    **When** logging is emitted
    **Then** structured JSON logging (D6) includes: generation number, best score, population diversity metrics, instance-level status
    [Ref: D6, existing get_logger() + JsonFormatter in logging_setup/setup.py]

13. **Given** optimization completes or is stopped
    **When** results are written
    **Then** all evaluated candidates with per-fold scores, objective values, and parameter vectors are written as Arrow IPC artifacts (D2, FR25), accompanied by a run manifest containing: dataset_hash, strategy_spec_hash, config_hash, fold_definitions, RNG seeds per instance, stop_reason, generation_count, and branch metadata
    [Ref: D2, existing safe_write_arrow_ipc in data_pipeline/utils/safe_write.py, Story 5.7 provenance requirements]

14. **Given** a strategy has conditional parameters (e.g., exit_type branches)
    **When** the orchestrator handles branching
    **Then** branch decomposition splits the search into separate sub-portfolios per branch, with batch budget allocated proportionally or via UCB1 multi-armed bandit
    [Ref: D10 conditional parameters, FR24]

15. **Given** optimization has completed
    **When** candidate promotion is performed
    **Then** top-N candidates by objective score are written as a promoted-candidates artifact with stable candidate IDs, intended as input for Story 5.4 validation gauntlet — V1 simple promotion without advanced clustering (Growth-phase FR26-FR28 deferred)
    [Ref: FR25 MVP optimization core, FR26-FR28 Growth-phase, Story 5.4 downstream contract]

16. **Given** optimization runs or resumes
    **When** RNG seeds are initialized or restored
    **Then** each algorithm instance uses a deterministic seed derived from a run-level master seed + instance index, persisted in checkpoints and recorded in the run manifest, so that identical inputs + identical seed produce identical candidate sequences
    [Ref: FR18 reproducibility, NFR5 checkpointing]

## Tasks / Subtasks

- [x] **Task 1: Extend pipeline state machine for OPTIMIZING stages** (AC: #1, #3)
  - [x]Add new `PipelineStage` enum values to `src/python/orchestrator/pipeline_state.py`:
    - `OPTIMIZING = "optimizing"` (active optimization)
    - `OPTIMIZATION_COMPLETE = "optimization-complete"` (gated — results ready for operator/validation)
  - [x]Add `StageTransition` entries to `STAGE_GRAPH`:
    - `REVIEWED → OPTIMIZING` (automatic, precondition: review approved + strategy spec + data exist)
    - `OPTIMIZING → OPTIMIZATION_COMPLETE` (automatic, precondition: optimization finished or budget exhausted)
  - [x]Update `STAGE_ORDER` list to include new stages in correct position
  - [x]Pipeline state stores only: current stage, artifact directory path, status summary (start time, generation count, best score). Optimizer-internal state (populations, instance states, generation details) stays in optimizer's own checkpoint files per D3
  - [x]**DO NOT** add optimizer-internal fields to `contracts/pipeline_checkpoint.toml` — optimizer owns its own checkpoint format

- [x] **Task 2: Create optimization configuration schema** (AC: #1, #6, #7, #11)
  - [x]Add `[optimization]` section to `config/base.toml`:
    ```toml
    [optimization]
    batch_size = 2048
    max_generations = 500
    checkpoint_interval_generations = 10
    cv_lambda = 1.5
    cv_folds = 5
    convergence_tolfun = 1e-3
    stagnation_generations = 50
    memory_budget_mb = 5632  # ~5.5GB per NFR4 data volume modeling; preflight reduces batch if insufficient
    sobol_fraction = 0.1
    ucb1_exploration = 1.414
    ```
  - [x]Add `[optimization.portfolio]` subsection:
    ```toml
    [optimization.portfolio]
    cmaes_instances = 10
    de_instances = 3
    cmaes_pop_base = 128
    de_pop_base = 150
    pop_scaling_factor = 5
    min_pop = 128
    ```
  - [x]Add `config/schema.toml` validation entries for all new fields
  - [x]Ensure `config_loader/loader.py` picks up new section via existing layered TOML mechanism
  - [x]Write test: `test_optimization_config_loads_defaults` — verify base.toml defaults parse correctly
  - [x]Write test: `test_optimization_config_env_override` — verify environment overlay works

- [x] **Task 3: Implement parameter space parser** (AC: #2, #14)
  - [x]Create `src/python/optimization/__init__.py`
  - [x]Create `src/python/optimization/parameter_space.py`:
    - `class ParameterSpec` — dataclass: name, type (continuous/integer/categorical/conditional), bounds, choices, conditions
    - `class ParameterSpace` — container for all parameters with dimensionality tracking
    - `def parse_strategy_params(strategy_spec: dict) -> ParameterSpace` — parse from strategy specification TOML
    - `def detect_branches(space: ParameterSpace) -> dict[str, ParameterSpace]` — identify conditional parameter branches (e.g., exit_type splits), return sub-spaces per branch
    - `def to_cmaes_bounds(space: ParameterSpace) -> tuple[np.ndarray, np.ndarray]` — convert to cmaes library format
    - `def to_nevergrad_params(space: ParameterSpace) -> ng.p.Instrumentation` — convert to Nevergrad parametrization
  - [x]Handle D10 full taxonomy: continuous (float bounds), integer (int bounds), categorical (choice list), conditional (parent parameter value → child params)
  - [x]Write test: `test_parse_continuous_params` — verify float parameter extraction from strategy TOML
  - [x]Write test: `test_parse_mixed_params` — verify mixed continuous/integer/categorical handling
  - [x]Write test: `test_detect_branches_exit_type` — verify conditional branching on exit_type
  - [x]Write test: `test_to_cmaes_bounds_shape` — verify bounds array dimensions match param count

- [x] **Task 4: Implement algorithm portfolio manager** (AC: #1, #6, #7, #10)
  - [x]Create `src/python/optimization/portfolio.py`:
    - `class AlgorithmInstance` — protocol/ABC: `ask(n: int) -> np.ndarray`, `tell(candidates: np.ndarray, scores: np.ndarray) -> None`, `converged() -> bool`, `state_dict() -> dict`, `load_state(state: dict) -> None`
    - `class CMAESInstance(AlgorithmInstance)` — wraps `cmaes.CatCMA` or `cmaes.CMAwM`: BIPOP/IPOP restart logic, noise-robust tolerances (tolfun >= 1e-3), stagnation detection
    - `class DEInstance(AlgorithmInstance)` — wraps Nevergrad `TwoPointsDE`: ask/tell adapter
    - `class SobolExplorer(AlgorithmInstance)` — quasi-random Sobol/Halton sampling via `scipy.stats.qmc`
    - `class PortfolioManager` — manages all instances:
      - `__init__(space: ParameterSpace, config: dict)` — compute population sizes from `max(128, 5 * N_params)`, allocate instances, scale instance count inversely with dimensionality
      - `ask_batch(batch_size: int) -> list[np.ndarray]` — collect candidates from all instances up to batch_size, allocate sobol_fraction to explorer
      - `tell_batch(candidates: list[np.ndarray], scores: np.ndarray) -> None` — route scores back to originating instances
      - `check_convergence() -> bool` — all instances converged or stagnated (with restart logic)
      - `state_dict() / load_state()` — full portfolio serialization for checkpointing
  - [x]Write test: `test_portfolio_ask_batch_fills_capacity` — verify batch_size candidates returned
  - [x]Write test: `test_portfolio_tell_routes_scores` — verify scores reach correct instances
  - [x]Write test: `test_population_scaling_with_params` — verify pop formula `max(128, 5*N)`
  - [x]Write test: `test_cmaes_restart_on_stagnation` — verify BIPOP restart triggers
  - [x]Write test: `test_sobol_fraction_allocation` — verify quasi-random fraction of batch

- [x] **Task 5: Implement branch portfolio orchestration** (AC: #14)
  - [x]Create `src/python/optimization/branch_manager.py`:
    - `class BranchPortfolio` — one PortfolioManager per branch
    - `class BranchManager`:
      - `__init__(branches: dict[str, ParameterSpace], config: dict)` — create sub-portfolio per branch
      - `allocate_budget(total_batch: int) -> dict[str, int]` — proportional or UCB1 allocation
      - `ask_all(total_batch: int) -> dict[str, list[np.ndarray]]` — ask from each branch
      - `tell_all(branch_results: dict[str, tuple[list[np.ndarray], np.ndarray]]) -> None` — tell per branch
      - UCB1 tracking: per-branch mean score + visit count, `exploration_weight` from config
      - `state_dict() / load_state()` — branch-level checkpointing
  - [x]If no conditional params detected, BranchManager wraps single branch transparently
  - [x]Write test: `test_branch_ucb1_shifts_budget` — verify budget shifts toward better-scoring branch
  - [x]Write test: `test_single_branch_passthrough` — verify no-branch case works seamlessly
  - [x]Write test: `test_branch_state_roundtrip` — verify checkpoint save/load preserves UCB1 state

- [x] **Task 6: Implement CV-inside-objective fold manager** (AC: #4, #5)
  - [x]Create `src/python/optimization/fold_manager.py`:
    - `class FoldSpec` — dataclass: fold_id, train_start, train_end, test_start, test_end, embargo_bars
    - `class FoldManager`:
      - `__init__(data_length: int, n_folds: int, embargo_bars: int)` — compute fold boundaries (time-series aware, non-shuffled)
      - `get_fold_boundaries() -> list[FoldSpec]` — return all fold definitions
      - `to_rust_fold_args() -> list[dict]` — format for Rust evaluator batch dispatch (fold boundaries as bar indices)
    - `def compute_cv_objective(fold_scores: np.ndarray, lambda_: float) -> float` — mean - lambda * std aggregation
  - [x]Fold boundaries must respect temporal ordering (no future data leakage)
  - [x]Embargo gap between train/test to prevent lookback contamination
  - [x]Write test: `test_fold_boundaries_no_overlap` — verify folds don't overlap
  - [x]Write test: `test_fold_embargo_gap` — verify embargo bars between train/test
  - [x]Write test: `test_cv_objective_penalizes_variance` — verify higher std → lower score
  - [x]Write test: `test_fold_to_rust_format` — verify output matches Rust evaluator expected input

- [x] **Task 7: Implement batch dispatch adapter for optimization** (AC: #3, #5, #11)
  - [x]Create `src/python/optimization/batch_dispatch.py`:
    - `class OptimizationBatchDispatcher`:
      - `__init__(batch_runner: BatchRunner, artifacts_dir: Path, config: dict)` — wraps existing `BatchRunner` from `rust_bridge/batch_runner.py`
      - `async dispatch_generation(candidates: list[np.ndarray], fold_specs: list[FoldSpec], strategy_spec_path: Path, market_data_path: Path, cost_model_path: Path) -> np.ndarray` — for each fold: write candidates as Arrow IPC → dispatch to Rust → collect per-fold results → return score matrix (candidates × folds)
      - Memory check before dispatch using existing `_get_available_memory_mb()` pattern
      - Progress reporting via existing `ProgressReport` pattern
    - Arrow IPC write for candidate batches: use `safe_write_arrow_ipc` from `data_pipeline/utils/safe_write.py`
    - Arrow IPC read for results: use `pyarrow.ipc.open_file` to read Rust output
  - [x]Reuse `BacktestJob` dataclass — extend with fold boundary fields if needed, or add fold metadata as separate Arrow IPC file alongside market data
  - [x]Write test: `test_dispatch_creates_arrow_input` — verify candidate batch written as Arrow IPC
  - [x]Write test: `test_dispatch_reads_fold_results` — verify per-fold score matrix shape
  - [x]Write test: `test_dispatch_memory_check` — verify memory guard before dispatch (mock)

- [x] **Task 8: Implement optimization checkpoint manager** (AC: #8, #9)
  - [x]Create `src/python/optimization/checkpoint.py`:
    - `class OptimizationCheckpoint` — dataclass: generation, branch_states (dict), portfolio_states (dict), best_candidates (list), evaluated_count, elapsed_time, config_hash
    - `def save_checkpoint(checkpoint: OptimizationCheckpoint, path: Path) -> None` — serialize to JSON using `crash_safe_write` from artifacts/storage.py
    - `def load_checkpoint(path: Path) -> OptimizationCheckpoint` — deserialize with version migration
    - `def should_checkpoint(generation: int, interval: int) -> bool` — simple modulo check
  - [x]Checkpoint includes all algorithm instance states (CMA-ES populations, DE states, Sobol index)
  - [x]Follow existing `.partial` → `fsync` → `os.replace` pattern from `artifacts/storage.py`
  - [x]Write test: `test_checkpoint_roundtrip` — save then load, verify all fields match
  - [x]Write test: `test_checkpoint_crash_safe` — verify .partial file is cleaned up
  - [x]Write test: `test_checkpoint_resume_generation` — verify optimization resumes at correct generation

- [x] **Task 9: Implement main optimization orchestrator** (AC: #1-#16)
  - [x]Create `src/python/optimization/orchestrator.py`:
    - `class OptimizationOrchestrator`:
      - `__init__(strategy_spec: dict, market_data_path: Path, cost_model_path: Path, config: dict, artifacts_dir: Path, batch_runner: BatchRunner)`
      - `async run(resume_from: Path | None = None) -> OptimizationResult` — main loop:
        1. Parse parameter space (Task 3)
        2. Detect branches, create BranchManager or single PortfolioManager (Task 4-5)
        3. Create FoldManager (Task 6)
        4. If resuming: load checkpoint, restore states
        5. Generation loop:
           a. `branch_manager.ask_all(batch_size)` → candidate batches per branch
           b. For each branch: `dispatcher.dispatch_generation(...)` → fold score matrices
           c. Compute CV objectives: `compute_cv_objective(fold_scores, lambda_)` per candidate
           d. `branch_manager.tell_all(...)` → feed scores back
           e. Log progress (D6 structured JSON)
           f. Checkpoint if interval reached (Task 8)
           g. Check convergence → break if all converged
        6. Write final results as Arrow IPC (Task 10)
        7. Simple candidate promotion: top-N by objective score
      - `def get_progress() -> dict` — current generation, best score, instance statuses
    - Generation journal: before dispatching a batch, write generation_id + candidate_ids to journal; after tell completes, mark journal entry done. On resume, replay incomplete journal entries to avoid duplicate or lost evaluations
    - `class OptimizationResult` — dataclass: best_candidates (list), all_candidates_path (Path to Arrow IPC), run_manifest_path (Path to JSON manifest), generations_run (int), total_evaluations (int), convergence_reached (bool), stop_reason (str)
  - [x]Wire into pipeline state machine as `StageExecutor` for OPTIMIZING stage
  - [x]Write test: `test_orchestrator_runs_one_generation` — mock dispatcher, verify ask/tell/checkpoint flow
  - [x]Write test: `test_orchestrator_resume_from_checkpoint` — verify generation counter continues
  - [x]Write test: `test_orchestrator_convergence_stops` — verify loop exits on convergence
  - [x]Write test: `test_orchestrator_writes_final_results` — verify Arrow IPC output exists

- [x] **Task 10: Implement results writer, run manifest, and candidate promotion** (AC: #13, #15, #16)
  - [x]Create `src/python/optimization/results.py`:
    - `class StreamingResultsWriter` — append-mode Arrow IPC writer: opens file at optimization start, appends per-generation results incrementally, finalizes on completion. Never accumulates all candidates in memory
      - `append_generation(generation: int, candidates: list[np.ndarray], fold_scores: np.ndarray, cv_objectives: np.ndarray, branch: str, instance_types: list[str]) -> None`
      - `finalize() -> Path` — flush, close, return path
      - Arrow IPC schema: candidate_id (uint64, stable monotonic), parameter_values (binary/struct), fold_scores (list[float64]), cv_objective (float64), generation (uint32), branch (utf8), instance_type (utf8)
    - `def write_run_manifest(artifacts_dir: Path, dataset_hash: str, strategy_spec_hash: str, config_hash: str, fold_definitions: list[dict], rng_seeds: dict, stop_reason: str, generation_count: int, branch_metadata: dict) -> Path` — crash-safe JSON manifest for downstream provenance (Story 5.7)
    - `def promote_top_candidates(results_path: Path, top_n: int = 20) -> Path` — read Arrow IPC, sort by cv_objective descending, write top-N as separate promoted-candidates Arrow IPC with stable candidate IDs for Story 5.4 intake
    - Use `safe_write_arrow_ipc` from `data_pipeline/utils/safe_write.py`
  - [x]Add Arrow schema definition to `contracts/arrow_schemas.toml` for optimization_candidates and promoted_candidates tables
  - [x]Write test: `test_results_arrow_schema_matches_contract` — verify written schema matches contract
  - [x]Write test: `test_streaming_writer_incremental` — verify file grows per generation without memory accumulation
  - [x]Write test: `test_promote_top_n_ordering` — verify correct ordering and count
  - [x]Write test: `test_run_manifest_contains_provenance` — verify all required provenance fields present

- [x] **Task 11: Register optimization executor with stage runner** (AC: #1, #3)
  - [x]Create `src/python/optimization/executor.py`:
    - `class OptimizationExecutor` — implements `StageExecutor` protocol from `orchestrator/stage_runner.py`:
      - `def execute(state: PipelineState, artifacts_dir: Path, config: dict) -> PipelineState` — instantiate OptimizationOrchestrator, call `run()`, update state with results path
      - Handle resume: check for existing checkpoint, pass to `run(resume_from=...)`
      - `def verify_artifact(artifacts_dir: Path) -> bool` — verify optimization results Arrow IPC exists and is readable
  - [x]Register executor in stage runner initialization (follow pattern from Epic 3 executors)
  - [x]Write test: `test_executor_implements_protocol` — verify StageExecutor protocol compliance
  - [x]Write test: `test_executor_resume_detects_checkpoint` — verify checkpoint detection

- [x] **Task 12: Integration tests** (AC: #1-#15)
  - [x]Create `tests/test_optimization/` directory with `__init__.py` and `conftest.py`
  - [x]`conftest.py`: fixtures for mock strategy spec, small market data Arrow IPC, mock cost model, temp artifacts directory
  - [x]Write test: `test_e2e_optimization_small_space` — 2-3 continuous params, 2 folds, 5 generations, verify full pipeline produces Arrow IPC results
  - [x]Write test: `test_e2e_optimization_with_branches` — conditional params, verify branch decomposition works end-to-end
  - [x]Write test: `test_e2e_checkpoint_resume` — run 3 generations, save checkpoint, resume, run 2 more, verify continuity
  - [x]Write test: `test_pipeline_state_transitions` — verify REVIEWED → OPTIMIZING → OPTIMIZATION_COMPLETE transitions
  - [x]Write test: `test_deterministic_seeds_reproduce` — same master seed + inputs → identical candidate sequences
  - [x]Write test: `test_generation_journal_crash_recovery` — simulate crash between ask and tell, verify no duplicate/lost evaluations on resume

- [x] **Task 13: Add Python dependencies** (AC: #1)
  - [x]Add to `src/python/pyproject.toml`:
    - `cmaes >= 0.10.0` — CMA-ES with CatCMA/CMAwM support
    - `nevergrad >= 1.0.0` — DE (TwoPointsDE) ask/tell interface
    - `scipy >= 1.11.0` — Sobol/Halton quasi-random via `scipy.stats.qmc`
    - `numpy` — already present (verify version compatibility)
    - `pyarrow` — already present
  - [x]Verify no dependency conflicts with existing packages
  - [x]Write test: `test_imports_optimization_deps` — verify all new deps importable

## Dev Notes

### Requirement Traceability Notes

- **FR13/FR24 wording tension:** The original PRD says "strategies can define their own optimization stages and parameter groupings" (FR13). The March 2026 research update on FR23/FR24 clarifies that the optimizer handles grouping automatically — the operator does not choose staging. This story follows the research update, which is the authoritative interpretation. The architecture (D3, D10) explicitly supports this: optimization is opaque to the state machine, and fixed staging is not mandated.
- **FR25 scope split:** FR25 covers both optimization artifact generation AND chart-led visualization. This story handles artifact generation (Arrow IPC results + run manifest). Chart-led visualization and evidence pack assembly are Story 5.5's responsibility via D11's analysis layer. This is deliberate scope separation, not an omission.
- **D3 stage model:** D3 shows `→ OPTIMIZING → OPTIMIZATION_COMPLETE (gated) →`. This story adds exactly those two stages. `OPTIMIZATION_READY` was removed as it adds a state D3 doesn't define and violates the "opaque optimizer" principle. The optimizer owns its internal checkpoint files; pipeline state stores only stage + artifact refs + summary metrics.

### Architecture Constraints

- **D1 (System Topology):** Python orchestrator spawns Rust binary via subprocess. All data exchange via Arrow IPC files. No PyO3/FFI. Fold-aware batch evaluation: pass fold boundaries, receive per-fold scores. The existing `BatchRunner` in `rust_bridge/batch_runner.py` uses `asyncio.create_subprocess_exec` — the optimization dispatcher must use the same pattern.
- **D3 (Pipeline Orchestration):** Optimization is opaque to state machine — single `OPTIMIZING` state externally, orchestrator manages internal complexity. Contract: Input (strategy spec, data, cost model, fold boundaries, budget) → Output (ranked candidates as Arrow IPC). Optimizer manages own checkpoints independently of pipeline checkpoint.
- **D6 (Logging):** Structured JSON via `get_logger("optimization.xxx")` from `logging_setup/setup.py`. Schema: `{ts, level, runtime, component, stage, strategy_id, msg, ctx}`.
- **D10 (Parameter Taxonomy):** Full taxonomy support: continuous, integer, categorical, conditional. No mandated staging or grouping (FR24 revision). The strategy specification in `contracts/strategy_specification.toml` defines parameter types.
- **NFR1-NFR4 (Performance):** 80%+ CPU sustained via batch dispatch to Rust. Memory budget ~5.5GB peak. Bounded pools. Stream results to disk, don't accumulate.
- **NFR5/NFR15 (Checkpointing):** Crash-safe write pattern: `.partial` → `flush` → `fsync` → `os.replace`. Use existing `crash_safe_write` from `artifacts/storage.py`.
- **FR42 (Resumability):** Interrupted runs resume from checkpoint. Follow existing `recovery.py` pattern.

### Critical Integration Points

1. **Rust Bridge** (`src/python/rust_bridge/batch_runner.py`):
   - `BacktestJob` dataclass: strategy_spec_path, market_data_path, cost_model_path, output_directory, config_hash, memory_budget_mb
   - `BatchRunner.run(job: BacktestJob) -> BatchResult` — async, spawns Rust binary
   - Must extend `BacktestJob` or create parallel `OptimizationJob` with fold boundary fields
   - Memory pre-check pattern: `_get_available_memory_mb()` minus 2GB OS reserve

2. **Pipeline State Machine** (`src/python/orchestrator/pipeline_state.py`):
   - Current stages: DATA_READY → STRATEGY_READY → BACKTEST_RUNNING → BACKTEST_COMPLETE → REVIEW_PENDING → REVIEWED
   - Must add: REVIEWED → OPTIMIZING → OPTIMIZATION_COMPLETE (per D3 — two stages only, no OPTIMIZATION_READY)
   - Pipeline state stores only: stage, artifact directory path, summary metrics (start time, generation count, best score). Optimizer manages its own internal checkpoint files
   - `PipelineState.save()` uses `crash_safe_write` already

3. **Stage Runner** (`src/python/orchestrator/stage_runner.py`):
   - `StageExecutor` protocol: `execute(state, artifacts_dir, config) -> PipelineState`
   - Register `OptimizationExecutor` following same pattern as Epic 3 executors
   - `GateManager.check_preconditions()` validates stage transitions

4. **Artifacts** (`src/python/data_pipeline/utils/safe_write.py`):
   - `safe_write_arrow_ipc(table, output_path)` — crash-safe Arrow IPC write
   - `crash_safe_write(path, content)` — crash-safe text write
   - Both use .partial → fsync → os.replace pattern

5. **Config** (`config/base.toml` via `config_loader/loader.py`):
   - Layered: base.toml → environments/local.toml → environments/vps.toml
   - `compute_config_hash()` used for reproducibility tracking

### Algorithm Selection (from Brief 5A + Codex Review)

- **Primary:** CMA-ES via `cmaes` library (CatCMAwM variant for mixed parameters)
  - 10 instances (default), pop=128 base, BIPOP/IPOP restarts
  - Noise-robust: LRA-CMA-ES, tolfun >= 1e-3
- **Secondary:** DE via Nevergrad (`TwoPointsDE`)
  - 3 instances (default), pop=150 base
- **Explorer:** Sobol quasi-random via `scipy.stats.qmc`
  - 10% of batch budget (sobol_fraction config)
- **Rejected:** Optuna (ask/tell not batch-native), NGOpt/Shiwa as primary (validated by Codex review — too general-purpose)
- **Batch allocation:** 2048 total slots per generation distributed across all instances + Sobol explorer

### CV-Inside-Objective Framework

- Each candidate evaluated K folds (default 5)
- Score = mean(fold_scores) - lambda * std(fold_scores)
- Lambda configurable (default 1.5, range 1.0-2.0)
- Fold boundaries: time-series splits, no shuffle, embargo gap = max_lookback + max_holding_period
- Fold boundaries passed to Rust evaluator as bar index ranges

### Conditional Parameter Branching

- Top-level categoricals (e.g., exit_type = {trailing_stop, take_profit, time_exit}) split search into sub-portfolios
- Each branch gets independent PortfolioManager with own instances
- Batch budget allocated via UCB1 multi-armed bandit (shift toward promising branches) or proportional (configurable)
- If no conditional parameters, single-branch passthrough (no overhead)

### Performance Considerations

- Batch dispatch is I/O bound (Arrow IPC write → Rust subprocess → Arrow IPC read)
- Python orchestrator is lightweight — CPU work is in Rust evaluator
- Keep candidate tracking in memory bounded: stream evaluated results to Arrow IPC incrementally
- Memory monitoring: check available memory before each Rust dispatch

### What to Reuse from Existing Codebase

| Module | What to Reuse | How |
|--------|--------------|-----|
| `rust_bridge/batch_runner.py` | `BatchRunner`, `BacktestJob`, `BatchResult`, `ProgressReport` | Wrap in `OptimizationBatchDispatcher`. Extend `BacktestJob` for fold boundaries or create sibling dataclass |
| `orchestrator/pipeline_state.py` | `PipelineStage`, `STAGE_GRAPH`, `WithinStageCheckpoint`, `PipelineState` | Extend enum and graph. Use `WithinStageCheckpoint` for generation progress |
| `orchestrator/stage_runner.py` | `StageExecutor` protocol, `StageRunner`, `PipelineConfig` | Implement protocol. Register new executor |
| `orchestrator/recovery.py` | `recover_from_checkpoint`, `startup_cleanup`, `verify_last_artifact` | Follow patterns for optimization checkpoint recovery |
| `data_pipeline/utils/safe_write.py` | `safe_write_arrow_ipc`, `crash_safe_write` | Use directly for all optimization artifact writes |
| `artifacts/storage.py` | `crash_safe_write`, `crash_safe_write_bytes` | Use for checkpoint persistence |
| `logging_setup/setup.py` | `get_logger`, `LogContext` | Use `get_logger("optimization.xxx")` for all optimization modules |
| `config_loader/loader.py` | Layered TOML loading, `compute_config_hash` | Config picked up automatically from new `[optimization]` section |

### What to Reuse from ClaudeBackTester

- **DO NOT** port the 5-stage parameter locking model — architecture explicitly rejects this (FR24, D10)
- **DO NOT** port the optimizer evaluation mechanism — we use Rust subprocess via Arrow IPC, not in-process Python
- **Conceptual reuse only:** ask/tell loop pattern, population management, convergence detection concepts
- Story 5.1 research will produce a "Compatibility Matrix" and "Do Not Carry Forward" appendix — defer to those findings

### Anti-Patterns to Avoid

1. **DO NOT hardcode batch sizes or population counts** — all must be config-driven via `[optimization]` section in base.toml
2. **DO NOT implement fixed parameter staging/grouping** — FR24 explicitly forbids mandated staging. The optimizer searches the full space jointly
3. **DO NOT use Optuna** — rejected per research (ask/tell not batch-native for our use case)
4. **DO NOT accumulate all results in memory** — stream to Arrow IPC incrementally. The full optimization may produce millions of evaluated candidates
5. **DO NOT duplicate data for each fold** — pass fold boundaries to Rust, not separate data files
6. **DO NOT skip the Sobol/Halton explorer** — ensures coverage even if CMA-ES/DE converge to local optima
7. **DO NOT use synchronous subprocess calls** — the existing BatchRunner uses `asyncio.create_subprocess_exec`; keep async
8. **DO NOT create a new checkpoint format** — follow existing `.partial` → `fsync` → `os.replace` pattern from `artifacts/storage.py`
9. **DO NOT implement clustering or advanced candidate selection** — that's Story 5.6 (Growth-phase). V1 uses simple top-N
10. **DO NOT break the StageExecutor protocol contract** — the optimization executor must implement the same interface as Epic 3 executors
11. **DO NOT use `print()` or Python `logging.basicConfig()`** — use `get_logger()` from `logging_setup/setup.py` (D6)
12. **DO NOT access `pipeline-state.json` directly** — use `PipelineState.load()` / `.save()` methods
13. **DO NOT skip the generation journal** — without it, a crash between ask and tell causes duplicate evaluations on resume, wasting compute and breaking reproducibility
14. **DO NOT generate candidate IDs randomly** — use stable monotonic IDs (run_seed + generation + index) so downstream stories (5.4, 5.7) can trace candidates deterministically
15. **DO NOT put optimizer-internal state in pipeline-state.json** — D3 requires optimizer to own its own checkpoint files; pipeline state stores only stage, artifact paths, and summary metrics

### Windows Compatibility Notes

- Use `Path` objects throughout (not string concatenation)
- Arrow IPC paths: forward slashes in Rust CLI args (existing `batch_runner.py` normalizes paths)
- `os.replace()` is atomic on Windows for same-volume renames (safe_write pattern works)
- `asyncio` subprocess: works on Windows with ProactorEventLoop (default in Python 3.8+)

### Project Structure Notes

New files to create:
```
src/python/optimization/
    __init__.py
    parameter_space.py      # Task 3: Parameter space parser
    portfolio.py            # Task 4: Algorithm portfolio manager
    branch_manager.py       # Task 5: Branch portfolio orchestration
    fold_manager.py         # Task 6: CV fold management
    batch_dispatch.py       # Task 7: Batch dispatch adapter
    checkpoint.py           # Task 8: Checkpoint manager
    orchestrator.py         # Task 9: Main orchestrator
    results.py              # Task 10: Results writer + candidate promotion
    executor.py             # Task 11: StageExecutor implementation

tests/test_optimization/
    __init__.py
    conftest.py             # Shared fixtures
    test_parameter_space.py # Task 3 tests
    test_portfolio.py       # Task 4 tests
    test_branch_manager.py  # Task 5 tests
    test_fold_manager.py    # Task 6 tests
    test_batch_dispatch.py  # Task 7 tests
    test_checkpoint.py      # Task 8 tests
    test_orchestrator.py    # Task 9 tests
    test_results.py         # Task 10 tests
    test_executor.py        # Task 11 tests
    test_e2e_optimization.py # Task 12 integration tests
```

Files to modify:
```
src/python/orchestrator/pipeline_state.py  # Task 1: Add OPTIMIZING + OPTIMIZATION_COMPLETE stages
config/base.toml                            # Task 2: Add [optimization] section
config/schema.toml                          # Task 2: Add validation for optimization config
contracts/arrow_schemas.toml                # Task 10: Add optimization_candidates + promoted_candidates schemas
src/python/pyproject.toml                   # Task 13: Add cmaes, nevergrad, scipy deps
```

### References

- [Source: _bmad-output/planning-artifacts/architecture.md — Decision 1: System Topology]
- [Source: _bmad-output/planning-artifacts/architecture.md — Decision 3: Pipeline Orchestration]
- [Source: _bmad-output/planning-artifacts/architecture.md — Decision 6: Logging]
- [Source: _bmad-output/planning-artifacts/architecture.md — Decision 10: Strategy Execution Model]
- [Source: _bmad-output/planning-artifacts/prd.md — FR23-FR25 Optimization Core]
- [Source: _bmad-output/planning-artifacts/prd.md — FR42 Resumability]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR1-NFR5 Performance and Reliability]
- [Source: _bmad-output/planning-artifacts/research/briefs/5A/ — Algorithm Selection + HuggingFace Review]
- [Source: _bmad-output/planning-artifacts/research/briefs/5A/codex-huggingface-review.md — Codex Validation]
- [Source: _bmad-output/planning-artifacts/research/briefs/5B/ — Candidate Selection (Growth-phase reference)]
- [Source: _bmad-output/planning-artifacts/research/briefs/5C/ — Validation Gauntlet Configuration]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 5 Stories 5.1-5.7]
- [Source: _bmad-output/implementation-artifacts/5-1-claudebacktester-optimizer-validation-pipeline-review.md]
- [Source: _bmad-output/implementation-artifacts/5-2-optimization-algorithm-candidate-selection-validation-gauntlet-research.md]
- [Source: src/python/rust_bridge/batch_runner.py — BatchRunner class]
- [Source: src/python/orchestrator/pipeline_state.py — PipelineStage enum, STAGE_GRAPH]
- [Source: src/python/orchestrator/stage_runner.py — StageExecutor protocol]
- [Source: src/python/data_pipeline/utils/safe_write.py — safe_write_arrow_ipc]
- [Source: src/python/logging_setup/setup.py — get_logger, JsonFormatter]
- [Source: src/python/artifacts/storage.py — crash_safe_write]
- [Source: contracts/strategy_specification.toml — Parameter type definitions]
- [Source: contracts/arrow_schemas.toml — Arrow IPC schema definitions]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Debug Log References
- CMA-ES `tell()` requires exactly `popsize` solutions — fixed by always asking full population from each instance and filling missing scores with -inf
- Existing orchestrator tests required updates for new OPTIMIZATION_COMPLETE terminal stage (3 tests updated)

### Completion Notes List
- Task 1: Extended PipelineStage enum with OPTIMIZING + OPTIMIZATION_COMPLETE, added STAGE_GRAPH transitions REVIEWED→OPTIMIZING→OPTIMIZATION_COMPLETE, updated 3 existing tests
- Task 2: Added [optimization] and [optimization.portfolio] sections to config/base.toml with 16 config keys, all validated in schema.toml
- Task 3: Created parameter_space.py with D10 taxonomy (continuous/integer/categorical/conditional), branch detection, CMA-ES/Nevergrad format conversion, encode/decode helpers
- Task 4: Created portfolio.py with CMAESInstance (BIPOP restart), DEInstance (Nevergrad TwoPointsDE), SobolExplorer (scipy.stats.qmc), PortfolioManager with configurable instance counts and population scaling
- Task 5: Created branch_manager.py with UCB1 budget allocation across conditional parameter branches, single-branch passthrough for non-branching strategies
- Task 6: Created fold_manager.py with time-series aware CV splits, embargo gaps, Rust-format fold boundary export, compute_cv_objective (mean - lambda*std)
- Task 7: Created batch_dispatch.py wrapping BatchRunner for fold-aware candidate dispatch with memory pre-flight checks
- Task 8: Created checkpoint.py with crash-safe JSON checkpointing (.partial→fsync→os.replace) for full optimizer state
- Task 9: Created orchestrator.py with async generation loop: ask→dispatch→CV objective→tell→checkpoint→convergence check
- Task 10: Created results.py with StreamingResultsWriter (incremental Arrow IPC), run manifest with full provenance, top-N candidate promotion
- Task 11: Created executor.py implementing StageExecutor protocol for OPTIMIZING stage with checkpoint resume detection
- Task 12: 56 unit tests + 6 integration tests across 10 test files
- Task 13: Added cmaes>=0.10.0, nevergrad>=1.0.0, scipy>=1.11.0, numpy>=1.24.0 to pyproject.toml
- Live tests: 3 @pytest.mark.live tests exercising full optimization loop, checkpoint resume, and artifact verification

### Change Log
- 2026-03-22: Story 5.3 implemented — all 13 tasks complete, 56 unit + 3 live tests passing, 1183 total tests green

### File List
**New files:**
- src/python/optimization/__init__.py
- src/python/optimization/parameter_space.py
- src/python/optimization/portfolio.py
- src/python/optimization/branch_manager.py
- src/python/optimization/fold_manager.py
- src/python/optimization/batch_dispatch.py
- src/python/optimization/checkpoint.py
- src/python/optimization/orchestrator.py
- src/python/optimization/results.py
- src/python/optimization/executor.py
- src/python/tests/test_optimization/__init__.py
- src/python/tests/test_optimization/conftest.py
- src/python/tests/test_optimization/test_parameter_space.py
- src/python/tests/test_optimization/test_portfolio.py
- src/python/tests/test_optimization/test_branch_manager.py
- src/python/tests/test_optimization/test_fold_manager.py
- src/python/tests/test_optimization/test_batch_dispatch.py
- src/python/tests/test_optimization/test_checkpoint.py
- src/python/tests/test_optimization/test_results.py
- src/python/tests/test_optimization/test_executor.py
- src/python/tests/test_optimization/test_e2e_optimization.py
- src/python/tests/test_optimization/test_live_optimization.py

**Modified files:**
- src/python/orchestrator/pipeline_state.py (added OPTIMIZING + OPTIMIZATION_COMPLETE stages)
- config/base.toml (added [optimization] section)
- config/schema.toml (added optimization validation entries)
- contracts/arrow_schemas.toml (updated optimization_candidates, added promoted_candidates)
- src/python/pyproject.toml (added cmaes, nevergrad, scipy, numpy deps)
- src/python/tests/test_orchestrator/test_pipeline_state.py (updated for new stages)
- src/python/tests/test_orchestrator/test_gate_manager.py (updated terminal stage test)
- src/python/tests/test_orchestrator/test_regression.py (updated progress % test)
