# Story 5-2b-optimization-search-space-schema-range-proposal: Story 5.2b: Optimization Search Space Schema & Intelligent Range Proposal — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-22
**Type:** Holistic System Alignment Review

---

**1. System Alignment**
- **Assessment:** CONCERN
- **Evidence:** [5.2b:8](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L8), [5.2b:30](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L30), [5.2b:151](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L151), [PRD:119](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L119), [PRD:551](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L551), [Architecture:81](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L81)
- **Observations:** The flat registry clearly helps reproducibility and removes the staged-model flaw, but the story barely addresses artifact completeness. It does not require a persisted proposal artifact, input hashes, or per-parameter rationale. It also introduces hardcoded ATR/spread fallbacks, which weakens fidelity and operator confidence. The “40+ parameters / deeply nested branches” target is beyond the minimum V1 proof of one family on one pair/timeframe.
- **Recommendation:** Keep the flat-schema change. Reduce V1 scope to “deterministic search-space declaration + persisted advisory proposal artifact with provenance.” Treat missing data/cost inputs as an explicit review state, not a warning-log fallback.

**2. PRD Challenge**
- **Assessment:** CONCERN
- **Evidence:** [PRD:476](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L476), [PRD:495](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L495), [PRD:496](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L496), [Epics:53](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L53), [Epics:54](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L54), [Epics:1231](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1231)
- **Observations:** The PRD is still internally conflicted. `FR13` and `FR24` talk about strategy-defined stages/groupings, while the research update says the optimizer should own grouping internally and the spec should define ranges and conditionals. The real operator need is not “stages”; it is “declare what is searchable, with safe defaults and explainable provenance.” The story also lacks a requirement for parameter identity, searchable-vs-fixed selection, and proposal evidence.
- **Recommendation:** Rewrite the PRD/epic wording so the spec defines searchable parameters, bounds, and conditional structure, while the optimizer chooses search policy. Add a requirement for proposal provenance and explicit searchable parameter selection.

**3. Architecture Challenge**
- **Assessment:** CONCERN
- **Evidence:** [Architecture:425](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L425), [Architecture:288](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L288), [Architecture:609](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L609), [Architecture:620](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L620), [Architecture:2033](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L2033), [5.2b:203](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L203), [5.2b:231](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L231)
- **Observations:** The story leaks optimizer internals into the schema layer by hard-defining `ParameterSpace` branch decomposition. That cuts against D3’s “optimizer is opaque/pluggable.” It also says the skill should update the spec file directly, while D9 says skills mutate via the API/orchestrator. Finally, Python hardcoded instrument metadata duplicates concerns that already belong in contracts/cost-model artifacts.
- **Recommendation:** Keep D7-aligned contract work in this story, but move `parse_strategy_params()` decomposition and branch-budget policy into Story 5.3. Make skill actions go through the orchestrator/API and emit artifacts. Source pip/spread metadata from contracts or artifacts, not code literals.

**4. Story Design**
- **Assessment:** CRITICAL
- **Evidence:** [5.2b:28](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L28), [5.2b:40](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L40), [5.2b:45](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L45), [5.2b:139](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L139), [5.2b:151](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L151), [5.2b:300](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L300), [5.2b:336](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L336)
- **Observations:** Several ACs are not testable as written: “sensible,” “pair-appropriate,” and “operator can review” are vague. The story also contradicts itself: it says not to hardcode ranges, then defines hardcoded pair lists, default ATR values, timeframe tables, and exact v002 ranges. It bundles schema migration, semantic validation, heuristics, reference migration, downstream contract design, and operator UX into one implementation unit. Legacy handling is also weak: “raise a clear error” is not enough for historical artifact reviewability.
- **Recommendation:** Split this into two stories: `schema/migration/validation` and `proposal/provenance/operator-review`. Replace subjective ACs with deterministic rules and saved outputs. Add explicit schema versioning or a read-only migration path for legacy specs.

**5. Downstream Impact**
- **Assessment:** CRITICAL
- **Evidence:** [5.2b:103](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L103), [5.2b:117](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L117), [5.2b:223](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L223), [5.2b:311](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-2b-optimization-search-space-schema-range-proposal.md#L311), [Epics:1248](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1248), [Epics:1274](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1274)
- **Observations:** The flat `dict[str, SearchParameter]` has no canonical parameter ID scheme, so repeated names across entry rules, exits, and filters will collide later. The proposed `branches[(categorical, choice)]` shape is too weak if a strategy has multiple independent top-level categoricals; that will force a 5.3 rewrite. The proposal output also lacks the provenance 5.3 and later evidence packs will need: dataset hash, config hash, indicator-registry version, spread source, and override history.
- **Recommendation:** Add canonical parameter paths/IDs now. Do not freeze a too-simple `ParameterSpace` contract in this story. Require the proposal output to persist provenance and operator overrides as first-class artifacts.

## Overall Verdict
VERDICT: REFINE

## Recommended Changes
1. Rewrite the story goal so the primary deliverable is a flat, deterministic search-space contract; make intelligent range proposal a separate advisory artifact.
2. Update the story’s FR mapping to resolve the `FR13`/`FR24` contradiction and align with the research update in [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L53).
3. Add an acceptance criterion for a persisted `optimization_space_proposal` artifact containing dataset hash, config hash, indicator-registry version, spread/cost-model source, proposal-engine version, and per-parameter rationale.
4. Add a canonical parameter ID/path scheme such as `entry.fast_ma.period` or `exit.trailing.atr_multiplier`; stop using bare names as the only key.
5. Add an explicit mechanism to mark parameters as searchable vs fixed; do not infer “optimize everything extractable.”
6. Remove hardcoded ATR/spread defaults from the acceptance contract, or demote them to an explicit provisional mode that is surfaced to the operator and saved in the artifact.
7. Move `parse_strategy_params()` branch decomposition and UCB1/budget allocation details into Story 5.3; this story should publish the search-space contract, not the optimizer’s internal representation.
8. Move pipeline command changes into a separate operator-workflow story, or require those commands to call the orchestrator/API and emit artifacts instead of editing spec files directly.
9. Add explicit schema-version or migration handling so legacy `v001` specs remain reviewable without undermining the single canonical runtime model.
