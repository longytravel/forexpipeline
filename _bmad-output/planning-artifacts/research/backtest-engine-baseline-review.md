# Backtest Engine Baseline Review

## Baseline Traceability

| Field | Value |
|---|---|
| **Repository** | `C:\Users\ROG\Projects\ClaudeBackTester` |
| **Branch** | `master` |
| **Commit** | `012ae57` (HEAD; story spec referenced `2084beb` which is 2 commits behind — no backtester-related code changes between them, only CURRENT_TASK.md updates) |
| **Review Date** | 2026-03-18 |
| **Reviewer** | Claude Opus 4.6 (dev-story workflow) |
| **Cross-Reference** | Story 2-1: `strategy-evaluator-baseline-review.md` (indicators, signal generation, exit types, strategy authoring — NOT duplicated here) |

**Line Count Correction:** The story specification listed inflated line counts (e.g., `sampler.py` as 37,531 lines, `runner.py` as 29,022 lines). Actual measured counts are dramatically smaller — the total backtester-related codebase is ~10,074 lines (1,646 Rust + 1,784 Python core + 3,185 optimizer + 3,459 pipeline), not 184K+. The inflated numbers may have been character counts or estimated from an earlier version.

---

## 1. Executive Summary

The ClaudeBackTester baseline is a **Python-first system** (8,428 lines Python) with a **small Rust PyO3 acceleration layer** (1,646 lines) for the hot evaluation loop. This is the most critical finding for the D1 multi-process migration: the "Rust backtester" is actually a 493-line PyO3 extension module, not a standalone binary or full crate.

**Key architectural shifts identified:**

1. **PyO3 in-process → D1 multi-process with Arrow IPC:** The current architecture passes numpy arrays directly to Rust via PyO3 zero-copy views with GIL release + rayon parallelism. The new architecture requires a separate Rust binary process communicating via Arrow IPC. The computation logic (trade simulation, metrics, filtering) transfers cleanly; the data marshalling layer must be completely replaced.

2. **Ad-hoc pipeline runner → D3 explicit state machine:** The current pipeline orchestrator (`runner.py`, 670 lines) is a sequential function with manual checkpoint calls. It has no formal state machine, no gate concept, and no operator approval transitions. The checkpoint system is solid (atomic JSON write-rename) but the orchestration layer needs complete redesign.

3. **Flat cost constants → D13 session-aware cost model:** Cost integration is minimal — three constants (`commission_pips=0.7`, `slippage_pips=0.5`, `max_spread_pips=3.0`) passed as function parameters. The new session-aware cost model crate requires integration at the trade simulation level, replacing these constants with per-bar cost lookups.

4. **Monolithic lib.rs → D14 strategy_engine + backtester separation:** The current `lib.rs` combines PyO3 entry point, parallel dispatch, signal filtering, trade simulation orchestration, and metric computation. For D14, trade simulation logic (`trade_basic.rs`, `trade_full.rs`, `sl_tp.rs`, `metrics.rs`, `filter.rs`, `constants.rs`) can be extracted into a shared `strategy_engine` crate, with `lib.rs` becoming the backtester binary's dispatch layer.

**Critical reuse opportunities:**
- Trade simulation logic (624 lines of clean, stateless Rust) is a direct port candidate
- 10-metric inline computation (241 lines) ports directly to the new backtester crate
- Validation pipeline stages (walk-forward, CPCV, Monte Carlo, regime, stability, confidence — 2,391 lines) are mature and reusable
- Staged optimization model with EDA/Sobol/CMA-ES sampling (1,760 lines) provides a solid foundation
- Checkpoint atomic-write pattern is production-proven

---

## 2. Module Inventory

### Rust Extension (`rust/src/` — 1,646 lines)

| File | Lines | Purpose | Story 2-1 Coverage | Story 3-1 Scope |
|---|---|---|---|---|
| `lib.rs` | 493 | PyO3 entry point: `batch_evaluate()`, rayon parallel dispatch, GIL release, input validation | Referenced | **Deep dive** — PyO3 bridge, parallelism, memory model |
| `constants.rs` | 93 | PL_* parameter layout (64 slots), M_* metric indices, direction/mode/exit codes | Referenced | **Deep dive** — complete layout documentation |
| `metrics.rs` | 241 | 10 inline metrics: trades, win_rate, profit_factor, sharpe, sortino, max_dd, return_pct, r_squared, ulcer, quality | Referenced | **Deep dive** — computation formulas, edge cases |
| `trade_basic.rs` | 188 | Basic SL/TP-only trade simulation with sub-bar resolution | Referenced | **Deep dive** — bar-by-bar loop, sub-bar fill |
| `trade_full.rs` | 435 | Full management: trailing stop, breakeven, partial close, stale exit, max bars | Referenced | **Deep dive** — management feature internals |
| `sl_tp.rs` | 140 | SL/TP computation: fixed pips, ATR-based, swing-based modes | Referenced | **Deep dive** — computation logic |
| `filter.rs` | 56 | Time filtering: hour range (with wrap-around), day bitmask | Referenced | **Deep dive** — filter integration |

### Python Backtester Core (`backtester/core/` — 1,784 lines)

| File | Lines | Purpose | Story 2-1 Coverage | Story 3-1 Scope |
|---|---|---|---|---|
| `engine.py` | 468 | `BacktestEngine` orchestrator: signal precomputation, encoding, Rust dispatch, result extraction | Partially covered (4.3) | **Deep dive** — full lifecycle, data marshalling |
| `encoding.py` | 243 | `EncodingSpec`, `encode_params()`, `decode_params()`: param dict ↔ float64 matrix conversion | Not covered | **Deep dive** — encoding system |
| `rust_loop.py` | 74 | PyO3 wrapper: imports `backtester_core`, exports PL_* constants with Python fallbacks | Referenced | **Moderate** — wrapper mechanics |
| `dtypes.py` | 133 | Mirror constants: direction codes, SL/TP modes, exit reasons, metric indices, signal columns, cost defaults | Referenced | **Moderate** — constant sync model |
| `metrics.py` | 306 | Python fallback metrics: `compute_metrics()`, individual metric functions, quality formula | Referenced | **Deep dive** — Python/Rust parity |
| `telemetry.py` | 559 | `TelemetryEngine`: per-trade Python simulation for debugging, parity verification with Rust | Not covered | **Moderate** — parity model |

### Python Optimizer (`backtester/optimizer/` — 3,185 lines)

| File | Lines | Purpose | Story 2-1 Coverage | Story 3-1 Scope |
|---|---|---|---|---|
| `staged.py` | 792 | `StagedOptimizer`: strategy-defined stages (signal → time → risk → management → refinement), param locking between stages | Not covered | **Moderate** — staged model, transition logic |
| `sampler.py` | 968 | Samplers: `SobolSampler`, `RandomSampler`, `EDASampler`, `CMAESSampler` (lazy), `build_neighborhood()` | Not covered | **Moderate** — sampling strategies |
| `run.py` | 489 | `run_optimization()`: main driver, data loading, engine creation, staged optimizer invocation | Not covered | **Moderate** — orchestration flow |
| `cv_objective.py` | 295 | `CVObjective`: K-fold cross-validation inside optimizer, auto fold configuration, CVaR aggregation | Not covered | **Moderate** — CV mechanics |
| `ranking.py` | 173 | `rank_by_quality()`, `combined_rank()`, `deflated_sharpe_ratio()`, overfitting ratio | Not covered | **Moderate** — ranking model |
| `prefilter.py` | 91 | `prefilter_invalid_combos()`, `postfilter_results()`: invalid param rejection + hard metric gates | Not covered | **Moderate** — filtering logic |
| `archive.py` | 170 | Result archival: CSV/JSON persistence, deduplication, candidate extraction | Not covered | **Moderate** — storage patterns |
| `config.py` | 140 | `OptimizationConfig`: trial counts, batch sizes, thresholds, DSR, cyclic passes | Not covered | **Moderate** — configuration model |
| `progress.py` | 66 | `BatchProgress`, `StageComplete`: progress tracking dataclasses | Not covered | **Gap-level** |

### Python Validation Pipeline (`backtester/pipeline/` — 3,459 lines)

| File | Lines | Purpose | Story 2-1 Coverage | Story 3-1 Scope |
|---|---|---|---|---|
| `runner.py` | 670 | `PipelineRunner`: 7-stage orchestration, checkpoint integration, report generation | Not covered | **Deep dive** — stage sequencing, control flow |
| `walk_forward.py` | 417 | Walk-forward: rolling/anchored windows, windowed evaluation via shared engine | Not covered | **Deep dive** — window generation, OOS evaluation |
| `cpcv.py` | 351 | CPCV: N-block combinatorial folds, purging + embargo, Sharpe distribution | Not covered | **Deep dive** — fold generation, leakage prevention |
| `monte_carlo.py` | 248 | Monte Carlo: block bootstrap, permutation testing, trade-skip resilience, stress testing | Not covered | **Deep dive** — simulation methods |
| `regime.py` | 471 | Regime analysis: ADX + normalized ATR 4-quadrant classification, per-regime performance | Not covered | **Deep dive** — classification model |
| `stability.py` | 316 | Stability analysis: parameter perturbation (±N steps), sensitivity measurement | Not covered | **Deep dive** — perturbation model |
| `confidence.py` | 328 | Confidence scoring: sequential gates, weighted composite (0-100), RED/YELLOW/GREEN rating | Not covered | **Deep dive** — scoring formula |
| `checkpoint.py` | 260 | Checkpoint: PipelineState JSON save/load, atomic write (temp→rename), enum conversion | Not covered | **Deep dive** — crash safety, resume |
| `types.py` | 242 | Result types: `PipelineState`, `CandidateResult`, `WalkForwardResult`, `CPCVResult`, `MonteCarloResult`, `ConfidenceResult`, `Rating` | Not covered | **Deep dive** — data model |
| `config.py` | 120 | `PipelineConfig`: all stage thresholds, cost defaults, window sizes, gate thresholds | Not covered | **Moderate** — configuration |
| `__init__.py` | 36 | Public API exports | Not covered | **Gap-level** |

### Cross-Reference with Story 2-1

Story 2-1 documented these modules (NOT re-documented here):
- **18 indicators** in `strategies/indicators.py` (493 lines) — full catalogue with parameter signatures, computation logic, warm-up requirements
- **Signal generation** in `strategies/base.py` — precompute-once, filter-many pattern, `Strategy` base class, `ParamDef`/`ParamSpace`
- **Exit types** — 7 types (SL, TP, trailing, breakeven, partial close, max bars, stale) with Rust implementation details
- **Fidelity risks** — EMA accumulation, warm-up alignment, sub-bar dependence, spread quality, Python/Rust parity
- **Cost model constants** — `commission_pips=0.7`, `slippage_pips=0.5`, `max_spread_pips=3.0` (identified as gap vs D13)
- **Data naming** — `EUR_USD` format (confirmed: optimizer/pipeline use same convention, no additional patterns)

---

## 3. Component Verdict Table

| Component | Baseline Location | Status | Verdict | V1 Port Boundary | Rationale | Effort | Downstream Story Notes |
|---|---|---|---|---|---|---|---|
| **Rust trade simulation** | `trade_basic.rs` (188L), `trade_full.rs` (435L) | Working, clean stateless Rust | **Keep** | **port-now** | Bar-by-bar simulation with sub-bar resolution. Pure functions with no external dependencies. Directly portable to new backtester crate | Low | 3-5: Core of Rust backtester crate. Port as-is, add cost model integration points |
| **Rust metrics computation** | `metrics.rs` (241L) | Working | **Keep** | **port-now** | 10 inline metrics with correct edge cases. Annualization factor, equity curve for DD/R²/Ulcer | Low | 3-5: Port to backtester crate. 3-6: Metrics feed SQLite ingest |
| **SL/TP computation** | `sl_tp.rs` (140L) | Working | **Keep** | **port-now** | Fixed/ATR/Swing modes. Clean pure function. Swing fallback to 1.5×ATR | Low | 3-5: Port as-is to strategy_engine crate |
| **Time filter** | `filter.rs` (56L) | Working | **Keep** | **port-now** | Hour range with wrap-around + day bitmask. Well-tested | Low | 3-5: Port as-is |
| **Parameter constants** | `constants.rs` (93L) | Working | **Adapt** | **port-now** | PL_* 64-slot layout, metric indices, mode codes. Must be shared between strategy_engine and backtester | Low | 3-4, 3-5: Shared constants crate or module |
| **PyO3 dispatch** | `lib.rs` (493L) | Working | **Replace** | **do-not-port** | PyO3 entry point, GIL release, rayon dispatch. Entirely replaced by D1 multi-process architecture. Computation logic preserved, marshalling replaced | Medium | 3-2: IPC research. 3-4: New Arrow IPC bridge replaces this |
| **Python engine orchestrator** | `engine.py` (468L) | Working | **Adapt** | **wrap-for-V1** | Signal precomputation, encoding, Rust dispatch. Lifecycle pattern preserved. Data marshalling changes from numpy→PyO3 to Arrow IPC serialization | Medium | 3-4: Python-side bridge adapter. Signal precomputation stays Python for V1 |
| **Parameter encoding** | `encoding.py` (243L) | Working | **Adapt** | **wrap-for-V1** | `EncodingSpec` with numeric/categorical/boolean/bitmask encoding. Currently maps to PL_* flat layout. New architecture needs encoding to Arrow IPC format instead | Medium | 3-4: Encoding adapts to Arrow IPC parameter transport. 3-8: Encoding affects operator skill parameter display |
| **Python metrics fallback** | `metrics.py` (306L) | Working | **Keep** | **wrap-for-V1** | Reference implementation for reporting and telemetry. Python/Rust parity verified by telemetry tests | Low | 3-7: AI analysis layer uses Python metrics for narrative generation |
| **Telemetry engine** | `telemetry.py` (559L) | Working | **Defer** | **defer** | Per-trade Python mirror of Rust loop. Valuable for debugging and parity but not on V1 critical path | Low | Post-V1: Diagnostic tool for fidelity verification |
| **Staged optimizer** | `staged.py` (792L) | Working | **Adapt** | **wrap-for-V1** | 5-stage model with strategy-defined stages. Stage locking reduces search space exponentially. Must adapt to use D3 state machine for stage transitions instead of internal loop | High | 3-3: State machine must model optimization stages. 3-8: Operator controls stage transitions |
| **Samplers** | `sampler.py` (968L) | Working | **Keep** | **wrap-for-V1** | Sobol, Random, EDA, CMA-ES. Sophisticated exploration→exploitation. These are pure numpy — no Rust dependency | Low | Phase 0 optimization research may replace/extend |
| **CV objective** | `cv_objective.py` (295L) | Working | **Keep** | **wrap-for-V1** | K-fold CV inside optimizer with CVaR aggregation. Pure Python | Low | Phase 0 may extend fold strategies |
| **Ranking & DSR** | `ranking.py` (173L) | Working | **Keep** | **wrap-for-V1** | Quality ranking, combined back/forward rank, Deflated Sharpe Ratio. Pure Python | Low | 3-7: Feeds AI analysis narrative |
| **Pre/post filter** | `prefilter.py` (91L) | Working | **Keep** | **wrap-for-V1** | Invalid combo rejection + hard metric gates. Pure Python | Low | 3-3: Gate definitions feed state machine |
| **Optimizer config** | `config.py` (140L) | Working | **Adapt** | **wrap-for-V1** | Comprehensive config dataclass. Must align with D3 pipeline config and strategy spec `optimization_plan` | Low | 3-3: Config feeds pipeline state machine |
| **Result archive** | `archive.py` (170L) | Working | **Adapt** | **wrap-for-V1** | CSV/JSON persistence. Must migrate to D2 (Arrow IPC/SQLite/Parquet) | Medium | 3-6: Archive adapts to SQLite ingest |
| **Validation pipeline stages** | `walk_forward.py` (417L), `cpcv.py` (351L), `monte_carlo.py` (248L), `regime.py` (471L), `stability.py` (316L), `confidence.py` (328L) | Working, mature | **Keep** | **wrap-for-V1** | Complete validation gauntlet. All stages use shared `BacktestEngine` for evaluation. Outputs feed confidence scoring. Pure Python | Low | 3-3: Validation stages become state machine stages. 3-7: Results feed evidence packs |
| **Pipeline runner** | `runner.py` (670L) | Working | **Replace** | **do-not-port** | Sequential orchestration with manual checkpoints. No state machine, no gates, no operator approval. Replaced by D3 explicit state machine | High | 3-3: Entirely new state machine. 3-8: Operator skills replace runner CLI |
| **Checkpoint system** | `checkpoint.py` (260L) | Working | **Adapt** | **wrap-for-V1** | Atomic JSON write (temp→rename). PipelineState serialization. Pattern is sound; JSON format migrates to D2 SQLite for queryable state | Medium | 3-3: Checkpoint format evolves for state machine. 3-6: State persists in SQLite |
| **Pipeline types** | `types.py` (242L) | Working | **Adapt** | **wrap-for-V1** | Result dataclasses. Must extend for D3 state machine states and D2 serialization | Low | 3-3: Types evolve with state machine. 3-6: Types inform SQLite schema |
| **Pipeline config** | `config.py` (120L) | Working | **Adapt** | **wrap-for-V1** | Thresholds and defaults. Must merge with D3 pipeline config and allow operator overrides | Low | 3-3, 3-8: Config exposed via operator skills |
| **Cost integration** | Constants in `dtypes.py` | Minimal | **Build New** | **port-now** | Only 3 flat constants. D13 requires session-aware cost model crate with per-bar cost lookups | High | 3-5: Cost model crate integration in trade sim. Already built in Epic 2 (Story 2-7) |

**Verdict Summary:** 4 Keep, 10 Adapt, 2 Replace, 1 Build New, 1 Defer (total: 18 components assessed)

---

## 4. Detailed Component Analysis

### 4.1 Rust Backtester Core (`rust/src/`)

The Rust extension is a PyO3 module exposing a single function `batch_evaluate()`. It replaced a prior Numba JIT implementation (commit `476abc0`).

**Architecture:**
- Single `#[pyfunction]` entry point — no struct state, no persistent worker pool
- GIL released via `py.allow_threads()` before entering rayon parallel section
- Each trial is independent — per-trial chunks of `metrics_out` and `pnl_buffers` prevent cross-trial synchronization
- Panic safety via `catch_unwind(AssertUnwindSafe(...))` — panicking trials produce zero metrics instead of crashing Python

**Data flow:**
```
Python numpy arrays → PyO3 PyReadonlyArray1/2 (zero-copy view) →
  .as_slice()? (contiguous memory validation) →
  rayon .par_iter().enumerate() (parallel trial dispatch) →
  per-trial: filter signals → compute SL/TP → simulate trade → collect PnL →
  compute_metrics_inline → write to metrics_out chunk
```

**Critical observation for D1 migration:** The current model achieves zero-copy via PyO3's numpy integration — price data, signal arrays, and sub-bar arrays are shared read-only across all rayon threads. In the D1 multi-process model, this data must be serialized via Arrow IPC to the Rust binary process. The computation logic (`trade_basic`, `trade_full`, `sl_tp`, `metrics`, `filter`) is fully portable — these are pure functions with no PyO3 or numpy dependencies. Only `lib.rs` (the PyO3 dispatch layer) must be replaced.

### 4.2 Python Backtester Orchestration (`backtester/core/`)

**BacktestEngine Lifecycle (`engine.py`):**

```
__init__(strategy, open_, high, low, close, volume, spread, pip_value, slippage_pips, max_trades_per_trial)
  → Validate signal causality (rejects REQUIRES_TRAIN_FIT)
  → Build encoding spec from strategy.param_space()
  → Build PL mapping (risk/time/signal params → PL_* slot indices)
  → Generate signals: strategy.generate_signals_vectorized(open_, high, low, close, volume, spread)
  → Unpack signal arrays (bar_index, direction, entry_price, hour, day, atr_pips)
  → Pre-compute swing SL prices for each signal
  → Build sig_filters 2D array (NUM_SIGNAL_PARAMS × n_signals) for PL_SIGNAL_P0..P9
  → Set up sub-bar data (passed in or defaults to H1 arrays)
```

```
evaluate_batch(param_matrix, exec_mode=EXEC_FULL)
  → Allocate metrics_out: zeros((n_trials, NUM_METRICS))
  → Allocate pnl_buffers: zeros((n_trials, max_trades_per_trial))
  → Build param_layout: maps EncodingSpec column indices → PL_* slot indices
  → Call batch_evaluate() with all arrays
  → Return metrics_out
```

```
evaluate_single(params_dict, exec_mode=EXEC_FULL)
  → encode_params(params_dict, encoding_spec) → (1, P) matrix
  → evaluate_batch(matrix) → (1, NUM_METRICS)
  → Unpack to named dict via dtypes metric names
  → Optionally compute Python metrics for comparison
```

**Key patterns:**
- **Precompute-once, filter-many:** Signals are generated ONCE in `__init__`, then all trials filter the same signal set using PL_* time/day/signal parameters. This is the baseline's most valuable pattern (also identified by Story 2-1, proposed for D10).
- **Shared engine across pipeline stages:** Walk-forward, CPCV, and stability all use the same `BacktestEngine` instance, evaluating different windows by passing windowed param_matrices or windowed metrics extraction. This avoids creating hundreds of engine instances.

**Parameter Encoding System (`encoding.py`):**

The `EncodingSpec` system converts between Python param dicts and `(N, P)` float64 matrices:
- **Numeric params:** stored as actual float64 values
- **Categorical params (strings):** stored as integer indices into value list
- **Booleans:** stored as 0.0 / 1.0
- **List params (allowed_days):** encoded as day bitmask (Mon=bit0 through Sun=bit6)

The PL_* layout then maps these encoded columns to fixed slot positions in a 64-element parameter vector. This two-level indirection (EncodingSpec column → PL_* slot) allows different strategies to use different subsets of the 64 slots while sharing the same Rust evaluation code.

**Data Marshalling Assessment:**
Current: numpy array `.as_slice()` — truly zero-copy, no serialization overhead.
New (D1): Arrow IPC serialization — adds serialization cost but enables multi-process isolation. For the typical workload (4K-bar H1 dataset with a few hundred signals), serialization is a small fraction of evaluation time. For M1 sub-bar arrays (~260K bars), serialization cost becomes meaningful — consider shared memory or memory-mapped Arrow files as an optimization.

### 4.3 Optimization Engine (`backtester/optimizer/`)

**Staged Optimization Model (`staged.py`):**

The optimizer uses a strategy-defined stage sequence. Default: `signal → time → risk → management → refinement`

Each stage:
1. Unlocks only the parameters in that stage's group(s)
2. Locks all previously-optimized parameters at their best values
3. Uses a budget of `trials_per_stage` (default: 200K) evaluations
4. Splits budget between exploration (Sobol/Random, first 40%) and exploitation (EDA/CMA-ES, remaining 60%)
5. After evaluation, applies post-filtering (min trades, max DD, min R²)
6. Selects best candidate by quality score
7. Locks best values and advances to next stage

Stages 1-3 use `EXEC_BASIC` (SL/TP only — faster). Stage 4 (management) switches to `EXEC_FULL`. Refinement uses `EXEC_FULL` with all params active in narrowed neighborhoods (±5 index steps).

**Key insight for D3:** The staged optimization model is itself a pipeline with stages and transitions. D3's state machine could model optimization stages as sub-states within an "optimization" pipeline stage, with the `StagedOptimizer` becoming an implementation detail behind a state machine stage interface.

**Sampling Strategies (`sampler.py`):**

| Sampler | Purpose | How it works |
|---|---|---|
| `SobolSampler` | Exploration | Quasi-random low-discrepancy sequence for uniform parameter space coverage |
| `RandomSampler` | Exploration | Uniform random sampling with optional constraint filtering |
| `EDASampler` | Exploitation | Estimation of Distribution Algorithm: builds probability model from elite candidates, samples from it, decays learning rate |
| `CMAESSampler` | Exploitation | Covariance Matrix Adaptation Evolution Strategy (lazy import, optional) |
| `build_neighborhood()` | Refinement | Generates perturbations within ±N index steps of best candidate |

**Cross-Validation Objective (`cv_objective.py`):**

Optional drop-in replacement for `engine.evaluate_batch()`. Evaluates each trial across K time folds with:
- Auto-configured fold boundaries based on data length and timeframe
- Embargo between folds (configurable, default 5 calendar days)
- Aggregation methods: CVaR (conditional value at risk), mean, geometric mean, mean-std
- Progressive culling (early stopping): eliminate bad trials after first few folds

**Ranking (`ranking.py`):**
- `rank_by_quality()`: Simple descending sort by quality score
- `combined_rank()`: Weighted sum of back-test rank + forward-test rank (forward weight=1.5)
- `deflated_sharpe_ratio()`: Bailey & Lopez de Prado DSR — adjusts for multiple testing bias
- `overfitting_ratio()`: Forward quality / back quality (ratio < 0.5 = overfitting flag)

**Assessment against FR23-FR28:**

| Requirement | Baseline Status | Gap Level |
|---|---|---|
| FR23: Dynamic group composition | **Partially met** — strategy-defined stages with param groups, but group composition is static per strategy | Moderate — need dynamic group sizing based on parameter count and budget |
| FR24: Strategy-defined stages | **Met** — `optimization_stages()` method on Strategy class defines stage order | Low — already implemented |
| FR25: 3D scatter visualization | **Not met** — no visualization | Deferred to growth phase |
| FR26: Cluster similar parameter sets | **Not met** — deduplication by `max_per_dedup_group` but no clustering | Deferred — Phase 0 optimization research |
| FR27: DSR gate + diversity archive | **Partially met** — DSR computed and used for pre-filtering; diversity via `max_per_dedup_group`. No formal diversity archive | Moderate — DSR exists, archive concept needs formalization |
| FR28: Principled candidate selection | **Partially met** — DSR, overfitting ratio, combined ranking exist. Parameter stability assessed in pipeline, not optimizer | Low — foundations exist |

### 4.4 Validation Pipeline (`backtester/pipeline/`)

**Pipeline Stages (from `runner.py`):**

```
Stage 1: Data Loading   → Load OHLCV + spread + sub-bar data
Stage 2: Optimization   → StagedOptimizer produces top N candidates
Stage 3: Walk-Forward   → Rolling/anchored OOS window evaluation
Stage 4: Stability       → Parameter perturbation analysis
Stage 5: Monte Carlo     → Bootstrap, permutation, stress testing
Stage 6: Confidence      → Sequential gates + weighted composite score
Stage 7: Report          → JSON output with full results
```

Stages 3-6 run per-candidate. Stage order is fixed (no configurable ordering). CPCV runs as a sub-step within Stage 3 (not a separate stage). Regime analysis runs after Monte Carlo as advisory (no score impact).

**Walk-Forward Validation (`walk_forward.py`):**

- Generates rolling windows: `wf_window_bars` (6 months H1), `wf_step_bars` (3 months H1)
- Embargo: `wf_embargo_bars` (1 week H1) between windows
- Supports anchored mode (expanding window) and rolling mode
- Labels windows as IS/OOS relative to optimization period
- Evaluates each candidate on each window using the shared `BacktestEngine`
- Computes per-window metrics (Sharpe, quality, profit factor, max DD, return %)
- Aggregates: pass rate, mean Sharpe, geometric mean quality, quality CV

**CPCV (`cpcv.py`):**

- Divides data into N blocks (default: auto from data length)
- Generates all C(N,k) combinatorial test/train splits
- **Purging:** removes `purge_bars` on BOTH sides of each test block boundary from training set
- **Embargo:** removes `embargo_bars` AFTER each test block from training set
- Produces Sharpe distribution across all folds
- Reports: mean Sharpe, Sharpe std, % positive Sharpe, per-fold details

**Monte Carlo (`monte_carlo.py`):**

| Test | Method | What it measures |
|---|---|---|
| Block bootstrap | Resample trade PnL in contiguous blocks | Sharpe ratio confidence interval (preserves serial correlation) |
| Permutation test | Shuffle trade PnL randomly | Statistical significance (p-value: probability of observed Sharpe under random PnL order) |
| Trade-skip resilience | Not implemented as separate test; assessed via bootstrap | How much quality drops if trades are randomly excluded |
| Stress test | Multiply spreads by `spread_multiplier`, slippage by `slippage_multiplier` | Execution cost sensitivity |

Also computes: Deflated Sharpe Ratio (DSR) for each candidate.

**Regime Analysis (`regime.py`):**

4-quadrant classification using ADX (trend strength) + normalized ATR (volatility):
- ADX ≥ 25 = Trending; ADX ≤ 20 = Ranging; between = uses rolling comparison
- Normalized ATR (current / rolling percentile) determines Quiet vs Volatile
- Quadrants: Trend+Quiet, Trend+Volatile, Range+Quiet, Range+Volatile
- Per-regime performance breakdown for each candidate
- **Advisory only** — does not affect confidence score or elimination

**Parameter Stability (`stability.py`):**

- For each parameter: perturb ±N steps (default: 3) in the discrete value list
- Evaluate all perturbations on the engine
- Compute quality ratio: perturbed quality / original quality
- Rating: ROBUST (≥85% mean quality retention), MODERATE (≥70%), FRAGILE (≥50%), OVERFIT (<50%)
- Reports per-parameter sensitivity breakdown

**Confidence Scoring (`confidence.py`):**

Sequential hard gates → weighted composite score:

**Hard Gates (all must pass):**
1. Walk-forward pass rate ≥ 60% (`wf_pass_rate_gate`)
2. CPCV: ≥50% positive Sharpe folds AND mean Sharpe ≥ 0.3 (when CPCV available)
3. DSR ≥ 0.95 AND permutation p-value ≤ 0.05

**Composite Score (0-100, after gates):**

| Component | Weight | Formula |
|---|---|---|
| Walk-Forward | 30% | Pass rate + geometric mean quality + min quality + CV + window count |
| Stability | 20% | Mean quality retention across perturbations |
| CPCV | 15% | Mean Sharpe + positive fold % |
| Monte Carlo | 15% | Bootstrap CI + permutation p + skip resilience + stress resilience |
| DSR | 10% | DSR score (0-1 mapped to 0-100) |
| Backtest | 10% | Original quality score |

**Rating:** GREEN ≥ 70, YELLOW ≥ 40, RED < 40

**Assessment against FR29-FR37:**

| Requirement | Baseline Status | Gap Level |
|---|---|---|
| FR29: Walk-forward with rolling windows | **Met** — rolling and anchored modes, configurable window/step/embargo | None |
| FR30: CPCV preventing data leakage | **Met** — combinatorial folds with purging + embargo | None |
| FR31: Parameter perturbation analysis | **Met** — ±N step perturbation with sensitivity scoring | None |
| FR32: Monte Carlo (bootstrap, permutation, stress) | **Met** — all three implemented | None |
| FR33: Regime analysis | **Met** — ADX+NATR 4-quadrant, per-regime breakdown | None |
| FR34: Confidence score aggregation | **Met** — weighted composite with RED/YELLOW/GREEN | None |
| FR35: IS vs OOS divergence flagging | **Partially met** — walk-forward compares IS/OOS windows; overfitting_ratio in ranking | Low — could be more explicit |
| FR36: Walk-forward visualization | **Not met** — no visualization | Deferred to growth phase |
| FR37: Temporal split visualization | **Not met** — no visualization | Deferred to growth phase |

---

## 5. PyO3 Bridge & Data Flow Analysis

### Current Interface: `batch_evaluate()`

**Complete Function Signature:**
```rust
fn batch_evaluate<'py>(
    py: Python<'py>,
    // Price data (shared read-only across all trials)
    high: PyReadonlyArray1<'py, f64>,        // H1 bar highs
    low: PyReadonlyArray1<'py, f64>,         // H1 bar lows
    close: PyReadonlyArray1<'py, f64>,       // H1 bar closes
    spread: PyReadonlyArray1<'py, f64>,      // H1 bar spreads
    pip_value: f64,                           // e.g., 0.0001 for EUR/USD
    slippage_pips: f64,                       // fixed slippage
    // Signal data (shared read-only)
    sig_bar_index: PyReadonlyArray1<'py, i64>,
    sig_direction: PyReadonlyArray1<'py, i64>,
    sig_entry_price: PyReadonlyArray1<'py, f64>,
    sig_hour: PyReadonlyArray1<'py, i64>,
    sig_day: PyReadonlyArray1<'py, i64>,
    sig_atr_pips: PyReadonlyArray1<'py, f64>,
    sig_swing_sl: PyReadonlyArray1<'py, f64>,
    sig_filter_value: PyReadonlyArray1<'py, f64>,
    sig_variant: PyReadonlyArray1<'py, i64>,
    sig_filters: PyReadonlyArray2<'py, i64>,  // (NUM_SIGNAL_PARAMS, n_signals)
    // Parameter matrix (shared read-only)
    param_matrix: PyReadonlyArray2<'py, f64>, // (n_trials, n_params)
    param_layout: PyReadonlyArray1<'py, i64>, // maps param columns → PL_* slots
    // Execution mode
    exec_mode: i64,                           // EXEC_BASIC=0, EXEC_FULL=1
    // Output (mutable, pre-allocated)
    metrics_out: &Bound<'py, PyArray2<f64>>,  // (n_trials, NUM_METRICS=10)
    // Working memory
    max_trades: i64,
    bars_per_year: f64,
    // Execution costs (flat constants)
    commission_pips: f64,
    max_spread_pips: f64,
    // Sub-bar data (shared read-only)
    sub_high: PyReadonlyArray1<'py, f64>,     // M1 sub-bar highs
    sub_low: PyReadonlyArray1<'py, f64>,
    sub_close: PyReadonlyArray1<'py, f64>,
    sub_spread: PyReadonlyArray1<'py, f64>,
    h1_to_sub_start: PyReadonlyArray1<'py, i64>, // H1 bar → M1 start index
    h1_to_sub_end: PyReadonlyArray1<'py, i64>,   // H1 bar → M1 end index
    pnl_buffers: &Bound<'py, PyArray2<f64>>,  // (n_trials, max_trades) working memory
) -> PyResult<()>
```

### 64-Slot Parameter Layout (PL_*)

| Slot | Constant | Purpose | Group |
|---|---|---|---|
| 0 | `PL_SL_MODE` | SL mode (0=fixed, 1=ATR, 2=swing) | Risk |
| 1 | `PL_SL_FIXED_PIPS` | Fixed SL distance in pips | Risk |
| 2 | `PL_SL_ATR_MULT` | ATR multiplier for SL | Risk |
| 3 | `PL_TP_MODE` | TP mode (0=RR, 1=ATR, 2=fixed) | Risk |
| 4 | `PL_TP_RR_RATIO` | Risk:Reward ratio for TP | Risk |
| 5 | `PL_TP_ATR_MULT` | ATR multiplier for TP | Risk |
| 6 | `PL_TP_FIXED_PIPS` | Fixed TP distance in pips | Risk |
| 7 | `PL_HOURS_START` | Session filter start hour | Time |
| 8 | `PL_HOURS_END` | Session filter end hour | Time |
| 9 | `PL_DAYS_BITMASK` | Day-of-week bitmask (Mon=bit0..Sun=bit6) | Time |
| 10 | `PL_TRAILING_MODE` | Trailing mode (0=off, 1=fixed, 2=ATR chandelier) | Management |
| 11 | `PL_TRAIL_ACTIVATE` | Trailing activation distance (pips) | Management |
| 12 | `PL_TRAIL_DISTANCE` | Trailing distance (pips) | Management |
| 13 | `PL_TRAIL_ATR_MULT` | Trailing ATR multiplier | Management |
| 14 | `PL_BREAKEVEN_ENABLED` | Breakeven enabled (0/1) | Management |
| 15 | `PL_BREAKEVEN_TRIGGER` | Breakeven trigger distance (pips) | Management |
| 16 | `PL_BREAKEVEN_OFFSET` | Breakeven offset from entry (pips) | Management |
| 17 | `PL_PARTIAL_ENABLED` | Partial close enabled (0/1) | Management |
| 18 | `PL_PARTIAL_PCT` | Partial close percentage | Management |
| 19 | `PL_PARTIAL_TRIGGER` | Partial close trigger distance (pips) | Management |
| 20 | `PL_MAX_BARS` | Maximum bars to hold trade | Management |
| 21 | `PL_STALE_ENABLED` | Stale exit enabled (0/1) | Management |
| 22 | `PL_STALE_BARS` | Bars with no progress before stale exit | Management |
| 23 | `PL_STALE_ATR_THRESH` | ATR threshold for "no progress" detection | Management |
| 24 | `PL_SIGNAL_VARIANT` | Signal variant selector | Signal |
| 25 | `PL_BUY_FILTER_MAX` | Max filter value for buy signals | Signal |
| 26 | `PL_SELL_FILTER_MIN` | Min filter value for sell signals | Signal |
| 27-36 | `PL_SIGNAL_P0..P9` | Generic signal parameter slots | Signal |
| 37 | `PL_NUM_PL_USED` | Number of active PL slots | Meta |
| 38-63 | (unused) | Reserved for future expansion | — |

**Assessment against D1:** The PL_* layout is an optimization for the current in-process model (flat array indexing is cache-friendly for rayon parallel iteration). In the new multi-process model, parameters would be serialized via Arrow IPC as named fields, making the flat layout unnecessary. However, the PL_* semantic grouping (Risk, Time, Management, Signal) maps naturally to D10's parameter groups and D14's strategy spec structure.

### Memory Model

**Current (PyO3 in-process):**
- Price arrays: shared read-only numpy views across all rayon threads — zero copy
- Signal arrays: shared read-only — zero copy
- Parameter matrix: shared read-only — zero copy
- `metrics_out`: pre-allocated mutable buffer, split into per-trial non-overlapping chunks
- `pnl_buffers`: pre-allocated mutable working memory, per-trial chunks

**Memory per trial:** ~`max_trades * 8` bytes for PnL buffer + `NUM_METRICS * 8` bytes for metrics = ~400KB at max_trades=50K

**Total allocation:** For 4096 trials (typical batch): ~1.6GB PnL buffers + 320KB metrics. The PnL buffers are the memory bottleneck.

**Assessment against NFR1 (80%+ CPU):** The rayon `par_iter` with GIL release achieves high CPU utilization when batch sizes are large (4096+). The default thread pool uses all available cores. No explicit P-core affinity or thread pinning exists.

**Assessment against NFR9 (resource management):** Memory is pre-allocated at batch start (good for determinism per NFR4). No dynamic heap allocation on hot paths. Worker pool uses rayon's default global pool — no explicit sizing or capping. No result streaming — all results held in memory until batch completes.

---

## 6. Optimization Engine Architecture

### Staged Optimization Flow

```
run_optimization(strategy, data, config)
  → Load data (H1 OHLCV + spread + M1 sub-bars)
  → Create BacktestEngine (signal precomputation)
  → Create StagedOptimizer(engine, strategy, config)
  → optimizer.run(data_arrays)
    → For each stage in strategy.optimization_stages():
      → Build encoding spec for unlocked params only
      → Determine exec_mode (BASIC for signal/time/risk, FULL for management)
      → Allocate budget (trials_per_stage)
      → Exploration phase (first 40% of budget):
        → SobolSampler or RandomSampler generates candidates
        → Prefilter invalid combos (breakeven_offset >= trigger, etc.)
        → engine.evaluate_batch() or cv_objective.evaluate_batch()
        → Postfilter results (min trades, max DD, min R²)
        → Track best quality score
      → Exploitation phase (remaining 60%):
        → EDA/CMA-ES/GA samples near best candidates
        → Same evaluation + filtering pipeline
        → EDA learning rate decays each batch
      → Lock best candidate's param values
      → Report stage completion (best quality, valid count)
    → Refinement stage:
      → Unlock ALL params in narrowed neighborhoods (±5 steps)
      → Use EXEC_FULL mode
      → Budget: refinement_trials (400K)
      → Same exploration→exploitation pipeline
    → Optional cyclic passes (max_cyclic_passes, default: 0)
    → Candidate selection:
      → DSR prefilter (≥0.95, fallback 0.90)
      → Deduplication (max 3 per signal+risk group)
      → Return top max_pipeline_candidates (20)
```

### Assessment against FR23-FR28 (Detailed)

**FR23 (Dynamic group composition):** The baseline uses strategy-defined `optimization_stages()` which returns a list of `(stage_name, [param_group_names])`. This is flexible — strategies can define any stage order and grouping. However, group composition is static at strategy definition time, not dynamically computed from parameter count and budget. **Gap: Medium.** Need a helper that auto-groups parameters based on total combinations vs available budget.

**FR24 (Strategy-defined stages):** **Fully met.** The `optimization_stages()` method on the Strategy base class defines stage order. Default is 5 stages but strategies can override.

**FR25-FR28 (assessed at gap level for V1):**
- FR25 (3D scatter): **Not met** — no visualization exists. This is growth-phase scope.
- FR26 (Clustering): **Not met** — `max_per_dedup_group` provides basic deduplication but no k-means or DBSCAN clustering. Phase 0 research topic.
- FR27 (DSR + diversity archive): **Partially met** — DSR computed and used. Diversity enforced via dedup groups but no formal archive with crowding distance or Pareto front.
- FR28 (Principled selection): **Partially met** — DSR, overfitting ratio, combined ranking. Missing: parameter stability weighting in selection (exists in pipeline, not integrated back to optimizer).

---

## 7. Validation Pipeline Architecture

### Stage Interaction Model

```
Optimizer → top N candidates (params_dict + metrics) →
  Walk-Forward (per-candidate: IS/OOS windows) →
    CPCV (per-candidate: combinatorial folds) →
  Stability (per-candidate: perturbation analysis) →
  Monte Carlo (per-candidate: bootstrap + permutation + stress) →
  Confidence (per-candidate: gates + composite score) →
  Report (JSON)
```

Key architectural observation: **all validation stages share a single BacktestEngine instance** created on the full dataset. Per-window evaluation is achieved by passing windowed parameter matrices and extracting windowed metrics — the engine doesn't know about windows. This is efficient (one-time signal precomputation) but means:
1. Signal causality is dataset-wide (correct for non-adaptive indicators)
2. Sub-bar data spans the full dataset (memory)
3. The engine is not thread-safe — stages run sequentially per candidate

### Confidence Scoring Model (Detailed)

The confidence system implements a two-phase model:

**Phase 1: Hard Gates** — any failure eliminates the candidate:
- WF pass rate ≥ 60%
- CPCV ≥ 50% positive Sharpe folds AND mean Sharpe ≥ 0.3
- DSR ≥ 0.95 AND permutation p ≤ 0.05

**Phase 2: Weighted Composite Score** (survivors only):
- Walk-forward score (30%): 5 sub-components with configurable weights
- Stability score (20%): mean quality retention ratio
- CPCV score (15%): mean Sharpe + positive fold percentage
- Monte Carlo score (15%): 4 sub-components (bootstrap CI, permutation p, skip, stress)
- DSR score (10%): direct mapping of DSR value
- Backtest score (10%): original in-sample quality

Rating thresholds: GREEN ≥ 70, YELLOW ≥ 40, RED < 40

**Assessment against FR34:** The confidence model is comprehensive and well-structured. The weighting scheme balances forward-looking validation (WF 30%, CPCV 15% = 45%) against robustness testing (stability 20%, MC 15% = 35%) and statistical significance (DSR 10%, backtest 10% = 20%). This is a mature model that can be preserved largely as-is for V1.

### Checkpoint and Resume (`checkpoint.py`)

**Format:** JSON with PipelineState dataclass serialization via `dataclasses.asdict()`

**PipelineState fields:**
- `strategy_name`, `strategy_version`, `pair`, `timeframe`
- `completed_stages`: list of stage names
- `candidates`: list of CandidateResult (params, metrics, validation results per stage)
- `pipeline_config`: serialized PipelineConfig
- `start_time`, `elapsed_secs`

**Atomic Write Mechanism:**
```python
tmp_path = filepath + ".tmp"
json.dump(data, f, indent=2, default=str)  # Write to temp
if os.path.exists(filepath):
    os.remove(filepath)  # Windows: must remove before rename
os.rename(tmp_path, filepath)  # Atomic rename
```

Note: On Windows, the `os.remove()` + `os.rename()` is not truly atomic — a crash between remove and rename loses the checkpoint. The `os.replace()` function would be better (it's atomic on both Windows and Unix). However, the pattern is functional and the failure window is microseconds.

**Resume Logic:**
- Load checkpoint JSON
- Reconstruct PipelineState with all nested dataclass types
- Check `completed_stages` to determine resume point
- Re-run from first incomplete stage
- State includes all intermediate results (walk-forward per-window, CPCV per-fold, etc.)

**Persisted vs Recomputed on Resume:**

| Category | What | Persisted/Recomputed | Mechanism |
|---|---|---|---|
| **Persisted** | Completed stage list | Persisted | `completed_stages` in checkpoint JSON |
| **Persisted** | Validation results per candidate (WF, CPCV, MC, stability, confidence) | Persisted | Nested dataclasses in `PipelineState.candidates[].results` |
| **Persisted** | Optimization candidates (params + metrics) | Persisted | `PipelineState.candidates[]` with encoded params and metric arrays |
| **Persisted** | Pipeline configuration | Persisted | `PipelineState.pipeline_config` serialized in checkpoint |
| **Recomputed** | BacktestEngine instance (signals, indicators, price data) | Recomputed | Engine re-initialized from data files on resume; signals re-precomputed |
| **Recomputed** | Encoding spec and PL parameter layout | Recomputed | Rebuilt from strategy class definition on resume |
| **Recomputed** | In-progress stage work (partial walk-forward windows, partial candidates) | Lost | No sub-stage checkpointing; stage restarts from beginning |

**Assessment against D3:** The checkpoint system lacks:
- Named stage states (only a list of completed stage names)
- Gate definitions (no concept of approval between stages)
- Operator transitions (no pause-for-review capability)
- Stage metadata (no start/end times per stage, no resource usage)
- Stage configuration snapshotting (config is serialized once, not per-stage)

These are all requirements for D3's explicit state machine.

**Assessment against NFR5 (incremental checkpointing):** Checkpoints are written after each COMPLETE stage, not during stage execution. A 6-hour walk-forward stage that crashes at 90% loses all progress. Sub-stage checkpointing (e.g., per-candidate within walk-forward) is not implemented.

---

## 8. Gap Analysis

### 8.1 Baseline Capabilities NOT Required by New Architecture

| Baseline Capability | Notes |
|---|---|
| PyO3 in-process binding layer (`lib.rs`) | Replaced by D1 multi-process + Arrow IPC |
| Numba fallback path (removed in `476abc0`) | Already removed; Rust is sole backend |
| `telemetry.py` per-trade Python mirror | Useful for debugging but not required for V1 pipeline |
| `progress.py` progress tracking | Basic dataclasses; D3 state machine provides richer tracking |
| Legacy combo encoding (signal_variant, buy_filter_max, sell_filter_min) | Replaced by D10 spec-driven parameter specification |
| Pipeline `__init__.py` exports | New pipeline module structure will differ |

### 8.2 New Architecture Requirements NOT Present in Baseline (Gaps to Build)

| Gap | Architecture Source | What Must Be Built | Priority |
|---|---|---|---|
| Arrow IPC serialization | D1 | Price data, signals, params, and results transported via Arrow IPC between Python orchestrator and Rust binary | **V1 Critical** |
| Separate Rust backtester binary | D1 | Standalone binary that reads Arrow IPC, evaluates, writes Arrow IPC results | **V1 Critical** |
| Explicit pipeline state machine | D3 | Named stages, gate transitions, operator approval, pause/resume | **V1 Critical** |
| Session-aware cost model crate | D13 | Per-bar cost lookups replacing flat constants (already built in Epic 2, Story 2-7) | **V1 Critical** (integration) |
| Strategy engine shared crate | D14 | Trade simulation, SL/TP, filters, metrics extracted as reusable crate | **V1 Critical** |
| Arrow IPC result storage | D2 | Hot data in Arrow IPC for live dashboard queries | **V1** |
| SQLite queryable state | D2 | Pipeline state, metadata, candidate results in SQLite | **V1** |
| Parquet archive | D2 | Cold storage for historical runs | **V1** |
| Operator pipeline skills | D9 | CLI/dialogue interface for pipeline operations | **V1** |
| AI analysis layer | — | Narrative generation, anomaly detection from backtest results | **V1** |
| Evidence packs | — | Bundled analysis artifacts for operator review | **V1** |
| Sub-stage checkpointing | NFR5 | Per-candidate or per-window checkpoints within long stages | **V1** |
| Memory-aware job scheduling | NFR2 | Bounded memory allocation across concurrent backtests | **V1** |

### 8.3 Architectural Shifts Requiring Fundamental Redesign

**1. PyO3 In-Process → D1 Multi-Process with Arrow IPC**

| Aspect | Current (PyO3) | New (D1) |
|---|---|---|
| Communication | Zero-copy numpy views | Arrow IPC serialization |
| Process model | Single process, GIL released for Rust threads | Separate Rust binary process |
| Data sharing | Shared memory (rayon threads see same arrays) | Serialized per-batch data |
| Parallelism | Rayon thread pool within Rust | Multiple Rust worker processes |
| Failure isolation | Panic → catch_unwind → zero metrics | Process crash → supervisor restart |
| Resource control | GIL + rayon defaults | Process-level memory limits |

**What transfers:** All computation logic (`trade_basic`, `trade_full`, `sl_tp`, `metrics`, `filter`, `constants`) — these are pure Rust functions with no PyO3 dependency.

**What must be rebuilt:** Entry point (PyO3 `batch_evaluate` → Arrow IPC reader + writer), memory management (numpy views → Arrow record batches), parallelism orchestration (rayon within process → multiple processes).

**2. Ad-Hoc Pipeline Runner → D3 Explicit State Machine**

| Aspect | Current (runner.py) | New (D3) |
|---|---|---|
| Stage definition | Hardcoded function calls in sequence | Named stages with metadata |
| Transitions | Implicit (function return → next call) | Explicit gate transitions with conditions |
| Operator control | None (run-to-completion) | Approve/reject/modify between stages |
| Checkpoint | Post-stage JSON dump | Per-transition state persistence in SQLite |
| Resume | Re-run from stage name | Transition back to any valid state |
| Monitoring | Logging only | State machine events + operator dashboard |

**3. Flat Cost Constants → D13 Session-Aware Cost Model**

Current cost integration points in the backtester:
1. `commission_pips` parameter to `batch_evaluate()` — applied per-trade in `trade_basic.rs` and `trade_full.rs` as flat deduction
2. `slippage_pips` parameter — applied at entry as price adjustment
3. `max_spread_pips` — applied as spread filter in **both** Rust (`lib.rs:319-324`, inside the per-signal loop: skips signals where `spread_at_signal > max_spread_pips` or NaN) and Python engine (signal-level filtering). The Rust filter is the authoritative enforcement point during batch evaluation.
4. `spread` array — per-bar spread applied at entry for buy orders

**What D13 requires:** Session-aware profiles where commission and slippage vary by time-of-day and market session. The trade simulation functions must accept per-bar cost values instead of flat constants. The cost model crate (already built in Story 2-7) provides the cost lookup; integration into trade simulation is the remaining work.

**4. Monolithic lib.rs → D14 Strategy Engine + Backtester Separation**

Proposed decomposition:

| Current Location | New Location | Contents |
|---|---|---|
| `constants.rs` | `strategy_engine` crate | Shared constants (modes, exits, metrics) |
| `filter.rs` | `strategy_engine` crate | Signal filtering (shared between backtester and live) |
| `sl_tp.rs` | `strategy_engine` crate | SL/TP computation (shared) |
| `trade_basic.rs` | `backtester` crate | Basic trade simulation (backtester-only) |
| `trade_full.rs` | `backtester` crate | Full trade simulation (backtester-only) |
| `metrics.rs` | `backtester` crate | Batch metrics computation (backtester-only) |
| `lib.rs` (PyO3 entry) | **removed** | Replaced by backtester binary with Arrow IPC |

The decomposition boundary is: `strategy_engine` contains logic needed by both backtester and live trading daemon (signal processing, SL/TP computation, filtering). `backtester` crate contains simulation-specific logic (bar-by-bar trade walking, batch metrics).

### 8.4 Baseline Patterns Potentially Superior to Architecture Assumptions

**1. Precompute-Once, Filter-Many (Already proposed for D10 in Story 2-1)**

The baseline's signal precomputation model is demonstrably efficient: signals are generated once on the full dataset, then filtered per-trial by the parameter matrix. This avoids redundant signal computation across millions of trials. Story 2-1 already proposed this for D10 adoption.

**Caveat (from Story 2-1 lessons-learned):** The `SignalCausality.REQUIRES_TRAIN_FIT` guard that makes this pattern safe must be preserved in any adoption. The `BacktestEngine.__init__` explicitly rejects REQUIRES_TRAIN_FIT strategies.

**2. Shared Engine Across Validation Stages**

The baseline creates ONE BacktestEngine and reuses it across walk-forward, CPCV, stability, and Monte Carlo stages. Windowed evaluation is achieved by time-bounding signal iteration, not by creating new engines per window. This is memory-efficient and avoids redundant signal precomputation.

**Assessment:** This pattern should be preserved in the D1 multi-process model. The Rust backtester process should support windowed evaluation within a single data load, not require re-loading data per window.

**3. Staged Optimization with Param Locking**

The exponential search space reduction from staged optimization is the baseline's most powerful optimization technique. A strategy with 25 parameters across 5 groups needs ~5× (stage_budget) evaluations instead of combinatorial_space evaluations. With 200K budget per stage, 1M total evaluations explore a space that would require billions of exhaustive trials.

**Assessment:** This staged model should be preserved as the V1 optimization approach. D3's state machine should model optimization stages as sub-states, not replace the staged logic.

**4. Atomic Checkpoint Write**

The temp→rename pattern is simple and effective. The Windows compatibility issue (need `os.remove` before `os.rename`) is handled, though `os.replace()` would be better.

**Assessment:** Preserve the atomic write pattern. Extend it with sub-stage granularity (per-candidate checkpoints within walk-forward) for NFR5 compliance.

---

## 9. Proposed Architecture Updates

### 9.1 D1 — Windowed Evaluation Support in Rust Binary

**Proposal:** The Rust backtester binary should support windowed evaluation (start_bar, end_bar parameters) within a single data load. This enables the shared-engine pattern from the baseline validation pipeline.

**Justification:** Creating a new Rust process and re-serializing all data per walk-forward window (potentially 20+ windows × 20 candidates = 400+ process launches) would negate the performance benefits of multi-process isolation. A single Rust process should accept multiple evaluation requests on the same loaded data.

**Impact:** D1 binary interface must include a "session" concept — load data once, evaluate many parameter sets across different time windows, then unload. This is more complex than a simple "input → process → output" model but matches the baseline's proven efficiency pattern.

### 9.2 D3 — Optimization Sub-States in Pipeline State Machine

**Proposal:** D3's state machine should model optimization as a compound stage with internal sub-states (one per optimization stage: signal, time, risk, management, refinement). Each sub-state transition should be checkpointable.

**Justification:** The baseline's staged optimization is the most computationally expensive phase (1M+ evaluations). A crash during stage 4 of 5 currently loses all progress. D3 should enable sub-stage checkpointing and resume within optimization.

**Impact:** D3 state machine design must support hierarchical states (pipeline stages containing optimization sub-stages).

### 9.3 D1/NFR5 — Sub-Stage Checkpointing for Long Validation Stages

**Proposal:** Walk-forward validation should checkpoint per-candidate (not just per-stage). CPCV should checkpoint per-fold.

**Justification:** Walk-forward with 20 candidates × 12 windows can take hours. A crash at candidate 18 loses all 17 completed candidates. The baseline provides no sub-stage checkpointing.

**Impact:** Checkpoint format must support partial stage results (e.g., "walk-forward: candidates 0-17 complete, 18-19 pending"). This requires D3's state machine to understand intra-stage progress.

### 9.4 D13 — Per-Bar Cost Integration Points

**Proposal:** Document that D13's session-aware cost model integrates at two points in the trade simulation:
1. **Entry cost:** `slippage_pips` and `spread` at entry bar → replaced by cost model lookup at signal bar timestamp
2. **Per-trade commission:** flat `commission_pips` → replaced by session-aware commission lookup

**Justification:** The baseline has exactly 2 cost integration points in trade simulation (entry adjustment and commission deduction). The cost model crate (Story 2-7) already provides the lookup function. The integration is surgical — modify `trade_basic.rs` and `trade_full.rs` to accept per-bar cost values instead of flat constants.

**Impact:** Trade simulation function signatures change to accept cost arrays (or cost lookup function pointers) instead of scalar constants. This is a breaking interface change that must be coordinated between Stories 3-4 and 3-5.

---

## Appendix A: Parameter Layout Reference

### Complete PL_* Constant Map

```
Slot  Constant              Type    Rust Constant      Semantic
----  --------------------  ------  -----------------  --------
0     PL_SL_MODE            i64     SL_FIXED_PIPS=0    SL mode selector
                                    SL_ATR_BASED=1
                                    SL_SWING=2
1     PL_SL_FIXED_PIPS      f64                        Fixed SL in pips
2     PL_SL_ATR_MULT        f64                        ATR multiplier for SL
3     PL_TP_MODE            i64     TP_RR_RATIO=0      TP mode selector
                                    TP_ATR_BASED=1
                                    TP_FIXED_PIPS=2
4     PL_TP_RR_RATIO        f64                        Risk:Reward ratio
5     PL_TP_ATR_MULT        f64                        ATR multiplier for TP
6     PL_TP_FIXED_PIPS      f64                        Fixed TP in pips
7     PL_HOURS_START        i64                        Session start hour (0-23)
8     PL_HOURS_END          i64                        Session end hour (0-23)
9     PL_DAYS_BITMASK       i64                        Day bitmask (Mon=1..Sun=64)
10    PL_TRAILING_MODE      i64     TRAIL_OFF=0        Trailing mode selector
                                    TRAIL_FIXED_PIP=1
                                    TRAIL_ATR_CHANDELIER=2
11    PL_TRAIL_ACTIVATE     f64                        Activation distance (pips)
12    PL_TRAIL_DISTANCE     f64                        Trail distance (pips)
13    PL_TRAIL_ATR_MULT     f64                        Chandelier ATR multiplier
14    PL_BREAKEVEN_ENABLED  i64     0/1                Breakeven toggle
15    PL_BREAKEVEN_TRIGGER  f64                        Trigger distance (pips)
16    PL_BREAKEVEN_OFFSET   f64                        Offset from entry (pips)
17    PL_PARTIAL_ENABLED    i64     0/1                Partial close toggle
18    PL_PARTIAL_PCT        f64                        Close percentage (0-1)
19    PL_PARTIAL_TRIGGER    f64                        Trigger distance (pips)
20    PL_MAX_BARS           i64                        Max bars to hold
21    PL_STALE_ENABLED      i64     0/1                Stale exit toggle
22    PL_STALE_BARS         i64                        Bars before stale check
23    PL_STALE_ATR_THRESH   f64                        ATR threshold for "no progress"
24    PL_SIGNAL_VARIANT     i64                        Signal variant selector
25    PL_BUY_FILTER_MAX     f64                        Max filter for buy signals
26    PL_SELL_FILTER_MIN    f64                        Min filter for sell signals
27-36 PL_SIGNAL_P0..P9      i64                        Generic signal params (-1=no filter)
37    PL_NUM_PL_USED        meta                       Number of active slots
38-63 (reserved)            -                          Future expansion
```

Total: 64 slots (`NUM_PL = 64`)

---

## Appendix B: Metrics Computation Reference

### 10 Inline Metrics (Rust `compute_metrics_inline`)

| Index | Constant | Metric | Formula | Edge Cases |
|---|---|---|---|---|
| 0 | `M_TRADES` | Trade count | `n` | 0 trades → all metrics zero |
| 1 | `M_WIN_RATE` | Win rate | `count(pnl > 0) / n` | — |
| 2 | `M_PROFIT_FACTOR` | Profit factor | `sum(wins) / abs(sum(losses))` | No losses → 10.0 cap |
| 3 | `M_SHARPE` | Sharpe ratio (annualized) | `(mean / std) * sqrt(ann_factor)` | std=0 → 0.0 |
| 4 | `M_SORTINO` | Sortino ratio (annualized) | `(mean / downside_std) * sqrt(ann_factor)` | No losing trades → 10.0 if mean>0, else 0.0 |
| 5 | `M_MAX_DD_PCT` | Max drawdown % | Peak-to-trough on equity curve, normalized by peak | Stored as positive value |
| 6 | `M_RETURN_PCT` | Return % | `total_return / (avg_sl_pips * 100)` × 100 | Normalized by risk (SL) |
| 7 | `M_R_SQUARED` | R² (equity curve linearity) | `1 - (SS_res / SS_tot)` on cumulative equity | SS_tot=0 → 0.0; negative R² capped at 0.0 |
| 8 | `M_ULCER` | Ulcer index | `sqrt(mean(drawdown²))` on equity curve | — |
| 9 | `M_QUALITY` | Quality composite | `sharpe * sqrt(win_rate) * pf_factor * (1 - max_dd/100) * r_sq_factor` | Composite; pf capped contribution; r_sq scaled |

**Annualization factor:** `n * bars_per_year / n_bars` — adjusts for data span and trade frequency.

**Quality score formula (detailed):**
```
quality = sharpe
        × sqrt(win_rate)
        × min(profit_factor, 3.0) / 3.0      # PF contribution capped at 3.0
        × (1.0 - max_dd_pct / 100.0)          # DD penalty
        × (0.5 + 0.5 * min(r_squared, 1.0))   # R² bonus (0.5 to 1.0 range)
```

---

## Appendix C: Checkpoint Format Reference

### PipelineState JSON Structure

```json
{
  "strategy_name": "ema_crossover",
  "strategy_version": "v001",
  "pair": "EUR_USD",
  "timeframe": "H1",
  "completed_stages": ["data_loading", "optimization", "walk_forward"],
  "candidates": [
    {
      "rank": 0,
      "params": {
        "sl_mode": "atr_based",
        "sl_atr_mult": 2.0,
        "tp_mode": "rr_ratio",
        "tp_rr_ratio": 2.0,
        "allowed_hours_start": 8,
        "allowed_hours_end": 16,
        "allowed_days": [0, 1, 2, 3, 4],
        "trailing_mode": "fixed_pip",
        "trail_activate_pips": 20.0,
        "trail_distance_pips": 15.0,
        "partial_close_enabled": true,
        "partial_close_pct": 0.5,
        "partial_close_trigger_pips": 30.0
      },
      "metrics": {
        "trades": 450,
        "win_rate": 0.42,
        "profit_factor": 1.85,
        "sharpe": 1.92,
        "sortino": 2.45,
        "max_dd_pct": 12.3,
        "return_pct": 156.7,
        "r_squared": 0.89,
        "ulcer": 3.2,
        "quality_score": 1.45
      },
      "walk_forward": {
        "n_windows": 12,
        "n_oos_windows": 8,
        "n_passed": 7,
        "pass_rate": 0.875,
        "mean_sharpe": 1.45,
        "mean_quality": 1.12,
        "geo_mean_quality": 1.08,
        "windows": ["... per-window details ..."]
      },
      "cpcv": {
        "n_folds": 10,
        "mean_sharpe": 1.32,
        "sharpe_std": 0.45,
        "pct_positive_sharpe": 0.8
      },
      "stability": {
        "rating": "ROBUST",
        "mean_quality_ratio": 0.91,
        "per_param": ["... per-param details ..."]
      },
      "monte_carlo": {
        "bootstrap_sharpe_mean": 1.88,
        "bootstrap_sharpe_ci_lower": 1.12,
        "bootstrap_sharpe_ci_upper": 2.64,
        "permutation_p_value": 0.001,
        "dsr": 0.98,
        "stress_quality_ratio": 0.82
      },
      "confidence": {
        "score": 78.5,
        "rating": "GREEN",
        "gates_passed": true,
        "gate_details": {"wf_pass_rate": true, "dsr": true, "permutation_p": true}
      }
    }
  ],
  "pipeline_config": {"... serialized PipelineConfig ..."},
  "start_time": "2026-03-15T10:30:00",
  "elapsed_secs": 14567.8
}
```

**Atomic write mechanism:** Write to `{filepath}.tmp` → `os.remove({filepath})` → `os.rename(tmp, filepath)`

---

## Appendix D: Cross-Reference with Story 2-1 Findings

### What Story 2-1 Documented (Referenced, Not Duplicated)

| Topic | Story 2-1 Section | Story 3-1 Extension |
|---|---|---|
| 18 indicators (SMA, EMA, ATR, RSI, MACD, Bollinger, etc.) | Section 5 full catalogue | None — not duplicated |
| Signal generation (precompute-once, filter-many) | Section 4.2 | Extended: how signals feed batch_evaluate via encoding system |
| Trade simulation modes (EXEC_BASIC, EXEC_FULL) | Section 4.4 | Extended: bar-by-bar loop, sub-bar resolution, management feature internals |
| 7 exit types | Section 4.4 | Referenced — not re-documented |
| Fidelity risks (EMA accumulation, warm-up, sub-bar dependence) | Section 4.4, Appendix B | Extended: backtester-specific risks (checkpoint loss, cost model inaccuracy) |
| Cost model (flat constants) | Section 3 verdict table | Extended: integration points, D13 migration path |
| Strategy authoring (Python classes, ParamDef/ParamSpace) | Section 6, 7 | Extended: encoding system, PL_* layout mapping |
| D10 proposals (precompute-once, sub-bar, exit extensions) | Section 9 | Referenced — not re-proposed |

### Story 2-1 Lessons Applied in This Review

From `reviews/lessons-learned.md`:
- **Completeness:** Used AST-like enumeration (full file reads, not scanning) to avoid missing modules (Story 2-1 lesson: 12/18 indicators missed by manual reading)
- **Formula verification:** Verified metric formulas against actual Rust source, not just function signatures (Story 2-1 lesson: ATR incorrectly documented as EMA)
- **Return type verification:** Checked actual return statements for result types (Story 2-1 lesson: Donchian documented as 2 returns, actually 3)
- **Explicit unknowns:** Documented gaps and uncertainties explicitly rather than assuming complete knowledge

---

## Downstream Handoff

### Story 3-2: Python-Rust IPC Research

**Extracted from this review:**
- Current PyO3 interface: `batch_evaluate()` with 28 parameters, zero-copy numpy views
- Data volumes: H1 bars (~4K per year), M1 sub-bars (~260K per year), signals (hundreds to thousands), param matrix (N_trials × N_params)
- Current zero-copy model works because PyO3 provides direct memory access; Arrow IPC adds serialization overhead but enables multi-process isolation
- Pain point: param_matrix and pnl_buffers are the largest data structures (4096 × 64 × 8 bytes = 2MB params, 4096 × 50K × 8 = 1.6GB PnL)

**Migration boundary:** Python orchestrator sends: price arrays + signal arrays + param_matrix + cost arrays. Rust binary returns: metrics_out array + (optionally) pnl_buffers for detailed analysis.

**V1 port decisions:** Port trade simulation logic to new binary (port-now). Replace PyO3 marshalling with Arrow IPC (build-new). Preserve param_layout concept but serialize as Arrow metadata, not flat array.

**Open questions:**
- Should the Rust binary support a "session" model (load data once, evaluate many batches)? See Proposed Architecture Update 9.1.
- How does sub-bar data transfer scale? 260K M1 bars × 4 arrays × 8 bytes = ~8MB per serialization — acceptable.

### Story 3-3: Pipeline State Machine

**Extracted from this review:**
- Current pipeline: 7 sequential stages with post-stage checkpoint
- No formal state machine — stages are hardcoded function calls in `runner.py`
- No gate concept — stages always proceed to next
- No operator approval — run-to-completion only
- Checkpoint format: JSON with PipelineState dataclass serialization, atomic write
- Resume: re-run from first incomplete stage (coarse granularity)
- Optimization is internally staged (signal → time → risk → management → refinement) — D3 should model these as sub-states

**Migration boundary:** `runner.py` (670L) is completely replaced by D3 state machine. Validation stage implementations (walk-forward, CPCV, etc.) are preserved as stage handlers. Checkpoint format migrates from JSON to SQLite (D2).

**V1 port decisions:** Replace runner.py orchestration (do-not-port). Preserve validation stage implementations (wrap-for-V1). Adapt checkpoint atomic write pattern (wrap-for-V1). Build state machine infrastructure (build-new).

**Deferred:** Sub-stage checkpointing per-candidate within validation stages (recommended but complex).

### Story 3-4: Python-Rust Bridge

**Extracted from this review:**
- Current bridge: `rust_loop.py` (74L) + PyO3 `lib.rs` (493L)
- Python side: BacktestEngine.evaluate_batch() prepares numpy arrays, calls batch_evaluate()
- Rust side: batch_evaluate() takes 28 params, releases GIL, uses rayon for parallel evaluation
- param_layout array maps EncodingSpec columns to PL_* slots (indirection layer)
- sig_filters 2D array enables per-trial signal filtering on generic parameters

**Migration boundary:** `rust_loop.py` and `lib.rs` are both replaced. New Python-side bridge serializes to Arrow IPC. New Rust-side binary deserializes Arrow IPC and dispatches evaluation.

**V1 port decisions:** Replace PyO3 entry point (do-not-port). Port computation functions (port-now). Build Arrow IPC serialization (build-new).

**Open questions:**
- Does the param_layout indirection survive? In Arrow IPC, parameters can be named fields — PL_* flat layout may be unnecessary.
- Should encoding.py adapt to produce Arrow-serializable parameter records instead of numpy matrices?

### Story 3-5: Rust Backtester Crate

**Extracted from this review:**
- Trade simulation: `trade_basic.rs` (188L) and `trade_full.rs` (435L) — pure functions, directly portable
- Metrics: `metrics.rs` (241L) — 10 inline metrics, pure function, directly portable
- SL/TP: `sl_tp.rs` (140L) — 3 modes each, pure function
- Filters: `filter.rs` (56L) — hour + day filtering, pure function
- Constants: `constants.rs` (93L) — must be shared with strategy_engine crate

**Migration boundary:** Extract these files into strategy_engine (shared) and backtester (simulation-specific) crates per D14 decomposition table in Section 8.3.

**V1 port decisions:** All 6 Rust files port-now. Cost model integration points: entry slippage (trade_basic:L30-40, trade_full:similar), commission deduction (trade_basic:L75, trade_full:similar).

**Deferred:** Sub-bar resolution optimization (current M1 resolution is adequate for V1).

### Story 3-6: Results Storage & SQLite

**Extracted from this review:**
- Current result formats: numpy arrays (metrics_out, pnl_buffers), JSON (checkpoint), CSV (archive.py)
- Metrics: 10 per trial in (N, NUM_METRICS) array
- PnL buffers: per-trial trade PnL arrays for equity curve reconstruction
- Checkpoint: PipelineState with all validation results nested
- Archive: CSV with candidate params + metrics, JSON metadata

**Migration boundary:** numpy arrays → Arrow IPC (hot data), JSON checkpoint → SQLite (queryable state), CSV archive → Parquet (cold storage).

**V1 port decisions:** Adapt archive.py to SQLite ingest (wrap-for-V1). Adapt checkpoint format to SQLite persistence (wrap-for-V1). Equity curve data (currently reconstructable from pnl_buffers, not persisted separately) should be persisted in D2 format.

**Deferred/no-port items:** telemetry.py result persistence (post-V1 diagnostic). Progress tracking (progress.py) not relevant to storage.

**Open questions:**
- Should PnL buffers be stored in Parquet (columnar, efficient for equity curve analysis) or Arrow IPC (hot, for real-time display)?
- Should validation sub-results (per-window WF, per-fold CPCV) be in separate SQLite tables or nested in a single results table?

### Story 3-7: AI Analysis Layer

**Extracted from this review:**
- Available metrics per candidate: 10 metrics (trades, win_rate, profit_factor, sharpe, sortino, max_dd, return_pct, r_squared, ulcer, quality)
- Walk-forward: per-window Sharpe, quality, pass rate, geo mean quality
- CPCV: Sharpe distribution, % positive, mean Sharpe
- Monte Carlo: bootstrap CI, permutation p-value, DSR, stress resilience
- Regime: per-regime performance breakdown (4 quadrants)
- Stability: per-parameter sensitivity, quality retention ratio
- Confidence: composite score (0-100), gate results, sub-scores

**Migration boundary:** AI analysis consumes validation pipeline outputs. No direct baseline code to port — build new using available metrics as input.

**V1 port decisions:** No baseline code to port. Build new AI analysis layer consuming D2-formatted results from Story 3-6 storage.

**Deferred/no-port items:** FR25 (3D scatter visualization), FR36-FR37 (walk-forward/temporal visualization) — growth-phase features, not V1.

**Open questions:**
- Should narrative generation use the full validation result tree or a pre-summarized metrics snapshot?
- How should anomaly detection thresholds (FR17: low trade count, perfect curves, sensitivity cliffs) be configured — hardcoded or operator-tunable?

### Story 3-8: Operator Pipeline Skills

**Extracted from this review:**
- Current operator touchpoints: CLI scripts for optimization runs, no formal skills
- Pipeline control: run-to-completion only, no pause/approve/reject
- Configuration: PipelineConfig + OptimizationConfig dataclasses with defaults
- Current outputs: JSON reports, checkpoint files

**Migration boundary:** Build operator skills for: run_backtest, get_pipeline_status, approve_gate, load_evidence_pack, refine_stage. Skills interact with D3 state machine, not pipeline runner.

**V1 port decisions:** No baseline operator skills to port. Build new skills consuming D3 state machine API. Configuration dataclasses (PipelineConfig, OptimizationConfig) provide sensible default values to seed new configuration schemas.

**Deferred/no-port items:** CLI scripts for ad-hoc optimization runs (replaced by operator skills). Progress.py real-time progress (post-V1).

**Open questions:**
- Should the operator be able to modify PipelineConfig between stages (e.g., tighten thresholds after reviewing walk-forward results)?
- What evidence pack format best supports the operator's approve/reject decision at each gate?

### Story 3-9: E2E Pipeline Proof

**Extracted from this review:**
- Architecture readiness: trade simulation and metrics are port-ready, pipeline orchestration needs complete redesign
- Critical path: D1 multi-process bridge (Story 3-4) → Rust backtester crate (Story 3-5) → state machine (Story 3-3) → results storage (Story 3-6)
- Risk: optimization engine (3,185L Python) stays Python for V1 — wrapping it behind state machine stages is the integration challenge
- Validation pipeline (3,459L Python) also stays Python — well-structured but needs state machine integration

**Migration boundary:** E2E proof exercises the full pipeline path from data loading through to a GREEN/YELLOW/RED confidence verdict, validating that all Epic 3 stories integrate correctly.

**V1 port decisions:** No baseline code to port. E2E proof validates the integration of all ported and newly-built components from Stories 3-2 through 3-8.

**Deferred/no-port items:** Full optimization cycle (E2E proof uses a simplified optimization with small trial count). Multi-pair pipeline execution (V1 proves single-pair end-to-end).

**Open questions:**
- What is the minimum fixture size (bars, trials, candidates) that exercises all pipeline stages meaningfully without taking hours?
- Should the E2E proof use a known-good strategy from ClaudeBackTester or a synthetic test strategy?

---

## V1 Port Boundary Summary

| Boundary | Components | Approach |
|---|---|---|
| **port-now** | trade_basic.rs, trade_full.rs, sl_tp.rs, metrics.rs, filter.rs, constants.rs | Port to strategy_engine + backtester Rust crates |
| **wrap-for-V1** | engine.py, encoding.py, metrics.py, staged.py, sampler.py, cv_objective.py, ranking.py, prefilter.py, archive.py, config.py (×2), walk_forward.py, cpcv.py, monte_carlo.py, regime.py, stability.py, confidence.py, checkpoint.py, types.py | Keep as Python behind artifact/state machine boundaries; adapt interfaces |
| **do-not-port** | lib.rs (PyO3 entry), runner.py (ad-hoc orchestration), rust_loop.py (PyO3 wrapper) | Replaced by D1/D3 architecture |
| **defer** | telemetry.py, progress.py | Post-V1 diagnostic tools |
| **build-new** | Arrow IPC bridge, pipeline state machine, operator skills, AI analysis, evidence packs, SQLite state, sub-stage checkpointing | New architecture components per Epic 3 stories |
