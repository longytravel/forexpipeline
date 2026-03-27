# Epic 3 Stories 3-1 & 3-2 — Results Summary

## Run Overview

| Story | Duration | Verdict | Tests | Key Deliverable |
|-------|----------|---------|-------|-----------------|
| 3-1 Backtest Engine Review | 43 min (03:31–04:14) | DONE | 108 unit, 11 live | Baseline review: 18-component verdict table |
| 3-2 IPC & Determinism Research | 30 min (04:19–04:49) | DONE | 119 unit (41 new), 3 live | IPC recommendation + reproducibility contract |

Both are **research stories** — no production code, deliverables are comprehensive research artifacts that inform Stories 3-3 through 3-9.

---

## Story 3-1: ClaudeBackTester Backtest Engine Review

### What Was Reviewed
- **28 components** across Rust (1,646 lines) and Python (8,428 lines)
- Key finding: ClaudeBackTester is **Python-first** with a small Rust PyO3 acceleration layer — not a Rust-centric system as initially assumed
- Actual codebase is ~10K lines, not 184K+ as story spec claimed

### Component Verdicts
| Verdict | Count | What |
|---------|-------|------|
| **Keep** | 4 | Trade simulation (trade_basic/full.rs), metrics.rs, SL/TP, time filtering |
| **Adapt** | 10 | Python engine, encoding, samplers, validation stages, checkpoint, configs |
| **Replace** | 2 | PyO3 dispatch (lib.rs), pipeline runner (runner.py) |
| **Build New** | 1 | Cost model integration (already built in Epic 2) |
| **Defer** | 1 | Telemetry engine (post-V1) |

### Four Architectural Shifts Identified
1. **PyO3 in-process → Multi-process Arrow IPC** — trade logic transfers clean; marshalling completely replaced
2. **Ad-hoc runner → Explicit state machine** — runner.py (670L) replaced; validation implementations preserved
3. **Flat cost constants → Session-aware cost model** — surgical change (2 integration points in Rust)
4. **Monolithic lib.rs → Strategy engine + backtester separation** — crate decomposition per D14

### Four Architecture Updates Proposed
1. **D1 Windowed evaluation** — Rust binary holds data, evaluates multiple param batches (avoids 400+ process launches)
2. **D3 Optimization sub-states** — model 5 optimization stages as sub-states for checkpoint/resume
3. **D1/NFR5 Sub-stage checkpointing** — per-candidate (walk-forward), per-fold (CPCV)
4. **D13 Per-bar cost integration** — document 2 surgical integration points

---

## Story 3-2: Python-Rust IPC & Deterministic Backtesting Research

### IPC Decision
**Subprocess + Arrow IPC** (validates architecture decision D1):
- Full process boundary for crash isolation
- Structured JSON stderr for errors
- Zero-copy mmap-friendly
- Windows-compatible
- Rejected: PyO3 in-process (current, crash-coupled), shared memory (complexity not worth marginal gain)

### Determinism Strategy
- **Floating-point:** FMA flags (`-C target-feature=-fma`), IEEE 754 on Windows x86-64
- **Rayon:** `IndexedParallelIterator` for deterministic chunk assignment
- **Seeds:** `SeedableRng` (ChaCha8Rng) with propagation across workers
- **Timestamps:** Int64 microsecond epoch, UTC-only

### Reproducibility Contract
- **Bit-identical:** Trade logs, equity curves, metrics
- **Tolerance-based:** Manifest hash only

### Two-Level Checkpoint Architecture
- **Within-stage (Rust):** Crash-safe resume with config hash, last index, open position state
- **Cross-stage (Python):** JSON state machine per D3

### Memory Budget
- **~1.5GB active** for 10-year EURUSD M1 with 16 threads
- Throttle-before-OOM thresholds defined

### Architecture Alignment
- **All D1-D14 aligned, zero deviations**

---

## Review Quality Summary

### Issues Found & Fixed During Pipeline
| Category | 3-1 | 3-2 |
|----------|-----|-----|
| HIGH findings | 2 (both fixed) | 1 (equity curve contract contradiction — fixed) |
| MEDIUM findings | 3 (fixed) | 4 (all fixed) |
| LOW findings | 1 | 3 (all fixed) |
| Tests added | 3 regression | 41 new (36 appendix + 5 regression) |
| Rejected findings | 1 | 2 |

### PIR Verdict (3-1)
- **Alignment: STRONG** — research correctly maps baseline to architecture decisions
- **Simplification: ADEQUATE**
- **Forward Look: ADEQUATE**

---

## Key Gaps Identified for Research

### Technical Gaps
1. **IPC pattern validation** — Arrow IPC chosen via analysis, not benchmarked against real competitors' approaches
2. **Determinism verification** — FMA flags and Rayon ordering theorized but not validated against production quant systems
3. **Checkpoint granularity** — per-candidate vs per-fold vs per-trial tradeoffs need external validation
4. **Memory budget** — 1.5GB model needs validation against real-world backtesting systems at scale
5. **Windowed evaluation pattern** — proposed but not researched against how VectorBT/others handle multi-window optimization

### Architecture Gaps
1. **State machine patterns** — D3 defined abstractly; need concrete patterns from production pipeline systems
2. **Evidence pack schema** — no precedent studied; Story 3-7/3-8 need this
3. **AI analysis of backtest results** — novel capability, no baseline from competitors
4. **Operator approval UX** — no research on how professional systems handle human-in-the-loop pipeline control

### Competitive Intelligence Gaps
1. How do VectorBT, MT5, NinjaTrader, QuantConnect, Zipline, Backtrader architect their engines?
2. What IPC/serialization patterns do high-performance quant systems use?
3. What validation methodologies (walk-forward, CPCV, Monte Carlo) are industry standard vs novel?
4. How do competitors handle results storage, visualization, and decision support?

---

## Research Briefs 3A/3B/3C — External Research (Completed 2026-03-18)

Three comprehensive research briefs were conducted externally and validated:

### Brief 3A: Backtesting Engine Architecture & Competitive Analysis
- **Key finding:** No existing system combines Rust vectorized evaluation + Python orchestrated WFO + subprocess isolation with Arrow IPC. System occupies unique architectural position.
- **Recommendation:** Library-with-subprocess-wrapper pattern preserves PyO3 escape hatch.
- **Validated:** D1 subprocess + Arrow IPC is defensible despite being unconventional. SQLite WAL caching at 0.05-0.25% overhead for crash recovery.

### Brief 3B: Deterministic Backtesting Validation Methodology
- **Key finding:** Naive Sharpe threshold (t≥2) has 37% false positive rate at 20 trials, 90% at 100 trials. Completely useless for optimization with 200K+ trials.
- **Recommendation:** DSR (Deflated Sharpe Ratio) and PBO (Probability of Backtest Overfitting) as primary validation gates.
- **Validated:** Tiered reproducibility (A/B/C). Regime analysis V1: volatility-regime bucketing.

### Brief 3C: Results Analysis, AI Narratives & Operator Experience
- **Key finding:** Competitive gap is the combination of persistence-first schema + anomaly detection for research pathologies + AI narratives constrained to internal evidence.
- **Recommendation:** Deterministic computation first, LLM narration second. Evidence packs support two-pass review (60s triage + 5-15min deep review).
- **Validated:** Adopt pyfolio/QuantStats for baseline metrics; build custom DSR/PBO/SPA gates and narrative layer.

---

## Optimization Methodology Research (Completed 2026-03-18)

Four research artifacts covering CV-inside-objective optimization and staged vs joint parameter optimization. Feeds into Epic 5 story creation.

### CV-Inside-Objective
- **Key finding:** Embedding cross-validation directly in the optimization objective (mean-λ·std aggregation across folds) is the primary defense against overfitting. DRO-optimal per Duchi & Namkoong (2019).
- **Computational cost:** 1.3-2.5x baseline with early stopping, not 5x.
- **Architecture implication:** Rust evaluator must support fold-aware batch evaluation (per-fold scores, not just aggregated).

### Staged vs Joint Optimization
- **Key finding:** 5-stage parameter locking (Signal → Time → Risk → Management → Refinement) misses cross-group interactions. Signal+Time separation is defensible; Risk/Management split is not.
- **Evidence:** March 2026 testing showed broken CMA-ES (random search) outperformed all "intelligent" optimizers on OOS metrics. Staged optimization produced deeper local optima that didn't generalize.
- **Architecture implication:** Architecture must NOT prescribe staging structure. Optimization is opaque to the pipeline state machine. Optimizer manages its own internal state behind a pluggable interface.

### Conditional Parameters
- **Key finding:** Conditional parameter handling (e.g., trailing params only active when trailing_mode ≠ none) reduces effective search space from ~10^15 to ~70M combinations.
- **Architecture implication:** Strategy spec must define parameter conditionals. Optimizer must respect them.

**Full research summary:** `research/briefs/optimization/optimization-methodology-research-summary.md`
