# PIR: Story 5-5-confidence-scoring-evidence-packs — Story 5.5: Confidence Scoring & Evidence Packs

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-23
**Type:** Post-Implementation Review (final alignment assessment)

---

## Codex Assessment Summary

Codex rated Objective Alignment as ADEQUATE, Simplification as ADEQUATE, Forward Look as CONCERN, and gave an overall verdict of REVISIT. Key observations:

| # | Codex Observation | My Assessment |
|---|---|---|
| 1 | Story advances operator confidence, artifact completeness, and fidelity but only partially advances reproducibility due to incomplete config hash and runtime timestamps | **AGREE** — The `confidence_config_hash` is present in the decision trace but does not include `anomaly.min_population_size`. However, this is a minor gap: the scoring path itself is fully deterministic, and the config hash covers all scoring-affecting parameters (gates, weights, thresholds). The anomaly config omission is real but low-impact since population tests are effectively no-ops in V1. The runtime timestamps are metadata, not scoring inputs — they don't break "same inputs → same outputs." |
| 2 | `/pipeline` review path still points at backtest evidence, creating a usability gap | **AGREE** — This is the most significant gap. The synthesis report confirms the `/pipeline` skill edit was denied by user permissions and remains a deferred action item. However, this is a *skill integration* issue, not a *story implementation* issue. The `record_operator_review` function exists and works; the wiring is the gap. |
| 3 | Visualization layer has more surface area than current consumers need | **PARTIALLY DISAGREE** — The visualization module was explicitly required by AC11 (equity curves, walk-forward results, parameter heatmaps, Monte Carlo plots, regime breakdowns). The five `prepare_*` functions map 1:1 to the acceptance criteria. The fact that no downstream consumer renders them yet is expected — this story *prepares* the data; Epic 4 (dashboard) *renders* it. The code is spec-shaped but not over-engineered. |
| 4 | Population-level anomaly tests are effectively dead code for V1 | **AGREE** — The `min_population_size=20` threshold means V1's 5-10 candidates never trigger population tests. However, the spec explicitly required this gating behavior (Task 5: "only run when `len(candidates) >= min_population_size`; skipped with info log otherwise"). The implementation correctly defers rather than stubbing — a single `logger.info` warning when skipped. This is reasonable scaffolding, not bloat. |
| 5 | Output contract is good for storage but thin for downstream consumption — metric IDs not independently resolvable from evidence pack alone | **PARTIALLY AGREE** — The evidence pack carries `per_stage_results`, `visualization_refs`, `narrative`, and `decision_trace`. It's true that a downstream consumer would need the gauntlet manifest to resolve every cited `[metric:...]` ID to its source data. But Story 5.7 (E2E Proof) will inherently have access to the full artifact tree. Embedding all metric source data would duplicate the gauntlet manifest. The reference-based approach is the right architectural call per D2 (don't copy Arrow IPC data). |
| 6 | Orchestrator keeps all packs in memory despite "persist immediately" intent | **AGREE, LOW IMPACT** — Lines 73-86 of `orchestrator.py` do `evidence_packs.append(pack)` after persisting, keeping them in memory for the aggregate manifest. For V1's 5-10 candidates with lightweight JSON packs, this is negligible. A streaming approach would be premature optimization. |
| 7 | Codex overall verdict: REVISIT | **DISAGREE** — see Verdict below |

## Objective Alignment
**Rating:** STRONG

The implementation directly serves all four system objectives:

- **Operator confidence:** RED/YELLOW/GREEN rating system with explicit gate outcomes, one-line interpretations per component, triage summary cards (≤10 fields, ≤3 risks, ≤200 words), and full evidence packs give the operator a clear decision interface. This is the first story that delivers the PRD's vision of "coherent evidence pack at each stage" (FR39) for the scoring layer.

- **Artifact completeness:** Every scoring artifact is persisted via `crash_safe_write_json` (.partial → fsync → os.replace per D2/NFR15). The aggregate manifest, per-candidate evidence packs, triage summaries, and operator reviews form a complete audit trail. The `DecisionTrace` captures config hashes, gate thresholds, and research brief versions — this is proper provenance.

- **Reproducibility:** The scoring pipeline is fully deterministic: no LLM calls, no stochastic components, template-driven narratives (D11). The `ConfidenceConfig` is loaded from TOML with weight-sum validation. The minor `anomaly.min_population_size` hash omission doesn't affect scoring reproducibility since population tests only produce info-level logs when skipped.

- **Fidelity:** The hard gate evaluator correctly implements the research-determined formula (DSR pass, PBO ≤ 0.40, cost stress at 1.5x multiplier). The 6-component weighted scorer matches the spec exactly. Short-circuited candidates correctly receive RED with "stage skipped" documentation (fixed in synthesis pass 2).

The `/pipeline` skill integration gap is real but doesn't work against objectives — it's a wiring issue that sits between this story's outputs and the operator's review workflow. The story correctly produces the artifacts; the skill needs updating to consume them.

## Simplification
**Rating:** STRONG

The module decomposition is clean and well-motivated:

- `gates.py` → hard gate evaluation (3 gates, pure functions)
- `scorer.py` → weighted composite scoring (6 components, deterministic)
- `anomaly_layer.py` → two-tier anomaly detection (5 per-candidate detectors + gated population tests)
- `narrative_engine.py` → template-driven narrative with metric citations
- `evidence_builder.py` → two-pass pack assembly (triage + full) with crash-safe persistence
- `visualization.py` → chart metadata preparation (5 chart types per AC11)
- `orchestrator.py` → sequential candidate processing with incremental persistence
- `executor.py` → StageExecutor protocol integration + operator review recording
- `config.py` → TOML config loading with frozen dataclasses and validation
- `models.py` → 10 dataclasses with JSON round-trip serialization

Each module has a single responsibility. No unnecessary abstractions. The orchestrator processes sequentially (appropriate for lightweight CPU work — no Rust dispatch needed). The config uses frozen dataclasses with `__post_init__` validation — no framework overhead.

I see no clear simplification opportunities. The visualization helpers Codex flagged are required by AC11 and are simple dict-returning functions, not a framework. The anomaly layer's population gating is 3 lines of code (a length check and a log message) — removing it would save nothing while losing the Growth path.

## Forward Look
**Rating:** ADEQUATE

**What works well for downstream:**
- The scoring manifest at `scoring-manifest.json` provides candidate IDs, ratings, composite scores, hard gate pass/fail, and file paths — sufficient for Story 5.7 (E2E Proof) to locate and present results.
- `PipelineStage.SCORING` and `SCORING_COMPLETE` are registered in the state machine with proper transitions (VALIDATION_COMPLETE → SCORING automatic, SCORING → SCORING_COMPLETE gated).
- The `ConfidenceExecutor` implements the `StageExecutor` protocol correctly with `execute()` returning `StageResult` and `validate_artifact()` checking manifest integrity.
- Operator review is properly separated as append-only artifacts that don't mutate immutable evidence packs (AC8).

**What needs attention:**
- **`/pipeline` skill wiring (HIGH):** The synthesis report confirms this was attempted but denied by permissions. Story 5.7 or a follow-up must wire the `/pipeline` review flow to load confidence evidence packs instead of (or in addition to) backtest evidence packs. Without this, the operator cannot exercise their review role through the standard interface.
- **Metric ID resolution (LOW):** Downstream consumers that want to trace a `[metric:walk_forward_oos]` citation back to its source data will need the gauntlet manifest. This is architecturally correct (reference, don't copy) but should be documented in Story 5.7's dev notes as a contract dependency.

## Observations for Future Stories

1. **Story 5.7 must wire `/pipeline` skill to confidence evidence.** The `record_operator_review` function and evidence pack artifacts exist but are unreachable through the operator's standard review workflow. This is the highest-priority integration gap from this story. The synthesis report has a prepared edit that was permission-denied — pick it up.

2. **Anomaly population tests need real implementation before Growth.** The `run_layer_a` population branch (Sharpe distribution shape, parameter clustering, OOS return correlation) currently logs a warning and returns empty. If Growth stories expect population-level anomaly detection, they must implement the actual statistical tests — the scaffolding is necessary but insufficient.

3. **Evidence pack metric-ID resolution contract.** Stories that render evidence pack contents (dashboard, E2E proof) should document that resolving `[metric:...]` citations requires access to the gauntlet manifest referenced by `optimization_run_id`. The evidence pack is self-contained for display but not for deep drill-down.

4. **Config hash completeness.** The `confidence_config_hash` should include `anomaly.min_population_size` for full reproducibility provenance. This is a one-line fix but should be picked up in the next story that touches the confidence module.

5. **Orchestrator memory pattern.** The orchestrator accumulates all evidence packs in a list for the aggregate manifest write. For V1 this is fine. If candidate counts grow significantly (Growth phase), refactor `_write_aggregate_manifest` to build the summary incrementally rather than from the full list.

## Verdict

**VERDICT: ALIGNED**

The scoring core is well-engineered, deterministic, and directly serves all four system objectives. The module decomposition is clean and appropriate. All 11 acceptance criteria are met in the implementation. The 95 tests (including 4 fixture types and 3 live tests) provide strong verification.

Codex's REVISIT verdict was driven primarily by the `/pipeline` skill integration gap and forward-look concerns. I disagree with REVISIT because:

1. The `/pipeline` skill is an *integration surface*, not part of this story's implementation scope. The story correctly produces all artifacts; the skill update was attempted and blocked by permissions. This is a tracked action item, not an alignment failure.
2. The output contract is sufficient for downstream consumption via file paths and manifest references — the architecture explicitly avoids data duplication (D2).
3. The visualization "surface area" concern conflates "not yet consumed" with "unnecessary" — the functions implement explicit acceptance criteria (AC11).

The one observation worth tracking: ensure Story 5.7 or a maintenance pass wires the `/pipeline` review flow to confidence evidence packs before the sprint closes.
