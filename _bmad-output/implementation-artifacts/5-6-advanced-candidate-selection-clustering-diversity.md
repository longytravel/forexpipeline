# Story 5.6: Advanced Candidate Selection — Clustering & Diversity

Status: review

## Story

As the pipeline operator,
I want optimization results clustered into distinct parameter groups, ranked using multi-objective methodology with equity curve quality as a first-class criterion, and selected for forward-testing using a mathematically principled diversity-preserving approach,
so that I evaluate genuinely different strategies rather than thousands of near-identical parameter sets.

**Story Type:** Growth-phase (MVP uses V1 simple candidate promotion from Story 5.3 — `promote_top_candidates()` top-N by cv_objective + operator review)

## Acceptance Criteria

1. **Given** optimization has produced 10K+ evaluated candidates (Story 5.3 output: `candidates.arrow`)
   **When** candidate selection runs
   **Then** similar parameter sets are clustered using Gower distance + HDBSCAN with automatic cluster count determination, producing distinct behavioral groups (FR26)

2. **Given** clustered candidates exist
   **When** equity curve quality is assessed
   **Then** five metrics are computed per candidate: K-Ratio, Ulcer Index, DSR, Gain-to-Pain Ratio, Serenity Ratio — per Brief 5B research recommendations (FR27)

3. **Given** candidates have equity curve quality metrics and validation scores
   **When** multi-objective ranking runs
   **Then** a 4-stage filtering funnel executes: hard gates → TOPSIS ranking with CRITIC-derived weights → stability filtering → Pareto frontier extraction (FR27)

4. **Given** the funnel has produced ranked candidates
   **When** forward-test candidates are selected
   **Then** selection uses a diversity-preserving methodology across clusters — not just top-N from a single ranking — with an 80/20 deterministic-exploratory split (FR28)

5. **Given** candidates are selected
   **When** the diversity archive is maintained
   **Then** a MAP-Elites style archive preserves behavioral diversity across dimensions: trade frequency, holding time, win rate, max drawdown (FR28)

6. **Given** selection is complete
   **When** results are presented to the operator
   **Then** cluster representatives and ranking rationale include visualization data for: parallel coordinates, parameter heatmaps, cluster membership plots (FR26, FR76)

7. **Given** the full selection pipeline completes
   **When** output is finalized
   **Then** 5-20 diverse candidates are emitted with clear documentation of why each was selected, which cluster it represents, and its position in the filtering funnel (FR28)

8. **Given** the same `candidates.arrow`, scoring manifest, and config (including `random_seed`)
   **When** candidate selection runs twice
   **Then** identical cluster IDs, rankings, selected candidate sets, and manifest content (excluding `selected_at` timestamp) are produced — full deterministic reproducibility

9. **Given** this story implements HDBSCAN per Brief 5B research
   **When** the implementation is complete
   **Then** Architecture document D11 candidate compressor description is updated from DBSCAN to HDBSCAN with rationale, and D11 file structure is updated to reflect `selection/` subsystem replacing single `analysis/candidate_compressor.py`

## Tasks / Subtasks

- [x] **Task 1: Data models and configuration** (AC: #1, #2, #5)
  - [x]Create `src/python/selection/models.py` with dataclasses:
    - `ClusterAssignment(candidate_id: int, cluster_id: int, is_noise: bool, membership_prob: float)`
    - `EquityCurveQuality(candidate_id: int, k_ratio: float, ulcer_index: float, dsr: float, gain_to_pain: float, serenity_ratio: float)`
    - `RankedCandidate(candidate_id: int, topsis_score: float, pareto_rank: int, cluster_id: int, stability_pass: bool, funnel_stage: str, selection_reason: str)`
    - `DiversityCell(dimensions: dict[str, str], best_candidate_id: int, best_score: float)` (MAP-Elites)
    - `SelectionManifest(strategy_id: str, optimization_run_id: str, selected_candidates: list[RankedCandidate], clusters: list[ClusterSummary], diversity_archive: list[DiversityCell], funnel_stats: FunnelStats, config_hash: str, selected_at: str, upstream_refs: UpstreamRefs, critic_weights: dict[str, float], gate_failure_summary: dict[str, int], random_seed_used: int)`
    - `UpstreamRefs(candidates_path: str, candidates_hash: str, scoring_manifest_path: str | None, scoring_manifest_hash: str | None)` — provenance links to upstream artifacts
    - `ClusterSummary(cluster_id: int, size: int, centroid_params: dict, representative_id: int, robustness_score: float, metrics_summary: dict)`
    - `FunnelStats(total_input: int, after_hard_gates: int, after_topsis: int, after_stability: int, after_pareto: int, final_selected: int)`
  - [x]Create `src/python/selection/config.py`:
    - `SelectionConfig` loaded from `config/base.toml` `[selection]` section
    - Fields: `min_cluster_size: int`, `hdbscan_min_samples: int`, `topsis_top_n: int`, `stability_threshold: float`, `target_candidates: int` (5-20), `deterministic_ratio: float` (0.8), `diversity_dimensions: list[str]`, `random_seed: int | None` (None = derive from optimization_run_id hash)
  - [x]Add `[selection]` section to `config/base.toml` and `config/schema.toml`

- [x] **Task 2: Clustering engine — Gower distance + HDBSCAN** (AC: #1)
  - [x]Create `src/python/selection/clustering.py`:
    - `compute_gower_distance(candidates: pa.Table, param_columns: list[str]) -> np.ndarray` — handles mixed continuous/categorical params
    - `cluster_candidates(distance_matrix: np.ndarray, config: SelectionConfig) -> list[ClusterAssignment]` — HDBSCAN with automatic cluster count, returns assignments including noise points
    - `compute_cluster_summaries(candidates: pa.Table, assignments: list[ClusterAssignment]) -> list[ClusterSummary]` — centroid, representative (best cv_objective within cluster), robustness_score (mean fold-score std within cluster)
  - [x]Dependencies: `hdbscan`, `gower` (add to requirements.txt / pyproject.toml)

- [x] **Task 3: Equity curve quality metrics** (AC: #2)
  - [x]Create `src/python/selection/equity_curve_quality.py`:
    - `compute_k_ratio(equity_curve: np.ndarray) -> float` — linear regression slope / standard error
    - `compute_ulcer_index(equity_curve: np.ndarray) -> float` — RMS of percentage drawdowns
    - `compute_dsr(sharpe: float, n_trials: int, sharpe_std: float) -> float` — Deflated Sharpe Ratio (Bailey & López de Prado)
    - `compute_gain_to_pain(returns: np.ndarray) -> float` — sum(returns) / sum(abs(negative returns))
    - `compute_serenity_ratio(returns: np.ndarray, equity_curve: np.ndarray) -> float` — Sharpe-like adjustment with drawdown penalty
    - `compute_all_quality_metrics(candidate_id: int, equity_curve: np.ndarray, returns: np.ndarray, sharpe: float, n_trials: int, sharpe_std: float) -> EquityCurveQuality`
  - [x]Each metric function must be pure, deterministic, tested independently

- [x] **Task 4: Multi-objective ranking — TOPSIS + CRITIC + Pareto** (AC: #3)
  - [x]Create `src/python/selection/ranking.py`:
    - `compute_critic_weights(decision_matrix: np.ndarray) -> np.ndarray` — CRITIC method: correlation-adjusted standard deviation weights
    - `topsis_rank(decision_matrix: np.ndarray, weights: np.ndarray, benefit_columns: list[int], cost_columns: list[int]) -> np.ndarray` — returns closeness coefficients (0-1)
    - `pareto_frontier(candidates: list[RankedCandidate], objectives: list[str]) -> list[RankedCandidate]` — non-dominated sorting (rank 1 = Pareto front)
    - `four_stage_funnel(candidates: pa.Table, quality_metrics: list[EquityCurveQuality], cluster_assignments: list[ClusterAssignment], config: SelectionConfig) -> tuple[list[RankedCandidate], FunnelStats]`:
      1. Hard gates: DSR pass required, PBO ≤ 0.40, cost stress survival (reuse confidence gate thresholds)
      2. TOPSIS ranking on [cv_objective, k_ratio, ulcer_index_inv, gain_to_pain, serenity_ratio, fold_score_std_inv]
      3. Stability filtering: exclude candidates with fold_score_std > threshold
      4. Pareto frontier across [topsis_score, robustness, diversity_distance]

- [x] **Task 5: Diversity archive — MAP-Elites style** (AC: #4, #5)
  - [x]Create `src/python/selection/diversity.py`:
    - `define_behavior_dimensions(config: SelectionConfig) -> list[BehaviorDimension]` — trade_frequency, avg_holding_time, win_rate, max_drawdown with bin boundaries
    - `build_diversity_archive(ranked_candidates: list[RankedCandidate], behavior_data: dict[int, dict]) -> list[DiversityCell]` — MAP-Elites grid: each cell keeps best candidate by topsis_score
    - `select_diverse_candidates(archive: list[DiversityCell], funnel_survivors: list[RankedCandidate], target_n: int, deterministic_ratio: float) -> list[RankedCandidate]`:
      - 80% deterministic: top candidates from filled archive cells, one per cluster preference
      - 20% exploratory: random draw from remaining occupied cells for behavioral coverage
    - Ensures no two selected candidates from same cluster unless cluster count < target_n

- [x] **Task 6: Visualization data preparation** (AC: #6)
  - [x]Create `src/python/selection/visualization.py`:
    - `prepare_parallel_coordinates(candidates: list[RankedCandidate], params: dict) -> dict` — JSON-serializable parallel coords data
    - `prepare_parameter_heatmap(clusters: list[ClusterSummary]) -> dict` — cluster × parameter matrix
    - `prepare_cluster_membership(assignments: list[ClusterAssignment], selected_ids: set[int]) -> dict` — 2D projection (UMAP) with cluster colors and selection highlights
    - All functions return dict structures for downstream dashboard rendering (Story 5.7 / Epic 4)
  - [x]Dependency: `umap-learn` for dimensionality reduction (add to requirements)

- [x] **Task 7: Selection executor — pipeline integration** (AC: #7)
  - [x]Create `src/python/selection/executor.py`:
    - `SelectionExecutor(StageExecutor)`:
      - `stage = PipelineStage.SELECTING` (new stage)
      - `execute(strategy_id: str, context: dict) -> StageResult`:
        1. Load optimization candidates from `candidates.arrow` (via `context["optimization_manifest"]`)
        2. Load equity curves from optimization artifacts
        3. Load confidence scores from scoring manifest (if available — graceful fallback)
        4. Run clustering → quality metrics → funnel → diversity selection
        5. Write `SelectionManifest` via crash_safe_write to `artifacts/{strategy_id}/v{NNN}/selection/manifest.json`
        6. Write visualization data to `artifacts/{strategy_id}/v{NNN}/selection/viz/`
      - `validate_artifact(artifact_path: Path, manifest_ref: Path) -> bool`
  - [x]Create `src/python/selection/orchestrator.py`:
    - `SelectionOrchestrator`:
      - `run_selection(candidates_path: Path, equity_curves_dir: Path, scoring_manifest: Path | None, config: SelectionConfig, output_dir: Path) -> SelectionManifest`
      - Coordinates: clustering → quality → ranking → diversity → manifest
  - [x]Add `SELECTING` and `SELECTION_COMPLETE` stages to `PipelineStage` enum in `src/python/orchestrator/pipeline_state.py`
  - [x]Add transitions: `SCORING_COMPLETE → SELECTING (automatic)`, `SELECTION_COMPLETE → [next stage] (gated — operator reviews selections)`
  - [x]Create `src/python/selection/__init__.py` with public API exports

- [x] **Task 8: Configuration and dependency management** (AC: #1, #3)
  - [x]Add `[selection]` section to `config/base.toml`:
    ```toml
    [selection]
    min_cluster_size = 5
    hdbscan_min_samples = 3
    topsis_top_n = 50
    stability_threshold = 0.3
    target_candidates = 10
    deterministic_ratio = 0.8
    diversity_dimensions = ["trade_frequency", "avg_holding_time", "win_rate", "max_drawdown"]
    max_clustering_candidates = 5000  # pre-filter by cv_objective if input exceeds this
    # random_seed = 42  # uncomment to fix seed; default derives from optimization_run_id hash
    ```
  - [x]Add schema validation to `config/schema.toml`
  - [x]Add dependencies to `requirements.txt` / `pyproject.toml`: `hdbscan>=0.8.33`, `gower>=0.1.2`, `umap-learn>=0.5.5`

- [x] **Task 9: Tests** (AC: #1-#7)
  - [x]Create `src/python/tests/test_selection/test_clustering.py`:
    - `test_gower_distance_mixed_types` — continuous + categorical params
    - `test_hdbscan_clusters_separable_data` — known-cluster synthetic data
    - `test_hdbscan_noise_points_assigned` — noise points flagged correctly
    - `test_cluster_summary_centroid_calculation`
    - `test_cluster_summary_representative_is_best`
    - `test_hdbscan_all_noise_singleton_fallback` — zero real clusters, each candidate becomes singleton
    - `test_hdbscan_single_cluster` — all candidates in one group
  - [x]Create `src/python/tests/test_selection/test_equity_curve_quality.py`:
    - `test_k_ratio_perfect_linear_curve` — should be high
    - `test_k_ratio_noisy_curve` — should be lower
    - `test_ulcer_index_no_drawdown` — should be 0
    - `test_ulcer_index_deep_drawdown` — should be high
    - `test_dsr_high_sharpe_many_trials` — deflation effect
    - `test_dsr_low_trial_count` — minimal deflation
    - `test_gain_to_pain_all_positive` — edge case
    - `test_serenity_ratio_smooth_equity` — should be high
    - `test_compute_all_quality_metrics_integration`
  - [x]Create `src/python/tests/test_selection/test_ranking.py`:
    - `test_critic_weights_sum_to_one`
    - `test_critic_weights_high_variance_column` — gets higher weight
    - `test_topsis_known_ranking` — verified against manual calculation
    - `test_topsis_benefit_vs_cost_columns`
    - `test_pareto_frontier_simple_2d` — known Pareto front
    - `test_pareto_frontier_all_dominated` — single winner
    - `test_four_stage_funnel_gate_filtering` — hard gates remove candidates
    - `test_four_stage_funnel_stats_accurate` — funnel counts match
    - `test_four_stage_funnel_all_fail_gates` — empty funnel returns empty manifest
    - `test_four_stage_funnel_fewer_than_target` — survivors < target_candidates, selects all
  - [x]Create `src/python/tests/test_selection/test_diversity.py`:
    - `test_map_elites_single_cell` — one candidate per cell
    - `test_map_elites_best_replaces_worse` — higher score wins cell
    - `test_diverse_selection_80_20_split` — deterministic vs exploratory ratio
    - `test_diverse_selection_cross_cluster` — no same-cluster duplicates when possible
    - `test_diverse_selection_target_count` — output count matches target_candidates
  - [x]Create `src/python/tests/test_selection/test_executor.py`:
    - `test_selection_executor_stage_registration`
    - `test_selection_executor_end_to_end` — synthetic candidates → manifest output
    - `test_selection_executor_crash_safe_write` — partial file cleaned up
    - `test_selection_executor_missing_scoring` — graceful fallback without confidence scores
    - `test_selection_manifest_schema_complete` — all required fields populated including upstream_refs, critic_weights, gate_failure_summary, random_seed_used
    - `test_selection_deterministic_rerun` — same inputs + same seed → identical manifest (AC #8)
    - `test_selection_manifest_upstream_refs_populated` — candidates_path, candidates_hash are non-empty
  - [x]Create `src/python/tests/test_selection/test_memory.py`:
    - `test_gower_chunked_computation` — verify chunked Gower produces same result as dense
    - `test_pre_filter_large_candidate_set` — >max_clustering_candidates triggers pre-filtering
  - [x]Create `src/python/tests/test_selection/__init__.py`

- [x] **Task 10: Architecture D11 and D3 updates** (AC: #9)
  - [x]Update `_bmad-output/planning-artifacts/architecture.md` D11 section: change "DBSCAN clustering on parameter space" to "HDBSCAN clustering with Gower distance on parameter space" with rationale from Brief 5B research
  - [x]Update D11 file structure: `analysis/candidate_compressor.py` → `selection/` subsystem (9 modules). Add rationale: Growth-phase candidate selection exceeds single-file scope; subsystem follows established `{module}/` pattern (confidence/, validation/, optimization/)
  - [x]Update D3 stage graph documentation to include `SELECTING` / `SELECTION_COMPLETE` stages as Growth-phase additions after `SCORING_COMPLETE`
  - [x]**Prerequisite:** These architecture updates must be committed BEFORE implementation begins, not as a side effect of story completion

## Dev Notes

### Architecture Constraints
- **D1 (Multi-Process):** Selection runs in Python process; no Rust subprocess needed (pure analytics on optimization output)
- **D2 (Artifact Schema):** Selection manifest is JSON (not Arrow IPC) — small output (5-20 candidates). Input `candidates.arrow` read via PyArrow
- **D3 (Pipeline Orchestration):** Selection is a new pipeline stage (`SELECTING` / `SELECTION_COMPLETE`). It's opaque to state machine — internal orchestration in `SelectionOrchestrator`
- **D11 (AI Analysis Layer):** Architecture places candidate compression at `analysis/candidate_compressor.py`. This Growth story exceeds single-file scope → creates `selection/` subsystem. Architecture D11 file structure and D3 stage graph must be updated BEFORE implementation (Task 10 prerequisite). Research (Brief 5B) recommends HDBSCAN over D11's DBSCAN
- **D13 (Cost Model):** Cost stress gate reuses confidence scoring thresholds — do not re-implement
- **D14 (Strategy Engine):** Equity curves and trade logs already available from optimization artifacts

### Technical Requirements
- **Deterministic-first (D11):** All metrics computed deterministically. No randomness except the 20% exploratory selection — seed that RNG from config for reproducibility
- **Crash-safe writes:** Use `crash_safe_write` pattern from `src/python/artifacts/storage.py` for manifest and viz data
- **Structured logging:** Use `get_logger("selection")` from `src/python/logging_setup/setup.py`
- **Config validation:** Validate `[selection]` config at startup, embed config hash in manifest

### Performance Considerations
- **Gower distance matrix:** O(n²) for 10K candidates × 30 params ≈ 100M distance pairs. Dense float64 would be ~2.4 GB which exceeds NFR4 memory budget. **Must use chunked computation:** compute Gower distance in row-batches (e.g., 1K×10K chunks), feed to HDBSCAN incrementally, or use `hdbscan` with `metric='precomputed'` on float32 (~1.2 GB) with explicit memory monitoring. If 10K candidates is typical, consider pre-filtering to top-N by cv_objective (e.g., top 2K) before computing full distance matrix
- **HDBSCAN:** Handles 10K points efficiently (sub-second on modern hardware with precomputed distance matrix)
- **TOPSIS:** Linear in candidate count after distance matrix — no concern
- **UMAP:** Only for visualization (not in hot path). Compute on selected candidates + cluster representatives only (~100-200 points max)
- **Memory budget (D3/NFR4):** Peak memory dominated by Gower distance matrix. With chunked float32 approach on 10K candidates: ~1.2 GB peak. With pre-filtering to 2K candidates: ~120 MB peak. Implement memory monitoring and log peak usage. Add a config guard: if candidate count exceeds `max_clustering_candidates` (default 5000), pre-filter by cv_objective first

### Upstream Contract (Story 5.3 → 5.6)
```
Input: candidates.arrow (Arrow IPC)
Schema: candidate_id: uint64, rank: uint32, params_json: utf8,
        cv_objective: float64, fold_scores: list(float64),
        branch: utf8, instance_type: utf8
Location: artifacts/{strategy_id}/v{NNN}/optimization/candidates.arrow
Volume: ~10,000 candidates × 7 fields → ~2.4 MB
```

### Upstream Contract (Story 5.5 → 5.6, optional)
```
Input: Scoring manifest with ConfidenceScore per candidate
Schema: candidate_id, rating (RED/YELLOW/GREEN), composite_score,
        breakdown (per-component), gates (pass/fail)
Location: artifacts/{strategy_id}/v{NNN}/scoring/manifest.json
Note: If scoring ran before selection, use gate results to pre-filter.
      If not available, selection uses its own hard gates from config.
```

### Downstream Contract (5.6 → Story 5.7 E2E)
```
Output: SelectionManifest (JSON)
Schema: strategy_id, optimization_run_id, selected_candidates[],
        clusters[], diversity_archive[], funnel_stats, config_hash,
        selected_at, upstream_refs{candidates_path, candidates_hash,
        scoring_manifest_path?, scoring_manifest_hash?},
        critic_weights{metric_name: weight}, gate_failure_summary{gate_name: fail_count},
        random_seed_used
Location: artifacts/{strategy_id}/v{NNN}/selection/manifest.json
Visualization: artifacts/{strategy_id}/v{NNN}/selection/viz/*.json
Note: Manifest is a provenance-rich decision artifact — downstream consumers
      (dashboard, evidence packs, audit) should NOT need to re-derive ranking
      decisions. CRITIC weights and gate summaries enable explainability without
      re-running the funnel.
```

### What to Reuse from Existing Code
- **`src/python/optimization/results.py`:** `promote_top_candidates()` — V1 simple promotion. Do NOT modify this. Story 5.6 creates a parallel advanced path. The orchestrator will choose V1 or advanced based on config
- **`src/python/confidence/gates.py`:** Hard gate logic (DSR pass, PBO threshold, cost stress). Reuse gate threshold values from `[confidence.hard_gates]` config — do NOT duplicate thresholds
- **`src/python/confidence/models.py`:** `ConfidenceScore`, `CandidateRating` — import and use for filtering candidates by rating
- **`src/python/artifacts/storage.py`:** `crash_safe_write()` — use for all file writes
- **`src/python/logging_setup/setup.py`:** `get_logger()` — use for structured logging
- **`src/python/orchestrator/pipeline_state.py`:** `PipelineStage`, `StageResult`, `CompletedStage` — extend with new stages
- **`src/python/orchestrator/stage_runner.py`:** `StageExecutor` protocol — implement for `SelectionExecutor`

### What NOT to Reuse
- **ClaudeBackTester:** No selection/clustering code exists in baseline. This is entirely new functionality
- **`src/python/confidence/scorer.py`:** Do not reuse the weighted composite scorer. TOPSIS is a different methodology. The confidence scorer normalizes and weights differently than TOPSIS closeness coefficients

## Anti-Patterns to Avoid

1. **Do NOT re-implement hard gates.** Import thresholds from `[confidence.hard_gates]` config and reuse the gate evaluation logic from `confidence/gates.py`. Duplicating thresholds means they'll drift
2. **Do NOT use k-means for clustering.** Architecture and research specify density-based clustering (HDBSCAN) because parameter spaces have irregular cluster shapes and noise. K-means assumes spherical clusters
3. **Do NOT sort candidates by a single metric.** The entire point of TOPSIS + diversity archive is multi-objective selection. Falling back to `sorted(candidates, key=lambda c: c.sharpe)` defeats the purpose
4. **Do NOT compute UMAP on all 10K candidates.** UMAP is only for visualization of selected candidates + cluster representatives. Computing on full set wastes time and memory
5. **Do NOT use random seed without config.** The 20% exploratory selection must be reproducible. Read seed from config or use `optimization_run_id` hash as seed
6. **Do NOT modify V1 simple promotion path.** `promote_top_candidates()` in `optimization/results.py` must remain untouched. Advanced selection is a parallel path, not a replacement
7. **Do NOT accumulate equity curves in memory.** Read equity curve data per-candidate from Arrow IPC files, compute metrics, discard. Streaming pattern, not load-all-then-process
8. **Do NOT skip noise points.** HDBSCAN labels some candidates as noise (-1 cluster). These must still be evaluated in the funnel — they just don't get cluster-based diversity bonuses
9. **Do NOT hardcode TOPSIS weights.** CRITIC computes weights from the data. Hardcoded weights would ignore the actual distribution of metric values in the current optimization run
10. **Do NOT compute dense Gower matrix on full 10K candidates without chunking.** A 10K×10K float64 matrix is ~2.4 GB. Use float32 + chunked computation, or pre-filter to `max_clustering_candidates` first. Log peak memory usage for NFR4 compliance

### Edge Cases to Handle

1. **Zero real clusters (all noise):** If HDBSCAN labels every candidate as noise (-1), treat each candidate as its own singleton cluster. Log a WARNING. Proceed with funnel — diversity archive will still differentiate by behavior dimensions
2. **All candidates fail hard gates:** Return an empty `SelectionManifest` with `funnel_stats.final_selected = 0`. Log an ERROR with gate failure distribution. Do NOT relax gates silently — the operator must decide whether to re-optimize with different parameters
3. **Fewer survivors than `target_candidates`:** Select all surviving candidates. Set `funnel_stats.final_selected` to actual count. Log a WARNING noting shortfall. Do not pad with rejected candidates
4. **Single cluster:** All candidates cluster together. Diversity archive still applies — behavioral dimensions (trade frequency, holding time) differentiate within the single parameter cluster. Selection proceeds normally
5. **Duplicate params_json:** Multiple candidates with identical parameters but different fold orderings. Deduplicate by keeping the one with best cv_objective before clustering

## Project Structure Notes

### Files to Create
```
src/python/selection/
├── __init__.py                    # Public API: SelectionOrchestrator, SelectionExecutor
├── models.py                      # ClusterAssignment, EquityCurveQuality, RankedCandidate, etc.
├── config.py                      # SelectionConfig loader from [selection] TOML section
├── clustering.py                  # Gower distance + HDBSCAN clustering
├── equity_curve_quality.py        # K-Ratio, Ulcer Index, DSR, Gain-to-Pain, Serenity
├── ranking.py                     # CRITIC weights, TOPSIS, Pareto frontier, 4-stage funnel
├── diversity.py                   # MAP-Elites archive, diversity-preserving selection
├── visualization.py               # Parallel coords, heatmap, cluster membership viz data
├── orchestrator.py                # SelectionOrchestrator — coordinates full pipeline
└── executor.py                    # SelectionExecutor — StageExecutor implementation

src/python/tests/test_selection/
├── __init__.py
├── test_clustering.py             # 7 tests
├── test_equity_curve_quality.py   # 9 tests
├── test_ranking.py                # 10 tests
├── test_diversity.py              # 5 tests
├── test_executor.py               # 7 tests
└── test_memory.py                 # 2 tests
```

### Files to Modify
```
src/python/orchestrator/pipeline_state.py  # Add SELECTING, SELECTION_COMPLETE stages + transitions
config/base.toml                           # Add [selection] section
config/schema.toml                         # Add selection schema validation
requirements.txt / pyproject.toml          # Add hdbscan, gower, umap-learn
_bmad-output/planning-artifacts/architecture.md  # Update D11: DBSCAN → HDBSCAN
```

### Alignment with Project Structure
- Module follows established pattern: `src/python/{module}/` with `models.py`, `config.py`, `executor.py`, `orchestrator.py`
- Test structure mirrors: `src/python/tests/test_{module}/`
- Config section pattern: `[selection]` in `config/base.toml` with schema validation
- Artifact output pattern: `artifacts/{strategy_id}/v{NNN}/selection/`

## References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 5, Story 5.6]
- [Source: _bmad-output/planning-artifacts/architecture.md — D1, D2, D3, D11, D13, D14]
- [Source: _bmad-output/planning-artifacts/prd.md — FR26, FR27, FR28, FR76]
- [Source: _bmad-output/planning-artifacts/research/briefs/5B/epic5-brief-5B-candidate-selection-equity-curve-quality.txt — Clustering, TOPSIS, MAP-Elites, equity curve metrics]
- [Source: _bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md — Upstream scoring contract, gate logic, models]
- [Source: _bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md — Upstream candidates contract, promote_top_candidates]
- [Source: _bmad-output/implementation-artifacts/5-2-optimization-algorithm-candidate-selection-validation-gauntlet-research.md — Research findings]
- [Source: src/python/optimization/results.py — promoted_candidates_schema, StreamingResultsWriter]
- [Source: src/python/confidence/models.py — ConfidenceScore, CandidateRating, ValidationEvidencePack]
- [Source: src/python/orchestrator/pipeline_state.py — PipelineStage enum, StageResult, transitions]
- [Source: src/python/orchestrator/stage_runner.py — StageExecutor protocol]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Debug Log References
- Fixed HDBSCAN float64 requirement (gower returns float32, HDBSCAN mst_linkage_core needs double_t)
- Fixed params_json expansion: Arrow table doesn't have expanded params, must convert to pandas and expand before clustering
- Updated existing orchestrator tests for new SELECTING/SELECTION_COMPLETE pipeline stages

### Completion Notes List
- Task 10: Architecture D11 updated (DBSCAN → HDBSCAN), D11 file structure updated (selection/ subsystem), D3 stage graph updated
- Task 1: 8 dataclasses with full JSON serialization (ClusterAssignment, EquityCurveQuality, RankedCandidate, DiversityCell, ClusterSummary, FunnelStats, UpstreamRefs, SelectionManifest). SelectionConfig with validation and deterministic config hash
- Task 2: Gower distance with chunked computation (float64 for HDBSCAN), HDBSCAN clustering with all-noise singleton fallback, cluster summaries with centroid/representative/robustness, pre-filter for memory budget
- Task 3: 5 pure deterministic metrics (K-Ratio via linregress, Ulcer Index via RMS drawdown, DSR via Bailey & López de Prado, Gain-to-Pain, Serenity Ratio)
- Task 4: CRITIC weights (correlation-adjusted std), TOPSIS ranking (vector normalization), non-dominated Pareto sorting, 4-stage funnel (hard gates → TOPSIS → stability → Pareto)
- Task 5: MAP-Elites grid with 4 behavior dimensions, 80/20 deterministic-exploratory selection with cross-cluster diversity preference
- Task 6: Parallel coordinates, parameter heatmap, cluster membership viz data (all JSON-serializable)
- Task 7: SelectionExecutor (StageExecutor protocol), SelectionOrchestrator (full pipeline coordination), SELECTING/SELECTION_COMPLETE stages in PipelineStage enum and STAGE_GRAPH
- Task 8: [selection] config in base.toml + schema.toml, hdbscan/gower/umap-learn dependencies
- Task 9: 55 unit tests + 3 live integration tests. All 193 tests pass (including orchestrator regression)

### Change Log
- 2026-03-23: Story 5.6 implemented — all 10 tasks complete, 58 tests total (55 unit + 3 live), 193 full regression pass

### File List
**Created:**
- src/python/selection/__init__.py
- src/python/selection/models.py
- src/python/selection/config.py
- src/python/selection/clustering.py
- src/python/selection/equity_curve_quality.py
- src/python/selection/ranking.py
- src/python/selection/diversity.py
- src/python/selection/visualization.py
- src/python/selection/orchestrator.py
- src/python/selection/executor.py
- src/python/tests/test_selection/__init__.py
- src/python/tests/test_selection/test_clustering.py
- src/python/tests/test_selection/test_equity_curve_quality.py
- src/python/tests/test_selection/test_ranking.py
- src/python/tests/test_selection/test_diversity.py
- src/python/tests/test_selection/test_executor.py
- src/python/tests/test_selection/test_memory.py
- src/python/tests/test_selection/test_live.py

**Modified:**
- src/python/orchestrator/pipeline_state.py (added SELECTING, SELECTION_COMPLETE stages + transitions)
- config/base.toml (added [selection] section, updated gated_stages)
- config/schema.toml (added selection schema validation)
- src/python/pyproject.toml (added hdbscan, gower, umap-learn dependencies)
- _bmad-output/planning-artifacts/architecture.md (D11: DBSCAN→HDBSCAN, file structure, D3: stage graph)
- src/python/tests/test_orchestrator/test_pipeline_state.py (updated for new stages)
- src/python/tests/test_orchestrator/test_gate_manager.py (updated for new stages)
