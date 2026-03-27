---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
inputDocuments:
  - prd.md
  - architecture.md
  - baseline-to-architecture-mapping.md
  - baseline-capability-gap-assessment-ClaudeBackTester-2026-03-13.md
---

# Forex Pipeline - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for Forex Pipeline, decomposing the requirements from the PRD and Architecture into implementable stories. The project is a brownfield rebuild of ClaudeBackTester — wrapping and extending what works, building what's missing, and proving end-to-end pipeline fidelity.

## Requirements Inventory

### Functional Requirements

**Data Pipeline (FR1-FR8)**
- FR1: The system can download M1 bid+ask historical data from Dukascopy automatically
- FR2: The system can validate ingested data — detecting gaps, incorrect prices, timezone misalignment, and stale quotes
- FR3: The system can assign a data quality score to each dataset period
- FR4: The system can quarantine suspect data periods and report quality issues to the operator
- FR5: The system can store validated data in Parquet format
- FR6: The system can convert M1 data to higher timeframes (M5, H1, D1, W)
- FR7: The system can perform chronological train/test splitting of data
- FR8: The system can ensure consistent data sourcing so re-runs against the same date range use identical data

**Strategy Definition & Research (FR9-FR13)**
- FR9: The operator can direct strategy research through natural dialogue, providing trading hypotheses, pair/timeframe preferences, and conditions
- FR10: The system can autonomously research and generate executable strategy code from operator direction
- FR11: The operator can review a summary of what a generated strategy does and confirm it matches their intent — without seeing the underlying code
- FR12: The system can represent strategies in a constrained, versioned specification that is reproducible and testable
- FR13: Strategies can define their own optimization stages and parameter groupings

**Backtesting (FR14-FR19)**
- FR14: The system can run a strategy against historical data using a researched execution cost model (spread/slippage assumptions per pair/session)
- FR15: The system can produce an equity curve, trade log, and key metrics for each backtest run (win rate, profit factor, Sharpe ratio, R-squared, max drawdown)
- FR16: The system can present backtest results as charts first (equity curve, drawdown, trade distribution) with a summary narrative
- FR17: The system can detect and flag anomalous results (unusually low trade count, suspiciously perfect curves, parameter sensitivity cliffs, zero trades over long periods)
- FR18: The system can produce identical backtest results given identical inputs (strategy specification, dataset, configuration)
- FR19: Strategy logic runs in the system; MT5 is used as an execution gateway only — the backtester cannot simulate capabilities MT5 doesn't support

**Execution Cost Modeling (FR20-FR22)**
- FR20: The system can maintain an execution cost model as a background infrastructure artifact, sourced from research (broker-published spreads, historical tick data, session-aware cost profiles, published slippage research)
- FR21: The system can apply session-aware spread and slippage assumptions (not flat constants) during backtesting
- FR22: The system can automatically update the execution cost model based on live reconciliation data

**Optimization (FR23-FR28)**
- FR23: The system can dynamically determine optimization group count and composition based on parameter count, interdependencies, and computational budget. **Research update (2026-03-18):** CV-objective research and staged-vs-joint analysis confirm that the optimizer must handle this automatically — the operator does not choose staging. Conditional parameter handling and automatic grouping are required. Architecture treats optimization as opaque to the state machine.
- FR24: Strategies can define their own optimization stages rather than using a fixed stage model. **Research update (2026-03-18):** The strategy spec defines parameter ranges and conditionals; the optimizer decides internally how to structure the search. 5-stage locking is NOT mandated — the optimizer is free to use joint optimization, 2-phase, or any methodology behind the pluggable interface.
- FR25: The system can run optimization across parameter space and present results with chart-led visualization
- FR26: The system can cluster similar high-performing parameter sets and present distinct groups rather than thousands of near-identical results
- FR27: The system can apply ranking mechanisms (DSR gate, diversity archive) to select candidates from optimization results
- FR28: The system can select forward-test candidates using a mathematically principled methodology (research-dependent — parameter stability, statistical significance, multi-objective ranking)

**Validation Gauntlet (FR29-FR37)**
- FR29: The system can run walk-forward validation with rolling train/test windows (overlapping, parallelized)
- FR30: The system can run Combinatorial Purged Cross-Validation (CPCV) preventing data leakage between overlapping windows
- FR31: The system can run parameter stability / perturbation analysis — testing whether small parameter changes produce similar results
- FR32: The system can run Monte Carlo simulation — bootstrap (randomize trade order), permutation (shuffle returns), stress testing (widen spreads, increase slippage)
- FR33: The system can run regime analysis — performance breakdown across market conditions (trending, ranging, volatile, quiet)
- FR34: The system can aggregate all validation stages into a confidence score with RED/YELLOW/GREEN rating and detailed breakdown
- FR35: The system can flag strategies with suspiciously high in-sample performance relative to out-of-sample
- FR36: The system can visualize in-sample vs out-of-sample vs forward test periods with clear markers showing where temporal splits are
- FR37: The system can visualize walk-forward windows and their individual results

**Pipeline Workflow & Operator Control (FR38-FR42)**
- FR38: The operator can control the entire pipeline through Claude Code dialogue without writing code
- FR39: The operator can review a coherent evidence pack at each pipeline stage and make accept, reject, or refine decisions
- FR40: The system can show pipeline stage status — where each strategy/candidate is, what passed, what failed, and why
- FR41: The system can allow any strategy (profitable or not) to progress through the full pipeline without blocking on profitability
- FR42: The system can resume interrupted pipeline runs from checkpoint without data loss

**Risk Management (FR43-FR47)**
- FR43: The system can calculate position sizing based on risk parameters (risk-based lot calculation)
- FR44: The system can enforce pre-trade gates: drawdown limits, spread filters, and circuit breaker
- FR45: The system can enforce exposure controls preventing strategies from collectively exceeding account risk limits
- FR46: The system can tag every trade to its originating strategy for multi-strategy tracking
- FR47: The operator can immediately halt all live trading across all strategies via a single kill-switch action that bypasses normal workflow gates and approval steps

**Practice & Live Deployment (FR48-FR51)**
- FR48: The system can deploy strategies to MT5 on VPS for practice trading (0.01 lots, 3000 GBP account)
- FR49: The system can deploy strategies to MT5 on VPS for live trading with configurable position sizing
- FR50: The system can enforce that practice and live trading occur only on VPS, never on local machine
- FR51: The operator can promote a strategy from practice to live through an explicit go/no-go gate based on reconciliation evidence

**Reconciliation (FR52-FR54)**
- FR52: The system can perform trade-level reconciliation by re-running the backtest against data that includes live trade points and checking signal timing match (same entry/exit candle)
- FR53: The system can attribute every difference between backtest and live to a known category (spread, slippage, fill timing, data latency)
- FR54: The operator can review reconciliation results showing backtest vs live signal comparison, candle by candle

**Live Monitoring (FR55-FR57)**
- FR55: The system can continuously track live performance of deployed strategies
- FR56: The system can alert the operator when live results drift beyond expected tolerance from backtest predictions
- FR57: The system can feed monitoring data back into refinement or retirement decisions

**Artifact Management (FR58-FR61)**
- FR58: The system can emit a versioned, persisted artifact at every pipeline stage
- FR59: The system can maintain an explicit configuration so that all pipeline behavior is traceable and reproducible
- FR60: The system can track input changes (new data, updated cost model) with artifact versioning
- FR61: The system can behave identically every time it is loaded — deterministic, consistent, no implicit drift

**Dashboard & Visualization — MVP (FR62-FR68)**
- FR62: The operator can view equity curves for backtest and live results in a browser-based dashboard
- FR63: The operator can view trade distribution charts (over time, by session, by outcome)
- FR64: The operator can view trade logs with key metrics per trade
- FR65: The operator can view pipeline stage status showing strategy progression through the gauntlet
- FR66: The operator can view temporal split markers on charts (in-sample, out-of-sample, forward test boundaries)
- FR67: The operator can view walk-forward window results
- FR68: The operator can view confidence score breakdown (RED/YELLOW/GREEN) per candidate

**Iteration & Refinement — Growth (FR69-FR73)**
- FR69: The system can perform multi-dimensional performance analytics (session, regime, day of week, trade clustering, entry/exit quality)
- FR70: The system can propose specific strategy refinements with predicted impact and before/after comparison
- FR71: The system can detect diminishing returns across refinement cycles and flag when iteration is no longer improving
- FR72: The operator can review system refinement suggestions and accept or reject them
- FR73: The operator can direct modifications and the system implements and re-tests

**Dashboard & Visualization — Growth (FR74-FR78)**
- FR74: The operator can view leaderboards ranking strategies and candidates across multiple metrics
- FR75: The operator can zoom from portfolio overview down to individual trade level
- FR76: The operator can view candidate cluster visualizations showing parameter regions and robustness scores
- FR77: The operator can view the funnel from total backtests to live candidates
- FR78: The operator can view before/after comparison for refinement iterations

**Strategy Lifecycle — Growth (FR79-FR82)**
- FR79: The operator can kill a strategy and the system archives the full artifact trail
- FR80: The operator can revisit archived strategies for future re-evaluation
- FR81: The system can detect when a live strategy should be retired and alert the operator
- FR82: The system can trigger periodic re-optimization on new data when markets evolve

**Portfolio Operations — Vision (FR83-FR87)**
- FR83: The operator can expand proven strategies to additional currency pairs
- FR84: The system can manage a portfolio of concurrent live strategies with independent tracking
- FR85: The system can autonomously research new strategy ideas without operator prompting
- FR86: The system can manage cross-strategy correlation and portfolio-level risk
- FR87: The system can optimize capital allocation across running strategies

### NonFunctional Requirements

**Performance (NFR1-NFR9)**
- NFR1: Backtesting and optimization must utilize all available CPU cores and available memory through parallel execution — target above 80% CPU utilization across all cores until completion or memory budget exhausted
- NFR2: The system must enforce memory-aware job scheduling with system-level monitoring spanning all runtimes (Python, Rust, child processes) — throttle concurrency before approaching system limits rather than allowing OOM crashes
- NFR3: Batch operations must use bounded worker pools with configurable concurrency limits. Optimization results must stream to persistent storage, not accumulate in memory
- NFR4: The system must use a deterministic memory budgeting model: at startup, inventory available system memory, reserve fixed OS/overhead margin (2-4GB), and pre-allocate the remainder across bounded pools and mmap regions. No dynamic heap allocation during compute hot paths. If a pipeline operation cannot fit within the pre-allocated budget, it reduces batch size or parallelism before starting — never mid-run, never crashes
- NFR5: Long-running optimization runs must checkpoint progress incrementally at configurable granularity. Interrupted runs resume from last checkpoint rather than restarting from zero
- NFR6: Dashboard pages must load within 3 seconds for standard views (equity curves, pipeline status, trade logs)
- NFR7: Live signal execution latency: signal generation to order submission under 500ms (system code). Total latency above 1 second must be alerted
- NFR8: The specific optimization methodology is a Phase 0 research deliverable — the NFR is "maximum speed without crashes"
- NFR9: The resource management strategy is a Phase 0 research output, co-determined with the optimization methodology

**Reliability (NFR10-NFR15)**
- NFR10: The system must prevent crashes during backtesting and optimization. Resource exhaustion must be handled by throttling, reducing batch size, or pausing — never by process termination. Highest-priority NFR
- NFR11: If a crash does occur despite prevention measures, the system must recover gracefully — resuming from the last checkpoint with no data corruption
- NFR12: VPS processes must auto-restart after reboot without manual intervention — re-establish MT5 connection, resume monitoring, restore heartbeat, alert operator with recovery summary
- NFR13: Any unplanned process termination, restart, or recovery action must alert the operator within 60 seconds of detection
- NFR14: The system must maintain a heartbeat monitor with context-dependent intervals — live trading: 30 seconds; backtesting/optimization on laptop: 5 minutes (configurable)
- NFR15: Data integrity must be maintained through all failure modes using crash-safe write semantics (write-ahead patterns: write-then-rename). Partial artifacts must never overwrite complete ones

**Security (NFR16-NFR18)**
- NFR16: Broker credentials and API keys must never be stored in plaintext in code, configuration files, or logs — use environment variables or encrypted credential storage
- NFR17: The VPS must not expose trading control interfaces to the public internet — local access or authenticated tunnels only
- NFR18: The emergency kill switch (FR47) must function even when other system components have failed — must close all open positions within 30 seconds with main application hung or crashed

**Integration (NFR19-NFR21)**
- NFR19: MT5 connection drops must be retried automatically with exponential backoff, alerting operator if reconnection fails after 5 consecutive attempts
- NFR20: Data source failures (Dukascopy) must not block pipeline operations that use already-cached data — graceful degradation
- NFR21: All external system interactions (MT5, data sources) must have configurable timeouts — no operation hangs indefinitely

### Additional Requirements

**From Architecture — 15 Decisions:**

- D1 (System Topology): Multi-process architecture — Python orchestrates, Rust computes, Node visualizes. Arrow IPC files as batch IPC mechanism. Rust runs in two modes: batch binary (spawned per job) and live daemon (persistent on VPS)
- D2 (Artifact Storage): Three-format hybrid — Arrow IPC (compute/canonical), SQLite (query/indexed), Parquet (archival/compressed). SQLite is derived index, rebuildable from Arrow/Parquet
- D3 (Pipeline Orchestration): Sequential state machine per strategy. Pipeline state is JSON file per strategy. Transitions typed: gated (operator review) or automatic. Resume after crash from state file. Growth phase adds strategy registry
- D4 (Dashboard-to-Backend): REST API + WebSocket via Python (FastAPI or similar). REST for historical/analytics queries, WebSocket for live state/progress/events
- D5 (Process Supervision): NSSM wraps Python orchestrator as Windows service on VPS. Kill switch as separate independent NSSM service. Auto-restart on crash, starts at boot
- D6 (Logging): Structured JSON log lines to logs/, one file per runtime per day. Alerts fire from monitoring, not log parsing
- D7 (Configuration): Layered TOML configs validated at startup. Schema validation fails loud before any stage runs. Config hash embedded in every artifact manifest. Secrets via env vars only
- D8 (Error Handling): Fail-fast at boundaries, orchestrator decides. Three categories: resource pressure (throttle), data/logic error (stop), external failure (retry with backoff)
- D9 (Operator Interface): Claude Code skills layer — structured access to every pipeline operation. Skills invoke REST API for data/mutations, Python analysis for narrative generation
- D10 (Strategy Execution Model): Specification-driven with AI generation. Three-layer: intent capture (Claude Code) → specification (JSON/TOML artifact) → evaluation (Rust engine). Format is Phase 0 research-dependent
- D11 (AI Analysis Layer): Narrative generator, anomaly detector, candidate compressor, evidence pack assembler, refinement suggester. Proactive monitoring triggers on stage completion, live divergence, cost drift, stale gates
- D12 (Reconciliation Data Flow): Augmented re-run with signal diff. Download latest data → re-run backtest with same config → diff signals candle-by-candle → attribute divergence → update cost model
- D13 (Cost Model Crate): Library crate consumed by backtester (inner-loop, not separate process). Thin CLI for standalone calibration. Session-aware spread/slippage profiles
- D14 (Strategy Engine Shared Crate): Core evaluation logic shared between backtester and live daemon. Signal fidelity guaranteed by identical code paths in both runtimes
- D15 (Live Daemon Communication): Named Pipes on Windows (kernel-level IPC, no network stack). Newline-delimited JSON protocol

**From Architecture — Cross-Cutting Concerns:**

- Session-awareness architecture: sessions as first-class dimension across cost model, backtesting, analytics, strategy conditions. Config-driven session schedule, session column stamped on every M1 bar in Arrow IPC
- Data quality gate specifications: 5 quality checks (gap detection, price integrity, timezone alignment, stale quotes, completeness), quality scoring formula, quarantine behavior, consistent data sourcing via hash-based identification
- Data volume modeling: ~2 GB per full pipeline run (single strategy, single pair). ~5.5 GB active memory during optimization peak. Growth: ~70 GB disk for 7 pairs x 5 strategies
- Contracts directory: Single source of truth for cross-runtime types — arrow_schemas.toml, sqlite_ddl.sql, error_codes.toml, session_schema.toml, strategy_specification schema
- Testing strategy: 70% unit / 20% integration / 10% system tests. Golden file tests for deterministic reproducibility. Round-trip reproducibility verification. Cross-runtime contract tests. Pre-commit local testing, no CI in MVP
- Implementation patterns: snake_case at all cross-runtime boundaries. Crash-safe write pattern (write→flush→rename). API response envelope. Config access pattern (load once, validate, freeze, hash)
- Multi-strategy resource management: Serialize optimization runs (only memory-hungry stage), allow concurrent non-optimization stages

**From Baseline-to-Architecture Mapping — Reuse Decisions:**

- **Keep:** Rust evaluation layer, backtest engine core loop, risk manager, data pipeline core (download/validation), MT5 integration
- **Wrap and extend:** strategy_engine (new spec interface wrapping existing evaluator), backtester (adapt to use strategy_engine + cost_model), validator (adapt output to Arrow IPC + confidence scoring), data_pipeline (add quality scoring/quarantine), monitoring (add context-dependent heartbeat intervals)
- **Build new:** common crate (Arrow schemas, errors, config), cost_model crate, cost_calibrator CLI, orchestrator (state machine), strategy module (spec-driven), analysis layer, reconciliation module, artifacts module, config_loader (TOML + schema), Claude Code skills, live_daemon (Named Pipes, different architecture from baseline)
- **Extend:** API (from existing dashboard backend), dashboard (add evidence packs, gates, analytics)
- **Research-dependent:** optimizer (significant rework likely after methodology research), strategy_engine interface (depends on strategy definition format research)

**From Baseline-to-Architecture Mapping — Phase 0 Research (9 topics):**

- Research 1: Strategy definition format (blocking — strategy_engine, strategy/, all compute)
- Research 2: Optimization methodology (blocking — optimizer crate)
- Research 3: Execution cost modeling (blocking — cost_model crate)
- Research 4: Python-Rust IPC (blocking — rust_bridge module)
- Research 5: Dashboard framework (parallel — dashboard build)
- Research 6: Candidate selection (parallel — analysis layer)
- Research 7: Validation gauntlet config (parallel — validator config)
- Research 8: Reconciliation methodology (parallel — reconciliation module)
- Research 9: Overfitting detection (parallel — analysis layer)

Critical path: Research topics 1-4 block implementation. Topics 5-9 can proceed in parallel.

### UX Design Requirements

N/A — no UI design document. This is a data pipeline / CLI operations platform with a browser dashboard. Dashboard requirements are captured in FR62-FR68 (MVP) and FR74-FR78 (Growth).

### Additional Notes from Epic Design

**Equity Curve Smoothness:** Smooth equity curves are a priority selection criterion for ROG. The specific metrics and weighting (R², K-Ratio, Ulcer Index, drawdown duration, etc.) are a research topic within Epic 5's research phase. Intent is captured; specifics determined by research.

### FR Coverage Map

| FR | Epic | Description |
|---|---|---|
| FR1 | Epic 1 | Download M1 bid+ask from Dukascopy |
| FR2 | Epic 1 | Validate ingested data |
| FR3 | Epic 1 | Assign data quality score |
| FR4 | Epic 1 | Quarantine suspect data |
| FR5 | Epic 1 | Store in Parquet format |
| FR6 | Epic 1 | Convert M1 to higher timeframes |
| FR7 | Epic 1 | Chronological train/test splitting |
| FR8 | Epic 1 | Consistent data sourcing |
| FR9 | Epic 2 | Operator directs strategy research via dialogue |
| FR10 | Epic 2 | System generates strategy code from direction |
| FR11 | Epic 2 | Operator reviews strategy summary |
| FR12 | Epic 2 | Constrained versioned strategy specification |
| FR13 | Epic 2 | Strategies define own optimization stages |
| FR14 | Epic 3 | Run strategy against historical data with cost model |
| FR15 | Epic 3 | Produce equity curve, trade log, key metrics |
| FR16 | Epic 3 | Chart-first results with summary narrative |
| FR17 | Epic 3 | Detect and flag anomalous results |
| FR18 | Epic 3 | Identical results from identical inputs |
| FR19 | Epic 3 | Strategy logic in system, MT5 as gateway only |
| FR20 | Epic 2 | Maintain execution cost model artifact |
| FR21 | Epic 2 | Apply session-aware spread/slippage |
| FR22 | Epic 7 | Auto-update cost model from live reconciliation |
| FR23 | Epic 5 | Dynamic optimization group sizing |
| FR24 | Epic 5 | Strategy-defined optimization stages |
| FR25 | Epic 5 | Optimization with chart-led visualization |
| FR26 | Epic 5 | Cluster similar parameter sets |
| FR27 | Epic 5 | Ranking mechanisms for candidate selection |
| FR28 | Epic 5 | Mathematically principled candidate selection |
| FR29 | Epic 5 | Walk-forward validation |
| FR30 | Epic 5 | CPCV preventing data leakage |
| FR31 | Epic 5 | Parameter stability analysis |
| FR32 | Epic 5 | Monte Carlo simulation |
| FR33 | Epic 5 | Regime analysis |
| FR34 | Epic 5 | Aggregated confidence score (RED/YELLOW/GREEN) |
| FR35 | Epic 5 | Flag in-sample vs out-of-sample divergence |
| FR36 | Epic 5 | Visualize temporal splits |
| FR37 | Epic 5 | Visualize walk-forward windows |
| FR38 | Epic 3 | Pipeline control via Claude Code dialogue |
| FR39 | Epic 3 | Evidence pack review at each stage |
| FR40 | Epic 3 | Pipeline stage status |
| FR41 | Epic 3 | No profitability gate |
| FR42 | Epic 3 | Resume from checkpoint |
| FR43 | Epic 6 | Position sizing calculation |
| FR44 | Epic 6 | Pre-trade gates (drawdown, spread, circuit breaker) |
| FR45 | Epic 6 | Exposure controls |
| FR46 | Epic 6 | Trade-to-strategy tagging |
| FR47 | Epic 6 | Kill switch |
| FR48 | Epic 6 | Deploy to MT5 practice |
| FR49 | Epic 6 | Deploy to MT5 live |
| FR50 | Epic 6 | VPS-only execution enforcement |
| FR51 | Epic 6 | Practice-to-live promotion gate |
| FR52 | Epic 7 | Trade-level reconciliation via re-run |
| FR53 | Epic 7 | Divergence attribution |
| FR54 | Epic 7 | Operator reviews reconciliation candle-by-candle |
| FR55 | Epic 6 | Continuous live performance tracking |
| FR56 | Epic 6 | Alert on drift beyond tolerance |
| FR57 | Epic 6 | Feed monitoring into refinement/retirement |
| FR58 | Epic 3 | Versioned artifact at every stage |
| FR59 | Epic 3 | Explicit traceable configuration |
| FR60 | Epic 3 | Track input changes with versioning |
| FR61 | Epic 3 | Deterministic identical behavior |
| FR62 | Epic 4 | Equity curves in dashboard |
| FR63 | Epic 4 | Trade distribution charts |
| FR64 | Epic 4 | Trade logs with metrics |
| FR65 | Epic 4 | Pipeline stage status in dashboard |
| FR66 | Epic 4 | Temporal split markers on charts |
| FR67 | Epic 4 | Walk-forward window results |
| FR68 | Epic 4 | Confidence score breakdown |
| FR69 | Epic 8 | Multi-dimensional performance analytics |
| FR70 | Epic 8 | System-proposed refinements with before/after |
| FR71 | Epic 8 | Diminishing returns detection |
| FR72 | Epic 8 | Operator review of refinement suggestions |
| FR73 | Epic 8 | Operator-directed modifications |
| FR74 | Epic 8 | Leaderboards |
| FR75 | Epic 8 | Zoom from portfolio to trade level |
| FR76 | Epic 8 | Candidate cluster visualizations |
| FR77 | Epic 8 | Funnel view |
| FR78 | Epic 8 | Before/after comparison |
| FR79 | Epic 8 | Strategy kill with archival |
| FR80 | Epic 8 | Revisit archived strategies |
| FR81 | Epic 8 | Retirement detection and alert |
| FR82 | Epic 8 | Periodic re-optimization |
| FR83 | Epic 9 | Expand to additional pairs |
| FR84 | Epic 9 | Portfolio of concurrent strategies |
| FR85 | Epic 9 | Autonomous strategy research |
| FR86 | Epic 9 | Cross-strategy correlation and risk |
| FR87 | Epic 9 | Capital allocation optimization |

**Coverage verification:** 87 FRs mapped across 9 epics. All FRs accounted for.

## Epic Design Principles

Each epic follows a consistent rhythm:

1. **Research Layer 1 — ClaudeBackTester Review:** Review the baseline implementation for this epic's domain. Assess what's reusable, what's better than planned, what's worse. Use every review as an opportunity to validate and revise our PRD/Architecture decisions.
2. **Research Layer 2 — External Research:** Academic literature, quant industry practice, technical alternatives. Use the latest information available at the time of implementation.
3. **Plan Validation:** Compare research findings against our architecture decisions. Adapt the plan if baseline or research shows a better approach.
4. **Build:** Implement based on validated decisions.
5. **E2E Pipeline Proof (Capstone):** Run the full system flow from the beginning through all completed epics. Not unit tests — the actual pipeline running a reference strategy end-to-end, verifying data flows correctly from stage to stage.

## Epic List

### Epic 1: Market Data Pipeline & Project Foundation

ROG can acquire, validate, score, and prepare high-quality market data for backtesting. Data is versioned and hash-identified for reproducibility. Project infrastructure (config, logging, contracts, project structure) is established.

- **Research Layer 1:** Review ClaudeBackTester data pipeline — acquisition, validation, splitting, timeframe conversion. Assess what's mature vs what needs rework. Validate architecture decisions against what's actually there.
- **Research Layer 2:** External research on data quality scoring, quarantine best practices, Dukascopy-specific handling.
- **Plan check:** Does ClaudeBackTester's data pipeline do anything we didn't capture in FR1-FR8? Does it handle edge cases we missed?
- **FRs covered:** FR1-FR8, FR58-FR59 (foundational artifact/config subset)
- **NFRs addressed:** NFR15 (crash-safe writes), NFR20 (graceful degradation), NFR21 (configurable timeouts)
- **Architecture:** D2 (artifact storage — initial), D6 (logging), D7 (configuration), contracts directory, project structure
- **E2E Proof:** Download EURUSD 1 year → validate → score → convert to H1 → split → verify artifacts on disk, correct and versioned. Establish reference dataset for all future pipeline proofs.
- **Dependencies:** None — starts immediately

### Epic 2: Strategy Definition & Cost Model

ROG can create a strategy through natural dialogue, review a summary of what it does, confirm it matches his intent, and have a versioned specification artifact locked for backtesting. A researched execution cost model with session-aware spread/slippage profiles is ready as background infrastructure.

- **Research Layer 1:** Deep-dive into ClaudeBackTester's Rust evaluator — what indicators exist, how strategy logic is structured, what's representable. Review the existing strategy authoring gap to understand what was actually painful.
- **Research Layer 2:** External research on strategy definition formats (DSL vs config vs template), execution cost modeling (broker spreads, tick data, session-aware profiles, slippage research).
- **Plan check:** Does the existing Rust evaluator handle things our spec doesn't cover? Are there indicator implementations we should preserve? Is our three-layer model (intent → spec → evaluator) actually better than what exists?
- **FRs covered:** FR9-FR13, FR20-FR21
- **Architecture:** D10 (strategy execution model), D13 (cost model crate), D14 (strategy engine shared crate — evaluator core)
- **E2E Proof:** Define MA crossover strategy via dialogue → review spec → verify cost model loads → verify strategy spec + cost model + reference dataset from Epic 1 all connect and are ready for backtesting.
- **Dependencies:** Epic 1 (project structure, config)

### Epic 3: Backtesting & Pipeline Operations

ROG can run a strategy against historical data using the cost model, review results via CLI (equity curve, trade log, key metrics, summary narrative), have anomalies flagged automatically, and control pipeline progression through dialogue. Results are deterministic — same inputs produce identical outputs. Interrupted runs resume from checkpoint.

- **Research Layer 1:** Review ClaudeBackTester's backtest engine — Rust batch evaluation loop, trade simulation, how Python invokes Rust. Assess what's reusable vs what needs rework for the new spec-driven model.
- **Research Layer 2:** External research on Python-Rust IPC (PyO3 vs subprocess+Arrow IPC vs shared memory), deterministic backtesting best practices.
- **Plan check:** Does the existing backtest loop handle things our architecture doesn't account for? Is the current Python-Rust boundary better than what we designed? Are there performance patterns worth preserving?
- **FRs covered:** FR14-FR19, FR38-FR42, FR58-FR61 (full artifact management)
- **NFRs addressed:** NFR1-NFR5 (performance, memory budgeting, checkpointing), NFR10-NFR11 (crash prevention/recovery)
- **Architecture:** D1 (multi-process topology), D3 (pipeline state machine), D8 (error handling), D9 (operator skills — basic pipeline set), D11 (analysis layer — narrative + anomaly + evidence packs), Python-Rust bridge
- **E2E Proof:** Reference dataset from E1 → reference strategy from E2 → cost model from E2 → backtest runs → trade log + equity curve + narrative + anomaly flags produced → pipeline state tracks progression → artifacts versioned and linked → re-run produces identical results.
- **Dependencies:** Epic 1 (market data), Epic 2 (strategy spec + cost model)

### Epic 4: Pipeline Dashboard & Visualization

ROG can visually review all pipeline results in a browser — equity curves, trade distributions by session/outcome, trade logs, pipeline stage status, temporal split markers, walk-forward window results, and confidence score breakdowns.

- **Research Layer 1:** Review ClaudeBackTester's existing dashboard — what framework, what visualizations exist, what works well, what's placeholder. Assess whether existing stack is worth keeping or replacing.
- **Research Layer 2:** External research on dashboard frameworks for chart-led quant dashboards.
- **Plan check:** Does the current dashboard do anything our FR62-FR68 missed? Is the existing framework good enough, or does research clearly show a better option?
- **FRs covered:** FR62-FR68
- **NFRs addressed:** NFR6 (3-second dashboard load)
- **Architecture:** D4 (REST API + WebSocket)
- **E2E Proof:** Run pipeline proof from E1→E2→E3 → open browser → all results visible in dashboard → charts render from real data flowing through API → pipeline status reflects actual state.
- **Dependencies:** Epic 3 (API server, data to visualize)

### Epic 5: Optimization & Validation Gauntlet

ROG can optimize strategy parameters across the full parameter space (the optimizer handles dependencies and structure internally — no mandated staging or grouping), validate robustness through the full gauntlet (walk-forward, CPCV, stability, Monte Carlo, regime analysis), see clustered candidates, and review aggregated confidence scores with clear go/caution/reject recommendations. Equity curve smoothness is a first-class selection criterion (specific metrics determined by research).

- **Research Layer 1:** Review ClaudeBackTester's optimizer (fixed 5-stage model) and validation pipeline (walk-forward, CPCV, Monte Carlo, confidence scoring). What works? What broke with the 5-stage model? (Key finding: staged grouping hides parameter dependencies — optimizer must be opaque.)
- **Research Layer 2:** External research on optimization algorithms (CMA-ES CMAwM, DE, TPE, hybrid) for batch-native ask/tell with CV-inside-objective, candidate selection (clustering, equity curve quality metrics, multi-objective ranking), validation gauntlet configuration (window sizing, Monte Carlo params, confidence score aggregation), overfitting detection.
- **Plan check:** Research confirmed 5-stage model is architecturally flawed (hides dependencies). CV-inside-objective is primary overfitting defense. Optimizer is opaque state machine behind ask/tell interface. Algorithm selection is Epic 5 research gate.
- **FRs covered:** FR23-FR28, FR29-FR37
- **NFRs addressed:** NFR5 (checkpointing), NFR8-NFR9 (research-determined methodology)
- **Architecture:** D11 (candidate compressor)
- **E2E Proof:** Full pipeline: reference data → strategy → backtest → optimize → validate → confidence score → dashboard shows optimization results + walk-forward + temporal splits. Entire flow from raw data through gauntlet works as one continuous pipeline.
- **Dependencies:** Epic 3 (backtester engine, pipeline orchestrator)

### Epic 6: Practice Deployment & Live Operations

ROG can deploy a validated strategy to MT5 on VPS for practice trading, monitor live performance, enforce risk limits (position sizing, drawdown, exposure), tag trades to strategies, and use a kill switch that works even when the main system is down. When confidence is established, ROG can promote from practice to live through an explicit evidence-based gate.

- **Research Layer 1:** Review ClaudeBackTester's live trader, MT5 integration, position management, risk gates, operational scripts. What deployment patterns exist? How does the current system handle reconnection, state persistence?
- **Research Layer 2:** External research on VPS deployment patterns for trading systems, kill switch independence patterns.
- **Plan check:** Does the existing live trader handle edge cases our FR43-FR51 didn't capture? Is NSSM the right choice given what's already there? Does the baseline's risk manager do anything our architecture missed?
- **FRs covered:** FR43-FR51, FR55-FR57
- **NFRs addressed:** NFR7 (signal latency), NFR12-NFR14 (auto-restart, alerts, heartbeat), NFR16-NFR18 (credentials, VPS isolation, independent kill switch), NFR19 (MT5 reconnect)
- **Architecture:** D5 (NSSM process supervision), D15 (Named Pipes live daemon), D14 (strategy engine — live daemon mode)
- **E2E Proof:** Full pipeline: data → strategy → backtest → optimize → validate → deploy to MT5 practice → signals fire → trades execute → monitoring tracks performance → kill switch works independently. Dashboard shows live status.
- **Dependencies:** Epic 5 (validated strategy), Epic 4 (dashboard for monitoring views)

### Epic 7: Reconciliation & Pipeline Fidelity Proof

ROG can verify that backtest signals match live signals candle-by-candle, see every divergence attributed to a known cause (spread, slippage, fill timing, data latency), and know the pipeline works. The cost model auto-calibrates from live execution data, making future backtests progressively more accurate. **Completing this epic = MVP complete.**

- **Research Layer 1:** Review ClaudeBackTester for any reconciliation-adjacent capabilities (gap assessment says none, but check for any trade comparison tooling or logging that could help).
- **Research Layer 2:** External research on reconciliation methodology — trade-level signal matching, divergence attribution taxonomy, tolerance band calibration.
- **Plan check:** Does the baseline have any reconciliation infrastructure we missed? Are there trade logging patterns that make reconciliation easier or harder?
- **FRs covered:** FR52-FR54, FR22
- **Architecture:** D12 (reconciliation data flow — augmented re-run with signal diff)
- **E2E Proof:** THE FULL MVP PIPELINE: data acquisition → validation → strategy definition → backtest → optimize → validate → deploy practice → live trades execute → reconciliation re-runs backtest against live data → signals match candle-by-candle → divergences attributed → cost model auto-updates → re-backtest with updated model. **This IS the pipeline proof the PRD promises.**
- **Dependencies:** Epic 6 (live trades to reconcile against)

### Epic 8: Iteration & Strategy Lifecycle (Growth)

ROG can get system-driven refinement suggestions backed by multi-dimensional analytics (session, regime, clustering, entry/exit quality), compare before/after across refinement cycles, detect diminishing returns, kill underperforming strategies with full archival, and revisit archived strategies. Dashboard extends with leaderboards, drill-down, candidate clusters, funnel views, and before/after comparison.

- **Research Layer 1:** Review ClaudeBackTester's analytics capabilities, any iteration tooling, strategy management patterns.
- **Research Layer 2:** External research on multi-dimensional trading analytics, refinement suggestion systems, diminishing returns detection.
- **FRs covered:** FR69-FR82
- **Dependencies:** Epic 7 (proven pipeline)

### Epic 9: Portfolio Operations (Vision)

ROG can expand to multiple currency pairs, manage a portfolio of concurrent live strategies, get autonomous research suggestions, manage cross-strategy correlation, and optimize capital allocation.

- **FRs covered:** FR83-FR87
- **Dependencies:** Epic 8

---

## Epic 1: Market Data Pipeline & Project Foundation

ROG can acquire, validate, score, and prepare high-quality market data for backtesting. Data is versioned and hash-identified for reproducibility. Project infrastructure (config, logging, contracts, project structure) is established.

### Story 1.1: ClaudeBackTester Data Pipeline Review

As the **operator**,
I want the system's data pipeline design validated against ClaudeBackTester's actual implementation,
So that I know which components to keep, adapt, or replace before writing any code.

**Acceptance Criteria:**

**Given** the ClaudeBackTester codebase is accessible
**When** the data pipeline modules are reviewed (acquisition, validation, splitting, timeframe conversion, storage)
**Then** a component verdict table is produced with keep/adapt/replace per component, with rationale
**And** any capabilities found in baseline that are missing from our PRD/Architecture are documented
**And** any baseline patterns that are better than our planned approach are flagged with a recommendation to adopt
**And** any baseline weaknesses or technical debt that should not be carried forward are documented
**And** the Architecture document is updated if findings warrant changes

### Story 1.2: External Data Quality & Acquisition Research

As the **operator**,
I want data quality scoring and acquisition best practices researched,
So that the data pipeline uses proven approaches rather than guesses.

**Acceptance Criteria:**

**Given** Story 1.1's verdict table identifies what needs research
**When** external research is conducted on data quality scoring, quarantine patterns, and Dukascopy-specific handling
**Then** a research artifact is produced covering: quality scoring methodologies, quarantine best practices, gap handling approaches, and Dukascopy API/data format specifics
**And** recommendations are compared against our Architecture's data quality gate specifications (D2, quality scoring formula)
**And** the Architecture document is updated if research shows a better approach
**And** a final build plan for Stories 1.3-1.9 is confirmed — each story knows whether it's porting baseline code or building new

### Story 1.3: Project Structure, Config & Logging Foundation

As the **operator**,
I want the project directory structure, configuration system, and structured logging established,
So that all subsequent development has a validated foundation to build on.

**Acceptance Criteria:**

**Given** the project directory layout follows the Architecture's structure pattern (D7, D6)
**When** the project is initialized
**Then** the directory structure matches the Architecture specification (src/python/, src/rust/, dashboard/, config/, contracts/, artifacts/, logs/)
**And** a `config/base.toml` exists with schema validation that fails loud at startup on invalid config (D7)
**And** environment-specific config layering works (local.toml, vps.toml)
**And** structured JSON logging writes to `logs/` with the unified log schema (D6) — timestamp, level, runtime, component, stage, strategy_id, msg
**And** the contracts directory skeleton exists with initial `arrow_schemas.toml` (including both bar and tick data schemas), `sqlite_ddl.sql`, `error_codes.toml`, `session_schema.toml`
**And** the crash-safe write pattern (write → flush → rename) is implemented as a shared utility
**And** a `.env.example` exists for secrets (MT5 credentials)
**And** config hash computation works — same config produces same hash

### Story 1.4: Dukascopy Data Download

As the **operator**,
I want to download historical data from Dukascopy — either M1 bars or tick data — with incremental updates,
So that I have complete, up-to-date market data at the resolution I need for my strategy type.

**Acceptance Criteria:**

**Given** a pair, date range, and data resolution (M1 or tick) are specified in config, with storage path `G:\My Drive\BackTestData` (configurable)
**When** the data download is executed
**Then** data is downloaded from Dukascopy at the requested resolution (FR1)
**And** M1 mode downloads aggregated M1 bid+ask bars (default, smaller, faster)
**And** tick mode downloads individual bid/ask ticks (optional, for scalping strategies)
**And** all timestamps are UTC, monotonically increasing
**And** if data already exists for part of the requested range, only the missing period is downloaded (incremental update)
**And** the incremental data is validated before merging with existing data (no gap between existing and new)
**And** a new versioned dataset artifact is created — the previous version is preserved, never overwritten
**And** download progress is logged with estimated size and time remaining
**And** if Dukascopy is unavailable, the system degrades gracefully — uses cached data if available, alerts on what it couldn't fetch (NFR20)
**And** download requests have configurable timeouts (NFR21)

### Story 1.5: Data Validation & Quality Scoring

As the **operator**,
I want ingested data validated for integrity and assigned a quality score,
So that I know the data is trustworthy before backtesting against it.

**Acceptance Criteria:**

**Given** raw data has been downloaded (Story 1.4) — M1 bars or tick data
**When** data validation runs
**Then** gap detection flags gaps > 5 consecutive M1 bars (or equivalent tick gap), WARNING if < 10 gaps/year, ERROR if > 50 gaps/year or any gap > 30 min (FR2)
**And** price integrity checks verify bid > 0, ask > bid, spread within 10x median for session (FR2)
**And** timezone alignment verifies all timestamps are UTC with no DST artifacts (FR2)
**And** stale quote detection flags periods where bid=ask or spread=0 for > 5 consecutive bars (FR2)
**And** completeness checks verify no unexpected missing weekday data (FR2)
**And** a quality score is computed using the Architecture's formula: `1.0 - (gap_penalty + integrity_penalty + staleness_penalty)` (FR3)
**And** score ranges produce correct ratings: GREEN (>= 0.95), YELLOW (0.80-0.95), RED (< 0.80) (FR3)
**And** suspect data periods are quarantined — marked in data with a `quarantined: bool` column (FR4)
**And** a quality report artifact is produced listing all issues, quarantined periods, and overall score (FR4)
**And** data with RED score blocks pipeline progression; YELLOW requires operator review
**And** all validation results are written using crash-safe write pattern (NFR15)

### Story 1.6: Parquet Storage & Arrow IPC Conversion

As the **operator**,
I want validated data stored in Parquet for archival and converted to Arrow IPC for compute,
So that data is efficiently accessible for both long-term storage and high-performance backtesting.

**Acceptance Criteria:**

**Given** data has been validated and scored (Story 1.5)
**When** storage conversion runs
**Then** validated data is stored in Parquet format with compression (FR5)
**And** data is converted to Arrow IPC format with the schema defined in `contracts/arrow_schemas.toml` — including session column computed from config schedule and quarantined column
**And** the session column is correctly stamped on every bar (or tick) based on the session schedule in `config/base.toml` (Architecture: session-awareness)
**And** Arrow IPC files are mmap-friendly for zero-copy access by Rust
**And** both Parquet and Arrow IPC files use crash-safe write pattern (NFR15)
**And** the Arrow IPC schema matches the contract definition exactly — any mismatch fails loud
**And** files are written to the configured storage path (`G:\My Drive\BackTestData`)

### Story 1.7: Timeframe Conversion

As the **operator**,
I want M1 data converted to higher timeframes (M5, H1, D1, W),
So that strategies targeting different timeframes have correctly aggregated data.

**Acceptance Criteria:**

**Given** validated data exists in Arrow IPC format (Story 1.6)
**When** timeframe conversion runs for a specified target timeframe
**Then** M1 data is correctly aggregated to the target timeframe — open from first bar, high/low from max/min, close from last bar (FR6)
**And** bid and ask columns are aggregated appropriately
**And** if source data is tick-level, it is first aggregated to M1 (open/high/low/close/bid/ask from ticks within each minute), then M1 is aggregated to higher timeframes
**And** session column is preserved or recomputed for the target timeframe
**And** quarantined bars are excluded from aggregation (bars within quarantined periods are skipped)
**And** output is stored in both Arrow IPC and Parquet formats following the same schema contracts
**And** conversion is deterministic — same input produces identical output

### Story 1.8: Data Splitting & Consistent Sourcing

As the **operator**,
I want data split chronologically for train/test and identified by hash for reproducibility,
So that backtests use consistent data and results are reproducible.

**Acceptance Criteria:**

**Given** validated, converted data exists (Story 1.7)
**When** data splitting is configured and executed
**Then** the system performs chronological train/test splitting at a configurable split point (FR7)
**And** no future data leaks into the training set — split is strictly temporal
**And** each dataset is identified by `{pair}_{start_date}_{end_date}_{source}_{download_hash}` (FR8)
**And** re-runs against the same date range use the identical Arrow IPC file with the same hash (FR8)
**And** new downloads create new versioned artifacts, never overwrite existing (FR8)
**And** the dataset identifier and hash are recorded in the artifact manifest (FR58, FR59)
**And** the manifest includes the config hash used to produce it

### Story 1.9: E2E Pipeline Proof — Market Data Flow

As the **operator**,
I want to run the full data pipeline end-to-end on a reference dataset and verify the complete artifact chain,
So that I know the market data flow works correctly before building on top of it.

**Acceptance Criteria:**

**Given** all data pipeline components are implemented (Stories 1.3-1.8)
**When** the pipeline proof is executed for EURUSD, 1 year of M1 data
**Then** data downloads successfully from Dukascopy to `G:\My Drive\BackTestData`
**And** validation runs and produces a quality score with GREEN/YELLOW/RED rating
**And** quality report artifact is produced
**And** data is stored in Parquet and converted to Arrow IPC with correct schema
**And** session column is correctly populated on every bar
**And** timeframe conversion produces H1 data correctly
**And** train/test split produces two datasets with correct temporal boundaries
**And** all artifacts are versioned, hash-identified, and linked via manifests
**And** re-running the pipeline with the same config produces identical artifacts (same hashes)
**And** all structured logs are present and correctly formatted
**And** this reference dataset is saved for use in all subsequent epic pipeline proofs

---

## Epic 2: Strategy Definition & Cost Model

ROG can create a strategy through natural dialogue, review a summary of what it does, confirm it matches his intent, and have a versioned specification artifact locked for backtesting. A researched execution cost model with session-aware spread/slippage profiles is ready as background infrastructure.

### Story 2.1: ClaudeBackTester Strategy Evaluator Review

As the **operator**,
I want the existing Rust strategy evaluator reviewed against our specification-driven architecture,
So that I know which indicator implementations, strategy patterns, and evaluator logic to keep, adapt, or replace before writing any code.

_story_type: research_

**Acceptance Criteria:**

1. **Given** the ClaudeBackTester codebase is accessible
**When** the Rust evaluator modules are reviewed (indicator implementations, strategy logic, signal generation, filter chains, exit rules)
**Then** a component verdict table is produced with keep/adapt/replace per component, with rationale

2. **And** all existing indicator implementations are catalogued with their parameter signatures and computation logic

3. **And** the existing strategy authoring workflow is documented — how ROG currently creates/modifies strategies, what was painful, what worked

4. **And** the current strategy representation format is documented — how strategies are defined, stored, and loaded by the Rust engine

5. **And** any capabilities in the baseline evaluator not covered by D10 (strategy execution model) or FR9-FR13 are documented

6. **And** any baseline evaluator patterns that are better than our three-layer model (intent → spec → evaluator) are flagged with a recommendation to adopt

7. **And** the Architecture document is updated if findings warrant changes to D10 or D14

### Story 2.2: Strategy Definition Format & Cost Modeling Research

As the **operator**,
I want strategy definition formats and execution cost modeling researched,
So that the strategy pipeline uses proven formats and realistic cost assumptions rather than guesses.

_story_type: research_

**Acceptance Criteria:**

1. **Given** Story 2.1's verdict table identifies what needs research
**When** external research is conducted on strategy definition formats and execution cost modeling
**Then** a research artifact is produced covering: strategy definition approaches (DSL vs config/TOML vs template-driven), indicator specification patterns, and constraint validation approaches

2. **And** execution cost modeling research covers: broker-published spread data sources, session-aware cost profiles (Asian/London/NY/overlap/off-hours), slippage research methodology, and tick-data-derived cost estimation

3. **And** the research compares at least 3 strategy definition format options with tradeoffs (expressiveness, tooling, AI-generation suitability, Rust parseability)

4. **And** recommendations are compared against D10 (strategy execution model) and D13 (cost model crate) specifications

5. **And** the Architecture document is updated if research shows a better approach for strategy format or cost model structure

6. **And** a final build plan for Stories 2.3-2.9 is confirmed — each story knows whether it's porting baseline code or building new

### Story 2.3: Strategy Specification Schema & Contracts

As the **operator**,
I want the strategy specification format defined with schema validation and contract enforcement,
So that every strategy is constrained, reproducible, and machine-verifiable before it enters the pipeline.

**Acceptance Criteria:**

1. **Given** the research-determined specification format (D10, Phase 0 output from Story 2.2)
**When** the strategy specification schema is created
**Then** a schema definition exists in `contracts/strategy_specification.toml` covering all D10 specification sections: metadata, entry_rules, exit_rules, position_sizing, optimization_plan, cost_model_reference (FR12)

2. **And** the schema supports the minimum representable constructs from D10: trend indicators, volatility indicators, exit types (stop loss, take profit, trailing, chandelier), session filters, volatility filters, timeframe, pair, position sizing (FR12)

3. **And** optimization_plan supports parameter_groups with ranges/step sizes, group_dependencies, and objective_function — allowing strategies to define their own optimization stages (FR13)

4. **And** a Python schema validator exists that fails loud on any specification that doesn't conform to the contract

5. **And** the validator checks: all referenced indicator types are recognized, parameter ranges are valid (min < max, step > 0), required fields are present, cost_model_reference points to a valid version string

6. **And** specification versioning works — each save creates a new version (v001, v002, ...) and previous versions are immutable (FR12)

7. **And** specification files are written using crash-safe write pattern (NFR15)

8. **And** a sample MA crossover strategy specification exists as a reference implementation

### Story 2.4: Strategy Intent Capture — Dialogue to Specification

As the **operator**,
I want to describe a trading strategy through natural dialogue and have it converted to a validated specification,
So that I can create strategies without writing code or learning a specification format.

**Acceptance Criteria:**

1. **Given** the operator provides a natural language strategy description (e.g., "Try a moving average crossover on EURUSD H1, only during London session, with a chandelier exit")
**When** the strategy intent capture process runs
**Then** a structured strategy specification is generated matching the `contracts/strategy_specification.toml` schema (FR9, FR10)

2. **And** the generated specification correctly maps dialogue elements to specification constructs: indicators, filters, exits, pair, timeframe (FR10)

3. **And** ambiguous or missing elements are resolved with sensible defaults (e.g., default position sizing, default stop loss if none specified) and the defaults are explicitly visible in the review step

4. **And** the specification passes schema validation before being presented to the operator

5. **And** the generation flow follows D10's AI generation flow: operator dialogue → Claude Code skill → specification artifact (versioned, saved)

6. **And** the specification is saved as a versioned artifact in the configured artifacts directory

7. **And** structured logs capture the intent capture event: operator input summary, generated spec version, validation result (D6)

### Story 2.5: Strategy Review, Confirmation & Versioning

As the **operator**,
I want to review a human-readable summary of what a generated strategy does, confirm it matches my intent, and have it locked for pipeline use,
So that I understand exactly what the system will execute before committing to backtesting.

**Acceptance Criteria:**

1. **Given** a strategy specification has been generated (Story 2.4)
**When** the strategy review process runs
**Then** a human-readable summary is presented: what indicators are used, entry/exit logic in plain English, filters applied, position sizing, pair, timeframe — without exposing the raw specification format (FR11)

2. **And** the operator can confirm the strategy, which locks the specification version for pipeline use

3. **And** the operator can request modifications (e.g., "try wider stops", "add a session filter") which creates a new specification version with the changes applied (D10 modification flow)

4. **And** modification creates a new versioned artifact (e.g., v001 → v002) — the previous version is preserved, never overwritten (FR12)

5. **And** when a modification is made, a diff summary shows what changed between versions (e.g., "Stop loss changed from 1.5× ATR to 2.0× ATR")

6. **And** the locked specification includes a config_hash linking it to the configuration state at time of creation (FR59)

7. **And** the specification artifact manifest records: version history, creation timestamp, operator confirmation timestamp, linked config hash

### Story 2.6: Execution Cost Model — Session-Aware Artifact

As the **operator**,
I want a researched execution cost model with session-aware spread and slippage profiles,
So that backtesting uses realistic transaction costs instead of flat assumptions.

**Acceptance Criteria:**

1. **Given** execution cost research data (broker-published spreads, historical tick data analysis, session profiles)
**When** the cost model artifact is created for a currency pair
**Then** the artifact follows D13's format: pair, version, source, calibrated_at, and per-session profiles (Asian, London, New York, London/NY overlap, off-hours) (FR20)

2. **And** each session profile contains: mean_spread_pips, std_spread, mean_slippage_pips, std_slippage — not flat constants (FR21)

3. **And** a Python cost model builder exists that can create cost model artifacts from: research data (manual input), historical tick data analysis (automated), or live calibration data (FR22 — interface only, actual live calibration data comes in Epic 7)

4. **And** cost model artifacts are versioned — new versions preserve previous versions (FR20, FR60)

5. **And** a schema definition exists in `contracts/cost_model_schema.toml` and cost model artifacts are validated against it

6. **And** a default EURUSD cost model artifact is created from research data as a baseline for pipeline proofs

7. **And** the cost model artifact is saved using crash-safe write pattern (NFR15)

8. **And** the cost model builder logs session profile statistics and data sources used (D6)

### Story 2.7: Cost Model Rust Crate

As the **operator**,
I want the execution cost model implemented as a Rust library crate that the backtester can consume,
So that session-aware transaction costs are applied efficiently in the per-trade hot path.

**Acceptance Criteria:**

1. **Given** cost model artifacts exist in D13 format (Story 2.6)
**When** the Rust cost model crate is implemented
**Then** a `crates/cost_model/` library crate exists with a public API to load a cost model artifact and query session-aware costs (D13)

2. **And** the crate can load a cost model JSON artifact, parse it, and build an in-memory session lookup table at job start

3. **And** the crate provides a `get_cost(session: &str) -> CostProfile` method that returns spread and slippage for a given session — O(1) lookup (FR21)

4. **And** the crate provides an `apply_cost(fill_price: f64, session: &str, direction: Direction) -> f64` method that adjusts a fill price by session-aware spread and slippage

5. **And** the crate validates the cost model artifact against the expected schema on load — fails loud on invalid data (D7 pattern)

6. **And** a thin CLI binary `cost_model_cli` wraps the library for standalone cost model validation and inspection (D13)

7. **And** the Cargo dependency graph matches D13: `backtester → cost_model` (lib dependency ready for Epic 3)

8. **And** unit tests verify: correct session lookup, cost application math, artifact validation, graceful error on missing/corrupt artifacts

### Story 2.8: Strategy Engine Crate — Specification Parser & Indicator Registry

As the **operator**,
I want the strategy engine crate to parse strategy specifications and maintain an indicator registry,
So that the Rust compute engine can validate and prepare strategies for evaluation in Epic 3.

**Acceptance Criteria:**

1. **Given** strategy specifications exist in the research-determined format (Story 2.3)
**When** the strategy engine crate is implemented
**Then** a `crates/strategy_engine/` library crate exists with a public API to load and validate strategy specifications (D14)

2. **And** the crate can parse a strategy specification artifact, deserialize all sections (metadata, entry_rules, exit_rules, position_sizing, optimization_plan, cost_model_reference), and build an in-memory representation

3. **And** an indicator registry exists that enumerates all supported indicator types (moving averages, ATR, Bollinger, etc.) with their parameter signatures — matching the catalogue from Story 2.1

4. **And** the crate validates that every indicator referenced in a specification exists in the registry and has valid parameters

5. **And** the crate validates that all filter types (session, volatility) reference valid configuration

6. **And** the crate validates that the cost_model_reference points to a loadable cost model artifact (cross-validates with cost_model crate from Story 2.7)

7. **And** the crate exposes a `validate_spec(spec: &StrategySpec) -> Result<ValidatedSpec, Vec<ValidationError>>` that returns all validation errors at once (not fail-on-first)

8. **And** the Cargo dependency graph matches D14: `strategy_engine` is a standalone crate that `backtester` and `live_daemon` will depend on in later epics

### Story 2.9: E2E Pipeline Proof — Strategy Definition & Cost Model

As the **operator**,
I want to run the full strategy definition and cost model flow end-to-end and verify all artifacts connect,
So that I know strategy creation and cost infrastructure work correctly before building backtesting on top of them.

**Acceptance Criteria:**

1. **Given** all strategy definition and cost model components are implemented (Stories 2.3-2.8)
**When** the pipeline proof is executed
**Then** an MA crossover strategy is defined via natural dialogue: "Moving average crossover on EURUSD H1, London session only, with chandelier exit at 3x ATR" (FR9, FR10)

2. **And** the generated specification passes schema validation and contains correct indicators, filters, exit rules, pair, timeframe

3. **And** the operator review presents a readable summary matching the dialogue intent (FR11)

4. **And** a modification is applied ("try wider stops") creating a new spec version with visible diff (D10 modification flow)

5. **And** the confirmed specification is locked and versioned with config hash (FR12)

6. **And** the EURUSD cost model artifact loads successfully with session-aware profiles (FR20, FR21)

7. **And** the Rust cost model crate loads the artifact and returns correct session-specific costs

8. **And** the Rust strategy engine crate parses the locked specification, validates all indicators exist in the registry, and confirms the spec is evaluable

9. **And** the strategy specification, cost model artifact, and Epic 1's reference dataset are all present, versioned, and linked — ready for backtesting in Epic 3

10. **And** all structured logs are present and correctly formatted (D6)

11. **And** this reference strategy and cost model are saved for use in all subsequent epic pipeline proofs

---

## Epic 3: Backtesting & Pipeline Operations

ROG can run a strategy against historical data using the cost model, review results via CLI (equity curve, trade log, key metrics, summary narrative), have anomalies flagged automatically, and control pipeline progression through dialogue. Results are deterministic — same inputs produce identical outputs. Interrupted runs resume from checkpoint.

### Story 3.1: ClaudeBackTester Backtest Engine Review

As the **operator**,
I want the existing Rust backtest engine reviewed against our specification-driven architecture,
So that I know which evaluation patterns, trade simulation logic, and Python-Rust boundary patterns to keep, adapt, or replace before writing any code.

_story_type: research_

**Acceptance Criteria:**

1. **Given** the ClaudeBackTester codebase is accessible
**When** the Rust backtest engine modules are reviewed (batch evaluation loop, trade simulation, position management, signal generation, Python-Rust invocation boundary)
**Then** a component verdict table is produced with keep/adapt/replace per component, with rationale

2. **And** the existing Python-Rust boundary is documented — how Python currently invokes Rust (subprocess, PyO3, shared memory), data exchange format, error propagation, and performance characteristics

3. **And** the existing trade simulation model is documented — how fills are calculated, how spread/slippage is applied, how position state is tracked through the evaluation loop

4. **And** any performance patterns in the baseline worth preserving are documented — memory access patterns, data layout (SoA vs AoS), parallelism approach (Rayon usage), mmap usage

5. **And** any capabilities in the baseline backtest engine not covered by FR14-FR19 or D1/D14 are documented

6. **And** any baseline patterns that are better than our multi-process architecture (D1) for the Python-Rust boundary are flagged with a recommendation to adopt

7. **And** the Architecture document is updated if findings warrant changes to D1, D8, or D14

### Story 3.2: Python-Rust IPC & Deterministic Backtesting Research

As the **operator**,
I want Python-Rust IPC mechanisms and deterministic backtesting best practices researched,
So that the backtesting pipeline uses a proven, performant bridge and guarantees reproducible results.

_story_type: research_

**Acceptance Criteria:**

1. **Given** Story 3.1's verdict table identifies the current Python-Rust boundary characteristics
**When** external research is conducted on Python-Rust IPC and deterministic backtesting
**Then** a research artifact is produced comparing at least 3 IPC options (PyO3 FFI, subprocess + Arrow IPC, shared memory / mmap) with tradeoffs: latency, serialization cost, crash isolation, complexity, debugging experience

2. **And** deterministic backtesting research covers: floating-point reproducibility across runs, random seed management for stochastic elements, deterministic iteration order in parallel evaluation, timestamp precision requirements, and platform-specific determinism concerns on Windows

3. **And** checkpoint/resume patterns are researched: incremental checkpoint strategies for long-running backtests, crash-safe checkpoint writing, resume verification (how to detect and recover from partial checkpoints) (NFR5, NFR11)

4. **And** memory budgeting patterns are researched: pre-allocation strategies for Rust batch processes, mmap data access patterns for Arrow IPC, streaming result output to avoid accumulation (NFR4, NFR10)

5. **And** recommendations are compared against D1 (multi-process topology), D3 (checkpoint/resume), and D8 (error handling at process boundaries)

6. **And** the Architecture document is updated if research shows a better approach for the Python-Rust bridge or checkpoint strategy

7. **And** a final build plan for Stories 3.3-3.9 is confirmed — each story knows whether it's porting baseline code or building new

### Story 3.3: Pipeline State Machine & Checkpoint Infrastructure

As the **operator**,
I want a pipeline orchestrator that tracks strategy progression through stages with checkpoint/resume support,
So that I can see where each strategy is in the pipeline, and interrupted runs resume without data loss.

**Acceptance Criteria:**

1. **Given** the pipeline orchestration pattern defined in D3
**When** the pipeline state machine is implemented
**Then** a `pipeline-state.json` file per strategy tracks current stage, completed stages, pending stages, and transition timestamps (D3)

2. **And** stage transitions are typed: `gated` transitions require operator review and explicit advance, `automatic` transitions proceed when preconditions are met (D3, FR39)

3. **And** pipeline stages are defined for the current epic scope: `data-ready` → `strategy-ready` → `backtest-running` → `backtest-complete` → `review-pending` (gated) → `reviewed` (FR40)

4. **And** the orchestrator can resume from crash: read state file → verify last completed artifact exists and is valid → continue from next stage (FR42, NFR11)

5. **And** within-stage checkpointing is supported: the Rust batch binary writes incremental checkpoint files at configurable granularity, and the orchestrator can detect and resume from partial checkpoints (NFR5)

6. **And** checkpoint writes use crash-safe write pattern (write → flush → rename) to prevent partial checkpoints from corrupting state (NFR15)

7. **And** the orchestrator enforces no profitability gate — any strategy can progress through the full pipeline regardless of backtest results (FR41)

8. **And** pipeline status is queryable: a Python function returns current state for any strategy including stage, progress percentage for in-progress stages, and last transition timestamp (FR40)

9. **And** structured error handling follows D8: resource pressure → throttle, data/logic error → stop and checkpoint, external failure → retry with backoff

10. **And** all state transitions are logged with the unified log schema (D6)

### Story 3.4: Python-Rust Bridge — Batch Evaluation Dispatch

As the **operator**,
I want Python to dispatch backtest jobs to the Rust batch binary with Arrow IPC data exchange,
So that the pipeline orchestrator can invoke high-performance Rust backtesting without serialization overhead.

**Acceptance Criteria:**

1. **Given** the research-determined IPC mechanism (Story 3.2) and multi-process topology (D1)
**When** the Python-Rust bridge is implemented
**Then** Python can invoke the Rust backtester binary with structured job parameters: strategy spec path, market data path (Arrow IPC), cost model path, output directory, and config hash

2. **And** the Rust binary reads market data directly via mmap of Arrow IPC files — no data copying or serialization (D1, D2)

3. **And** the Rust binary writes results as Arrow IPC files to the specified output directory — trade log, equity curve, per-trade metrics (D2)

4. **And** error propagation works across the process boundary: Rust exits with structured error on stderr (JSON matching D8 error schema), Python captures and routes to the orchestrator's error handling (D8)

5. **And** the bridge supports job cancellation: Python can signal the Rust process to checkpoint and exit gracefully (NFR5)

6. **And** the bridge reports progress: Rust writes periodic progress updates (bars processed, estimated time remaining) that Python can read for pipeline status (FR40)

7. **And** the bridge enforces memory budgeting: job parameters include memory budget, Rust pre-allocates within budget at startup (NFR4)

8. **And** process isolation is maintained: a Rust crash does not take down the Python orchestrator (D1, NFR10)

9. **And** the bridge is deterministic: identical job parameters produce identical Rust output files (FR18)

### Story 3.5: Rust Backtester Crate — Trade Simulation Engine

As the **operator**,
I want the Rust backtester to evaluate strategy specifications against historical market data with session-aware cost modeling,
So that backtest results reflect realistic execution conditions and the same code path will be used for live signals.

**Acceptance Criteria:**

1. **Given** strategy specifications from the strategy_engine crate (D14) and cost model from the cost_model crate (D13)
**When** the Rust backtester crate is implemented
**Then** a `crates/backtester/` binary crate exists that loads a validated strategy spec, market data (Arrow IPC), and cost model, and runs a complete backtest evaluation (FR14)

2. **And** the evaluation loop processes bars chronologically: for each bar, evaluate entry rules → evaluate exit rules → apply position management → record trades (FR19)

3. **And** trade fills apply session-aware costs from the cost model: the bar's session column is used to look up spread and slippage via the cost_model crate's `apply_cost` method (FR14, FR21)

4. **And** the backtester shares core evaluation logic with the future live daemon via the strategy_engine crate — signal evaluation is identical in both contexts (D14, FR19)

5. **And** the backtester produces per-trade records: entry time, exit time, entry price (adjusted for costs), exit price (adjusted for costs), direction, session, profit/loss, holding duration, exit reason (FR15)

6. **And** the backtester produces an equity curve: cumulative P&L at every bar, with drawdown tracking (FR15)

7. **And** key metrics are computed: win rate, profit factor, Sharpe ratio, R-squared of equity curve, max drawdown (amount and duration), total trades, average trade duration (FR15)

8. **And** results are deterministic: running the same strategy spec against the same market data with the same cost model produces bit-identical output (FR18)

9. **And** the backtester respects quarantined bars: no signals are generated during quarantined periods in the market data (Architecture: data quality gates)

10. **And** the backtester pre-allocates memory at startup within the specified budget and streams results to disk — no unbounded heap growth during evaluation (NFR4, NFR10)

### Story 3.6: Backtest Results — Artifact Storage & SQLite Ingest

As the **operator**,
I want backtest results stored as versioned artifacts in Arrow IPC and ingested into SQLite for querying,
So that results are efficiently accessible for both analysis and dashboard display.

**Acceptance Criteria:**

1. **Given** the Rust backtester produces Arrow IPC output files (Story 3.5)
**When** backtest results are processed by the Python orchestrator
**Then** results follow the D2 artifact storage pattern: Arrow IPC (canonical) → SQLite (queryable) → Parquet (archival)

2. **And** Arrow IPC result files are stored in the strategy's versioned artifact directory: `artifacts/{strategy_id}/v{NNN}/backtest/results.arrow`, `equity-curve.arrow`, `trade-log.arrow` (D2)

3. **And** trade-level records are ingested into SQLite with indexes on strategy_id, session, entry_time for efficient analytics queries (D2)

4. **And** a manifest.json is produced for each backtest run recording: strategy spec version, cost model version, dataset hash, config hash, run timestamp, result file paths, and key metrics summary (FR58, FR59)

5. **And** the manifest links all inputs explicitly — given a manifest, all inputs can be retrieved to reproduce the run (FR59, FR61)

6. **And** input changes are tracked with artifact versioning: if the cost model or dataset changes, a new backtest version is created rather than overwriting (FR60)

7. **And** all artifact writes use crash-safe write pattern (NFR15)

8. **And** Parquet archival copies are created for long-term compressed storage (D2)

9. **And** SQLite uses WAL mode for crash-safe concurrent read/write access (D2)

### Story 3.7: AI Analysis Layer — Narrative, Anomaly Detection & Evidence Packs

As the **operator**,
I want backtest results presented with a summary narrative, anomaly flags, and a coherent evidence pack,
So that I can quickly understand what happened, spot problems, and make informed decisions about pipeline progression.

**Acceptance Criteria:**

1. **Given** backtest results exist in SQLite and Arrow IPC (Story 3.6)
**When** the AI analysis layer processes the results
**Then** a summary narrative is generated presenting results chart-first: equity curve shape, drawdown profile, trade distribution — followed by key metrics and interpretation (FR16, D11)

2. **And** anomaly detection runs automatically, checking for: unusually low trade count (< 10 trades per year), suspiciously perfect equity curves (R² > 0.99), parameter sensitivity cliffs, zero trades over long periods (> 3 months), and win rate extremes (> 80% or < 20%) (FR17)

3. **And** each anomaly is flagged with severity (WARNING or ERROR), description, and recommendation (D11)

4. **And** an evidence pack is assembled for operator review: narrative summary, key metrics table, anomaly flags (if any), equity curve data, trade distribution by session, and links to full trade log (FR39, D11)

5. **And** the evidence pack is saved as a versioned artifact: `artifacts/{strategy_id}/v{NNN}/backtest/narrative.json` containing the narrative text, anomaly flags, and evidence pack metadata (FR58)

6. **And** the evidence pack presents enough information for the operator to make an accept/reject/refine decision without needing to inspect raw data (FR39)

7. **And** anomaly flags do NOT block pipeline progression — they inform the operator's decision but the system allows any strategy to advance (FR41)

8. **And** the analysis layer is implemented as Python modules under `src/python/analysis/` with clear interfaces: `generate_narrative(backtest_id)`, `detect_anomalies(backtest_id)`, `assemble_evidence_pack(backtest_id)` (D11)

### Story 3.8: Operator Pipeline Skills — Dialogue Control & Stage Management

As the **operator**,
I want to control the pipeline through Claude Code dialogue — running backtests, reviewing results, and advancing or rejecting stages,
So that I can operate the entire pipeline through conversation without writing code.

**Acceptance Criteria:**

1. **Given** the pipeline state machine (Story 3.3) and evidence pack generation (Story 3.7)
**When** the operator pipeline operations are implemented
**Then** the existing `/pipeline` skill is extended with a "Run Backtest" operation that triggers a backtest for a specified strategy, invoking the Python-Rust bridge and tracking progress (FR38, D9)

2. **And** the `/pipeline` skill's "Status" operation is extended to display pipeline state for all strategies: stage, progress, last transition, any anomaly flags (FR40, D9)

3. **And** the `/pipeline` skill is extended with a "Review Results" operation that presents the evidence pack (narrative, metrics, anomalies) and prompts the operator for accept/reject/refine decision (FR39, D9)

4. **And** the `/pipeline` skill is extended with an "Advance Stage" operation that moves a strategy to the next stage after operator review — recording the decision and timestamp in the pipeline state (FR39, D9)

5. **And** the `/pipeline` skill is extended with a "Reject Stage" operation that marks a strategy stage as rejected with operator-provided reason — the strategy can be modified and re-submitted (FR39, D9)

6. **And** the `/pipeline` skill is extended with a "Resume Pipeline" operation that detects interrupted runs and resumes from the last checkpoint (FR42, D9)

7. **And** all operations follow the D9 implementation pattern: read pipeline state from filesystem, invoke Python modules for mutations, present structured output to operator. All operations are accessible from the single `/pipeline` menu — no separate skills are created

8. **And** skills enforce the no-profitability-gate principle: at no point does a skill block progression based on P&L results (FR41)

9. **And** all skill invocations are logged with the unified log schema including operator actions (D6)

### Story 3.9: E2E Pipeline Proof — Backtesting & Pipeline Operations

As the **operator**,
I want to run the full backtesting pipeline end-to-end — from market data through strategy evaluation to reviewed results — and verify deterministic reproducibility,
So that I know the backtesting engine and pipeline operations work correctly before building optimization on top of them.

**Acceptance Criteria:**

1. **Given** all backtesting and pipeline components are implemented (Stories 3.3-3.8)
**When** the pipeline proof is executed using Epic 1's reference dataset and Epic 2's reference strategy and cost model
**Then** the pipeline state machine initializes for the reference strategy and tracks progression through stages (D3, FR40)

2. **And** the Python-Rust bridge dispatches the backtest job with correct parameters: strategy spec path, market data path, cost model path, memory budget (D1)

3. **And** the Rust backtester evaluates the strategy against the reference dataset with session-aware cost application and produces trade log, equity curve, and key metrics (FR14, FR15)

4. **And** results are stored as versioned artifacts in Arrow IPC, ingested into SQLite, and archived to Parquet (D2, FR58)

5. **And** the manifest links all inputs: dataset hash, strategy spec version, cost model version, config hash (FR59)

6. **And** the AI analysis layer generates a narrative summary, runs anomaly detection, and assembles an evidence pack (FR16, FR17, D11)

7. **And** the operator reviews the evidence pack via `/pipeline` → "Review Results" and advances the pipeline via `/pipeline` → "Advance Stage" (FR39, D9)

8. **And** `/pipeline` → "Status" shows the correct stage progression with timestamps (FR40)

9. **And** a second run with identical inputs produces bit-identical results: same trade log, same equity curve, same metrics, same manifest hash (FR18, FR61)

10. **And** pipeline resume works: if the backtest is interrupted mid-run and restarted, it resumes from the last checkpoint rather than restarting (FR42, NFR5)

11. **And** all structured logs are present and correctly formatted across both Python and Rust runtimes (D6)

12. **And** this backtest result and pipeline state are saved for use in all subsequent epic pipeline proofs

---

## Epic 5: Optimization & Validation Gauntlet

ROG can optimize strategy parameters across the full parameter space, validate robustness through the full gauntlet, see clustered candidates, and review aggregated confidence scores with clear go/caution/reject recommendations.

### Story 5.1: ClaudeBackTester Optimizer & Validation Pipeline Review

As the **operator**,
I want the existing ClaudeBackTester optimizer and validation pipeline reviewed against our opaque-optimizer architecture,
So that I know which optimization patterns, validation logic, and confidence scoring to keep, adapt, or replace before writing any code.

_story_type: research_

**Acceptance Criteria:**

1. **Given** the ClaudeBackTester codebase is accessible
**When** the optimizer modules are reviewed (5-stage parameter locking, evaluation dispatch, candidate tracking, convergence logic)
**Then** a component verdict table is produced with keep/adapt/replace per component, with rationale — specifically noting how the 5-stage model hides parameter dependencies

2. **And** the existing validation pipeline is reviewed: walk-forward implementation, CPCV implementation (if any), Monte Carlo simulation, confidence scoring formula, regime analysis
**Then** each validation component gets a verdict: keep/adapt/replace with rationale

3. **And** the existing candidate selection logic is documented — how ClaudeBackTester currently ranks, filters, and presents optimization results to the operator

4. **And** any parameter grouping or staging patterns in the baseline are documented with their actual behavior — do they work, do they hide dependencies, what broke in March 2026 testing?

5. **And** the current optimizer's interface with the Rust evaluator is documented — how candidates are dispatched, how scores are returned, batch size handling, parallelism model

6. **And** any capabilities in the baseline optimizer not covered by FR23-FR28 or the baseline validation pipeline not covered by FR29-FR37 are documented

7. **And** the Architecture document is updated if findings warrant changes to D3, D11, or the optimizer crate design

**Research sources to review:**
- ClaudeBackTester optimizer modules (Python orchestration + Rust evaluation)
- ClaudeBackTester validation pipeline (walk-forward, confidence scoring)
- March 2026 optimization testing results (CMA-ES vs random search, OOS failure analysis)
- Existing optimization research: `_bmad-output/planning-artifacts/research/briefs/optimization/` (CV-objective framework, methodology summary)

### Story 5.2: Optimization Algorithm, Candidate Selection & Validation Gauntlet Research

As the **operator**,
I want optimization algorithms, candidate selection methodology, and validation gauntlet configuration researched against our specific architecture,
So that implementation stories use proven, research-backed approaches rather than guesses.

_story_type: research_

**Acceptance Criteria:**

1. **Given** Story 5.1's verdict table identifies what needs external research
**When** external research is conducted on optimization algorithms for batch-native ask/tell with CV-inside-objective
**Then** a research artifact recommends: primary algorithm (from CMA-ES CMAwM, DE, TPE, hybrid candidates), Python library for ask/tell implementation, population sizing, convergence detection, and handling of mixed parameter types (continuous, integer, categorical, conditional)

2. **And** candidate selection research covers: equity curve quality metrics (Ulcer Index, K-Ratio, R-squared, Serenity Ratio, and others used by quant practitioners), multi-objective ranking framework, parameter space clustering methodology (algorithm, distance metric, cluster count), and diversity archive design (MAP-Elites or post-hoc)

3. **And** validation gauntlet configuration research covers: walk-forward window sizing for forex M1 data (anchored vs rolling, number of windows, purge/embargo gaps), CPCV parameterization (N groups, k test groups, purge sizing, PBO threshold), Monte Carlo simulation parameters (sim counts for bootstrap/permutation/stress, stress levels for cost model), parameter perturbation methodology, and regime analysis configuration (volatility bucketing, session interaction, minimum trade counts)

4. **And** confidence score aggregation research covers: how to combine walk-forward + CPCV + stability + Monte Carlo + regime results into RED/YELLOW/GREEN rating, weighting methodology, hard gates vs continuous scoring, and threshold calibration

5. **And** recommendations are compared against the Architecture decisions (D3 opaque optimizer, D11 candidate compressor, CV-inside-objective from optimization research) and against FR23-FR28, FR29-FR37

6. **And** the Architecture document is updated if research shows a better approach than currently specified

7. **And** a final build plan for Stories 5.3+ is confirmed — each implementation story knows the research-backed approach it will use

**Research sources (completed):**
- Brief 5A — Algorithm selection: `research/briefs/5A/` (4 files: brief, deep research report, compass artifact, algorithm recommendation)
- Brief 5B — Candidate selection & equity curve quality: `research/briefs/5B/` (4 files: brief, deep research report, compass artifact, quant strategy selection)
- Brief 5C — Validation gauntlet configuration: `research/briefs/5C/` (4 files: brief, deep research report, compass artifact, gauntlet configuration)
- Prior optimization research: `research/briefs/optimization/` (CV-objective framework, implementation plan, methodology summary)
- Brief 3B — Deterministic backtesting & validation methodology (walk-forward, CPCV, overfitting detection, regime analysis)
- Brief 3C — Results analysis, anomaly detection, evidence packs
- HuggingFace optimization research: `research/briefs/5A/Hugging Face Optimization Research Brief.txt` (Shiwa/NGOpt meta-optimizer, algorithm comparison matrix)
- Codex comparative review: `research/briefs/5A/codex-huggingface-review.md` (HuggingFace vs existing research analysis)

### Story 5.2b: Optimization Search Space Schema & Intelligent Range Proposal

As the **operator**,
I want the strategy specification's optimization_plan to use a flat parameter registry with D10 taxonomy support (continuous, integer, categorical, conditional) instead of staged parameter groups, and I want the system to intelligently propose sensible parameter ranges based on the indicator registry, pair volatility, timeframe scaling, and actual market data statistics,
So that complex Expert Advisors with 20+ exit types, 40+ parameters, and deeply nested conditional branches can define their optimization search space correctly — and I don't have to hand-tune every range for every new strategy.

**Acceptance Criteria:**

1. **Given** the strategy specification schema defines an optimization_plan section
**When** the schema is evaluated against FR24 (no mandated staging or grouping)
**Then** the `parameter_groups` and `group_dependencies` fields are replaced with a flat `parameters` registry where each parameter declares: type (continuous/integer/categorical), bounds (min/max for numeric, choices for categorical), optional step (for integer rounding/display), and optional condition (parent parameter + value for conditional activation)

2. **And** the schema supports deeply nested conditional parameters — a categorical parameter's choice can itself contain child parameters that are also categorical with their own children — enabling complex EA structures like exit_type → trailing_method → chandelier → atr_period/atr_multiplier without depth limits

3. **And** the Pydantic v2 validators in specification.py are updated to validate the new schema: parameter type correctness, bounds validity (min < max), condition references point to valid categorical parents with valid choice values, no orphaned conditions, no circular dependencies

4. **Given** a strategy is being created via intent capture (Story 2-4 flow)
**When** the system knows the indicator types, pair, and timeframe
**Then** a range proposal engine proposes sensible optimization bounds for every searchable parameter using: indicator registry metadata (parameter types, typical ranges), timeframe scaling heuristics (M1 periods differ from D1), pair volatility from actual market data (ATR-based scaling for pip-denominated params), and physical constraints (stop_loss > typical spread, period < available data bars)

5. **And** the range proposal engine computes pair-specific ATR statistics from the actual downloaded market data (Epic 1) at the strategy's timeframe — using these to scale pip-based parameter ranges (wider ranges for volatile pairs, tighter for stable pairs)

6. **And** the operator can review, adjust, or override any proposed range before the optimization_plan is finalized — the proposal is a smart default, not a mandate

7. **And** cross-parameter constraints are validated: slow_period > fast_period ranges don't overlap impossibly, conditional parameters only activate when their parent condition is met, pip-based ranges are pair-appropriate

8. **Given** the reference strategy (ma-crossover) exists at v001
**When** the schema migration runs
**Then** a v002 is created with the new flat parameter registry format, expanded to include all searchable parameters (entry indicators, stop loss type/values, take profit type/values, trailing stop params, session filter) with ranges proposed by the range proposal engine

9. **And** the /pipeline skill is updated to support: "Propose optimization space" (runs range proposal for current strategy), "Review search space" (shows parameter registry with ranges), and "Adjust parameter range" (operator overrides)

10. **And** the contract for Story 5-3's `parse_strategy_params()` is clearly defined: function signature, input format (new optimization_plan), output format (ParameterSpace with branches), and how conditional parameters map to optimizer sub-portfolios

- **FRs covered:** FR12, FR13, FR24 (updated — no staged groups)
- **Architecture:** D10 (parameter taxonomy), D7 (configuration)
- **Dependencies:** Story 2-3 (schema contracts), Story 2-4 (intent capture), Epic 1 (market data for ATR stats)
- **Downstream:** Story 5-3 (parse_strategy_params reads this), Story 5-7 (E2E proof uses reference v002)

### Story 5.3: Python Optimization Orchestrator

As the **operator**,
I want a Python optimization orchestrator that manages a portfolio of algorithm instances via ask/tell, dispatches batch evaluations to the Rust evaluator with CV-inside-objective fold management, and tracks candidates with checkpointing,
So that optimization runs are robust, resumable, and exploit the full batch throughput of the Rust evaluator — with a configurable portfolio that adapts to parameter count for Growth-phase scalability.

**Acceptance Criteria:**

1. **Given** a strategy specification and market data exist from Epic 2 and Epic 1
**When** an optimization run is started via the pipeline
**Then** the orchestrator initializes a portfolio of algorithm instances: CMA-ES (CatCMAwM) via `cmaes` library + DE (TwoPointsDE) via Nevergrad, filling the configured batch capacity per generation (D3, FR23). Batch size (default 2048) and portfolio composition are config-driven, not hardcoded

2. **And** the optimizer handles the full D10 parameter taxonomy: continuous, integer, categorical, and conditional parameters — without mandated staging or grouping (FR23, FR24 research update)

3. **And** each generation follows the ask/tell cycle: ask N candidates from all instances → dispatch batch to Rust evaluator via Epic 3 bridge (D1) → receive per-fold scores → tell scores back to each instance

4. **And** the CV-inside-objective is computed correctly: each candidate is evaluated across K folds, producing a score of mean - lambda * std where lambda is configurable (default from optimization research, ~1.0-2.0)

5. **And** fold boundaries are passed to the Rust evaluator as part of the batch dispatch, enabling fold-aware evaluation without duplicating data (D1 fold-aware batch evaluation)

6. **And** population sizing scales with parameter dimensionality: `pop = max(128, 5 * N_params)` as baseline heuristic, with BIPOP/IPOP restart strategy for multi-basin exploration. Instance count adjusts inversely (fewer instances with larger populations for high-D spaces)

7. **And** convergence detection uses relaxed tolerances (tolfun >= 1e-3) appropriate for noisy CV objectives, with stagnation detection triggering restarts rather than premature termination

8. **And** the orchestrator supports checkpointing: optimizer state (all instance populations, generation count, best candidates) is persisted at configurable intervals using crash-safe write pattern (NFR5, NFR15)

9. **And** interrupted optimization runs can be resumed from the last checkpoint without data loss (FR42)

10. **And** a quasi-random sampling component (Sobol/Halton) runs alongside algorithm instances to ensure exploration of unexplored regions

11. **And** memory usage stays within the deterministic budget (~5.5GB peak) with bounded worker pools and streaming results (NFR1-NFR4)

12. **And** optimization progress is logged with structured JSON logging (D6): generation number, best score, population diversity metrics, instance-level status

13. **And** optimization results are written as Arrow IPC artifacts: all evaluated candidates with their per-fold scores, objective values, and parameter vectors (D2, FR25)

14. **And** conditional parameters are handled via branch decomposition: top-level categoricals (e.g., exit_type) split the search into separate sub-portfolios per branch, keeping effective dimensionality manageable as strategies grow. Batch budget is allocated across branches proportionally or via multi-armed bandit (UCB1) shifting toward promising branches

15. **And** the V1 simple candidate promotion path works: top-N candidates by objective score are presented for operator review, without requiring advanced clustering (V1 fallback for FR26-FR28 which are Growth-phase)

- **FRs covered:** FR23, FR24, FR25 (MVP optimization core)
- **NFRs addressed:** NFR1-NFR5 (performance, memory, checkpointing)
- **Architecture:** D1 (fold-aware batch evaluation), D3 (opaque optimizer), D10 (parameter taxonomy)
- **Dependencies:** Story 5.2 (research decisions), Epic 3 Stories 3.4-3.5 (Rust bridge + evaluator)
- **Research sources:** Brief 5A (algorithm selection + HuggingFace review), optimization research (CV-objective framework)

### Story 5.4: Validation Gauntlet

As the **operator**,
I want optimized candidates run through an independent validation gauntlet — walk-forward, CPCV, parameter perturbation, Monte Carlo, and regime analysis — each producing reviewable artifacts,
So that I can distinguish genuinely robust strategies from overfit ones before committing to practice deployment.

**Acceptance Criteria:**

1. **Given** optimization has produced ranked candidates (Story 5.3)
**When** the validation gauntlet is triggered for selected candidates
**Then** walk-forward validation runs with rolling windows sized per research recommendations for forex M1 data, with purge/embargo gaps preventing leakage between train and test periods (FR29)

2. **And** walk-forward uses temporal ordering (train on past, test on future) as an independent validation layer distinct from the CV-inside-objective used during optimization

3. **And** CPCV runs with research-determined configuration: N groups, k test groups, purge/embargo sizing appropriate for indicator lookback periods and strategy holding times (FR30)

4. **And** CPCV results produce a Probability of Backtest Overfitting (PBO) score — PBO > 0.40 is a hard RED gate per D11

5. **And** parameter perturbation analysis tests each candidate: small changes to parameters (research-defined neighborhood) produce similar performance, with stability metrics quantifying sensitivity (FR31)

6. **And** Monte Carlo simulation runs three variants: bootstrap (randomize trade order, 1000+ sims), permutation (shuffle returns for significance testing), and stress testing (widen spreads/slippage to 1.5x, 2x, 3x cost model) (FR32)

7. **And** regime analysis breaks down performance across market conditions: volatility terciles crossed with forex sessions where trade counts permit, with minimum trade count thresholds per bucket for statistical validity (FR33)

8. **And** each validation stage produces its own Arrow IPC artifact with results, plus a human-readable summary for the evidence pack (D2, FR39)

9. **And** the gauntlet runs stages in an optimized order: cheapest/fastest filters first (perturbation, then walk-forward, then CPCV, then Monte Carlo, then regime) with configurable short-circuit logic (if walk-forward fails badly, skip expensive stages)

10. **And** strategies with suspiciously high in-sample performance relative to out-of-sample are flagged automatically (FR35)

11. **And** DSR (Deflated Sharpe Ratio) is computed for all candidates with >10 evaluated — mandatory per D11

12. **And** gauntlet progress is checkpointed: if interrupted mid-gauntlet, it resumes from the last completed stage for each candidate (NFR5)

13. **And** visualization data is produced for: in-sample vs out-of-sample vs forward test periods with clear temporal split markers (FR36), and walk-forward window individual results (FR37)

14. **And** all validation runs are deterministic: same candidate + same data + same config produces identical results (FR18)

- **FRs covered:** FR29-FR33, FR35-FR37 (validation gauntlet core + visualization data)
- **NFRs addressed:** NFR5 (checkpointing), NFR8-NFR9 (research-determined methodology)
- **Architecture:** D11 (validation gates: DSR mandatory, PBO <= 0.40), D1 (Rust evaluation for walk-forward windows)
- **Dependencies:** Story 5.3 (optimization candidates), Story 5.2 (gauntlet configuration research)
- **Research sources:** Brief 5C (gauntlet configuration), Brief 3B (validation methodology), Brief 5A (CV-objective interaction with walk-forward)

### Story 5.5: Confidence Scoring & Evidence Packs

As the **operator**,
I want all validation results aggregated into a single confidence score with RED/YELLOW/GREEN rating and detailed breakdown, assembled into an evidence pack I can review in under 60 seconds for the headline and 15 minutes for the full assessment,
So that I can make an informed go/caution/reject decision on each candidate without needing to interpret raw statistical output.

**Acceptance Criteria:**

1. **Given** a candidate has completed the full validation gauntlet (Story 5.4)
**When** confidence scoring runs
**Then** all validation stage results are aggregated into a composite confidence score using the research-determined formula: hard gates first (DSR pass, PBO <= 0.40, cost stress survival at 1.5x), then weighted scoring across remaining components (FR34)

2. **And** the confidence score produces a clear RED/YELLOW/GREEN rating with research-calibrated thresholds — RED means reject (hard gate failed or composite below threshold), YELLOW means caution (passed gates but marginal on some components), GREEN means proceed (strong across all components)

3. **And** the detailed breakdown shows each component's individual score, its weight in the composite, whether it passed/failed any hard gate, and a one-line interpretation (FR34)

4. **And** an evidence pack is assembled per Brief 3C's two-pass specification: Pass 1 (60-second summary card) with headline metrics, dominant edge description, top 3 risks, delta vs baseline; Pass 2 (15-minute full review) with complete charts and statistical detail (D11, FR39)

5. **And** every narrative claim in the evidence pack cites exact metric IDs or chart IDs — no ungrounded statements (D11 deterministic-first, LLM-second narrative architecture from Brief 3C)

6. **And** the AI analysis layer generates narrative summaries using structured inputs only: JSON metric sets + anomaly flags + evidence artifact references → constrained structured output (D11, FR16)

7. **And** anomaly detection runs the two-tier system: Layer A silent scoring on all candidates, Layer B surfaced flags when multiple detectors agree or tier-1 academic tests trigger (Brief 3C anomaly detection toolkit, FR17, FR35)

8. **And** the evidence pack includes a decision trace: pre-committed thresholds and gates used, PASS/FAIL outcome per gate, operator note fields for the review decision (Brief 3C evidence pack specification)

9. **And** the operator can review candidates via `/pipeline` → "Review Optimization Results" and make accept/reject/refine decisions that advance the pipeline (FR39, D9)

10. **And** all confidence scores, evidence packs, and operator decisions are persisted as versioned artifacts with crash-safe write pattern (D2, NFR15, FR58)

11. **And** visualization data includes: equity curve quality charts, walk-forward per-window results, parameter sensitivity heatmaps, Monte Carlo distribution plots, regime performance breakdown (FR25, FR36, FR37)

- **FRs covered:** FR34 (confidence score), FR16-FR17 (narrative + anomaly), FR25 (chart-led visualization), FR35-FR37 (overfitting flags + temporal visualization)
- **Architecture:** D11 (AI analysis layer, two-pass evidence packs, DSR/PBO gates), D9 (operator dialogue control)
- **Dependencies:** Story 5.4 (validation results), Story 3.7 (AI analysis layer infrastructure), Story 3.8 (operator pipeline skills)
- **Research sources:** Brief 5C (confidence score aggregation), Brief 3C (evidence packs, narrative architecture, anomaly detection)

### Story 5.6: Advanced Candidate Selection — Clustering & Diversity (Growth)

As the **operator**,
I want optimization results clustered into distinct parameter groups, ranked using multi-objective methodology with equity curve quality as a first-class criterion, and selected for forward-testing using a mathematically principled diversity-preserving approach,
So that I evaluate genuinely different strategies rather than thousands of near-identical parameter sets.

_story_type: growth_

**Acceptance Criteria:**

1. **Given** optimization has produced 10K+ evaluated candidates (Story 5.3)
**When** candidate selection runs
**Then** similar parameter sets are clustered using Gower distance + HDBSCAN (resolving D11 DBSCAN specification in favor of HDBSCAN per 5B research), producing distinct groups with automatic cluster count determination (FR26)

2. **And** equity curve quality metrics are computed for each candidate: K-Ratio, Ulcer Index, DSR, Gain-to-Pain Ratio, Serenity Ratio — per Brief 5B research recommendations

3. **And** multi-objective ranking uses TOPSIS with CRITIC-derived weights across a 4-stage filtering funnel: hard gates → TOPSIS ranking → stability filtering → Pareto frontier (FR27)

4. **And** forward-test candidates are selected using mathematically principled methodology that preserves diversity across clusters — not just top-N from a single ranking (FR28)

5. **And** a diversity archive (MAP-Elites style) maintains behavioral diversity across dimensions defined by research (e.g., trade frequency, holding time, win rate, max drawdown) with 80/20 deterministic-exploratory split

6. **And** cluster representatives and ranking rationale are presented to the operator with visualization: parallel coordinates, parameter heatmaps, cluster membership (FR26)

7. **And** the output is 5-20 diverse candidates ready for validation gauntlet, with clear documentation of why each was selected (FR28)

8. **And** the Architecture document D11 is updated to reflect HDBSCAN over DBSCAN if the research finding is confirmed during implementation

- **FRs covered:** FR26 (clustering), FR27 (ranking), FR28 (principled selection) — all Growth-phase per PRD
- **Architecture:** D11 (candidate compressor — HDBSCAN amendment)
- **Dependencies:** Story 5.3 (optimization candidates), Story 5.2 (selection methodology research)
- **Note:** This is a **Growth-phase** story. MVP uses V1 simple candidate promotion (top-N by objective + operator review) defined in Story 5.3. This story adds the advanced selection pipeline on top.
- **Research sources:** Brief 5B (candidate selection, equity curve quality, clustering, diversity archive)

### Story 5.7: E2E Pipeline Proof — Optimization & Validation

As the **operator**,
I want to run the full optimization and validation pipeline end-to-end — from strategy + data through optimization, validation gauntlet, confidence scoring, to operator review — and verify the entire flow works as one continuous pipeline,
So that I know the optimization and validation machinery works correctly before building deployment on top of it.

**Acceptance Criteria:**

1. **Given** Epic 3's E2E proof has established a working backtest pipeline with reference dataset, reference strategy, and reference cost model
**When** the optimization and validation proof is executed
**Then** the optimization orchestrator initializes with research-configured algorithm portfolio and dispatches batch evaluations through the Epic 3 Rust bridge (D1, D3)

2. **And** optimization runs to completion (or configurable evaluation budget) producing ranked candidates with per-fold CV-objective scores

3. **And** the V1 simple candidate promotion path selects top-N candidates for validation (MVP scope — no advanced clustering)

4. **And** each selected candidate runs through the full validation gauntlet: walk-forward → CPCV → parameter perturbation → Monte Carlo → regime analysis (FR29-FR33)

5. **And** confidence scores are computed with RED/YELLOW/GREEN ratings and detailed breakdowns (FR34)

6. **And** evidence packs are assembled with two-pass format: 60-second summary card + full review (D11, FR39)

7. **And** the operator reviews results via `/pipeline` → "Review Optimization Results" and advances the pipeline via accept/reject/refine decisions (FR39, D9)

8. **And** `/pipeline` → "Status" shows the correct stage progression through optimization and validation stages with timestamps (FR40)

9. **And** the full pipeline is deterministic: same inputs (strategy spec, dataset, cost model, config) produce identical optimization results, validation scores, and confidence ratings (FR18, FR61)

10. **And** pipeline resume works: if interrupted at any stage (optimization, validation, scoring), it resumes from the last checkpoint (FR42, NFR5)

11. **And** structured logs cover the full flow across Python orchestration and Rust evaluation runtimes (D6)

12. **And** all artifacts are persisted with manifests linking: dataset hash, strategy spec version, cost model version, config hash, optimizer config, validation config (FR58, FR59)

13. **And** this optimization and validation result is saved for use in subsequent epic pipeline proofs (Epic 6 deployment)

- **E2E Proof:** Full pipeline: reference data → reference strategy → reference cost model → optimize (portfolio of CMA-ES + DE instances, CV-inside-objective) → V1 candidate selection → validation gauntlet (walk-forward + CPCV + perturbation + Monte Carlo + regime) → confidence score (RED/YELLOW/GREEN) → evidence pack → operator review → pipeline advances. Entire flow from Epic 1 data through gauntlet works as one continuous pipeline.
- **FRs covered:** FR23-FR25 (optimization), FR29-FR37 (validation), FR34 (confidence), FR38-FR42 (pipeline operations)
- **Dependencies:** Stories 5.3-5.5 (all optimization and validation components), Epic 3 E2E proof (baseline pipeline)
