# Results Analysis, AI Narratives and Operator Experience for Backtesting

## Research objective and design constraints

This research focuses on how high-performing systems persist, analyse, present, and operationalise backtest results—then applies cutting-edge AI techniques (structured LLM analysis, narrative generation, anomaly detection, and “evidence packs”) to create a defensible competitive advantage. The differentiator is not “more charts”; it is *intelligent evaluation* that (a) spots failure modes early, (b) explains them in plain English without hallucination, and (c) produces self-contained artefacts that remain readable outside the running system. citeturn11view0turn9search3turn6search0

Two practical constraints heavily shape the design:

First, this is a **solo operator pipeline** (one decision-maker). That favours fast triage, repeatable gates, and an interaction model that reduces cognitive load and avoids alert fatigue. citeturn11view0turn6search36

Second, **false positives must be minimised**—especially for anomaly detection. In both quant research and ML monitoring, frequent noisy warnings rapidly train the operator to ignore the system, which then defeats the purpose of automation. citeturn11view0turn1search19

## Competitive landscape patterns in results and analysis

A consistent pattern emerges across incumbents: most systems either (a) provide strong *metrics + visualisation* but weak provenance/automation, or (b) provide strong *experiment tracking provenance* but little domain intelligence for trading-specific pathologies.

**Python-first backtesting libraries tend to keep results in memory as rich objects, optimised for interactive analysis.** VectorBT exposes a `Portfolio` abstraction with “record classes” representing events such as orders, logs, trades/positions, and drawdowns—excellent for ad‑hoc exploration but not a persistence-first results database by default. citeturn0search0turn0search4

**Retail trading platforms tend to generate human-facing reports and tables, with limited deep provenance.** MetaTrader 5’s Strategy Tester report enumerates canonical backtest report measures (gross profit/loss, multiple drawdown variants, and other stability/profitability statistics). citeturn0search2turn0search10

NinjaTrader’s documentation is unusually explicit about definitions and formulas (e.g., Profit Factor = Gross Profit / Gross Loss; Sharpe ratio guidance; time-in-market; profit-per-month; recovery and flat-period measures). That explicitness is a useful model for building operator-trustworthy metric definitions in your own UI and evidence packs. citeturn3search0turn3search12

**Quant platform UIs are strong at “single-run explanation” but weaker at cross-run database-style querying unless you build it yourself.** QuantConnect’s backtest results page centres the equity curve and provides trades, logs, performance statistics, and downloads; it also exposes programmatic access (e.g., reading backtest orders via API/endpoint), but the platform experience is still primarily run-by-run browsing rather than “results DB” workflows. citeturn0search1turn0search33

**Backtesting frameworks that emphasise extensibility typically offer “analysis hooks” (analyser plugins) rather than an opinionated storage schema.** Backtrader’s `Analyzer` family and built-in analyzers (e.g., drawdown stats) demonstrate a composable approach: analysis components attach to runs and compute additional summaries. citeturn0search7turn0search3

**Tear sheets remain the de facto baseline for “operator scanning.”** Pyfolio tear sheets combine performance statistics with a curated set of plots (rolling returns, rolling beta, rolling Sharpe, drawdowns, underwater plot, and multiple distribution/period views). QuantStats modernises this into modules for stats, plots, and report/HTML tear-sheet generation. These libraries implicitly encode “what matters enough to be on page one.” citeturn2search4turn2search1turn2search25

**MLOps tracking systems show the strongest pattern for provenance at scale: “metadata in a DB, artefacts in an artefact store.”** MLflow explicitly separates a backend store for run metadata (run IDs, parameters, metrics, tags, times) from an artefact store for large files. W&B Artifacts, and Neptune’s artefact tracking features, similarly emphasise versioned inputs/outputs and lineage graphs rather than burying everything inside one monolithic file. citeturn1search0turn1search1turn1search2

image_group{"layout":"carousel","aspect_ratio":"16:9","query":["QuantConnect backtest results page screenshot","MetaTrader 5 strategy tester report screenshot","pyfolio tear sheet underwater plot screenshot","MLflow tracking UI runs metrics screenshot"],"num_per_query":1}

## Results storage and schema design for SQLite-first persistence

### What “works at scale” across systems

Competitors rarely publish their internal storage schemas, but the observable architectural pattern is clear: systems that scale to many runs tend to store **compact, queryable metadata separately** from **large time-series and artefacts**, which are stored in efficient file formats and referenced by ID. This is explicit in MLflow’s backend-store vs artefact-store split. citeturn1search0

For your Story 3‑6 (“SQLite results storage”), SQLite can plausibly be the *metadata and index layer* for a solo operator, even with very large theoretical limits; SQLite documents extremely high theoretical row limits, constrained in practice by database file size. citeturn7search19  For concurrency and responsiveness, Write‑Ahead Logging (WAL) is a well‑documented improvement mode: SQLite explains WAL behaviour, and the common practical guidance is that WAL enables concurrent readers during writes (still one writer), which matters if you’re ingesting results while browsing them. citeturn12search3turn12search38

For the “artefact layer” (equity curves, position matrices, per-bar exposures, per-trade curves, optimisation surfaces), columnar formats are purpose-built. Apache Parquet is described as a column-oriented format designed for efficient storage/retrieval with high-performance compression/encoding, and it is broadly supported across analytics tooling. citeturn12search0turn12search8  
A practical benefit of Parquet-like artefact files is that systems such as DuckDB can query Parquet directly and push down filters/columns—useful if you later want “SQL over artefacts” without importing everything into SQLite. citeturn12search2turn12search10

### Field inventory from competitors and what it implies for schema

Competitor outputs strongly suggest three “canonical layers” you should store:

**Run metadata and configuration**  
This is what enables provenance and reproducibility: strategy version, parameter set, dataset ID/time range, transaction cost model, execution assumptions, benchmark configuration, and engine version. QuantConnect makes this tangible by generating formal reports from a “backtest results JSON file,” implying a standardised run-results structure that is separable from code. citeturn0search25turn0search13

**Event logs (orders, fills, trades, positions)**  
QuantConnect surfaces orders/trades/logs, downloadable closed trades, and APIs for orders access. citeturn0search1  
VectorBT’s record classes (orders/trades/drawdowns) reinforce that a robust schema must capture discrete events—not just an equity curve. citeturn0search0  
MetaTrader 5 and NinjaTrader emphasise “report metrics” grounded in these events (profit/loss aggregates, drawdown, and trade performance stats). citeturn0search2turn3search0

**Time series and derived series**  
Equity curve, drawdown/underwater, daily/weekly/monthly returns, rolling statistics—these dominate tear sheets and operator interpretation. Pyfolio explicitly lists rolling Sharpe, underwater plot, and drawdown periods as first-class tear-sheet elements. citeturn2search4turn2search35

### Recommended SQLite schema pattern for a solo operator

A SQLite-first schema should optimise for: fast filtering/sorting across runs; deep drill-down into any run; and stable provenance. A strong, proven pattern is to treat each backtest as an “experiment run” (MLOps-style), and then attach artefacts and analyses as versioned objects. citeturn1search0turn1search1turn4search4

A pragmatic schema (conceptual, not SQL DDL) looks like:

**Core identity tables**
- `runs`: `run_id` (UUID), timestamps, engine name/version, run status, duration, seed, environment fingerprint (python deps / container hash), “notes” field.
- `strategies`: `strategy_id`, human name, git commit hash, strategy package version, optional “entry point”.
- `datasets`: `dataset_id`, vendor/source, universe definition, bars frequency, start/end, data-quality flags, checksum/hashes.
- `cost_models`: `cost_model_id`, fee schedule, spread/slippage model, borrow/margin, “stress envelope” parameters.

**Provenance join tables**
- `run_provenance`: `run_id`, `strategy_id`, `dataset_id`, `cost_model_id`, benchmark definition ID, plus “derived from run_id” for optimisation chains.

**Metrics and summaries**
- `metrics`: `run_id`, `metric_name`, `value`, `unit`, `calculation_version`.
- `metric_sets`: optional grouping (e.g., “IS metrics”, “OOS metrics”, “WFA fold metrics”) to avoid ambiguity.

**Events**
- `orders`: `run_id`, order_id, symbol, side, type, quantity, limit/stop, timestamps, status.
- `fills`: `run_id`, fill_id, order_id, price, quantity, commission, slippage estimate, liquidity flags.
- `trades`: `run_id`, trade_id, symbol, entry/exit timestamps, entry/exit price, pnl gross/net, MAE/MFE, holding time.
- `positions`: optional snapshots; for scale, store snapshots as artefacts.

**Artefact registry**
- `artifacts`: `artifact_id`, `run_id`, artefact_type (equity_curve, drawdowns, positions, optimisation_surface, plots, pdf_report), storage_uri/path, hash, size, created_at.
- `artifact_lineage`: for “evidence pack” builds and derived artefacts (narrative generated from metrics vX, etc.).

This mirrors the MLflow/W&B/Neptune idea: queryable metadata in the DB, heavy objects in artefact storage. citeturn1search0turn1search1turn1search2

### Query patterns that should drive indexing

Trader/operator questions are remarkably consistent across communities and platforms:

Operators ask for *ranking* and *risk sanity checks* (“profit factor, max drawdown, Sharpe/Sortino, trade count”), not just total return. citeturn7search0turn7search5turn7search8  
They ask behavioural questions: “Did it fail on Mondays?” “What is MAE for losing trades?”—which implies you need trade-level logs plus calendar/time bucketing. citeturn10search37  
Platforms embed these concepts directly into their metric sets (MT5 drawdown types; NinjaTrader recovery/flat periods; QuantConnect’s drawdown report and trade statistics). citeturn0search5turn0search2turn3search0

That implies your highest-value indexes are typically:
- `(metrics.metric_name, metrics.value)` for ranking filters
- `(trades.symbol, trades.entry_time)` and `(trades.exit_time)` for regime/time slicing
- `(run_provenance.strategy_id, run_provenance.dataset_id)` for provenance queries
- `(artifacts.run_id, artifacts.artefact_type)` for fast evidence-pack assembly

## AI analysis layer for narratives and trustworthy automation

### What “state-of-the-art” means in this context

The frontier in finance-oriented LLM work is not “LLMs place trades”; it is LLMs as *interfaces and analysts* over structured data, supported by domain adaptation and tool use. Finance-specialised LLMs such as BloombergGPT and FinGPT demonstrate that domain training/adaptation improves performance on finance language tasks, even if they are not purpose-built for backtest interpretation. citeturn6search2turn6search3turn6search18  
At the same time, recent academic work on LLM-based investing strategies warns that evaluation can be overstated by survivorship and data-snooping biases—exactly the failure modes your anomaly detector must surface when narrating results. citeturn4search9

For narrative generation specifically, your task aligns closely with the “data-to-text” and “table-to-text” research communities: translating structured data into faithful natural-language narratives. Surveys define data-to-text generation as translating data instances into user-consumable narratives and explicitly note commercial “narrative BI” frameworks. citeturn6search0  
This is important because it frames “AI narrative for backtests” as an engineering discipline with known pitfalls: numeric faithfulness, omission errors, and misleading emphasis.

### A practical architecture for AI narratives without hallucination

The most reliable pattern is **deterministic computation first, LLM narration second**:

1) Deterministic layer computes metrics, attribution slices, regime buckets, and anomaly test outputs from raw artefacts/trades.

2) LLM layer receives only *structured* inputs (JSON metric sets + anomaly flags + references to evidence artefacts), and is constrained to produce a structured output that can be validated.

OpenAI’s Structured Outputs are explicitly designed to enforce JSON Schema adherence, reducing failures like missing keys or invalid enum values, and shifting the burden from “prompting harder” to “constraining outputs.” citeturn9search3turn9search13turn9search0  
Similarly, tool use documentation from Anthropic frames tools as contracts where the model decides when to call operations, enabling a controlled agentic workflow rather than free-form guessing. citeturn8search2

Given your “evidence pack” requirement, a high-leverage strategy is to make narrative generation *reference-driven*: for every narrative claim, the LLM must cite the exact metric IDs or chart IDs that support it (not web citations—internal evidence references). This is a direct application of hallucination-mitigation research that categorises retrieval/grounding as a major mitigation class. citeturn8search0turn8search5

### AI narrative “pattern catalogue” tailored to backtest results

The following patterns are both implementable and aligned to “trustworthy narratives”:

**Metric-to-Story template (single run)**  
Input: (a) summary metrics, (b) drawdown periods, (c) rolling metrics, (d) trade distribution summaries, (e) anomaly flags.  
Output schema:  
- `executive_summary` (3–6 sentences)  
- `what_worked` / `what_failed` (each claim must include metric references)  
- `regime_behavior` (link to regime slices)  
- `implementation_risks` (cost/liquidity assumptions)  
- `confidence_and_limits` (explicitly list unknowns and simplifying assumptions)

Structured Outputs make this schema enforcement practical. citeturn9search3turn9search5

**Compare-to-baseline narrative (run vs benchmark or buy-and-hold)**  
Many traders explicitly compare to buy-and-hold or ask “is it better than the market segment?” which suggests you should store benchmark series and produce relative narratives (alpha, beta, capture, correlation). citeturn7search24turn7search12turn2search6

**Cross-run “leaderboard narratives” (portfolio of candidates)**  
Instead of ranking by a single metric (which practitioners debate heavily), generate narratives that explain *why* the top candidates differ: e.g., “same Sharpe, different time-in-market and drawdown recovery profile.” Practitioners explicitly highlight that strategies with identical headline ratios can “feel completely different” operationally (holding time, trade frequency, long flat periods). citeturn7search9turn3search0

**Narrative QA over evidence pack (operator interrogation)**  
The operator asks natural questions (“Did it fail on Mondays?”). Support this by adding precomputed slices (day-of-week, session, volatility regime) and letting the LLM answer only by quoting from these slices. citeturn10search37turn6search0

## Anomaly detection toolkit for backtest pathologies with low false positives

### Why anomaly detection here is different from generic time-series anomaly detection

Generic time-series anomaly detection surveys focus on outliers, change points, and distribution shifts, including deep learning approaches for multivariate series. citeturn6search1turn6search5turn6search29  
Backtest anomaly detection is more specific: it targets *research process failures* (overfitting, data snooping) and *simulation realism failures* (liquidity mirages, fill assumptions), not just unusual points in a series.

A key insight from quant validation literature is that impressive backtests can be artefacts of biased research processes; the CFA Institute explicitly frames backtesting as valuable only when major biases are eliminated, and emphasises “statistical hygiene.” citeturn7search10

### Core tests with strong academic grounding

If you implement only a few “tier‑1” anomaly checks, these have unusually strong foundations:

**Multiple-testing / data snooping controls**  
- White’s Reality Check directly addresses data snooping when many strategies are tested on the same data. citeturn5search0turn5search4  
- Hansen’s Superior Predictive Ability (SPA) test is designed as a more powerful and less alternative-sensitive improvement over the Reality Check framework. citeturn5search1

**Backtest overfitting probability and Sharpe correction**  
- The Deflated Sharpe Ratio corrects observed Sharpe for non-normality, sample length, and selection bias from multiple trials—highly relevant when you run large parameter sweeps/optimisations. citeturn2search3turn11view0  
- The Probability of Backtest Overfitting (PBO) framework with combinatorially symmetric cross-validation (CSCV) explicitly targets the “research pipeline overfitting” problem and is used to estimate how likely a backtest is overfit. citeturn5search2turn5search23turn5search27

These should be treated as “high-confidence” anomalies: if they trigger, you do not just warn—you change the operator’s prior.

### Practical “production-grade” anomaly patterns for backtests

To stay aligned with “minimise false positives,” implement anomaly detection as **evidence-weighted scoring**, not a single threshold.

A robust shortlist of high-signal detectors is:

**Boundary cliff and regime sensitivity**
- Detect performance cliffs at the in-sample/out-of-sample boundary by comparing key metrics (Sharpe, drawdown, hit rate) across stages (IS/WFA/OOS) and flagging discontinuities. The recently published IS–WFA–OOS protocol paper explicitly treats “peak backtest” as insufficient and highlights stage-by-stage evaluation and decision gates. citeturn11view0turn5search2  
- Regime concentration: compute conditional performance by market regime (volatility buckets, trend/range proxies) and flag if most returns concentrate in narrow conditions.

**Parameter fragility / sensitivity**
- Build an optimisation surface and flag “knife-edge” regions: when small parameter changes produce dramatic degradation. This is explicitly endorsed as “stable region” selection (avoid cliff zones) in the IS–WFA–OOS framework paper. citeturn11view0turn5search2

**Implementation realism stress**
- Run “cost inflation envelopes” (commission/spread/slippage multipliers) and flag if the strategy breaks immediately under mild stress; execution friction and cost assumptions are repeatedly emphasised as major sources of backtest/live divergence. citeturn11view0turn0search2  
- Liquidity mirage flags: unusually favourable fill assumptions relative to market microstructure constraints (for platforms that support tick-level simulation, use tick replay / market replay when available; NinjaTrader highlights tick replay as a mechanism for tick‑accurate historical recalculation). citeturn3search11turn11view0

**Metric contradictions**
- Flag suspicious combinations: very high win rate but low profit factor; very high profit factor with tiny trade count; large max drawdown with deceptively high CAGR; etc. Traders repeatedly reference these metrics together because single metrics are misleading. citeturn7search0turn7search36turn3search0

### Setting thresholds to reduce alert fatigue

The most defensible approach is a two-layer design:

**Layer A: silent scoring** (compute and store anomaly scores for every run).  
**Layer B: surfaced flags** only when (a) multiple independent detectors agree, or (b) a “tier‑1 academic” test triggers (Reality Check/SPA/DSR/PBO). citeturn2search3turn5search0turn5search1turn5search2

This “multi-signal” approach mirrors how drift detection tooling often combines statistical tests/metrics to make drift/no-drift decisions rather than relying on a single metric. citeturn1search3turn1search19

## Evidence pack specification for self-contained strategy evaluation

### Strong external analogies to steal from

Three external concepts map cleanly onto “evidence packs”:

**Experiment tracking artefacts**  
MLflow frames artefacts as large outputs stored separately from run metadata. W&B Artifacts explicitly track/ संस्करणed datasets/models as inputs/outputs of runs. Neptune supports tracking file artefacts and their metadata, and even comparing artefact metadata between runs. citeturn1search0turn1search1turn1search2turn1search22

**Model cards as “boundary objects”**  
Model cards are defined as Markdown files with metadata that preserve discoverability and reproducibility; Hugging Face explicitly treats them as essential documentation and a shared artefact between stakeholders. This is a direct blueprint for how your evidence pack should balance narrative and structured facts. citeturn4search2turn4search8

**Auditable deployment packets**  
A March 2026 quant validation framework paper explicitly uses the phrase “evidence pack” and enumerates a minimum set: search transparency, artefact logging (backtest config, data version, seed, stage-by-stage results), and decision trace (pass/fail rules and mapping). This is unusually aligned with your stated direction and can be treated as a directly supportive precedent. citeturn11view0

### Minimum viable evidence pack for your system

A minimum evidence pack that is genuinely self-contained (readable without the system) should be a single folder or zip with:

**A human-readable report (HTML + printable PDF)**
- Executive summary narrative
- Key charts and “top risks”
- Explicit limitations and assumptions

**A machine-readable manifest (`manifest.json`)**
- Run ID, timestamps
- Strategy version (git hash), engine version
- Dataset ID and data time range + hashes
- Cost model ID + parameters
- Seeds and randomness controls
- Pointers + hashes for every included file

This mirrors artefact logging and provenance patterns from experiment tracking systems. citeturn1search0turn1search1

**Canonical artefacts**
- Trade list (CSV/Parquet): entry/exit, pnl net/gross, MAE/MFE, holding time
- Equity and drawdown series (Parquet)
- Summary metrics table (JSON/CSV)
- Optimisation surface / parameter sensitivity artefact (if optimisation was performed)
- Anomaly detector outputs: each flag must include *supporting evidence pointers* (chart IDs, table rows)

Parquet is a strong candidate for these bulk artefacts due to its columnar design and compression. citeturn12search0

**Decision trace**
- Pre-committed thresholds and gates used
- PASS/FAIL outcome by gate
- Operator note fields (free text)
This is directly aligned to “auditable decision gates” thinking in the IS–WFA–OOS paper. citeturn11view0

### Evidence pack scanning optimisation

If the operator is one person, the pack should support a two-pass reading:

Pass 1 (≤60 seconds): “Is this even worth deeper review?”  
Pass 2 (5–15 minutes): “Do I approve, reject, or request modifications?”

To support that, the front page must be a *summary card* with:
- headline metrics (Sharpe/Sortino, max drawdown, profit factor, trade count)
- “dominant edge description” (1–2 sentences)
- top 3 risks/anomalies with severity
- “what changed since last run” (if comparative)

This is consistent with how tear sheets prioritise a small set of plots/metrics for fast scanning. citeturn2search4turn2search25

For distribution-level understanding, include a returns/trade-return histogram and tail indicators; tools like Pineify explicitly elevate return distribution analysis (fat tails, skewness) because it helps distinguish “smooth but fragile” from “spiky but resilient.” citeturn10search13

## Operator experience patterns for a solo approval workflow

### Human-in-the-loop approval gates: proven UX patterns

A strong pattern from MLOps governance is staged promotion with explicit permissions and approval points (e.g., “Development → Production” restrictions). Amazon SageMaker’s model registry staging construct explicitly discusses enforcing approval gates at stage transitions via permissions. MLflow’s Model Registry emphasises lineage, versioning, aliasing, and metadata tagging across lifecycle stages. citeturn4search35turn4search4

Your system should adapt this into a *solo-operator* workflow (not a committee), but keep the same core idea: every promotion writes an audit record and locks the evidence pack.

### Strategy review workflow as a decision pipeline

A decision-oriented pipeline (explicitly recommended in recent quant validation work) advances a strategy only through pre-committed decision gates, not through “peak metric chasing.” citeturn11view0

A practical solo workflow is:

**Intake and triage**
- Operator sees a queue of candidate runs
- Each run displays: status, key metrics, anomaly severity, and “delta vs baseline”

**Review mode**
- Narrative + evidence side-by-side (charts + trade slices)
- “Ask questions” panel that answers only using internal evidence references (no free-form speculation)

**Decision**
- Approve / reject / revise
- Forced “reason codes” + free text note  
- Evidence pack snapshot captured and immutable

This is aligned with the “decision trace” requirement for auditable research and reduces hindsight editing. citeturn11view0

### Decision support dashboards: what to show, in what order

The most valuable content for a solo operator, based on competitor UIs and practitioner discussions, is:

**Behaviour first, then summary**  
Start with behaviour and risk visuals (equity curve + underwater/drawdown), then show metrics; QuantConnect highlights drawdown analysis explicitly in reports, and pyfolio treats underwater/drawdowns as core tear-sheet plots. citeturn0search5turn2search4

**Trade distribution and “how it makes money”**
- holding time distribution
- profit distribution (by trade, by day/week/month)
- MAE/MFE for winners/losers (operator questions explicitly ask for this) citeturn10search37turn3search0

**Stress and fragility**
- cost stress envelope results
- parameter sensitivity surface and “stable region” highlight (avoid cliffs) citeturn11view0turn5search2

**Explainability of anomalies**
Every anomaly flag should click through to an evidence panel: the exact chart/time window/trade subset that caused it, plus the test definition used. Systems like NinjaTrader explicitly document metric definitions, which is a good trust pattern to replicate. citeturn3search0

## Competitive feature matrix and assessment of pyfolio and quantstats adoption

### Competitive feature matrix and gap analysis

The matrix below focuses on *results storage/persistence, analysis depth, provenance, and narrative automation*—the dimensions most relevant to Stories 3‑6 to 3‑8.

| System | Results representation | Persistence/export | Built-in analytics | Provenance/versioning | AI narrative + evidence pack |
|---|---|---|---|---|---|
| VectorBT | Portfolio object with event record classes (orders/trades/drawdowns) citeturn0search0 | Primarily user-managed persistence; rich interactive plotting citeturn0search20 | Strong portfolio analytics and plotting citeturn0search20 | Not an opinionated run database by default (user builds this) citeturn0search0 | Not native |
| QuantConnect | Cloud UI shows equity, trades, logs, stats; API access to orders/trades citeturn0search1turn0search33 | Reports generated from backtest results JSON (Lean report creator) citeturn0search25turn0search13 | Strong run UI + report visuals (e.g., drawdown chart) citeturn0search5 | Platform-level run IDs and access via API; versioning depends on user practices citeturn0search33 | Not native |
| MetaTrader 5 | Strategy Tester report enumerates standard metrics (profit/loss, drawdowns, etc.) citeturn0search2turn0search10 | Human-facing report output (terminal/report artefacts) citeturn0search10 | Standard metrics; oriented to manual interpretation citeturn0search2 | Limited explicit provenance beyond test settings (in typical workflows) citeturn0search10 | Not native |
| NinjaTrader | Strategy Analyzer + Trade Performance views; explicit metric definitions citeturn3search2turn3search0 | Exports possible; supports tick replay for fidelity in some use cases citeturn3search11 | Extensive metrics and optimisation fitness measures citeturn3search13turn3search0 | Limited formal experiment provenance unless user builds tooling citeturn3search2 | Not native |
| Backtrader | Extensible analyzers; drawdown analyzer and others citeturn0search7turn0search3 | User-managed persistence (python objects/logs) citeturn0search7 | Modular analyzers; requires user curation for tear-sheet experience citeturn0search7 | Not an opinionated run DB by default citeturn0search7 | Not native |
| Pyfolio / QuantStats | Curated tear sheets (pyfolio plots include underwater/rolling Sharpe etc.) citeturn2search4turn2search25 | Generates tear sheets (QuantStats: HTML tear sheets) citeturn2search25 | Strong metric-and-plot “scan pack” baseline citeturn2search4turn2search25 | Not a run/provenance system; expects user to supply returns and context citeturn2search4 | Not native |
| MLflow / W&B / Neptune | Runs with metrics/params/tags + artefacts lineage citeturn1search0turn1search1turn1search2 | Artefact store + metadata store pattern citeturn1search0 | Strong comparison across runs; domain-agnostic citeturn1search0turn1search9 | Strong lineage/versioning; model registry concepts in MLflow citeturn4search4 | Not trading-specific; narratives require custom layer |
| Evidently AI | Drift/quality reports with statistical tests and dashboards citeturn1search19turn1search7 | Generates interactive reports; integrates with tracking platforms citeturn1search31turn1search3 | Excellent “detector + report” pattern but ML/LLM quality focused citeturn1search7 | Can be logged as artefacts; provenance depends on host tool citeturn1search31 | Not trading-specific narratives |

**Gap that remains open for your product**  
Across these systems, the missing combination is: (1) a persistence-first schema optimised to answer trader questions across thousands of runs, (2) a detection layer that flags backtest-specific research/simulation pathologies, and (3) an AI narrative layer constrained to internal evidence that emits an exportable evidence pack. (The closest “philosophical” precedent to an evidence pack in quant validation appears in recent research explicitly calling for it as part of auditable deployment.) citeturn11view0turn1search0turn2search3turn5search2

### Evaluation of pyfolio and quantstats for adoption vs custom build

**Licensing is permissive for both**, which lowers friction for adaptation:
- Pyfolio is licensed under Apache 2.0. citeturn13search1  
- QuantStats also states it is distributed under Apache Software License. citeturn13search2  
Empyrical—the metric core used by zipline/pyfolio—is likewise Apache-licensed and documents common risk/performance metrics. citeturn13search10turn2search6

**Decision lens: adopt for baseline tear sheets, extend for your differentiators.**  
Pyfolio and QuantStats encode “what belongs in a tear sheet” (rolling metrics, drawdown visualisations, monthly/annual breakdowns, underwater plots). citeturn2search4turn2search25  
This makes them excellent as:
- a baseline metrics library (Empyrical + QuantStats stats)
- a baseline plot set for evidence packs (QuantStats/pyfolio-style plots)

But they do **not** solve your differentiators:
- They don’t provide run-level provenance/versioning and cross-run querying (that’s your SQLite schema + artefact registry).
- They don’t implement backtest overfitting controls (DSR/PBO/Reality Check/SPA).
- They don’t provide constrained AI narratives tied to evidence references.

So the best strategy is typically:
- Use Empyrical/QuantStats to accelerate standard metric correctness and familiar visuals. citeturn2search6turn2search25  
- Build custom “research integrity” metrics and anomaly detectors (DSR/PBO + gate logic) as first-class tables in your results DB. citeturn2search3turn5search2turn5search0turn5search1  
- Build the narrative/evidence-pack layer as its own pipeline stage, using Structured Outputs and tool-calling constraints to keep the LLM honest and reproducible. citeturn9search3turn9search13turn8search2