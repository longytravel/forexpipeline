# Strategy Evaluator Baseline Review

## Baseline Traceability

| Field | Value |
|---|---|
| Repository | `C:\Users\ROG\Projects\ClaudeBackTester` |
| Branch | `master` |
| Commit | `2084beb0683547de3efa1702f49319d30938b851` |
| Commit Date | 2026-03-15 16:27:42 +0000 |
| Review Date | 2026-03-15 |
| Reviewer | Claude Opus 4.6 (automated) |

---

## 1. Executive Summary

The ClaudeBackTester strategy evaluator is a **Python-first architecture with a Rust acceleration layer** — fundamentally different from the `crates/strategy_engine/` Rust-crate structure assumed by D14. The baseline contains **15,491 lines of Python** across strategies, core engine, optimizer, validation pipeline, live trading, and verification modules, plus **1,646 lines of Rust** in a single `backtester_core` PyO3 extension that handles only the hot loop (parallel batch trade simulation and metrics computation).

**Key findings:**

1. **Structural mismatch with D14:** There are no Rust crates for `strategy_engine`, `backtester`, `optimizer`, or `validator`. The entire strategy evaluation — indicator computation, signal generation, filter chains, encoding — lives in Python. Rust handles only trade simulation and metrics. This is the opposite of D14's assumption that indicators, filters, and exits are Rust modules.

2. **Mature evaluation model:** The baseline's "precompute-once, filter-many" pattern is well-engineered — signals are generated once from OHLCV data, then filtered per-trial during optimization. This is the right architecture for optimizer throughput and maps well to the D10 three-layer model if adapted correctly.

3. **No specification-driven strategy definition:** Strategies are Python classes with hardcoded parameter spaces. There is no config file, TOML, JSON, or any declarative strategy format. Creating a new strategy requires writing Python code. This is the "major unresolved gap" identified in baseline-to-architecture-mapping.md and the primary target for D10's intent→spec→evaluator model.

4. **18 indicators (16 public + 2 private helpers), 10 strategies, comprehensive exit system:** The indicator library and trade management system (6 exit types, modular composition) are mature and production-tested. The evaluation is deterministic with minor floating-point accumulation risks in EMA computation.

5. **No session-aware cost model:** Cost modeling is limited to constant `commission_pips` (0.7), `slippage_pips` (0.5), and a `max_spread_pips` filter. No session-dependent spread profiles or variable commission structures exist. D13's session-aware cost model is entirely new work.

6. **Strong backtest-to-live verification:** The `verification/comparator.py` (1,066 lines) provides signal-level parity checking between backtest replay and live MT5 trades — direct evidence that the baseline prioritizes the fidelity objective (FR19/FR52).

**Overall verdict:** The baseline evaluation engine is reusable but the strategy definition layer must be replaced. Core computation logic (indicators, SL/TP, trade simulation) should be **adapted** to work behind D10's specification-driven interface. The Rust extension's architecture needs restructuring from a monolithic batch evaluator to the modular crate structure specified in D14.

---

## 2. Module Inventory

### Python Codebase (`backtester/` — 15,491 lines)

| File | Lines | Purpose |
|---|---|---|
| **strategies/base.py** | 442 | Strategy ABC, ParamDef, ParamSpace, Signal, SLTPResult, SLMode/TPMode enums |
| **strategies/indicators.py** | 493 | 18 indicator functions (SMA, EMA, ATR, RSI, MACD, Bollinger, Stochastic, ADX, Donchian, SuperTrend, Keltner, Williams %R, CCI, swing_highs, swing_lows, rolling_max/min, true_range) |
| **strategies/sl_tp.py** | ~120 | SL/TP calculation with swing-based stops |
| **strategies/modules.py** | 215 | Modular trade management (trailing, breakeven, partial close, max bars, stale exit) |
| **strategies/registry.py** | ~90 | Strategy registry with `@register` decorator pattern |
| **strategies/param_widening.py** | 238 | Parameter space expansion for optimizer search |
| **strategies/ema_crossover.py** | 207 | EMA crossover strategy |
| **strategies/macd_crossover.py** | 190 | MACD signal line crossover strategy |
| **strategies/rsi_mean_reversion.py** | 209 | RSI oversold/overbought reversion |
| **strategies/bollinger_reversion.py** | 189 | Bollinger band touch reversion |
| **strategies/stochastic_crossover.py** | 213 | Stochastic %K/%D cross in zones |
| **strategies/adx_trend.py** | 190 | ADX directional trend following |
| **strategies/donchian_breakout.py** | ~180 | Donchian channel breakout |
| **strategies/hidden_smash_day.py** | 281 | Larry Williams reversal pattern |
| **strategies/always_buy.py** | ~80 | Benchmark/testing strategy |
| **strategies/verification_test.py** | 415 | Multi-signal high-frequency generator for parity testing |
| **core/engine.py** | 466 | BacktestEngine orchestrator — connects strategy→encoding→Rust batch eval |
| **core/dtypes.py** | ~200 | Numeric constants (direction codes, SL/TP modes, exit reasons, PL layout indices) |
| **core/encoding.py** | 243 | Parameter encoding/decoding — maps named params to 64-slot flat array |
| **core/metrics.py** | 306 | Python reference metrics (Sharpe, Sortino, quality score, etc.) |
| **core/telemetry.py** | 559 | Per-trade detailed telemetry (MFE, MAE, exit reason analysis) |
| **optimizer/staged.py** | 546 | Multi-stage optimization (random sample → focused → walk-forward) |
| **optimizer/run.py** | 424 | Optimization orchestrator |
| **optimizer/sampler.py** | 379 | Parameter sampling strategies |
| **optimizer/archive.py** | ~200 | MAP-Elites diversity archive |
| **pipeline/runner.py** | 670 | Full validation pipeline runner (stages 3-7) |
| **pipeline/walk_forward.py** | 417 | Walk-forward validation |
| **pipeline/cpcv.py** | 351 | Combinatorial Purged Cross-Validation |
| **pipeline/monte_carlo.py** | 248 | Monte Carlo simulation |
| **pipeline/confidence.py** | 329 | Confidence scoring |
| **pipeline/stability.py** | 316 | Parameter stability analysis |
| **pipeline/regime.py** | 471 | Regime detection |
| **pipeline/config.py** | ~200 | Pipeline configuration with thresholds |
| **pipeline/checkpoint.py** | 260 | Checkpoint save/load (JSON, atomic write) |
| **pipeline/types.py** | 242 | Pipeline data types |
| **verification/comparator.py** | 1,066 | Backtest-to-live trade verification |
| **risk/manager.py** | 187 | Live trading risk management |
| **live/trader.py** | 703 | Live trading engine |
| **live/position_manager.py** | 220 | Position management |
| **live/config.py** | ~60 | Live trading config (pair, timeframe, risk settings) |
| **broker/mt5_orders.py** | 298 | MT5 order execution |
| **broker/mt5.py** | 258 | MT5 connection management |
| **data/downloader.py** | 372 | Dukascopy data downloading |
| **data/validation.py** | 304 | Data validation |
| **data/splitting.py** | ~150 | Train/test data splitting |
| **data/timeframes.py** | ~100 | Timeframe conversion |
| **cli/main.py** | 209 | CLI entry point |

### Rust Extension (`rust/src/` — 1,646 lines)

| File | Lines | Purpose |
|---|---|---|
| **lib.rs** | 493 | PyO3 entry point — `batch_evaluate()` function, parallel evaluation via rayon |
| **constants.rs** | 93 | Mirrors `dtypes.py` — direction codes, SL/TP modes, exit reasons, PL layout indices |
| **filter.rs** | 56 | `signal_passes_time_filter()` — hour range + day bitmask |
| **metrics.rs** | 241 | `compute_metrics_inline()` — 10 metrics per trial (Sharpe, Sortino, quality, etc.) |
| **sl_tp.rs** | 140 | `compute_sl_tp()` — SL/TP price computation from parameters |
| **trade_basic.rs** | 188 | `simulate_trade_basic()` — SL/TP-only trade with sub-bar (M1) resolution |
| **trade_full.rs** | 435 | `simulate_trade_full()` — full management (trailing, breakeven, partial, stale, max bars) |

### Rust Dependencies (`rust/Cargo.toml`)

```toml
[package]
name = "backtester_core"
version = "0.1.0"
edition = "2024"

[lib]
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.24", features = ["extension-module"] }
numpy = "0.24"
rayon = "1.10"
```

---

## 3. Component Verdict Table

| Component | Baseline Location | Status | Verdict | Rationale | Effort | Notes for Story 2.8 |
|---|---|---|---|---|---|---|
| **Indicator computation** | `strategies/indicators.py` (493 lines) | Working, Python-only | **Adapt** | 18 indicators are pure numpy functions — correct logic but must be ported to Rust for D14's `indicators.rs`. Python versions can remain as reference/test oracle | High | Direct input to 2.8 indicator registry; see Section 5 for full catalogue |
| **Signal generation / evaluator core** | `strategies/base.py` + `core/engine.py` | Working | **Adapt** | "Precompute-once, filter-many" pattern is sound. Must wrap with spec-driven interface (D10) instead of Python class inheritance. Engine orchestration moves to spec→evaluator pipeline | Medium | Evaluation flow becomes: parse spec → build evaluator → generate signals → encode → batch evaluate |
| **Filter chain** | `core/engine.py` (Python) + `rust/src/filter.rs` (Rust) | Working | **Adapt** | Session filter (hour range + day bitmask) and max spread filter exist in both Python and Rust. Must generalize to support D10's volatility filter and arbitrary filter composition from spec | Medium | Filter types to support: session (exists), volatility (new), day-of-week (exists), spread (exists) |
| **Exit rule evaluation** | `rust/src/trade_basic.rs` + `trade_full.rs` + `strategies/modules.py` | Working | **Adapt** | Comprehensive exit system: SL (3 modes), TP (3 modes), trailing (3 modes), breakeven, partial close, max bars, stale exit. Rust implementation is correct. Must expose via spec-driven configuration instead of PL_ flat array | Medium | D14's `exits.rs` can largely wrap existing Rust logic with spec-driven parameterization |
| **Strategy loading/parsing** | None — code-based only | **Gap** | **Replace** | No declarative strategy format exists. Strategies are Python classes. D10 requires spec-driven loading from a structured format (Story 2.2 scope) | High | This is the largest gap — entirely new spec parser needed (Story 2.8 scope) |
| **Position sizing** | `risk/manager.py` (live only) | Partial | **Adapt** | Risk-based sizing exists for live trading but not integrated into backtester. Backtester uses fixed pip-based PnL. Must add position sizing as a spec field per D10 | Low | Backtester PnL is in pips (unit-normalized); position sizing is a live execution concern |
| **Optimization metadata** | `strategies/base.py` ParamDef/ParamSpace | Working | **Adapt** | Parameter groups, discrete value lists exist. Must map to D10's `optimization_plan` with parameter_groups, dependencies, objective_function. Current encoding (PL_ layout) works but is not spec-aware | Medium | `ParamDef.group` maps naturally to D10 parameter_groups; need to add dependency support |
| **Cost modeling** | Constants only in `core/dtypes.py` | Minimal | **Build New** | Only `commission_pips`, `slippage_pips`, `max_spread_pips` constants. No session-aware profiles, no variable spreads. D13 cost model is entirely new work | High | D13 cost_model crate is net-new; baseline provides only the constant defaults |
| **Metrics computation** | `core/metrics.py` (Python) + `rust/src/metrics.rs` (Rust) | Working | **Keep** | 10 metrics computed identically in Python and Rust. Quality score formula is tuned. Can be used as-is in D14 evaluator output | Low | Metrics module is self-contained; port to D14's strategy_engine crate with minimal changes |
| **Backtest-to-live verification** | `verification/comparator.py` (1,066 lines) | Working | **Keep** | Signal-level parity checking is exactly what FR19/FR52 require. Architecture should preserve this capability | Low | Verification module validates that D14's shared crate achieves signal fidelity |

---

## 4. Detailed Component Analysis

### 4.1 Indicator Computation (`strategies/indicators.py`)

**Architecture:** All 18 indicators are stateless, pure numpy functions. Each takes OHLCV arrays and parameters, returns numpy arrays. No class state, no side effects. This is the correct architecture for the D14 `indicators.rs` module.

**Computation pattern:**
```python
def ema(data: np.ndarray, period: int) -> np.ndarray:
    out = np.full(len(data), np.nan)
    alpha = 2.0 / (period + 1)
    out[period - 1] = np.mean(data[:period])  # seed with SMA
    for i in range(period, len(data)):
        out[i] = alpha * data[i] + (1 - alpha) * out[i - 1]
    return out
```

**Warm-up behavior:** All indicators use NaN fill for the warm-up period. The warm-up length equals the indicator period (or the longest sub-indicator period for composite indicators like MACD and ADX). Signal generation skips NaN bars.

**Price source handling:** Indicators accept raw numpy arrays — the caller decides which OHLC field to pass. Most strategies use `close` for trend indicators and `high/low/close` for volatility indicators.

**Multi-timeframe:** Not supported. All computation is single-timeframe. Multi-timeframe support would require a new data pipeline feeding multiple resolution arrays.

### 4.2 Signal Generation (`strategies/base.py`, concrete strategies)

**Pattern — precompute-once, filter-many:**
1. `generate_signals(open, high, low, close, volume, spread, hour, day)` — runs indicators, finds entry conditions, produces a list of `Signal` objects with ALL possible parameter variants embedded
2. `filter_signals(signals, params)` — filters the pre-generated signal list by trial-specific parameters (e.g., which EMA combo, which RSI threshold)
3. `calc_sl_tp(signal, params, high, low, pip_value, swing_lookback)` — computes SL/TP prices for a specific signal and parameter set

**Signal data structure:**
```python
@dataclass
class Signal:
    bar_index: int          # Which bar generated the signal
    direction: Direction    # BUY or SELL
    entry_price: float      # Price at next bar open (signal bar close as last-bar fallback only)
    hour: int               # Hour of signal bar (for time filter)
    day_of_week: int        # 0=Monday, 6=Sunday (for day filter)
    atr_pips: float         # ATR at signal bar (mandatory for SL/TP sizing)
    attrs: dict[str, float] # Strategy-specific attributes for filtering
```

**Variant encoding:** Strategies like `ema_crossover` generate signals for ALL period combinations simultaneously, storing the combo identifier in `attrs["ema_combo"]`. During filtering, the variant parameter selects matching signals. This avoids re-running indicator computation per trial.

**Determinism:** Signal generation is deterministic — same OHLCV data produces identical signals. The numpy operations are platform-deterministic for single-threaded execution. The only risk is EMA's sequential accumulation loop, where floating-point rounding could theoretically diverge across CPU architectures, but this is a minimal risk in practice.

### 4.3 Evaluation Pipeline (`core/engine.py`)

**BacktestEngine orchestration:**
1. Strategy generates signals from OHLCV arrays
2. Signals encoded to flat numpy arrays: `sig_bar_index`, `sig_direction`, `sig_entry_price`, `sig_atr_pips`, `sig_hour`, `sig_day`, `sig_filters` (up to 10 filter columns)
3. Parameter matrix encoded via `encoding.py` → `(N_trials, 64)` float64 array using PL_ layout
4. `batch_evaluate()` called via PyO3 into Rust
5. Rust evaluates N parameter sets in parallel (rayon)
6. Per trial: iterate signals → time filter → SL/TP compute → trade simulation → collect PnL → compute metrics
7. Returns `(N_trials, 10)` metrics matrix

**PL_ parameter layout** (64 slots per trial):
- Slots 0-6: SL/TP parameters (sl_mode, sl_fixed_pips, sl_atr_mult, tp_mode, tp_rr_ratio, tp_atr_mult, tp_fixed_pips)
- Slots 7-9: Time filters (hours_start, hours_end, days_bitmask)
- Slots 10-13: Trailing stop (mode, activate, distance, atr_mult)
- Slots 14-16: Breakeven (enabled, trigger, offset)
- Slots 17-19: Partial close (enabled, pct, trigger)
- Slots 20-21: Max bars (max_bars, execution_mode)
- Slots 22-24: Stale exit (enabled, bars, atr_threshold)
- Slots 25-26: Signal filtering (variant, buy_filter_max, sell_filter_min)
- Slots 27-36: Signal params (p0-p9, strategy-specific)
- Slots 37-63: Reserved

### 4.4 Trade Simulation (Rust)

**Two execution modes:**

1. **Basic mode** (`trade_basic.rs`, 188 lines): SL/TP only. Sub-bar (M1) resolution for SL/TP checks. Conservative tiebreak: if both SL and TP hit on same sub-bar, SL wins.

2. **Full mode** (`trade_full.rs`, 435 lines): All management features — trailing stop (fixed pip or ATR chandelier), breakeven with offset, partial close, max bars limit, stale exit (low ATR threshold). H1-level checks for max_bars and stale exit, sub-bar resolution for price-sensitive management.

**Sub-bar resolution:** The engine passes both H1 arrays and M1 sub-bar arrays, with `h1_to_sub_start`/`h1_to_sub_end` mapping arrays. This allows SL/TP and trailing stop to check against M1 high/low within each H1 bar, dramatically improving simulation accuracy vs. H1-only checking.

**Spread handling:** Spread is incorporated at entry (added for buys, absent for sells) and at exit. Per-bar spread array is passed through the pipeline.

### 4.5 Metrics Computation

**10 metrics computed per trial** (identical formulas in Python `metrics.py` and Rust `metrics.rs`):

| Index | Metric | Formula |
|---|---|---|
| 0 | trades | Count of completed trades |
| 1 | win_rate | wins / total |
| 2 | profit_factor | gross_profit / gross_loss (capped at 10.0) |
| 3 | sharpe | mean(pnl) / std(pnl) * sqrt(trades_per_year) |
| 4 | sortino | mean(pnl) / downside_std * sqrt(trades_per_year) |
| 5 | max_dd_pct | Maximum drawdown as % of equity curve peak |
| 6 | return_pct | total_pnl / (avg_sl_pips * trades) * 100 |
| 7 | r_squared | R-squared of equity curve vs. linear regression |
| 8 | ulcer | Ulcer Index (RMS of drawdown percentages) |
| 9 | quality | Composite: sharpe * sqrt(win_rate) * (1 - max_dd_pct/100) * log(trades+1) / ln(50) |

### 4.6 Modular Trade Management (`strategies/modules.py`)

**Module composition pattern:** Management features are defined as `ManagementModule` subclasses that declare their parameters, PL slot mappings, and optimization group. Strategies compose modules via `management_params()` helper.

**Default modules:**
1. `TrailingStopModule` — trailing mode (off/fixed_pip/atr_chandelier), activation distance, trail distance, ATR multiplier
2. `BreakevenModule` — enabled flag, trigger pips, offset pips
3. `PartialCloseModule` — enabled flag, close percentage, trigger pips
4. `MaxBarsModule` — maximum bars held, execution mode (basic/full)
5. `StaleExitModule` — enabled flag, stale bars threshold, ATR threshold

This modular pattern is well-designed and should be preserved in the D14 architecture.

---

## 5. Indicator Catalogue

This catalogue feeds Story 2.8 (Strategy Engine Crate — Specification Parser & Indicator Registry).

### 5.1 Simple Moving Average (SMA)

| Field | Value |
|---|---|
| Canonical Name | `sma` |
| Parameters | `data: ndarray, period: int` |
| Input Type | Single price series (typically close) |
| Output Type | Single ndarray (same length as input) |
| Output Shape | `(N,)` float64, NaN-filled for bars 0..period-2 |
| Warm-up Period | `period` bars |
| Computation | Cumulative sum method: `cumsum[i] - cumsum[i-period]) / period` |
| Dependencies | None |
| Used By | None directly (EMA seeds with SMA) |
| Price Sources | Any single OHLC field (caller decides) |

### 5.2 Exponential Moving Average (EMA)

| Field | Value |
|---|---|
| Canonical Name | `ema` |
| Parameters | `data: ndarray, period: int` |
| Input Type | Single price series |
| Output Type | Single ndarray |
| Output Shape | `(N,)` float64, NaN-filled for bars 0..period-2 |
| Warm-up Period | `period` bars |
| Computation | Recursive: `alpha = 2/(period+1)`, seed with SMA of first `period` bars, then `alpha * data[i] + (1-alpha) * prev` |
| Dependencies | None |
| Used By | `ema_crossover`, `verification_test` |
| Price Sources | Any single OHLC field |
| Fidelity Note | Sequential accumulation — minimal floating-point divergence risk across platforms |

### 5.3 True Range

| Field | Value |
|---|---|
| Canonical Name | `true_range` |
| Parameters | `high: ndarray, low: ndarray, close: ndarray` |
| Input Type | Three OHLC arrays |
| Output Type | Single ndarray |
| Output Shape | `(N,)` float64 |
| Warm-up Period | 0 bars (first bar uses high-low) |
| Computation | `max(high-low, |high-prev_close|, |low-prev_close|)`, first bar = high-low |
| Dependencies | None |
| Used By | `atr()` |
| Price Sources | High, Low, Close |

### 5.4 Average True Range (ATR)

| Field | Value |
|---|---|
| Canonical Name | `atr` |
| Parameters | `high: ndarray, low: ndarray, close: ndarray, period: int` |
| Input Type | Three OHLC arrays |
| Output Type | Single ndarray |
| Output Shape | `(N,)` float64, NaN-filled for bars 0..period-2 |
| Warm-up Period | `period` bars |
| Computation | Wilder's smoothing of True Range: seed with SMA of first `period` TR values, then `prev * (period-1)/period + tr[i] / period` |
| Dependencies | `true_range` |
| Used By | All strategies (mandatory for SL/TP sizing via `signal.atr_pips`) |
| Price Sources | High, Low, Close |

### 5.5 Relative Strength Index (RSI)

| Field | Value |
|---|---|
| Canonical Name | `rsi` |
| Parameters | `close: ndarray, period: int` |
| Input Type | Single price series (close) |
| Output Type | Single ndarray |
| Output Shape | `(N,)` float64, NaN-filled for bars 0..period |
| Warm-up Period | `period + 1` bars |
| Computation | Wilder's RSI: average gain/loss over period, smoothed with `(prev * (period-1) + current) / period` |
| Dependencies | None |
| Used By | `rsi_mean_reversion`, `verification_test` |
| Price Sources | Close only |

### 5.6 MACD (Moving Average Convergence Divergence)

| Field | Value |
|---|---|
| Canonical Name | `macd` |
| Parameters | `close: ndarray, fast_period: int, slow_period: int, signal_period: int` |
| Input Type | Single price series (close) |
| Output Type | Tuple of 3 ndarrays: `(macd_line, signal_line, histogram)` |
| Output Shape | Each `(N,)` float64, NaN-filled for warm-up |
| Warm-up Period | `slow_period + signal_period - 1` bars |
| Computation | `macd_line = ema(close, fast) - ema(close, slow)`, `signal = ema(macd_line, signal)`, `histogram = macd_line - signal` |
| Dependencies | `ema` (x3) |
| Used By | `macd_crossover`, `verification_test` |
| Price Sources | Close only |

### 5.7 Bollinger Bands

| Field | Value |
|---|---|
| Canonical Name | `bollinger_bands` |
| Parameters | `close: ndarray, period: int, num_std: float` |
| Input Type | Single price series (close) |
| Output Type | Tuple of 3 ndarrays: `(upper, middle, lower)` |
| Output Shape | Each `(N,)` float64, NaN-filled for bars 0..period-2 |
| Warm-up Period | `period` bars |
| Computation | `middle = sma(close, period)`, `std = rolling_std(close, period)`, `upper = middle + num_std * std`, `lower = middle - num_std * std` |
| Dependencies | `sma` (implicitly via rolling computation) |
| Used By | `bollinger_reversion`, `verification_test` |
| Price Sources | Close only |

### 5.8 Stochastic Oscillator

| Field | Value |
|---|---|
| Canonical Name | `stochastic` |
| Parameters | `high: ndarray, low: ndarray, close: ndarray, k_period: int, d_period: int` |
| Input Type | Three OHLC arrays |
| Output Type | Tuple of 2 ndarrays: `(%K, %D)` |
| Output Shape | Each `(N,)` float64, NaN-filled for warm-up |
| Warm-up Period | `k_period + d_period - 1` bars |
| Computation | `%K = (close - rolling_min(low, k)) / (rolling_max(high, k) - rolling_min(low, k)) * 100`, `%D = sma(%K, d_period)` |
| Dependencies | `rolling_max`, `rolling_min`, `sma` |
| Used By | `stochastic_crossover`, `verification_test` |
| Price Sources | High, Low, Close |

### 5.9 ADX (Average Directional Index)

| Field | Value |
|---|---|
| Canonical Name | `adx` |
| Parameters | `high: ndarray, low: ndarray, close: ndarray, period: int` |
| Input Type | Three OHLC arrays |
| Output Type | Tuple of 3 ndarrays: `(adx, plus_di, minus_di)` |
| Output Shape | Each `(N,)` float64, NaN-filled for warm-up |
| Warm-up Period | `2 * period` bars (period for DI smoothing + period for ADX smoothing) |
| Computation | Directional movement → smoothed +DI/-DI → DX → smoothed ADX (Wilder's smoothing) |
| Dependencies | `true_range` (implicitly) |
| Used By | `adx_trend`, `verification_test` |
| Price Sources | High, Low, Close |

### 5.10 Donchian Channel

| Field | Value |
|---|---|
| Canonical Name | `donchian` |
| Parameters | `high: ndarray, low: ndarray, period: int` |
| Input Type | Two OHLC arrays (high, low) |
| Output Type | Tuple of 3 ndarrays: `(upper, middle, lower)` |
| Output Shape | Each `(N,)` float64, NaN-filled for bars 0..period-2 |
| Warm-up Period | `period` bars |
| Computation | `upper = rolling_max(high, period)`, `lower = rolling_min(low, period)`, `middle = (upper + lower) / 2` |
| Dependencies | `rolling_max`, `rolling_min` |
| Used By | `donchian_breakout`, `verification_test` |
| Price Sources | High, Low |

### 5.11 Rolling Maximum

| Field | Value |
|---|---|
| Canonical Name | `rolling_max` |
| Parameters | `data: ndarray, period: int` |
| Input Type | Single array |
| Output Type | Single ndarray |
| Output Shape | `(N,)` float64, NaN-filled for bars 0..period-2 |
| Warm-up Period | `period` bars |
| Computation | `np.max(sliding_window_view(data, period), axis=1)` |
| Dependencies | None |
| Used By | `donchian`, `stochastic` |
| Price Sources | Any single OHLC field (caller decides) |

### 5.12 Rolling Minimum

| Field | Value |
|---|---|
| Canonical Name | `rolling_min` |
| Parameters | `data: ndarray, period: int` |
| Input Type | Single array |
| Output Type | Single ndarray |
| Output Shape | `(N,)` float64, NaN-filled for bars 0..period-2 |
| Warm-up Period | `period` bars |
| Computation | `np.min(sliding_window_view(data, period), axis=1)` |
| Dependencies | None |
| Used By | `donchian`, `stochastic` |
| Price Sources | Any single OHLC field (caller decides) |

### 5.13 SuperTrend

| Field | Value |
|---|---|
| Canonical Name | `supertrend` |
| Parameters | `high: ndarray, low: ndarray, close: ndarray, period: int, multiplier: float` |
| Input Type | Three OHLC arrays |
| Output Type | Tuple of 2 ndarrays: `(supertrend_line, direction)` |
| Output Shape | Each `(N,)` float64; direction is 1.0 (up) or -1.0 (down) |
| Warm-up Period | `period` bars (inherits from ATR) |
| Computation | ATR-based adaptive stop: `upper_band = hl2 + multiplier * atr`, `lower_band = hl2 - multiplier * atr`. Direction flips when price crosses band. SuperTrend line follows the active band |
| Dependencies | `atr` |
| Used By | Strategy classes using trend-following with adaptive stops |
| Price Sources | High, Low, Close |

### 5.14 Keltner Channel

| Field | Value |
|---|---|
| Canonical Name | `keltner` |
| Parameters | `high: ndarray, low: ndarray, close: ndarray, ema_period: int, atr_period: int, multiplier: float` |
| Input Type | Three OHLC arrays |
| Output Type | Tuple of 3 ndarrays: `(upper, middle, lower)` |
| Output Shape | Each `(N,)` float64, NaN-filled for warm-up |
| Warm-up Period | `max(ema_period, atr_period)` bars |
| Computation | `middle = ema(close, ema_period)`, `upper = middle + multiplier * atr(H,L,C, atr_period)`, `lower = middle - multiplier * atr(H,L,C, atr_period)` |
| Dependencies | `ema`, `atr` |
| Used By | Volatility channel strategies |
| Price Sources | High, Low, Close |

### 5.15 Williams %R

| Field | Value |
|---|---|
| Canonical Name | `williams_r` |
| Parameters | `high: ndarray, low: ndarray, close: ndarray, period: int` |
| Input Type | Three OHLC arrays |
| Output Type | Single ndarray |
| Output Shape | `(N,)` float64, NaN-filled for bars 0..period-2. Range: [-100, 0] |
| Warm-up Period | `period` bars |
| Computation | `(highest_high - close) / (highest_high - lowest_low) * -100` |
| Dependencies | `_rolling_max`, `_rolling_min` (private helpers) |
| Used By | Momentum/oscillator strategies |
| Price Sources | High, Low, Close |

### 5.16 Commodity Channel Index (CCI)

| Field | Value |
|---|---|
| Canonical Name | `cci` |
| Parameters | `high: ndarray, low: ndarray, close: ndarray, period: int` |
| Input Type | Three OHLC arrays |
| Output Type | Single ndarray |
| Output Shape | `(N,)` float64, NaN-filled for warm-up |
| Warm-up Period | `period` bars |
| Computation | `typical_price = (H+L+C)/3`, `cci = (tp - sma(tp)) / (0.015 * mean_deviation(tp))` |
| Dependencies | `sma` (implicitly via rolling computation) |
| Used By | Trend/momentum strategies |
| Price Sources | High, Low, Close |

### 5.17 Swing Highs

| Field | Value |
|---|---|
| Canonical Name | `swing_highs` |
| Parameters | `high: ndarray, lookback: int` |
| Input Type | Single OHLC array (high) |
| Output Type | Single ndarray (boolean mask or NaN-filled swing values) |
| Output Shape | `(N,)` float64 |
| Warm-up Period | `lookback` bars on each side |
| Computation | Bar is a swing high if `high[i]` is the maximum within `lookback` bars on both sides |
| Dependencies | None |
| Used By | SL/TP computation (swing-based stops in `sl_tp.py`) |
| Price Sources | High |

### 5.18 Swing Lows

| Field | Value |
|---|---|
| Canonical Name | `swing_lows` |
| Parameters | `low: ndarray, lookback: int` |
| Input Type | Single OHLC array (low) |
| Output Type | Single ndarray (boolean mask or NaN-filled swing values) |
| Output Shape | `(N,)` float64 |
| Warm-up Period | `lookback` bars on each side |
| Computation | Bar is a swing low if `low[i]` is the minimum within `lookback` bars on both sides |
| Dependencies | None |
| Used By | SL/TP computation (swing-based stops in `sl_tp.py`) |
| Price Sources | Low |

### Indicator Summary for Story 2.8

All indicators are **stateless pure functions** taking numpy arrays and returning numpy arrays. They can be ported to Rust for D14's `indicators.rs` with the same signatures using `ndarray` or raw slices. The Python versions should remain as test oracles for parity verification.

**Naming convention note:** The baseline uses `EUR_USD` format in some contexts (data file naming) and `EURUSD` in others (live config `pair` field), and `EUR/USD` in checkpoint.json. The Pipeline uses `EURUSD`. Indicator functions themselves are pair-agnostic — they operate on raw price arrays.

---

## 6. Strategy Authoring Workflow

### Current Workflow (Code-Based)

**Creating a new strategy requires:**

1. Create a new Python file in `backtester/strategies/` (e.g., `my_strategy.py`)
2. Import `Strategy` ABC, `Signal`, `ParamDef`, `ParamSpace`, indicators, `@register` decorator
3. Implement the `Strategy` subclass with:
   - `name` property (string identifier)
   - `version` property (semantic version)
   - `param_space()` method — define all parameters with discrete value lists and groups
   - `generate_signals()` method — compute indicators, find entry conditions, return `Signal` list (or override `generate_signals_vectorized()` for the numpy-array-based path used by most concrete strategies)
   - `filter_signals()` method — filter signals by trial-specific parameters
   - `calc_sl_tp()` method — compute SL/TP prices
   - `signal_causality()` method (optional) — declare `CAUSAL` (default) or `REQUIRES_TRAIN_FIT`; engine rejects non-causal strategies from the precompute path
   - `management_modules()` method (optional) — declare which management modules (trailing, breakeven, partial close, stale exit) the strategy uses; defaults to `DEFAULT_MODULES`
   - `optimization_stages()` method (optional) — declare optimization stage ordering; strategies like `ema_crossover` override this to include management module groups
4. Add `@register` decorator to the class
5. Add import in `backtester/strategies/__init__.py` (`import backtester.strategies.my_strategy  # noqa: F401`)
6. Run the optimizer pipeline

**Modifying a strategy requires:**
1. Edit the Python class directly
2. Modify parameter values in `ParamDef` lists
3. Potentially update encoding mappings in `core/encoding.py` if new signal params are added
4. Re-run optimization

### Pain Points

1. **High barrier to entry:** Creating a strategy requires Python programming skills. The operator must understand numpy arrays, the Strategy ABC interface, the encoding system, and the PL_ layout. No non-programmer can create strategies.

2. **Encoding complexity:** The 64-slot flat PL_ array is an implementation detail that leaks into strategy code. Strategies must know their PL_ slot assignments, and adding a new signal parameter requires coordinating between the strategy class, encoding.py, and dtypes.py/constants.rs.

3. **Tight coupling to Rust layout:** Adding management features requires updating both Python (modules.py, dtypes.py, encoding.py) and Rust (constants.rs, trade_full.rs). This dual-language synchronization is error-prone.

4. **No validation of strategy correctness:** There is no schema validation on strategy definitions. A typo in a parameter name or an incorrect PL_ mapping causes silent bugs rather than clear errors.

5. **No versioning of strategy configurations:** While strategies have a `version` property, there is no config_hash or specification locking mechanism. Strategy behavior can change silently when code is modified.

### What Works Well (Preserve in New System)

1. **Precompute-once, filter-many pattern:** Excellent for optimizer throughput. Signals generated once, filtered cheaply per trial. This pattern should be preserved in the spec-driven evaluator.

2. **Module composition for management features:** `DEFAULT_MODULES` pattern is clean — a new management feature is a self-contained module with parameters and PL_ mappings. This composability should carry over.

3. **Registry pattern:** `@register` decorator with automatic discovery is clean. The spec-driven system should have a similar registry for indicator types and filter types.

4. **Mandatory ATR in signals:** Every signal carries `atr_pips`, making all SL/TP computation volatility-aware by default. This should remain a core requirement.

5. **Parameter grouping:** `ParamDef.group` (signal, risk, management, time) enables the optimizer to reason about parameter types. This maps directly to D10's parameter_groups.

### Explicit Unknowns

The following aspects could not be determined from the codebase alone and require operator follow-up:

1. **Strategy iteration frequency:** How often does the operator create or modify strategies? Is it daily, weekly, or ad hoc? This affects the priority of authoring workflow improvements (FR9/FR10).
2. **Undocumented strategy variants:** The repo has 10 registered strategies, but the operator may have experimented with unregistered or local-only strategies not committed to the repository.
3. **Live trading history:** Which strategies have actually been deployed live vs. only backtested? The `live/` module exists but commit history alone does not reveal deployment frequency or duration.
4. **Pain point severity ranking:** The 5 pain points documented above are inferred from code complexity. The operator may rank them differently based on lived experience.
5. **Parameter tuning process:** How does the operator decide on initial parameter ranges for `ParamDef`? Is there domain knowledge, prior research, or trial-and-error that is not captured in code?
6. **Multi-pair usage:** The codebase supports one pair per pipeline run. Does the operator run multiple pairs concurrently, and if so, how is that managed?

---

## 7. Strategy Representation Format

### Current Format: Python Code (No Declarative Specification)

There is **no declarative strategy format**. Strategies are defined entirely in Python code:

**Strategy definition** = Python class inheriting from `Strategy` ABC
**Parameter space** = `ParamDef` objects with hardcoded value lists
**Persistence** = Pipeline checkpoint JSON files storing final parameters

### Checkpoint JSON Structure (Post-Optimization)

The only "strategy representation" that persists to disk is the pipeline checkpoint:

```json
{
  "strategy_name": "ema_crossover",
  "strategy_version": "1.0.0",
  "pair": "EUR/USD",
  "timeframe": "H1",
  "completed_stages": [3, 4, 5, 6, 7],
  "current_stage": 7,
  "candidates": [
    {
      "candidate_index": 0,
      "params": {
        "ema_combo": 13300,
        "sl_mode": "fixed_pips",
        "sl_fixed_pips": 30,
        "sl_atr_mult": 0.75,
        "tp_mode": "fixed_pips",
        "tp_rr_ratio": 1.5,
        "tp_atr_mult": 2.5,
        "tp_fixed_pips": 150,
        "trailing_mode": "off",
        "trail_activate_pips": 20,
        "trail_distance_pips": 15,
        "trail_atr_mult": 2.0,
        "breakeven_enabled": false,
        "partial_close_enabled": false,
        "partial_close_pct": 70,
        "partial_close_trigger_pips": 20,
        "max_bars": 200,
        "stale_exit_enabled": false,
        "allowed_hours_start": 0,
        "allowed_hours_end": 23,
        "allowed_days": [0, 1, 2, 3, 4]
      },
      "back_quality": 0.1507,
      "forward_quality": 0.0,
      "back_sharpe": 0.4005,
      "back_trades": 688,
      "n_trials": 200840
    }
  ]
}
```

### Loading Mechanism

1. Strategy name string → `registry.get(name)` → returns strategy **class** (not instance); raises `KeyError` with available strategies list if name is unknown
2. `registry.create(name, **kwargs)` → calls `get()` internally, then instantiates the class with provided kwargs
3. Params dict → `encoding.encode_params(spec, params)` → 64-slot PL_ array
4. PL_ array + signal arrays → Rust `batch_evaluate()` or Python telemetry loop

### Validation

- **Parameter validation:** None at the strategy definition level. `ParamDef` declares allowed values but there is no schema enforcement on the params dict loaded from checkpoint.
- **Type validation:** None. PL_ slots are all float64; integer parameters are cast.
- **Structural validation:** None. No check that required parameters are present.
- **Referential validation:** Present. `registry.get()` raises `KeyError` listing all available strategies if an unknown strategy name is requested. Runtime call sites use `create_strategy()` which invokes this check. Tests explicitly cover the unknown-strategy failure path.

### Comparison to D10 Specification Schema

D10 requires a specification with: `metadata{}`, `entry_rules[]`, `exit_rules[]`, `position_sizing{}`, `optimization_plan{}`, `cost_model_reference`. The baseline has **none of this structure**. The checkpoint's flat `params` dict is the closest analog, but it conflates entry rules, exit rules, time filters, and management features into a single flat namespace.

---

## 8. Gap Analysis — Baseline vs D10/FR9-FR13

### 8.1 Baseline Capabilities NOT Covered by D10 Minimum Representable Constructs

| Baseline Capability | D10 Coverage | Recommendation |
|---|---|---|
| Sub-bar (M1) resolution for SL/TP | Not in D10 constructs table | **Adopt** — significant accuracy improvement; add as evaluator implementation detail |
| Stale exit (low-ATR trade closure) | Not in D10 exit types | **Adopt** — useful for preventing capital lock-up in dead trades |
| Partial close at profit target | Not in D10 exit types | **Adopt** — real strategy feature worth preserving |
| Breakeven with offset | Not in D10 exit types | **Adopt** — widely used risk management technique |
| Max bars exit | Not in D10 exit types | **Adopt** — prevents infinite trade duration |
| MAP-Elites diversity archive | Not in D10 optimization | **Document** — valuable for optimization diversity; may inform FR13 |
| Parameter widening | Not in D10 optimization | **Document** — optimizer implementation detail |
| Hidden Smash Day pattern | Beyond D10 constructs (price action) | **Note** — D10 primitives should be extensible enough to express this |
| Causality contract (`SignalCausality` enum) | Not in D10 constructs | **Adopt** — `CAUSAL` vs `REQUIRES_TRAIN_FIT` classification prevents look-ahead bias in precompute path; engine rejects non-causal strategies from shared evaluation |

### 8.2 D10 Requirements NOT Present in Baseline (Gaps to Build)

| D10/FR Requirement | Baseline Status | Priority |
|---|---|---|
| **Declarative strategy specification format** | Absent — code-only | **Critical** — Story 2.2 scope |
| **Natural language strategy generation** (FR9) | Absent | **Critical** — Story 2.4 scope |
| **Intent understanding dialogue** (FR10) | Absent | **Critical** — Story 2.4 scope |
| **Operator review without raw spec exposure** (FR11) | Absent | **High** — Story 2.5 scope |
| **Specification versioning with config_hash** (FR12) | Absent — no spec versioning | **High** — Story 2.5 scope |
| **Optimization plan in spec** (FR13) | Partial — ParamDef exists but not spec-embedded | **Medium** — Story 2.3 scope |
| **Session-aware cost model** (D13, FR20-FR22) | Absent — constants only | **High** — Story 2.6/2.7 scope |
| **Volatility filter** (D10 constructs) | Absent — only session/day/spread filters | **Medium** — Story 2.8 scope |
| **Multi-pair support in spec** | Implicit — one pair per pipeline run | **Low** — future scope |

### 8.3 Baseline vs Three-Layer Model (Intent → Spec → Evaluator)

**Does baseline separate intent from specification?**
No. There is no intent layer. The operator directly writes Python code that IS the specification AND the evaluator. Intent is lost — there's no record of what the operator was trying to achieve, only how they implemented it.

**Does baseline separate specification from evaluation?**
Partially. The `ParamDef`/`ParamSpace` system defines what parameters exist and the `generate_signals()` (or `generate_signals_vectorized()`)/`filter_signals()`/`calc_sl_tp()` methods define how they're evaluated. The `management_modules()` and `optimization_stages()` methods further shape the evaluation pipeline. But these are tightly coupled in the same Python class. The specification (parameter space) and evaluation (signal generation logic) are co-located and co-dependent.

**Are there baseline patterns superior to three-layer model?**
Yes — the "precompute-once, filter-many" pattern is an optimizer-aware optimization that the three-layer model should adopt. The naive three-layer approach would re-evaluate the full spec per trial, which is O(trials * bars). The baseline's approach is O(bars + trials * signals), which is dramatically faster. D10's evaluator should implement this optimization.

**Critical constraint — causality guard:** This pattern is only safe for strategies whose signals are purely causal (computed from past data only). The baseline explicitly models this via `SignalCausality` enum in `base.py` — strategies declare either `CAUSAL` (signals depend only on historical bars) or `REQUIRES_TRAIN_FIT` (signals depend on future/fitted data, e.g., curve-fitting). The engine (`engine.py`) rejects `REQUIRES_TRAIN_FIT` strategies from the shared precompute path with a `NotImplementedError`. Tests in `test_causality.py` enforce this contract. D10/D14 must carry this guard forward — any precompute-once evaluator must reject or separately handle non-causal strategies to prevent look-ahead bias.

### 8.4 D10 Phase 0 Open Questions — Baseline Evidence

**Strategy spec format constraints from baseline evidence:**
- The baseline's flat `params` dict with discrete value lists suggests the spec format needs: discrete parameter domains (not continuous), parameter grouping, and variant encoding (combo integers that pack multiple sub-parameters).
- The 64-slot PL_ layout is an implementation artifact, not a format constraint — the spec format should use named parameters, and encoding should be internal.
- Format selection (JSON/TOML/DSL) is Story 2.2's scope. Baseline evidence suggests JSON (used in checkpoints) is familiar to the codebase.

**Complex strategy logic mapping to primitives:**
- `hidden_smash_day` is the most complex strategy: it uses multi-bar patterns (previous bar comparison, close position within range). This tests whether D10's primitives can express price action patterns, not just indicator crossovers.
- `verification_test` uses 7 different signal modes in a single strategy, showing that strategies can be multi-modal. The spec format must support conditional logic within entry rules.

**Indicator extensibility model:**
- Baseline: add a function to `indicators.py`, import it in the strategy class. No registration, no schema.
- D14: needs a formal indicator registry (Story 2.8) where indicators declare their signatures, inputs, outputs, and warm-up requirements. The baseline's pure-function pattern maps cleanly to this.

---

## 9. Proposed Architecture Updates

### 9.1 D14 (Strategy Engine Shared Crate) — Structural Revision

**Finding:** D14 assumes a Rust-native `strategy_engine` crate with `evaluator.rs`, `indicators.rs`, `filters.rs`, `exits.rs`. The baseline reveals that:
- Indicators are Python-only (493 lines of numpy)
- Strategy logic is Python-only (442 lines of ABC + 2,000+ lines of concrete strategies)
- Only the hot loop (trade simulation + metrics) is Rust (1,646 lines)

**Proposed Change:** D14 should acknowledge a **phased Rust migration**:
- **Phase 1 (Epic 2):** Keep indicators in Python. Rust `strategy_engine` crate contains: spec parser (TOML/JSON → StrategySpec struct), evaluator builder (StrategySpec → evaluator config), and the existing trade simulation + metrics logic.
- **Phase 2 (Epic 3+):** Port indicator computation to Rust `indicators.rs` for full Rust evaluation path. Python indicators remain as test oracles.

**Rationale:** Porting 18 indicators to Rust is significant work that can be deferred without blocking the spec-driven pipeline. The current Python→encode→Rust handoff already achieves the performance target (200K+ trials evaluated in the baseline).

**System objective justification:** This change preserves operator confidence (working indicators are not disrupted) and artifact completeness (Python test oracles verify Rust parity) while still achieving the D14 goal of a shared crate for backtest/live signal fidelity.

### 9.2 D10 (Strategy Execution Model) — Exit Type Extensions

**Finding:** The baseline implements 7 exit types, while D10's minimum representable constructs table lists only 4 (SL, TP, trailing, chandelier).

**Proposed Change:** Add to D10 minimum representable constructs:

| Construct | Description | Justification |
|---|---|---|
| Breakeven exit | Move SL to breakeven + offset after profit threshold | Used in production strategies; widely adopted risk management |
| Partial close | Close a percentage at profit threshold | Capital efficiency; real trading feature |
| Max bars exit | Close trade after N bars regardless of PnL | Prevents capital lock-up; timing constraint |
| Stale exit | Close if ATR drops below threshold for N bars | Handles market regime change during trade |

**System objective justification:** These exit types demonstrably improve operator confidence (broader strategy expressiveness) and fidelity (matching baseline's actual capabilities ensures no regression).

### 9.3 D10 — Sub-Bar Resolution as Evaluator Requirement

**Finding:** The baseline uses M1 sub-bar data within each H1 bar for SL/TP and trailing stop checks. This dramatically improves simulation accuracy compared to bar-close-only checking.

**Proposed Change:** D10 evaluator specification should include sub-bar resolution as a required implementation detail, not just an optimization. The evaluator must support configurable sub-bar resolution (M1 within H1, or tick within M1 for future refinement).

**System objective justification:** Fidelity (FR19) — sub-bar resolution eliminates a major source of backtest/live divergence where SL/TP would be hit intra-bar but the bar-close-only simulation wouldn't detect it.

### 9.4 D10 — Precompute-Once, Filter-Many as Evaluator Pattern

**Finding:** The baseline's evaluation pattern generates all possible signals once, then filters per trial. This is O(bars + trials * signals) vs. the naive O(trials * bars).

**Proposed Change:** D10 should specify this as the evaluator's internal optimization pattern. The spec→evaluator builder should: (1) compute all indicators once, (2) generate candidate signals for all parameter variants, (3) per trial, filter signals and simulate trades.

**Required guard:** D10 must also specify a **causality contract**: the precompute path is only valid for strategies whose signals are purely causal (depend only on historical data). The baseline enforces this via `SignalCausality` enum and engine-level rejection of `REQUIRES_TRAIN_FIT` strategies. D14's evaluator must include an equivalent guard — strategies that require fitted/future data must use a separate per-fold evaluation path, not the shared precompute cache.

**System objective justification:** Reproducibility (deterministic generation), performance (200K+ trials per optimization cycle), and fidelity (causality guard prevents look-ahead bias) are all served by this pattern with its constraint.

---

## Appendix A: Representative Baseline Strategy Configuration (Regression Seed)

### EMA Crossover — `results/ema_eur_usd_h1/checkpoint.json`

```json
{
  "strategy_name": "ema_crossover",
  "strategy_version": "1.0.0",
  "pair": "EUR/USD",
  "timeframe": "H1",
  "candidates": [
    {
      "params": {
        "ema_combo": 13300,
        "sl_mode": "fixed_pips",
        "sl_fixed_pips": 30,
        "sl_atr_mult": 0.75,
        "tp_mode": "fixed_pips",
        "tp_rr_ratio": 1.5,
        "tp_atr_mult": 2.5,
        "tp_fixed_pips": 150,
        "trailing_mode": "off",
        "trail_activate_pips": 20,
        "trail_distance_pips": 15,
        "trail_atr_mult": 2.0,
        "breakeven_enabled": false,
        "breakeven_trigger_pips": 30,
        "breakeven_offset_pips": 2,
        "partial_close_enabled": false,
        "partial_close_pct": 50,
        "partial_close_trigger_pips": 40,
        "max_bars": 200,
        "stale_exit_enabled": false,
        "stale_exit_bars": 20,
        "stale_exit_atr_threshold": 0.3,
        "allowed_hours_start": 0,
        "allowed_hours_end": 23,
        "allowed_days": [0, 1, 2, 3, 4]
      },
      "back_quality": 0.1507,
      "back_sharpe": 0.4005,
      "back_trades": 688,
      "n_trials": 200840
    }
  ]
}
```

**Encoding note:** `ema_combo = 13300` encodes two EMA periods: fast = 13300 / 1000 = 13, slow = 13300 % 1000 = 300. Strategies pack multiple discrete parameters into a single integer for efficient variant filtering.

---

## Appendix B: Fidelity and Determinism Assessment (AC #9)

### Determinism Verified

| Component | Deterministic? | Notes |
|---|---|---|
| Indicator computation | Yes | Pure numpy functions, no state between calls |
| Signal generation | Yes | Same OHLCV → same signals, no randomness |
| Parameter encoding | Yes | Deterministic mapping from names to PL_ slots |
| Rust batch evaluation | Yes | No randomness, rayon parallelism doesn't affect results |
| Metrics computation | Yes | Same PnL array → same metrics |

### Fidelity Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **EMA floating-point accumulation** | Low | Sequential loop in `ema()` could diverge ~1e-15 across CPU architectures. Mitigated by seeding with SMA and using float64 |
| **Indicator warm-up alignment** | Low | Different warm-up periods per indicator mean the first valid signal bar varies. Current code handles this correctly with NaN checks |
| **Sub-bar resolution dependence** | Medium | Results depend on M1 data availability and alignment. Missing sub-bar data falls back to H1 bar checking, which can produce different SL/TP outcomes |
| **Spread array data quality** | Medium | Per-bar spread values affect both entry (for buys) and the max_spread filter. Data quality issues in spread would silently change signal filtering |
| **Python/Rust parity drift** | Medium | Constants in `dtypes.py` must stay synchronized with `constants.rs`. Manual sync is error-prone. Recommend automated parity tests |
| **Backtest/live timing** | Low | Both backtest and live use next-bar open as entry price; signal-bar close is only a fallback for the last bar in the dataset (live trading edge case). The `verification/comparator.py` uses a 2-bar tolerance for alignment verification |

---

## Appendix C: Cost Model Assessment (AC #10)

### Current Cost Logic

| Location | Mechanism | Value |
|---|---|---|
| `core/dtypes.py` | `DEFAULT_COMMISSION_PIPS = 0.7` | Constant per trade |
| `core/dtypes.py` | `DEFAULT_MAX_SPREAD_PIPS = 3.0` | Signal rejection threshold |
| `optimizer/run.py` | `slippage_pips = 0.5` | Constant per trade entry |
| `pipeline/config.py` | `commission_pips = 0.7`, `max_spread_pips = 3.0` | Pipeline defaults |
| `live/config.py` | `slippage_pips = 0.5`, `commission_per_lot = 7.0` | Live trading (USD per RT lot) |
| Rust `trade_basic.rs` / `trade_full.rs` | Entry/exit spread + slippage + commission subtracted from PnL | Applied per trade |

### D13 Compatibility Assessment

The baseline has **no session-aware cost modeling**:
- No spread profiles by session (London, NY, Asian)
- No time-of-day spread curves
- No pair-specific commission schedules
- No variable slippage models
- Spread is used as a per-bar array (data-driven) but not modeled or predicted

D13's session-aware cost model is **entirely new work**. The baseline provides only the constant defaults that D13 will replace. The per-bar spread array infrastructure in the evaluation pipeline can be reused — instead of raw historical spread, it would be populated from the D13 cost model artifact.

### Integration Path

The D13 cost model crate should produce cost profiles that replace the constants:
1. `commission_pips` → session-aware commission schedule
2. `slippage_pips` → time-of-day and volatility-dependent slippage
3. `max_spread_pips` → session-dependent spread thresholds
4. Per-bar spread array → modeled/predicted spread curve (or historical with session floor)

The Rust evaluation pipeline already accepts per-bar spread arrays, so the D13 integration point is **data preparation** (building the spread/cost arrays from the model), not evaluation logic changes.

---

## Appendix D: Data Naming Convention Observations

| Context | Format Used | Example |
|---|---|---|
| Checkpoint JSON `pair` field | Slash-separated | `EUR/USD` |
| Live config `pair` field | Concatenated | `EURUSD` |
| Data file naming | Underscore-separated | `EUR_USD_H1.parquet` |
| Result directory naming | Underscore, lowercase | `ema_eur_usd_h1/` |
| Pipeline (Forex Pipeline project) | Concatenated | `EURUSD` |

The baseline is inconsistent across contexts. The Forex Pipeline should define a canonical format (`EURUSD`) and provide a mapping utility for ClaudeBackTester compatibility. Indicator functions are pair-agnostic — they operate on raw price arrays — so the naming convention affects only data loading and artifact labeling.
