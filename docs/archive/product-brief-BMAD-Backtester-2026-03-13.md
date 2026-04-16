---
stepsCompleted: [1, 2, 3, 4, 5, 6]
status: complete
version: 2
supersedes: _bmad-output/planning-artifacts/product-brief-BMAD-Backtester-2026-03-12.md
inputDocuments:
  - _bmad-output/planning-artifacts/product-brief-BMAD-Backtester-2026-03-12.md
  - _bmad-output/planning-artifacts/research/technical-backtester-optimization-strategy-research-2026-03-02.md
  - Research/hardware-optimization-playbook.md
  - Research/deep-research-report.md
  - Research/memory_architecture_brief.md
  - docs/index.md
  - docs/project-overview.md
  - docs/architecture.md
  - docs/technology-stack.md
  - docs/data-models.md
  - docs/api-contracts.md
  - docs/component-inventory.md
  - docs/development-guide.md
  - docs/source-tree-analysis.md
date: 2026-03-13
author: ROG
---

# Product Brief: BMAD Backtester

## Executive Summary

BMAD Backtester is a trading-system operating platform for ROG. It is intended to take a strategy from defined idea through backtest, optimization, validation, practice deployment, reconciliation, and controlled live promotion without requiring manual coding.

This is not a greenfield replacement of a nonexistent baseline. ClaudeBackTester already contains substantial engine capability: data handling, backtesting, staged optimization, validation, live trading, MT5 integration, risk controls, and monitoring. The BMAD effort exists to turn that baseline into a more trustworthy, operator-led, artifact-driven system.

V1 focuses on a narrow, demonstrable slice: one strategy specification path, one pair/timeframe path, one practice deployment route, one reconciliation flow, and one go/no-go promotion gate. Success is measured first by reproducibility, evidence quality, and bounded backtest-to-live divergence. Profitability remains the business goal, but it is not the product acceptance criterion for V1.

---

## Core Vision

### Problem Statement

The current trading stack has real technical depth but weak product coherence. Important capabilities exist, yet they are difficult to operate confidently as a non-developer because the workflow is fragmented, evidence is spread across tools, and the path from idea to live decision is not governed by explicit artifacts and approval gates.

The core problem is not "build a faster backtester." The core problem is "build a trustworthy operating system around a trading engine so ROG can move from hypothesis to live decision with clear evidence, reproducible runs, and controlled risk."

### Problem Impact

- Operator confidence is low because the system does not make it easy to distinguish verified facts, open assumptions, and pending decisions.
- Strong engine capabilities are underused because workflow orchestration and evidence presentation lag the computational core.
- Planning drift occurs because baseline capabilities, actual gaps, and design priorities are not separated into durable artifacts.
- Non-coder operation is unreliable unless AI outputs are converted into deterministic, reviewable artifacts instead of chat-only decisions.
- Architecture work risks going sideways until strategy representation and fidelity measurement are treated as first-class design problems.

### Why Existing Solutions Fall Short

The reference system, ClaudeBackTester, solves substantial parts of the technical problem. It already provides:

- data acquisition and preparation,
- a backtest engine,
- staged optimization,
- a multi-stage validation pipeline,
- live trading via MT5,
- pre-trade risk controls, and
- monitoring interfaces.

What it does not yet provide well enough for BMAD goals is:

- an operator-first workflow,
- a deterministic strategy authoring path,
- a reconciliation layer that explains backtest/live divergence,
- a clear approval model for practice-to-live promotion,
- portfolio-level coordination,
- investor-grade reporting, and
- a planning artifact chain that supports BMAD progression.

External tools also fall short because they tend to optimize either for raw backtesting or for retail trading convenience, not for evidence quality, reproducibility, and AI-assisted operation.

### Proposed Solution

BMAD Backtester will be a layered system with four responsibilities:

1. Strategy definition
Convert human intent into a constrained, versioned strategy specification that can be tested, reviewed, and executed reproducibly.

2. Research and validation execution
Run backtest, optimization, and validation against controlled data and configuration, producing durable stage artifacts.

3. Operator review and decision support
Present the evidence needed for ROG to accept, reject, refine, or promote a strategy.

4. Practice and live operations
Deploy approved strategies to MT5, reconcile expected versus actual behavior, and enforce controlled promotion to live capital.

The product will be built around a fidelity contract:

- same strategy specification,
- same data assumptions,
- same execution semantics where possible,
- explicit tolerance bands where live markets differ, and
- explicit attribution when outcomes diverge.

### Product Principles

- Reuse validated baseline capability before replacing it.
- Prefer explicit artifacts over chat-only state.
- Separate facts, hypotheses, decisions, and deferred questions.
- Optimize for operator clarity before feature breadth.
- Treat reconciliation as a core product feature, not a post-hoc report.
- Keep V1 narrow enough to prove trust before expanding scope.

### Key Differentiators

- Baseline-first rebuild rather than wholesale reinvention.
- Operator-first design for a non-coder decision maker.
- Fidelity measured as a contract with tolerances and attribution.
- BMAD-compatible artifact flow from brief to PRD to architecture to implementation.
- Clear stage outputs for both human review and AI workflow continuity.

---

## Target Users

### Primary Users

**ROG - Operator and decision maker**

ROG is the primary user and the product is optimized around his workflow. He understands market mechanics, capital allocation, and trade-offs, but he does not want to operate the system by writing or modifying code.

ROG needs to be able to:

- define the trading intent or research direction,
- review evidence packs from each stage,
- understand whether a strategy is robust enough for practice or live deployment,
- compare expected versus actual behavior after deployment, and
- make capital allocation decisions with an audit trail.

Success for ROG means the system behaves like a disciplined research and deployment operating environment, not like an opaque automation black box.

### Secondary Users

**Investors and external reviewers**

These users do not operate the platform directly. They consume reports, evidence, and performance summaries that demonstrate process quality, validation discipline, and live track record.

**AI delivery agents inside the BMAD workflow**

These are not customer users, but they are operational users of the artifact chain. The product brief, future PRD, and architecture must be structured so AI agents can act consistently without inventing missing decisions.

### User Journey

1. ROG defines a strategy intent or research hypothesis.
2. The system translates that intent into a constrained strategy specification.
3. The system runs backtest, optimization, and validation and produces a review pack.
4. ROG reviews results and either rejects, refines, or approves the candidate for practice deployment.
5. The system deploys to practice via MT5 and begins reconciliation.
6. ROG reviews reconciliation evidence and decides whether to refine further or promote to live.
7. The system monitors live performance and flags drift, rule violations, or retirement conditions.

The "aha" moment is not just seeing a good equity curve. It is seeing a complete chain of evidence from idea to practice deployment with outcomes that are explainable and reproducible.

---

## Success Metrics

### User and System Success

The product is successful when it gives the operator trustworthy control, not merely faster computation.

Initial success metrics for V1:

- Reproducibility: the same strategy specification, dataset, and configuration reproduce materially identical results within defined tolerance.
- Artifact completeness: every stage emits a saved, reviewable artifact and audit trail.
- Operator independence: ROG can drive the full V1 workflow without manual code changes.
- Recovery and resilience: interrupted runs resume from checkpoint without data loss.
- Evidence quality: each candidate can be reviewed through one coherent evidence pack rather than multiple disconnected outputs.

### Business Objectives

The short-term business objective is to establish a trustworthy process, not to claim broad platform completeness.

Milestones:

1. Establish a verified baseline view of ClaudeBackTester capabilities and gaps.
2. Deliver one end-to-end V1 slice from strategy specification to practice reconciliation.
3. Demonstrate that the reconciliation layer can explain divergence rather than merely report it.
4. Use that slice to inform a stronger PRD and architecture document.
5. Expand only after the operator workflow and fidelity model are proven.

### Key Performance Indicators

The following KPIs are intended to guide PRD and architecture work:

| KPI | Definition |
|---|---|
| Reproducible run rate | Percentage of reruns that stay within agreed metric tolerance using identical inputs |
| Stage artifact completion rate | Percentage of pipeline stages that emit required saved outputs and metadata |
| Practice reconciliation match rate | Percentage of practice trades and signals that can be matched and explained against system expectations |
| Unexplained divergence rate | Percentage of trade or metric divergence not attributable to known categories |
| Operator decision turnaround | Time from completed run to accept, reject, or refine decision |
| Manual intervention count | Number of times the operator must leave the guided workflow or edit code manually |
| Practice promotion readiness rate | Percentage of candidates that produce complete evidence packs for go/no-go review |

---

## MVP Scope

### Core Features

V1 includes only the features required to prove a trustworthy end-to-end slice:

- constrained strategy specification path for at least one strategy family,
- backtest, optimization, and validation flow built on the verified baseline engine concepts,
- review pack covering metrics, charts, validation summary, and decision-ready narrative,
- practice deployment path through MT5 as execution gateway,
- reconciliation flow that compares expected versus actual behavior and records divergence reasons,
- explicit go/no-go promotion gate from practice to live, and
- audit trail and saved artifacts for every major stage.

### Out of Scope for MVP

The following items are explicitly deferred:

- broad autonomous strategy discovery,
- portfolio allocation and correlation management,
- investor reporting,
- automated retirement and re-optimization,
- full multi-strategy concurrency,
- unrestricted AI code generation, and
- support for every possible strategy representation.

### MVP Success Criteria

The MVP is successful when:

- one strategy family on one pair/timeframe can move from hypothesis to practice deployment without manual coding,
- every stage output is persisted and reviewable,
- reconciliation can explain most observed divergence through known categories,
- the operator can make a confident accept, reject, or refine decision from the evidence pack, and
- the product produces enough clarity to support PRD and architecture with fewer open ambiguities.

### Future Vision

After V1 proves trust and workflow coherence, the platform can expand into:

- additional strategy families and representations,
- portfolio-level orchestration,
- automated research assistance,
- investor-grade reporting,
- retirement and re-optimization loops, and
- broader multi-strategy live operations.

The long-term vision remains an end-to-end trading operating platform. The near-term product goal is to make the first trustworthy slice indisputable.

### Inputs to Next BMAD Stage

This brief should be treated as the source of truth for the next BMAD artifacts.

**Locked by this brief**

- The project is a baseline-first rebuild, not a blank-sheet reinvention.
- V1 is a narrow trust slice, not the full 23-step future platform.
- MT5 is the execution gateway for practice and live operation.
- Practice deployment and reconciliation are mandatory before live promotion.
- Artifact quality and operator clarity are core product concerns.

**Open for PRD and architecture**

- strategy representation model,
- artifact schemas and stage contracts,
- reconciliation taxonomy and tolerance bands,
- exact subsystem keep-versus-replace boundaries, and
- final technology and deployment decisions within the known project constraints.
