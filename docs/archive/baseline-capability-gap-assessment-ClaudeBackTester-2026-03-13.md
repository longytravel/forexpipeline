---
status: complete
date: 2026-03-13
author: Codex
sourceSystem: C:/Users/ROG/Projects/ClaudeBackTester
inputDocuments:
  - docs/index.md
  - docs/project-overview.md
  - docs/architecture.md
  - docs/technology-stack.md
  - docs/api-contracts.md
  - docs/component-inventory.md
  - docs/development-guide.md
  - docs/source-tree-analysis.md
---

# Baseline Capability and Gap Assessment: ClaudeBackTester

## Executive Summary

ClaudeBackTester should be treated as a verified baseline with meaningful reusable capability, not as an empty or failed predecessor. The documented system already includes core data, backtest, optimization, validation, live trading, MT5 integration, risk management, dashboarding, scripts, and test coverage.

The BMAD redesign should therefore focus on operational coherence, deterministic strategy specification, reconciliation, operator workflow, and selective subsystem replacement. A wholesale rewrite would discard useful assets and obscure the real design problem.

## Verified Baseline Capabilities

### Core trading and research engine

- Historical data acquisition, validation, splitting, and timeframe conversion are documented as implemented.
- A backtest engine exists with Rust-backed batch evaluation and staged optimization.
- Validation includes walk-forward, CPCV, stability, Monte Carlo, regime analysis, and confidence scoring.

### Live operations

- A live trader exists with MT5 integration, position management, state persistence, and risk gates.
- Operational scripts exist for deployment, start, stop, status, and bulk execution.
- A dashboard stack exists for optimization monitoring and result visualization.

### Quality and maintainability signals

- The documented codebase reports 533 tests across 24 test files.
- The system exposes clear module boundaries for data, strategies, optimizer, pipeline, live trading, broker, and risk.
- Existing documentation is strong enough to support structured reuse decisions.

## Verified Gaps and Weaknesses

### Product and operator workflow gaps

- The current system is still developer-operated in practice.
- There is no documented deterministic path from human trading intent to constrained executable strategy specification.
- There is no single operator workflow that produces a durable artifact chain from idea through promotion decision.

### Trust and fidelity gaps

- The reference docs do not show a first-class reconciliation subsystem that explains backtest-versus-practice divergence.
- The system documents live capability but not a clear promotion model from practice evidence to live approval.
- Fidelity appears to be an important goal, but it is not yet documented as a contract with explicit tolerances and attribution categories.

### Coverage gaps

- `config/`, `notifications/`, `verification/`, `reporting/`, and `research/` are documented as stubs.
- Portfolio-level orchestration and investor reporting are not part of the documented implemented system.
- Some user-facing areas are still placeholders, such as run history in the dashboard.

### Architectural constraints to manage

- The optimizer is documented as a fixed five-stage model today.
- The codebase is a multi-technology monolith, which raises the cost of broad replacement.
- Existing performance and hardware assumptions are strong enough that architecture work should treat them as constraints unless explicitly reopened.

## Reuse Direction

| Area | Direction | Notes |
|---|---|---|
| Data pipeline | Keep and adapt | Already documented as mature enough to serve V1 |
| Backtest engine | Keep | Core technical asset |
| Rust evaluation layer | Keep | Important performance baseline |
| Validation pipeline | Keep and adapt | Strong differentiator worth preserving |
| Live trader and MT5 integration | Keep and adapt | Useful baseline, but needs reconciliation and promotion gating around it |
| Risk manager | Keep | Already aligned with trust-first goals |
| Dashboard and result views | Extend | Good starting point for operator evidence packs |
| Strategy authoring model | Replace or add new layer | Major unresolved gap |
| Reconciliation subsystem | Build new | Core missing feature for BMAD goal |
| Portfolio manager | Defer | Explicitly outside V1 |
| Investor reporting | Defer | Valuable later, not V1-critical |

## Implications for PRD

The PRD should not describe BMAD Backtester as a broad greenfield platform. It should describe:

- the verified baseline capabilities already present,
- the operator and trust problems still unsolved,
- the V1 trust slice to be delivered first, and
- the explicit boundaries between V1 and future phases.

The PRD should also treat "no manual coding" as an operator experience requirement rather than a claim that all logic is created magically by AI.

## Implications for Architecture

Architecture work should start from five questions:

1. What is the strategy representation model for V1?
2. What artifacts must each stage emit, and in what schema?
3. How is reconciliation defined at trade, signal, and aggregate levels?
4. Which baseline subsystems are wrapped versus rewritten?
5. What tolerance bands define acceptable practice-versus-backtest divergence?

If those questions are answered well, the rest of the architecture becomes much easier to sequence.

## Recommended Use of This Document

Use this file alongside the V2 product brief as an input to:

- PRD creation,
- architecture creation,
- epics and story planning, and
- future BMAD implementation readiness checks.
