# AI-powered narrative generation for backtest analysis

**LLM-driven narrative generation transforms raw backtest metrics into decision-ready intelligence — a capability no retail or institutional platform currently provides end-to-end.** The core technical pattern is a multi-stage pipeline where deterministic code computes all metrics, an LLM performs anomaly detection and narrative synthesis grounded in structured JSON, and post-generation verification ensures zero hallucinated numbers. This approach bridges the gap between the exhaustive metrics of QuantStats/VectorBT and the institutional-grade "strategy cards" modeled on ML model cards, aerospace readiness reviews, and clinical case reports. The key academic foundations — Bailey & López de Prado's Deflated Sharpe Ratio, Combinatorial Purged Cross-Validation (CPCV), and regime-conditional decomposition — provide the statistical rigor that prevents AI narratives from becoming dangerously overconfident.

---

## 1. The Python backtesting metrics ecosystem is mature but narrative-blind

### QuantStats: the metrics API for AI pipelines

QuantStats (ranaroussi/quantstats, **~6.9k GitHub stars**, Apache 2.0, actively maintained through 2025) is the de facto standard for Python backtest analysis. Its architecture across three modules — `qs.stats`, `qs.plots`, `qs.reports` — makes it uniquely suited as the metrics computation layer for an AI narrative system. Every metric is individually callable as a function returning a scalar or small DataFrame, making programmatic extraction into LLM prompts trivial.

The complete QuantStats metrics catalog spans **60+ individual calculations** across six categories:

- **Risk-adjusted ratios**: Sharpe, Sortino, Calmar, Omega, Information Ratio, plus autocorrelation-corrected "smart" variants (Smart Sharpe, Smart Sortino) and the **Probabilistic Sharpe Ratio** — the probability that observed Sharpe exceeds a benchmark
- **Risk metrics**: Volatility, Max Drawdown, VaR (99%), CVaR/Expected Shortfall (99%), Ulcer Index, Risk of Ruin
- **Distribution metrics**: Skewness, Kurtosis, Tail Ratio, Outlier Win/Loss Ratios
- **Trade-level proxies**: Win Rate, Profit Factor, Payoff Ratio, Kelly Criterion, CPC Index, Common Sense Ratio, Consecutive Wins/Losses
- **Regression/factor metrics**: Alpha, Beta (via OLS), R², Rolling Greeks
- **Advanced**: Monte Carlo simulation (configurable iterations) producing CAGR, drawdown, and Sharpe distributions; Drawdown Details DataFrame with start/valley/end/duration for every drawdown

The HTML tear sheet (`qs.reports.html()`) generates a self-contained report with a **two-column metrics table** (Strategy vs. Benchmark), year-over-year returns comparison, and **17 plot types** including monthly heatmaps, distribution overlays, rolling Sharpe/Sortino/Volatility, underwater plots, and Monte Carlo distributions. The `template_path` parameter allows fully custom HTML templates.

```python
# Core integration pattern: metrics extraction for LLM pipeline
import quantstats as qs

metrics = {
    'sharpe': qs.stats.sharpe(returns),
    'sortino': qs.stats.sortino(returns),
    'max_drawdown': qs.stats.max_drawdown(returns),
    'calmar': qs.stats.calmar(returns),
    'var_99': qs.stats.var(returns),
    'cvar_99': qs.stats.cvar(returns),
    'win_rate': qs.stats.win_rate(returns),
    'profit_factor': qs.stats.profit_factor(returns),
    'kelly': qs.stats.kelly_criterion(returns),
    'skew': qs.stats.skew(returns),
    'kurtosis': qs.stats.kurtosis(returns),
    'prob_sharpe': qs.stats.probabilistic_sharpe_ratio(returns),
    'drawdown_details': qs.stats.drawdown_details(returns).to_dict(),
}
# Feed metrics dict directly to LLM as structured JSON
```

### VectorBT: the backtesting engine with built-in QuantStats bridge

VectorBT's open-source version (v0.21.0, NumPy + Numba-accelerated) provides the `Portfolio` class as its analysis core, constructed via `from_signals()`, `from_orders()`, or `from_order_func()`. Its `pf.stats()` method produces **28 default metrics** including trade-level statistics (Best/Worst Trade, Avg Winning/Losing Trade Duration, Profit Factor, Expectancy).

The built-in **QSAdapter** (`vectorbt.returns.qs_adapter`) bridges directly to QuantStats — `pf.qs.sharpe()`, `pf.qs.plot_snapshot()`, `pf.qs.metrics_report()` — with automatic frequency alignment. VectorBT excels at vectorized parameter sweeps, testing thousands of parameter combinations simultaneously and producing heatmap-ready indexed results. Custom metrics use a tuple-based `StatsBuilderMixin` pattern, enabling per-call or global metric extension.

VectorBT PRO (commercial, invite-only) adds expanding trade metrics (MAE/MFE over time), simulation date-range analysis, pattern detection, and **1000× faster rolling metrics** than QuantStats.

### Pyfolio's legacy and what it got right

Pyfolio (Quantopian, now maintained as `stefan-jansen/pyfolio-reloaded`, v0.9.7) established the gold standard with **seven distinct tear sheet types**: full, returns, positions, round-trip, interesting-times, Bayesian, and capacity. Two features remain unmatched:

**Bayesian tear sheets** used PyMC3 MCMC sampling with a Student-T model to produce **posterior distributions** for Sharpe ratio, mean returns, and volatility — providing probability distributions instead of point estimates. The Bayesian cone plot projected forward returns with uncertainty bands (wider cone = less data = more uncertainty). This pattern of expressing metric uncertainty rather than point estimates is directly applicable to LLM narrative generation.

**Interesting-times tear sheets** automatically overlaid strategy performance during hardcoded crisis events (Lehman Brothers, Flash Crash, EU debt crisis, etc.) — a regime-analysis proxy that QuantConnect later adopted.

Empyrical-reloaded (`stefan-jansen/empyrical-reloaded`) remains the pure functional metrics engine behind pyfolio, with rolling metric variants (`roll_sharpe_ratio`, `roll_alpha_beta`, etc.) and Fama-French data loading.

### Critical gap: no framework includes regime detection

**None of the core Python backtesting frameworks include built-in regime detection.** The standard integration pattern is external: use `hmmlearn.GaussianHMM` or `statsmodels.MarkovRegression` to classify periods as bull/bear/neutral, then compute QuantStats metrics per regime subset. VectorBT PRO's `sim_start`/`sim_end` parameters enable regime-windowed metric computation without re-simulation.

| Library | Status (2026) | Strengths | Limitations |
|---------|:---:|---|---|
| QuantStats | ✅ Active (v0.0.81) | 60+ metrics, HTML tearsheet, pandas extension | No regime analysis, no trade-level data |
| VectorBT OSS | ⚠️ v0.21.0 frozen | Vectorized parameter sweeps, QS bridge | Commercial features in PRO only |
| Pyfolio-reloaded | ⚠️ Low activity | Bayesian analysis, positions/transactions | PyMC3 dependency issues |
| Empyrical-reloaded | ⚠️ Maintained | Pure functional API, rolling metrics | Minimal feature development |
| Backtrader | ⚠️ Stable | True trade-level analysis, PyFolio bridge | Limited visualization, event-driven only |

---

## 2. Platform comparison reveals a universal narrative gap

### QuantConnect leads with AI integration but lacks automated interpretation

QuantConnect presents backtest results through runtime statistics banners, built-in charts (equity, drawdown, exposure, capacity), and a comprehensive **Overall Statistics table** including Probabilistic Sharpe Ratio, Estimated Strategy Capacity, and Portfolio Turnover. The LEAN Report Creator generates professional HTML/PDF tear sheets with crisis event overlays, rolling Sharpe/Beta (6 and 12-month), and monthly return heatmaps.

QuantConnect's **Mia V2** (launched 2025-2026) is the most advanced AI integration in retail trading: a fully agentic assistant connected via MCP (Model Context Protocol) that can create strategies, run backtests, debug errors, analyze results, and review live algorithms. Their official MCP server bridges Claude, GPT, and Copilot to the QuantConnect API. However, **Mia focuses on strategy development and debugging, not systematic narrative generation or anomaly detection for backtest results.**

### Competitive feature matrix

| Capability | QuantStats | QuantConnect | MT5 | NinjaTrader |
|---|:---:|:---:|:---:|:---:|
| Sharpe / Sortino / Calmar | ✅ | ✅ | Sharpe only | ✅ |
| Probabilistic Sharpe | ✅ | ✅ | ❌ | ❌ |
| Rolling metrics over time | ✅ | ✅ | ❌ | ❌ |
| Crisis event analysis | ❌ | ✅ | ❌ | ❌ |
| Monte Carlo simulation | ✅ | ❌ | ❌ | ✅ |
| MAE/MFE trade analysis | ❌ | ❌ | ❌ | ✅ |
| 6-type drawdown decomposition | ❌ | ❌ | ✅ | ❌ |
| Benchmark comparison | ✅ | ✅ | ❌ | ❌ |
| API/programmatic access | ✅ (Python) | ✅ (REST) | ❌ | Limited |
| AI/LLM integration | ❌ | ✅ (Mia V2) | ❌ | ❌ |
| **Narrative interpretation** | **❌** | **❌** | **❌** | **❌** |
| **Automated anomaly detection** | **❌** | **❌** | **❌** | **❌** |
| **Regime-conditional analysis** | **❌** | **❌** | **❌** | **❌** |
| **Deployment recommendation** | **❌** | **❌** | **❌** | **❌** |

The bottom four rows represent the **AI narrative generation opportunity** — capabilities that no platform provides today and that constitute the proprietary value of a narrative generation system.

### Ten gaps AI narrative generation fills

The research identified ten specific gaps across all retail platforms: (1) no narrative interpretation of raw numbers, (2) no automated red flag / anomaly detection, (3) no cross-backtest comparative analysis, (4) no factor attribution explaining *why* a strategy works, (5) no regime-conditional risk analysis, (6) no forward-looking risk assessment, (7) no trade clustering / pattern analysis, (8) no actionable next-step recommendations, (9) limited overfitting detection beyond QuantConnect's PSR, and (10) no execution quality preview. Professional quant shops address these through dedicated risk managers and portfolio managers reviewing results — AI narrative generation democratizes this for the solo trader.

---

## 3. MLflow and W&B patterns translate directly to strategy cards

### From model cards to strategy cards

ML model cards (Mitchell et al., 2019) define a **9-section documentation standard**: Model Details, Intended Use, Factors, Metrics, Evaluation Data, Training Data, Quantitative Analyses, Ethical Considerations, and Caveats. Hugging Face's implementation uses YAML metadata headers plus Markdown body sections. Google's Model Card Toolkit provides JSON schemas with Jinja2 rendering.

The model card pattern adapts to trading strategy evaluation by mapping ML concepts to quant concepts:

| Model Card Section | Strategy Card Equivalent |
|---|---|
| Model Details | Strategy identity, parameters, asset class, timeframe |
| Intended Use | Target markets, in-scope conditions, capital requirements |
| Factors (performance disaggregation) | **Regime-disaggregated metrics** (bull/bear/sideways Sharpe) |
| Metrics | Core metrics + robustness tests (CPCV, Monte Carlo) |
| Evaluation Data | Out-of-sample period, walk-forward windows |
| Training Data | In-sample period, data source, survivorship handling |
| Ethical Considerations → | **Anomaly & Red Flag scan** (overfitting, bias signatures) |
| Caveats & Recommendations | Deployment conditions, kill-switch criteria, monitoring plan |

### Experiment tracking patterns that work for backtests

MLflow treats each experiment run as a record with parameters, time-series metrics, tags, and artifacts. This maps directly: **each backtest = one MLflow run**, with strategy parameters as `log_param()`, performance metrics as `log_metric()`, and equity curves/trade logs as artifacts. The Model Registry with aliases ("champion", "staging", "archived") becomes a strategy registry with promotion workflows.

W&B adds three patterns particularly valuable for strategy evaluation:

- **W&B Reports**: WYSIWYG documents with embedded live experiment panels — the closest existing pattern to narrative-wrapped evidence bundles. Reports combine Markdown text, LaTeX, and dynamically-linked charts into sharable decision documents.
- **Programmatic alerts** via `run.alert()`: Trigger Slack/email notifications when metrics cross thresholds — directly applicable to flagging suspicious backtest results (Sharpe > 3.0, unrealistic drawdown, etc.).
- **Registry automations**: Trigger workflows when artifact versions are created or aliases change — enabling automated strategy card generation when a new backtest completes.

### Cross-domain evidence bundle patterns

The research identified compelling parallels across domains:

- **Aerospace Test Readiness Reviews (TRR)**: NASA uses checklist-based evidence packages with entrance/exit criteria, traceability of tests to requirements, and risk matrices. The pattern of "objective evidence must demonstrate coherence between state, exposure history, and chosen action" maps directly to strategy validation.
- **Clinical case reports**: The structure Introduction → Presentation → Findings → Discussion → Conclusion translates to Hypothesis → Strategy Design → Backtest Metrics → Alternative Explanations → Deployment Decision.
- **Legal evidence bundles**: Organized collections of exhibits supporting a specific argument, with chain-of-custody tracking — analogous to data provenance and code versioning for backtest reproducibility.

The synthesis is a **two-layer strategy card**: machine-readable YAML metadata (metrics, lineage, flags) plus human-readable Markdown narrative (analysis, evidence, recommendation). This mirrors Hugging Face's model card format exactly.

---

## 4. Academic foundations for rigorous AI-generated narratives

### Bailey & López de Prado's overfitting framework is non-negotiable

Three papers form the statistical backbone of any credible backtest analysis system:

**The Deflated Sharpe Ratio (DSR)** (Bailey & López de Prado, 2014) corrects for two sources of Sharpe inflation: selection bias under multiple testing, and non-normally distributed returns. It incorporates the number of independent experiments tried, the variance of Sharpe ratios across experiments, sample length, skewness, and kurtosis. **Any AI-generated narrative that reports a Sharpe ratio without acknowledging the number of trials is fundamentally misleading.**

**The Probability of Backtest Overfitting (PBO)** (Bailey, Borwein, López de Prado & Zhu, 2015) uses combinatorial symmetric cross-validation to estimate the probability that an in-sample-optimal strategy underperforms out-of-sample. It partitions data into S equal subsets and evaluates all C(S, S/2) training/testing combinations. PBO > 0.5 means the strategy is more likely overfit than not.

**Combinatorial Purged Cross-Validation (CPCV)** (López de Prado, 2018) addresses three Walk-Forward pitfalls: single path dependency, regime bias, and data waste. CPCV generates C(N,k) possible train/test splits with purging (removing overlapping labels) and embargoing (buffer = 0.01T after each test fold), producing a **distribution of performance metrics** rather than a single point estimate. Empirical comparison (ScienceDirect, 2024) demonstrated CPCV's "marked superiority" in false discovery prevention over traditional Walk-Forward, with novel variants (Bagged CPCV, Adaptive CPCV) showing further improvement.

**Practical threshold from Harvey & Liu**: Apply a **50% Sharpe haircut** as a rule of thumb. If Sharpe < 1.0 after haircutting, the strategy likely has no real edge. Harvey, Liu & Zhu (2016) propose raising the t-statistic threshold from 2.0 to **3.0** to account for multiple testing in factor discovery.

### Multiple hypothesis testing corrects the "best of N" problem

| Test | Purpose | Key Advantage | Implementation |
|---|---|---|---|
| White's Reality Check (2000) | Tests if best model has predictive superiority over benchmark | Bootstrap-based, accounts for dependence | Python `arch` library |
| Hansen's SPA Test (2005) | Improves on White's RC, avoids least favorable configuration | More powerful with many irrelevant models | Python `arch` library |
| Step-SPA Test (Hsu & Kuan, 2010) | Identifies *all* significant models, not just whether any exist | Controls familywise error rate | Custom implementation |
| Model Confidence Set (Hansen et al., 2010) | Sequentially eliminates worst models, leaves equal-quality set | Provides a set of plausible "best" models | R `MCS` package |

### Monte Carlo complements Walk-Forward

Monte Carlo bootstrap resampling generates thousands of alternative equity curves from a single backtest's trade list. Professional standards require **≥1,000 iterations for basic analysis, 5,000-10,000 for final validation**, with ruin probability threshold < 1-5%. Critical insight from Kevin Davey (World Cup Trading Champion): **median Monte Carlo drawdown is typically 2-3× the backtest maximum drawdown**. Monte Carlo and Walk-Forward are complementary — WF detects overfitting to specific regimes, MC stress-tests execution robustness.

### LLMs for financial analysis: promising but regime-blind

Kim, Muhn & Nikolaev (2024) demonstrated that **GPT-4 can outperform human financial analysts** in predicting earnings changes from financial statements alone, with trading strategies based on GPT predictions yielding higher Sharpe ratios. However, Li et al. (2025) provide the critical counterpoint: **LLM-based strategies underperform in bull markets** (excessive conservatism) and suffer disproportionate losses in bear markets (inadequate risk control). Their conclusion — "regime-awareness and adaptive risk management are more critical than increasing architectural complexity" — directly informs narrative generation design.

Domain-specific models (BloombergGPT, 50B parameters, $2.67M training cost; FinGPT, open-source, ~$300 fine-tuning) demonstrate that financial fine-tuning improves NLP tasks but doesn't solve the fundamental challenge of grounded numerical reasoning. The FAITH framework (2025) found that financial hallucinations are often **mechanical** — column shifts in tables, unit swaps (millions to billions) — rather than semantic, suggesting that structured JSON input with explicit labels is the primary defense.

### XAI techniques for explaining strategy performance

SHAP is the dominant XAI technique in finance (most widely used across 138 reviewed articles per Yeo et al., 2024). For trading strategy evaluation, SHAP values can explain *why* specific buy/sell/hold actions were taken at given time points (Kumar & Satapathy, 2022). The practical application: decompose strategy returns into feature contributions, enabling narratives like "72% of the strategy's alpha is attributable to momentum factor exposure, with the remaining 28% from mean-reversion signals during high-VIX periods."

The EU AI Act and GDPR Article 22 now mandate explainability rights, making XAI integration not just technically valuable but potentially a regulatory requirement for any AI-assisted trading decision system.

---

## 5. The AI narrative generation pipeline: architecture and prompting

### Multi-stage pipeline eliminates hallucination risk

The core principle: **never let the LLM compute metrics**. All Sharpe ratios, drawdowns, and statistical tests must be computed by deterministic Python code and injected as structured JSON. The LLM's role is interpretation, pattern recognition, and narrative synthesis — not arithmetic.

```
Stage 1: DATA PREPARATION (Deterministic Python — No LLM)
├── Parse raw backtest output → structured JSON
├── Compute all derived metrics via QuantStats
├── Run statistical tests (normality, stationarity, regime detection)
├── Generate parameter sensitivity surface data
├── Compute benchmark comparisons
└── Output: strategy_data.json (complete, verified)

Stage 2: ANOMALY DETECTION (LLM Call #1 — Focused)
├── Input: strategy_data.json + anomaly checklist prompt
├── Model: Claude at temperature 0.1-0.2
├── Output: JSON array of {flag, severity, evidence, confidence}
└── Post-processing: Code validates all referenced numbers

Stage 3: NARRATIVE GENERATION (LLM Call #2 — Structured)
├── Input: strategy_data.json + anomaly results + narrative template
├── Model: Claude at temperature 0.3
├── Output: JSON with narrative sections per template
└── Post-processing: Code verifies every cited number matches source

Stage 4: VERDICT & CONFIDENCE SCORING (LLM Call #3)
├── Input: All above + deployment criteria
├── Output: recommendation, confidence score, conditions
└── Post-processing: Sanity check verdict against anomaly severity

Stage 5: ASSEMBLY (Deterministic Python)
├── Combine all outputs into Strategy Card JSON
├── Generate Markdown/PDF report with code-generated charts
└── Output: Complete Evidence Pack
```

### Prompting patterns ranked by effectiveness

The research identified six prompting techniques with clear reliability ordering for backtest analysis:

**Chain-of-Thought + Program-of-Thoughts hybrid** is the gold standard. CoT improves reasoning (2.3× accuracy on math benchmarks per Wei et al., 2022), while PoT delegates computation to Python interpreters, outperforming CoT by **~20% on financial datasets** (FinQA/ConvFinQA). The LLM reasons about *what* to interpret, deterministic code handles *how* to compute.

**Role prompting** sets the analytical persona. The system prompt establishes a "senior quantitative analyst performing due diligence" with explicit hard rules: never fabricate numbers, always cite data, flag missing metrics, express confidence levels. This framing activates the model's strongest analytical capabilities.

**Few-shot exemplars** with scored examples calibrate output quality and format consistency. Including one example of a "good" strategy assessment and one "problematic" strategy assessment teaches the model the expected reasoning depth and scoring calibration.

**JSON Schema constraints** for structured output prevent free-form hallucination. The hybrid JSON approach — structured fields for metrics and assessments with embedded narrative text fields — enables both machine parsing and human readability.

**Self-consistency** (sampling multiple reasoning paths at low temperature) reduces hallucination in subjective judgments. Running the anomaly scan twice with slightly different prompt formulations and flagging divergent conclusions as LOW confidence provides a practical calibration mechanism.

### The system prompt template

```
You are a senior quantitative analyst performing due diligence on a 
trading strategy backtest. You must:

1. ONLY reference numbers explicitly provided in the data below
2. Never fabricate, interpolate, or assume any metric not provided
3. Show reasoning step-by-step before making any judgment
4. Flag metrics that are missing but needed for complete assessment
5. Express confidence levels (HIGH/MEDIUM/LOW) for each conclusion
6. Compare every metric against the benchmark ranges below

BENCHMARK RANGES FOR RETAIL STRATEGIES:
- Sharpe Ratio: 0.5-1.5 realistic; >2.0 suspicious; >3.0 almost certainly overfit
- Profit Factor: 1.3-2.0 realistic; >3.0 suspicious
- Max Drawdown: Expect 2-3x worst historical DD in live trading
- Win Rate: Context-dependent; >80% on trend strategies is suspicious
- Minimum trades for statistical significance: 200+
```

### The CoT reasoning chain for each metric

```
For each metric, follow this exact reasoning chain:

1. STATE the metric name and its value from the data
2. COMPARE to the benchmark range provided above  
3. CONTEXTUALIZE — what does this mean for this specific strategy type?
4. ASSESS — is this a strength, concern, or red flag?
5. CITE — what other metrics support or contradict this assessment?

Example: "The Sharpe ratio is 1.34 [STATE]. This falls within the 
realistic range of 0.5-1.5 [COMPARE]. For a mean reversion strategy on 
SPY with daily rebalancing, this is consistent with published research 
showing mean reversion edges typically deliver Sharpe 0.8-1.5 
[CONTEXTUALIZE]. This is a moderate strength [ASSESS]. The Sortino of 
1.89 suggests upside volatility exceeds downside, consistent with the 
mean reversion profile [CITE]."
```

### Anti-hallucination verification pipeline

Post-generation verification is a code-side responsibility, not an LLM responsibility:

```python
def verify_narrative(narrative_json, source_data):
    """Cross-check every number in LLM output against source data."""
    errors = []
    cited_numbers = extract_numbers_from_text(narrative_json)
    
    for number, context in cited_numbers:
        if not exists_in_source(number, source_data, tolerance=0.01):
            errors.append(f"Number {number} in '{context}' not in source")
    
    # Logical consistency check
    if narrative_json['verdict']['recommendation'] == 'DEPLOY':
        if any(f['severity'] == 'critical' for f in narrative_json['red_flags']):
            errors.append("DEPLOY contradicts CRITICAL red flags")
    
    return errors
```

Key grounding techniques from the literature: (1) inject data as structured JSON, never prose; (2) explicit grounding instruction — "If data is insufficient, state 'INSUFFICIENT DATA' rather than estimating"; (3) temperature 0.1-0.3 for all factual analysis; (4) the PHANTOM/VeNRA architecture where the LLM acts as "Code Architect" over verified fact ledgers rather than performing arithmetic directly.

---

## 6. Anomaly detection methods ranked by reliability

### The forensic backtest audit checklist

The research consolidated anomaly detection patterns from Bailey & López de Prado, Build Alpha, Brian G. Peterson's practitioner guidelines, and QuantConnect's implicit validation into a ranked checklist:

| Priority | Red Flag | Detection Method | Reliability | False Positive Rate |
|:---:|---|---|:---:|:---:|
| 1 | **Sharpe > 3.0** | Threshold check | ★★★★★ | Very Low |
| 2 | **Large IS/OOS performance gap** (ratio > 2.0) | Compare in-sample vs. out-of-sample Sharpe | ★★★★★ | Low |
| 3 | **Smooth equity curve** (no meaningful drawdowns) | Drawdown frequency + depth analysis | ★★★★★ | Very Low |
| 4 | **Number of trials not disclosed** | Check if DSR/PBO computed | ★★★★★ | Low |
| 5 | **Parameter cliff edges** | ±10% variation → performance collapse | ★★★★☆ | Low |
| 6 | **Look-ahead bias signatures** | Entries at optimal prices, returns before signals | ★★★★☆ | Low |
| 7 | **Survivorship bias** | Delisted instruments excluded from universe | ★★★★☆ | Low |
| 8 | **Unrealistic fill assumptions** | Fills at exact OHLC, volume vs. position size | ★★★★☆ | Low |
| 9 | **Regime-concentrated returns** (>70% from one regime) | Per-regime return attribution | ★★★★☆ | Medium |
| 10 | **Too many free parameters** (>4-5) | Parameter count vs. trade count ratio | ★★★★☆ | Medium |
| 11 | **Performance cliff at specific dates** | Rolling window Sharpe, equity curve inflections | ★★★★☆ | Medium |
| 12 | **Profit driven by few outlier trades** | Remove top 5 trades, recompute Sharpe | ★★★☆☆ | Medium |
| 13 | **Insufficient trades** (<200) | Simple count | ★★★★★ | Low |
| 14 | **No losing months/years** | Calendar analysis | ★★★★☆ | Low |
| 15 | **Win rate > 80% on trend strategies** | Strategy-type-conditional threshold | ★★★☆☆ | Medium-High |

The first four items are **critical-severity by default** — any one should cap the overall confidence score at MEDIUM regardless of other metrics. Items 5-11 are **warning-severity**, requiring explanation but not necessarily disqualifying. Items 12-15 are **info-severity**, warranting investigation.

### Automated threshold rules

```python
ANOMALY_RULES = {
    'sharpe_suspicious': lambda m: m['sharpe'] > 2.0,
    'sharpe_critical': lambda m: m['sharpe'] > 3.0,
    'profit_factor_suspicious': lambda m: m['profit_factor'] > 3.0,
    'insufficient_trades': lambda m: m['total_trades'] < 200,
    'is_oos_gap': lambda m: m.get('is_sharpe', 0) / max(m.get('oos_sharpe', 1), 0.01) > 2.0,
    'regime_concentrated': lambda m: max(m.get('regime_returns', {}).values()) / m['total_return'] > 0.7,
    'drawdown_unrealistic': lambda m: abs(m['max_drawdown']) < 0.02 and m['annualized_return'] > 0.10,
    'parameter_fragile': lambda m: m.get('param_sensitivity') == 'fragile',
    'no_oos_data': lambda m: m.get('oos_sharpe') is None,
}
```

---

## 7. The minimum viable strategy card specification

### Two-layer architecture: YAML metadata + Markdown narrative

```yaml
---
strategy_card_version: "1.0"
strategy_name: "Momentum-Value Hybrid H4"
strategy_id: "strat-mv-h4-v3.2"
version: "3.2"
status: "candidate"  # draft | candidate | staging | live | archived | rejected
created_date: "2026-03-15"

# Classification
asset_class: "forex"
instruments: ["EUR/USD", "GBP/USD"]
timeframe: "H4"
strategy_type: "momentum-value-hybrid"
holding_period: "2-10 days"
parameter_count: 4

# Lineage (MLflow-style provenance)
experiment_id: "exp-2026-03-mv-h4"
best_run_id: "run-abc123"
data_version: "fxdata-v2026.03"
code_version: "git:abc123"
optimization_method: "CMA-ES with CPCV"

# Core Metrics
metrics:
  sharpe_oos: {value: 1.42, ci_95: [1.05, 1.79]}
  max_drawdown: {value: -0.087, threshold: -0.15}
  profit_factor: {value: 1.63}
  win_rate: {value: 0.54}
  total_trades: {value: 847}
  deflated_sharpe: {value: 0.98}
  pbo: {value: 0.12}
  monte_carlo_95th_dd: {value: -0.22}

# Regime-disaggregated (the key differentiation from model cards)
regime_metrics:
  bull: {sharpe: 1.8, trades: 312}
  bear: {sharpe: 0.6, trades: 198}
  sideways: {sharpe: 1.1, trades: 337}

# Anomaly Scan Results
flags:
  - {type: "warning", flag: "bear_regime_weakness", evidence: "Sharpe drops to 0.6 in bear regimes"}
  - {type: "info", flag: "walk_forward_validated", evidence: "8 windows, efficiency 0.72"}

# Verdict
verdict:
  recommendation: "PAPER_TRADE"
  confidence: 7
  conditions: ["Validate on 3-month paper trade", "Add vol filter for bear regimes"]
  kill_switch: ["Drawdown exceeds -15%", "30-day rolling Sharpe < 0.3"]
---
```

### The ten non-negotiable elements for deployment confidence

A solo retail trader needs these before committing capital:

1. **Clear hypothesis** — Can you explain the edge in one sentence without referencing backtest results?
2. **Positive out-of-sample results** — in-sample alone is insufficient evidence
3. **Sharpe ratio < 2.0 on OOS** (>2.0 is suspicious per Bailey & López de Prado)
4. **Minimum 200+ trades** for statistical significance
5. **Parameter stability** — neighboring values produce similar performance (no cliff edges)
6. **Regime decomposition** — strategy doesn't rely on a single regime for all returns
7. **Realistic costs** — commissions, slippage, and spread explicitly modeled
8. **Monte Carlo stress test** — expect **2-3× the historical max drawdown** in live trading
9. **Walk-forward or CPCV validation** — at least one forward-testing method
10. **Pre-defined kill switch** — specific, measurable conditions for stopping the strategy

---

## 8. Walk-forward and out-of-sample analysis best practices

### CPCV over traditional Walk-Forward

Traditional Walk-Forward suffers from three problems López de Prado identified: single-path dependency (one historical sequence, easily overfit), warm-up period data waste, and regime bias (results depend on which regimes fall in which windows). **CPCV generates C(N,k) combinatorial splits** — for N=10 groups with k=2 test groups, that's 45 unique train/test configurations producing a distribution of metrics rather than a single point estimate.

Implementation requirements: **purging** removes training samples whose labels overlap with test periods, and **embargoing** adds a buffer (recommended 0.01×T total observations) after each test fold to prevent information leakage from serial correlation. Empirical results (2024) show CPCV achieves "marked superiority" in false discovery prevention over traditional Walk-Forward, with lower PBO and superior DSR.

### The validation cascade

The recommended validation sequence, ordered by rigor:

1. **In-sample optimization** (CMA-ES, genetic algorithm, grid search) → produces candidate parameters
2. **Parameter sensitivity analysis** → verify no cliff edges, stable neighborhood
3. **CPCV validation** → produces distribution of Sharpe/drawdown across C(N,k) splits
4. **Monte Carlo bootstrap** (5,000+ iterations) → stress-tests execution robustness, produces 95th-percentile drawdown estimate
5. **Walk-forward on held-out period** → truly unseen data, the final exam
6. **Paper trading** → real-time execution without capital risk
7. **Scaled live deployment** → fractional position sizing, gradual scale-up

Each stage gates the next — failure at any stage should prevent advancement. The strategy card should record the current stage and evidence for each completed stage.

---

## 9. Implementation roadmap for a solo retail quant

### Phase 1: Metrics extraction layer (week 1-2)

Build the deterministic Python layer that computes all metrics from a VectorBT `Portfolio` object and outputs structured JSON. Use QuantStats for the 60+ metrics catalog. Add regime detection via `hmmlearn.GaussianHMM` (2-3 states on returns + volatility). Compute DSR and PBO from López de Prado's formulas. Run Monte Carlo via `qs.stats.montecarlo()` or custom bootstrap.

### Phase 2: Anomaly detection module (week 2-3)

Implement the 15-item anomaly checklist as deterministic Python rules (threshold checks, ratio computations). Augment with a focused LLM call for pattern interpretation — the LLM identifies contextual anomalies that rule-based systems miss (e.g., "profits concentrated in a period that coincides with a well-known market dislocation").

### Phase 3: Narrative generation pipeline (week 3-5)

Build the multi-stage LLM pipeline: anomaly scan → narrative generation → verdict. Use the system prompt template with benchmark ranges, the CoT reasoning chain, and structured JSON output. Implement the post-generation verification pipeline that cross-checks every cited number.

### Phase 4: Strategy card assembly (week 5-6)

Combine YAML metadata, narrative sections, and code-generated visualizations into a self-contained strategy card. Use the two-layer architecture. Implement the MLflow-style experiment registry for strategy versioning with aliases (candidate → staging → live → archived).

### Phase 5: Refinement and calibration (ongoing)

Calibrate confidence scoring by comparing AI verdicts against actual out-of-sample performance. Build a feedback loop where live performance updates the strategy card. Refine prompting patterns based on failure modes encountered.

### Priority ranking of features by impact

The highest-value features for a solo trader, ranked:

1. **Anomaly detection scan** — prevents deploying overfit strategies (highest downside protection)
2. **Regime-disaggregated metrics** — reveals hidden fragility in aggregate numbers
3. **Executive narrative with verdict** — saves hours of manual interpretation per backtest
4. **Strategy card with provenance** — enables systematic comparison across strategy variants
5. **Monte Carlo stress testing** — calibrates realistic drawdown expectations
6. **Walk-forward/CPCV integration** — provides statistical rigor for out-of-sample validation
7. **Kill-switch criteria generation** — pre-commits to rational exit conditions before deployment bias sets in

---

## Conclusion: narrative generation is the missing layer between computation and decision

The Python backtesting ecosystem has solved the metrics computation problem — QuantStats computes **60+ metrics** with a single function call, and VectorBT enables vectorized parameter sweeps across thousands of configurations. What remains unsolved across every platform (QuantConnect, MT5, NinjaTrader, pyfolio) is the **interpretation layer**: transforming raw numbers into grounded, skeptical, decision-ready narratives.

The technical architecture is clear: a multi-stage pipeline where deterministic code owns all computation, LLMs own interpretation and synthesis, and post-generation verification ensures grounding. The key academic insight is that **any narrative that doesn't account for the number of trials attempted (via DSR/PBO) and regime-conditional performance is fundamentally misleading**. The key engineering insight is that **structured JSON input with explicit benchmark ranges and anti-hallucination instructions reduces LLM failure modes to near-zero** for factual financial analysis.

The strategy card pattern — synthesized from ML model cards, aerospace TRRs, and clinical case reports — provides the structural framework. The anomaly detection checklist, ranked by reliability and false-positive rate, provides the safety net. And the ten non-negotiable deployment criteria provide the decision gate. Together, these components constitute a system that gives a solo retail trader **institutional-grade due diligence** on every backtest, automated and available in seconds rather than hours.