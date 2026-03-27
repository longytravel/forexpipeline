# Story 5-6-advanced-candidate-selection-clustering-diversity: Story 5.6: Advanced Candidate Selection — Clustering & Diversity — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-23
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

**HIGH Findings**
- Real scoring-manifest integration is broken. `SelectionOrchestrator` loads aggregate scoring entries unchanged, but `four_stage_funnel()` expects per-candidate `gate_results` and `per_stage_summaries`. With the actual Story 5.5 manifest shape, every candidate will fail DSR or PBO as soon as scoring artifacts are supplied. This is a direct AC3/AC7 integration failure. [orchestrator.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/orchestrator.py#L319) [ranking.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/ranking.py#L252) [confidence/orchestrator.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/confidence/orchestrator.py#L195)
- Cluster assignments and summaries use row positions as candidate IDs. `cluster_candidates()` writes `candidate_id=i`, and `compute_cluster_summaries()` then indexes with `df.iloc[members]` and stores `best_idx` as the representative ID. After prefiltering/deduplication or with non-contiguous IDs, cluster membership, representatives, and downstream selection all point at the wrong candidate. [clustering.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/clustering.py#L127) [clustering.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/clustering.py#L153) [clustering.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/clustering.py#L210)
- Equity-curve quality is not computed from real artifacts reliably. If no equity file exists, the code silently substitutes the same hard-coded toy equity curve for every candidate, and it computes DSR with `n_trials` equal to the filtered candidate count after prefilter/dedup rather than the optimization trial count. That makes AC2 materially inaccurate and weakens hard-gate decisions. [orchestrator.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/orchestrator.py#L83) [orchestrator.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/orchestrator.py#L287)
- The four-stage funnel does not match the story. In fallback mode it only applies DSR and skips PBO/cost-stress gates; Stage 4 uses `k_ratio` instead of `diversity_distance`; and it returns all stable candidates with Pareto ranks instead of extracting the frontier survivors. AC3 is not actually implemented as specified. [ranking.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/ranking.py#L268) [ranking.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/ranking.py#L395) [ranking.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/ranking.py#L417)
- Visualization data is largely placeholder output. `_prepare_viz_data()` passes empty parameter maps into parallel coordinates, and cluster membership never computes UMAP; it falls back to `x=i, y=0`. That does not satisfy AC6’s requirement for meaningful parallel coordinates and cluster membership plots. [orchestrator.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/orchestrator.py#L396) [visualization.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/visualization.py#L30) [visualization.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/visualization.py#L112)
- Selected manifest entries lose their funnel provenance. Diversity selection rebuilds each `RankedCandidate` with `funnel_stage="selected"`, so the final output no longer tells the operator where each candidate sat in the funnel, contrary to AC7. [diversity.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/diversity.py#L193) [diversity.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/diversity.py#L242) [diversity.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/diversity.py#L265)

**MEDIUM Findings**
- The MAP-Elites archive is often built from placeholder behavior values, not real trade behavior. When the candidate table lacks trade stats, three of the four dimensions default to constants, so AC5’s “behavioral diversity” is largely synthetic. [orchestrator.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/orchestrator.py#L386) [diversity.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/diversity.py#L99)
- Gate-failure counts are computed in `four_stage_funnel()` and then discarded; the manifest summary is recomputed separately and returns all zeros when no scoring manifest is present. That loses real filtering information. [ranking.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/ranking.py#L242) [orchestrator.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/orchestrator.py#L131) [orchestrator.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/orchestrator.py#L343)
- `deterministic_ratio=0.0` still produces one deterministic pick because of `max(1, ...)`. That is an off-by-one/config-semantics bug in the diversity split logic. [diversity.py](/c/Users/ROG/Projects/Forex Pipeline/src/python/selection/diversity.py#L158)

**Acceptance Criteria Scorecard**

| AC | Status | Assessment |
|---|---|---|
| 1 | Partially Met | Gower + HDBSCAN are implemented, but assignment/summarization is index-based rather than candidate-id based. |
| 2 | Partially Met | All five metric functions exist, but pipeline integration fabricates equity curves and under-deflates DSR. |
| 3 | Not Met | Funnel shape exists, but hard gates, Pareto objectives, and frontier extraction do not match the story. |
| 4 | Partially Met | Diversity-preserving 80/20 selection exists, but it depends on corrupted cluster IDs in some cases and loses funnel provenance. |
| 5 | Partially Met | MAP-Elites archive exists, but behavior dimensions are frequently populated from placeholders rather than real behavior data. |
| 6 | Not Met | Heatmap output exists, but parallel coordinates and cluster membership data are placeholder-level, not story-complete. |
| 7 | Partially Met | Candidates are emitted with reasons and cluster IDs, but final outputs lose their actual funnel position. |
| 8 | Fully Met | The pipeline is deterministic for the exercised paths with a fixed seed; current tests support that claim. |
| 9 | Partially Met | The architecture doc content appears updated, but the “committed before implementation” prerequisite could not be verified because this workspace has no `.git` metadata. |

**Test Coverage Gaps**
- No test uses non-contiguous candidate IDs or reordered/prefiltered tables, so the row-index/candidate-id corruption is completely missed.
- No test feeds the real Story 5.5 aggregate `scoring-manifest.json`; tests either omit scoring or inject fake per-candidate gauntlet fields.
- No test validates behavior when equity-curve files are missing, or that DSR uses total optimization trials rather than filtered survivors.
- Visualization tests only assert that JSON keys exist; they do not verify real parameter axes, real ranking rationale, or a real 2D projection.
- No test checks that selected candidates preserve their pre-selection funnel stage/provenance as required by AC7.
- No test exercises `deterministic_ratio` edge cases such as `0.0` or `1.0`.

**Summary**
1 of 9 criteria are fully met, 6 are partially met, and 2 are not met.

The main blockers are the broken scoring-manifest integration, candidate-id/index corruption in clustering, placeholder quality/viz data, and the funnel not implementing the specified Pareto stage. Git metadata was unavailable here, so I could not do the workflow’s git-vs-story or commit-order verification.
