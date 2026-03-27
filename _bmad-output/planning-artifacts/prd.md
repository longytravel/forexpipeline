---
stepsCompleted:
  - step-01-init
  - step-02-discovery
  - step-02b-vision
  - step-02c-executive-summary
  - step-03-success
  - step-04-journeys
  - step-05-domain
  - step-06-innovation-skipped
  - step-07-project-type
  - step-08-scoping
  - step-09-functional
  - step-10-nonfunctional
  - step-11-polish
  - step-12-complete
classification:
  projectType: Desktop/CLI operations platform
  domain: Personal algorithmic trading
  complexity: high
  projectContext: brownfield
  keyConcerns:
    - Strategy generation quality
    - Backtester accuracy
    - Reconciliation effectiveness
    - Deployment reliability
  userRole: Strategy director and decision-maker, not coder or strategy author
inputDocuments:
  - product-brief-BMAD-Backtester-2026-03-13.md
  - baseline-capability-gap-assessment-ClaudeBackTester-2026-03-13.md
documentCounts:
  briefs: 1
  research: 0
  brainstorming: 0
  projectDocs: 0
  gapAssessments: 1
workflowType: 'prd'
date: 2026-03-13
author: ROG
lastEdited: 2026-03-13
editHistory:
  - date: 2026-03-13
    changes: 'Post-validation edits: added 2 missing KPIs, sharpened NFR1/NFR13/NFR19 metrics, added update strategy note, added Section 8→9 cross-reference'
---

# Product Requirements Document — BMAD Backtester

**Project:** Forex Pipeline
**Author:** ROG
**Date:** 2026-03-13

## Executive Summary

BMAD Backtester is a personal trading operations platform that takes a strategy from idea through research, coding, backtesting, optimization, validation, and live deployment — without requiring the operator to write code. The system acts as an autonomous research and execution team; the operator directs, reviews evidence, and makes decisions.

The platform is a baseline-first rebuild of the existing ClaudeBackTester system, which already provides a capable engine for data handling, backtesting, staged optimization, validation, live trading via MT5, and risk controls. What it lacks is operational coherence: a trustworthy pipeline where backtest results reliably predict live performance, and where the system actively diagnoses performance and proposes improvements.

V1 targets one end-to-end slice: a single strategy family on one pair/timeframe, taken from hypothesis through a gauntlet of testing — backtesting, optimization, forward testing, live matching — each with sub-layers of validation that progressively build confidence before real capital is at risk.

### What Makes This Special

**End-to-end fidelity.** The core promise is that backtest results predict live performance. When the system says a strategy makes money, the operator sees it making money in exactly the same way in live trading. When results diverge, the system explains why.

**Intelligent iteration.** The system doesn't just test — it diagnoses. Advanced analytics examine performance across multiple dimensions, identify what's working and what isn't, and propose specific refinements. The operator reviews suggestions, approves changes, and the system re-tests with clear before/after comparison. Winners get dialed up, losers dialed down.

**Autonomous research pipeline.** The operator provides direction and trading hypotheses. The system handles research, strategy code generation, testing, and analysis. This is a research analyst that also happens to be the execution engine.

## Project Classification

| Field | Value |
|---|---|
| **Project Type** | Desktop/CLI operations platform |
| **Domain** | Personal algorithmic trading |
| **Complexity** | High (technical — multi-stage pipeline fidelity, not regulatory) |
| **Project Context** | Brownfield — building on verified ClaudeBackTester engine capabilities |
| **Operator Role** | Strategy director and decision-maker; system handles research, coding, and execution |

## Success Criteria

### User Success

- The operator can push any strategy — profitable or not — through the entire pipeline from definition to live deployment without writing code and without the system blocking progression on profitability.
- The operator can review a coherent evidence pack at each stage and make an informed accept, reject, or refine decision.
- When the system's advanced analytics suggest refinements, the operator can understand the reasoning and see measurable before/after impact.
- The operator can confidently distinguish "the pipeline works correctly" from "this strategy is profitable" as separate questions.

### Business Success

- **3-month target:** One strategy running live on one pair/timeframe with trade-level reconciliation proving the pipeline works. Backtest-to-live fidelity within 5% on aggregate metrics, with differences attributed to known causes (spread, slippage).
- **6-month target:** Iteration loop producing measurably improved strategies. Multiple pairs or strategy families entering the pipeline. The backtester is being calibrated by real execution data.
- **12-month target:** A portfolio of live strategies — good ones expanded, poor ones retired, new ones coming online. The system is a functioning research-and-deployment operation.

### Technical Success

- **Signal-level fidelity:** When the backtester is re-run against data that includes a live trade point, it fires the same signal at the same candle.
- **Reconciliation attribution:** Every difference between backtest and live is attributed to a known category (spread, slippage, fill timing, data latency). Unexplained divergence rate trends toward zero over time.
- **Execution cost modeling:** Spread and slippage assumptions are researched and modeled per pair/session before the first backtest — not hardcoded constants. Sources include broker-published spreads, historical tick data distributions, session-aware cost profiles, and published slippage research. The cost model is a first-class pipeline artifact.
- **Backtester calibration:** The pre-researched cost model is validated and refined by live reconciliation data, making the backtester progressively more accurate over time.
- **Pipeline completeness:** Every stage emits a persisted, reviewable artifact. Interrupted runs resume from checkpoint.
- **Reproducibility:** Same strategy specification, dataset, and configuration produce materially identical results within defined tolerance.

### Measurable Outcomes

| Metric | V1 Target |
|---|---|
| End-to-end pipeline completion | At least one strategy through all stages to live |
| Aggregate backtest-to-live fidelity | Within 5% |
| Trade-level signal match rate | Same entry/exit candle on re-run with live data |
| Unexplained divergence rate | Decreasing trend, target < 5% of trades |
| Manual code interventions required | Zero for standard workflow |
| Iteration cycle improvement | Measurable metric improvement per refinement cycle until diminishing returns |
| Operator decision turnaround | Time from completed pipeline stage to operator accept/reject/refine decision — target under 1 working day for standard reviews |
| Practice promotion readiness rate | Percentage of validated candidates that produce complete evidence packs sufficient for go/no-go review — target 100% for candidates reaching promotion gate |

## Product Scope

### MVP — Pipeline Proof

One pair, one timeframe, one strategy family. The strategy does not need to be profitable. The goal is proving the machinery works end-to-end:

- Execution cost research and modeling — researched spread/slippage assumptions per pair/session as a first-class artifact before first backtest
- Strategy definition path (system-generated from operator direction)
- Backtest, optimization, and validation gauntlet
- Practice deployment via MT5
- Trade-level reconciliation comparing backtest signals to live signals
- Execution cost feedback loop (live data validates and refines the pre-researched cost model)
- Operator review and decision workflow at each stage
- Persisted artifacts and audit trail throughout

### Growth Features (Post-MVP)

- Iteration loop with advanced analytics and system-driven refinement suggestions
- Expansion to additional currency pairs using proven pipeline
- Multiple strategy families entering the pipeline concurrently
- Before/after comparison across refinement cycles
- Strategy performance diagnostics across multiple dimensions (regime, session, trade clustering, exit efficiency)
- Dial-up/dial-down allocation based on what's working

### Vision (Future)

- Full portfolio of live strategies — automated expansion, retirement, and rebalancing
- System-driven autonomous strategy research without operator prompting
- Cross-strategy correlation and portfolio-level risk management
- Progressively smarter backtester calibrated by accumulated live data
- The system operates as a complete trading research and deployment operation

## User Journeys

### Journey 1: ROG — Pipeline Proof (MVP)

ROG opens a dialogue with the system. He has a hypothesis — maybe a moving average crossover concept, maybe something the system surfaced from research. The system asks clarifying questions: what pair, what timeframe, any specific conditions or filters? ROG gives direction. The system takes over.

The system generates strategy code from the specification. ROG doesn't see the code — he sees a summary of what the strategy does and a confirmation that it matches his direction. The system runs the backtest using the pre-researched execution cost model already in the system (spread and slippage assumptions by pair/session — background infrastructure, not a conversation).

Results come back as charts first — equity curve, drawdown, trade distribution over time — with a summary narrative. The system flags anything anomalous: "This strategy produced only 12 trades in 10 years — that's unusually low. Here's why." ROG reviews, says "next stage."

Optimization runs. The system dynamically determines how many parameter groups to use based on the strategy's parameter count and interdependencies — not a hardcoded five. A strategy with 70 parameters might need ten groups; one with 6 parameters might need three. Results come back with the same chart-led presentation. Validation gauntlet follows: walk-forward, stability checks, each producing visual evidence.

Practice deployment to MT5. The system monitors. After enough trades, reconciliation kicks in: the system downloads latest data including the live trade points, re-runs the backtest, and checks — did the signal fire at the same candle? Yes. P&L difference of 0.3 pips — attributable to spread widening during news. The cost model is updated automatically in the background.

The pipeline works. The numbers match. The machinery is proven. Profitability is irrelevant at this stage — what matters is that the system behaves identically every time and the backtest predicts live signal timing.

**Requirements revealed:** Dialogue-based interaction, chart-first presentation with anomaly detection, dynamic optimization grouping, trade-level reconciliation with attribution, cost model as background infrastructure with automatic calibration, deterministic reproducibility, consistent system behavior on every load.

### Journey 2: ROG — Iteration and Refinement (Growth)

The pipeline is trusted. Now ROG wants profitable strategies. He directs the system toward a strategy family. The system runs it through the gauntlet and presents results.

The advanced analytics layer kicks in. Not just "here's your profit" — the system digs: performance by session, by regime, by day of week. Trade clustering analysis. Entry timing quality. Exit efficiency. It presents charts showing where the strategy bleeds and where it earns.

The system proposes: "Adding a chandelier exit reduces average drawdown by 15% with minimal impact on total return. Here's the before/after." ROG reviews the comparison charts. "Try it." The system re-runs with the modification, presents side-by-side results.

Over several cycles, the strategy improves. Each cycle shows measurable gains. Eventually the curve flattens — diminishing returns. The system flags it: "Last three refinements produced less than 0.5% improvement. This strategy may be near its optimization ceiling." ROG decides to deploy it live and move on to the next idea.

**Requirements revealed:** Multi-dimensional performance analytics, system-driven refinement suggestions with before/after comparison, iterative cycle tracking with diminishing returns detection, chart-led comparative presentation.

### Journey 3: ROG — Strategy Kill Decision

A strategy has been through several iteration cycles. The analytics show it's not getting better. The system presents the evidence: "After 6 refinement cycles, this strategy remains net negative across all tested configurations. The core signal appears to lack edge in current market conditions."

ROG reviews the charts, agrees, and kills it. The system archives everything — the full artifact trail — so it's available if ROG wants to revisit the concept later under different conditions. Clean, no drama.

**Requirements revealed:** Clear kill criteria presentation, strategy archival with full artifact history, ability to revisit archived strategies.

### Journey 4: System Pipeline — Stage-to-Stage Artifact Flow

Each pipeline stage produces a standardized artifact that the next stage consumes. The execution cost model feeds into the backtester. Backtest results feed into optimization. Optimization results feed into validation. Validated candidates feed into deployment.

Every artifact is versioned, persisted, and reproducible. If any stage is re-run with the same inputs, it produces the same outputs. If inputs change (new data, updated cost model), the artifact is versioned accordingly and the change is traceable.

The system behaves identically every time it's loaded. Configuration is explicit. Process is deterministic. When behavior needs to change, it changes through deliberate configuration updates, not through implicit drift.

**Requirements revealed:** Standardized artifact schemas per stage, artifact versioning and persistence, deterministic pipeline behavior, explicit configuration management, traceability of input changes.

### Journey Requirements Summary

| Capability | Revealed By |
|---|---|
| Dialogue-based operator interaction | Journey 1 |
| Execution cost model as background infrastructure | Journey 1 |
| Chart-first result presentation with summary narrative | Journeys 1, 2, 3 |
| Anomaly detection and sanity checking | Journey 1 |
| Dynamic optimization group sizing | Journey 1 |
| Trade-level reconciliation with attribution | Journey 1 |
| Automatic cost model calibration | Journey 1 |
| Deterministic reproducibility and consistent behavior | Journeys 1, 4 |
| Multi-dimensional performance analytics | Journey 2 |
| System-driven refinement suggestions | Journey 2 |
| Before/after comparative analysis | Journey 2 |
| Diminishing returns detection | Journey 2 |
| Strategy archival and kill workflow | Journey 3 |
| Standardized artifact schemas and versioning | Journey 4 |
| Explicit configuration management | Journey 4 |

## Domain-Specific Requirements

### Market Data Integrity

The system depends on accurate historical and live data. Bad data produces misleading backtests. Requirements:
- Data validation on ingestion — detect gaps, incorrect prices, timezone misalignment, and stale quotes
- Clear reporting when data quality issues are found, with the ability to quarantine suspect periods
- Consistent data sourcing so that re-runs against the same date range use identical data

### Execution Environment Constraints

MT5 is the execution gateway. Its behavior is a hard constraint:
- Order types, fill semantics, and session handling must be modeled accurately in the backtester
- The system must account for MT5-specific behaviors (partial fills, requotes, connection drops) in both practice and live
- Strategy code must be compatible with MT5's execution model — the backtester cannot simulate capabilities MT5 doesn't support

### Temporal Sensitivity

Strategies behave differently across sessions, regimes, and market conditions:
- The system must be session-aware (London, New York, Asian, overlap periods) for both analysis and execution cost modeling
- Regime detection (trending, ranging, volatile) should inform analytics and refinement suggestions
- Time-of-day and day-of-week patterns are first-class analytical dimensions

### Overfitting Risk

The biggest domain risk is a strategy that looks great in backtest and fails live because it was curve-fitted to historical noise:
- The validation gauntlet (walk-forward, stability, out-of-sample testing) exists specifically to mitigate this
- Dynamic optimization grouping reduces combinatorial explosion that enables overfitting
- The system should flag strategies with suspiciously high in-sample performance relative to out-of-sample
- Reconciliation provides the ultimate overfitting check — does live match backtest or not?

## Platform-Specific Requirements

### Interaction Architecture

The system operates through two complementary interfaces:

- **Claude Code (CLI/conversation)** — primary control and analysis layer. The operator directs strategy research, reviews system-generated analysis, makes pipeline decisions, and controls the system through natural dialogue. The system has programmatic access to all data for deep analysis.
- **Web dashboard (browser-based)** — operator visualization layer. Equity curves, trade distributions, strategy comparison, pipeline stage results, and candidate selection views render visually for the operator's review. Required from MVP — chart-led review is core to the operator workflow.

Both interfaces work from the same underlying data. The conversation layer analyzes and recommends; the dashboard layer visualizes for human review.

### Infrastructure Model

| Environment | Purpose | Trading |
|---|---|---|
| **Local laptop** | Development, deployment testing | Never — testing only, connects to same MT5 account for verification |
| **VPS** | Practice trading, live trading | All practice and live trades execute here |

- Practice trading runs on VPS with real MT5 — 0.01 lots on a £3,000 account initially
- Live trading runs on the same VPS — only lot size and risk parameters change
- Local laptop connects to the same MT5 account for deployment testing and verification but never executes trades
- Both environments see the same account state
- Significant local computing power available — the system can run intensive backtests and optimizations on the laptop

### Hardware Context

Architecture and performance decisions target this hardware:

| Component | Specification |
|---|---|
| **CPU** | Intel i9-14900HX — 16 P-cores + 16 E-cores (32 threads) |
| **RAM** | 64GB |
| **OS** | Windows 11 |
| **Broker** | IC Markets via MetaTrader 5, 1:500 leverage |
| **Data source** | Dukascopy M1 bid+ask, stored in Parquet format on Google Drive (`G:\My Drive\BackTestData`) |


### Multi-Strategy MT5 Management

Multiple strategies will run concurrently on a single MT5 instance. Requirements:
- Trade attribution — every trade must be tagged to its originating strategy
- Position sizing coordination — strategies must not collectively exceed account risk limits
- Interference prevention — strategies must not conflict on the same instrument
- Independent tracking — each strategy's equity curve, P&L, and reconciliation data are isolated

### Technical Architecture Considerations

- **Dashboard is MVP-required** — the operator needs visual evidence (equity curves, trade charts, pipeline status) to review results. Minimal but functional from day one.
- **Conversation-driven control** — the system is operable through Claude Code dialogue. The dashboard visualizes but doesn't drive workflow.
- **Data-first design** — all data is persisted and well-structured. The system analyzes programmatically; the dashboard presents visually. Same data, two lenses.
- **Environment parity** — pipeline behavior must be identical across local and VPS. The only difference is whether trades execute.
- **Always-online** — VPS is always connected. Offline operation is not a requirement.
- **No Telegram in V1** — MT5 mobile app provides sufficient remote monitoring.
- **System updates** — deployed via git pull on VPS with manual verification. No auto-update mechanism required for a personal operations platform.

### Dashboard Requirements

#### MVP Dashboard

Minimum viable visualization to support chart-led pipeline review:
- Equity curves for backtest results
- Trade distribution charts (over time, by session, by outcome)
- Pipeline stage status — clear visual showing where each strategy/candidate is in the pipeline, what passed, what failed, and why
- In-sample vs out-of-sample vs forward test period markers — lines on charts showing where temporal splits are
- Walk-forward window visualization

#### Growth Dashboard

- **Leaderboards** — strategy and candidate ranking across multiple metrics
- **Zoom in/out** — drill from portfolio overview down to individual trade level
- **Candidate selection view** — visualize parameter clusters, robustness scores, and the compression from millions of backtests down to forward test candidates
- **Before/after comparison** — side-by-side views for refinement iterations
- **Multi-dimensional analytics** — session, regime, trade clustering, entry/exit quality
- **Funnel view** — from total backtests → profitable → robust clusters → validated → forward testing → live candidates

### Decision Support Under Complexity

The system generates massive volumes of data (hundreds of thousands to millions of backtest runs). The operator must not be expected to navigate this raw. The system must compress, cluster, and present actionable views:

- **Candidate compression** — cluster similar parameter sets and present distinct groups, not thousands of near-identical rows
- **Pipeline funnel** — clear visual progression from raw backtest volume down to actionable candidates
- **Anomaly surfacing** — automatically flag results that look wrong (zero trades, suspiciously perfect curves, parameter sensitivity cliffs)
- **Decision clarity** — at every stage, the operator should understand what's being recommended and why

## Research-Dependent Design Requirements

Several core system components require dedicated research and methodology validation before implementation. Phase 0 research scope and component-level keep/replace decisions are mapped to MVP feature commitments in the Project Scoping section below. These are not features to be guessed at — they require investigation of academic literature, quant industry best practice, and potentially custom experimentation.

**Approach:** For each research-dependent component, the system (with operator support) conducts focused research to define the methodology, validates it against known standards, and implements the validated approach. The methodology becomes a versioned artifact that can be refined over time.

### Known Research-Dependent Components

| Component | Core Question | Research Domain |
|---|---|---|
| **Candidate selection pipeline** | How to compress millions of backtest results into a principled set of forward test candidates? Parameter stability analysis, clustering, statistical significance filtering, multi-objective ranking. | Quantitative finance, combinatorial optimization |
| **Optimization methodology** | Dynamic group sizing, parameter interdependency detection, avoiding combinatorial explosion while preserving important interactions. | Optimization theory, experimental design |
| **Validation gauntlet design** | Walk-forward window sizing, Monte Carlo methodology, out-of-sample split ratios, statistical confidence thresholds. | Statistical validation, time series analysis |
| **Execution cost modeling** | Spread and slippage assumptions by pair, session, volatility regime. Initial research-based model refined by live data. | Market microstructure |
| **Reconciliation methodology** | Trade-level signal matching, divergence attribution taxonomy, tolerance band calibration. Layered tolerance model — define fidelity thresholds separately at signal, order, fill, and aggregate PnL levels. | Trade execution analysis |
| **Overfitting detection** | Statistical tests to distinguish genuine edge from curve-fitting. In-sample vs out-of-sample performance ratios. | Statistical learning theory |
| **Strategy robustness scoring** | Multi-criteria assessment combining stability, sensitivity, statistical significance, and forward performance. | Portfolio construction, risk analysis |

These components represent the intellectual core of the product. Getting the methodology right is more important than getting the code right — correct methodology with basic implementation beats sophisticated engineering on a flawed approach.

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Pipeline proof through baseline reuse. ClaudeBackTester is a verified baseline with meaningful reusable capability — not an empty predecessor. The MVP wraps and adapts what exists, builds only what's genuinely missing, and proves end-to-end fidelity. A wholesale rewrite would discard useful assets and obscure the real design problem.

**Critical caveat:** "Keep" does not mean "don't question." Every baseline component must be validated through Phase 0 research before the keep/replace decision is final. If research shows a better approach exists (e.g., Optuna vs the existing optimizer, Bayesian vs grid search), we replace.

**Resource model:** Solo operator (ROG) with AI-assisted development. Significant local computing power available. The constraint is getting methodology right, not headcount.

**Architectural constraint:** ClaudeBackTester is a multi-technology monolith (Python, Rust, Node). Broad replacement is expensive. The default strategy is wrap and extend — but research may override this for specific components.

### Phase 0 — Research & Methodology Validation (Pre-MVP)

Before building, validate that every major component uses the best available approach. Research covers both new components and baseline components being kept. Phase 0 output is a validated technology and methodology decision for each component.

| Component | Research Questions | Baseline Status |
|---|---|---|
| **Backtest engine** | Event-driven vs vectorized? Best architecture for speed + fidelity? | Exists — validate or replace |
| **Rust evaluation layer** | Still optimal for hot path? Alternative approaches for batch evaluation? | Exists — validate or replace |
| **Optimization framework** | Optuna? Bayesian? Genetic algorithms? Best practice for parameter search in trading systems? Dynamic grouping approaches? | Exists as fixed five-stage — validate approach or adopt new |
| **Validation pipeline** | Walk-forward, CPCV, Monte Carlo configured optimally? Missing methodologies? Statistical confidence thresholds? | Exists — validate and enhance |
| **Strategy definition** | Best representation model? DSL, config, template? How do quant shops handle strategy specification? | Does not exist — research informs new build |
| **Candidate selection** | Parameter stability analysis, clustering, statistical filtering — principled approach? | Does not exist — research informs new build |
| **Dashboard technology** | Best visualization framework for chart-led quant dashboards? | Exists — validate or replace framework |
| **Reconciliation** | Trade-level matching methodologies, divergence attribution frameworks? | Does not exist — research informs new build |
| **Execution cost modeling** | Spread/slippage research sources, session-aware cost models? | Does not exist — research informs new build |

**Research approach:** Operator-directed AI research + dedicated deep research where needed. ROG can feed topics to external researchers in parallel with system-driven research.

**Phase 0 output:** A validated technology and methodology decision for each component. "Keep baseline" becomes a researched decision, not a default assumption. "Replace" is justified by evidence that a better approach exists.

### MVP Feature Set (Phase 1) — Pipeline Proof

**Core Journey Supported:** Journey 1 (Pipeline Proof) — one strategy, one pair, one timeframe, end-to-end.

**Must-Have Capabilities (subject to Phase 0 validation):**

| Capability | Baseline Status | MVP Work |
|---|---|---|
| Data pipeline | **Keep and adapt** — mature: acquisition, validation, splitting, timeframe conversion | Verify, minimal adaptation |
| Backtest engine | **Keep** — Rust-backed batch evaluation, core technical asset | Verify, integrate with cost model |
| Rust evaluation layer | **Keep** — important performance baseline | Validate via Phase 0 |
| Execution cost model | **Build new** — no baseline exists | Research phase + implementation |
| Optimization | **Adapt** — exists as fixed five-stage, needs dynamic grouping | Phase 0 determines approach |
| Validation pipeline | **Keep and adapt** — walk-forward, CPCV, stability, Monte Carlo, regime analysis, confidence scoring | Verify, ensure artifact output per stage |
| Risk manager | **Keep** — already aligned with trust-first goals | Verify, integrate into pipeline |
| Strategy definition | **Build new** — no deterministic path from intent to executable spec | Core new development |
| Operator workflow | **Build new** — system is developer-operated, no operator workflow | Core new development |
| MVP dashboard | **Extend** — dashboard stack exists; run history is placeholder | Add pipeline status, equity curves, temporal split markers |
| Practice deployment | **Adapt** — live trader exists with MT5, position management, risk gates | Add practice trading path, promotion gating |
| Reconciliation | **Build new** — no reconciliation subsystem exists | Core new development |
| Deterministic reproducibility | **Fix** — not enforced in baseline | Architectural enforcement |
| Artifact persistence | **Adapt** — module boundaries exist, no standardized artifact chain | Standardize stage outputs, versioning |
| Stub modules | **Build out** — `config/`, `notifications/`, `verification/`, `reporting/`, `research/` are stubs | Implement what MVP needs |

**Core new development (3 items):**
1. Strategy definition layer — dialogue-driven, system generates code from operator direction
2. Operator workflow — Claude Code conversation-driven pipeline control
3. Reconciliation subsystem — trade-level signal matching, divergence attribution

**Explicitly NOT in MVP:**
- Candidate selection pipeline (research-dependent — use manual/simple selection for MVP)
- Advanced analytics and refinement suggestions
- Multi-strategy concurrent operation
- Leaderboards and rich dashboard features
- Strategy archival and kill workflow
- Multi-pair expansion
- Portfolio manager (deferred per baseline assessment)
- Investor reporting (deferred per baseline assessment)

### Phase 2 — Growth (Intelligent Iteration)

**Journeys supported:** Journey 2 (Iteration and Refinement), Journey 3 (Strategy Kill)

- Candidate selection pipeline — research-validated methodology
- Advanced analytics — multi-dimensional performance diagnosis
- System-driven refinement suggestions with before/after comparison
- Multi-strategy MT5 — concurrent strategies with trade attribution
- Rich dashboard — leaderboards, zoom, candidate clusters, funnel visualization
- Strategy lifecycle — archival, kill decisions, revisit capability
- Diminishing returns detection
- Stub modules fully implemented

### Phase 3 — Vision (Portfolio Operations)

- Multi-pair expansion with proven pipeline
- Portfolio-level orchestration and allocation
- Automated strategy research without operator prompting
- Cross-strategy correlation and risk management
- Self-calibrating backtester from accumulated live data
- Complete trading research and deployment operation

### Risk Mitigation Strategy

**Methodology risk:** Core components need research validation before implementation. Mitigation: Phase 0 research with operator + AI collaboration.

**Fidelity risk:** Backtest-predicts-live could fail if execution isn't modeled accurately. Mitigation: execution cost research upfront, practice trading on VPS, progressive calibration.

**Baseline reuse risk:** ClaudeBackTester may have undocumented behaviors. Mitigation: verify each subsystem against gap assessment + Phase 0 research. The assessment is a starting point, not final word.

**Consistency risk:** Previous system's inconsistent behavior was the primary pain point. Mitigation: deterministic reproducibility enforced architecturally.

**Monolith risk:** Multi-technology codebase raises cost of broad changes. Mitigation: wrap and adapt by default, replace only where Phase 0 research justifies it.

## Functional Requirements

This is the capability contract for the product. If a capability is not listed here, it will not exist in the final product. UX, architecture, and epics all trace back to this list.

### Data Pipeline

- **FR1:** The system can download M1 bid+ask historical data from Dukascopy automatically
- **FR2:** The system can validate ingested data — detecting gaps, incorrect prices, timezone misalignment, and stale quotes
- **FR3:** The system can assign a data quality score to each dataset period
- **FR4:** The system can quarantine suspect data periods and report quality issues to the operator
- **FR5:** The system can store validated data in Parquet format
- **FR6:** The system can convert M1 data to higher timeframes (M5, H1, D1, W)
- **FR7:** The system can perform chronological train/test splitting of data
- **FR8:** The system can ensure consistent data sourcing so re-runs against the same date range use identical data

### Strategy Definition & Research

- **FR9:** The operator can direct strategy research through natural dialogue, providing trading hypotheses, pair/timeframe preferences, and conditions
- **FR10:** The system can autonomously research and generate executable strategy code from operator direction
- **FR11:** The operator can review a summary of what a generated strategy does and confirm it matches their intent — without seeing the underlying code
- **FR12:** The system can represent strategies in a constrained, versioned specification that is reproducible and testable
- **FR13:** Strategies can define their own optimization stages and parameter groupings

### Backtesting

- **FR14:** The system can run a strategy against historical data using a researched execution cost model (spread/slippage assumptions per pair/session)
- **FR15:** The system can produce an equity curve, trade log, and key metrics for each backtest run (win rate, profit factor, Sharpe ratio, R², max drawdown)
- **FR16:** The system can present backtest results as charts first (equity curve, drawdown, trade distribution) with a summary narrative
- **FR17:** The system can detect and flag anomalous results (unusually low trade count, suspiciously perfect curves, parameter sensitivity cliffs, zero trades over long periods)
- **FR18:** The system can produce identical backtest results given identical inputs (strategy specification, dataset, configuration)
- **FR19:** Strategy logic runs in the system; MT5 is used as an execution gateway only — the backtester cannot simulate capabilities MT5 doesn't support

### Execution Cost Modeling

- **FR20:** The system can maintain an execution cost model as a background infrastructure artifact, sourced from research (broker-published spreads, historical tick data, session-aware cost profiles, published slippage research)
- **FR21:** The system can apply session-aware spread and slippage assumptions (not flat constants) during backtesting
- **FR22:** The system can automatically update the execution cost model based on live reconciliation data

### Optimization

- **FR23:** The system can dynamically determine optimization group count and composition based on parameter count, interdependencies, and computational budget
- **FR24:** Strategies can define their own optimization stages rather than using a fixed stage model
- **FR25:** The system can run optimization across parameter space and present results with chart-led visualization
- **FR26:** The system can cluster similar high-performing parameter sets and present distinct groups rather than thousands of near-identical results
- **FR27:** The system can apply ranking mechanisms (DSR gate, diversity archive) to select candidates from optimization results
- **FR28:** The system can select forward-test candidates using a mathematically principled methodology (research-dependent — parameter stability, statistical significance, multi-objective ranking)

### Validation Gauntlet

- **FR29:** The system can run walk-forward validation with rolling train/test windows (overlapping, parallelized)
- **FR30:** The system can run Combinatorial Purged Cross-Validation (CPCV) preventing data leakage between overlapping windows
- **FR31:** The system can run parameter stability / perturbation analysis — testing whether small parameter changes produce similar results
- **FR32:** The system can run Monte Carlo simulation — bootstrap (randomize trade order), permutation (shuffle returns), stress testing (widen spreads, increase slippage)
- **FR33:** The system can run regime analysis — performance breakdown across market conditions (trending, ranging, volatile, quiet)
- **FR34:** The system can aggregate all validation stages into a confidence score with RED (fail) / YELLOW (caution) / GREEN (deploy) rating and detailed breakdown
- **FR35:** The system can flag strategies with suspiciously high in-sample performance relative to out-of-sample
- **FR36:** The system can visualize in-sample vs out-of-sample vs forward test periods with clear markers showing where temporal splits are
- **FR37:** The system can visualize walk-forward windows and their individual results

### Pipeline Workflow & Operator Control

- **FR38:** The operator can control the entire pipeline through Claude Code dialogue without writing code
- **FR39:** The operator can review a coherent evidence pack at each pipeline stage and make accept, reject, or refine decisions
- **FR40:** The system can show pipeline stage status — where each strategy/candidate is, what passed, what failed, and why
- **FR41:** The system can allow any strategy (profitable or not) to progress through the full pipeline without blocking on profitability
- **FR42:** The system can resume interrupted pipeline runs from checkpoint without data loss

### Risk Management

- **FR43:** The system can calculate position sizing based on risk parameters (risk-based lot calculation)
- **FR44:** The system can enforce pre-trade gates: drawdown limits, spread filters, and circuit breaker
- **FR45:** The system can enforce exposure controls preventing strategies from collectively exceeding account risk limits
- **FR46:** The system can tag every trade to its originating strategy for multi-strategy tracking
- **FR47:** The operator can immediately halt all live trading across all strategies via a single kill-switch action that bypasses normal workflow gates and approval steps

### Practice & Live Deployment

- **FR48:** The system can deploy strategies to MT5 on VPS for practice trading (0.01 lots, £3,000 account)
- **FR49:** The system can deploy strategies to MT5 on VPS for live trading with configurable position sizing
- **FR50:** The system can enforce that practice and live trading occur only on VPS, never on local machine
- **FR51:** The operator can promote a strategy from practice to live through an explicit go/no-go gate based on reconciliation evidence

### Reconciliation

- **FR52:** The system can perform trade-level reconciliation by re-running the backtest against data that includes live trade points and checking signal timing match (same entry/exit candle)
- **FR53:** The system can attribute every difference between backtest and live to a known category (spread, slippage, fill timing, data latency)
- **FR54:** The operator can review reconciliation results showing backtest vs live signal comparison, candle by candle

### Live Monitoring

- **FR55:** The system can continuously track live performance of deployed strategies
- **FR56:** The system can alert the operator when live results drift beyond expected tolerance from backtest predictions
- **FR57:** The system can feed monitoring data back into refinement or retirement decisions

### Artifact Management

- **FR58:** The system can emit a versioned, persisted artifact at every pipeline stage
- **FR59:** The system can maintain an explicit configuration so that all pipeline behavior is traceable and reproducible
- **FR60:** The system can track input changes (new data, updated cost model) with artifact versioning
- **FR61:** The system can behave identically every time it is loaded — deterministic, consistent, no implicit drift

### Dashboard & Visualization (MVP)

- **FR62:** The operator can view equity curves for backtest and live results in a browser-based dashboard
- **FR63:** The operator can view trade distribution charts (over time, by session, by outcome)
- **FR64:** The operator can view trade logs with key metrics per trade
- **FR65:** The operator can view pipeline stage status showing strategy progression through the gauntlet
- **FR66:** The operator can view temporal split markers on charts (in-sample, out-of-sample, forward test boundaries)
- **FR67:** The operator can view walk-forward window results
- **FR68:** The operator can view confidence score breakdown (RED/YELLOW/GREEN) per candidate

### Iteration & Refinement (Growth Phase)

- **FR69:** The system can perform multi-dimensional performance analytics (session, regime, day of week, trade clustering, entry/exit quality)
- **FR70:** The system can propose specific strategy refinements (e.g., "add a chandelier exit", "add a volatility filter") with predicted impact and before/after comparison
- **FR71:** The system can detect diminishing returns across refinement cycles and flag when iteration is no longer improving
- **FR72:** The operator can review system refinement suggestions and accept or reject them
- **FR73:** The operator can direct modifications ("try wider stops", "add a session filter") and the system implements and re-tests

### Dashboard & Visualization (Growth Phase)

- **FR74:** The operator can view leaderboards ranking strategies and candidates across multiple metrics
- **FR75:** The operator can zoom from portfolio overview down to individual trade level
- **FR76:** The operator can view candidate cluster visualizations showing parameter regions and robustness scores
- **FR77:** The operator can view the funnel from total backtests → profitable → robust clusters → validated → forward testing → live
- **FR78:** The operator can view before/after comparison for refinement iterations

### Strategy Lifecycle (Growth Phase)

- **FR79:** The operator can kill a strategy and the system archives the full artifact trail
- **FR80:** The operator can revisit archived strategies for future re-evaluation
- **FR81:** The system can detect when a live strategy should be retired (drawdown thresholds, regime shift, performance decay) and alert the operator
- **FR82:** The system can trigger periodic re-optimization on new data when markets evolve (scheduled or triggered by performance drift)

### Portfolio Operations (Vision Phase)

- **FR83:** The operator can expand proven strategies to additional currency pairs
- **FR84:** The system can manage a portfolio of concurrent live strategies with independent tracking
- **FR85:** The system can autonomously research new strategy ideas without operator prompting
- **FR86:** The system can manage cross-strategy correlation and portfolio-level risk
- **FR87:** The system can optimize capital allocation across running strategies

## Non-Functional Requirements

### Performance

- **NFR1:** Backtesting and optimization must utilize all available CPU cores and available memory through parallel execution — the system must not artificially limit itself to a fraction of available resources. Target: batch workloads sustain above 80% CPU utilization across all cores until completion or memory budget (NFR4) is exhausted
- **NFR2:** The system must enforce memory-aware job scheduling with system-level monitoring that spans all runtimes (Python, Rust, and any child processes) — not just process-level. Throttle concurrency before approaching system limits rather than allowing OOM crashes
- **NFR3:** Batch operations must use bounded worker pools with configurable concurrency limits. Optimization results must stream to persistent storage, not accumulate in memory. This prevents resource exhaustion proactively rather than reactively
- **NFR4:** The system must use a deterministic memory budgeting model: at startup, inventory available system memory, reserve a fixed OS/overhead margin (2-4GB), and pre-allocate the remainder across bounded pools and mmap regions. No dynamic heap allocation during compute hot paths. The crash prevention guarantee comes from predictable allocation — not from an arbitrary percentage ceiling. If a pipeline operation cannot fit within the pre-allocated budget, it reduces batch size or parallelism before starting — never mid-run, never crashes
- **NFR5:** Long-running optimization runs must checkpoint progress incrementally at configurable granularity (e.g., every N evaluations, where N is determined by evaluation speed and acceptable re-work on recovery). If any interruption occurs — failure, power loss, or manual stop — the run resumes from the last checkpoint rather than restarting from zero
- **NFR6:** Dashboard pages must load within 3 seconds for standard views (equity curves, pipeline status, trade logs)
- **NFR7:** Live signal execution latency is measured in two segments: (a) signal generation to order submission (system code — must complete in under 500ms) and (b) order submission to broker acknowledgement (network/broker — measured and logged, not directly controllable). Total latency above 1 second must be alerted
- **NFR8:** The specific optimization methodology (vectorized vs event-driven, parallelization strategy) is a Phase 0 research deliverable — the NFR is "maximum speed without crashes," and research determines how
- **NFR9:** The resource management strategy (memory pooling, result streaming, worker pool sizing) is a Phase 0 research output, co-determined with the optimization methodology — different optimization approaches have fundamentally different memory profiles

### Reliability

- **NFR10:** The system must prevent crashes during backtesting and optimization. Resource exhaustion must be handled by throttling, reducing batch size, or pausing — never by process termination. This is the highest-priority non-functional requirement
- **NFR11:** If a crash does occur despite prevention measures, the system must recover gracefully — resuming from the last checkpoint with no data corruption. Prevention (NFR10) and recovery (NFR11) are tested separately
- **NFR12:** VPS processes must auto-restart after reboot without manual intervention. Recovery scope: re-establish MT5 connection, resume monitoring of existing positions, re-evaluate pending signals, restore heartbeat monitoring, and alert the operator with a recovery summary
- **NFR13:** Any unplanned process termination, restart, or recovery action must alert the operator within 60 seconds of detection
- **NFR14:** The system must maintain a heartbeat monitor with context-dependent intervals — live trading processes: 30 seconds; backtesting/optimization on laptop: 5 minutes (configurable). If the process fails to report within the interval, an alert fires
- **NFR15:** Data integrity must be maintained through all failure modes using crash-safe write semantics. All pipeline artifacts use write-ahead patterns (write-then-rename or equivalent). Partial artifacts must never overwrite complete ones. If the system dies mid-stage, the last completed stage's artifact remains valid

### Security

- **NFR16:** Broker credentials and API keys must never be stored in plaintext in code, configuration files, or logs. Use environment variables or encrypted credential storage
- **NFR17:** The VPS must not expose trading control interfaces to the public internet — local access or authenticated tunnels only
- **NFR18:** The emergency kill switch (FR47) must function even when other system components have failed — it must not depend on the health of the main application. Test criteria: with the main application hung or crashed, the kill switch must close all open positions within 30 seconds

### Integration

- **NFR19:** MT5 connection drops must be retried automatically with exponential backoff, logging each retry attempt and alerting the operator if reconnection fails after 5 consecutive attempts
- **NFR20:** Data source failures (Dukascopy) must not block pipeline operations that use already-cached data. The system degrades gracefully — uses what it has, alerts about what it can't fetch
- **NFR21:** All external system interactions (MT5, data sources) must have configurable timeouts — no operation hangs indefinitely waiting for an unresponsive external service
