# PIR: Story 5-6-advanced-candidate-selection-clustering-diversity — Story 5.6: Advanced Candidate Selection — Clustering & Diversity

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-23
**Type:** Post-Implementation Review (final alignment assessment)

---

## Codex Assessment Summary

Codex rated: Objective Alignment ADEQUATE, Simplification CONCERN, Forward Look CONCERN → REVISIT.

| # | Codex Observation | My Verdict | Reasoning |
|---|---|---|---|
| OA-1 | Reproducibility is strongest part | **AGREE** | Config hashing (`config.py:52`), deterministic seed derivation from `optimization_run_id`, and `test_live_deterministic_reproducibility` assertion confirm AC#8 is met robustly. |
| OA-2 | Artifact completeness is strong | **AGREE** | `crash_safe_write_json` for manifest and viz data, `SELECTING`/`SELECTION_COMPLETE` pipeline stages, upstream refs with SHA-256 hashes — all directly serve FR58/FR59/FR61. |
| OA-3 | Operator confidence only partially served (no evidence pack) | **PARTIALLY DISAGREE** | The architecture explicitly separates concerns: `analysis/evidence_pack.py` assembles evidence packs (FR39), while `selection/` produces decision artifacts. The manifest contains CRITIC weights, gate failure summaries, cluster rationale, and per-candidate `selection_reason` — this is the *input* to an evidence pack, not the pack itself. Building the pack is not this story's responsibility. |
| OA-4 | Fidelity weakness with synthetic fallback curves | **AGREE, but context matters** | When real equity curves are absent, all candidates get identical synthetic metrics. The WARNING log (`orchestrator.py:~340`) is honest, and `n_trials` now correctly uses `total_candidates_tested`. This is an inherent limitation of the current pipeline state — equity curve files from optimization don't exist yet. The implementation is ready for when they do. |
| OA-5 | SELECTING inserted without feature flag | **DISAGREE** | `SCORING_COMPLETE → SELECTING` is AUTOMATIC, meaning the pipeline progresses without operator action. The V1 path (`promote_top_candidates()`) is preserved untouched per Anti-Pattern #6. The orchestrator chooses V1 or advanced based on config. The stage exists in the graph but only triggers if the pipeline reaches it. A feature flag would add complexity for the same effect. |
| S-1 | MAP-Elites built before real behavior inputs exist | **DISAGREE** | AC#5 explicitly requires the MAP-Elites archive. The story spec mandates `trade_frequency, avg_holding_time, win_rate, max_drawdown` as behavior dimensions. Building the machinery now with logged fallback warnings means zero code changes when upstream data matures. This is not overbuild — it's building to spec. |
| S-2 | Equity quality before real equity artifacts | **DISAGREE** | Same reasoning. AC#2 requires five metrics computed per candidate. The fallback is necessary and honest. Deferring would leave the acceptance criterion unmet. |
| S-3 | UMAP viz never computes 2D projection | **AGREE** | `visualization.py` accepts `projection_2d` but the orchestrator never computes it. The fallback (`has_projection: false`) is documented. This is a deferred action item from synthesis, not a simplification failure — UMAP on the hot path was explicitly avoided per Dev Notes anti-pattern #4. |
| S-4 | `funnel_stage` overwritten to "selected" | **AGREE, minor** | Original stage is preserved in `selection_reason` text, which is parseable but not ideal. A structured `original_funnel_stage` field would be cleaner. The synthesis addressed this as a design compromise — acceptable for now, worth tracking. |
| FL-1 | Scoring manifest contract mismatch | **DISAGREE** | `_load_scoring_manifests` handles unknown manifest shapes by returning `None`, triggering the funnel's own DSR evaluation. This is designed graceful degradation, not a broken contract. The synthesis report explicitly rejected this finding (Codex H1) with the same reasoning. |
| FL-2 | Downstream provenance compressed into free text | **PARTIALLY AGREE** | The manifest carries `critic_weights`, `gate_failure_summary`, `funnel_stats`, and per-candidate `topsis_score`/`pareto_rank`/`cluster_id` as structured data. Only the funnel position is in `selection_reason` text. This is adequate but not exemplary. |
| FL-3 | No operator evidence pack for next stories | **DISAGREE** | Architecture places evidence pack assembly at `analysis/evidence_pack.py` (FR39). Selection emits the decision data; the assembler combines it. Story 5.7's E2E proof already consumes selection manifests directly. |
| FL-4 | Universal SELECTING stage insertion | **DISAGREE** | The AUTOMATIC transition means no new operator burden. The V1 path is untouched. This is correct Growth-phase architecture — the stage exists when advanced selection is configured, and is inert otherwise. |

## Objective Alignment
**Rating:** ADEQUATE

**Reproducibility (STRONG):** Config hash embedded in manifest, seed deterministically derived from `optimization_run_id` when not explicit, `test_live_deterministic_reproducibility` verifies identical manifests (excluding timestamp) on rerun. This is the best reproducibility story of any Epic 5 module.

**Artifact completeness (STRONG):** The `SelectionManifest` is the most provenance-rich artifact in the pipeline: upstream refs with file hashes, CRITIC weights, gate failure summary, funnel stats, diversity archive, and per-candidate selection reasons. The executor uses `crash_safe_write_json` for all outputs. Pipeline state correctly includes `SELECTING`/`SELECTION_COMPLETE` with `selection-complete` in `gated_stages`.

**Operator confidence (ADEQUATE):** The manifest is machine-readable JSON with sufficient data for downstream evidence pack assembly. It does not itself constitute an operator-facing evidence pack, but this is architecturally correct — that responsibility belongs to `analysis/evidence_pack.py`. The `selection_reason` field provides human-readable text per candidate.

**Fidelity (CONCERN, mitigated):** When equity curves and trade stats are absent (the current state), metrics are computed from synthetic fallback data. This is honestly logged with WARNING, and the `n_trials` fix ensures DSR uses the correct multiple-testing denominator. The fidelity concern is real but inherent to the pipeline's current maturity — the implementation is ready for real data.

## Simplification
**Rating:** ADEQUATE

The 10-module subsystem (`selection/`) matches the established project pattern (`confidence/`, `validation/`, `optimization/`) and the architecture's explicit D11 file structure update. Each module has a clear single responsibility.

Codex's CONCERN was driven by machinery that runs on fallback data. I disagree this constitutes over-engineering:
- All 9 acceptance criteria explicitly require these capabilities (clustering, 5 quality metrics, 4-stage funnel, MAP-Elites, visualization data)
- Graceful fallbacks are preferable to `NotImplementedError` stubs — they let the pipeline run end-to-end
- The code review caught and fixed 7 real bugs (cluster ID corruption, gate failure double-computation, viz params empty, etc.) — this is a sign of working code, not dead code

One genuine simplification opportunity exists: the UMAP dependency is declared but never invoked in the orchestrator. This could be deferred to a requirements-optional or removed until Story 5.7 dashboard work needs it.

## Forward Look
**Rating:** ADEQUATE

**Output contract serves downstream:** The `SelectionManifest` JSON schema is well-defined with `to_json()`/`from_json()` round-trip support. Story 5.7's E2E proof already consumes this artifact via `context["selection_manifest"]`. The executor returns `StageResult` with `manifest_ref` pointing to the file path.

**Scoring integration is graceful:** The optional `scoring_manifest_path` parameter with `None` fallback means selection works with or without confidence scoring. The funnel's own DSR gate provides equivalent filtering when scoring is absent. This is the right design for a pipeline where stages can run independently.

**Observations for downstream:**
- When real equity curve files exist, the orchestrator's `_compute_quality_metrics` method will pick them up automatically via `equity_curves_dir` — no code changes needed.
- When trade stats (trade_count, avg_holding_time, win_rate) appear in `candidates.arrow`, the `_extract_behavior_data` method will use them instead of defaults — also no code changes.
- The `funnel_stage="selected"` overwrite means downstream consumers must parse `selection_reason` text for original funnel position. If structured provenance becomes important (e.g., for dashboard filtering), adding an `original_funnel_stage` field to `RankedCandidate` is a 3-line change.

## Observations for Future Stories

1. **Equity curve file contract (Epic 6+):** When optimization starts writing per-candidate equity curve files, document the expected path pattern so `SelectionOrchestrator._compute_quality_metrics` can find them. Currently the code scans `equity_curves_dir / f"candidate_{cid}.arrow"` — this convention should be codified in the optimization output contract.

2. **Trade behavior stats in candidates.arrow (Epic 6+):** The MAP-Elites archive becomes genuinely useful when `trade_count`, `avg_holding_time`, `win_rate`, and `max_drawdown` are real columns in the candidates table. Consider adding these as optional columns in the optimization output schema.

3. **UMAP dependency:** `umap-learn` is in `pyproject.toml` but never imported by the orchestrator. Either compute the projection when needed (Story 5.7 dashboard) or make it an optional dependency to avoid unnecessary install overhead.

4. **Evidence pack integration:** When the operator dashboard consumes selection results, it should assemble an evidence pack from the selection manifest rather than expecting the selection stage to produce one. The manifest has all the data; presentation is a separate concern.

5. **Funnel stage provenance:** If operator-facing tools need to filter/sort selected candidates by their original funnel position (pareto vs. pareto_dominated vs. stability), consider adding `original_funnel_stage: str` to the `RankedCandidate` model rather than parsing `selection_reason` text.

## Verdict

**VERDICT: OBSERVE**

The implementation serves the system's core objectives — reproducibility and artifact completeness are strong, the subsystem follows established patterns, and all 9 acceptance criteria are met. The code review found and fixed 7 real bugs with 10 regression tests, and 322 tests pass with zero regressions.

I disagree with Codex's REVISIT verdict. Codex's concerns fall into two categories:
1. **Inherent pipeline immaturity** (no real equity curves, no trade stats, scoring manifest shape uncertainty) — these are upstream data gaps, not implementation failures. The graceful fallbacks with honest warnings are the correct engineering response.
2. **Architectural separation of concerns** (no evidence pack, no UMAP projection) — these are responsibilities of other components (`analysis/evidence_pack.py`, Story 5.7 dashboard) per the architecture document.

The observations worth tracking are: (a) UMAP dependency declared but unused, (b) `funnel_stage` overwrite losing structured provenance, and (c) ensuring upstream contracts evolve to provide the data selection is ready to consume. None of these rise to REVISIT level — they are natural Growth-phase maturation items.
