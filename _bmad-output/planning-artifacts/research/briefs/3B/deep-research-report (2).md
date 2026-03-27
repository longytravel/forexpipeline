# Research Brief RB-3B: Deterministic Backtesting & Validation Methodology

## Reproducibility and determinism in production backtesting

### What “reproducible” means in institutional practice
Across regulated finance, “reproducibility” is less about academic elegance and more about *auditability, governance, and controllability*. Supervisory guidance such as entity["organization","Federal Reserve","us central bank"] SR 11-7 frames expectations around rigorous validation, strong governance, and documentation detailed enough that independent parties can understand, replicate, and challenge results. citeturn12search1turn12search0 In the EU/UK, algorithmic trading rules and supervisory reviews emphasise testing, controlled deployment, and record keeping (inventorying algorithms/changes, evidence of testing/validation, and retained records). citeturn12search2turn12search3turn12search10turn12search11

**Practical inference for RB-3B:** even if regulators do not literally require *bit-identical* backtest outputs, the *direction of travel* is clear: you want an evidentiary chain from (data snapshot, code version, config) → (decisions/trades) → (metrics) that can survive internal challenge and external scrutiny. citeturn12search1turn12search2turn12search3

### Is bit-identical output “overkill” or “table stakes”?
Academic numerical computing literature explicitly defines reproducibility as **bitwise identical results across runs**, even when parallel scheduling and hardware resources change—precisely because non-associativity and scheduling variance break naïve expectations. citeturn27view0 A modern reproducible summation paper defines reproducibility exactly this way and explains why dynamic scheduling + floating-point non-associativity makes even summation hard to reproduce; it then proposes order-independent techniques. citeturn27view0turn27view1

In systems engineering practice, determinism is often treated as a *spectrum* rather than a binary. A widely cited engineering discussion distinguishes determinism “within one build”, “across builds”, and “across platforms”, explicitly noting that IEEE-754 conformance does **not** guarantee identical results across all conforming systems. citeturn23view2

**Recommendation: adopt a tiered reproducibility standard (so you can be “strict where it matters” without blocking delivery).**

### Proposed reproducibility standard for ClaudeBackTester
The goal is to align your “reproducibility contract” (bit-identical trade logs, FMA flags, Rayon determinism) with what is feasible and valuable.

**Tier A: Deterministic research replay (same artefact, same machine class)**  
Guarantee: identical event stream → identical decisions/trades and identical trade log bytes.  
How to achieve (core controls):
- Freeze *data snapshot* and *feature generation* inputs; point-in-time integrity is essential to avoid silent revisions contaminating backtests. citeturn39search13turn12search1  
- Freeze build artefacts (compiler version, flags, dependencies) and runtime config; this is the minimal foundation for “same inputs → same outputs”. citeturn12search1turn11view1  
- Eliminate nondeterminism from parallel reductions and map iteration ordering; Rayon documents that reduction order is “not specified”, and for floating-point operations that can make results “not fully deterministic”. citeturn25view1

**Tier B: Deterministic engine correctness (same inputs, different CPU/thread schedules)**  
Guarantee: changing thread counts / scheduling does not change outputs (or changes are bounded and explainable).  
This is the standard explicitly targeted by reproducible numerics research (order-independent methods). citeturn27view0turn27view1  
Practical options:
- Use deterministic reductions (fixed partitioning + stable combine order) *or* designed-for-reproducibility accumulators for critical aggregates. citeturn27view0turn25view1  
- If full Tier-B is expensive, apply it selectively to “decision-boundary” computations (position sizing, risk limits, any thresholded signal) and accept tolerances elsewhere.

**Tier C: Cross-platform reproducibility (x86 vs ARM / different FPUs)**  
Guarantee: same results across materially different FPUs/ABIs is *not always achievable* with naïve IEEE floats. Real-world issues include subnormal handling and flush-to-zero behaviour that may be platform-ABI dependent. citeturn43view0turn23view2  
Recommendation: treat Tier C as “nice-to-have” for V1 unless you have a concrete multi-platform deployment requirement.

### Floating-point determinism: specific pitfalls and controls
Your existing focus on **FMA flags** is well founded. FMA changes rounding semantics: it performs multiply-add with one rounding instead of two, which can change branch outcomes and assertions. citeturn23view0

Compiler flags can silently legalise algebraic rewrites and contraction:
- `-ffast-math` explicitly enables assumptions like associativity, “no NaNs/Infs”, and sets `-ffp-contract=fast` (allowing aggressive contraction). citeturn23view1  
- For Rust specifically, `rustc` exposes `-C target-feature` with `+`/`-` toggles (e.g., disabling `fma` on x86 if you choose), and documents the combining/override behaviour. citeturn11view1turn9view0

**Minimum V1 control set (practical, high impact):**
1. Ship with “no fast-math” semantics and explicitly manage FP contraction. citeturn23view1  
2. Pin CPU features (or explicitly disable `fma`) via `-C target-feature` and record the resulting target-features list in the backtest artefact. citeturn11view1turn9view0  
3. Treat parallel reductions over floats as non-deterministic unless you enforce order (Rayon explicitly warns about this). citeturn25view1  
4. Decide how you handle NaN payloads and subnormals across platforms; IEEE does not guarantee unique NaN propagation, and real platforms may flush subnormals. citeturn27view1turn43view0turn23view2

## Walk-forward and time-series validation best practices

### Walk-forward is a special case of time-series cross-validation
The general statistical framing is “rolling origin” evaluation: each test point (or test block) is evaluated only after training on prior data; future data must not be used to construct forecasts. citeturn34view0 This is the time-series analogue of cross-validation where ordering cannot be shuffled without leakage. citeturn34view0

Practitioner platforms implement this as periodic re-optimisation/retraining:
- entity["company","QuantConnect","algorithmic trading platform"] defines walk-forward optimisation as periodically adjusting logic/parameters using a trailing window and explicitly calls out the tradeoff: optimise frequently to fit recent data **vs** optimise less to reduce overfitting and improve runtime. citeturn35view0  
- entity["company","NinjaTrader","trading software company"] describes WFO as repeated (optimise on an in-sample segment → test forward on following out-of-sample segment), sliding the segments forward. citeturn35view2

### Window sizing: what “best practice” actually looks like
There is no universally optimal window length; it is a bias–variance tradeoff under nonstationarity:
- Shorter training windows adapt to new regimes but increase estimation variance and the probability of selecting noise. citeturn35view0turn29view1  
- Longer windows lower variance but risk training on regimes that no longer apply (“structural changes” / nonstationarities). citeturn29view1turn41view1  

A practical “best practice” framing is to treat window choices as *modelled hyperparameters with stability goals*, not as a single magic number, and to evaluate sensitivity across plausible window lengths rather than selecting a single optimised value. This is consistent with time-series CV guidance (you do not test on earliest observations because training sets that are too small yield unreliable forecasts). citeturn34view0

### Anchored vs rolling (expanding vs sliding)
- **Anchored / expanding windows**: keep the start fixed and grow training over time; good when the process is stable enough that older history remains relevant, and when you want lower variance. citeturn34view0turn35view0  
- **Rolling / sliding windows**: fixed-length training windows that move; good when you expect regimes to change and you prefer adaptivity. citeturn34view0turn35view0  

**Forex-specific note:** FX regimes (volatility and policy-driven shifts) can change abruptly; rolling windows often reflect operational reality better than anchored windows, but they can also *amplify overfitting* if re-optimisation is too frequent. citeturn29view1turn35view0turn41view1

### Retraining/optimisation frequency pitfalls
The most common “failure mode” is *iterating on out-of-sample until it becomes in-sample*. A backtesting protocol paper states this bluntly: modifying a model after observing OOS failure and then re-testing is “no longer an out-of-sample test”; it is overfitting. citeturn29view1turn29view2

**Operational control (V1 must-have):** treat each OOS segment as *single-use for decision-making* in your pipeline UI/automation. Store an immutable record of “this OOS was consumed by experiment X”, and prevent repeated tuning against it unless it is explicitly reclassified as in-sample. citeturn29view1turn29view2

image_group{"layout":"carousel","aspect_ratio":"16:9","query":["walk-forward validation time series cross validation diagram","purged cross validation embargo diagram finance","combinatorial purged cross validation backtest paths diagram","rolling forecasting origin cross validation illustration"],"num_per_query":1}

## CPCV beyond the original description

### CPCV’s purpose in one sentence
Combinatorial Purged Cross-Validation exists because financial labels/features often span time (e.g., event horizons, holding periods), which causes leakage in ordinary k-fold CV; CPCV adds **purging and embargoing** and then generates **multiple combinatorial backtest paths** rather than a single split. citeturn18view0turn29view2

### Practical implementation details that matter in production
A widely used open-source reference implementation in **mlfinlab** explicitly states the core invariants:
- implement CPCV from *Chapter 12* of entity["book","Advances in Financial Machine Learning","lopez de prado 2018"]; citeturn18view0  
- training is **purged** of observations overlapping test-label intervals; citeturn18view0turn29view2  
- test sets are assumed contiguous (`shuffle=False`) with no training samples in between; citeturn18view0  
- supports a percent **embargo** (a buffer after test) via `pct_embargo`. citeturn18view0turn29view2  
- includes “Stacked CPCV” for multi-asset datasets. citeturn18view0  

**CPCV implementation guide (production-focused):**

**Define “information intervals” correctly (this is where most teams go wrong).**  
Purging requires knowing the time span over which each training sample’s label/feature uses information. The mlfinlab interface models this explicitly as `samples_info_sets` (start time index → end time value). citeturn18view0  
For trading strategies, the safest mapping is often:
- label interval = from signal formation time to trade exit (or horizon end), because P&L and many features depend on what happens while a trade is “alive”. This aligns with the broader warning that leakage can occur if training uses data that overlaps the test label horizon. citeturn29view2turn18view0

**Apply both purge and embargo (not just purge).**  
The backtesting protocol literature notes leakage can remain even after naïve splitting; embargo is intended to reduce subtle contamination (market impact, delayed reactions, overlapping construction). citeturn29view2turn18view0

**Use CPCV for model selection, not just “reporting a distribution”.**  
CPCV is most valuable when it is used to:
- compare strategies/hyperparameters under consistent anti-leakage rules; citeturn29view2turn18view0  
- compute *stability* metrics across many paths (variance of Sharpe, drawdown dispersion, sign consistency), instead of focusing on the best path. This directly addresses the “winner’s curse” framing where models rarely work as well as in the backtest. citeturn29view0turn29view2

### Refinements since “classic CPCV”
**Stacked CPCV for multi-asset** is a pragmatic refinement: once you validate portfolios rather than single instruments, “overlap and leakage” can occur across assets via shared information sets; mlfinlab implements a `StackedCombinatorialPurgedKFold` specifically for this. citeturn18view0

**Production reality:** CPCV is computationally more expensive than simple walk-forward, but it addresses a key weakness of single-path validation: if you only evaluate one temporal path you can be “lucky” in regime placement. The protocol paper’s core point—data are limited in finance, so overfitting risk is structurally higher—supports investing in better resampling designs rather than relying on one split. citeturn29view0turn34view0

### Common CPCV mistakes that let overfitting through
These are the “gotchas” that tend to survive code reviews because the pipeline still *runs*:

1. **Using timestamps but not label horizons.** You purge by date indices, but your labels use forward returns/horizons; leakage persists. citeturn18view0turn29view2  
2. **Embargo set to zero by default.** You have “CPCV” in name only. citeturn18view0turn29view2  
3. **Treating CPCV as independent folds.** Paths are correlated; you must interpret distributions as *dependent* evidence, not as 30 independent p-values. This is exactly why multiple-testing control is required alongside CV. citeturn31view0turn29view2turn17view3  
4. **Selecting hyperparameters on the same CPCV paths you report as “final OOS”.** That becomes iterated OOS. citeturn29view1turn29view2

## Monte Carlo validation: what’s most valuable and what it can’t prove

### Monte Carlo in strategy validation is usually bootstrap with assumptions
A common practical implementation is to resample trades or equity changes to produce a distribution of outcomes (final equity, drawdown, etc.). The entity["company","AmiBroker","trading software company"] documentation is explicit: it creates an original list of N trades, then repeatedly samples with replacement to create alternative trade sequences and derives a distribution of equity and drawdowns. citeturn32view2

This can be valuable, but it assumes your resampling scheme is an adequate approximation of the dependence structure of returns/trades—an assumption that frequently fails in finance. citeturn33view0turn29view1

### Ranking Monte Carlo techniques by practical value for FX (V1 vs later)
**Highest value (V1 candidates):**

**Trade/equity bootstrap for path risk (but only if dependence is handled).**  
AmiBroker explicitly warns that bootstrapping a trade list can understate drawdowns if the real strategy has overlapping trades, because the bootstrap may implicitly sequentialise them; it recommends using bar-by-bar equity changes to better handle overlap. citeturn32view2  
For FX strategies that can hold multiple positions or scale in/out, prefer **equity-change resampling** or a bootstrap that preserves overlap structure. citeturn32view2

**Block/bootstrap methods for dependence (must-have if you rely on bootstrap inference).**  
The entity["book","The Stationary Bootstrap","Politis and Romano 1994"] introduces a resampling procedure for *weakly dependent stationary observations* by sampling blocks of random length (geometric), explicitly designed for time series rather than iid data. citeturn33view0turn33view1  
Inference: for financial series with autocorrelation/vol clustering, block-based bootstraps reduce the “false confidence” problem versus naive shuffle. citeturn33view0turn33view1turn41view1

**Parameter perturbation / stability stress tests.**  
This is not classic “Monte Carlo”, but it is often more diagnostic than trade shuffling: if small parameter changes destroy performance, you likely have a fragile fit. This aligns with the protocol emphasis on robustness and avoiding exaggerated positives. citeturn29view0turn29view2

**Lower value (defer unless you have a clear null model):**

**Pure trade shuffling** as a probability-of-ruin estimator can be misleading if the strategy’s edge is conditional on regime sequences (common in FX). It may either understate or overstate risk depending on the regime structure you destroy. citeturn33view0turn29view1

### “False positive rate”: how to think about it
A bootstrap/Monte Carlo test does **not** automatically give you a controlled false positive rate unless:
1. the null distribution is credible, and  
2. you correct for *selection* (how many strategies/params you tried). citeturn17view3turn17view2turn29view2turn31view0  

Monte Carlo is therefore best positioned as:
- a **robustness check** (how bad can it get under plausible reorderings/perturbations?), and  
- an input into broader multiple-testing-aware inference, not a standalone “pass/fail”. citeturn29view2turn17view2turn17view3

## Overfitting detection toolkit beyond walk-forward/CPCV/Monte Carlo

### Why your pipeline needs explicit multiple-testing control
The core academic point is blunt: **data snooping is endemic** and reusing the same dataset for model selection creates a serious chance that “good” results are luck. entity["book","A Reality Check for Data Snooping","White 2000 econometrica"] opens by defining data snooping as data reuse for inference/model selection and motivates a bootstrap-based test to assess whether the best model has genuine predictive superiority. citeturn17view3turn16view2

The modern finance multiple-testing literature argues that traditional “t > 2” cutoffs are not sufficient under multiplicity; it argues that a newly discovered factor should exceed a t-ratio of 3.0, while also warning even 3.0 can be too low because many trials are unpublished/unknown. citeturn31view0turn30view1

A backtesting protocol paper operationalises this with a concrete warning: iterated “out-of-sample” is not out-of-sample, and protocols/checklists reduce false positives. citeturn29view1turn29view2turn29view0

### Toolkit: recommended additions and priority order
Below is an “implementable toolkit” ordered by (i) incremental value over what you already have, (ii) maturity of methods, and (iii) fit to FX backtesting.

**V1 must-have additions**

**Deflated Sharpe Ratio (DSR) + Probabilistic Sharpe framing.**  
entity["book","The Deflated Sharpe Ratio","Bailey and lopez de prado 2014"] explicitly targets two inflation sources: (a) non-normal returns/short samples and (b) selection bias from multiple testing; it defines DSR as a PSR-like statistic with the threshold adjusted to reflect multiplicity (number of trials and dispersion across trials). citeturn17view2turn16view1  
**Why it matters for you:** if ClaudeBackTester has optimisation + multiple validation paths, DSR gives you a principled, pipeline-friendly way to penalise “try enough knobs until Sharpe looks great.” citeturn17view2turn29view2

**Probability of Backtest Overfitting (PBO) / CSCV.**  
entity["book","The Probability of Backtest Overfitting","Bailey et al 2015"] proposes a framework to assess the probability that backtest overfitting has occurred and introduces combinatorially symmetric cross-validation (CSCV) to estimate it; it explicitly argues that classic hold-out methods can be unreliable for investment backtests. citeturn17view1turn16view0turn16view0  
**Pipeline use:** treat PBO as an overfitting “risk score” that gates promotion from research → paper → live. citeturn17view1turn29view2

**Single-use holdout enforcement (“OOS budget”).**  
The protocol paper’s “iterated OOS is not OOS” is a governance control, not just a statistical idea. Build this into the state machine: you get a limited number of “looks” at the final holdout per strategy family. citeturn29view1turn29view2

**V1 should-have additions**

**White’s Reality Check / Superior Predictive Ability-style testing** for strategy families.  
Reality Check provides a way to test whether the best model in a search has genuine superiority over a benchmark while accounting for snooping via bootstrap. citeturn17view3turn16view2  
This is most relevant when you run large strategy sweeps (grid searches, feature subsets, model classes). citeturn17view3turn29view2

**“Placebo” and falsification tests inspired by empirical failure data.**  
A large cohort study of 888 trading algorithms on entity["company","Quantopian","quant research platform"] found that commonly reported metrics like Sharpe had very little value in predicting OOS performance (R² < 0.025) and that more backtesting iterations correlated with larger IS–OOS discrepancies. citeturn17view4turn17view5  
Practical response: build automatic placebo tests (randomised entry timing, inverted signals, shifted features) to detect strategies whose “edge” survives implausible perturbations—often a sign of leakage or data artefacts. citeturn17view4turn29view2

### Expected false positive rates: a concrete intuition you can use in gates
One reason “t ≈ 2” is a weak gate under search is that, under a simple null where test statistics are roughly standard normal, the probability of finding at least one “significant” result increases rapidly with the number of trials. This is the intuition behind both the multiple-testing paper’s higher cutoffs citeturn31view0 and the protocol paper’s warning that with 20 randomly selected strategies one is likely to exceed a two-sigma threshold. citeturn29view1turn29view2

Illustrative calculation (null ≈ Normal):
- With 20 trials, P(at least one Z>2) ≈ 37%.  
- With 100 trials, it rises to ≈ 90%.  
- Even Z>3 can appear frequently if you search enough (1000 trials → ~74%).  
These numbers are consistent with the literature’s motivation for stronger cutoffs and explicit multiplicity control. citeturn31view0turn29view1turn17view2

## Regime analysis that is practical for V1

### What “regime” methods are realistically used for
Regime methods are used for two distinct purposes:
1. **ex post diagnosis** (understand when/why the strategy worked or failed), and  
2. **ex ante adaptation** (change position sizing, switch strategy variants, or halt trading). citeturn41view1turn29view1turn29view2  

The second is harder and easier to overfit, because “if I had known the regime earlier…” is a classic hindsight trap. citeturn29view1turn29view2

### Academic anchors: Markov switching and change-point detection
Two canonical academic approaches:

**Markov switching / hidden regimes.**  
entity["book","A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle","Hamilton 1989 econometrica"] proposes modelling regime shifts as a discrete-state Markov process (Markov switching regression), providing a tractable framework for changes in regime. citeturn41view1turn41view2

**Online change-point detection (pragmatic monitoring).**  
entity["book","Bayesian Online Changepoint Detection","Adams and MacKay 2007"] defines changepoints as abrupt variations in generative parameters and derives an online algorithm to infer the most recent changepoint and run length; it explicitly notes usefulness in finance/time series contexts. citeturn41view0turn40view1

### V1 recommendation: keep it simple and “gated”
For FX strategy validation (especially as part of a backtesting approval pipeline), the most reliable V1 regime approach is:

**Regime segmentation for evaluation (not for live switching):**
- Segment history by simple, interpretable regime proxies: realised volatility buckets, trend strength proxies, or session/time-zone buckets (London/NY/Asia) if your strategy is session-dependent. This is consistent with the protocol paper’s emphasis on structural changes and model dynamics. citeturn29view1turn29view2  
- Require that performance is *not dominated* by a single regime segment (e.g., “all profits came from one crisis month”), because that is a common overfitting signature. citeturn29view0turn17view4

**Monitoring-style change detection as a guardrail:**
- Implement an online change-point monitor on key live-equivalent statistics (hit rate, slippage proxy, volatility of strategy returns). This uses the change-point idea as a “risk alarm,” not as a predictive alpha engine. citeturn41view0turn29view2

**Defer to later (nice-to-have):**
- Full Hidden Markov Models for regime prediction/strategy switching as an automated allocation decision, unless you can demonstrate stable benefits under strict non-leaky validation and single-use OOS rules. citeturn41view1turn29view1turn29view2

## Validation pipeline design, competitor comparison, and gap analysis

### Validation methodology matrix: your approach vs best practice vs competitors
The matrix below treats “our approach” as the capabilities you described (determinism contract; walk-forward + CPCV + Monte Carlo + regime analysis + confidence scoring). Where I cannot verify implementation specifics from your internal stories, I evaluate the *method category* against best-practice expectations.

| Validation area | ClaudeBackTester approach (as described) | Academic / best-practice expectation | Competitor / platform reality | Gaps and recommendations |
|---|---|---|---|---|
| Reproducibility | Bit-identical trade logs; FMA flags; Rayon determinism | Bitwise reproducibility is a recognised goal in reproducible numerics; floating-point + parallel scheduling make it non-trivial. citeturn27view0turn25view1turn23view2 | Most retail platforms do not promise bit-identical replay; they focus on feature testing. (Often no explicit determinism guarantees are stated.) citeturn35view1turn35view2 | Keep Tier-A determinism as a V1 must-have; treat cross-platform bitwise determinism as “defer unless required”. Add explicit artefact capture: compiler flags, target features, thread counts. citeturn11view1turn25view1turn23view1 |
| Walk-forward | Present | Valid as rolling-origin evaluation; must avoid iterated OOS and choose window policies based on nonstationarity and stability. citeturn34view0turn29view1 | QuantConnect and NinjaTrader support WFO and explicitly describe IS→OOS rolling. citeturn35view0turn35view2 | Add “OOS budget” enforcement and stability metrics (parameter stability, dispersion). citeturn29view1turn29view2 |
| CPCV | Present | Strong anti-leakage method when labels overlap; must implement purging + embargo correctly; interpret dependence. citeturn18view0turn29view2 | CPCV is not standard in retail tools; open-source libs exist (mlfinlab). citeturn18view0 | Add “label interval contract” (info sets), default non-zero embargo, and “no hyperparameter tuning on reported OOS paths”. citeturn18view0turn29view1 |
| Monte Carlo / bootstrap | Present | Useful for robustness given credible resampling assumptions; time-series dependence suggests block-style bootstraps. citeturn33view0turn32view2turn29view1 | AmiBroker provides trade/equity bootstrap and warns about overlapping-trade distortion. citeturn32view2 | Promote block/bootstrap variants and parameter perturbation as V1. Treat naive trade shuffles as “diagnostic only” unless dependence is preserved. citeturn33view0turn32view2 |
| Overfitting detection | Confidence scoring + regime analysis (as described) | Add explicit multiplicity controls: DSR, PBO/CSCV, Reality Check / SPA-style tests, single-use OOS. citeturn17view2turn17view1turn17view3turn29view1turn31view0 | Retail tools often claim “forward testing prevents overfitting” in marketing language. (E.g., MetaTrader’s forward test claims “parameter fitting is practically impossible” if both segments perform similarly.) citeturn35view1 | Implement DSR + PBO as first-class gates; add “number of trials attempted” tracking (required input to inference). citeturn17view2turn17view1turn29view2 |
| Regime handling | Regime analysis present | Regime shifts are real; use segmentation for diagnosis and change detection for monitoring; be cautious about predictive regime switching. citeturn41view1turn41view0turn29view1 | Most platforms provide little regime machinery out of the box. citeturn35view2turn35view1 | V1: regime segment reporting + change-point alarms. Defer full HMM switching unless validated under strict protocol. citeturn41view0turn41view1turn29view2 |

### Optimal sequencing of validation stages with gate criteria
This sequence is designed to minimise wasted computation and, more importantly, to stop “unknown unknowns” (leakage, nondeterminism, selection bias) from contaminating later evidence.

**Foundation gates (must pass before any performance claims)**
1. **Reproducibility artefact gate:** same inputs produce bit-identical trade log on repeated runs; record compiler flags/target features; reject runs where parallel reduction nondeterminism could change decisions. citeturn25view1turn11view1turn23view2turn27view0  
2. **Data integrity gate:** point-in-time snapshot + clear handling of revisions, costs, and execution assumptions; the protocol paper explicitly warns that ignoring costs undermines significance. citeturn29view1turn39search13

**Primary evidence gates (core validation)**
3. **Walk-forward (rolling origin) performance gate:** require performance consistency across folds; prohibit iterating on OOS segments. citeturn34view0turn29view1turn35view0  
4. **CPCV gate (anti-leakage multi-path):** require stable distribution across combinatorial paths; default embargo > 0; enforce correct label horizons. citeturn18view0turn29view2  

**Overfitting-control gates (selection-aware inference)**
5. **Multiplicity-adjusted metrics gate:** compute DSR and require it exceed a preset threshold; compute PBO and require it be comfortably below 0.5 (exact threshold is a policy decision; the method provides the estimate). citeturn17view2turn17view1  
6. **Strategy-family correction (optional but high-value if you do large searches):** Reality Check-style testing vs a baseline to reduce “best of many” illusions. citeturn17view3turn29view2  

**Robustness and deployment gates**
7. **Monte Carlo / bootstrap stress gate:** block-bootstrap where dependence matters; parameter perturbation stability; report tail drawdowns and failure percentiles. citeturn33view0turn32view2turn29view2  
8. **Regime robustness gate:** require the strategy is not a single-regime artefact; add change-point monitoring logic as a live guardrail. citeturn29view1turn41view0turn41view1

### “Red flags we’re missing” list (validation gaps that commonly let bad strategies through)
These are framed as concrete failure patterns because that is what actually slips through committees.

1. **Iterated OOS masquerading as validation.** If a strategy was modified after observing OOS failure and then re-tested, evidence is contaminated. citeturn29view1turn29view2  
2. **No accounting of “how many shots were taken.”** Without tracking number of trials (params, variants, feature sets), Sharpe/t-stats are inflated; DSR/PBO exist because this is endemic. citeturn17view2turn17view1turn17view3turn31view0  
3. **Single-path success.** One walk-forward path can be a lucky regime alignment; CPCV exists to generate multiple backtest paths. citeturn18view1turn18view0  
4. **Performance dominated by a small number of trades or a single regime window.** The 888-strategy cohort study found Sharpe was weakly predictive of OOS and that repeated backtesting correlates with IS–OOS divergence. citeturn17view4turn17view5  
5. **Monte Carlo that breaks the strategy’s dependence structure.** Trade shuffles that sequentialise overlapping exposures can understate drawdowns; vendors explicitly warn about this distortion. citeturn32view2  
6. **Hidden nondeterminism in FP + parallelism.** If float reductions or FMA contraction changes a threshold crossing, you can get different trades; Rayon documents reduction order is unspecified and float results can be non-deterministic. citeturn25view1turn23view0turn23view1  
7. **Cross-platform FP surprises treated as “bugs in the strategy.”** Platforms may flush subnormals or vary IEEE edge-case behaviour; if you ever run validation across heterogeneous infrastructure, you need an explicit policy. citeturn43view0turn23view2  

### Competitor validation approaches: what they do and what they miss
- **QuantConnect:** provides walk-forward optimisation tools and explicitly discusses the tradeoff between optimisation frequency and overfitting. citeturn35view0  
- **NinjaTrader:** provides walk-forward optimisation with clear IS/OOS segmentation mechanics and multiple optimisation criteria, but does not inherently solve multiplicity or backtest-overfitting accounting at the research-process level. citeturn35view2  
- **MetaTrader 5:** includes built-in forward testing and claims that if the robot is equally efficient on optimisation and forward segments “parameter fitting is practically impossible” — a claim that is not statistically defensible without accounting for multiple trials and dependence. citeturn35view1turn31view0turn17view3  
- **VectorBT ecosystem:** provides walk-forward optimisation examples (e.g., rolling splits over multiple windows) but, like most libraries, leaves multiplicity control and leakage governance to the user. citeturn38view0turn35view3turn29view2  
- **Backtrader:** provides analyzers and community patterns; walk-forward is typically user-assembled rather than a built-in, governance-driven protocol. citeturn14search4turn14search1turn14search0  

**Strategic takeaway for your roadmap:** competitors mostly implement *mechanics* (WFO, optimisation, forward segments). The academic edge—and where ClaudeBackTester can be genuinely institutional-grade—is formal leakage control (CPCV done correctly), explicit multiplicity control (DSR/PBO/Reality Check), and engineering-grade determinism that enables audit and debugging. citeturn18view0turn17view2turn17view1turn25view1turn12search3