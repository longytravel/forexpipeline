# Research Briefs Summary: Tasks 3A, 3B, 3C

## Source Files
- `3A/RB-3A-backtesting-engine-architecture-competitive-analysis.md` (brief)
- `3A/deep-research-report (1).md` (deep research)
- `3A/compass_artifact_wf-2a9c2c55-...md` (compass)
- `3A/Backtesting Engine Architecture Research Brief.txt` (extended analysis)
- `3B/RB-3B-deterministic-backtesting-validation-methodology.md` (brief)
- `3B/deep-research-report (2).md` (deep research)
- `3B/compass_artifact_wf-7ba6d0f6-...md` (compass)
- `3B/Gemini` (gemini analysis)
- `3C/RB-3C-results-analysis-ai-narratives-operator-experience.md` (brief)
- `3C/deep-research-report (3).md` (deep research)
- `3C/compass_artifact_wf-79856384-...md` (compass)
- `3C/Gemini` (gemini analysis)

---

## Brief 3A: Backtesting Engine Architecture & Competitive Analysis

### Research Objective
External validation of the planned architectural direction: subprocess orchestration, Arrow IPC for data interchange, pipeline state machine, and checkpoint/resume for windowed evaluation. Informs Stories 3-3, 3-4, 3-5.

### Key Findings

**Architectural landscape pattern:** High-performance backtesters bifurcate into a high-level Python orchestration layer and a low-level compiled compute kernel (Rust or C#). This hybrid approach is exemplified by Nautilus Trader and QuantConnect LEAN. The Python GIL and sequential event loops (Backtrader, Zipline) create bottlenecks at terabyte-scale data.

**Two optimization axes:** Engines optimize for either (a) throughput at scale (many parameter sets quickly) or (b) execution realism/parity with live trading. Systems targeting both become hybrids: vectorized/batch computation where causality allows, event-driven simulation for order lifecycle/fills/slippage.

**Parallelism pattern:** Engines that scale to large optimization workloads treat each backtest run (or run-slice) as an independent unit of work schedulable across processes/threads.

### Competitive Analysis Matrix

| System | Architecture | IPC Pattern | Parallelism | Crash Recovery |
|--------|-------------|-------------|-------------|----------------|
| **VectorBT** | Vectorized NumPy/Numba, pure Python | In-process | Thread-level via Numba | None native |
| **Nautilus Trader** | Rust core + Python orchestration (PyO3) | In-process via PyO3 | Rust-level threading | Limited |
| **QuantConnect LEAN** | C# engine + Python wrapper | Subprocess/API | Cloud-distributed jobs | Platform-level |
| **MetaTrader 5** | C++ engine, MQL5 strategies | Proprietary IPC | Distributed optimization agents | Built-in |
| **Backtrader** | Pure Python event loop | In-process | None native | None native |
| **Zipline** | Pure Python event loop | In-process | None native | None native |
| **NinjaTrader** | .NET engine | In-process | Strategy Analyzer optimization | Limited |

**Unique positioning:** No existing backtesting system combines Rust-speed vectorized evaluation, Python-orchestrated walk-forward optimization with cross-validation objectives, and subprocess-based process isolation with Arrow IPC. Closest analogs: VectorBT (vectorized without Rust/WFO), Nautilus (Rust+Python without vectorized optimization), MT5 (distributed optimization without Python/Rust).

### Performance Benchmarks

**IPC overhead (Arrow IPC via subprocess):** 30-280ms per batch. At target scale of millions of evaluations, this translates to 8-78 hours of pure IPC overhead per million-evaluation optimization run.

**SQLite WAL result caching:** 0.05-0.25% overhead with batched commits. Provides per-evaluation crash recovery and enables "restart by re-running the script" pattern.

**Vectorized vs event-driven:** VectorBT demonstrates ~1000x speedups over pure Python event loops via NumPy vectorization. Nautilus achieves similar gains via Rust compilation.

### Architectural Recommendations

1. **Highest-impact change:** Design the Rust evaluator as a library with a subprocess wrapper, not subprocess-only binary. Zero cost now, provides zero-friction migration path to PyO3 in-process bindings later. Eliminates 30-280ms IPC overhead per batch.

2. **Lowest-risk, highest-value adoption:** SQLite WAL-backed result caching with batched commits. At 0.05-0.25% overhead, provides per-evaluation crash recovery. Combined with two-level checkpointing, matches enterprise HPC robustness at fraction of complexity.

3. **Arrow IPC validation verdict:** Arrow IPC is validated for the current architecture. It is the industry-standard high-performance serialization for columnar data. The subprocess wrapper preserves process isolation (crash safety). Future PyO3 migration eliminates the IPC layer entirely when ready.

4. **Cross-system takeaways for state machine:** Production systems that handle crash recovery either (a) use database-backed checkpointing (QuantConnect, enterprise HPC) or (b) treat runs as idempotent/restartable (VectorBT approach). The planned two-level checkpoint (coarse pipeline state + fine SQLite per-eval) aligns with pattern (a) while being simpler.

---

## Brief 3B: Deterministic Backtesting & Validation Methodology

### Research Objective
How to guarantee reproducibility, validate backtesting correctness, detect overfitting, and implement regime-aware analysis. Informs validation and statistical integrity of the pipeline.

### Key Findings

**Reproducibility is tiered, not binary.** Three tiers proposed:

**Tier A — Deterministic research replay (same artifact, same machine class):**
- Guarantee: identical event stream produces identical decisions/trades and identical trade log bytes
- Controls: freeze data snapshot + feature generation inputs; freeze build artifacts (compiler version, flags, deps); eliminate nondeterminism from parallel reductions and map iteration ordering
- Rayon explicitly documents reduction order is "not specified" and floating-point operations are "not fully deterministic"

**Tier B — Deterministic engine correctness (same inputs, different CPU/thread schedules):**
- Guarantee: changing thread counts/scheduling does not change outputs (or changes are bounded and explainable)
- Options: deterministic reductions (fixed partitioning + stable combine order) or designed-for-reproducibility accumulators
- If full Tier-B is expensive, apply selectively to "decision-boundary" computations (position sizing, risk limits, thresholded signals)

**Tier C — Cross-platform portability:**
- IEEE 754 does not guarantee unique NaN propagation; real platforms may flush subnormals
- Full cross-platform bit-identical is impractical; bounded tolerance is the pragmatic standard

### Floating-Point Determinism Controls (V1 Minimum)

1. Ship with "no fast-math" semantics; explicitly manage FP contraction
2. Pin CPU features (or explicitly disable `fma`) via `-C target-feature`; record resulting target-features list in backtest artifact
3. Treat parallel reductions over floats as non-deterministic unless order is enforced
4. Decide NaN payload and subnormal handling across platforms
5. FMA changes rounding semantics: multiply-add with one rounding instead of two, can change branch outcomes

### Overfitting Detection Toolkit

**Tier-1 academic tests (high-confidence; if triggered, change the operator's prior):**

- **White's Reality Check:** Directly addresses data snooping when many strategies are tested on same data
- **Hansen's Superior Predictive Ability (SPA) test:** More powerful improvement over Reality Check
- **Deflated Sharpe Ratio (DSR):** Corrects observed Sharpe for non-normality, sample length, and selection bias from multiple trials. Critical for large parameter sweeps.
- **Probability of Backtest Overfitting (PBO):** Uses combinatorially symmetric cross-validation (CSCV) to estimate how likely a backtest is overfit

**False positive rates under multiple testing (concrete numbers):**
- 20 trials: P(at least one Z>2) ~ 37%
- 100 trials: P(at least one Z>2) ~ 90%
- 1000 trials: P(at least one Z>3) ~ 74%
- This motivates stronger cutoffs and explicit multiplicity control beyond naive t ~ 2 threshold

### Walk-Forward and Cross-Validation

- **Walk-Forward Analysis (WFA):** Standard approach but insufficient alone
- **Combinatorial Purged Cross-Validation (CPCV):** Explicitly targets research pipeline overfitting; generates many train/test splits from limited data without leakage
- IS-WFA-OOS protocol: In-sample optimization, walk-forward validation, out-of-sample final test with pre-committed gates

### Regime Analysis (Practical V1)

**Two canonical academic approaches:**

1. **Markov Switching (Hamilton 1989):** Models regime shifts as discrete-state Markov process. Provides tractable framework for regime changes.
2. **Bayesian Online Change-Point Detection (Adams & MacKay 2007):** Infers most recent changepoint and run length online. Explicitly useful for finance/time-series.

**V1 practical recommendation:** Start with simple volatility-regime bucketing (e.g., realized vol terciles), then optionally add HMM if needed. The key is that strategy performance should be evaluated per-regime, not just aggregate.

---

## Brief 3C: Results Analysis, AI Narratives & Operator Experience

### Research Objective
How to persist, analyze, present, and operationalize backtest results using AI narratives, anomaly detection, and evidence packs. Informs Stories 3-6, 3-7, 3-8. Two key constraints: solo operator pipeline (one decision-maker) and false positive minimization.

### Key Findings

### Results Storage: SQLite-First Schema

**Architecture pattern:** Queryable metadata in SQLite, heavy objects (equity curves, position matrices, optimization surfaces) in Parquet artifact files. Mirrors MLflow/W&B/Neptune backend-store vs artifact-store split.

**Recommended schema (conceptual):**

- **Core identity:** `runs` (UUID, timestamps, engine version, status, duration, seed, environment fingerprint, notes), `strategies` (git commit hash, version), `datasets` (vendor, universe, frequency, start/end, checksums), `cost_models` (fees, spread/slippage, margin)
- **Provenance:** `run_provenance` joining run to strategy/dataset/cost_model, plus "derived from run_id" for optimization chains
- **Metrics:** `metrics` (run_id, metric_name, value, unit, calculation_version), `metric_sets` (IS/OOS/WFA fold grouping)
- **Events:** `orders`, `fills`, `trades` (entry/exit, pnl gross/net, MAE/MFE, holding time), `positions` (optional snapshots as artifacts)
- **Artifact registry:** `artifacts` (type, storage_uri, hash, size), `artifact_lineage` (for evidence pack builds)

**SQLite WAL mode:** Enables concurrent readers during writes (one writer). DuckDB can query Parquet directly with filter/column pushdown for "SQL over artifacts" without importing.

### AI Narrative Architecture

**State-of-the-art framing:** LLMs as interfaces and analysts over structured data, not LLMs placing trades. Aligns with "data-to-text" research community. Known pitfalls: numeric faithfulness, omission errors, misleading emphasis.

**Practical architecture (deterministic-first, LLM-second):**

1. Deterministic layer computes metrics, attribution slices, regime buckets, anomaly test outputs from raw artifacts/trades
2. LLM layer receives only structured inputs (JSON metric sets + anomaly flags + evidence artifact references)
3. LLM is constrained to produce structured output validatable against schema (OpenAI Structured Outputs / Anthropic tool-use contracts)
4. Every narrative claim must cite exact metric IDs or chart IDs (internal evidence references, not web citations) — hallucination mitigation via grounding

**AI Narrative Pattern Catalog (tailored to backtests):**
- Performance summary narrative (aggregate metrics to plain English)
- Risk characterization (drawdown analysis, tail risk, regime sensitivity)
- Trade pattern analysis (clustering, time-of-day effects, pair correlations)
- Anomaly explanation (what triggered, why it matters, evidence pointers)
- Comparative narrative (this run vs baseline/previous best)

### Anomaly Detection Toolkit

**Key distinction:** Backtest anomaly detection targets research process failures (overfitting, data snooping) and simulation realism failures (liquidity mirages, fill assumptions), not generic time-series outliers.

**Tier-1 tests (academic grounding):**
- White's Reality Check + Hansen's SPA test (data snooping)
- Deflated Sharpe Ratio (selection bias correction)
- Probability of Backtest Overfitting / CSCV (research pipeline overfitting)

**Practical production-grade anomaly patterns:**
- Liquidity mirages (fills at prices with insufficient volume)
- Overnight gap exploitation (unrealistic fill assumptions)
- Survivorship bias indicators
- Excessive parameter sensitivity (performance cliffs near optimal)
- Cost model stress failures (results flip under realistic costs)

**Threshold strategy (two-layer design to reduce alert fatigue):**
- Layer A: Silent scoring (compute and store anomaly scores for every run)
- Layer B: Surfaced flags only when (a) multiple independent detectors agree OR (b) tier-1 academic test triggers

### Evidence Pack Specification

**Minimum viable evidence pack (self-contained, readable without the system):**

1. **Human-readable report (HTML + printable PDF):** Executive summary narrative, key charts + "top risks", explicit limitations and assumptions
2. **Machine-readable manifest (manifest.json):** Run ID, timestamps, strategy version (git hash), engine version, dataset ID + hashes, cost model parameters, seeds, pointers + hashes for every included file
3. **Canonical artifacts:** Trade list (CSV/Parquet), equity and drawdown series (Parquet), summary metrics table (JSON/CSV), optimization surface (if applicable), anomaly detector outputs with evidence pointers
4. **Decision trace:** Pre-committed thresholds and gates used, PASS/FAIL outcome by gate, operator note fields

**Two-pass scanning optimization:**
- Pass 1 (60 seconds or less): Summary card with headline metrics (Sharpe/Sortino, max drawdown, profit factor, trade count), dominant edge description (1-2 sentences), top 3 risks/anomalies with severity, delta since last run
- Pass 2 (5-15 minutes): Full review for approve/reject/revise decision

### Operator UX Patterns

**Decision support dashboard order:**
1. Behavior first: equity curve + underwater/drawdown
2. Then summary metrics
3. Trade distribution: holding time, profit distribution, MAE/MFE for winners/losers
4. Stress and fragility: cost stress envelope, parameter sensitivity surface, "stable region" highlighting
5. Anomaly explainability: every flag clicks through to evidence panel (exact chart/time window/trade subset + test definition)

**Solo approval workflow (adapted from MLOps staged promotion):**
- Intake/triage: queue of candidate runs with status, key metrics, anomaly severity, delta vs baseline
- Review mode: narrative + evidence side-by-side, "ask questions" panel using only internal evidence references
- Decision: approve/reject/revise with forced reason codes + free text notes; evidence pack snapshot captured and immutable

### Competitive Feature Matrix Gap Analysis

**Gap no competitor fills:** The missing combination across all systems is:
1. Persistence-first schema optimized for querying across thousands of runs
2. Detection layer flagging backtest-specific research/simulation pathologies
3. AI narrative layer constrained to internal evidence, emitting exportable evidence packs

### pyfolio/QuantStats Evaluation

- **Licensing:** Both Apache 2.0. Empyrical (metric core) also Apache-licensed.
- **Recommendation: Adopt for baseline, extend for differentiators.**
  - Use Empyrical/QuantStats for standard metric correctness and familiar visuals (tear sheets, rolling metrics, drawdown visualizations, monthly/annual breakdowns)
  - Build custom research integrity metrics (DSR/PBO/Reality Check/SPA + gate logic) as first-class tables in results DB
  - Build narrative/evidence-pack layer as own pipeline stage with Structured Outputs and tool-calling constraints

---

## Cross-Brief Implementation Priorities

| Priority | Source | Recommendation |
|----------|--------|---------------|
| 1 | 3A | Design Rust evaluator as library-with-subprocess-wrapper (PyO3 migration path) |
| 2 | 3A | SQLite WAL result caching with batched commits (0.05-0.25% overhead) |
| 3 | 3B | Ship V1 with no-fast-math, pinned CPU features, ordered reductions (Tier A) |
| 4 | 3B | Implement DSR + PBO as primary overfitting gates |
| 5 | 3C | Adopt Empyrical/QuantStats for baseline metrics; build custom anomaly layer |
| 6 | 3C | Deterministic-first, LLM-second narrative architecture with structured outputs |
| 7 | 3C | Two-pass evidence pack with 60-second summary card |
| 8 | 3B | Volatility-regime bucketing for V1 regime analysis |
