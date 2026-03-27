# Batch optimization for noisy, mixed-parameter trading systems

**CatCMAwM run as multiple parallel instances inside a Nevergrad or direct `cmaes` harness is the strongest approach for this problem.** Your 2048-batch capacity is a major asset — but only if you fill it with 10–20 independent optimizer populations rather than one giant population. The fact that random search previously beat intelligent optimizers almost certainly traces to the old single-block IS objective, not algorithm failure: with CV-inside-objective producing a stable score, population-based evolutionary methods will reliably outperform random search. DE variants (especially L-SHADE) are a strong secondary algorithm, while TPE and GP-based Bayesian optimization are poor fits at batch size 2048.

---

## Why CMA-ES family wins this problem

CMA-ES is natively batch (population-based), handles noisy objectives through implicit averaging, and scales well to 15–30 dimensions. The key advance is **CatCMAwM** (Hamano et al., GECCO 2025) — CMA-ES with Covariance Matrix Adaptation with Margin for categorical variables — which handles continuous, integer, and categorical parameters simultaneously. It's the current state-of-the-art for mixed-variable black-box optimization, outperforming both CMAwM (integer-only extension) and TPE on benchmarks up to 20 mixed dimensions.

CMA-ES's convergence rate per evaluation is **roughly independent of population size** when using the rank-μ update. This means a population of 200 converges in the same total evaluations as a population of 13 — just in fewer, larger generations. For noisy CV-based objectives, larger populations provide natural noise averaging: the fitness ranking stabilizes because noise across candidates partially cancels out. The covariance matrix needs roughly **O(N²)** evaluations to adapt (about 400–900 for 20–30D), well within your 10K–100K budget.

CMA-ES's main limitation is **no native conditional/hierarchical parameter support**. The distribution operates over a fixed-dimensional space. Workarounds include decomposing the problem by categorical branch (run separate CMA-ES per algorithm type), padding inactive parameters with dummy values, or using an outer TPE layer for structural decisions with inner CMA-ES for continuous tuning.

For noise specifically, **LRA-CMA-ES** (Learning Rate Adaptation, Nomura et al. 2023) adapts the learning rate to maintain constant signal-to-noise ratio, letting the default population size work on noisy functions. **PSA-CMA-ES** automatically increases population size when noise or multimodality is detected. Both are available in the `cmaes` Python library.

## DE is the strongest alternative and natural complement

Differential Evolution is the other algorithm family worth running. Modern variants dominate CEC competitions: **L-SHADE** won CEC 2014, and LSHADE-SPACMA (which combines L-SHADE with a CMA-ES subpopulation) won CEC 2017. DE is inherently population-based, making it batch-native with no quality degradation.

DE's recommended population size of **5–10× dimensionality** (100–300 for 20–30D) maps cleanly to your batch architecture. L-SHADE's linear population reduction — starting large for exploration and shrinking for exploitation — is elegant for fixed budgets. DE handles noisy objectives reasonably well because its greedy parent-vs-offspring selection naturally filters noise, though it lacks CMA-ES's sophisticated covariance learning.

DE's weakness is **mixed parameter handling**: it was designed for continuous spaces. Extensions like L-SHADE MV exist for mixed variables, but they're less mature than CatCMAwM. For pure continuous or integer subspaces, DE is excellent. For categorical/conditional structures, it requires external orchestration.

**The hybrid CMA-ES + DE portfolio consistently outperforms either alone.** UMOEAs-II (CEC 2016 winner) maintains two subpopulations — one evolved by DE, one by CMA-ES — exchanging information. Your batch capacity lets you run both simultaneously without overhead.

## TPE and GP-BO are poor fits at batch 2048

TPE (Tree-structured Parzen Estimator) excels at **one thing your problem needs** — native conditional/hierarchical parameter support — but fails catastrophically at batch evaluation. TPE is fundamentally sequential: each suggestion is conditioned on all previous observations. The constant-liar workaround (assigning fake values to pending trials) works for 10–32 parallel workers but **effectively degrades to random search at batch=2048**. With 2048 "lying" points creating a dense field of pessimistic values, TPE's model becomes meaningless.

TPE also struggles with high dimensionality. Its default mode uses independent univariate KDEs that cannot capture parameter correlations. Even multivariate TPE underperforms CMA-ES on fully-active 15–30D spaces. Loshchilov and Hutter (2016) showed CMA-ES dominating TPE on a 19-parameter noisy DNN hyperparameter problem after approximately 200 evaluations.

GP-based Bayesian optimization is **not viable**: O(N³) inference cost makes it impractical beyond ~5000 observations, it degrades above 15–20 dimensions, and batch acquisition functions like qEI scale as O(q⁴) — completely infeasible for q=2048. Benchmark papers show BO libraries like Ax consuming >20,000 seconds of computational time even on 10D problems.

## Library recommendation: `cmaes` + Nevergrad, with Optuna for orchestration

Three libraries serve distinct roles in the optimal architecture:

**`cmaes` (CyberAgentAILab, ~438 GitHub stars)** provides the lowest-overhead, most capable CMA-ES implementation. It supports CatCMAwM, LRA-CMA, WS-CMA (warm starting), and IPOP/BIPOP restarts. The ask/tell interface is clean: `ask()` returns one candidate, `tell(solutions)` accepts the entire batch. It's pure Python with only NumPy as a dependency — minimal serialization footprint and negligible overhead relative to your Rust evaluation time. This is the recommended engine for the CMA-ES instances.

**Nevergrad (Meta, ~3.9K stars)** provides the algorithm portfolio framework. Its `TwoPointsDE` is explicitly designed for very high `num_workers` and is the recommended DE variant for batch=2048. Nevergrad's `NGOpt` meta-optimizer auto-selects algorithms based on problem characteristics. The ask/tell API works by calling `ask()` in a loop (not true vectorized batch, but Python overhead for 2048 calls is milliseconds). Checkpointing via `OptimizerDump` callback is built in.

**Optuna (11K+ stars)** is useful as an orchestration layer when conditional parameters are critical, since its dynamic search spaces handle conditionals via Python if/else naturally. However, its CMA-ES sampler doesn't support categorical distributions, and its TPE sampler degrades at large batch sizes. Use it for the outer structural search if needed, not as the primary optimizer.

| Feature | cmaes | Nevergrad | pymoo | Optuna |
|---|---|---|---|---|
| **CatCMAwM** | ✅ Native | ❌ | ❌ | ✅ Via OptunaHub |
| **True batch tell** | ✅ | ❌ (loop) | ✅ (`ask()` returns pop) | ❌ (loop) |
| **2048 batch viable** | ✅ | ✅ (TwoPointsDE) | ✅ | ⚠️ TPE degrades |
| **Conditional params** | ❌ | ❌ | ❌ | ✅ Dynamic spaces |
| **Algorithm variety** | CMA-ES only | 100+ algorithms | GA, DE, PSO, CMA | TPE, CMA, GP, samplers |
| **Overhead** | Minimal | Low | Low | Medium |
| **Warm starting** | ✅ WS-CMA | ❌ | ❌ | ❌ |

## Optimal batch architecture: portfolio of parallel instances

With **2048 batch slots** and **750+ evals/sec**, the architecture should fill every slot every generation:

```
2048 batch slots per generation:
├── 10 × CMA-ES (CatCMAwM), pop=128 each     → 1280 slots
│   ├── 5 instances: IPOP restarts (increasing pop on convergence)
│   └── 5 instances: random initial σ and starting points (BIPOP-style)
├── 3 × DE (L-SHADE or TwoPointsDE), pop=150  →  450 slots
│   └── Different mutation strategies per instance
├── 1 × Quasi-random sampling (Sobol/Halton)   →  200 slots
│   └── Pure exploration, fills gaps, ensures diversity
└── Reserve for re-evaluation of top candidates →  118 slots
    └── Noise reduction on the most promising solutions
```

This portfolio achieves several goals simultaneously. Multiple CMA-ES instances from different starting points discover **different local optima** — critical for downstream portfolio construction. DE instances explore differently (less correlation-aware, more diversity-preserving). Sobol sampling ensures unexplored regions aren't missed. Re-evaluation slots reduce noise on the best candidates, producing more reliable rankings.

**Population sizing rationale**: For 20D, CMA-ES default pop is ~13, but the recommended range extends to 5N=100. Using pop=128 gives **robust noise averaging** while allowing ~78 generations per 10K evaluations per instance (10K/128 ≈ 78). CMA-ES needs roughly 100N=2000 evals to adapt covariance, achievable in 16 generations at pop=128. With 100K total budget, each of 10 instances gets 10K evals — sufficient for full convergence with multiple restarts.

## Handling the hard parts: conditionals, noise, failures, and diversity

**Conditional parameters** are the thorniest issue since CMA-ES and DE lack native support. The cleanest solution is **decomposition**: if your search space has a top-level categorical like `algorithm_type ∈ {X, Y, Z}`, run separate optimizer portfolios per branch. Each branch has only its active parameters (perhaps 8–15D instead of 30D), making the optimization easier. Allocate batch budget across branches proportionally or use a multi-armed bandit (e.g., UCB1) to shift budget toward more promising branches over time.

**Noisy CV objectives** require configuration changes from CMA-ES defaults. Relax `tolfun` from 1e-11 to **1e-3 or 1e-4** (your CV scores likely have variance at this scale). Increase `tolstagnation` by 3–5× to prevent premature termination. Consider **LRA-CMA-ES** which automatically adapts the learning rate to noise level. Monitor σ (step size) — if it oscillates rather than decreasing, the algorithm is noise-limited and you should increase population size or use re-evaluations.

**Failed evaluations** (Rust crashes on invalid candidates) should be handled by assigning `float('inf')` as the fitness. For CMA-ES, this preserves population size without distorting the covariance update too much — the failed candidate simply ranks worst. For DE, the greedy selection ensures the parent survives. Track failure rate: if >10% of candidates fail, the search space bounds need tightening or constraint handling needs improvement. The `cmaes` library supports ask/tell with resampling for NaN returns.

**Population diversity for downstream clustering** is achieved through the multi-instance architecture. After optimization, collect all solutions across all instances with fitness above a threshold (e.g., top 25%). Apply **k-means clustering** on the parameter vectors with k = desired portfolio size. Select the best solution from each cluster. This yields diverse, high-performing parameter sets naturally. For a more principled approach, **MAP-Elites** (quality-diversity optimization) maintains a grid of elite solutions across user-defined feature dimensions — potentially trading metrics like average holding period or trade frequency.

## Convergence detection and warm-starting strategy

Standard CMA-ES termination criteria (`tolfun`, `tolx`, `NoEffectAxis`) trigger appropriately on clean objectives but **fire prematurely on noisy ones**. Recommended convergence detection for your setup:

- **Primary signal**: σ drops below a threshold and stops decreasing for 20+ generations (the optimizer has "zoomed in" as far as noise permits)
- **Secondary signal**: Running average of generation-best fitness over last 50 generations shows <0.1% improvement rate
- **Never stop early with budget remaining** — always restart. BIPOP-CMA-ES restarts with alternating large and small populations, naturally exploring different regions

**Warm starting** is valuable between optimization campaigns. The `cmaes` library supports `source_solutions` — a list of (parameters, fitness) pairs from prior runs used to initialize the distribution's mean and covariance. This is **WS-CMA-ES** (Nomura et al., AAAI 2021). Checkpointing via pickle after every generation costs negligible time relative to your Rust evaluation overhead. Save: mean vector, covariance matrix, σ, evolution paths, generation counter, best-so-far.

## Trading-specific considerations that matter

The shift from single-block IS to **CV-inside-objective (mean − λ·std across K folds)** is the critical fix. This mirrors established practice: López de Prado's Combinatorial Purged Cross-Validation (CPCV) generates distributions of out-of-sample performance rather than single estimates. Your mean − λ·std formulation is formally equivalent to **robust optimization under ellipsoidal uncertainty** — higher λ trades peak performance for stability, which is exactly what prevents the "optimizer's curse" where in-sample Sharpe ratios bear no relation to out-of-sample performance.

Professional quant firms are secretive about specifics, but publicly available information suggests most use **ensembles of diverse strategies** rather than single optimized parameter sets. DE Shaw describes "proprietary optimization technology to construct dynamically evolving investment portfolios." Headlands Technologies' blog describes researchers whose primary job is "optimal settings for everything, or automated ways of optimizing them." The community consensus (Ernest Chan, López de Prado, QuantConnect forums) emphasizes that **parameter plateaus matter more than parameter peaks** — a broad region of parameter space yielding consistent results is worth far more than a sharp optimum.

With 15–30 parameters, overfitting risk is real even with CV-inside-objective. Mitigations: compute the **Deflated Sharpe Ratio** to account for multiple testing (Bailey & López de Prado, 2014), prefer parameter sets near the center of high-performing clusters rather than at extremes, and always hold out a final test period that the optimizer never touches.

## Conclusion

The recommended stack is **`cmaes` library (CatCMAwM) for the CMA-ES engine + Nevergrad (TwoPointsDE) for the DE engine**, running as a portfolio of 10–15 parallel instances that fill your 2048-batch capacity. This architecture exploits your throughput advantage (750+ evals/sec) while maintaining solution diversity for downstream portfolio construction.

Three configuration choices matter most: **(1)** population size of 100–200 per instance (not the default 13), balancing noise averaging against generation count; **(2)** BIPOP restart strategy to explore multiple basins of attraction; and **(3)** relaxed termination tolerances (`tolfun` ≥ 1e-3) to prevent premature convergence on noisy CV objectives. Handle conditional parameters through branch decomposition rather than forcing them into algorithms that don't support them natively.

The key insight from your experience — random search beating intelligent optimizers — was indeed an objective-function problem, not an algorithm problem. With CV-inside-objective providing a stable, meaningful score, CMA-ES and DE will show clear improvement over random search within the first 2000–5000 evaluations. The question is no longer "do optimizers work?" but "how do we extract maximum diversity and robustness from a well-functioning optimizer?" — and the multi-instance portfolio architecture answers that directly.