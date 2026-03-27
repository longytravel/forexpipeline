---
status: complete
date: 2026-03-14
author: ROG + John (PM)
inputDocuments:
  - baseline-capability-gap-assessment-ClaudeBackTester-2026-03-13.md
  - architecture.md (15 decisions, revised 2026-03-13)
  - prd.md
purpose: Bridge the gap assessment to the new architecture. Determines per-component what to keep/wrap/replace. Informs epic creation and Phase 0 research sequencing.
---

# Baseline-to-Architecture Mapping

## Decision Context

The Forex Pipeline is a brownfield project building on the ClaudeBackTester. The PRD's default strategy is "wrap-and-extend" — preserve what works, replace what doesn't, build what's missing. This document maps the existing baseline capabilities to the new architecture's structure so that epic creation reflects reality rather than guesswork.

## Source: Gap Assessment Reuse Direction

From `baseline-capability-gap-assessment-ClaudeBackTester-2026-03-13.md`:

| Area | Direction | Baseline Status |
|---|---|---|
| Data pipeline | Keep and adapt | Mature — acquisition, validation, splitting, timeframe conversion |
| Backtest engine | Keep | Core technical asset with Rust-backed batch evaluation |
| Rust evaluation layer | Keep | Performance baseline worth preserving |
| Validation pipeline | Keep and adapt | Walk-forward, CPCV, stability, Monte Carlo, regime, confidence scoring |
| Live trader + MT5 | Keep and adapt | Needs reconciliation and promotion gating |
| Risk manager | Keep | Already aligned with trust-first goals |
| Dashboard | Extend | Good starting point for evidence packs |
| Strategy authoring | Replace / add new layer | Major unresolved gap |
| Reconciliation | Build new | Core missing feature |
| Portfolio manager | Defer | Not V1 |

## Mapping to New Architecture (15 Decisions)

### Compute Tier (Rust Crates)

| New Architecture Component | Baseline Status | Action | Phase 0 Research Needed? | Notes |
|---|---|---|---|---|
| `crates/common/` (Arrow schemas, errors, config, logging, checkpoint) | Partial — Rust layer exists but schemas are new | **Build new**, informed by baseline patterns | No | New contracts-first approach; baseline Rust patterns may inform style |
| `crates/strategy_engine/` (D14 — shared evaluator, indicators, filters, exits) | **Exists** — Rust evaluation layer documented as working | **Wrap then extend** | Yes — strategy definition format research determines spec-to-evaluator interface | Core reusable asset. Current evaluation works; new spec-driven interface wraps it |
| `crates/cost_model/` (D13 — session-aware spread/slippage lib) | **Does not exist** | **Build new** | Yes — execution cost modeling research | Gap assessment confirms no baseline. Research-first |
| `crates/cost_calibrator/` (thin CLI for cost model) | Does not exist | **Build new** | Yes — depends on cost model research | |
| `crates/backtester/` (batch backtest binary) | **Exists** — Rust-backed batch evaluation | **Wrap and adapt** | No (strategy_engine research affects interface, not backtester core) | Adapt to use strategy_engine crate + cost_model lib. Core backtest loop likely reusable |
| `crates/optimizer/` (batch optimization binary) | **Exists** — staged optimization documented | **Wrap and adapt** | Yes — optimization methodology research | Current: fixed 5-stage model. New: research-selected methodology. Likely significant rework |
| `crates/validator/` (validation gauntlet) | **Exists** — walk-forward, CPCV, Monte Carlo, confidence scoring | **Keep and adapt** | Yes — validation gauntlet configuration research | Strong baseline. Adapt output to Arrow IPC + confidence scoring contract |
| `crates/live_daemon/` (D15 — live signal evaluation via Named Pipes) | **Partial** — live trader exists but different architecture | **Build new**, reference baseline live logic | No (Named Pipe protocol is new; strategy_engine handles signal fidelity) | Baseline live trader is Python-centric. New architecture puts signal evaluation in Rust daemon |

### Orchestration Tier (Python)

| New Architecture Component | Baseline Status | Action | Phase 0 Research Needed? | Notes |
|---|---|---|---|---|
| `orchestrator/` (D3 — pipeline state machine) | **Does not exist** as formal state machine | **Build new** | No | Baseline has ad-hoc pipeline flow. New: explicit state machine with gates |
| `api/` (D4 — REST + WebSocket) | **Partial** — dashboard backend exists | **Extend** | Yes — dashboard framework research affects API shape | Existing API likely usable as starting point |
| `data_pipeline/` (acquisition, quality, Arrow conversion) | **Exists** — documented as mature | **Keep and adapt** | No | Add quality scoring/quarantine (new). Core download/validation reusable |
| `strategy/` (D10 — spec loading, registry, validation) | **Does not exist** as spec-driven system | **Build new** | Yes — strategy definition format research | Major gap. Current system has no deterministic spec model |
| `rust_bridge/` (subprocess spawn, Arrow IPC exchange) | **Partial** — Rust invocation exists | **Adapt** | Yes — Python-Rust IPC research may change mechanism | Baseline already calls Rust; adapt to Arrow IPC contract |
| `risk/` (position limits, kill switch) | **Exists** | **Keep** | No | Gap assessment confirms alignment with trust goals |
| `monitoring/` (heartbeat, position tracking, alerting) | **Partial** — live monitoring exists | **Adapt** | No | Add context-dependent heartbeat intervals, structured alerts |
| `mt5_integration/` (connector, executor, account reader) | **Exists** | **Keep and adapt** | No | Add trade attribution (FR46), reconnect with backoff |
| `analysis/` (D11 — narrative, anomaly, compression, evidence packs) | **Does not exist** | **Build new** | No | Entirely new capability. Core differentiator |
| `reconciliation/` (D12 — signal matching, cost model feedback) | **Does not exist** | **Build new** | Yes — reconciliation methodology research | Gap assessment confirms this is the core missing feature |
| `artifacts/` (manifest, storage, SQLite manager) | **Partial** — some artifact handling exists | **Build new** | No | New contracts-first approach with crash-safe writes |
| `config_loader/` (D7 — TOML, schema validation, hashing) | **Partial** — config exists but not schema-validated | **Build new** | No | New deterministic config with hash-based reproducibility |
| `logging_setup/` (D6 — structured JSON logging) | **Partial** — logging exists | **Adapt** | No | Switch to structured JSON, per-runtime files |

### Interface Tier

| New Architecture Component | Baseline Status | Action | Phase 0 Research Needed? | Notes |
|---|---|---|---|---|
| `dashboard/` (browser-based) | **Exists** — optimization monitoring, result visualization | **Extend** | Yes — dashboard framework research | Good starting point. Extend for evidence packs, gates, analytics |
| `.claude/skills/` (D9 — operator interface) | **Does not exist** | **Build new** | No | Entirely new. Primary operator command layer |

## Phase 0 Research — Sequencing and Baseline Impact

Research topics ordered by dependency. Baseline knowledge informs but does not determine outcomes.

| # | Research Topic | Blocking | Baseline Informs? | Research Approach |
|---|---|---|---|---|
| 1 | **Strategy definition format** | strategy_engine evaluator, strategy/ module, all compute | Yes — current Rust evaluator constrains what's representable | `/bmad-technical-research` — DSL vs config vs template, how the current evaluator works, what needs to change |
| 2 | **Optimization methodology** | optimizer crate | Yes — current 5-stage model is the starting point | `/bmad-technical-research` — MAP-Elites, Bayesian, genetic, hybrid. Evaluate against current staged approach |
| 3 | **Execution cost modeling** | cost_model crate, backtester per-trade costs | No — baseline has no cost model | `/bmad-domain-research` — broker spreads, tick data distributions, session-aware profiles, slippage research |
| 4 | **Python-Rust IPC** | rust_bridge module | Yes — current invocation pattern exists | `/bmad-technical-research` — PyO3, subprocess+Arrow IPC, shared memory. Benchmark against current approach |
| 5 | **Dashboard framework** | dashboard build | Yes — current stack exists | `/bmad-technical-research` — evaluate current vs alternatives against PRD chart requirements |
| 6 | **Candidate selection** | candidate_compressor in analysis layer | Partially — current optimization produces candidates | `/bmad-domain-research` — statistical filtering, clustering, multi-objective ranking |
| 7 | **Validation gauntlet config** | validator crate configuration | Yes — current validation is strong | `/bmad-domain-research` — window sizing, Monte Carlo params, confidence thresholds. Calibrate against baseline |
| 8 | **Reconciliation methodology** | reconciliation module | No — baseline has no reconciliation | `/bmad-domain-research` — trade-level signal matching, divergence attribution, tolerance bands |
| 9 | **Overfitting detection** | anomaly detector in analysis layer | Partially — current validation has some detection | `/bmad-domain-research` — detection methods, threshold calibration |

**Critical path:** Research topics 1-4 block implementation. Topics 5-9 can proceed in parallel with early implementation stages.

## Epic Sequencing Implications

Based on this mapping, the epic structure should be:

| Epic | Name | Depends On | Key Baseline Leverage |
|---|---|---|---|
| **Epic 0** | Phase 0 Research (topics 1-4, critical path) | Nothing — starts immediately | Baseline code informs research but doesn't block it |
| **Epic 1** | Foundation (config, logging, contracts, project structure) | Nothing — can parallel with Epic 0 | Adapt baseline config patterns |
| **Epic 2** | Data Pipeline + Quality Gates | Epic 1 | **Heavy reuse** — baseline data pipeline is mature |
| **Epic 3** | Strategy Engine + Cost Model (Rust crates) | Epic 0 (research topics 1, 3) | **Wrap** baseline Rust evaluator with new spec interface |
| **Epic 4** | Backtester + Pipeline Orchestrator | Epics 1, 2, 3 | **Wrap** baseline backtest engine |
| **Epic 5** | API Server + Analysis Layer | Epics 1, 4 | **Extend** baseline API |
| **Epic 6** | Operator Skills + Dashboard | Epic 0 (research topic 5), Epic 5 | **Extend** baseline dashboard |
| **Epic 7** | Optimization + Validation | Epic 0 (research topic 2), Epic 4 | **Adapt** baseline — significant rework likely |
| **Epic 8** | Reconciliation + Cost Feedback | Epic 0 (research topic 8), Epic 4 | **Build new** — no baseline |
| **Epic 9** | VPS Deployment + Live Daemon | Epics 4, 8 | **Adapt** baseline live trader + MT5 integration |

**Epics 0 and 1 can run in parallel.** Epic 0 unblocks the research-dependent epics (3, 7, 8). Epic 1 unblocks the foundation-dependent epics (2, 4, 5).

## Key Decisions Captured

1. **Option B selected:** Baseline deep-dive before epic creation (this document).
2. **Wrap-and-extend confirmed** as default per PRD — this mapping shows where that applies and where it doesn't.
3. **Phase 0 research is Epic 0** — first implementation priority, research topics 1-4 on critical path.
4. **The baseline's strengths are in the compute layer** (Rust evaluator, backtest engine, validation) and data pipeline. These get wrapped/adapted, not rewritten.
5. **The baseline's gaps are in operator workflow, reconciliation, and cost modeling.** These are built new.
6. **Next step:** Create formal epics and stories using the [CE] workflow, informed by this mapping.
