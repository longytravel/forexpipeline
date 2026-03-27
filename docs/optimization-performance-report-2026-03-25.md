# Optimization Performance Report — 2026-03-25

## Executive Summary

The optimization pipeline was transformed from non-functional (0.25 evals/sec, 0% valid scores) to production-ready (363 evals/sec, 100% valid scores) in a single session. The MA-crossover strategy was optimized from **-12 pips to +424 pips** on the full-year EURUSD H1 2025 backtest.

---

## Problem Statement

The optimization pipeline had three cascading failures:

1. **Binary incompatibility** — Rust release binary (Mar 19) only supported V1 optimization_plan format; Python generated V2 specs with `schema_version=2`. Every evaluation failed silently, producing -inf scores.
2. **Sequential execution** — Rust batch mode processed candidates one-at-a-time in a `for` loop. Python dispatched folds sequentially. On a 32-core machine, 31 cores sat idle.
3. **Independent backtests** — Each candidate ran a full independent backtest (186K M1 bars), repeating all data loading, indicator computation, and bar iteration. The architecture specified "precompute-once, evaluate-many" from the ClaudeBackTester baseline.

## Changes Made

### Phase 1: Rayon Parallelization (0.25 → 37.4 evals/sec, 150x)

**Files modified:**

| File | Change |
|------|--------|
| `src/rust/crates/backtester/Cargo.toml` | Added `rayon = "1.10"` |
| `src/rust/crates/backtester/src/engine.rs` | Extracted `load_market_data()` and `run_backtest_from_batch()` from `run_backtest()`. Data loaded once, shared as `&RecordBatch` across threads. `run_backtest_from_batch` skips progress/checkpoint I/O for batch use. |
| `src/rust/crates/backtester/src/bin/forex_backtester.rs` | Replaced sequential `for` loop in `run_batch_mode` with `candidates.par_iter().map(...)`. `AtomicUsize` progress counter. Best candidate re-run with full `run_backtest()` for detailed output. |
| `src/python/optimization/batch_dispatch.py` | Sequential fold `await` → `asyncio.gather()` for parallel fold dispatch. Added `return_exceptions=True`. Initialized `all_fold_scores` to `-inf` instead of zeros. Added `asyncio.Semaphore` to limit concurrent subprocesses. |
| `src/python/rust_bridge/batch_runner.py` | Added `RAYON_NUM_THREADS` env var to subprocess. Added `n_concurrent` parameter to `dispatch()`. |

**Key design decisions:**
- `RecordBatch` is `Send + Sync` — safe to share across Rayon threads via immutable reference
- Each Rayon thread clones `StrategySpec`, applies candidate params, calls `run_backtest_from_batch`
- Failed candidates return `NEG_INFINITY` (not propagated errors) to keep score vector aligned
- Fold parallelism gives 2x on top of Rayon's 32x

### Phase 2: Vectorized Batch Evaluator (37.4 → 363 evals/sec, 10x)

**Files created/modified:**

| File | Change |
|------|--------|
| `src/rust/crates/backtester/src/batch_eval.rs` | **NEW** — 616-line vectorized evaluator. SoA (Structure-of-Arrays) layout. Single chronological pass through bars scoring ALL candidates simultaneously. |
| `src/rust/crates/backtester/src/lib.rs` | Added `pub mod batch_eval` |
| `src/rust/crates/backtester/src/bin/forex_backtester.rs` | `run_batch_mode` now calls `batch_eval::run_batch_vectorized()` as primary path. Rayon per-candidate loop retained as fallback. |
| `src/python/optimization/orchestrator.py` | Group dispatch changed to parallel `asyncio.gather()` (safe because vectorized eval is single-threaded per subprocess). Signal cache `max_entries` increased to 1024. |
| `src/python/rust_bridge/batch_runner.py` | `RAYON_NUM_THREADS=1` for vectorized mode (no internal Rayon needed). |

**How vectorized evaluation works:**

All candidates within a signal group share identical entry signals (same `fast_period`/`slow_period`). Only exit parameters differ (`sl_atr_multiplier`, `tp_rr_ratio`, `trailing_atr_multiplier`). The vectorized evaluator exploits this:

```
1. Pre-scan enriched Arrow data for entry signal bars
2. Allocate SoA candidate state arrays (contiguous Vec<f64> per field)
3. Single pass through bars:
   - At entry signal: open positions for ALL idle candidates
   - At every bar: check SL/TP/trailing for ALL active candidates
   - Record trade PnL when candidates exit
4. Compute Sharpe ratio per candidate from trade PnL arrays
```

Instead of N independent passes (one per candidate), this does ONE pass with an inner loop over candidates per bar. The SoA layout ensures cache-friendly sequential memory access for the inner loops.

**Complexity:** O(bars * candidates) with one data pass, vs O(bars * candidates) with N data passes. The constant factor improvement comes from: single data load, sequential memory access, no redundant indicator computation, no per-candidate subprocess overhead.

## Performance Progression

| Stage | Evals/sec | Wall-clock (40K evals) | Bottleneck |
|-------|-----------|----------------------|------------|
| Broken (V1/V2 mismatch) | 439* | 3.9 min* | *Fake — binary failed instantly, -inf scores |
| Fixed binary, sequential | 0.25 | ~44 hours | Single-threaded Rust, sequential folds |
| + Rayon (32 cores) | 37.4 | 18 min | Per-candidate independent backtest |
| + Vectorized evaluator | 363 | **1.9 min** | Subprocess spawn overhead |

### Remaining bottleneck: subprocess overhead

Each (group, fold) pair spawns a separate Rust subprocess. With 20 groups * 2 folds = 40 spawns per generation, Windows process creation (~200-500ms each) dominates. The Rust evaluation itself completes in milliseconds.

**To reach 750+ evals/sec** (architecture target), reduce subprocess count by either:
1. Multi-group Rust invocation — pass all groups in one subprocess, process internally
2. Persistent Rust worker — long-lived process accepting evaluation requests
3. Pre-aggregate to H1 data — 186K M1 bars → 6,200 H1 bars, 30x less data loading

## Optimization Results

### Configuration
- Strategy: MA-crossover on EURUSD H1 2025
- Entry params: fast_period [5-50 step 5], slow_period [20-120 step 10] = 110 possible groups
- Exit params: sl_atr_multiplier [0.5-6.0], tp_rr_ratio [0.5-8.0], trailing_atr_multiplier [0.5-6.0]
- Algorithm: CMA-ES (CatCMAwM) + DE (TwoPointsDE) portfolio
- Settings: 20 generations, 2048 batch, 2-fold CV, lambda=1.0

### Head-to-Head: Baseline vs Optimized

| Metric | Baseline | Optimized | Change |
|--------|----------|-----------|--------|
| Net P&L | -12.23 pips | **+423.97 pips** | **+436 pips** |
| Sharpe ratio | -0.013 | **1.026** | +1.04 |
| Win rate | 33.3% | **86.7%** | +53pp |
| Profit factor | 0.968 | **7.824** | +6.86 |
| R-squared | 0.180 | **0.948** | +0.77 |
| Max drawdown | 230.6 pips | **70.3 pips** | -69% |
| Total trades | 24 | 15 | -9 |
| Avg trade | -0.51 pips | **+28.26 pips** | +28.8 |
| Largest loss | -61.50 pips | **-46.08 pips** | +25% smaller |

### Optimized Parameters
```
fast_period = 25
slow_period = 120
sl_atr_multiplier = 3.085
tp_rr_ratio = 0.808
trailing_atr_period = 25
trailing_atr_multiplier = 3.433
```

**Interpretation:** Wider MA spread (25/120 vs default 20/50) catches bigger trends. Low TP ratio (0.81x risk) takes quick profits — 87% win rate. Generous trailing stop (3.43 ATR) protects runners. Fewer trades (15 vs 24) but dramatically better quality.

## Code Review Summary

All changes were reviewed by both Codex and Gemini:

| Reviewer | Verdict | Key Findings |
|----------|---------|-------------|
| Codex | **APPROVED** | No thread safety issues. Clean SoA layout. Correct long/short exits. One minor: extract shared `build_signal_column_name` to prevent divergence between `batch_eval.rs` and `engine.rs`. |
| Gemini | **APPROVED** | Correct cost model, Sharpe, trailing logic. One warn: TP `atr_multiple` path in batch_eval differs from engine.rs (uses `risk_reward` semantics). Only matters if `atr_multiple` TP type is used in optimization — currently not. |

### Known Technical Debt

1. **Duplicated `build_signal_column_name`** in `batch_eval.rs` and `engine.rs` — should be extracted to shared module
2. **TP type handling** — `batch_eval.rs` assumes `risk_reward` TP. If `atr_multiple` TP is needed, lines 119-121 must be updated to match engine.rs
3. **O() documentation** — batch_eval doc comment says O(bars) but is actually O(bars * candidates) with single data pass. Update comment.
4. **Subprocess overhead** — 40 spawns/gen on Windows. Multi-group Rust invocation would eliminate this.

## How to Operate

### Running an optimization
```bash
cd "C:/Users/ROG/Projects/Forex Pipeline"
PYTHONPATH=src/python .venv/Scripts/python.exe -c "
from optimization.orchestrator import OptimizationOrchestrator
# ... see src/python/optimization/__init__.py for full API
"
```

### Key configuration (config/base.toml or passed to orchestrator)
```toml
[optimization]
max_generations = 50       # More = better search, longer runtime
batch_size = 2048          # Candidates per generation
cv_folds = 2              # Cross-validation folds
max_concurrent_procs = 32  # Subprocess semaphore limit
```

### Strategy param design for throughput
- **Entry params** create signal groups (each needs signal precompute + separate Rust subprocess). Keep to 5-50 groups for best throughput.
- **Exit params** are handled by the vectorized evaluator within each group. Can be arbitrarily wide with minimal cost.
- Signal cache warms on first generation. Subsequent generations reuse cached enriched data.

### Rebuilding Rust binary
```bash
cd src/rust && cargo build --release -p backtester
```
Build takes ~10-40 seconds. Binary at `src/rust/target/release/forex_backtester.exe`.
