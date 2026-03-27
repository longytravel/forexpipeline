# Story 3-8-operator-pipeline-skills-dialogue-control-stage-management: Story 3.8: Operator Pipeline Skills — Dialogue, Control & Stage Management — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-18
**Type:** Holistic System Alignment Review

---

**1. System Alignment**
- **Assessment:** CONCERN
- **Evidence:** [story 3.8](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-8-operator-pipeline-skills-dialogue-control-stage-management.md#L15), [story 3.8](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-8-operator-pipeline-skills-dialogue-control-stage-management.md#L45), [PRD](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L252), [PRD](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L293), [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L394)
- **Observations:** This story clearly advances operator confidence and artifact completeness, and it partially helps reproducibility via status, resume, and logging. It barely advances fidelity, and it works against operator confidence by reducing review to CLI text even though MVP requires chart-led visual review. It also drifts beyond V1 by scanning “all strategies” before the architecture’s cross-strategy registry exists.
- **Recommendation:** Keep the conversational control surface, but scope V1 to explicit strategy/candidate control and make review output point to artifact lineage plus dashboard/chart links, not only formatted text.

**2. PRD Challenge**
- **Assessment:** CONCERN
- **Evidence:** [PRD](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L516), [PRD](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L551), [PRD](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L558), [story 3.8](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-8-operator-pipeline-skills-dialogue-control-stage-management.md#L63), [story 3.8](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-8-operator-pipeline-skills-dialogue-control-stage-management.md#L71)
- **Observations:** FR38-FR42 are the right capabilities, but the story maps them too narrowly. It over-specifies implementation details the operator does not care about (menu numbering, single-menu requirement, direct Python snippets), while under-specifying what the operator does care about: “what passed, what failed, and why,” explicit lineage, and visual evidence. `run_backtest()` also pulls inputs from `artifacts/` by convention rather than explicit refs, which is weak against FR59-FR61.
- **Recommendation:** Rewrite the story around operator outcomes and reproducibility contracts: explicit input refs, explanatory status, evidence provenance, and reviewable visuals. Treat skill menu structure as a UX choice, not a requirement.

**3. Architecture Challenge**
- **Assessment:** CRITICAL
- **Evidence:** [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L571), [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L595), [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L807), [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L2135), [story 3.8](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-8-operator-pipeline-skills-dialogue-control-stage-management.md#L114), [story 3.8](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-8-operator-pipeline-skills-dialogue-control-stage-management.md#L387)
- **Observations:** The story cites D9 while implementing the opposite of D9. Architecture says skills use REST API for data/mutations and analysis endpoints, with direct file reads only for status/artifact review; this story bans REST, invokes Python directly, and collapses everything into one `/pipeline` menu. That creates a duplicate control path the dashboard/API will have to replace later.
- **Recommendation:** Change the story to use a single orchestrator/API-backed mutation surface now. If you want one `/pipeline` entrypoint for UX, fine, but do not encode “no REST API” or “single skill only” as architecture rules.

**4. Story Design**
- **Assessment:** CONCERN
- **Evidence:** [story 3.8](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-8-operator-pipeline-skills-dialogue-control-stage-management.md#L25), [story 3.8](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-8-operator-pipeline-skills-dialogue-control-stage-management.md#L64), [story 3.8](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-8-operator-pipeline-skills-dialogue-control-stage-management.md#L107), [epics](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md#L1052)
- **Observations:** The ACs are only partly verifiable. The story prompts `accept/reject/refine` but only implements accept/reject; `refine` is not persisted as a `GateDecision`. It resolves evidence by “latest version on disk,” which is unsafe for reproducibility. The evidence-pack artifact name is inconsistent with Epic 3.7 (`narrative.json` there, `evidence_pack.json` here). The FR41 test is a grep-based proxy that can miss real gating logic and fail on harmless display code.
- **Recommendation:** Add an explicit refine path or remove refine from the prompt, make evidence selection state-driven rather than “latest,” align the artifact contract, and replace grep tests with behavior tests using losing strategies.

**5. Downstream Impact**
- **Assessment:** CONCERN
- **Evidence:** [epics](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md#L1104), [epics](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md#L1114), [PRD](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L551), [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L394), [story 3.8](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-8-operator-pipeline-skills-dialogue-control-stage-management.md#L62)
- **Observations:** Story 3.9 needs manifest-linked, reproducible runs; this story currently relies on artifact discovery and “latest” selection instead of explicit lineage. As the pipeline grows, filesystem scans and implicit latest-version rules will become technical debt fast. Missing now: stable `run_id`/`config_hash`/artifact refs in operator actions, and dashboard deep links from evidence packs.
- **Recommendation:** Make this story emit the exact downstream contract now: explicit refs in state and logs, deterministic target selection, and chart/deep-link metadata for later dashboard use.

## Overall Verdict
VERDICT: REFINE

## Recommended Changes
1. Replace “no REST API” with “mutations go through the orchestrator/API surface; direct file reads are allowed only for status/artifact display.”
2. Remove the hard requirement that everything must live in one `/pipeline` menu; allow one entrypoint or multiple skills as long as the UX stays coherent.
3. Change `run_backtest()` to require explicit input refs or state-derived refs for strategy spec, dataset, cost model, and config hash; do not load “latest from artifacts.”
4. Change evidence loading and gate decisions to use the `evidence_pack_ref` from pipeline state/manifest, not `v{latest}` discovery.
5. Add full `refine` support end-to-end with persisted `GateDecision(decision="refine")`, or stop prompting for it in this story.
6. Align the evidence-pack artifact contract with Story 3.7 and make one canonical filename/path.
7. Expand status/output requirements to include `last_outcome`, `blocking_reason`, and artifact/deep-link references so FR40 is actually satisfied.
8. Add dashboard/chart references to the evidence pack review flow so CLI control still supports MVP chart-led review.
9. Replace the grep-based FR41 test with behavior tests that prove a losing/anomalous strategy can still be advanced, rejected, or refined.
10. Add integration tests for skill/API/orchestrator/analysis flow, including explicit target selection, idempotent resume, and lineage-preserving logging with `run_id`, `config_hash`, and artifact refs.
