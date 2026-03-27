---
stepsCompleted:
  - 1
  - 2
  - 3
  - 4
  - 5
  - 6
  - 7
  - 8
inputDocuments:
  - prd.md
  - prd-validation-report.md
  - hardware-optimization-playbook.md
workflowType: 'architecture'
lastStep: 8
status: 'complete'
completedAt: '2026-03-13'
revisedAt: '2026-03-18'
revisionNote: 'Research integration update — incorporated findings from Stories 3-1/3-2, Research Briefs 3A/3B/3C, CV-objective research, and staged-vs-joint optimization research. Key changes: D1 adds fold-aware batch evaluation + library-with-subprocess-wrapper + windowed evaluation; D3 optimization is opaque to state machine; D10 expanded minimum constructs (sub-bar SL/TP, stale exit, partial close, breakeven, max bars, SignalCausality, conditional params); D11 adds deterministic-first AI architecture + two-pass evidence packs + DSR/PBO validation guidance; D14 adds phased indicator migration (Python Phase 1, Rust Phase 2); Phase 0 research table updated with 9 resolved topics; optimizer crate clarified as evaluation engine (search algorithm runs in Python). Previous revision: Multi-agent review addressed 12 gaps (2026-03-13).'
decisions: 15
project_name: 'Forex Pipeline'
user_name: 'ROG'
date: '2026-03-13'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**

87 FRs across 14 subsystems defining a 13-stage pipeline from data acquisition through live monitoring. The pipeline decomposes into three architectural tiers:

| Tier | Subsystems | FRs | Architectural Role |
|---|---|---|---|
| **Compute** | Backtesting, Optimization, Validation Gauntlet, Execution Cost Modeling | FR14-FR37 | CPU/memory-intensive batch processing — hot path for P-core affinity, SIMD, mmap |
| **Orchestration** | Data Pipeline, Strategy Definition, Pipeline Workflow, Risk Management, Reconciliation, Artifact Management | FR1-FR13, FR38-FR42, FR43-FR47, FR52-FR54, FR58-FR61 | Pipeline control, artifact flow, operator gates, deterministic behavior |
| **Interface** | Dashboard (MVP + Growth), Live Monitoring, Practice/Live Deployment | FR48-FR51, FR55-FR57, FR62-FR68 | Operator visibility, MT5 execution gateway, visualization |

MVP scope (FR1-FR68) delivers one strategy on one pair through the full pipeline. Growth (FR69-FR82) adds iteration, analytics, and lifecycle management. Vision (FR83-FR87) adds portfolio operations.

**Non-Functional Requirements:**

21 NFRs organized by architectural impact:

- **Performance (NFR1-NFR9):** Max hardware utilization (80%+ CPU sustained), deterministic memory budgeting (pre-allocate at startup, no dynamic allocation on hot path), bounded worker pools, streaming results, incremental checkpointing. The optimization methodology itself is a Phase 0 research deliverable — architecture must accommodate whatever approach research selects.
- **Reliability (NFR10-NFR15):** Crash prevention is the highest-priority NFR. Throttle before OOM, never terminate. Crash-safe write semantics on all artifacts. VPS auto-restart with full recovery sequence. Heartbeat monitoring with context-dependent intervals.
- **Security (NFR16-NFR18):** No plaintext credentials. VPS not exposed publicly. Kill switch operates independently of main application health.
- **Integration (NFR19-NFR21):** MT5 reconnection with exponential backoff. Graceful degradation on data source failure. Configurable timeouts on all external calls.

**Scale & Complexity:**

- Primary domain: Desktop/CLI data pipeline with live trading integration
- Complexity level: High
- Estimated architectural components: 8-10 major subsystems with defined interfaces

### Technical Constraints & Dependencies

| Constraint | Source | Architectural Impact |
|---|---|---|
| **Multi-runtime monolith** | Brownfield (Python + Rust + Node) | Must define clean inter-process boundaries; cannot assume single-runtime |
| **MT5 execution model** | Domain constraint | Backtester fidelity bounded by MT5 capabilities — order types, fills, sessions |
| **Wrap-and-extend default** | PRD MVP strategy | Architecture must support incremental replacement of baseline components |
| **Phase 0 research gates** | PRD methodology | Component interfaces must be stable even when implementations change post-research |
| **Hardware-specific optimization** | Playbook + NFR1 | P-core/E-core workload split, mmap data access, SoA layouts, SIMD kernels — Rust compute layer |
| **Dual environment** | PRD infrastructure model | Pipeline logic environment-agnostic; execution layer VPS-only; same MT5 account visible from both |
| **Parquet archival + Arrow IPC active** | Playbook data pipeline | Two-format data strategy — cold storage vs hot compute access |
| **Deterministic memory budgeting** | NFR4 (revised) | Pre-allocate at startup from available memory minus OS reserve (2-4GB). No dynamic heap allocation during compute hot paths. Crash prevention through predictable allocation, not arbitrary percentage ceilings |
| **Single operator** | PRD user role | No multi-tenancy, no auth complexity — but operator visibility at every gate is mandatory |

### Cross-Cutting Concerns Identified

| Concern | Affected Components | Architectural Implication |
|---|---|---|
| **Deterministic reproducibility** | All compute stages | Same inputs → same outputs. Configuration explicit. No implicit drift. Enforced architecturally, not by convention |
| **Artifact versioning & persistence** | All 13 pipeline stages | Standardized artifact schema, versioned storage, crash-safe writes. Every stage emits, every next stage consumes |
| **Resource management** | Backtesting, Optimization, Validation | Deterministic memory budgeting: pre-allocate pools at startup, mmap for data (OS-managed pages), stream results to disk. Crash prevention via predictable allocation — if a workload can't fit the budget, reduce batch size before starting, not mid-run |
| **Session-awareness** | Cost modeling, Backtesting, Analytics, Execution | London/NY/Asian/overlap as first-class dimension in cost model, analysis, and regime detection |
| **Crash safety** | All artifact-producing stages | Write-ahead patterns, checkpoint/resume, partial never overwrites complete |
| **Operator gate pattern** | Pipeline workflow, all stage transitions | Evidence pack → operator review → accept/reject/refine at every gate. Consistent UX pattern |
| **Configuration parity** | Local + VPS environments | Identical pipeline behavior, diverging only at execution layer |

### Data Volume Modeling

Concrete numbers for architectural sizing. Based on Dukascopy M1 bid+ask data for a single pair.

**Raw Data Volumes:**

| Dataset | Records | Arrow IPC Size (mmap) | Parquet Size | Notes |
|---|---|---|---|---|
| 1 year EURUSD M1 bid+ask | ~525,600 bars | ~40 MB | ~4 MB | 6 float64 columns (O/H/L/C/bid/ask) + timestamp |
| 10 years EURUSD M1 | ~5.26M bars | ~400 MB | ~40 MB | Primary backtest dataset |
| 10 years, 7 pairs M1 | ~36.8M bars | ~2.8 GB | ~280 MB | Growth phase multi-pair |

**Compute Output Volumes (per optimization run):**

| Artifact | Sizing Basis | Estimated Size | Format |
|---|---|---|---|
| Single backtest result | ~500 trades × 20 fields | ~80 KB Arrow IPC | Arrow IPC |
| Equity curve | ~5.26M data points × 3 fields | ~125 MB Arrow IPC | Arrow IPC |
| Optimization candidates | 10,000 candidates × 30 fields | ~2.4 MB Arrow IPC | Arrow IPC |
| Full optimization run (10K backtests) | 10K × trade logs + equity curves | ~800 MB Arrow IPC total | Arrow IPC |
| Walk-forward validation (8 windows) | 8 × backtest outputs | ~100 MB Arrow IPC | Arrow IPC |

**SQLite Ingest & Query Performance:**

| Operation | Volume | Expected Performance | Notes |
|---|---|---|---|
| Ingest 10K backtest trade logs | ~5M trade records | ~30 seconds (WAL mode, batch insert) | Python sqlite3, 1000-row batches |
| Query trades by strategy+session | Indexed scan | <100ms for typical queries | Indexes on strategy_id, session, entry_time |
| Aggregate analytics across 5M trades | Full table scan with aggregation | ~2-5 seconds | Acceptable for dashboard API with caching |
| Total SQLite DB size (1 optimization) | 5M trades + indexes | ~500 MB | Single file, WAL mode |

**Disk Budget Per Full Pipeline Run (single strategy, single pair):**

| Stage | Size | Cumulative |
|---|---|---|
| Market data (Arrow IPC) | 400 MB | 400 MB |
| Backtest results | 800 MB | 1.2 GB |
| SQLite (trade-level) | 500 MB | 1.7 GB |
| Validation outputs | 100 MB | 1.8 GB |
| Manifests, configs, logs | ~10 MB | ~1.8 GB |
| Parquet archival (compressed) | ~100 MB | ~1.9 GB |

**Total: ~2 GB per full pipeline run.** With 64 GB RAM and a typical SSD, this is well within capacity. Growth phase with 7 pairs × 5 strategies = ~70 GB disk, manageable with periodic archival.

**Memory Budget During Optimization (Peak):**

| Component | Allocation | Notes |
|---|---|---|
| Market data (mmap'd Arrow IPC) | OS-managed, ~400 MB resident | Not counted against heap budget |
| Rayon thread stacks (16 P-cores) | 16 × 8 MB = 128 MB | Pre-allocated |
| Per-thread trade buffers (pre-allocated) | 16 × 50 MB = 800 MB | SmallVec / fixed arrays |
| Equity curve accumulator (streaming) | ~125 MB per active backtest | Streamed to disk, not held |
| Arrow IPC result writer buffers | ~200 MB | Batch flush to disk |
| OS + Python orchestrator reserve | 4 GB | Conservative |
| **Total heap budget** | **~5.5 GB active** | **Well under 64 GB** |

The mmap'd market data is managed by the OS page cache and doesn't compete with heap allocations. The real constraint is the number of concurrent backtest evaluations holding trade buffers — 16 concurrent (one per P-core) × 50 MB each is the bottleneck, and it fits comfortably.

### Session-Awareness Architecture

Sessions are a first-class architectural dimension affecting cost modeling, backtesting, analytics, and strategy conditions. This cross-cutting concern requires consistent representation across all three runtimes.

**Session Definitions (in config):**

```toml
# config/base.toml — session schedule
[sessions]
timezone = "UTC"

[sessions.asian]
start = "00:00"
end = "08:00"
label = "Asian"

[sessions.london]
start = "08:00"
end = "16:00"
label = "London"

[sessions.new_york]
start = "13:00"
end = "21:00"
label = "New York"

[sessions.london_ny_overlap]
start = "13:00"
end = "16:00"
label = "London/NY Overlap"

[sessions.off_hours]
start = "21:00"
end = "00:00"
label = "Off Hours"
```

**How sessions flow through the architecture:**

| Component | Session Usage | Implementation |
|---|---|---|
| **Market data (Arrow IPC)** | Session label as a computed column during data pipeline stage | `data_pipeline/arrow_converter.py` stamps each M1 bar with its session(s) based on config schedule |
| **Cost model (Rust)** | Session-aware spread/slippage lookup during per-trade simulation | `cost_model/spread_model.rs` loads session cost profiles from cost model artifact; `backtester/trade_simulator.rs` passes session label to cost model on each fill |
| **Backtester (Rust)** | Session filter as a strategy condition | Strategy specification can include session filters in `entry_rules[].filters[]`; evaluator checks bar's session column |
| **Analytics (Python)** | Session as a grouping dimension for trade-level analysis | `analysis/narrative.py` and API routes group by session column in SQLite |
| **Dashboard** | Session breakdown in trade distribution charts | REST API returns session-grouped aggregates; dashboard renders per-session performance |
| **Strategy specification** | Session as a representable filter type | `"filter": {"type": "session", "include": ["london", "london_ny_overlap"]}` |

**Data flow:**
```
config/base.toml (session schedule)
    │
    ├──► data_pipeline/arrow_converter.py
    │    stamps session label column on every M1 bar in Arrow IPC
    │
    ├──► cost_model artifact (JSON/TOML)
    │    session → {mean_spread, std_spread, mean_slippage, std_slippage}
    │
    ├──► Rust backtester reads session column from Arrow IPC
    │    ├── applies session filters from strategy spec
    │    └── passes session to cost model for per-trade costs
    │
    ├──► SQLite trade records include session column
    │    └── analytics queries GROUP BY session
    │
    └──► Dashboard renders session breakdown charts
```

**Contracts definition (contracts/session_schema.toml):**
```toml
[session_column]
name = "session"
type = "utf8"
nullable = false
values = ["asian", "london", "new_york", "london_ny_overlap", "off_hours"]
description = "Session label computed from bar timestamp and config schedule"
```

### Data Quality Gate Specifications

The data pipeline (FR1-FR8) is the first gate. Quality issues here propagate to every downstream stage.

**Quality Checks (FR2):**

| Check | Method | Severity | Action |
|---|---|---|---|
| **Gap detection** | Expected bar count vs actual per hour; flag gaps > 5 consecutive M1 bars. During low-activity sessions (Asian, off-hours), consider raising threshold to 10 bars if false positives occur for less liquid pairs. | WARNING if < 10 gaps/year, ERROR if > 50 gaps/year or any gap > 30 min | Quarantine gap periods, interpolation NOT allowed |
| **Price integrity** | Bid > 0, Ask > Bid, spread within 10× median for that session | ERROR on any negative/zero/inverted price | Reject entire download batch |
| **OHLC violation** | high < low, high < max(open, close), low > min(open, close) | ERROR | Quarantine bar |
| **Extreme range** | (high - low) > 50× rolling median range for M1 (20× for M5, 10× for higher TFs) | WARNING | Log, include in quality report. Do NOT quarantine — may be real volatility events (flash crashes, news spikes) |
| **Timezone alignment** | Verify all timestamps are UTC, no DST artifacts, monotonically increasing | ERROR on any non-UTC or non-monotonic timestamp | Reject and re-download |
| **Stale quotes** | Flag periods where bid=ask or spread=0 for > 5 consecutive bars | WARNING | Quarantine period, flag in quality report |
| **Completeness** | Weekend gaps expected (Fri 22:00 - Sun 22:00 UTC); flag unexpected missing days | ERROR on missing weekday data | Re-download attempt, then quarantine |

**Data Quality Score (FR3):**

```
quality_score = 1.0 - (gap_penalty + integrity_penalty + staleness_penalty)

gap_penalty     = min(1.0, total_gap_minutes / total_expected_minutes × 10)
integrity_penalty = min(1.0, bad_price_bars / total_bars × 100)
staleness_penalty = min(1.0, stale_bars / total_bars × 50)
```

Score ranges: **GREEN** (≥ 0.95) — proceed. **YELLOW** (0.80-0.95) — operator review with quality report. **RED** (< 0.80) — blocked, re-download or manual intervention.

**Quarantine Behavior (FR4):**
- Quarantined periods are marked in the Arrow IPC with a `quarantined: bool` column
- Backtester skips quarantined bars (no signals generated during quarantined periods)
- Quality report artifact lists all quarantined periods with reasons
- Operator is notified via pipeline status (visible in `/pipeline-status` skill and dashboard)

**Consistent Data Sourcing (FR8):**
- Every dataset is identified by `{pair}_{start_date}_{end_date}_{source}_{download_hash}`
- Re-runs against the same date range MUST use the identical Arrow IPC file (same hash)
- New downloads create new versioned artifacts, never overwrite existing

## Technology Foundation

_Brownfield project — technology stack established by baseline, not selected from starter templates._

### Locked-In Technology Decisions

| Domain | Technology | Source |
|---|---|---|
| **Compute hot path** | Rust | Baseline + Hardware Playbook (SIMD, mmap, P-core affinity, SoA layouts) |
| **Orchestration / pipeline control** | Python | Baseline (existing modules, MT5 integration, data pipeline) |
| **Dashboard** | Web/browser-based (Node ecosystem) | PRD + Baseline (existing dashboard stack) |
| **Data storage — archival** | Parquet | Hardware Playbook (columnar, compressed, rich metadata) |
| **Data storage — active compute** | Arrow IPC (mmap'd) | Hardware Playbook (zero-copy, O(1) random access) |
| **Data source** | Dukascopy M1 bid+ask via `dukascopy-python` library (v4.0.1, MIT, REST API). Tick data also supported via same library (`INTERVAL_TICK`). | PRD constraint + Phase 0 research (Story 1.1/1.2) |
| **Execution gateway** | MetaTrader 5 | PRD hard constraint |
| **Deployment** | Git pull on VPS, manual verification | PRD |
| **OS** | Windows 11 (local laptop + VPS) | PRD infrastructure model |

### Phase 0 Research-Dependent Decisions

These technology choices are explicitly deferred to Phase 0 research. The architecture defines stable interfaces so that research outcomes change implementations, not boundaries.

| Decision | Options Space | Interface Stability Requirement |
|---|---|---|
| **Dashboard framework** | Existing Node stack vs alternatives | Must serve chart-led views (equity curves, trade distributions, pipeline status) within 3s (NFR6) |
| **Optimization methodology** | Population-based (CMA-ES, DE), Bayesian (TPE), hybrid — algorithm is pluggable behind batch interface. CV-inside-objective research complete (see Research Update 1). Staged vs joint parameter optimization research complete. Algorithm selection and fold design pending. | Must accept parameter space + strategy via batch interface (ask N candidates → evaluate → tell scores), emit ranked candidates with artifacts. Must support fold-aware evaluation (per-fold scores, not just aggregated). |
| **Strategy definition format** | **RESOLVED (Story 2-2):** TOML specification format | Versioned, reproducible. Schema in `contracts/strategy_specification.toml`. Implemented in `strategy_engine` crate. |
| **Python-Rust IPC** | **RESOLVED (Story 3-2):** Subprocess + Arrow IPC | Batch evaluation dispatch with ~20ms overhead per invocation. Full crash isolation (NFR10). Structured JSON errors on stderr. |
| **Testing framework** | Per-runtime: pytest, cargo test, web test runner | Must support deterministic reproducibility verification |
| **Candidate selection pipeline** | Statistical filtering, clustering, multi-objective ranking | Must compress optimization output to principled forward-test set |
| **Validation gauntlet configuration** | Walk-forward window sizing, Monte Carlo params, confidence thresholds | Must emit per-test evidence with RED/YELLOW/GREEN scoring |

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**
1. System Topology / Process Model
2. Artifact Schema & Storage
3. Pipeline Orchestration Pattern
4. Error Handling Strategy

**Important Decisions (Shape Architecture):**
5. Dashboard-to-Backend Communication
6. Process Supervision on VPS
7. Configuration Management
8. Logging & Observability

**Deferred Decisions (Phase 0 Research):**
- Optimization methodology, dashboard framework, strategy definition format, Python-Rust IPC mechanism details, candidate selection pipeline, validation gauntlet configuration

### Decision 1: System Topology — Multi-Process with Arrow IPC

**Decision:** Three separate processes. Python orchestrates. Rust computes. Node visualizes. Arrow IPC files are the IPC mechanism for batch compute — no serialization, both runtimes mmap the same files.

**Rust runs in two modes:**

| Mode | Use Case | Lifecycle |
|---|---|---|
| **Batch binary** | Backtesting, optimization, validation | Spawned per job, Arrow IPC data exchange, exits when done |
| **Live daemon** | Real-time signal evaluation on VPS | Persistent process, lightweight message protocol, same strategy code as batch |

**Rationale:**
- Baseline is already multi-process — wrap-and-extend preserves this
- Phase 0 may change the Rust layer; separate binary behind a defined contract makes replacement trivial
- Process isolation is strictly better for NFR10 (crash prevention) — Rust crash doesn't take Python down
- Arrow IPC eliminates serialization overhead — no performance penalty for process separation
- Same Rust codebase for batch and live guarantees signal fidelity (FR19, FR52)

**Research Update 1 — Fold-Aware Batch Evaluation (Stories 3-1, 3-2, Research Briefs 3A-3C, CV-Objective Research):**

The Rust batch binary must support **fold-aware evaluation** as an infrastructure capability. This means:

- Accept fold boundary definitions (bar indices + embargo size) alongside parameter sets
- Compute indicators on the full dataset once per parameter set (shared computation)
- Evaluate trade simulation per-fold by slicing to fold boundaries
- Return **per-fold scores** in addition to any aggregated score
- The aggregation function (mean-λ·std, geometric mean, CVaR, etc.) is NOT the evaluator's concern — the Python orchestrator aggregates

This is an interface requirement driven by CV-inside-objective research, not a methodology decision. Whatever optimization algorithm is selected in Phase 0, it will need per-fold scores from the evaluator.

**Research Update 2 — Library-with-Subprocess-Wrapper Pattern (Research Brief 3A):**

The Rust backtester is structured as a **library crate** with a thin binary wrapper. All computation logic lives in the library; the binary handles CLI argument parsing, subprocess lifecycle, and Arrow IPC I/O. This preserves a zero-cost migration path to PyO3 in-process if a specific hot path ever needs it, without changing the library's API.

**Research Update 3 — Windowed Evaluation (Story 3-1):**

The Rust binary loads market data once per invocation and supports evaluating multiple parameter batches within a single process lifetime. This avoids re-loading 400MB mmap'd data per batch. The binary accepts `--window-start` and `--window-end` for windowed evaluation within a single data load.

**Affects:** All components. Defines the fundamental process architecture.

### Decision 2: Artifact Schema & Storage — Arrow IPC / SQLite / Parquet Hybrid

**Decision:** Three-format storage strategy, each format doing what it's best at.

| Layer | Format | Purpose |
|---|---|---|
| **Compute** | Arrow IPC | Rust batch binary writes results at full SIMD speed. mmap-friendly, bulk, immutable |
| **Query** | SQLite | After batch completes, Python ingests Arrow results into SQLite. Trade-level records indexed for analytics |
| **Archival** | Parquet | Long-term compressed cold storage. SQLite is rebuildable from Arrow/Parquet |

**Data flow:**
```
Rust batch → Arrow IPC (fast, bulk, canonical)
    ↓
Python ingest → SQLite (queryable, indexed, trade-level)
    ↓
Dashboard → reads SQLite via API (analytics, filtering, aggregation)
    ↓
Archival → Parquet (compressed, cold storage)
```

**Directory structure:**
```
artifacts/
  {strategy_id}/
    v001/
      manifest.json
      pipeline-state.json
      pipeline.db              # SQLite — trade-level, queryable
      data-pipeline/
        market-data.arrow
        quality-report.json
      backtest/
        results.arrow
        equity-curve.arrow
        trade-log.arrow
        narrative.json
      optimization/
        candidates.arrow
        clusters.json
      validation/
        walk-forward.arrow
        confidence-score.json
      reconciliation/
        signal-match.arrow
        divergence-report.json
  archive/                     # Parquet cold storage
```

**Rationale:**
- Millions of backtests × hundreds of trades = hundreds of millions of trade records
- Trade-level analytics (FR69 — session, regime, clustering) require SQL query capability
- Rust hot path never touches SQLite — no performance penalty during compute
- SQLite is embedded, zero-config, WAL-mode crash-safe, perfect for single operator
- SQLite is a derived index, not source of truth — rebuildable from Arrow/Parquet if corrupted

**Affects:** All pipeline stages, dashboard, analytics, archival.

### Decision 3: Pipeline Orchestration — Sequential State Machine Per Strategy

**Decision:** Each strategy gets an independent sequential state machine. Pipeline state is a JSON file per strategy. Growth phase adds a strategy registry for cross-strategy coordination.

**State machine properties:**
- Stages execute sequentially — inherent to the pipeline (can't optimize before backtesting)
- Parallelism lives within stages (Rayon inside Rust), not between stages
- Transitions are typed: `gated` (operator reviews evidence, decides) or `automatic` (cost model calibration, monitoring)
- Resume after crash: read state file → verify last completed artifact → continue from next stage
- Within-stage checkpointing (NFR5) handled by Rust batch binary writing incremental checkpoint files

**Research Update — Optimization is Opaque to the State Machine (CV-Objective & Staged-vs-Joint Research):**

The pipeline state machine treats optimization as a **single opaque state** (`OPTIMIZING`). It does NOT model optimization sub-stages (signal optimization, risk optimization, etc.) as state machine sub-states. The optimization engine manages its own internal state — whether it uses staged parameter grouping, joint optimization, CV folds, successive halving, or any other methodology is an internal concern behind a pluggable interface.

The state machine only tracks:
```
... → BACKTESTING → BACKTEST_COMPLETE (gated) → OPTIMIZING → OPTIMIZATION_COMPLETE (gated) → VALIDATING → ...

Growth-phase extension (Story 5.6): After SCORING_COMPLETE, the pipeline adds:
```
... → SCORING_COMPLETE (gated) → SELECTING → SELECTION_COMPLETE (gated — operator reviews selections) → [next stage]
```
SELECTING runs HDBSCAN clustering, multi-objective ranking (TOPSIS+CRITIC), and MAP-Elites diversity selection. Internal orchestration is opaque to the state machine (same pattern as OPTIMIZING).
```

The optimizer's internal state (current generation, fold progress, convergence metrics) is persisted in its own checkpoint files within the optimization artifact directory, not in `pipeline-state.json`. This separation ensures that:
1. Optimization methodology can change without touching the state machine
2. The state machine remains simple and testable
3. Optimizer checkpoint/resume is the optimizer's responsibility

The Python orchestrator's contract with the optimizer is:
- **Input:** Strategy spec (parameter space + conditionals), market data path, cost model path, fold boundaries, compute budget
- **Output:** Ranked candidates with per-fold scores, saved as Arrow IPC artifacts
- **Progress:** Callback for progress updates (trials completed, current best score)
- **Resume:** Optimizer can resume from its own checkpoints if interrupted

**Growth phase extension:**
```
Strategy Registry
  ├── strategy-A/pipeline-state.json  → stage: validation (gated)
  ├── strategy-B/pipeline-state.json  → stage: live-monitoring (automatic)
  └── shared/
        ├── risk-state.json          → aggregate exposure, position limits
        └── resource-budget.json     → compute resource allocation
```

**Multi-strategy resource management (Growth phase):**

When multiple strategies are in the pipeline concurrently:

| Scenario | Constraint | Resolution |
|---|---|---|
| Two strategies optimizing simultaneously | Memory budget: 64 GB total, 4 GB OS reserve | Orchestrator runs one optimization at a time. Strategies queue for the compute slot. This is simple and prevents memory contention — optimization is the only stage that approaches memory limits. |
| Multiple strategies in different stages | No memory contention — backtest/validation use < 5 GB each | Concurrent execution allowed. Orchestrator tracks active Rust processes and their estimated memory usage. |
| Multiple live strategies on VPS | CPU: live daemon is lightweight (single bar evaluation) | Single live daemon process evaluates all active strategies sequentially per bar. No parallelism needed — bar evaluation is microseconds. |
| Collective risk limits | FR45: aggregate exposure limits | `shared/risk-state.json` tracks total exposure across all live strategies. Position sizing checks aggregate before allowing new trades. |

The key insight: **optimization is the only memory-hungry stage**. All other stages fit comfortably in memory. The orchestrator simply serializes optimization runs and allows everything else to run concurrently.

**Rationale:**
- Pipeline is inherently sequential with operator gates — no DAG complexity needed
- DAG engines (Airflow) solve multi-team dependency problems this project doesn't have
- State is a single inspectable JSON file per strategy
- Multi-strategy support is additive — registry layer on top, not a rewrite
- Resource management is simple because only one stage (optimization) is memory-intensive

**Affects:** Pipeline workflow (FR38-FR42), artifact management (FR58-FR61), checkpoint/resume (NFR5).

### Decision 4: Dashboard-to-Backend — REST API + WebSocket

**Decision:** Python serves REST API for query-heavy views and WebSocket for live updates. Single process (FastAPI or similar).

| Channel | Purpose | Examples |
|---|---|---|
| **REST** | Historical data, analytics queries, artifact retrieval | Trade-level analytics, leaderboards, candidate comparison, equity curves |
| **WebSocket** | Live state, progress, real-time events | Optimization progress, live trade events, pipeline stage transitions, heartbeat status |

**Rationale:**
- Trade-level analytics across millions of records = SQL queries via API, not file reads from Node
- Decouples dashboard from storage layout — schema changes don't touch frontend
- WebSocket gives live optimization progress without polling
- Python already runs as orchestrator — FastAPI adds REST + WebSocket in one process
- NFR6 (3-second dashboard load) — API can pre-aggregate common views

**Affects:** Dashboard (FR62-FR68), live monitoring (FR55-FR57), operator workflow.

### Decision 5: Process Supervision — Windows Service via NSSM

**Decision:** NSSM (Non-Sucking Service Manager) wraps the Python orchestrator as a Windows service on VPS. Kill switch runs as a separate independent service.

**Properties:**
- Auto-restart on crash with configurable delay
- Starts at boot, before user login
- stdout/stderr to log files
- On startup/restart: NFR12 recovery sequence (reconnect MT5, scan positions, resume monitoring, alert operator)

**Kill switch independence (NFR18):**
- Separate NSSM service, separate process
- Functions even when main service is hung or crashed
- Can close all positions within 30 seconds independently

**Rationale:**
- NSSM is a single exe, no install, no dependencies, battle-tested
- Windows-native, no Node process manager dependency on VPS
- Two independent services ensures kill switch survives main process failure

**Affects:** VPS deployment (FR48-FR51), reliability (NFR12), security (NFR18).

### Decision 6: Logging & Observability — Structured JSON to Shared Directory

**Decision:** Each runtime writes structured JSON log lines to `logs/`, one file per runtime per day. Alerts fire directly from monitoring, not from log parsing.

**Unified log schema:**
```json
{
  "ts": "2026-03-13T14:22:00.123Z",
  "level": "INFO",
  "runtime": "rust|python|node",
  "component": "backtester|orchestrator|dashboard|...",
  "stage": "optimization",
  "strategy_id": "ma-cross-v3",
  "msg": "...",
  "ctx": {}
}
```

**Rationale:**
- Single operator — tailing three log files, not searching across hundreds of services
- Structured JSON is machine-parseable — dashboard can ingest for display (Growth phase)
- No write contention — each runtime owns its own file
- Alerting (NFR13) is a dedicated path, not log-dependent

**Affects:** All runtimes, heartbeat monitoring (NFR14), operator alerts (NFR13).

### Decision 7: Configuration — TOML with Schema Validation

**Decision:** Layered TOML configs validated at startup. Environment variables for secrets only.

**Structure:**
```
config/
  base.toml                # Shared pipeline config
  environments/
    local.toml             # execution_enabled = false
    vps.toml               # execution_enabled = true, heartbeat intervals
  strategies/
    ma-cross-v3.toml       # Strategy-specific, versioned
```

**Properties:**
- Schema validation at startup — fail loud before any stage runs
- Config hash embedded in every artifact manifest — reproducibility is verifiable
- TOML: no implicit type coercion, deterministic parsing, native in Rust (serde) and Python (tomllib)
- Secrets (NFR16) via environment variables only — never in config files, never in git

**Rationale:**
- Deterministic configuration is a core requirement (FR61) — TOML's unambiguous syntax prevents drift
- Config hash + data hash = reproducibility proof
- Layered overrides give environment parity (FR50) with minimal divergence
- Schema validation catches misconfiguration before a 3-hour optimization run, not during

**Affects:** All components, reproducibility (FR18, FR61), environment parity.

### Decision 8: Error Handling — Fail-Fast at Boundaries, Orchestrator Decides

**Decision:** Each runtime catches errors at component boundaries, wraps in structured error type, propagates to orchestrator. Orchestrator decides response based on error category.

**Error categories and responses:**

| Category | Example | Response |
|---|---|---|
| **Resource pressure** | Memory near budget, thermal throttle | Throttle — reduce concurrency, continue at lower throughput |
| **Data/logic error** | Corrupt data, strategy compile failure | Stop stage, checkpoint, alert operator |
| **External failure** | MT5 disconnect, Dukascopy timeout | Retry with backoff (NFR19), alert after threshold |

**Structured error type:**
```json
{
  "code": "RESOURCE_MEMORY_PRESSURE",
  "category": "resource",
  "severity": "warning",
  "recoverable": true,
  "action": "throttle",
  "component": "optimization",
  "runtime": "rust",
  "context": { "memory_used_gb": 59.2, "budget_gb": 60.0 },
  "msg": "Memory within 2GB of budget — reducing batch concurrency from 16 to 8"
}
```

**Runtime boundaries:**
- **Rust** panics caught at process boundary — exit with error code + structured error on stderr
- **Python** exceptions caught at stage boundaries — checkpoint + alert, never silent continuation
- **Node** errors non-critical — log, restart dashboard, pipeline unaffected

**Rationale:**
- NFR10 (crash prevention) requires distinguishing resource pressure (throttle) from logic errors (stop)
- Structured errors carry enough context for automated response
- Silent error swallowing is the worst failure mode for a fidelity-critical system

**Affects:** All components, crash prevention (NFR10), recovery (NFR11), alerting (NFR13).

### Decision 9: Operator Interface — Claude Code Skills Layer

**Decision:** Claude Code is the primary operator command interface. A set of Claude Code skills provides structured access to every pipeline operation. Skills invoke the REST API for data and pipeline control, and use Python analysis modules for narrative generation and decision support.

The PRD is explicit: Claude Code drives workflow; dashboard visualizes (FR38, Interaction Architecture section, line 294: "conversation-driven control — the system is operable through Claude Code dialogue").

**Skill categories:**

| Category | Skills | FRs Covered |
|---|---|---|
| **Strategy** | `/strategy-research`, `/strategy-review`, `/strategy-update` | FR9, FR10, FR11, FR12, FR73 |
| **Pipeline** | `/pipeline-status`, `/pipeline-run`, `/pipeline-advance`, `/pipeline-reject`, `/pipeline-resume` | FR38, FR39, FR40, FR41, FR42 |
| **Analysis** | `/backtest-review`, `/optimization-review`, `/validation-review` | FR16, FR17, FR25, FR34 |
| **Deployment** | `/deploy-practice`, `/deploy-live`, `/promote` | FR48, FR49, FR51 |
| **Monitoring** | `/live-status`, `/reconciliation-review`, `/kill-switch` | FR54, FR55, FR56, FR47 |
| **Lifecycle** | `/strategy-kill`, `/strategy-archive` | FR79, FR80 (Growth) |
| **Research** | `/research-topic`, `/research-status` | Phase 0 support |

**How skills work architecturally:**

```
Operator (ROG)
    │ natural dialogue
    ▼
Claude Code + Skills (.claude/skills/*.md)
    │ programmatic access
    ├──► REST API (data queries, pipeline control)
    ├──► Python analysis modules (narrative, anomaly detection)
    ├──► Pipeline state files (direct read for status)
    └──► Artifact files (direct read for evidence review)
    │
    ▼ presents to operator
Evidence pack + narrative + recommendation
```

**Skill implementation pattern:**
- Each skill is a Claude Code skill file (`.claude/skills/pipeline_*.md`, `.claude/skills/strategy_*.md`, etc.)
- Skills read pipeline state and artifacts directly from the filesystem
- Skills invoke REST API endpoints for mutations (advance stage, trigger run, deploy)
- Skills call Python analysis functions for narrative generation and anomaly detection
- Skills maintain consistency by always reading current state — no caching, no stale assumptions

**Consistency across sessions (FR61):**
- Skills always read `pipeline-state.json` for current status
- Skills always read the latest artifact manifest for context
- Skills reference the same TOML config with the same hash
- No session-specific state — everything is in files and database

**Rationale:**
- FR38 requires Claude Code dialogue control — skills are the structured way to provide this
- The operator never writes code — skills translate intent into system actions
- Skills are versionable, testable, and follow the same naming/pattern conventions as the rest of the system
- Dashboard remains valuable for visualization but skills are the action layer

**Affects:** All operator-facing FRs (FR9, FR38-42, FR47, FR51, FR54), operator workflow, Phase 0 research process.

### Decision 10: Strategy Execution Model — Specification-Driven with AI Generation

**Decision:** Strategies are structured specifications (not raw code). The Rust compute engine has a strategy evaluator that interprets specifications. AI generates specifications from operator dialogue. This is Phase 0 research-dependent but the interface contract is defined here.

**Three-layer model:**

| Layer | Responsibility | Runtime |
|---|---|---|
| **Intent capture** | Claude Code dialogue → structured specification draft | Claude Code skill |
| **Specification** | Versioned, deterministic, constrained strategy definition | JSON/TOML artifact |
| **Evaluation** | Interpret specification, apply to market data, produce signals | Rust engine |

**Strategy specification contract (interface — format is Phase 0):**

```
Strategy Specification
├── metadata (name, version, pair, timeframe, created_by, config_hash)
├── entry_rules[]
│   ├── condition (indicator, threshold, comparator)
│   ├── filters[] (session, regime, day_of_week)
│   └── confirmation[] (optional secondary conditions)
├── exit_rules[]
│   ├── stop_loss (type, value)
│   ├── take_profit (type, value)
│   └── trailing (type, params)
├── position_sizing (method, risk_percent, max_lots)
├── optimization_plan
│   ├── parameter_groups[] (which params, ranges, step sizes)
│   ├── group_dependencies[] (which groups interact)
│   └── objective_function (metric, direction)
└── cost_model_reference (version of cost model to use)
```

**AI generation flow (FR9 → FR10 → FR11):**

```
Operator: "Try a moving average crossover on EURUSD H1,
           only during London session, with a chandelier exit"
    │
    ▼
Claude Code /strategy-research skill
    │ generates structured specification
    ▼
Strategy specification artifact (versioned, saved)
    │
    ▼
Claude Code /strategy-review skill
    │ presents summary: "This strategy enters long when
    │ 20-period EMA crosses above 50-period EMA during
    │ London session hours, exits via chandelier exit at 3x ATR..."
    ▼
Operator confirms → specification locked → pipeline begins
```

**Why specification-driven, not code generation:**
- Specifications are deterministic and reviewable — no hidden behavior
- The Rust evaluator is tested once; specifications are just data
- Specifications are diffable — version changes are inspectable
- AI can reliably generate structured data; generating correct Rust code is fragile
- Phase 0 research may evolve the specification schema without changing the evaluator architecture

**Minimum representable constructs (interface requirement — format is Phase 0):**

The specification must be able to represent at least these constructs, derived from PRD journeys and FRs:

| Construct Category | Examples from PRD | Interface Requirement |
|---|---|---|
| **Trend indicators** | Moving average crossover (Journey 1) | Indicator type, period(s), price source (close/open/hl2), comparison operator |
| **Volatility indicators** | Chandelier exit (Journey 2), ATR-based stops | Indicator type, period, multiplier, trailing behavior |
| **Exit types** | Stop loss, take profit, trailing stop, chandelier exit (FR73) | Exit type enum, value (fixed pips / ATR multiple / percentage), trailing params |
| **Session filters** | "Add a session filter" (FR73) | Filter type = session, include/exclude list referencing config session labels |
| **Volatility filters** | "Add a volatility filter" (FR70) | Filter type = volatility, indicator (ATR/Bollinger width), threshold, direction |
| **Timeframe** | H1 (Journey 1), configurable | Base timeframe for signal evaluation |
| **Pair** | EURUSD (Journey 1), configurable | Instrument identifier |
| **Position sizing** | Risk percent, max lots | Method enum (fixed_risk / fixed_lots), risk_percent, max_lots |
| **Optimization parameters** | "Try wider stops" (FR73), parameter groupings (FR13) | Parameter name, range (min/max/step), group membership, group dependencies, conditional activation (e.g., trailing params only active when trailing_mode ≠ none) |

**Research Update — Additional Minimum Constructs (Strategy Evaluator Baseline Review, Story 2-1):**

The ClaudeBackTester baseline implements capabilities not yet in the minimum constructs table above. These must be representable in the strategy specification for V1:

| Construct | Source | Interface Requirement |
|---|---|---|
| **Sub-bar (M1) SL/TP resolution** | trade_full.rs, baseline | H1+ strategies evaluate SL/TP fills using M1 sub-bar data for realistic intra-bar fill detection. Spec must declare sub-bar timeframe requirement |
| **Stale exit** | trade_full.rs, baseline | Close trade after N bars if ATR drops below threshold (prevents capital lock-up). Exit type enum includes `stale` |
| **Partial close at profit target** | trade_full.rs, baseline | Close X% of position at TP1, let remainder run. Spec includes `partial_close: {enabled, percent, target_pips}` |
| **Breakeven with offset** | trade_full.rs, baseline | Move SL to entry ± offset after reaching activation level. Spec includes `breakeven: {enabled, activation_pips, offset_pips}` |
| **Max bars exit** | trade_full.rs, baseline | Close trade after N bars regardless of PnL. Spec includes `max_bars_exit: {enabled, bars}` |
| **SignalCausality enum** | baseline encoding.py | Each signal parameter tagged as `CAUSAL` (uses only past data) or `REQUIRES_TRAIN_FIT` (needs training period). Prevents look-ahead bias in validation |
| **Conditional parameter activation** | CV-objective research | Parameters define activation conditions (e.g., `trailing_step` only active when `trailing_mode != "none"`). Optimizer must respect conditionals to avoid wasting trials on irrelevant combinations |

**Strategy specification → Rust evaluator interface contract:**

```
Python (specification loader)
    │
    │ 1. Load strategy spec artifact (JSON/TOML)
    │ 2. Validate against contracts/strategy_specification.toml schema
    │ 3. Serialize to Rust-consumable format (Arrow IPC metadata or sidecar file)
    │
    ▼
Rust batch binary (backtester/optimizer/validator)
    │
    │ 1. Read strategy spec from sidecar file alongside market data
    │ 2. Build evaluator from spec (indicator instances, filter chain, exit rules)
    │ 3. For each bar: evaluate entry conditions → check filters → evaluate exit conditions
    │ 4. Record signals and trades in Arrow IPC output
    │
    ▼
Output: Arrow IPC results (trades, equity curve, signals)
```

The evaluator is a **rule engine**, not a general-purpose interpreter. The specification defines a finite set of composable primitives (indicators, filters, exits). The evaluator pre-builds the indicator computation graph at job start and evaluates it per-bar. This is deterministic by construction — same spec + same data = same signals.

**Modification flow (FR73 — operator directs changes):**

```
Operator: "try wider stops"
    │
    ▼
Claude Code /strategy-update skill
    │ reads current spec → identifies stop_loss parameter
    │ creates new spec version with modified stop_loss value
    │ saves as new versioned artifact (spec v002)
    │
    ▼
Operator reviews diff: "Stop loss changed from 1.5× ATR to 2.0× ATR"
    │ confirms → pipeline re-runs from backtest stage with v002
```

**Phase 0 research determines:**
- Exact specification format (JSON vs TOML vs custom DSL)
- How complex strategy logic maps to specification primitives (compound conditions, multi-timeframe)
- Whether novel strategy types need a code generation escape hatch
- How the Rust evaluator handles the specification (compiled rules vs interpreter vs hybrid)
- Which indicators are built-in vs extensible (plugin model for custom indicators)

**Affects:** Strategy definition (FR9-FR13), backtesting (FR14-FR19), optimization (FR23-FR24), the entire compute pipeline.

### Decision 11: AI Analysis Layer — Narrative Generation and Decision Support

**Decision:** A Python analysis module generates human-readable narratives, detects anomalies, compresses candidates, and assembles evidence packs. Claude Code skills invoke this module and present results to the operator.

**Components:**

| Component | Responsibility | FRs |
|---|---|---|
| **Narrative generator** | Produces summary text from backtest/optimization/validation results | FR16 |
| **Anomaly detector** | Flags suspicious results (low trades, perfect curves, sensitivity cliffs) | FR17, FR35 |
| **Candidate compressor** | Clusters similar parameter sets, presents distinct groups | FR26, FR28, Decision Support |
| **Evidence pack assembler** | Combines metrics, chart references, narratives, and recommendations into a single reviewable unit | FR39 |
| **Refinement suggester** | Analyzes multi-dimensional performance, proposes specific changes | FR70, FR71 (Growth) |

**How each component works:**

| Component | Input | Processing | Output |
|---|---|---|---|
| **Narrative generator** | SQLite trade data + Arrow IPC results + strategy spec | Computes summary statistics (win rate, profit factor, max DD, Sharpe). Structures into template-driven narrative sections: overview, strengths, weaknesses, session breakdown, risk assessment. Claude Code skills present the narrative. | Structured JSON: `{overview, metrics, strengths[], weaknesses[], session_breakdown{}, risk_assessment}` |
| **Anomaly detector** | SQLite trade data + strategy spec + historical baselines | Rule-based checks with configurable thresholds (see below). Runs automatically after every backtest/optimization/validation completion. | Structured JSON: `{anomalies[]: {type, severity, description, evidence, recommendation}}` |
| **Candidate compressor** | Arrow IPC optimization candidates (10K+) | HDBSCAN clustering with Gower distance on parameter space → identify distinct behavioral groups (handles mixed continuous/categorical params and irregular cluster shapes; automatic cluster count determination). Per-group: compute centroid, spread, representative candidate. Rank groups by robustness (cross-validation stability, not raw return). Growth-phase: full `selection/` subsystem with TOPSIS+CRITIC multi-objective ranking, MAP-Elites diversity archive, and equity curve quality metrics. | Structured JSON: `{clusters[]: {id, size, centroid_params, representative_candidate, robustness_score, metrics_summary}}` |
| **Evidence pack assembler** | Narrative + anomalies + metrics + chart references | Combines all analysis outputs into a single reviewable unit per pipeline gate. Includes: summary narrative, key metrics table, anomaly flags, chart URLs (dashboard deep links), recommendation (proceed/caution/reject). | Structured JSON: evidence pack artifact saved alongside stage artifacts |
| **Refinement suggester** (Growth) | Multi-dimensional analytics results (FR69) + strategy spec + historical iteration data | Analyzes performance by session, regime, day-of-week, entry timing, exit efficiency. Identifies specific weaknesses. Maps weaknesses to spec modifications. Estimates impact from historical data. Detects diminishing returns across cycles (FR71). | Structured JSON: `{suggestions[]: {change, predicted_impact, confidence}, diminishing_returns: bool, iterations_analyzed: int}` |

**Anomaly detection thresholds:**

| Anomaly Type | Threshold | Severity | FR |
|---|---|---|---|
| Low trade count | < 30 trades over backtest period | WARNING | FR17 |
| Zero trades | 0 trades in any 2-year window | ERROR | FR17 |
| Suspiciously perfect equity curve | Max drawdown < 1% with > 100 trades | ERROR | FR17 |
| Parameter sensitivity cliff | >50% performance change from ±1 step in any parameter | WARNING | FR17 |
| In-sample vs out-of-sample divergence | IS Sharpe > 2× OOS Sharpe | WARNING | FR35 |
| Extreme profit factor | Profit factor > 5.0 | WARNING | FR17 |
| Trade clustering | >50% of trades in single calendar month | WARNING | FR17 |
| Win rate extremes | Win rate > 90% or < 20% with > 50 trades | WARNING | FR17 |

**Proactive Monitoring & Insight Surfacing:**

The PRD requires the system to "actively diagnose performance and propose improvements" — not just respond when asked. The analysis layer runs proactively in these scenarios:

| Trigger | What Runs | How Operator is Notified | FR |
|---|---|---|---|
| **Backtest/optimization/validation completes** | Anomaly detector (automatic) | Anomalies included in evidence pack; flagged in `/pipeline-status` output and dashboard stage indicator | FR17, FR35 |
| **Live trade diverges from backtest prediction** | Reconciliation divergence check (automatic) | Alert via monitoring heartbeat; visible in `/live-status` skill output | FR56 |
| **Reconciliation completes** | Cost model drift check (automatic) | If observed costs consistently exceed model: log + flag in `/reconciliation-review` | FR22 |
| **Refinement cycle completes** (Growth) | Diminishing returns detector (automatic) | "Last N refinements produced < 0.5% improvement" message in evidence pack | FR71 |
| **Live strategy performance decay** (Growth) | Drawdown/regime shift detection (automatic, periodic) | Alert via `/live-status`; operator prompted with retirement recommendation | FR81 |
| **Pipeline stage blocked > configurable time** | Stale gate detector | Reminder in `/pipeline-status` that a gate awaits review | FR40 |

**Notification delivery:** All proactive insights are surfaced through two channels:
1. **Dashboard indicators** — stage badges show anomaly counts, live monitoring shows alert state
2. **Claude Code skill output** — when operator runs `/pipeline-status` or `/live-status`, proactive findings are included at the top of the response

There is no push notification mechanism in MVP (no email, no Slack). The system surfaces insights whenever the operator checks in. Growth phase may add push notifications via the stub `notifications/` module.

**How it integrates:**
- Analysis modules are Python functions exposed via REST API endpoints (`/api/v1/analysis/{strategy_id}/narrative`, `/api/v1/analysis/{strategy_id}/anomalies`, etc.)
- Claude Code skills call these endpoints and format results into readable operator narrative
- Analysis modules query SQLite for trade-level data and read Arrow IPC artifacts for raw results
- Anomaly detector runs automatically as a post-stage hook in the orchestrator (stage_runner.py calls anomaly detector after Rust binary completes)
- Evidence packs reference dashboard URLs for chart visualization
- All analysis outputs are saved as artifacts alongside stage outputs

**Rationale:**
- The PRD repeatedly describes "chart-first presentation with summary narrative" — narratives need a generator
- "Decision clarity" requires compression and recommendation, not raw data dumps
- Proactive anomaly detection prevents the operator from reviewing bad results without warning
- This layer bridges compute output and operator understanding
- Keeping it in Python (not in skills) makes it testable, versionable, and accessible via API

**Research Update — AI Architecture Principles (Research Brief 3C):**

1. **Deterministic computation first, LLM narration second.** All metrics, anomaly checks, clustering, and scoring are computed deterministically by Python code. The LLM (Claude Code skills) narrates and explains the deterministic results. No LLM is in the metric calculation path. This ensures reproducibility and auditability.

2. **Evidence packs support two-pass review.** First pass: 60-second triage card (key metrics table, anomaly flags, GREEN/YELLOW/RED verdict, one-paragraph summary). Second pass: 5-15 minute deep review (full trade analysis, session breakdown, parameter sensitivity, equity curve analysis). Both passes are generated from the same underlying data; the triage card is a filtered view.

3. **Structured outputs with mandatory internal evidence citations.** AI narratives must reference specific data from the evidence pack (e.g., "Sharpe ratio of 1.2 across London sessions" must cite the session breakdown table). Claims not supported by internal evidence are flagged.

**Research Update — Validation Methodology Guidance (Research Brief 3B, CV-Objective Research):**

Research Brief 3B identified critical overfitting detection requirements for the validation gauntlet:

- **Deflated Sharpe Ratio (DSR)** corrects for multiple testing — naive Sharpe threshold (t≥2) has 37% false positive rate at 20 trials, 90% at 100 trials. DSR is mandatory for any optimization producing >10 candidates.
- **Probability of Backtest Overfitting (PBO)** uses CPCV combinatorial splits to estimate true overfitting probability. PBO ≤ 0.40 recommended as gate.
- **Reproducibility is tiered**, not binary: Tier A (bit-identical outputs), Tier B (statistical reproducibility within tolerance), Tier C (regime-conditional). V1 targets Tier A for computation outputs.
- **Regime analysis V1:** Volatility-regime bucketing (high/medium/low ATR periods) as the simplest regime decomposition.

These inform the validation gauntlet configuration (Phase 0 item) but do not prescribe specific thresholds — those are set during Epic 5 research.

**Affects:** All operator review FRs (FR16, FR17, FR26, FR35, FR39), proactive alerting (FR56, FR71, FR81), decision support, Growth analytics (FR69-FR73).

### Decision 12: Reconciliation Data Flow — Augmented Re-Run with Signal Diff

**Decision:** Reconciliation works by augmenting historical data with live trade timestamps, re-running the exact backtest configuration, and performing candle-by-candle signal comparison. Cost model auto-updates from observed execution data.

**Data flow:**

```
Live MT5 trades (with timestamps)
    │
    ▼
Python reconciliation module
    ├── 1. Download latest market data covering live trade period
    ├── 2. Merge live trade timestamps into dataset as reference points
    ├── 3. Re-run backtest via Rust binary with SAME config + updated data
    ├── 4. Diff backtest signals vs live signals (candle-by-candle)
    ├── 5. For each divergence: attribute to category
    │      (spread, slippage, fill timing, data latency, signal miss)
    └── 6. Emit reconciliation artifact (Arrow IPC + summary JSON)
             │
             ▼
        Cost model update (FR22)
        ├── Extract actual spread/slippage from live fills
        ├── Compare to cost model assumptions
        └── Update cost model artifact with observed data
```

**Attribution categories:**

| Category | Description | Expected? |
|---|---|---|
| Spread widening | Live spread exceeded model assumption | Yes — normal |
| Slippage | Fill price differed from signal price | Yes — normal |
| Fill timing | Order filled on different candle than signal | Investigate |
| Data latency | Live data arrived late, signal delayed | Investigate |
| Signal mismatch | Backtest fires signal, live doesn't (or vice versa) | Critical — fidelity failure |

**Cost model feedback loop (FR22):**
- After reconciliation, actual spread/slippage data is extracted from live fills
- `cost_model_updater.py` compares observed values to current cost model
- If observed values consistently exceed assumptions, cost model artifact is re-versioned
- Next backtest run automatically picks up the updated cost model
- This is automatic background infrastructure — not an operator conversation

**Affects:** Reconciliation (FR52-FR54), cost model (FR20-FR22), backtesting fidelity, operator trust.

### Phase 0 Research Process

**Decision:** Phase 0 research is conducted through Claude Code skills using BMAD research workflows, with outputs stored as versioned artifacts in `_bmad-output/planning-artifacts/research/`.

**Research per component:**

| Component | Research Approach | Output Artifact |
|---|---|---|
| Strategy definition format | `/bmad-technical-research` | `research/strategy-definition-research.md` |
| Optimization methodology | `/bmad-technical-research` | `research/optimization-methodology-research.md` |
| Dashboard framework | `/bmad-technical-research` | `research/dashboard-framework-research.md` |
| Python-Rust IPC | `/bmad-technical-research` | `research/python-rust-ipc-research.md` |
| Candidate selection | `/bmad-domain-research` | `research/candidate-selection-research.md` |
| Validation gauntlet config | `/bmad-domain-research` | `research/validation-gauntlet-research.md` |
| Execution cost modeling | `/bmad-domain-research` | `research/execution-cost-research.md` |
| Reconciliation methodology | `/bmad-domain-research` | `research/reconciliation-methodology-research.md` |
| Overfitting detection | `/bmad-domain-research` | `research/overfitting-detection-research.md` |

**Research completed to date (as of 2026-03-18):**

| Topic | Status | Key Finding | Artifact |
|---|---|---|---|
| Python-Rust IPC | **RESOLVED** | Subprocess + Arrow IPC (D1 validated). ~20ms overhead, full crash isolation. | `research/3-2-ipc-determinism-research.md` |
| Strategy definition format | **RESOLVED** | TOML specification, implemented in `strategy_engine` crate | `research/strategy-definition-format-cost-modeling-research.md` |
| Backtest engine architecture | **RESOLVED** | 4 keep, 10 adapt, 2 replace, 1 build. Library-with-subprocess-wrapper pattern. | `research/backtest-engine-baseline-review.md` |
| Deterministic backtesting | **RESOLVED** | FMA flags, ChaCha8Rng, int64 timestamps, Rayon IndexedParallelIterator. Bit-identical reproducibility contract. | `research/3-2-ipc-determinism-research.md` |
| Competitive architecture analysis | **RESOLVED** | No existing system combines Rust vectorized + Python orchestrated WFO + subprocess isolation. System occupies unique position. | `research/briefs/3A/` |
| CV-inside-objective | **RESEARCH COMPLETE** | mean-λ·std aggregation is DRO-optimal (Duchi & Namkoong 2019). 1.3-2.5x cost with early stopping, not 5x. Emerging best practice, not yet standard. | `research/briefs/optimization/` |
| Staged vs joint optimization | **RESEARCH COMPLETE** | 5-stage parameter locking misses cross-group interactions. Signal+Time separation defensible; Risk/Management split is not. Conditional parameter handling reduces effective search space. Architecture must not prescribe staging — optimizer decides internally. | `research/briefs/optimization/` |
| Validation methodology (DSR/PBO) | **RESEARCH COMPLETE** | Naive Sharpe thresholds fail at scale. DSR and PBO are mandatory gates. Tiered reproducibility. | `research/briefs/3B/` |
| Results analysis & AI narratives | **RESEARCH COMPLETE** | Deterministic-first, evidence-constrained narration. Two-pass review design. | `research/briefs/3C/` |
| Optimization algorithm selection | **PENDING** | Population-based (CMA-ES/CMAwM), Bayesian (TPE), or hybrid. Must be batch-native for Rust evaluator integration. | — |
| Dashboard framework | **PENDING** | Existing Node stack vs alternatives | — |
| Execution cost modeling sources | **RESOLVED** | Session-aware cost model implemented in `cost_model` crate (Epic 2) | `research/data-quality-acquisition-research.md` |

**Research → Implementation gate:**
1. Research artifact produced and saved
2. Operator reviews findings and methodology recommendation
3. Operator accepts/rejects/refines
4. Accepted methodology becomes a locked decision — updates the architecture document
5. Implementation proceeds from the locked decision

**Rationale:**
- PRD line 378: "Operator-directed AI research + dedicated deep research where needed"
- BMAD already has research workflow skills — use them
- Research outputs as artifacts maintain the audit trail principle
- The gate prevents implementation from starting before methodology is validated

**Affects:** All Phase 0 deferred decisions, implementation sequencing, methodology quality.

### Decision 13: Cost Model Crate — Library Consumed by Backtester

**Decision:** The cost model is a Rust library crate (`crates/cost_model/`), not a separate binary. The backtester crate depends on it directly. A thin CLI binary wraps the library for standalone cost model calibration.

**Rationale:**
- FR21 requires session-aware spread/slippage applied **per trade during backtesting** — this is inner-loop, not a separate stage
- A process boundary in the per-trade hot path would destroy performance (subprocess call per trade is absurd)
- The cost model artifact (session → spread/slippage profile) is loaded once at job start and queried per fill
- Standalone calibration (building the cost model artifact from market data or live fills) is a separate offline operation that uses the same library via a thin binary

**Cargo dependency:**
```
backtester → cost_model (lib dependency)
optimizer  → backtester (lib dependency, reuses backtest engine)
validator  → backtester (lib dependency, reuses backtest engine)
```

**Cost model artifact format:**
```json
{
  "pair": "EURUSD",
  "version": "v003",
  "source": "research+live_calibration",
  "calibrated_at": "2026-03-13T14:00:00Z",
  "sessions": {
    "asian":             { "mean_spread_pips": 1.2, "std_spread": 0.3, "mean_slippage_pips": 0.1, "std_slippage": 0.05 },
    "london":            { "mean_spread_pips": 0.8, "std_spread": 0.2, "mean_slippage_pips": 0.05, "std_slippage": 0.03 },
    "new_york":          { "mean_spread_pips": 0.9, "std_spread": 0.25, "mean_slippage_pips": 0.06, "std_slippage": 0.03 },
    "london_ny_overlap": { "mean_spread_pips": 0.6, "std_spread": 0.15, "mean_slippage_pips": 0.03, "std_slippage": 0.02 },
    "off_hours":         { "mean_spread_pips": 2.0, "std_spread": 0.8, "mean_slippage_pips": 0.2, "std_slippage": 0.1 }
  }
}
```

**Affects:** Backtester (FR14, FR21), cost model (FR20-FR22), reconciliation feedback (Decision 12), Rust crate dependency graph.

### Decision 14: Strategy Engine Shared Crate

**Decision:** A `strategy_engine` crate contains the core strategy evaluation logic — indicator computation, signal generation, filter chain, exit rule evaluation. Both `backtester` and `live_daemon` depend on this crate. Signal fidelity (FR19, FR52) is guaranteed by both runtimes executing identical code paths.

**Crate responsibilities:**

| Component | Location | Purpose |
|---|---|---|
| `strategy_engine/src/evaluator.rs` | Shared crate | Build evaluator from spec, evaluate per-bar, produce signals |
| `strategy_engine/src/indicators.rs` | Shared crate | Indicator computation (MA, ATR, Bollinger, etc.) |
| `strategy_engine/src/filters.rs` | Shared crate | Session filter, volatility filter, day-of-week filter |
| `strategy_engine/src/exits.rs` | Shared crate | Stop loss, take profit, trailing stop, chandelier exit |
| `backtester/src/engine.rs` | Backtester crate | Batch loop: iterate bars, call evaluator, simulate fills, record trades |
| `live_daemon/src/signal_evaluator.rs` | Live daemon crate | Real-time loop: receive bar, call evaluator, emit signal to Python |

**Rationale:**
- Signal fidelity is THE core promise of the system — same code must evaluate signals in backtest and live
- Without a shared crate, the backtester and live daemon implementations would drift
- The shared crate is pure computation — no I/O, no state management, easily testable
- Backtester adds batch-specific concerns (trade simulation, equity tracking); live daemon adds real-time concerns (message handling, state management)

**Research Update — Phased Indicator Migration (Strategy Evaluator Baseline Review, Story 2-1/3-1):**

The baseline review revealed a structural mismatch: D14 assumes indicators, signals, filters, and exits are all Rust modules in `strategy_engine`. In reality, ALL 18 indicators are Python (`strategies/indicators.py`, 493 lines). Rust only contains trade simulation and metrics.

**Phase 1 (Epic 3 — MVP):** Indicators remain in Python. Python pre-computes all indicators on the full dataset, writes signal arrays to Arrow IPC, passes to Rust binary. Rust handles trade simulation, metrics, and per-fold scoring. This works because indicators are computed ONCE per pipeline run (precompute-once, filter-many pattern) — they are NOT on the hot path.

**Phase 2 (Growth — Live Daemon):** Port indicator computation to Rust `strategy_engine/src/indicators.rs`. Required for NFR7 (<500ms signal-to-order latency) where the live daemon must evaluate indicators in real-time. Python indicator code remains as test oracles for cross-runtime fidelity verification.

The `strategy_engine` crate's current contents (spec parsing, validation, indicator registry with 21 indicators) remain correct — it defines WHAT indicators exist. Phase 2 adds HOW to compute them in Rust.

**Affects:** Backtester (FR14-FR18), live daemon (FR55-FR57), signal fidelity (FR19, FR52), Rust workspace structure.

### Decision 15: Live Daemon Communication — Named Pipes on Windows

**Decision:** The Python orchestrator communicates with the Rust live daemon via Windows Named Pipes. The protocol is newline-delimited JSON messages.

**Why Named Pipes (not alternatives):**

| Option | Verdict | Reason |
|---|---|---|
| Unix sockets | Not available | Windows 11 does not support Unix domain sockets natively |
| TCP localhost | Rejected | Requires port management, firewall rules, unnecessary network stack overhead for local IPC |
| Named Pipes | **Selected** | Native Windows IPC, kernel-level, no network stack, bidirectional, supports both sync and async I/O |
| Shared memory | Rejected for control | Good for data (Arrow IPC already does this), but poor for request-response control messages |

**Protocol:**

```
Pipe name: \\.\pipe\forex_pipeline_live_daemon

Python → Rust messages:
  {"type": "new_bar", "data": {"pair": "EURUSD", "timestamp": "...", "o": 1.1234, ...}}
  {"type": "config_update", "data": {"strategy_spec_path": "..."}}
  {"type": "shutdown"}

Rust → Python messages:
  {"type": "signal", "data": {"direction": "long", "pair": "EURUSD", "timestamp": "...", "confidence": 0.85}}
  {"type": "heartbeat", "data": {"uptime_s": 3600, "last_bar_processed": "..."}}
  {"type": "error", "data": {"code": "STRATEGY_EVAL_FAILED", "msg": "..."}}
```

**Rust implementation:** `windows-named-pipes` crate or `tokio::net::windows::named_pipe` for async.

**Affects:** Live daemon (FR55-FR57), VPS deployment (FR48-FR51), Python-Rust IPC.

### Decision Impact Analysis

**Implementation Sequence:**
1. Configuration management (TOML + schema) — everything depends on config
2. Logging setup — needed before anything else runs
3. Contracts directory — Arrow schemas, SQLite DDL, API contracts, error codes, session schema, strategy spec schema
4. Artifact directory structure + SQLite schema — data foundation
5. `strategy_engine` shared crate — indicator/filter/exit evaluation core (Decision 14)
6. `cost_model` library crate — session-aware spread/slippage (Decision 13)
7. Pipeline state machine — orchestration skeleton
8. Rust backtester binary (depends on strategy_engine + cost_model) — compute foundation
9. Data pipeline with quality gates — market data acquisition and validation
10. Python API server (REST + WebSocket) — dashboard foundation
11. Analysis layer (narrative, anomaly detection, proactive monitoring, evidence packs) — operator understanding
12. Claude Code skills for operator workflow — primary interface
13. Optimization + validation binaries — extend compute pipeline
14. Reconciliation data flow with cost model feedback — fidelity loop
15. NSSM service setup on VPS — deployment foundation
16. Rust live daemon with Named Pipe protocol (Decision 15, depends on strategy_engine) — after batch binary is proven

**Cross-Component Dependencies:**
- Config hash flows into artifact manifests (D7 → D2)
- Error types are consumed by pipeline state machine (D8 → D3)
- SQLite is populated after Rust batch, queried by API (D2 → D1 → D4)
- NSSM supervises the orchestrator which hosts the API (D5 → D4)
- Structured logs are the diagnostic layer for error handling (D6 → D8)
- Claude Code skills invoke REST API and read artifacts (D9 → D4 → D2)
- Strategy specification feeds into strategy_engine evaluator (D10 → D14 → D1)
- Cost model is a lib dependency of backtester (D13 → backtester crate)
- Strategy engine is shared between backtester and live daemon (D14 → backtester + live daemon)
- Analysis layer queries SQLite and reads artifacts (D11 → D2)
- Anomaly detector runs as post-stage hook in orchestrator (D11 → D3)
- Reconciliation triggers backtest re-run and updates cost model (D12 → D1 → D2 → D13)
- Skills use analysis layer for evidence packs and narratives (D9 → D11)
- Live daemon communicates via Named Pipes (D15 → D14)
- Session-awareness flows from config through data pipeline to cost model to analytics (D7 → D13 → D11)

**Rust Workspace Dependency Graph:**

```
forex-pipeline/src/rust/ (Cargo workspace)
│
├── crates/common/           ← Arrow schemas, error types, config, logging, checkpoint
│       ▲
│       │ (all crates depend on common)
│       │
├── crates/strategy_engine/  ← Indicator computation, signal evaluation, filters, exits
│       │                       depends on: common
│       ▲
│       │
├── crates/cost_model/       ← Session-aware spread/slippage model (library crate)
│       │                       depends on: common
│       ▲
│       │
├── crates/backtester/       ← Batch backtest binary
│       │                       depends on: common, strategy_engine, cost_model
│       ▲
│       │
├── crates/optimizer/        ← Batch optimization binary (methodology pluggable — see Phase 0)
│       │                       depends on: common, backtester (lib), strategy_engine, cost_model
│       │                       NOTE: optimizer is a thin Rust binary that accepts batches
│       │                       of parameter sets and returns per-fold scores. The optimization
│       │                       ALGORITHM (CMA-ES, TPE, etc.) runs in Python and calls this
│       │                       binary via subprocess. The Rust side handles evaluation, not search.
│       ▲
│       │
├── crates/validator/        ← Batch validation binary
│       │                       depends on: common, backtester (lib), strategy_engine, cost_model
│       │
└── crates/live_daemon/      ← Persistent live signal daemon (VPS)
                                depends on: common, strategy_engine, cost_model
```

**Binary naming convention:** All binaries are prefixed with `forex_` for namespace clarity:
- `forex_backtester` — batch backtest binary
- `forex_optimizer` — batch optimization binary
- `forex_validator` — batch validation binary
- `forex_cost_calibrator` — thin CLI wrapping cost_model lib for standalone calibration
- `forex_live_daemon` — persistent live signal evaluation daemon

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**Critical Conflict Points Identified:** 7 boundary areas where AI agents could diverge — naming, data formats, API contracts, event protocols, file organization, error propagation, and test placement.

### Naming Patterns

**Cross-Boundary Rule:** `snake_case` is the universal convention at every runtime boundary. No exceptions.

| Boundary | Convention | Example |
|---|---|---|
| SQLite tables | plural, snake_case | `trades`, `backtest_results`, `equity_curves` |
| SQLite columns | snake_case | `strategy_id`, `entry_price`, `created_at` |
| SQLite indexes | `idx_{table}_{column}` | `idx_trades_strategy_id` |
| JSON fields (API + files) | snake_case | `"walk_forward_score": 0.82` |
| TOML config keys | snake_case | `heartbeat_interval_ms = 5000` |
| REST URL paths | kebab-case | `/api/v1/backtest-results` |
| REST query params | snake_case | `?strategy_id=ma-cross-v3&stage=validation` |
| WebSocket event names | dot.snake_case | `pipeline.stage_changed`, `optimization.progress_update` |
| File/directory names | snake_case | `walk_forward.arrow`, `cost_model/` |
| Artifact keys in manifests | snake_case | `"confidence_score"`, `"equity_curve"` |
| Strategy IDs | kebab-case | `ma-cross-v3`, `breakout-london-v1` |

**Per-Runtime Internal Code:**

| Runtime | Functions/Variables | Types/Classes | Constants |
|---|---|---|---|
| Python | `snake_case` | `PascalCase` | `UPPER_SNAKE_CASE` |
| Rust | `snake_case` | `PascalCase` | `UPPER_SNAKE_CASE` |
| Node/JS | `camelCase` | `PascalCase` | `UPPER_SNAKE_CASE` |

Node uses `camelCase` internally but the API client layer translates to/from `snake_case` at the boundary. One translation layer, one location.

### Structure Patterns

**Project Organization — By Runtime, Then By Component:**

```
forex-pipeline/
  src/
    python/                    # Orchestrator + API
      orchestrator/
        pipeline_state.py
        stage_runner.py
      api/
        routes/
        websocket/
        models/
      data_pipeline/
      mt5_integration/
      tests/                   # pytest convention — separate tests/ dir
    rust/                      # Compute engine
      src/
        backtester/
        optimizer/
        validator/
        live_daemon/
        common/                # Shared types, Arrow schema definitions
      tests/                   # Integration tests; unit tests co-located via #[cfg(test)]
    dashboard/                 # Node/browser
      src/
        components/
        pages/
        api_client/            # snake_case ↔ camelCase translation lives here
        stores/
      tests/                   # Co-located *.test.ts also acceptable
  config/
    base.toml
    environments/
    strategies/
  contracts/                   # Canonical schema definitions (Arrow, SQLite DDL, API)
  artifacts/                   # Runtime output — structure per Decision 2
  logs/
  scripts/                     # Build, deploy, utility scripts
```

**Test Placement:**
- **Python:** `tests/` directory mirroring source structure. `pytest` convention.
- **Rust:** Unit tests via `#[cfg(test)]` in source files. Integration tests in `tests/` directory.
- **Node:** Co-located `*.test.ts` files next to source. Integration tests in `tests/` directory.

**Shared Types Location:** Each runtime defines its own types but the canonical schema definitions (Arrow schemas, SQLite DDL, API contracts) live in a shared `contracts/` directory at the project root as `.toml` or `.json` schema files. This is the single source of truth — runtime-specific types are generated or manually aligned from these.

### Format Patterns

**API Response Envelope:**

Every REST response uses a consistent wrapper:

```json
{
  "data": { ... },
  "error": null,
  "meta": {
    "timestamp": "2026-03-13T14:22:00.123Z",
    "request_id": "abc-123"
  }
}
```

Error responses:
```json
{
  "data": null,
  "error": {
    "code": "STAGE_NOT_FOUND",
    "message": "No backtest results for strategy ma-cross-v3",
    "detail": {}
  },
  "meta": { ... }
}
```

**HTTP Status Code Usage:**
- `200` — success (GET, PUT)
- `201` — created (POST that creates)
- `400` — client error (bad params)
- `404` — not found
- `409` — conflict (pipeline stage in wrong state)
- `500` — server error

**Timestamp Formats:**

| Context | Format | Example |
|---|---|---|
| JSON / API / logs | ISO 8601 UTC | `"2026-03-13T14:22:00.123Z"` |
| Arrow IPC columns | int64 epoch microseconds | `1741875720123000` |
| SQLite columns | ISO 8601 text | `"2026-03-13T14:22:00.123Z"` |
| TOML config | ISO 8601 | `start_date = "2020-01-01"` |

Epoch micros in Arrow for compute performance. ISO 8601 everywhere humans or queries touch data.

**Null Handling:**
- JSON: explicit `null` — never omit fields, never use empty strings as null substitutes
- SQLite: `NULL` — nullable columns explicitly marked in DDL
- Arrow: nullable columns use Arrow's native null bitmap

### Communication Patterns

**WebSocket Event Protocol:**

```json
{
  "event": "pipeline.stage_changed",
  "timestamp": "2026-03-13T14:22:00.123Z",
  "data": {
    "strategy_id": "ma-cross-v3",
    "from_stage": "optimization",
    "to_stage": "validation",
    "transition_type": "gated"
  }
}
```

**Event Naming Convention:** `{domain}.{action_in_snake_case}`

| Domain | Events |
|---|---|
| `pipeline` | `stage_changed`, `state_updated`, `error_occurred` |
| `optimization` | `progress_update`, `batch_completed`, `candidate_found` |
| `backtest` | `progress_update`, `completed`, `checkpoint_saved` |
| `validation` | `test_completed`, `gauntlet_finished` |
| `monitoring` | `heartbeat`, `position_update`, `signal_fired` |
| `system` | `resource_warning`, `config_reloaded`, `service_started` |

**Rust-to-Python Error Propagation:**

Rust batch binary communicates via:
- Exit code `0` = success, non-zero = failure category
- On success: results in Arrow IPC files at agreed paths
- On failure: structured JSON error on stderr (per Decision 8 schema), partial results checkpointed to disk

Python never parses Rust stdout for data. stdout is for structured log lines only.

### Process Patterns

**Pipeline Stage Contract:**

Every pipeline stage implementation follows this contract:

```
Input:  config (TOML) + input artifacts (Arrow IPC / JSON)
Output: output artifacts (Arrow IPC / JSON) + updated pipeline-state.json
Side effects: log lines (structured JSON), checkpoint files (if long-running)
```

- Stages are stateless between runs — all state is in artifacts and pipeline-state.json
- No stage reads another stage's internal state — only its published artifacts
- Checkpoint files use `.partial` suffix until complete, then atomic rename

**Crash-Safe Write Pattern:**

All artifact writes across all runtimes follow:
1. Write to `{filename}.partial`
2. Flush / fsync
3. Atomic rename to `{filename}`

Never overwrite a complete artifact with a partial one. If `.partial` exists on startup, it's from a crash — delete it and re-run.

**Configuration Access Pattern:**

- Config is loaded once at process startup, validated against schema, and frozen
- No runtime config modification — restart to pick up changes
- Config hash computed at load time, embedded in all artifact manifests
- Each runtime loads TOML natively (Python: `tomllib`, Rust: `serde` + `toml`, Node: `@iarna/toml` or equivalent)

### Enforcement Guidelines

**All AI Agents MUST:**

1. Use `snake_case` at every cross-runtime boundary — no exceptions, no "just this once"
2. Follow the crash-safe write pattern for any file that persists state or results
3. Use the API response envelope for every REST endpoint — no bare responses
4. Include `strategy_id` and `stage` in every log line and event payload
5. Never read another stage's internal working files — only published artifacts
6. Validate config at startup — fail immediately with a clear message, not silently mid-run
7. Use the `contracts/` schema definitions as the source of truth for shared data types

**Anti-Patterns (Explicitly Forbidden):**

- Direct SQLite access from Rust — Rust writes Arrow, Python ingests to SQLite
- Passing data between runtimes via stdout parsing — use Arrow IPC files or the REST API
- Implicit config values — every config key must exist in `base.toml` with a default
- Swallowing errors silently — every error must propagate to the orchestrator or log
- Creating undocumented artifact files — every output must be declared in the stage contract

## Testing Strategy

### Testing Pyramid

| Layer | Scope | Framework | Approximate Ratio | Runs When |
|---|---|---|---|---|
| **Unit tests** | Single function/module in isolation | Rust: `#[cfg(test)]`, Python: `pytest`, Node: `vitest` | 70% of all tests | Every code change, pre-commit |
| **Integration tests** | Cross-module within a single runtime | Rust: `tests/` dir, Python: `tests/` dir, Node: `tests/` dir | 20% of all tests | Pre-merge, CI |
| **System tests** | Cross-runtime (Python spawns Rust binary, reads Arrow output) | Python `pytest` orchestrating subprocess calls | 10% of all tests | Pre-merge, manual before deploy |

No E2E browser tests in MVP — dashboard is visualization-only, tested via API integration tests.

### Deterministic Reproducibility Verification (FR18, FR61)

**The core invariant:** Same strategy specification + same dataset (identical Arrow IPC file) + same config (identical TOML hash) = identical output (bit-for-bit Arrow IPC results).

**How to verify:**

1. **Golden file tests (Rust unit tests):** Small deterministic test fixtures (10-100 bars) with known expected outputs. Strategy engine evaluator produces signals that are compared against golden files. Any change to evaluator logic that changes output breaks the golden file test — intentional changes update the golden file with review.

2. **Round-trip reproducibility tests (integration):** Run backtest → record output hash → run same backtest again → compare hashes. Must be identical. This catches non-determinism from floating-point ordering, thread scheduling, or implicit state.

3. **Config hash embedding:** Every artifact manifest includes the config hash and data hash used to produce it. Reproducibility is verifiable after the fact: re-run with the same hashes, compare output hashes.

4. **Cross-runtime contract tests:** Python's strategy spec loader serializes a spec → Rust reads it and produces signals → Python reads the signals and verifies against expected output. This tests the serialization boundary.

**Sources of non-determinism to guard against:**
- Floating-point accumulation order in parallel reductions (Rayon) — use deterministic reduction order or Kahan summation
- HashMap iteration order — use BTreeMap or sorted keys for any deterministic output
- Timestamp generation — test fixtures use fixed timestamps, never `now()`
- Random seeds in Monte Carlo — seed is stored in config, reproducible by definition

### Test Data Strategy

**Deterministic test fixtures live in `src/rust/tests/test_data/`:**

| Fixture | Contents | Purpose |
|---|---|---|
| `tiny_market_10bars.arrow` | 10 M1 bars with known OHLC values | Unit test: indicator computation, signal evaluation |
| `small_market_1000bars.arrow` | 1000 M1 bars from real Dukascopy data (fixed date range) | Integration test: full backtest cycle |
| `known_signals.json` | Expected signals for tiny_market with a reference strategy spec | Golden file comparison |
| `cost_model_test.json` | Fixed cost model artifact with known session spreads | Unit test: cost model application |

**Fixture generation:** A Python script (`scripts/generate_test_fixtures.py`) creates Arrow IPC fixtures from a fixed seed or a pinned Dukascopy date range. Fixtures are committed to git (small, deterministic). The script is re-runnable to verify fixtures haven't drifted.

### Python-Rust Bridge Testing

The bridge (`src/python/rust_bridge/`) is one of the hardest testing boundaries:

| Test Type | Approach | What It Verifies |
|---|---|---|
| **Unit (Python side)** | Mock the Rust binary subprocess call. Provide pre-built Arrow IPC output files as mock results. | Python ingester, error parser, result handling logic |
| **Unit (Rust side)** | Golden file tests in Rust `#[cfg(test)]` with tiny fixtures. | Backtest engine, strategy evaluator, Arrow output format |
| **Integration (bridge)** | Python test spawns the real Rust binary (debug build) with tiny test fixtures. Verifies: exit code, Arrow output files exist and parse correctly, structured error on stderr for error cases. | Subprocess lifecycle, Arrow IPC compatibility, error propagation |
| **Contract (schema)** | Python reads `contracts/arrow_schemas.toml`, Rust reads same file. Both validate that their Arrow schema definitions match. | Schema drift prevention across runtimes |

### CI/CD Approach

Single-operator project — no GitHub Actions CI in MVP. Instead:

**Pre-commit (local):**
- `cargo test` — all Rust unit + integration tests
- `pytest src/python/tests/` — all Python tests
- Config schema validation (`scripts/validate_config.py`)

**Pre-deploy (manual checklist before VPS git pull):**
- Full test suite passes locally
- `cargo build --release` succeeds
- Reproducibility spot-check: re-run a known backtest, verify hash match
- Config diff between local and VPS environments reviewed

**Growth phase may add:** GitHub Actions for automated testing on push, but the single-operator model means local testing is the primary gate.

### Contracts Directory Content

The `contracts/` directory is the single source of truth for cross-runtime type definitions. Each file defines schemas that all runtimes must conform to.

**`contracts/arrow_schemas.toml` — Arrow IPC field definitions per stage:**

```toml
[market_data]
columns = [
  { name = "timestamp", type = "int64", nullable = false, description = "Epoch microseconds UTC" },
  { name = "open", type = "float64", nullable = false },
  { name = "high", type = "float64", nullable = false },
  { name = "low", type = "float64", nullable = false },
  { name = "close", type = "float64", nullable = false },
  { name = "bid", type = "float64", nullable = false },
  { name = "ask", type = "float64", nullable = false },
  { name = "session", type = "utf8", nullable = false, values = ["asian", "london", "new_york", "london_ny_overlap", "off_hours"] },
  { name = "quarantined", type = "bool", nullable = false, default = false },
]

[backtest_trades]
columns = [
  { name = "trade_id", type = "int64", nullable = false },
  { name = "strategy_id", type = "utf8", nullable = false },
  { name = "direction", type = "utf8", nullable = false, values = ["long", "short"] },
  { name = "entry_time", type = "int64", nullable = false },
  { name = "exit_time", type = "int64", nullable = false },
  { name = "entry_price", type = "float64", nullable = false },
  { name = "exit_price", type = "float64", nullable = false },
  { name = "spread_cost_pips", type = "float64", nullable = false },
  { name = "slippage_cost_pips", type = "float64", nullable = false },
  { name = "pnl_pips", type = "float64", nullable = false },
  { name = "session", type = "utf8", nullable = false },
  { name = "lot_size", type = "float64", nullable = false },
]

[optimization_candidates]
columns = [
  { name = "candidate_id", type = "int64", nullable = false },
  { name = "params_json", type = "utf8", nullable = false, description = "JSON-encoded parameter set" },
  { name = "total_trades", type = "int64", nullable = false },
  { name = "profit_factor", type = "float64", nullable = false },
  { name = "sharpe_ratio", type = "float64", nullable = false },
  { name = "max_drawdown_pct", type = "float64", nullable = false },
  { name = "win_rate", type = "float64", nullable = false },
  { name = "net_pnl_pips", type = "float64", nullable = false },
]
```

**`contracts/sqlite_ddl.sql` — SQLite table definitions:**

```sql
CREATE TABLE IF NOT EXISTS trades (
    trade_id        INTEGER PRIMARY KEY,
    strategy_id     TEXT NOT NULL,
    backtest_run_id TEXT NOT NULL,
    direction       TEXT NOT NULL CHECK(direction IN ('long', 'short')),
    entry_time      TEXT NOT NULL,  -- ISO 8601
    exit_time       TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    exit_price      REAL NOT NULL,
    spread_cost     REAL NOT NULL,
    slippage_cost   REAL NOT NULL,
    pnl_pips        REAL NOT NULL,
    session         TEXT NOT NULL,
    lot_size        REAL NOT NULL,
    candidate_id    INTEGER,  -- NULL for single backtest, set for optimization
    FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id)
);

CREATE INDEX idx_trades_strategy_id ON trades(strategy_id);
CREATE INDEX idx_trades_session ON trades(session);
CREATE INDEX idx_trades_entry_time ON trades(entry_time);
CREATE INDEX idx_trades_candidate_id ON trades(candidate_id);

CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id          TEXT PRIMARY KEY,
    strategy_id     TEXT NOT NULL,
    config_hash     TEXT NOT NULL,
    data_hash       TEXT NOT NULL,
    spec_version    TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    total_trades    INTEGER,
    status          TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed', 'checkpointed'))
);
```

**`contracts/error_codes.toml` — Structured error code registry:**

```toml
[resource]
RESOURCE_MEMORY_PRESSURE = { severity = "warning", recoverable = true, action = "throttle" }
RESOURCE_THERMAL_THROTTLE = { severity = "warning", recoverable = true, action = "throttle" }
RESOURCE_DISK_FULL = { severity = "error", recoverable = false, action = "stop" }

[data]
DATA_CORRUPT_ARROW = { severity = "error", recoverable = false, action = "stop" }
DATA_SCHEMA_MISMATCH = { severity = "error", recoverable = false, action = "stop" }
DATA_QUALITY_FAILED = { severity = "warning", recoverable = true, action = "alert" }

[strategy]
STRATEGY_SPEC_INVALID = { severity = "error", recoverable = false, action = "stop" }
STRATEGY_EVAL_FAILED = { severity = "error", recoverable = false, action = "stop" }
STRATEGY_ZERO_TRADES = { severity = "warning", recoverable = true, action = "alert" }

[external]
EXTERNAL_MT5_DISCONNECT = { severity = "warning", recoverable = true, action = "retry" }
EXTERNAL_DUKASCOPY_TIMEOUT = { severity = "warning", recoverable = true, action = "retry" }
EXTERNAL_MT5_ORDER_REJECTED = { severity = "error", recoverable = false, action = "alert" }
```

## Project Structure & Boundaries

### Complete Project Directory Structure

```
forex-pipeline/
├── .gitignore
├── .env.example                        # Template for secrets (MT5 credentials, etc.)
├── CLAUDE.md                           # AI agent project context
│
├── .claude/
│   └── skills/                         # Decision 9: Operator interface skills
│       ├── strategy_research.md        # /strategy-research — FR9, FR10
│       ├── strategy_review.md          # /strategy-review — FR11
│       ├── pipeline_status.md          # /pipeline-status — FR40
│       ├── pipeline_run.md             # /pipeline-run — FR38
│       ├── pipeline_advance.md         # /pipeline-advance — FR39
│       ├── pipeline_reject.md          # /pipeline-reject — FR39
│       ├── pipeline_resume.md          # /pipeline-resume — FR42
│       ├── backtest_review.md          # /backtest-review — FR16, FR17
│       ├── optimization_review.md      # /optimization-review — FR25, FR26
│       ├── validation_review.md        # /validation-review — FR34
│       ├── deploy_practice.md          # /deploy-practice — FR48
│       ├── deploy_live.md              # /deploy-live — FR49
│       ├── promote.md                  # /promote — FR51
│       ├── live_status.md              # /live-status — FR55, FR56
│       ├── reconciliation_review.md    # /reconciliation-review — FR54
│       ├── kill_switch.md              # /kill-switch — FR47
│       └── research_topic.md           # /research-topic — Phase 0
│
├── config/
│   ├── base.toml                       # Shared pipeline config (all defaults live here)
│   ├── schema.toml                     # Config schema for startup validation
│   ├── environments/
│   │   ├── local.toml                  # execution_enabled = false
│   │   └── vps.toml                    # execution_enabled = true, heartbeat intervals
│   └── strategies/
│       └── ma_cross_v3.toml            # Strategy-specific, versioned with pipeline
│
├── contracts/                          # Single source of truth for cross-runtime types
│   ├── arrow_schemas.toml              # Arrow IPC field definitions per stage (see below)
│   ├── sqlite_ddl.sql                  # SQLite table definitions + indexes (see below)
│   ├── api_endpoints.toml              # REST endpoint contracts (path, params, response shape)
│   ├── websocket_events.toml           # Event names + payload schemas
│   ├── error_codes.toml                # Structured error code registry
│   ├── session_schema.toml             # Session label definitions + column spec
│   ├── cost_model_schema.toml          # Cost model artifact format (Decision 13)
│   └── strategy_specification.toml     # Strategy spec schema (Decision 10)
│
├── src/
│   ├── python/                         # Orchestrator + API + integrations
│   │   ├── pyproject.toml              # Python project config (dependencies, tools)
│   │   ├── main.py                     # Entry point — config load, validation, orchestrator start
│   │   │
│   │   ├── orchestrator/               # Pipeline state machine (Decision 3)
│   │   │   ├── __init__.py
│   │   │   ├── pipeline_state.py       # State file read/write, stage transitions
│   │   │   ├── stage_runner.py         # Stage dispatch — invokes Rust binary or Python stage
│   │   │   ├── gate_manager.py         # Operator gate logic — evidence pack assembly, accept/reject
│   │   │   └── recovery.py             # Crash recovery sequence (NFR12)
│   │   │
│   │   ├── api/                        # REST + WebSocket server (Decision 4)
│   │   │   ├── __init__.py
│   │   │   ├── server.py               # FastAPI app setup, middleware, lifespan
│   │   │   ├── routes/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── pipeline.py         # /api/v1/pipeline-status, /api/v1/pipeline-stages
│   │   │   │   ├── backtest.py         # /api/v1/backtest-results, /api/v1/equity-curves
│   │   │   │   ├── optimization.py     # /api/v1/optimization-candidates, /api/v1/leaderboard
│   │   │   │   ├── validation.py       # /api/v1/validation-results, /api/v1/confidence-scores
│   │   │   │   ├── analytics.py        # /api/v1/trade-analytics (Growth: session, regime)
│   │   │   │   ├── monitoring.py       # /api/v1/live-positions, /api/v1/heartbeat
│   │   │   │   └── artifacts.py        # /api/v1/artifacts, /api/v1/manifests
│   │   │   ├── websocket/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── manager.py          # Connection manager, broadcast
│   │   │   │   └── events.py           # Event emission for pipeline/optimization/monitoring
│   │   │   └── models/
│   │   │       ├── __init__.py
│   │   │       ├── responses.py        # API envelope: {data, error, meta}
│   │   │       └── queries.py          # Query parameter models
│   │   │
│   │   ├── data_pipeline/              # FR1-FR7: Dukascopy acquisition + quality
│   │   │   ├── __init__.py
│   │   │   ├── downloader.py           # Dukascopy M1 bid+ask download
│   │   │   ├── quality_checker.py      # Gap detection, integrity validation
│   │   │   ├── arrow_converter.py      # Raw data → Arrow IPC (mmap-ready)
│   │   │   └── parquet_archiver.py     # Arrow → Parquet cold storage
│   │   │
│   │   ├── strategy/                   # FR8-FR13: Strategy definition + management (Decision 10)
│   │   │   ├── __init__.py
│   │   │   ├── loader.py               # Load strategy specification, validate, hash
│   │   │   ├── registry.py             # Strategy registry (Growth: multi-strategy)
│   │   │   ├── translator.py           # Strategy spec → Rust-consumable format
│   │   │   └── specification_schema.py # Strategy specification validation against schema
│   │   │
│   │   ├── rust_bridge/                # Python-Rust process boundary
│   │   │   ├── __init__.py
│   │   │   ├── batch_runner.py         # Spawn Rust batch binary, pass config + Arrow paths
│   │   │   ├── result_ingester.py      # Arrow IPC results → SQLite ingest
│   │   │   └── error_parser.py         # Parse Rust stderr structured errors
│   │   │
│   │   ├── risk/                       # FR43-FR47: Risk management
│   │   │   ├── __init__.py
│   │   │   ├── position_limits.py      # Position sizing, exposure limits
│   │   │   └── kill_switch.py          # Independent kill switch logic (NFR18)
│   │   │
│   │   ├── monitoring/                 # FR55-FR57: Live monitoring
│   │   │   ├── __init__.py
│   │   │   ├── heartbeat.py            # Context-dependent heartbeat intervals (NFR14)
│   │   │   ├── position_tracker.py     # Live position state
│   │   │   └── alerting.py             # Operator alerts (NFR13)
│   │   │
│   │   ├── mt5_integration/            # MT5 execution gateway
│   │   │   ├── __init__.py
│   │   │   ├── connector.py            # MT5 connection, reconnect with backoff (NFR19)
│   │   │   ├── executor.py             # Order execution (VPS only)
│   │   │   └── account_reader.py       # Position/balance reads
│   │   │
│   │   ├── analysis/                   # Decision 11: AI analysis layer
│   │   │   ├── __init__.py
│   │   │   ├── narrative.py            # Backtest/optimization/validation narrative generation
│   │   │   ├── anomaly_detector.py     # Result anomaly detection and flagging (FR17, FR35)
│   │   │   ├── evidence_pack.py        # Assemble stage evidence packs for operator review (FR39)
│   │   │   └── refinement_suggester.py # Growth: multi-dimensional analytics + suggestions (FR70, FR71)
│   │   │
│   │   ├── selection/                  # Decision 11: Growth-phase candidate selection subsystem (FR26, FR27, FR28)
│   │   │   ├── __init__.py             # Public API: SelectionOrchestrator, SelectionExecutor
│   │   │   ├── models.py              # ClusterAssignment, EquityCurveQuality, RankedCandidate, SelectionManifest
│   │   │   ├── config.py              # SelectionConfig loader from [selection] TOML section
│   │   │   ├── clustering.py          # Gower distance + HDBSCAN clustering (replaces single candidate_compressor.py)
│   │   │   ├── equity_curve_quality.py # K-Ratio, Ulcer Index, DSR, Gain-to-Pain, Serenity Ratio
│   │   │   ├── ranking.py             # CRITIC weights, TOPSIS, Pareto frontier, 4-stage funnel
│   │   │   ├── diversity.py           # MAP-Elites archive, diversity-preserving selection
│   │   │   ├── visualization.py       # Parallel coords, heatmap, cluster membership viz data
│   │   │   ├── orchestrator.py        # SelectionOrchestrator — coordinates full pipeline
│   │   │   └── executor.py            # SelectionExecutor — StageExecutor for SELECTING stage
│   │   │
│   │   ├── reconciliation/             # FR52-FR54: Signal-to-execution reconciliation (Decision 12)
│   │   │   ├── __init__.py
│   │   │   ├── signal_matcher.py       # Expected vs actual trade matching
│   │   │   ├── divergence_reporter.py  # Divergence analysis + reporting
│   │   │   ├── data_augmenter.py       # Merge live trade timestamps into historical dataset
│   │   │   └── cost_model_updater.py   # FR22: live data → cost model feedback loop
│   │   │
│   │   ├── artifacts/                  # FR58-FR61: Artifact management
│   │   │   ├── __init__.py
│   │   │   ├── manifest.py             # Manifest creation (config hash, data hash, versions)
│   │   │   ├── storage.py              # Artifact directory management, crash-safe writes
│   │   │   └── sqlite_manager.py       # SQLite schema init, WAL mode, ingest coordination
│   │   │
│   │   ├── config_loader/              # Decision 7: TOML config + validation
│   │   │   ├── __init__.py
│   │   │   ├── loader.py               # Layered TOML loading (base → environment → strategy)
│   │   │   ├── validator.py            # Schema validation at startup
│   │   │   └── hasher.py               # Config hash computation
│   │   │
│   │   ├── logging_setup/              # Decision 6: Structured JSON logging
│   │   │   ├── __init__.py
│   │   │   └── setup.py                # Python logger → structured JSON to logs/
│   │   │
│   │   └── tests/
│   │       ├── conftest.py             # Shared fixtures
│   │       ├── test_orchestrator/
│   │       ├── test_api/
│   │       ├── test_data_pipeline/
│   │       ├── test_rust_bridge/
│   │       ├── test_strategy/
│   │       ├── test_analysis/          # AI analysis layer tests
│   │       ├── test_risk/
│   │       ├── test_mt5/
│   │       ├── test_reconciliation/
│   │       ├── test_artifacts/
│   │       └── test_config/
│   │
│   ├── rust/                           # Compute engine — Cargo workspace
│   │   ├── Cargo.toml                  # Workspace root
│   │   ├── rust-toolchain.toml         # Pin Rust version for reproducibility
│   │   │
│   │   ├── crates/
│   │   │   ├── common/                 # Shared types, Arrow schema builders, error types
│   │   │   │   ├── Cargo.toml
│   │   │   │   └── src/
│   │   │   │       ├── lib.rs
│   │   │   │       ├── arrow_schemas.rs    # Arrow schema definitions (aligned with contracts/)
│   │   │   │       ├── error_types.rs      # Structured error type (Decision 8)
│   │   │   │       ├── config.rs           # TOML config loading + validation
│   │   │   │       ├── logging.rs          # Structured JSON log writer
│   │   │   │       └── checkpoint.rs       # Checkpoint read/write with .partial pattern
│   │   │   │
│   │   │   ├── strategy_engine/        # Decision 14: Shared strategy evaluation (signal fidelity)
│   │   │   │   ├── Cargo.toml          # depends on: common
│   │   │   │   └── src/
│   │   │   │       ├── lib.rs
│   │   │   │       ├── evaluator.rs        # Build evaluator from spec, per-bar signal evaluation
│   │   │   │       ├── indicators.rs       # Indicator computation (MA, EMA, ATR, Bollinger, etc.)
│   │   │   │       ├── filters.rs          # Session filter, volatility filter, day-of-week filter
│   │   │   │       └── exits.rs            # Stop loss, take profit, trailing stop, chandelier exit
│   │   │   │
│   │   │   ├── cost_model/             # Decision 13: Execution cost modeling (library crate)
│   │   │   │   ├── Cargo.toml          # depends on: common. Library crate — no main.rs
│   │   │   │   └── src/
│   │   │   │       ├── lib.rs              # Public API: load cost model artifact, query per-trade cost
│   │   │   │       ├── spread_model.rs     # Session-aware spread modeling
│   │   │   │       ├── slippage_model.rs   # Slippage estimation
│   │   │   │       └── calibration.rs      # Cost model calibration from market/live data
│   │   │   │
│   │   │   ├── cost_calibrator/        # Thin CLI binary wrapping cost_model lib
│   │   │   │   ├── Cargo.toml          # depends on: common, cost_model
│   │   │   │   └── src/
│   │   │   │       └── main.rs             # CLI: build/update cost model artifact from data sources
│   │   │   │
│   │   │   ├── backtester/             # FR14-FR18: Backtesting engine
│   │   │   │   ├── Cargo.toml          # depends on: common, strategy_engine, cost_model
│   │   │   │   └── src/
│   │   │   │       ├── lib.rs              # Exposes backtest engine as lib for optimizer/validator
│   │   │   │       ├── main.rs             # Batch binary entry point (forex_backtester)
│   │   │   │       ├── engine.rs           # Core backtesting loop (SIMD, SoA layout)
│   │   │   │       ├── trade_simulator.rs  # Order fill simulation, calls cost_model per fill
│   │   │   │       ├── equity_tracker.rs   # Equity curve computation
│   │   │   │       └── output.rs           # Arrow IPC result writing
│   │   │   │
│   │   │   ├── optimizer/              # FR19-FR28: Optimization engine
│   │   │   │   ├── Cargo.toml          # depends on: common, backtester (lib), strategy_engine, cost_model
│   │   │   │   └── src/
│   │   │   │       ├── lib.rs
│   │   │   │       ├── main.rs             # Batch binary entry point (forex_optimizer)
│   │   │   │       ├── evaluator.rs        # Parallel candidate evaluation (Rayon P-core pool)
│   │   │   │       ├── resource_monitor.rs # Memory budget enforcement, throttling (NFR4)
│   │   │   │       └── output.rs           # Candidates Arrow IPC writing
│   │   │   │
│   │   │   ├── validator/              # FR29-FR33: Validation gauntlet
│   │   │   │   ├── Cargo.toml          # depends on: common, backtester (lib), strategy_engine, cost_model
│   │   │   │   └── src/
│   │   │   │       ├── lib.rs
│   │   │   │       ├── main.rs             # Batch binary entry point (forex_validator)
│   │   │   │       ├── walk_forward.rs     # Walk-forward analysis (parallelized windows)
│   │   │   │       ├── monte_carlo.rs      # Monte Carlo permutation tests
│   │   │   │       ├── confidence.rs       # RED/YELLOW/GREEN scoring (FR34)
│   │   │   │       └── output.rs           # Validation results Arrow IPC writing
│   │   │   │
│   │   │   └── live_daemon/            # FR55-FR57: Live signal evaluation (VPS)
│   │   │       ├── Cargo.toml          # depends on: common, strategy_engine, cost_model
│   │   │       └── src/
│   │   │           ├── main.rs             # Persistent daemon entry point (forex_live_daemon)
│   │   │           ├── pipe_handler.rs     # Windows Named Pipe server (Decision 15)
│   │   │           ├── signal_loop.rs      # Real-time bar → strategy_engine evaluator → signal
│   │   │           └── state.rs            # Daemon state management, heartbeat emission
│   │   │
│   │   └── tests/                      # Workspace-level integration tests
│   │       ├── integration_backtest.rs
│   │       ├── integration_optimizer.rs
│   │       └── test_data/              # Deterministic test fixtures (small Arrow IPC files)
│   │
│   └── dashboard/                      # Browser-based operator interface
│       ├── package.json
│       ├── tsconfig.json
│       ├── vite.config.ts              # Or equivalent (Phase 0 framework decision)
│       │
│       ├── src/
│       │   ├── main.ts                 # App entry point
│       │   ├── api_client/             # snake_case ↔ camelCase translation boundary
│       │   │   ├── index.ts
│       │   │   ├── rest_client.ts      # REST API calls, response envelope unwrapping
│       │   │   ├── websocket_client.ts # WebSocket connection, event routing
│       │   │   └── types.ts            # API response types (aligned with contracts/)
│       │   ├── stores/                 # Client-side state
│       │   │   ├── pipeline_store.ts
│       │   │   ├── backtest_store.ts
│       │   │   ├── optimization_store.ts
│       │   │   └── monitoring_store.ts
│       │   ├── pages/
│       │   │   ├── pipeline_overview.ts    # Pipeline stage status, operator gates
│       │   │   ├── backtest_results.ts     # Equity curves, trade log, narrative
│       │   │   ├── optimization_dashboard.ts # Candidate leaderboard, progress
│       │   │   ├── validation_report.ts    # Gauntlet results, confidence scores
│       │   │   ├── live_monitoring.ts      # Position tracking, heartbeat, kill switch (VPS)
│       │   │   └── analytics.ts            # Trade analytics (Growth: session, regime)
│       │   ├── components/
│       │   │   ├── charts/             # Equity curves, distributions, scatter plots
│       │   │   ├── tables/             # Trade logs, candidate tables, leaderboards
│       │   │   ├── gates/              # Operator gate UI — evidence pack, accept/reject
│       │   │   ├── status/             # Pipeline stage indicators, heartbeat, alerts
│       │   │   └── layout/             # Shell, navigation, common layout
│       │   └── utils/
│       │       ├── formatters.ts       # Date, number, percentage formatting
│       │       └── constants.ts
│       │
│       └── tests/
│           ├── api_client.test.ts
│           └── stores/
│
├── artifacts/                          # Runtime output (Decision 2 structure)
│   └── .gitkeep                        # Directory tracked, contents gitignored
│
├── logs/                               # Structured JSON logs (Decision 6)
│   └── .gitkeep
│
├── scripts/
│   ├── setup_local.sh                  # Local dev environment setup
│   ├── setup_vps.sh                    # VPS service installation (NSSM)
│   ├── build_rust.sh                   # Cargo build with release profile
│   └── validate_config.py              # Standalone config validation utility
│
└── docs/
    ├── architecture.md                 # → symlink or copy from planning artifacts
    └── runbooks/
        ├── vps_deployment.md           # Step-by-step VPS setup
        └── recovery_procedures.md      # Crash recovery, kill switch operation
```

### Architectural Boundaries

**Process Boundaries (Decision 1):**

```
┌─────────────────────────────────────────────────────────┐
│ Python Orchestrator Process                              │
│  ┌──────────────┐  ┌──────────┐  ┌───────────────────┐ │
│  │ Orchestrator  │  │ API      │  │ MT5 Integration   │ │
│  │ State Machine │  │ Server   │  │ (VPS only)        │ │
│  └──────┬───────┘  └────┬─────┘  └───────────────────┘ │
│         │               │                                │
│    ┌────▼────┐     ┌────▼────┐                          │
│    │ Rust    │     │ SQLite  │                           │
│    │ Bridge  │     │ Manager │                           │
│    └────┬────┘     └─────────┘                          │
└─────────┼───────────────────────────────────────────────┘
          │ subprocess spawn + Arrow IPC files
          │
┌─────────▼───────────────────────────────────────────────┐
│ Rust Batch Binary (per job, exits when done)            │
│  ┌────────────┐ ┌───────────┐ ┌───────────┐            │
│  │ Backtester │ │ Optimizer │ │ Validator │  ...        │
│  └────────────┘ └───────────┘ └───────────┘            │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Rust Live Daemon (VPS only, persistent)                 │
│  Signal evaluation, lightweight message protocol        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Dashboard (Browser)                                      │
│  REST + WebSocket → Python API Server                   │
└─────────────────────────────────────────────────────────┘
```

**Data Boundaries:**

| Boundary | Writer | Reader | Format | Direction |
|---|---|---|---|---|
| Market data | Python data_pipeline | Rust batch binary | Arrow IPC (mmap) | Python → Rust |
| Compute results | Rust batch binary | Python rust_bridge | Arrow IPC | Rust → Python |
| Queryable trades | Python result_ingester | Python API routes | SQLite (WAL) | Internal Python |
| Dashboard data | Python API server | Dashboard api_client | JSON over REST/WS | Python → Browser |
| Archival | Python parquet_archiver | (cold storage) | Parquet | Terminal |
| Config | TOML files | All runtimes | TOML (read-only) | Shared |
| Pipeline state | Python orchestrator | Python orchestrator | JSON file | Internal Python |
| Errors | Rust stderr | Python error_parser | Structured JSON | Rust → Python |

**API Boundary — REST Endpoints:**

| Route Group | Module | Key Endpoints |
|---|---|---|
| Pipeline | `api/routes/pipeline.py` | `GET /api/v1/pipeline-status`, `POST /api/v1/pipeline-stages/{stage}/advance` |
| Backtest | `api/routes/backtest.py` | `GET /api/v1/backtest-results/{strategy_id}`, `GET /api/v1/equity-curves/{strategy_id}` |
| Optimization | `api/routes/optimization.py` | `GET /api/v1/optimization-candidates`, `GET /api/v1/leaderboard` |
| Validation | `api/routes/validation.py` | `GET /api/v1/validation-results/{strategy_id}`, `GET /api/v1/confidence-scores` |
| Analytics | `api/routes/analytics.py` | `GET /api/v1/trade-analytics` (Growth phase) |
| Monitoring | `api/routes/monitoring.py` | `GET /api/v1/live-positions`, `GET /api/v1/heartbeat`, `POST /api/v1/kill-switch` |
| Artifacts | `api/routes/artifacts.py` | `GET /api/v1/artifacts/{strategy_id}`, `GET /api/v1/manifests/{strategy_id}` |

### Requirements to Structure Mapping

**Compute Tier (Rust):**

| Subsystem | FRs | Crate | Binary / Lib |
|---|---|---|---|
| Strategy evaluation (shared) | FR9-FR13, FR19, FR52 | `crates/strategy_engine/` | Library (Decision 14) |
| Execution cost modeling | FR20-FR22 | `crates/cost_model/` | Library (Decision 13) |
| Cost model calibration | FR20 | `crates/cost_calibrator/` | `forex_cost_calibrator` |
| Backtesting | FR14-FR18 | `crates/backtester/` | `forex_backtester` (lib + binary) |
| Optimization | FR23-FR28 | `crates/optimizer/` | `forex_optimizer` |
| Validation Gauntlet | FR29-FR33 | `crates/validator/` | `forex_validator` |
| Live signal evaluation | FR55-FR57 | `crates/live_daemon/` | `forex_live_daemon` |

**Orchestration Tier (Python):**

| Subsystem | FRs | Module |
|---|---|---|
| Data Pipeline | FR1-FR7 | `data_pipeline/` |
| Strategy Definition | FR8-FR13 | `strategy/` |
| Pipeline Workflow | FR38-FR42 | `orchestrator/` |
| Risk Management | FR43-FR47 | `risk/` |
| Practice/Live Deployment | FR48-FR51 | `mt5_integration/` + `orchestrator/` |
| Reconciliation | FR52-FR54 | `reconciliation/` |
| Artifact Management | FR58-FR61 | `artifacts/` |

**Interface Tier (Dashboard + Python API):**

| Subsystem | FRs | Location |
|---|---|---|
| Live Monitoring | FR55-FR57 | `monitoring/` (Python) + `pages/live_monitoring.ts` (Dashboard) |
| Dashboard MVP | FR62-FR65 | `dashboard/src/pages/` — pipeline_overview, backtest_results, optimization_dashboard, validation_report |
| Dashboard Growth | FR66-FR68 | `dashboard/src/pages/analytics.ts` + enhanced chart components |

**Operator Interface Tier (Claude Code Skills + Analysis):**

| Subsystem | FRs | Location |
|---|---|---|
| Operator dialogue control | FR38-FR42 | `.claude/skills/pipeline_*.md` |
| Strategy research & generation | FR9-FR11 | `.claude/skills/strategy_*.md` + `strategy/specification_schema.py` |
| Result analysis & narratives | FR16, FR17, FR35 | `analysis/narrative.py` + `analysis/anomaly_detector.py` |
| Evidence pack assembly | FR39 | `analysis/evidence_pack.py` |
| Candidate compression | FR26, FR28 | `analysis/candidate_compressor.py` |
| Reconciliation review | FR54 | `.claude/skills/reconciliation_review.md` + `reconciliation/` |
| Kill switch | FR47 | `.claude/skills/kill_switch.md` + `risk/kill_switch.py` |

**Cross-Cutting Concerns Mapping:**

| Concern | Location |
|---|---|
| Deterministic reproducibility | `config_loader/hasher.py` + `artifacts/manifest.py` + `rust/crates/common/config.rs` |
| Crash-safe writes | `artifacts/storage.py` + `rust/crates/common/checkpoint.rs` |
| Structured logging | `logging_setup/setup.py` + `rust/crates/common/logging.rs` |
| Error propagation | `rust_bridge/error_parser.py` + `rust/crates/common/error_types.rs` |
| Operator gates | `orchestrator/gate_manager.py` + `.claude/skills/pipeline_advance.md` + `dashboard/src/components/gates/` |
| Session-awareness | `rust/crates/cost_model/spread_model.rs` + `rust/crates/backtester/trade_simulator.rs` |
| AI analysis & narratives | `analysis/` module (Decision 11) |
| Cost model feedback | `reconciliation/cost_model_updater.py` (Decision 12) |
| Phase 0 research process | `.claude/skills/research_topic.md` + `_bmad-output/planning-artifacts/research/` |

### Development Workflow

**Local Development:**
- Python: `python -m src.python.main --env local` — runs orchestrator + API, execution disabled
- Rust: `cargo build --release` from `src/rust/` — produces binaries in `target/release/`
- Dashboard: `npm run dev` from `src/dashboard/` — dev server proxying API to Python

**VPS Deployment (Decision 5):**
- Git pull → `scripts/build_rust.sh` → `scripts/setup_vps.sh` (NSSM service registration)
- Two NSSM services: `forex-pipeline` (main orchestrator) + `forex-kill-switch` (independent)
- Same codebase, `--env vps` flag enables execution + monitoring

**Build Artifacts:**
- Rust binaries: `src/rust/target/release/forex_{backtester,optimizer,validator,cost_model,live_daemon}`
- Python: runs from source (no build step)
- Dashboard: `npm run build` → static assets served by Python API or standalone

## Architecture Validation Results

_Validated by multi-agent review (PM, Dev, QA, Analyst, SM) on 2026-03-13. Initial self-assessment replaced with peer-reviewed findings._

### Coherence Validation ✅

**Decision Compatibility:** All 15 decisions interlock without contradictions.

- D1-D8 (core decisions): all compatible — multi-process topology, Arrow IPC data exchange, sequential state machine, REST+WS API, NSSM supervision, structured logging, TOML config, fail-fast errors
- D9 (Skills) → D4 (REST API): Skills invoke API for mutations — compatible
- D9 (Skills) → D11 (Analysis): Skills call analysis for narratives, proactive findings included in skill output — compatible
- D10 (Strategy Spec) → D14 (Strategy Engine): Spec is loaded by Python, consumed by strategy_engine evaluator in Rust — compatible
- D11 (Analysis) → D2 (Storage): Analysis queries SQLite for trade-level data, reads Arrow IPC for raw results — compatible
- D12 (Reconciliation) → D13 (Cost Model): Reconciliation triggers cost model update via the same library — compatible
- D13 (Cost Model lib) → Backtester: Library dependency, no process boundary in hot path — compatible with performance requirements
- D14 (Strategy Engine shared) → Backtester + Live Daemon: Same evaluation code guarantees signal fidelity (FR19, FR52) — compatible
- D15 (Named Pipes) → D14: Live daemon uses strategy_engine for evaluation, Named Pipes for Python communication — compatible and Windows-native

**Pattern Consistency:** All naming, structure, and communication patterns align across all 15 decisions. Session-awareness flows consistently from config through data pipeline to cost model to analytics. The skills layer follows the same `snake_case` boundary conventions.

### Requirements Coverage

**Functional Requirements — Trace (87 FRs):**

| FR Range | Subsystem | Architectural Home | Coverage | Notes |
|---|---|---|---|---|
| FR1-FR7 | Data Pipeline (acquisition) | `src/python/data_pipeline/` | Full | Quality gates specified with scoring and quarantine |
| FR8 | Data consistency | `artifacts/manifest.py` + data hashing | Full | Identical Arrow IPC file guaranteed by hash |
| FR9-FR11 | Strategy Research & Generation | D9 skills + D10 specification model | Full | Minimum representable constructs defined; exact format Phase 0 |
| FR12-FR13 | Strategy Specification | `strategy_engine` crate + `contracts/strategy_specification.toml` | Full | Optimization parameter grouping in spec schema |
| FR14-FR18 | Backtesting | `crates/backtester/` + `strategy_engine` + `cost_model` | Full | Session-aware costs per trade (D13), deterministic reproducibility verified by golden file tests |
| FR19 | Signal fidelity (backtest=live) | `strategy_engine` shared crate (D14) | Full | Same code path in backtester and live daemon |
| FR20-FR22 | Execution Cost Modeling | `crates/cost_model/` (lib) + D12 feedback loop | Full | Session-aware cost model artifact with live calibration |
| FR23-FR28 | Optimization | `crates/optimizer/` | Full | Dynamic grouping interface Phase 0; resource management for Growth specified |
| FR29-FR37 | Validation Gauntlet | `crates/validator/` | Full | Confidence scoring (RED/YELLOW/GREEN) |
| FR38-FR42 | Pipeline Workflow & Operator Control | D9 skills + `orchestrator/` | Full | Proactive stale gate detection added |
| FR43-FR47 | Risk Management | `risk/` + `/kill-switch` skill | Full | Multi-strategy aggregate limits for Growth (D3 extension) |
| FR48-FR51 | Practice & Live Deployment | `mt5_integration/` + deployment skills | Full | |
| FR52-FR54 | Reconciliation | D12 augmented re-run + `/reconciliation-review` skill | Full | |
| FR55-FR57 | Live Monitoring | `monitoring/` + `live_daemon` (D15) + `/live-status` skill | Full | Named Pipe protocol for Windows specified |
| FR58-FR61 | Artifact Management | `artifacts/` | Full | Config hash + data hash = reproducibility proof |
| FR62-FR68 | Dashboard MVP | `src/dashboard/` | Full | Framework Phase 0; contract-driven API |
| FR69-FR73 | Iteration & Refinement (Growth) | D11 analysis layer + skills | Full | Proactive diminishing returns detection, session/regime/clustering analytics |
| FR74-FR78 | Dashboard Growth | `src/dashboard/` enhanced pages | Full | |
| FR79-FR82 | Strategy Lifecycle (Growth) | `/strategy-kill`, `/strategy-archive` skills + `strategy/registry.py` | Full | Proactive retirement detection (FR81) via D11 |
| FR83-FR87 | Portfolio Operations (Vision) | Strategy registry + shared risk state | Architecturally supported | Multi-strategy resource management specified in D3 |

**Non-Functional Requirements — Trace (21 NFRs):**

| NFR | Domain | Architectural Support | Coverage |
|---|---|---|---|
| NFR1-NFR3 | CPU performance | Rust SIMD/SoA/mmap (Playbook), P-core affinity, Rayon | Full |
| NFR4 | Memory budgeting | Pre-allocate at startup from available memory minus 4GB OS reserve. Data volume modeling confirms ~5.5GB active heap during optimization. | Full |
| NFR5 | Checkpointing | `.partial` → fsync → atomic rename pattern in all runtimes | Full |
| NFR6 | Dashboard latency (3s) | API pre-aggregation + SQLite indexed queries (<100ms typical) | Full |
| NFR7 | Processing latency alert | Structured logging + alerting pipeline (D6, D11 proactive monitoring) | Full |
| NFR8-NFR9 | Streaming, bounded pools | Rayon thread pool sized to P-cores; streaming Arrow IPC writes | Full |
| NFR10 | Crash prevention | Error categories (D8): resource pressure → throttle, not crash | Full |
| NFR11 | Crash-safe artifacts | Crash-safe write pattern enforced in all runtimes | Full |
| NFR12 | VPS auto-restart + recovery | NSSM (D5) + recovery sequence in `recovery.py` | Full |
| NFR13 | Operator alerting within 60s | Proactive monitoring (D11) + heartbeat (NFR14) | Full |
| NFR14 | Heartbeat monitoring | Context-dependent intervals in config; live: 30s, batch: 5min | Full |
| NFR15 | Data integrity on failure | Partial never overwrites complete (crash-safe write pattern) | Full |
| NFR16 | No plaintext credentials | Env vars only (D7), .env.example template, .gitignore | Full |
| NFR17 | VPS not exposed publicly | No public ports; Named Pipes for local IPC (D15) | Full |
| NFR18 | Independent kill switch | Separate NSSM service, separate process (D5) | Full |
| NFR19 | MT5 reconnection with backoff | `mt5_integration/connector.py` with exponential backoff, 5-attempt alert | Full |
| NFR20 | Graceful degradation | Error categories (D8): external failure → retry + alert + continue with available data | Full |
| NFR21 | Configurable timeouts | All external call timeouts in TOML config (D7) | Full |

### Implementation Readiness

**Decision Completeness:**
- 15 decisions documented with rationale, technology choices, and affected components
- Phase 0 deferred decisions have stable interface contracts
- Research process defined with gates and artifact storage
- All previously identified structural ambiguities resolved (cost model crate, strategy engine sharing, live daemon protocol)

**Structure Completeness:**
- ~110 files/directories defined across 3 runtimes + skills + contracts + tests
- All component boundaries mapped including Rust workspace dependency graph
- All integration points specified with concrete protocols

**Pattern Completeness:**
- 11 boundary naming rules + per-runtime conventions
- Crash-safe write pattern, stage contract, config access pattern
- API envelope, WebSocket event protocol, Named Pipe protocol, error propagation
- Enforcement guidelines and anti-patterns

**Testing Completeness:**
- Testing pyramid defined (70/20/10 split across unit/integration/system)
- Deterministic reproducibility verification approach specified
- Test data strategy with fixtures and generation script
- Python-Rust bridge testing approach defined
- Pre-commit and pre-deploy checklist defined

**Cross-Cutting Completeness:**
- Session-awareness architecture fully specified (config → data → cost model → analytics → dashboard)
- Data quality gates with scoring, thresholds, and quarantine behavior
- Data volume modeling with concrete numbers for storage, memory, and query performance
- Proactive monitoring triggers and notification delivery specified
- Multi-strategy resource management for Growth phase

### Gap Analysis Results

**Critical Gaps:** None.

**Phase 0 Dependent (By Design):**
- Strategy specification exact format (JSON/TOML/DSL) — interface contract defined, format deferred
- Optimization methodology (MAP-Elites/Bayesian/genetic/hybrid) — evaluator interface defined
- Dashboard framework selection — API contract defined, framework deferred
- Candidate selection methodology — compressor interface defined in D11
- Validation gauntlet configuration (window sizes, confidence thresholds) — scoring interface defined

All have stable interface contracts — research changes implementations, not boundaries.

**Minor (Resolve During Implementation):**
- Trade attribution tagging in MT5 integration (FR46) — straightforward implementation detail
- Exact Rust feature flags for conditional compilation (e.g., VPS-only live daemon features)
- Dashboard component library selection (follows framework choice)

### Architecture Completeness Checklist

**✅ Requirements Analysis**
- [x] Project context thoroughly analyzed (87 FRs, 21 NFRs, 3 architectural tiers)
- [x] Scale and complexity assessed
- [x] Technical constraints identified (9 constraints)
- [x] Cross-cutting concerns mapped (9 concerns)
- [x] Data volume modeling with concrete numbers
- [x] Session-awareness architecture specified end-to-end
- [x] Data quality gate specifications with scoring and thresholds

**✅ Architectural Decisions**
- [x] 15 decisions documented with rationale (original 12 + cost model crate, strategy engine, live daemon protocol)
- [x] Technology stack fully specified
- [x] Integration patterns defined
- [x] Performance considerations addressed with data volume modeling
- [x] Operator interface defined as primary command layer (D9)
- [x] Strategy execution model with minimum representable constructs (D10)
- [x] AI analysis layer with proactive monitoring and anomaly thresholds (D11)
- [x] Reconciliation data flow with cost model feedback (D12)
- [x] Cost model as library crate with session-aware artifact format (D13)
- [x] Strategy engine shared crate for signal fidelity (D14)
- [x] Live daemon Named Pipe protocol for Windows (D15)
- [x] Phase 0 research process defined with gates

**✅ Implementation Patterns**
- [x] Naming conventions established (11 boundary rules)
- [x] Structure patterns defined (by-runtime-then-component)
- [x] Communication patterns specified (WebSocket, Named Pipes, error propagation, skills-to-API)
- [x] Process patterns documented (stage contract, crash-safe writes, config access)
- [x] Contracts directory content specified (Arrow schemas, SQLite DDL, error codes)

**✅ Project Structure**
- [x] Complete directory structure defined (~110 files/directories)
- [x] Component boundaries established (process, data, API, skills)
- [x] Rust workspace dependency graph with binary naming
- [x] Integration points mapped (12+ data boundary flows)
- [x] Requirements to structure mapping complete (all subsystems + operator interface tier)

**✅ Testing Strategy**
- [x] Testing pyramid (70% unit / 20% integration / 10% system)
- [x] Deterministic reproducibility verification approach
- [x] Test data strategy with fixtures
- [x] Python-Rust bridge testing approach
- [x] Pre-commit and pre-deploy checklist

### Architecture Readiness Assessment

**Overall Status:** READY FOR PHASE 0 RESEARCH, THEN IMPLEMENTATION

**Confidence Level:** High — reviewed by multi-agent panel, all identified gaps addressed

**Key Strengths:**
- Clean process separation with isolated failure domains
- Arrow IPC eliminates serialization overhead; data volume modeling confirms sizing
- Claude Code skills as primary operator interface — matches PRD intent (FR38)
- Specification-driven strategy model — deterministic, reviewable, diffable, with minimum construct requirements
- Strategy engine shared crate guarantees signal fidelity between backtest and live
- Cost model as library crate — session-aware, per-trade in hot path, live-calibrated
- AI analysis layer with proactive monitoring — system surfaces insights, doesn't wait to be asked
- Session-awareness as first-class architectural dimension from config to dashboard
- Data quality gates with quantified scoring before any backtest runs
- Reconciliation with cost model feedback creates a self-improving fidelity loop
- Concrete data volume numbers validate memory budgeting and storage assumptions
- Testing strategy addresses the hardest boundary (Python-Rust bridge)
- Every FR and NFR traces to a concrete location in the project structure

**Phase 0 Research Must Complete Before Implementation Begins:**
- Strategy specification format → unlocks strategy_engine evaluator implementation
- Optimization methodology → unlocks optimizer crate implementation
- Dashboard framework → unlocks dashboard implementation
- Candidate selection methodology → unlocks candidate_compressor implementation

### Implementation Handoff

**AI Agent Guidelines:**
- Follow all 15 architectural decisions exactly as documented
- Use implementation patterns consistently across all components
- Respect project structure and boundaries, especially the Rust workspace dependency graph
- Use `contracts/` schema definitions as the single source of truth for cross-runtime types
- Refer to this document for all architectural questions
- Claude Code skills are the operator's primary interface — implement alongside backend capabilities
- Run anomaly detector as a post-stage hook — proactive, not on-demand only
- Session-awareness must flow end-to-end: config → data pipeline → cost model → backtester → analytics → dashboard

**Implementation Sequence:**
1. Phase 0 research — resolve deferred decisions before building
2. Configuration management (TOML + schema + session definitions)
3. Contracts directory — all schema definitions
4. Logging setup
5. Strategy engine shared crate (D14) + cost model library (D13)
6. Data pipeline with quality gates
7. Backtester binary (D1)
8. Pipeline state machine + orchestrator
9. REST API + WebSocket server
10. Analysis layer with proactive monitoring (D11)
11. Claude Code skills (D9)
12. Optimization + validation binaries
13. Reconciliation with cost model feedback (D12)
14. NSSM service setup on VPS (D5)
15. Live daemon with Named Pipes (D15)
16. Dashboard (after framework research)
