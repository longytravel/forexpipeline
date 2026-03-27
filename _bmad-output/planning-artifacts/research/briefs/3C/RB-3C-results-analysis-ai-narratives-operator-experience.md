# Research Brief RB-3C: Results Analysis, AI Narratives & Operator Experience

## Research Objective
Research how the best systems store, analyze, present, and act on backtesting results — then study cutting-edge AI analysis techniques to build our unique competitive advantage: AI-generated narratives, anomaly detection, and evidence packs that make strategy evaluation genuinely intelligent.

## Why This Matters
Stories 3-6 (SQLite results storage), 3-7 (AI analysis layer), and 3-8 (operator pipeline skills) represent our most differentiating features. No competitor has AI-generated narrative analysis of backtest results with evidence packs. Getting the storage schema, analysis pipeline, and operator UX right here is what makes this system worth building vs just using VectorBT.

## Scope

### Primary Questions

#### Results Storage & Schema (Story 3-6)
1. **How do competitors store backtest results?** SQLite, Parquet, HDF5, flat files, databases? What works at scale?
2. **Schema design for backtesting data:** What fields matter? How do production systems structure trade logs, equity curves, metrics, metadata?
3. **Versioning & provenance:** How do systems track which strategy version + data version + cost model produced which results?
4. **Query patterns:** What questions do traders actually ask their results database? This shapes the schema.

#### AI Analysis & Narratives (Story 3-7)
5. **AI for financial analysis:** What's the state of the art in using LLMs/AI to analyze trading results? Who's doing this well?
6. **Anomaly detection in backtesting:** Statistical methods for detecting suspicious patterns (curve-fitting artifacts, regime-dependent performance, liquidity mirages)
7. **Narrative generation:** How can AI turn a wall of metrics into a coherent story about strategy behavior? What makes a good analysis narrative?
8. **Evidence packs:** What's the equivalent concept in other fields? (ML experiment tracking has "run artifacts"; legal has "evidence bundles"; medicine has "case reports") What structure works?

#### Operator Experience (Story 3-8)
9. **Human-in-the-loop pipeline control:** How do MLOps/DataOps systems handle operator approval gates? What UX patterns work?
10. **Strategy review workflow:** How do professional quant teams review and approve strategies? What information do they need at each stage?
11. **Decision support dashboards:** What visualization and summary information helps a human make a good approve/reject/refine decision?

### Competitive Systems — Results & Analysis

| System | Known Results Features | Questions |
|--------|----------------------|-----------|
| **VectorBT** | Rich DataFrame-based results, built-in plotting, portfolio analytics | Schema design? How do power users extend it? Stats available? |
| **QuantConnect** | Research notebooks, Alpha Streams, Lean reports | Report generation? How do they present validation results? |
| **MT5** | Strategy tester reports, optimization results viewer | What metrics? How do traders actually interpret results? |
| **NinjaTrader** | Performance analytics, trade replay | Visualization approach? What traders find useful vs noise? |
| **Backtrader** | Analyzers framework, extensible metrics | Community-built analyzers worth studying? |
| **Quantopian (archived)** | Tear sheets (pyfolio), factor analysis | pyfolio's approach — still the gold standard for tear sheets? |
| **MLflow / W&B / Neptune** | Experiment tracking, artifact storage, comparison | Relevant patterns for backtesting experiment tracking? |
| **Evidently AI** | ML monitoring and data drift detection | Applicable to strategy performance monitoring? |

### AI & Analysis Sources

| Source | What to Extract |
|--------|----------------|
| **GitHub: pyfolio** | Tear sheet design, what metrics they chose and why |
| **GitHub: quantstats** | Modern alternative to pyfolio, design decisions |
| **GitHub: empyrical** | Risk metrics library, calculation methodology |
| **Reddit r/algotrading** | "What metrics do you look at?", "How do you know a strategy is good?", common analysis mistakes |
| **Reddit r/MachineLearning** | LLM for financial analysis, AI anomaly detection in time series |
| **ArXiv / SSRN** | Papers on AI-assisted trading analysis, narrative generation from data, anomaly detection in financial time series |
| **MLOps blogs** | Experiment tracking patterns, artifact management, human-in-the-loop ML |
| **Anthropic / OpenAI cookbooks** | Structured data analysis with LLMs, best practices for financial reasoning |
| **Academic: Explainable AI** | How to make AI analysis trustworthy and interpretable for financial decisions |
| **Trading psychology literature** | Cognitive biases in strategy evaluation, what information helps vs hinders good decisions |

### Specific Novel Research Areas

#### Evidence Pack Design
- **Concept:** A self-contained package of metrics, charts, narratives, and supporting data that lets an operator make an informed approve/reject/refine decision
- **Analogies to study:**
  - ML experiment cards (Hugging Face model cards)
  - FDA drug trial evidence packages
  - Legal case bundles
  - Academic peer review supplementary materials
  - Insurance underwriting packages
- **Questions:** What's the minimum viable evidence pack? What information is noise? How to structure for fast human scanning?

#### AI Narrative Generation for Trading
- **Concept:** Instead of dumping 50 metrics on the operator, AI reads the metrics and writes a narrative: "This strategy performs well in trending markets but has a 23% drawdown during ranging periods. The walk-forward analysis shows degrading performance in recent windows, suggesting potential regime sensitivity..."
- **Questions:** What prompting patterns produce useful financial narratives? How to ensure AI doesn't hallucinate about data it's analyzing? How to calibrate confidence levels? What's the right balance of narrative vs data?

#### Anomaly Detection in Backtest Results
- **Concept:** Automatically flag suspicious patterns that suggest overfitting, data snooping, or unrealistic assumptions
- **Patterns to detect:**
  - Performance cliff at out-of-sample boundary
  - Excessive parameter sensitivity
  - Unrealistic fill assumptions
  - Regime-concentrated returns
  - Look-ahead bias artifacts
  - Survivorship bias indicators
- **Questions:** What statistical tests are most reliable? What false positive rate is acceptable? How do production systems handle this?

## Expected Deliverables
1. **Results schema design guide** — field inventory from competitor analysis, optimal SQLite schema patterns
2. **Evidence pack specification** — structure, minimum viable content, operator scanning optimization
3. **AI analysis pattern catalog** — prompting patterns, metric interpretation, narrative generation approaches
4. **Anomaly detection toolkit** — statistical tests, thresholds, implementation priorities
5. **Operator UX patterns** — what information, what sequence, what visualization, what actions
6. **Competitive feature matrix** — results/analysis features across all competitors, with gap analysis
7. **pyfolio/quantstats evaluation** — can we adopt/adapt their metrics framework, or build custom?

## Informs Stories
- **3-6** Results Storage (schema design, query patterns, versioning)
- **3-7** AI Analysis Layer (narrative generation, anomaly detection, evidence packs)
- **3-8** Operator Pipeline Skills (decision support, approval UX, information hierarchy)

## Research Constraints
- The AI analysis layer is our **key differentiator** — invest more research here
- Focus on **operator experience** — the system is for one person (ROG) making strategy decisions
- Don't over-design for team workflows; this is a solo operator pipeline
- Evidence packs should be **self-contained** — readable without the full system running
- Anomaly detection should **minimize false positives** — annoying alerts erode trust
