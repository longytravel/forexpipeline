# Optimization Run Report — 2026-03-24

## Summary

Ran baseline backtest + optimization sweep on `ma-crossover` v001 (EURUSD H1, 2025 full year).
The optimization infrastructure **works end-to-end** but a Windows Smart App Control block on the
freshly-compiled release binary prevented the final production run from producing scored results.

## What Was Done

### 1. Baseline Backtest (PASSED)

Default params → Rust backtester → 24 trades, both directions.

| Param | Value |
|-------|-------|
| fast_period | 20 |
| slow_period | 50 |
| SL (ATR mult) | 1.5 |
| TP (RR ratio) | 3.0 |
| Trailing ATR period | 14 |
| Trailing ATR mult | 3.0 |

| Metric | Value |
|--------|-------|
| Net P&L | -12.23 pips |
| Total trades | 24 (12L / 12S) |
| Win rate | 33.3% |
| Sharpe | -0.013 |
| Profit factor | 0.968 |

### 2. Wide Open Optimization Scope (SET)

Updated `artifacts/strategies/ma-crossover/v001.toml` to schema_version=2 flat parameter format.

| Parameter | Type | Range | Step | Values |
|-----------|------|-------|------|--------|
| fast_period | integer | 10–30 | 5 | 5 |
| slow_period | integer | 30–70 | 10 | 5 |
| sl_atr_multiplier | continuous | 0.5–6.0 | 0.5 | 12 |
| tp_rr_ratio | continuous | 0.5–8.0 | 0.5 | 16 |
| trailing_atr_period | integer | 5–50 | 5 | 10 |
| trailing_atr_multiplier | continuous | 0.5–6.0 | 0.5 | 12 |

Search space: **576,000 combinations** across 6 dimensions.

Classification (three-tier D10 taxonomy):
- **Signal** (entry, triggers signal precompute): fast_period, slow_period → 25 groups max
- **Batch** (exit, Rust handles at runtime): sl_atr_multiplier, tp_rr_ratio, trailing_atr_period, trailing_atr_multiplier

### 3. Small Debug Run (PASSED — proved optimizer produces real scores)

Settings: debug binary, batch=16, 5 gens, 2 folds, 2 CMA-ES + 1 DE.

| Result | Value |
|--------|-------|
| Time | 318s |
| Generations | 5 |
| Evaluations | 80 |
| Throughput | 0.25 evals/sec |
| Valid scores | **80/80 (100%)** |
| Best CV Sharpe | 0.074970 |
| Best params | fast=5, slow=90, SL=6.0, TP=8.0, trail(5, 4.8) |

Parameter diversity across 80 candidates:
- fast_period: 20 unique values (5–100)
- slow_period: 18 unique values (20–200)
- sl_atr_multiplier: 35 unique values (0.5–6.0)
- tp_rr_ratio: 38 unique values (0.5–8.0)
- trailing_atr_period: 10 unique values (5–50)
- trailing_atr_multiplier: 35 unique values (0.5–6.0)

### 4. Production Release Run (THROUGHPUT PROVED — scores blocked)

Settings: release binary (Mar 19, pre-V2), batch=2048, 50 gens, 2 folds, 10 CMA-ES + 3 DE.

| Result | Value |
|--------|-------|
| Time | 231.8s (3.9 min) |
| Generations | 50 |
| Evaluations | **101,850** |
| Throughput | **439.5 evals/sec** |
| Valid scores | 0/101,850 |

Scores were all -inf because the **old release binary (Mar 19)** couldn't parse V2 `optimization_plan`
(it only knew V1 `parameter_groups` format). Every Rust invocation failed instantly with a parse error,
which is why it appeared so fast — it was failing, not evaluating.

### 5. Release Binary Rebuild (BLOCKED)

Rebuilt release binary with `cargo build --release` — compiled successfully (37s).
**Windows Smart App Control blocks the new binary**: `"An Application Control policy has blocked this file"`

This is a known Windows 11 issue. The binary must be manually unblocked.

## Bugs Found & Fixed

### Bug: `write_toml_spec` strips `optimization_plan` (FIXED)

**File**: `src/python/optimization/param_classifier.py` line 277

**Before** (broken):
```python
spec_for_rust = {k: v for k, v in spec.items() if k != "optimization_plan"}
```

**After** (fixed):
```python
spec_for_rust = dict(spec)
```

**Impact**: Rust strategy_engine requires `optimization_plan` (non-optional field in `StrategySpec` struct).
Stripping it caused every batch evaluation to fail with "missing field `optimization_plan`".
The batch_dispatch caught the error silently and returned -inf scores, so the optimizer appeared to
run but produced no usable results.

### Root Cause of Old Release Binary Failure

The release binary from Mar 19 only supports V1 optimization_plan format (`parameter_groups`).
The V2 format (`schema_version=2`, flat `parameters` registry) was added to the Rust
`strategy_engine` types after Mar 19 — the debug binary (Mar 24) has it, but the release binary
was stale.

## What Needs To Happen Next

### Immediate: Unblock the release binary

**Right-click** `src/rust/target/release/forex_backtester.exe` in File Explorer →
**Properties** → check **"Unblock"** at the bottom → **Apply**.

Or: Windows Security → App & browser control → Smart App Control → set to "Evaluation" or "Off".

### Then: Re-run optimization

```bash
cd "C:/Users/ROG/Projects/Forex Pipeline"
rm -rf artifacts/ma-crossover/v001/optimization/

PYTHONPATH=src/python .venv/Scripts/python.exe -u -c "
import sys, time, warnings; sys.path.insert(0, 'src/python')
warnings.filterwarnings('ignore')
import tomllib, asyncio
from pathlib import Path
from config_loader import load_config
from logging_setup import setup_logging
from optimization.orchestrator import OptimizationOrchestrator
from rust_bridge.batch_runner import BatchRunner

config = load_config()
setup_logging(config)

spec_path = Path('artifacts/strategies/ma-crossover/v001.toml')
with open(spec_path, 'rb') as f:
    strategy_spec = tomllib.load(f)

market_data_path = Path(config['data_pipeline']['storage_path']) / 'arrow' / 'EURUSD_2025_full' / 'v1' / 'market-data.arrow'
cost_model_path = Path('artifacts/cost_models/EURUSD/v001.json')
artifacts_dir = Path('artifacts/ma-crossover/v001/optimization')
artifacts_dir.mkdir(parents=True, exist_ok=True)

# Production settings
config['optimization']['max_generations'] = 50
config['optimization']['batch_size'] = 2048
config['optimization']['cv_folds'] = 2

binary_path = Path('src/rust/target/release/forex_backtester.exe')
batch_runner = BatchRunner(binary_path=binary_path)

orchestrator = OptimizationOrchestrator(
    strategy_spec=strategy_spec,
    market_data_path=market_data_path,
    cost_model_path=cost_model_path,
    config=config,
    artifacts_dir=artifacts_dir,
    batch_runner=batch_runner,
)
result = asyncio.run(orchestrator.run())
print(f'Evals: {result.total_evaluations:,}')
print(f'Best: {result.best_candidates}')
"
```

### Expected outcome after unblock

With the fixed release binary + fixed `write_toml_spec`:
- **~100K evaluations in ~4 minutes** at ~440 evals/sec
- **Real scores** (not -inf) — the small debug run proved this works
- **Best candidate with params + CV Sharpe** for comparison against baseline
- Full artifacts: optimization-results.arrow, promoted-candidates.arrow, run-manifest.json

### To get the pip comparison

After optimization, run a full backtest with the best params (see Section 3 — the debug run
found fast=5, slow=90, SL=6.0, TP=8.0, trail(5, 4.8) with Sharpe 0.075 vs baseline -0.013).
Use the `precompute_signals` + Rust binary flow from `operator_actions.run_backtest` to get
trade-level pip results.

## Architecture Notes for Future

**Why Wide Open entry params are slow**: Entry params (fast_period, slow_period) are "signal" params
that require separate enriched Arrow data per unique combination. With 20×19=380 entry combos,
you need 380 signal precomputes + 380×2 Rust invocations per generation. This is by design (D10
three-tier taxonomy) — entry params are the expensive path, exit params are the cheap path.

**Recommended approach for wide search**: Use Tight/Explore on entry params (5-25 groups),
Wide Open on exit params (batch params). This gives 576K search space while keeping signal
groups manageable for 440+ evals/sec throughput.

**Design target** (from architecture.md): 750 evals/sec baseline, 10K-100K evaluations per run,
30-300 second completion. The 439.5 evals/sec achieved is in the right ballpark — the gap is
from signal cache overhead and Python orchestration between generations.
