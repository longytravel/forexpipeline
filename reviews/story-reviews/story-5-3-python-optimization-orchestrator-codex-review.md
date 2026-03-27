# Story 5-3-python-optimization-orchestrator: Story 5.3: Python Optimization Orchestrator — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-22
**Type:** Holistic System Alignment Review

---

## 1. System Alignment
- **Assessment:** CONCERN
- **Evidence:** The story advances reproducibility, artifact persistence, and fold-aware fidelity through checkpoints, Arrow IPC outputs, and CV-inside-objective scoring [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L50) [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L75). It barely advances operator confidence: it promises raw results and logs, while the PRD requires chart-led review and evidence packs at each stage [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L83) [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L497) [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L517).
- **Observations:** This is trying to solve V1 platform proof and Growth-phase optimizer sophistication in one story. CMA-ES + DE + Sobol + branch decomposition + UCB1 is more search-quality ambition than V1 needs, especially when V1 is not gated on profitability. The story also works against simplicity and reproducibility by adding more stochastic moving parts without explicit seed, ordering, or replay guarantees.
- **Recommendation:** Keep the core batch ask/tell loop, fold-aware evaluation, checkpointing, and artifact emission. Make multi-algorithm portfolioing, UCB1 branch allocation, and possibly DE optional or follow-on. Add a minimal operator-facing stage summary artifact so this stage improves confidence, not just throughput.

## 2. PRD Challenge
- **Assessment:** CONCERN
- **Evidence:** The PRD still says strategies define optimization stages and groupings [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L476), while Epic 5’s research update says the optimizer should decide internally and fixed staging is not mandated [epics](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L54). The story follows the research update, not the original PRD wording [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L20). FR25 also requires chart-led visualization [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L497), but this story only guarantees raw Arrow output and top-N promotion [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L75) [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L85).
- **Observations:** The real problems are resumability, deterministic search orchestration, fold-aware scoring, and artifact provenance. The imagined problems are mandatory UCB1 branch budgeting and mandatory multi-optimizer sophistication in MVP. FR13, FR23, and FR24 are not cleanly decomposed anymore.
- **Recommendation:** Update the requirement trace so optimization is framed as “optimizer-owned search structure over strategy-defined parameter ranges/conditionals.” Split FR25 into two concerns: optimization artifact generation here, operator visualization/evidence pack later.

## 3. Architecture Challenge
- **Assessment:** CRITICAL
- **Evidence:** D3 says optimization is opaque to the state machine and should expose a single external `OPTIMIZING` state with optimizer-owned checkpoints [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L291). Task 1 contradicts that by adding `OPTIMIZATION_READY`, `OPTIMIZATION_COMPLETE`, and pipeline checkpoint fields for optimizer internals [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L90) [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L101). D11 expects a reviewable evidence-pack artifact per gate [architecture](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L825), but this story does not define one.
- **Observations:** The chosen topology is right: Python should orchestrate ask/tell and Rust should evaluate via Arrow IPC. The story’s problem is boundary drift. It mixes pipeline-state ownership, optimizer-state ownership, and downstream analysis responsibilities.
- **Recommendation:** Enforce D3 literally. Keep one external `OPTIMIZING` stage. Let the optimizer own its checkpoint file and recovery journal; let pipeline state store only stage, artifact refs, and status summary. Also clean up the architecture text so Python search ownership and any Rust optimizer crate role are unambiguous.

## 4. Story Design
- **Assessment:** CRITICAL
- **Evidence:** The story is too large for a single implementation slice: 13 tasks, multiple contracts/config changes, 9 new modules, and full integration tests [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L90) [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L435). It contains direct contradictions: AC11 says ~5.5GB budget while config defaults to `4096` MB [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L63) [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L114). It forbids accumulating results in memory [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L385) but Task 10 writes `all_candidates: list[dict]` at the end [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L251).
- **Observations:** Several ACs are not verifiable as written: “exploration of unexplored regions,” inverse instance scaling, “presented for operator review,” and absolute memory usage. The biggest missing piece is deterministic correctness under resume: there is no explicit journal/phase model for crashes between `ask`, dispatch, and `tell`, so duplicate or lost evaluations are likely.
- **Recommendation:** Split this into smaller stories. Add explicit ACs for deterministic seeds, stable candidate IDs/order, atomic generation journaling, resume idempotency, and manifest/provenance. Replace absolute resource ACs with budget-preflight and bounded-streaming behavior.

## 5. Downstream Impact
- **Assessment:** CONCERN
- **Evidence:** Story 5.4 expects ranked, deterministic candidates ready for validation [epics](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1251) [epics](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1279). Story 5.5 expects evidence-pack inputs and operator review later, not raw optimization output as the decision point [epics](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1290) [epics](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1313). Story 5.7 expects manifests linking dataset hash, strategy spec version, cost model version, config hash, and validation config [epics](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1384). This story’s result schema does not require most of that provenance [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L251).
- **Observations:** If you ship this as written, downstream stories will need to reverse-engineer run context from filenames and pipeline state. AC15 is also pointed at the wrong consumer: V1 promotion should feed validation, not direct operator go/no-go.
- **Recommendation:** Make the output contract richer now: candidate table, run manifest, fold spec, hashes, RNG seed set, stop reason, stable candidate IDs, and a promoted-candidates artifact explicitly intended for Story 5.4.

## Overall Verdict
VERDICT: REFINE

## Recommended Changes
1. Remove `OPTIMIZATION_READY` and `OPTIMIZATION_COMPLETE` from the story and keep a single external `OPTIMIZING` stage, with optimizer-owned checkpoints only.
2. Split the story into smaller implementation slices: optimizer core, Rust dispatch/fold handling, and results/provenance/pipeline integration.
3. Add acceptance criteria and tasks for deterministic seeds, stable candidate IDs, canonical candidate ordering, and reproducibility tests across rerun and resume.
4. Replace the end-of-run `all_candidates: list[dict]` design with an append/streaming writer plus a crash-safe generation journal.
5. Add a run manifest artifact containing dataset hash, strategy spec version/hash, cost model version/hash, config hash, fold definitions, RNG seeds, stop reason, and branch metadata.
6. Clarify that Story 5.3 produces visualization-ready optimization artifacts; do not claim full FR25 unless the story also emits an optimization stage summary/evidence artifact.
7. Change AC15 so promotion targets validation intake, not direct operator review.
8. Resolve the FR13/FR23/FR24 wording conflict in the story’s dev notes and traceability section.
9. Replace the absolute `~5.5GB peak` AC with a preflight budget contract: reduce batch size/concurrency before start if the planned run does not fit.
10. Make branch decomposition, UCB1 allocation, and secondary optimizers optional or deferred unless research says they are required for MVP proof rather than optimization quality.
