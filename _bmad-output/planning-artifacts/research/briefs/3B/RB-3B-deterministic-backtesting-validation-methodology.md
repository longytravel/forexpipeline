# Research Brief RB-3B: Deterministic Backtesting & Validation Methodology

## Research Objective
Validate our reproducibility contract and validation methodology (walk-forward, CPCV, Monte Carlo) against academic best practices and industry standards. Ensure we're using state-of-the-art techniques and not missing critical validation approaches that prevent overfitting.

## Why This Matters
Story 3-2 defined a reproducibility contract (bit-identical trade logs, FMA flags, Rayon determinism) and Story 3-1 documented ClaudeBackTester's existing validation pipeline (walk-forward, CPCV, Monte Carlo, regime analysis, confidence scoring). These are the core of whether our backtesting results can be trusted. If our validation methodology has gaps, every strategy we approve could be an overfitting artifact.

## Scope

### Primary Questions
1. **Reproducibility in practice:** How do institutional quant teams ensure backtest reproducibility? What guarantees do they actually provide? Is bit-identical overkill or table stakes?
2. **Walk-forward analysis best practices:** What are the current best practices for window sizing, anchored vs rolling, retraining frequency? What pitfalls do people hit?
3. **Combinatorial Purged Cross-Validation (CPCV):** Beyond de Prado's original paper — what refinements exist? How is it actually implemented in production? Common mistakes?
4. **Monte Carlo validation:** Which Monte Carlo techniques are most valuable? Trade shuffling? Equity curve randomization? Parameter perturbation? What's the false positive rate?
5. **Overfitting detection:** What modern techniques exist beyond what we have? Deflated Sharpe Ratio? Probability of Backtest Overfitting (PBO)? Multiple testing correction?
6. **Regime analysis:** How do production systems detect and handle regime changes? Hidden Markov Models? Change-point detection? What's practical vs academic?
7. **Floating-point determinism:** Real-world experiences with FMA flags, cross-platform reproducibility, numerical stability in financial calculations
8. **Strategy validation pipeline design:** What's the optimal sequence of validation stages? What should gate what?

### Academic Sources to Study

| Topic | Key Papers / Authors |
|-------|---------------------|
| **CPCV** | de Prado "Advances in Financial Machine Learning" (2018), Bailey et al. "Probability of Backtest Overfitting" |
| **Walk-forward** | Pardo "The Evaluation and Optimization of Trading Strategies" (2008), Aronson "Evidence-Based Technical Analysis" |
| **Deflated Sharpe** | Bailey & de Prado "The Deflated Sharpe Ratio" (2014) |
| **Multiple testing** | Harvey, Liu & Zhu "...and the Cross-Section of Expected Returns" (2016), White's Reality Check |
| **Monte Carlo** | Davison & Hinkley "Bootstrap Methods and their Application", papers on bootstrap validation for trading |
| **Regime detection** | Hamilton "A New Approach to the Economic Analysis of Nonstationary Time Series", papers on HMM for markets |
| **Overfitting** | Bailey et al. "Pseudo-Mathematics and Financial Charlatanism" (2014), recent ML overfitting papers |
| **Strategy evaluation** | Campisi "The Development of Walk-Forward Testing" (2020s updates), recent survey papers |

### Community & Practitioner Sources

| Source | What to Extract |
|--------|----------------|
| **Reddit r/algotrading** | "My strategy worked in backtest but failed live" posts — what went wrong, what validation would have caught it |
| **Reddit r/QuantFinance** | Debates on validation methodology, "is walk-forward enough?", CPCV implementation experiences |
| **QuantConnect forums** | How their validation pipeline works, what users add on top |
| **Elite Trader forums** | Professional traders discussing validation, "how I know my edge is real" |
| **GitHub implementations** | Open-source CPCV, walk-forward, PBO implementations — code quality, edge cases handled |
| **ArXiv / SSRN** | Recent papers (2022-2025) on backtest validation, overfitting detection, ML in strategy validation |
| **Marcos Lopez de Prado** | His latest work, talks, interviews — he's the authority on backtest overfitting |
| **QuantStart / QuantInsti** | Practitioner-focused articles on validation methodology |
| **YouTube conference talks** | QuantCon, PyData, academic finance conferences |

### Competitor Validation Approaches

| System | Known Validation Features | Questions |
|--------|--------------------------|-----------|
| **VectorBT** | Random param generation, out-of-sample splitting | Does it have walk-forward? CPCV? How do power users validate? |
| **QuantConnect** | Walk-forward, out-of-sample, paper trading bridge | Full validation pipeline? What do institutional users add? |
| **MT5** | Forward testing, genetic optimization | How does it prevent overfitting during optimization? |
| **NinjaTrader** | Walk-forward optimizer (WFO) add-on | Implementation details? How good is it? |
| **Backtrader** | Community analyzers | What validation tools has the community built? |
| **Quantopian (archived)** | Contest results, what strategies survived live | What validation caught overfitting? What didn't? |

## Expected Deliverables
1. **Validation methodology matrix** — our approach vs best practices vs competitors, with gap analysis
2. **Overfitting detection toolkit** — which techniques we should implement, priority order, expected false positive rates
3. **CPCV implementation guide** — practical lessons from real implementations, common pitfalls
4. **Reproducibility standard** — what level of determinism is industry standard, where we're over/under-investing
5. **Regime analysis recommendation** — practical approach for V1, what to defer
6. **Validation stage sequencing** — optimal order of validation stages with gate criteria
7. **"Red flags we're missing" list** — validation gaps that could let bad strategies through

## Informs Stories
- **3-5** Rust Backtester Crate (determinism guarantees, floating-point handling)
- **3-7** AI Analysis Layer (what metrics matter, anomaly detection baselines)
- **3-3** Pipeline State Machine (validation stage sequencing, gate criteria)
- **Future optimization stories** (Epic 5 — what validation to run during optimization)

## Research Constraints
- Focus on **forex-relevant** validation — some techniques matter more for equities/options
- Distinguish between **V1 must-have** vs **nice-to-have** — we need pipeline proof first
- Prefer **practical implementations** over theoretical frameworks
- Weight **failure stories** heavily — what validation didn't catch and why
