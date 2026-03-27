# Validation gauntlet configuration for forex strategy backtesting

**A strategy that survives every layer of this gauntlet — walk-forward, CPCV, parameter perturbation, Monte Carlo, and regime analysis — with a composite confidence score above 0.70 is statistically distinguishable from noise and structurally robust enough for live deployment.** This report provides specific, implementable parameter recommendations for each of the seven validation layers (FR29–FR34 plus ordering), calibrated to the constraints of forex M1 intraday data with ~5M bars, 200–2000 trades per strategy, 15–30 parameter dimensions, and a computational budget of minutes per candidate at 750 evals/sec.

The architecture assumes a prior 5-fold purged K-fold CV was already used *inside* the optimization objective to guide CMA-ES parameter selection. The gauntlet described here is a **post-optimization validation pipeline** — it takes an already-optimized parameter set and stress-tests it from multiple independent angles. Each layer answers a different question, and the final confidence score aggregates them into a single deployment-readiness metric.

---

## FR29: Walk-forward validation tests temporal deployment fidelity

Walk-forward validation adds a fundamentally different check than the K-fold CV used during optimization. K-fold asks "which parameters generalize across shuffled temporal blocks?" Walk-forward asks "does this fixed parameter set survive sequential forward deployment through time?" It detects slow parameter decay, regime-transition fragility, and signals with finite half-lives — failure modes invisible to non-chronological CV.

**The critical implementation choice**: do not re-optimize inside walk-forward windows. Take the already-optimized parameters and simply replay them across sequential out-of-sample windows. This transforms walk-forward from an optimization procedure into a pure validation pass.

### Window configuration by trade count

The binding constraint is trades per OOS window. With only 200 total trades spread across 28 windows, each window averages just 7 trades — far below the **30-trade minimum** needed for meaningful inference. The solution is to adapt window count to trade density:

| Total trades | IS period | OOS period | Step size | Windows | Avg trades/OOS |
|---|---|---|---|---|---|
| 200 | 2 years | 6 months | 6 months | 6 | ~33 |
| 500 | 1 year | 3 months | 3 months | ~28 | ~18 (flag) |
| 1,000 | 9 months | 3 months | 3 months | ~28 | ~36 |
| 2,000 | 6 months | 2 months | 2 months | ~42 | ~48 |

**Use rolling windows, not expanding.** Rolling keeps the IS size constant so each window tests the same "amount of learning." Expanding windows bias later tests with massive training data, masking parameter decay. For fixed rule-based strategy validation (not ML model retraining), rolling is strictly superior.

### Purge and embargo for M1 forex

**Purge** removes bars where trades from the IS period could overlap with the OOS boundary. Set purge equal to maximum trade duration: for intraday forex trades lasting minutes to hours, **purge = 480 M1 bars (8 hours)** provides conservative coverage.

**Embargo** adds an autocorrelation buffer after the OOS boundary. The project's existing internal documentation recommends 1–5 days for intraday forex. For walk-forward, use **2,880 M1 bars (2 trading days)** — sufficient for microstructure effects to dissipate without consuming excessive data.

### Walk-forward efficiency thresholds

WFE measures OOS performance as a fraction of IS performance. Robert Pardo's original framework defines these bands:

- **WFE ≥ 60%** with ≥80% of windows profitable: strong pass
- **WFE ≥ 50%** aggregate across all OOS windows: pass
- **WFE 30–50%**: marginal, indicates moderate overfitting or legitimate regime change
- **WFE < 30%**: likely overfit — hard fail
- **WFE > 100%**: suspicious, investigate data leakage

For strategies with fewer than 30 trades in some OOS windows, report WFE on the **concatenated OOS equity curve** rather than averaging per-window WFE. Flag low-count windows but weight them lower rather than rejecting outright.

---

## FR30: CPCV generates a distribution where walk-forward gives a point estimate

Combinatorial Purged Cross-Validation addresses the core limitation of walk-forward: it tests only one historical path. CPCV systematically constructs **multiple backtest paths** from combinatorial train/test splits, producing a distribution of OOS performance metrics. A 2024 paper by Arian et al. directly compared CPCV to walk-forward and found CPCV produced **lower PBO and superior DSR test statistics**, with walk-forward exhibiting "notable shortcomings in false discovery prevention."

### N and k configuration

The number of groups (N) and test groups (k) must balance path diversity against trades-per-path:

| N | k | Splits C(N,k) | Paths | Training % | Best for |
|---|---|---|---|---|---|
| 6 | 2 | 15 | 5 | 67% | 200-trade strategies (minimum viable) |
| 10 | 2 | 45 | 9 | 80% | **Recommended default** for 500+ trades |
| 12 | 2 | 66 | 11 | 83% | 1,000+ trades, more granular |
| 10 | 3 | 120 | 36 | 70% | When more paths needed |

**N=10, k=2 is the recommended default.** Each path covers the full timeline, training uses 80% of data, and the 20% test split mirrors the optimization's 5-fold structure. With 1,000 trades, each path gets all 1,000 trades (paths span the full timeline reassembled from test groups). With 200 trades and N=6, each group contains ~33 trades — barely sufficient but workable.

**Purge**: 480 M1 bars (8 hours), same as walk-forward. **Embargo**: **4,320 M1 bars (3 trading days)** — slightly more conservative than walk-forward because CPCV's non-chronological splits create more boundary surfaces where leakage could occur.

### PBO calculation and interpretation

The Probability of Backtest Overfitting (Bailey, Borwein, López de Prado, Zhu 2014/2017) uses the CSCV (Combinatorial Symmetric Cross-Validation) algorithm:

1. Partition the strategy's P&L matrix into S equal submatrices (S even; **S=8 producing 70 combinations** or S=10 producing 252 is recommended over the S=16/12,870 combinations in the original paper, for computational tractability)
2. For each combination, select S/2 submatrices as IS and the complement as OOS
3. Find the IS-optimal configuration and compute its OOS rank
4. Compute the logit: λ = ln(ω̄ / (1 − ω̄)) where ω̄ is the relative OOS rank
5. **PBO = proportion of logits ≤ 0** — the fraction of times the IS-optimal underperforms the OOS median

| PBO value | Interpretation | Action |
|---|---|---|
| **< 0.05** | Very likely genuine (analogous to p < 0.05) | Strong pass |
| **0.05–0.15** | Probably genuine with minor concerns | Pass |
| **0.15–0.30** | Uncertain, may be overfitting | Borderline, needs additional evidence |
| **0.30–0.50** | Likely some overfitting | Fail |
| **> 0.50** | IS-optimal is worse than random OOS | Hard fail |

Bailey et al.'s empirical examples show a genuine seasonal strategy achieving **PBO of 0.04%** while random walks yield PBO ≈ 100%. The strict Neyman-Pearson threshold is PBO < 0.05; practitioners with strong economic rationale often accept PBO < 0.15–0.20.

### Relationship to prior K-fold CV and DSR

The 5-fold purged CV in optimization produces a single scalar fitness score. CPCV produces a **distribution** of OOS Sharpe ratios. This distribution feeds directly into the Deflated Sharpe Ratio: the variance of Sharpe ratios across CPCV paths provides V[SR], and the number of optimization trials provides N for the DSR correction. **DSR > 0.95** means the observed Sharpe survives correction for multiple testing. Below 0.50, the strategy is indistinguishable from the expected maximum of N noise-driven trials.

**Computational cost**: With N=10, k=2, you need 45 evaluations. At 750 evals/sec batched, this takes **under 1 second** for the split evaluations themselves (using the Target Function Representation trick from the internal architecture — compute the full backtest once, then slice the result vector into fold-specific quality scores). For full PBO/CSCV with S=10, you need 252 combinations — still under 1 second batched.

---

## FR31: Parameter perturbation reveals fragile peaks versus robust plateaus

A strategy sitting on a **parameter plateau** — where ±10% shifts in any parameter produce similar performance — is structurally robust. A strategy on a **parameter island** — where performance collapses with minor changes — is almost certainly overfit to historical noise.

### Perturbation methodology for 15–30 dimensions

**Use Sobol sequences** for perturbation sampling. Compared to random sampling or Latin Hypercube, Sobol provides ~20× better space-filling precision per sample in high dimensions, is deterministic (reproducible), and is natively available via `scipy.stats.qmc.Sobol`. Generate points in [0,1]^D, then map to perturbation ranges centered on the optimized parameter vector.

**Perturbation magnitudes by parameter type:**
- **Continuous parameters** (thresholds, multipliers): ±10% of value for standard, ±20% for stress
- **Integer parameters** (lookback periods): ±10% of value with minimum ±1 step. "If the best parameter setting is 20, values 18 to 22 should show about as good performance" (Build Alpha)
- **Categorical/binary parameters**: swap-one-at-a-time testing; flip each flag independently

**Sample count**: **200–500 Sobol-sampled perturbations** provide reliable distributional statistics. At 750 evals/sec batched (one batch of 2,048 covers all samples plus headroom), this requires **under 3 seconds**.

### Two-stage sensitivity analysis

The computational budget permits a sophisticated two-stage approach:

**Stage 1 — Morris screening** (r=15 trajectories, k=30 parameters → 465 evaluations, ~0.6 sec): Identifies which parameters actually matter. The Morris method computes μ* (mean absolute elementary effect, measuring overall influence) and σ (interaction/nonlinearity). Typically reveals that only **5–8 of 30 parameters** significantly affect performance.

**Stage 2 — Sobol indices** on the 8–12 influential parameters (n=128 samples → ~2,300 evaluations, ~3 sec): Provides precise first-order (S1) and total-order (ST) variance decomposition. If the top 3 parameters explain >80% of variance, the strategy's behavior is interpretable and its sensitivity profile is clear.

### Stability metrics and thresholds

| Metric | Pass | Marginal | Fail |
|---|---|---|---|
| **Degradation ratio** (median perturbed Sharpe / original) | > 0.85 | 0.70–0.85 | < 0.70 |
| **Coefficient of variation** of Sharpe under perturbation | < 0.15 | 0.15–0.30 | > 0.30 |
| **Plateau fraction** (% of perturbations retaining >50% of original performance) | > 80% | 60–80% | < 60% |
| **Alvarez Z-score** (distance of optimized from perturbed mean in σ units) | < 1σ | 1–2σ | > 2σ |

The **Alvarez Z-score** is particularly powerful: if the optimized parameters produce a Sharpe ratio more than 2 standard deviations above the mean of perturbed samples, the optimal point is an isolated peak — a hallmark of overfitting.

**Composite stability score**: `StabilityScore = 0.4 × DegradationRatio + 0.3 × (1 − CV_normalized) + 0.3 × PlateauFraction`, yielding a 0–1 metric where > 0.80 passes and < 0.65 fails.

---

## FR32: Monte Carlo separates signal from sequence luck and execution fragility

Monte Carlo validation operates at three levels: trade-level resampling (testing path dependency), return-level permutation (testing statistical significance), and execution stress testing (testing real-world viability). The first two require **no backtest re-runs** — they operate on the pre-computed trade list and complete in under 1 second.

### Bootstrap: trade order randomization

**Run 1,000 bootstrap samples** — sufficient for stable distributional estimates while keeping computation trivial. For each sample, randomly permute the trade sequence to generate a new equity curve with the same terminal P&L but different drawdown profile.

**Key outputs and thresholds:**
- **P95 maximum drawdown < 25–30%** for FX (BacktestBase institutional threshold)
- **P5 Sharpe ratio > 0** (ideally > 0.3)
- **P(drawdown > 30%) < 5%** — ruin probability gate
- **P50 recovery factor > 2.0** (net profit / max drawdown)

For strategies where trade clustering matters (burst-trading during volatility), use **block bootstrap** with block size l ≈ N^(1/3). For 1,000 trades, l ≈ 10 trades per block. Use `arch.bootstrap.optimal_block_length()` for automatic selection.

### Permutation: return shuffling for significance testing

**Hansen's Superior Predictive Ability (SPA) test** is preferred over White's Reality Check — it's more powerful due to studentized test statistics. The procedure shuffles trade returns to destroy any temporal pattern while preserving the return distribution, then compares the original strategy's Sharpe against this null distribution across **1,000 permutations**.

**Threshold: p < 0.05** to declare the strategy statistically distinguishable from random. A p-value above 0.10 is a fatal failure. Use the stationary bootstrap (Politis & Romano 1994) rather than simple shuffling to respect any remaining serial dependence.

### Stress testing: spreads, slippage, and missed trades

| Stress dimension | Levels to test | Pass criterion |
|---|---|---|
| **Spread multiplication** | 1.0×, 1.5×, 2.0×, 3.0× baseline | Profitable at 2.0× |
| **Slippage addition** | +0.1, +0.2, +0.3, +0.5 pips/trade | Profitable at +0.2 pips |
| **Missed trades** | Skip 5%, 10%, 15% randomly | Profitable at 10% skip rate |
| **Clustered losses** | Group losing trades into consecutive blocks of 5–10 | P95 drawdown < 35% |

For EUR/USD M1, actual observed slippage averages ~0.27 pips with σ ≈ 0.27 pips (StrategyQuant forum data). The 2× spread test simulates news events and Asian session widening. The 10% trade-skip test simulates VPS outages and execution failures.

Spread and slippage stress require **4–8 backtest re-runs** (negligible time). Trade-skip and loss-clustering operate on the trade list (no re-run needed).

---

## FR33: Regime analysis catches strategies that only work in one market state

A strategy that concentrates 80% of its profits in high-volatility London sessions while bleeding during the other 60% of market time is regime-dependent, not robust. Regime analysis decomposes performance by market condition to detect this fragility.

### Regime classification framework

**Primary dimension — volatility terciles**: Compute ATR-14 on daily bars, rank using percentiles over a **rolling 252-day (1-year) window**, classify into terciles at the 33rd and 67th percentile. Assign each trade to the volatility regime prevailing at its entry day. This is simpler and more robust than HMM for validation purposes.

**Secondary dimension — trend strength**: ADX-14 on daily bars. ADX < 20 = ranging, ADX 20–35 = moderate trend, ADX ≥ 35 = strong trend. For a simpler 2-bin version: ADX < 25 = ranging, ADX ≥ 25 = trending.

**Forex sessions** (UTC, non-DST): Asian 22:00–07:00, London 07:00–13:00, NY/Overlap 13:00–22:00.

### When to cross dimensions versus analyze independently

The binding constraint is **minimum trades per cell**. Require at least 30 trades per cell (absolute minimum) and prefer 50+:

- **200 trades**: Analyze volatility terciles (3 cells, ~67 each) and sessions (3 cells, ~67 each) **independently**. Do not cross dimensions.
- **500 trades**: Either 3 volatility terciles OR a 2×2 matrix ({low/high vol} × {ranging/trending} = 4 cells, ~125 each).
- **1,000 trades**: Full 2×2 matrix plus independent session analysis. Optionally 3×3 (9 cells, ~111 each).
- **2,000 trades**: Full 3×3 matrix, session × volatility (6–9 cells), and optionally a 2-state HMM overlay.

For **HMM**, if used: fit a 2-state GaussianHMM (via `hmmlearn`) on daily [log_returns, realized_vol]. Label states by inspecting `model.covars_` — the higher-variance state is the high-volatility regime. Use `covariance_type="full"` and `n_iter=100`. HMM is best treated as a supplementary check, not the primary classification.

### Pass/fail criteria for regime validation

A strategy **passes** if:
- Performance is positive in ≥ 2 of 3 volatility regimes
- No single regime shows annualized Sharpe < −1.0
- No single regime's max drawdown exceeds 2× the overall max drawdown
- Profits are not concentrated > 75% in a single regime representing < 30% of market time

A strategy **fails** if:
- Any regime with > 50 trades shows Sharpe < −1.5
- One regime contributes > 80% of drawdown while containing < 25% of trades
- The strategy is only profitable during one specific session or volatility condition

**Statistical testing**: Use the **Kruskal-Wallis H test** (non-parametric, handles non-normal trade P&Ls) to test whether performance differs significantly across regimes. If significant (p < 0.05), follow up with Dunn's test for pairwise comparisons. A significant result is acceptable if the worst regime still has positive expectancy — it means performance *varies* across regimes, not that it fails.

---

## FR34: Geometric weighted scoring with hard gates prevents false certification

### Hard gates: binary pass/fail, evaluated first

These tests have well-defined null hypotheses or absolute thresholds. Failing any one immediately rejects the strategy:

| Gate | Threshold | Rationale |
|---|---|---|
| Minimum trade count | ≥ 50 | GT-Score paper minimum; statistical estimates unstable below this |
| Aggregate OOS Sharpe | > 0 | Basic sanity; no edge if losing money forward |
| PBO | < 0.50 | Bailey & López de Prado: > 0.50 means more likely overfit than not |
| Walk-forward efficiency | ≥ 0.50 | Pardo's institutional minimum |
| MC permutation p-value | < 0.10 | Indistinguishable from random above this |

### Soft scores: continuous 0–1 metrics, geometrically aggregated

Following the GT-Score's multiplicative precedent, use a **geometric weighted mean** rather than arithmetic. A near-zero score on any component appropriately crushes the composite, preventing a strategy that aces Monte Carlo but fails CPCV from passing.

| Component | Score mapping (0–1) | Weight |
|---|---|---|
| **S_cpcv**: CPCV path consistency | Fraction of CPCV paths with positive Sharpe | 0.30 |
| **S_wf**: Walk-forward efficiency | sigmoid(WFE, center=0.7, steepness=10) | 0.20 |
| **S_mc**: Permutation significance | 1 − p_value | 0.20 |
| **S_param**: Parameter stability | Composite stability score (§FR31) | 0.15 |
| **S_regime**: Regime consistency | min(regime_sharpes) / max(regime_sharpes), clipped [0,1] | 0.15 |

**Composite confidence score**: `C = S_cpcv^0.30 × S_wf^0.20 × S_mc^0.20 × S_param^0.15 × S_regime^0.15`

| Confidence | Interpretation | Action |
|---|---|---|
| **> 0.80** | High confidence | Deploy (paper trade → live) |
| **0.60–0.80** | Moderate confidence | Watchlist, manual review |
| **0.40–0.60** | Low confidence | Paper trade only |
| **< 0.40** | Very low | Reject even if hard gates passed |

**CPCV receives the highest weight (0.30)** because the Arian et al. comparison study found it strictly dominates walk-forward in overfitting detection. Walk-forward and Monte Carlo share second tier at 0.20 each because they test genuinely different dimensions (temporal deployment vs. statistical significance). Parameter stability and regime analysis are important but more heuristic, earning 0.15 each.

### Calibration without a known-good strategy corpus

Generate **50–100 random strategies** (random entry/exit rules on the same data) and run them through the full gauntlet. The 95th percentile of random strategies' composite scores becomes the noise floor. Any real strategy must exceed this threshold. This mirrors Build Alpha's "Vs. Random" test — "if your strategy can't exceed this baseline in a meaningful way, there's a strong chance the strategy is overfit." Recalibrate quarterly as market conditions shift.

---

## Gauntlet ordering maximizes early rejection and computational efficiency

The optimal sequence runs cheapest tests first and short-circuits on fatal failures. After hard gates, expensive tests run **in parallel** to minimize wall-clock time.

### Recommended execution sequence

| Order | Layer | Cost (evals) | Wall time | Can short-circuit? |
|---|---|---|---|---|
| 1 | **Hard gates** (trade count, basic OOS metrics) | 0 | < 1 sec | Yes — FATAL if fails |
| 2 | **Parameter perturbation** (FR31) | ~500 | ~3 sec | Yes — FATAL if extreme instability |
| 3 | **MC bootstrap** on trade list (FR32 partial) | 0 (no re-run) | < 0.5 sec | Yes — FATAL if extreme tail risk |
| 4–7 | **Parallel block** — run simultaneously: | | | |
| 4 | Walk-forward validation (FR29) | ~6–28 backtests | ~30 sec | Contributes to score |
| 5 | CPCV/PBO (FR30) | ~45–252 combos | ~45 sec | Yes — FATAL if PBO > 0.60 |
| 6 | MC permutation (FR32 partial) | 0 (no re-run) | < 1 sec | Yes — FATAL if p > 0.10 |
| 7 | Regime analysis (FR33) | 0 (on existing trades) | ~5 sec | Contributes to score |
| 8 | **Confidence aggregation** (FR34) | 0 | < 0.1 sec | Final score |

**Total wall time: ~60–120 seconds** with 8+ CPU cores parallelizing steps 4–7. Well within the 2–5 minute target.

### Short-circuit rules

**Fatal failures (stop immediately):**
- Trade count < 50
- Aggregate OOS Sharpe ≤ 0
- Parameter stability CV > 1.0 (extreme instability)
- MC bootstrap P5 Sharpe < −0.5 (extreme tail risk)
- PBO ≥ 0.60 (strong overfitting evidence)
- WFE < 0.30 (severe generalization failure)
- MC permutation p > 0.10 (indistinguishable from random)

**Warning flags (continue but reduce confidence):**
- PBO 0.40–0.59
- WFE 0.30–0.49
- Parameter stability CV 0.30–0.50
- Any regime with Sharpe < −0.5

### Redundancy analysis across validation layers

Walk-forward and CPCV both test temporal robustness but from different angles — WF tests **a single chronological deployment path**, CPCV tests **a distribution across combinatorial paths**. Both are needed because a strategy can pass one but fail the other. If forced to choose one, choose CPCV. Parameter stability and Monte Carlo permutation both stress the strategy but test different properties: stability tests the **parameter surface smoothness**, permutation tests **statistical significance against a null**. They are complementary, not redundant.

**The only genuine redundancy**: MC bootstrap (trade reshuffling) and MC permutation (return shuffling) overlap in testing distributional properties of the trade stream. They can be consolidated into a single "Monte Carlo robustness" score, but keeping them separate provides clearer diagnostic information — bootstrap reveals path/drawdown risk while permutation reveals whether the signal is real.

---

## Complete configuration reference card

For quick implementation, here is every parameter in one place:

### Walk-forward (FR29)
`mode=validation_only, window=rolling, IS=9mo, OOS=3mo, step=3mo, purge=480_bars, embargo=2880_bars, WFE_pass=0.50, min_trades_per_window=30`

### CPCV/PBO (FR30)
`N=10, k=2, splits=45, paths=9, purge=480_bars, embargo=4320_bars, PBO_S=10, PBO_hard_fail=0.50, PBO_pass=0.15, metric=sharpe`

### Parameter stability (FR31)
`method=sobol_sequence, n_perturbations=500, perturbation_pct=0.10, stress_pct=0.20, sensitivity=morris_then_sobol, stability_pass=0.80`

### Monte Carlo (FR32)
`bootstrap_n=1000, permutation_n=1000, block_length=auto, spread_stress=[1.5,2.0,3.0], slippage_stress=[0.1,0.2,0.3,0.5], trade_skip=[0.05,0.10,0.15], p_value_threshold=0.05`

### Regime analysis (FR33)
`vol_method=ATR14_daily_tercile, vol_window=252d, trend_method=ADX14_daily, trend_threshold=25, sessions=[asian,london,ny], min_trades_per_regime=30, cross_dimensions=trade_count_dependent`

### Confidence scoring (FR34)
`hard_gates=[trades>=50, oos_sharpe>0, pbo<0.50, wfe>=0.50, mc_p<0.10], aggregation=geometric_weighted, weights=[cpcv=0.30, wf=0.20, mc=0.20, stability=0.15, regime=0.15], deploy_threshold=0.80`

### Key Python libraries
`skfolio.model_selection.CombinatorialPurgedCV`, `SALib` (Morris/Sobol), `scipy.stats.qmc.Sobol`, `arch.bootstrap` (stationary bootstrap, optimal block length), `hmmlearn.hmm.GaussianHMM`, `pypbo` (PBO calculation)

## Conclusion: the gauntlet as an integrated diagnostic system

The most important design insight is that no single test is sufficient. Walk-forward can pass a lucky path; CPCV can pass a strategy that works only in specific sessions; Monte Carlo can pass a parameter-fragile peak; regime analysis can pass a statistically insignificant pattern. Only the intersection of all passing criteria provides genuine evidence of a tradeable edge.

The **geometric weighted aggregation** is the key architectural choice. Unlike additive scoring where a perfect Monte Carlo result can compensate for poor CPCV performance, multiplicative scoring ensures every dimension must contribute positively. This mirrors the GT-Score's finding that multiplicative objectives produce **98% better generalization ratios** than single-metric optimization.

Three implementation priorities should guide development order. First, implement hard gates and MC bootstrap — these cost essentially nothing (no backtest re-runs) and immediately filter obviously bad candidates. Second, implement CPCV with PBO, which is the single highest-value test. Third, layer in walk-forward, parameter perturbation, and regime analysis. The confidence score formula can initially use equal weights and be recalibrated after processing 50–100 random strategies to establish empirical noise floors. The full gauntlet should run in **60–120 seconds per candidate** with parallelization, leaving ample headroom within the minutes-per-candidate constraint.