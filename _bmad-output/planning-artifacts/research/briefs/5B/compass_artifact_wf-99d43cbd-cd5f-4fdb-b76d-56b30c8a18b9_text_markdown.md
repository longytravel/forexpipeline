# Post-optimization candidate selection for algorithmic trading strategies

**The most effective approach to selecting trading strategy candidates from 10K–100K optimization results combines a four-stage hierarchical filtering funnel with TOPSIS-based ranking, Gower-distance HDBSCAN clustering, and explicit quality-diversity archives.** This framework addresses the core challenge: conventional single-objective optimization converges on narrow parameter regions that overfit historical data, while principled diversity maintenance and multi-criteria ranking surface genuinely robust strategies. The five integrated components below—equity curve metrics, ranking frameworks, clustering, diversity archives, and selection protocols—form a coherent pipeline that reduces a candidate pool of 100K to **10–35 forward-test candidates** with statistical rigor and minimal selection bias.

---

## The five metrics that actually measure equity curve quality

Beyond the Sharpe ratio, five metrics capture distinct and complementary aspects of equity curve quality for moderate-length curves (200–500 trades). Each was selected for robustness at moderate sample sizes, orthogonality to cross-validation variance penalties, and established use by quantitative practitioners.

**K-Ratio (Kestner, 1996/2013)** ranks first. It measures the linearity of log-equity growth by regressing log(cumulative equity) against trade index and dividing slope by standard error: `K = slope / std_error`. Unlike Sharpe, K-Ratio is path-dependent—two strategies with identical mean/variance can produce vastly different K-Ratios if one has erratic equity behavior. Values above **2.0** indicate strong consistency. Linear regression remains stable at 200+ observations, making this the most reliable single metric for equity curve shape. Implementation requires five lines using `scipy.stats.linregress`; no external library needed.

**Ulcer Index and Martin Ratio** capture drawdown depth and duration simultaneously through quadratic mean of all drawdowns: `UI = √(mean(DD_i²))`. The squaring mechanism disproportionately penalizes severe drawdowns—a property that max drawdown and standard deviation both lack. The derived Martin Ratio (`excess_return / UI`) serves as a superior risk-adjusted return measure. Available in QuantStats via `qs.stats.ulcer_index()`. The Ulcer Index complements CV variance penalties because CV treats upside and downside symmetrically, while UI exclusively captures downside pain.

**Deflated Sharpe Ratio (Bailey & López de Prado, 2014)** is non-negotiable for pools of 10K–100K candidates. It answers: "Given I tested N strategies, what is the probability this candidate's Sharpe ratio is genuinely positive?" The formula adjusts the expected maximum Sharpe under the null hypothesis using the number of effective trials, cross-sectional SR variance, and higher moments. Without DSR, the **False Strategy Theorem** guarantees the best candidate's apparent Sharpe is inflated by selection bias alone. Apply as a hard gate: only candidates with **DSR > 0.95** should advance.

**Gain-to-Pain Ratio (Schwager, 2012)** divides total returns by the absolute sum of losing returns: `GPR = Σ(all returns) / |Σ(negative returns)|`. Jack Schwager called this one of the most important metrics for evaluating hedge fund managers. It captures aggregate efficiency—how many dollars of profit per dollar of loss—without assuming normality. Values above **1.0** are good; above **2.0** excellent. As a ratio of sums rather than moments, GPR converges quickly and is robust at 200+ trades. Available in QuantStats.

**Serenity Ratio (KeyQuants, 2018)** combines Ulcer Index with Conditional Drawdown at Risk: `Serenity = Excess_Return / (UI × CDaR_α / Volatility)`. It captures extreme drawdown tail risk that other metrics miss entirely. AlternativeSoft demonstrated that portfolios selected by top-10 Serenity Ratio outperformed top-10 Sharpe portfolios by **50.57%** over 2011–2020. However, CDaR estimation requires sufficient drawdown episodes—use α=80% rather than 95% when trade count is below 400. Ranked fifth due to implementation complexity and moderate-sample instability.

These metrics interact with CV-based variance penalties as follows: K-Ratio captures *within-fold* path quality (CV captures *across-fold* consistency), Ulcer Index targets downside risk that symmetric variance penalties miss, GPR measures absolute efficiency orthogonal to both, and DSR corrects the multiple-testing problem inherent in large searches. Equity Curve R² (`r_value²` from the same regression as K-Ratio) serves as a fast pre-filter—drop all candidates with **R² < 0.80** before computing more expensive metrics.

| Metric | Formula | Library | Robustness (200–500 trades) | Unique capture |
|--------|---------|---------|---------------------------|----------------|
| K-Ratio | `slope / std_error` of log-equity regression | scipy (custom) | Very good | Path-dependent growth consistency |
| Ulcer Index | `√(mean(DD_i²))` | QuantStats | Good | Drawdown depth × duration |
| DSR | Adjusted SR significance test | Custom (~10 lines) | Good (requires skew/kurtosis) | Multiple-testing correction |
| Gain-to-Pain | `Σ(returns) / |Σ(losses)|` | QuantStats | Very good | Aggregate efficiency |
| Serenity | `Return / (UI × CDaR/vol)` | Custom | Moderate (needs 400+ trades) | Extreme tail drawdown risk |

---

## A four-stage filtering funnel beats pure Pareto or scalarization

Pure Pareto methods (NSGA-II) fail catastrophically with 4–8 objectives: at that dimensionality, **60–90% of candidates become non-dominated**, destroying selection pressure entirely. Pure scalarization collapses multi-dimensional trade-offs into a single number that is sensitive to weight specification. The recommended approach is a **hierarchical filtering funnel** that applies the right method at the right scale.

**Stage 1: Hard gates (100K → 5–10K).** Eliminate candidates failing non-negotiable thresholds in O(N) time. Gate on: CV-objective geometric mean > 0 across all folds, maximum fold-level drawdown < 30%, minimum trade count > 30 per fold, and equity curve R² > 0.80. This mirrors real practitioner decision-making and costs virtually nothing computationally.

**Stage 2: TOPSIS ranking (10K → 200).** Normalize all 4–8 objectives via z-score, weight using the CRITIC method (data-driven weights based on standard deviation × inter-criteria decorrelation), and rank by TOPSIS closeness coefficient. TOPSIS measures each candidate's distance from the ideal and anti-ideal points across all objectives, producing a total ordering without weight sensitivity problems. Starting weights for trading: CV-objective mean **0.30**, per-fold variance (inverse) **0.25**, equity curve quality composite **0.25**, parameter stability **0.20**. Run sensitivity analysis: perturb weights ±20% and verify the top-200 set shows Jaccard similarity > 0.7.

**Stage 3: Parameter stability filter (200 → 50).** For each candidate, evaluate ±5–10% perturbation across all parameters. Require >70% of the neighborhood to remain profitable. Rank by mean quality across the neighborhood, not just the point estimate. This catches overfitted candidates that sit on narrow peaks in the fitness landscape.

**Stage 4: Pareto analysis on reduced set (50 → 15–20).** With only 50 candidates and 2–3 key objectives (CV-mean, inverse-variance, Martin Ratio), NSGA-III non-dominated sorting works well. Use pymoo's `PseudoWeights` to select from the Pareto front, or identify knee points where marginal trade-offs are steepest.

```python
from pymoo.util.nds.non_dominated_sorting import NonDominatedSorting
from pymoo.mcdm.pseudo_weights import PseudoWeights
import numpy as np

# F: (n_candidates, n_objectives), all minimized (negate maximization objectives)
F = np.column_stack([-cv_mean, fold_variance, -k_ratio, ulcer_index])
fronts = NonDominatedSorting().do(F)
pareto_idx = fronts[0]

weights = np.array([0.30, 0.25, 0.25, 0.20])
selected = PseudoWeights(weights).do(F[pareto_idx])
```

What about quant firm practices? No major firm publicly discloses its selection framework. However, López de Prado's published work (formerly Guggenheim, now ADIA) provides the most practically relevant framework: DSR as a statistical gate, ONC clustering to determine effective independent trials, and CPCV for out-of-sample validation distributions. The recent GT-Score composite (Sheppert, 2025) achieved **98% higher generalization ratio** (0.365 vs 0.185) by embedding anti-overfitting principles directly into the objective function.

---

## HDBSCAN on Gower distances handles mixed trading parameters naturally

Trading strategy parameters mix continuous values (stop-loss distance), integers (lookback period), categoricals (indicator type), and conditional parameters (trailing stop offset only relevant when trailing mode is active). The clustering solution must handle all four types natively.

**Gower distance** is the recommended distance metric. For continuous features, it computes range-normalized Manhattan distance; for categoricals, simple matching (0 or 1); and critically, its δ-mechanism handles conditional parameters by setting irrelevant parameters to `NaN` and automatically excluding them from the distance calculation. The distance normalizes by the count of valid comparisons, making it mathematically principled for conditional dependencies. The `gower` Python library computes the full matrix: `gower.gower_matrix(df, cat_features=cat_mask)`.

**HDBSCAN** is the primary clustering algorithm. It accepts precomputed distance matrices, automatically determines cluster count via Excess of Mass extraction, detects noise points (labeling outliers as -1), and stores cluster medoids directly. Set `min_cluster_size` to approximately 1% of data points. For parameter spaces exceeding 20 dimensions, apply UMAP dimensionality reduction to 8–15 dimensions first—McInnes demonstrated that UMAP → HDBSCAN achieves **>99% accuracy** on benchmarks where raw HDBSCAN on 50+ dimensions achieves <18%.

**K-Medoids with DynMSC** serves as a strong alternative. The `kmedoids` library (Rust-backed FasterPAM) provides O(k)-fold speedup, and DynMSC automatically selects optimal k by maximizing Medoid Silhouette. The key advantage: medoids are actual data points, directly interpretable as strategy parameter sets.

For scalability beyond 30K candidates, the full Gower distance matrix becomes memory-prohibitive (~40GB at 100K). Use a two-stage approach: subsample 20–30K for clustering, then assign remaining candidates to nearest cluster medoid.

```python
import gower, hdbscan, umap
import numpy as np, pandas as pd

# Set conditional parameters to NaN
df.loc[df['trailing_mode'] == 'off', 'trailing_offset'] = np.nan
cat_features = [col in ['indicator_type', 'trailing_mode'] for col in df.columns]

# Compute Gower distance matrix
dist_matrix = gower.gower_matrix(df, cat_features=cat_features)

# Optional UMAP reduction for >15 dimensions
if df.shape[1] > 15:
    reducer = umap.UMAP(metric='precomputed', n_components=10, n_neighbors=50)
    embedding = reducer.fit_transform(dist_matrix)

# HDBSCAN clustering
clusterer = hdbscan.HDBSCAN(
    min_cluster_size=max(10, len(df) // 100),
    metric='precomputed', cluster_selection_method='eom'
)
labels = clusterer.fit_predict(dist_matrix)

# Representative selection: balance centrality + performance
for cid in range(labels.max() + 1):
    mask = labels == cid
    cluster_dists = dist_matrix[np.ix_(mask, mask)]
    centrality = 1 - cluster_dists.sum(axis=1) / cluster_dists.sum(axis=1).max()
    perf = (df.loc[mask, 'sharpe'] - df.loc[mask, 'sharpe'].min()) / df.loc[mask, 'sharpe'].ptp()
    combined = 0.5 * centrality + 0.5 * perf.values
    representative = np.where(mask)[0][combined.argmax()]
```

Visualize with UMAP 2D projections colored by cluster and sized by performance, plus parallel coordinates plots (`plotly.express.parallel_coordinates`) to profile what makes each cluster distinct.

---

## Quality-diversity archives outperform post-hoc clustering—use MAP-Elites

**The recommendation is YES: use explicit quality-diversity archives rather than relying solely on post-hoc clustering.** Three lines of evidence support this.

First, **direct trading evidence** now exists. QuantEvolve (Yun, Lee & Jeon, 2025) explicitly applied quality-diversity optimization to trading strategy generation, using a feature map aligned with investor preferences (strategy type, risk profile, turnover, return characteristics). It outperformed conventional baselines on both equity and futures markets with realistic transaction costs. The evolutionary process discovered an inverted U-shaped relationship between max drawdown and Sharpe ratio—structure that single-objective optimization would never reveal.

Second, **theoretical guarantees** are strong. Qian et al. (IJCAI 2024) proved that MAP-Elites achieves optimal polynomial-time approximation ratios on NP-hard problems where standard evolutionary algorithms require exponential time. The mechanism: diverse solutions serve as **stepping stones** that help escape local optima—directly relevant to trading's deceptive fitness landscapes where in-sample optima are out-of-sample disasters.

Third, post-hoc clustering has a **fundamental limitation**: it can only diversify among solutions the optimizer already found. If the optimizer converged to a narrow behavioral region (the typical failure mode), clustering within that region produces illusory diversity. Two strategies with very different parameters can have nearly identical trading behavior, and vice versa. Clustering on parameter values ≠ behavioral diversity.

The computational overhead is negligible. MAP-Elites archive operations (cell lookup, fitness comparison) are O(1) per evaluation. For the same evaluation budget, you get behavioral diversity essentially for free.

**Implementation with pyribs** (ICAROS Lab, USC):

```python
from ribs.archives import CVTArchive
from ribs.emitters import EvolutionStrategyEmitter
from ribs.schedulers import Scheduler

# 3 behavioral dimensions, 2000 CVT cells
archive = CVTArchive(
    solution_dim=NUM_PARAMS, cells=2000,
    ranges=[(0, 50), (0, 252), (0, 0.5)]  # trades/month, holding_days, max_dd
)
emitters = [EvolutionStrategyEmitter(archive, x0=init, sigma0=0.1, batch_size=36)
            for _ in range(3)]
scheduler = Scheduler(archive, emitters)

for _ in range(num_iterations):
    solutions = scheduler.ask()
    objectives, measures = evaluate_strategies(solutions)  # Sharpe, [freq, hold, dd]
    scheduler.tell(objectives, measures)
```

Use **CVT-MAP-Elites** (not grid-based) to avoid the exponential cell explosion with 3+ behavioral dimensions. Set archive size to 1,000–5,000 cells. The three recommended behavioral dimensions are **log trade frequency**, **log average holding period**, and **maximum drawdown**—these capture the most economically meaningful variation in strategy behavior. For expensive backtests (>1 second each), consider Surrogate-Assisted Illumination (SAIL) to reduce required evaluations by 10–100×.

The hybrid architecture integrates both approaches: run MAP-Elites during optimization to discover diverse behavioral niches, then apply post-hoc HDBSCAN clustering within behavioral regions to find parameter-space structure. This captures both behavioral diversity (which strategies *do*) and parameter diversity (how they *achieve* it).

---

## Select 10–35 candidates with 80% deterministic, 20% exploratory allocation

The forward-test selection protocol must balance statistical rigor against operational feasibility. The operative unit is **clusters, not individual candidates**—López de Prado & Lewis (2019) established that the Optimal Number of Clusters (ONC) algorithm determines the effective count of independent trials from a large pool, typically yielding **K = 5–50** for 10K–100K candidates.

**Selection count.** Forward-test 1 representative per surviving cluster plus 2–5 wild cards: typically **10–35 total candidates**. For HFT/intraday, constrain to 5–15 (higher execution costs of parallel live testing, but shorter validation needed at 4–8 weeks). For swing trading, 15–35 candidates are feasible with 3–12 months of validation.

**Deterministic vs. probabilistic split.** Fill **80% of slots** with the top-ranked DSR-passing cluster exemplar from each cluster—this is justified because DSR and PBO filtering have already vetted statistical significance. Fill the remaining **20%** using Boltzmann/softmax sampling over qualified-but-lower-ranked clusters: `P(cluster k) = exp(Score_k / τ) / Σ exp(Score_j / τ)`, with temperature τ calibrated so the top cluster has 3–5× the probability of a median cluster. Wild cards improve regime robustness: strategies appearing mediocre individually may contribute disproportionately to portfolio diversification.

**Multiple testing at the selection stage.** Since DSR already embeds FWER correction against the full N trials, the additional correction needed at the cluster level is **Benjamini-Hochberg FDR at q = 0.05** applied to cluster-level DSR p-values. This is appropriate because you are selecting multiple strategies for a portfolio, not a single winner. Additionally, verify that surviving candidates have **t-statistics > 3.0** per Harvey, Liu & Zhu (2016)—an independent cross-check.

**Avoiding selection bias requires pre-registration.** Before viewing any results, document: the exact scoring formula and weights, DSR and PBO thresholds, number of forward-test slots, deterministic/wild-card split ratio, and the random seed for stochastic selection. Implement partially blind human review—present candidates without showing overall rank or exact Sharpe; show equity curve shape, trade logic, drawdown profile, and regime analysis. Only after completing the review checklist, reveal full metrics.

The human review checklist should cover elements that automated metrics miss:

- Can you articulate *why* this strategy should work (economic mechanism, behavioral bias)?
- Does >50% of profit come from <5% of trades (concentrated fragility)?
- Do nearby parameter values produce dramatically different results (parameter cliff)?
- Does shifting entry/exit by one bar destroy performance (the "delay test")?
- Does the strategy have at least 10–20 trades per degree of freedom (Pardo's rule)?

**Complete pipeline stage-gate summary:**

| Stage | Action | Scale reduction | Key method |
|-------|--------|----------------|------------|
| 1 | Hard gates | 100K → 5–10K | Min Sharpe, max DD, min trades, R² > 0.80 |
| 2 | TOPSIS ranking | 10K → 200 | CRITIC-weighted multi-objective scoring |
| 3 | Parameter stability | 200 → 50 | Neighborhood perturbation ±5–10% |
| 4 | Pareto + clustering | 50 → 15–20 clusters | NSGA-III on 2–3 key objectives, HDBSCAN |
| 5 | DSR + BH-FDR gates | Clusters → qualified set | DSR > 0.95, BH q = 0.05, t > 3.0 |
| 6 | Selection + review | Qualified → 10–35 final | 80% deterministic, 20% softmax wild cards |

---

## Library recommendations and implementation roadmap

The complete Python toolkit spans six packages, each addressing a specific pipeline component:

- **Equity metrics**: `quantstats` (Ulcer Index, GPR, Calmar) + `scipy.stats` (K-Ratio, R² via `linregress`) + custom DSR (~10 lines)
- **Multi-objective ranking**: `pymoo` (non-dominated sorting, NSGA-III, pseudo-weights) + custom TOPSIS (~15 lines with numpy)
- **Clustering**: `gower` (distance matrix) + `hdbscan` or `sklearn.cluster.HDBSCAN` (clustering) + `kmedoids` (FasterPAM/DynMSC alternative)
- **Dimensionality reduction/visualization**: `umap-learn` (UMAP) + `plotly` (parallel coordinates, scatter)
- **Quality-diversity**: `pyribs` (CVT-MAP-Elites, CMA-ME, CMA-MAE)
- **Statistical testing**: `scipy.stats` (for DSR) + `statsmodels.stats.multitest` (BH-FDR via `multipletests`)

---

## Conclusion

The central insight across all five research areas is that **diversity is not a luxury but a structural requirement** for robust strategy selection. Post-hoc clustering on parameters provides shallow diversity; MAP-Elites provides behavioral diversity by construction; and the hierarchical funnel ensures that diversity is preserved through each filtering stage rather than accidentally eliminated by early gates.

Three findings stand out as particularly actionable. First, K-Ratio and Gain-to-Pain Ratio together capture what Sharpe ratio misses—path consistency and aggregate efficiency—while requiring only trivial computation. Second, TOPSIS with CRITIC weights provides a defensible, data-driven ranking that avoids the Pareto curse of dimensionality and the fragility of hand-tuned scalarization weights. Third, the 80/20 deterministic-exploratory split at the selection stage is the closest thing to a free lunch in this pipeline: it costs almost nothing but provides regime insurance.

The most counterintuitive recommendation is that explicit quality-diversity optimization (MAP-Elites) should replace or augment standard optimization rather than being added as a post-processing step. The QuantEvolve results (2025) and the theoretical stepping-stone guarantees (Qian et al., 2024) provide strong evidence that the strategies you never discover through single-objective optimization are exactly the ones you need when market regimes shift.