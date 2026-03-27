# Story 5-5-confidence-scoring-evidence-packs: Story 5.5: Confidence Scoring & Evidence Packs — Codex PIR

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-23
**Type:** Post-Implementation Review (alignment analysis)

---

**1. Objective Alignment**

Assessment: `ADEQUATE`

Specific evidence:
- [prd.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L509), [prd.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L517), [prd.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L551), [prd.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L554) define the target: confidence scoring, evidence packs, versioned artifacts, deterministic behavior.
- [scorer.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/scorer.py#L177), [gates.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/gates.py#L12), [evidence_builder.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/evidence_builder.py#L80), [narrative_engine.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/narrative_engine.py#L12) give deterministic scoring, explicit gates, threshold snapshots, config hashing, and cited narrative output.
- [orchestrator.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/orchestrator.py#L72), [evidence_builder.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/evidence_builder.py#L154), [executor.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/executor.py#L124), [pipeline_state.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/pipeline_state.py#L114) show saved artifacts for every candidate, append-only review files, and state-machine integration.
- [scorer.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/scorer.py#L210), [anomaly_layer.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/anomaly_layer.py#L76), [orchestrator.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/orchestrator.py#L189), [test_integration.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_confidence/test_integration.py#L224) show that repeat runs keep scores stable but still emit fresh timestamps, so artifact bytes are not strictly reproducible.
- [config.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/config.py#L80), [orchestrator.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/orchestrator.py#L66), [evidence_builder.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/evidence_builder.py#L97) show `anomaly.min_population_size` affects behavior but is excluded from `confidence_config_hash`.
- [operator_actions.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/operator_actions.py#L72), [operator_actions.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/operator_actions.py#L86), [operator_actions.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/operator_actions.py#L301), [operator_actions.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/operator_actions.py#L332), [synthesis report](/C:/Users/ROG/Projects/Forex%20Pipeline/reviews/synthesis/5-5-confidence-scoring-evidence-packs-synthesis-report.md#L57) show the operator path still expects old backtest evidence packs.

Concrete observations:
- This story clearly advances `operator confidence`, `artifact completeness`, and `fidelity` inside the scoring stage itself. The RED/YELLOW/GREEN model, explicit gate outcomes, citations, and triage/full-pack split all help a non-coder understand why a candidate passed or failed.
- It only partially advances `reproducibility`. The numerical scoring path is deterministic, but the persisted artifacts include run-time timestamps and an incomplete config hash, so “same inputs, same outputs” is weaker than the architecture intends.
- The biggest thing working against system objectives is operator workflow: the new evidence exists, but the current `/pipeline` loading path still points at backtest evidence. For V1, that is a real usability gap.
- Scope-wise, this mostly fits V1. The only mild overreach is population-level anomaly scaffolding and extra visualization prep work that V1 does not yet consume.

**2. Simplification**

Assessment: `ADEQUATE`

Specific evidence:
- [visualization.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/visualization.py#L14), [visualization.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/visualization.py#L31), [visualization.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/visualization.py#L49), [visualization.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/visualization.py#L68), [visualization.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/visualization.py#L86), [orchestrator.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/orchestrator.py#L116) show five chart-metadata builders exist, but production code only uses `prepare_all_visualizations`.
- [evidence_builder.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/evidence_builder.py#L132) stores only `per_stage_summaries` as `per_stage_results`, while [models.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/models.py#L217) and [narrative_engine.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/narrative_engine.py#L22) imply a richer citation/evidence story.
- [orchestrator.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/orchestrator.py#L73) keeps every `ValidationEvidencePack` in memory anyway, despite its own “persist one candidate at a time” intent at [orchestrator.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/orchestrator.py#L77).
- [anomaly_layer.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/anomaly_layer.py#L295) keeps a V1 placeholder path for population tests that currently only warns.

Concrete observations:
- The core split into `gates`, `scorer`, `narrative`, `builder`, and `executor` is reasonable. I would not collapse that.
- The clearest simplification is the visualization layer. Right now it has more surface area than current consumers need. Either persist the chart metadata it prepares, or remove/defer those helpers until Epic 4 actually reads them.
- A second simplification would be to embed a direct reference to the gauntlet manifest or carry forward the upstream metric/chart refs in the evidence pack, instead of selectively rehydrating pieces across multiple layers.
- None of this looks catastrophically over-engineered, but there is measurable “spec-shaped” code that is not yet serving a live downstream consumer.

**3. Forward Look**

Assessment: `CONCERN`

Specific evidence:
- [story 5.5](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L54), [story 5.5](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L366) require `/pipeline` review flow and Story 5.7 consumability.
- [operator_actions.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/operator_actions.py#L72), [operator_actions.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/operator_actions.py#L86), [operator_actions.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/orchestrator/operator_actions.py#L332) still scan `v*/backtest/evidence_pack.json` and deserialize the old `EvidencePack` model.
- [executor.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/executor.py#L124) defines `record_operator_review`, but [rg evidence](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/executor.py#L124) plus repository usage search show it is not wired into production pipeline actions.
- [orchestrator.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/orchestrator.py#L195) gives downstream consumers candidate IDs, ratings, scores, and file paths, but not enough embedded context to render charts or independently resolve all cited metric IDs from the evidence pack alone.
- [evidence_builder.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/evidence_builder.py#L139), [visualization.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/visualization.py#L105) mean downstream consumers get summaries and raw chart refs, not the prepared chart metadata functions created in this story.
- [anomaly_layer.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/anomaly_layer.py#L50), [anomaly_layer.py](/C:/Users/ROG/Projects/Forex%20Pipeline/src/python/confidence/anomaly_layer.py#L305), [story 5.5](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L300) show a growth assumption: once candidate counts rise, behavior changes, but the population-test path still produces no substantive output.

Concrete observations:
- Internally, the stage sets up the next stories reasonably well: there is a scoring manifest, per-candidate evidence packs, triage summaries, and pipeline-state support for `SCORING_COMPLETE`.
- Externally, it does not yet set up the operator-facing next step correctly. The main review surface still speaks “backtest evidence pack,” not “validation scoring evidence pack.”
- The output contract is also thinner than downstream dashboards/E2E proof are likely to want. The pack should probably carry forward metric-id mappings and chart metadata directly, so later stages do not have to reopen the gauntlet manifest to explain the evidence pack.
- The baked-in assumption that V1 has only 5-10 candidates is fine today, but it means the anomaly layer’s population branch is effectively dead code until it is genuinely implemented.

**OVERALL**

`REVISIT`

The scoring core is aligned, but the story is not fully serving BMAD Backtester’s objectives end-to-end yet. The main reasons are the incomplete `/pipeline` review integration, weaker-than-intended reproducibility provenance, and an output contract that is good for storage but still thin for downstream consumption.
