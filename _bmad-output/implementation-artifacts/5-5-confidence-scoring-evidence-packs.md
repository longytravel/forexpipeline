# Story 5.5: Confidence Scoring & Evidence Packs

Status: review

## Story

As the **operator**,
I want all validation results aggregated into a single confidence score with RED/YELLOW/GREEN rating and detailed breakdown, assembled into an evidence pack with a triage summary card for quick scanning and a full assessment for deep review,
So that I can make an informed go/caution/reject decision on each candidate without needing to interpret raw statistical output.

## Acceptance Criteria

1. **Given** a candidate has a gauntlet manifest from Story 5.4 (complete or short-circuited)
   **When** confidence scoring runs
   **Then** all available validation stage results are aggregated into a composite confidence score using the research-determined formula: hard gates first (DSR pass, PBO ≤ 0.40, cost stress survival at 1.5x), then weighted scoring across remaining components. Short-circuited candidates receive RED rating with missing stages scored as 0.0 and documented as "stage skipped due to {gate_name} failure"
   [Ref: FR34, D11, Brief 5C]

2. **Given** a composite confidence score is computed
   **When** the rating is assigned
   **Then** the score maps to RED/YELLOW/GREEN using research-calibrated thresholds — RED means reject (hard gate failed or composite below threshold), YELLOW means caution (passed gates but marginal on some components), GREEN means proceed (strong across all components)
   [Ref: FR34, Brief 5C threshold calibration]

3. **Given** a confidence score is computed
   **When** the breakdown is rendered
   **Then** it shows each component's individual normalized score (0.0–1.0), its weight in the composite, whether it passed/failed any hard gate, and a one-line interpretation
   [Ref: FR34]

4. **Given** a candidate has been scored
   **When** the evidence pack is assembled
   **Then** it follows the two-pass specification: Pass 1 (triage summary card: ≤10 headline fields, ≤3 risk items, ≤200 words total) with rating, composite score, headline metrics, dominant edge description, top 3 risks, and optional delta vs baseline; Pass 2 (full evidence pack) with complete chart data references, statistical detail, per-stage breakdown, session analysis, and anomaly report — every section must include citation references
   [Ref: D11 two-pass evidence packs, Brief 3C, FR39]

5. **Given** an evidence pack is assembled
   **When** narrative claims are generated
   **Then** every claim cites an exact metric ID or chart ID — no ungrounded statements. Narratives are template-driven from computed statistics, not LLM-generated.
   [Ref: D11 deterministic-first architecture, Brief 3C]

6. **Given** validation results exist for a candidate
   **When** the AI analysis layer generates narrative summaries
   **Then** it uses structured inputs only: JSON metric sets + anomaly flags + evidence artifact references → constrained structured output
   [Ref: D11, FR16]

7. **Given** all candidates from the gauntlet
   **When** anomaly detection runs
   **Then** it executes the two-tier system: Layer A performs per-candidate anomaly scoring (IS-OOS divergence, regime concentration, perturbation cliffs, walk-forward degradation, tail risk); Layer B surfaces flags only when multiple detectors agree or tier-1 academic tests trigger. Cross-candidate population-level statistical tests (distribution shape, clustering) are gated behind a configurable minimum candidate count (default: 20) and skipped in V1 if below threshold
   [Ref: Brief 3C anomaly detection toolkit, FR17, FR35]

8. **Given** an evidence pack is assembled
   **When** a decision trace is included
   **Then** it records: pre-committed thresholds and gate definitions used, PASS/FAIL outcome per gate with the actual metric value, a `confidence_config_hash` identifying the scoring configuration version, and research brief version provenance. Operator review decisions are stored in a separate append-only artifact, not in the immutable evidence pack
   [Ref: Brief 3C evidence pack specification]

9. **Given** confidence scoring and evidence packs are complete
   **When** the operator reviews candidates
   **Then** candidates are reviewable via `/pipeline` → "Review Optimization Results" with accept/reject/refine decisions recorded in a separate append-only `operator-review-candidate-{id}.json` artifact (not mutating the immutable evidence pack) that advance the pipeline
   [Ref: FR39, D9]

10. **Given** confidence scoring and evidence assembly complete
    **When** artifacts are persisted
    **Then** all confidence scores, evidence packs, and operator decisions are written as versioned artifacts using the crash-safe write pattern (`.partial` → `fsync` → `os.replace`)
    [Ref: D2, NFR15, FR58]

11. **Given** an evidence pack is assembled
    **When** visualization data is prepared
    **Then** it includes: equity curve quality charts (per-fold and aggregate), walk-forward per-window results, parameter sensitivity heatmaps, Monte Carlo distribution plots, regime performance breakdown by volatility tercile × forex session
    [Ref: FR25, FR36, FR37]

## Tasks / Subtasks

- [x] **Task 1: Define confidence scoring data models** (AC: #1, #2, #3, #4, #8, #10)
  - [x]Create `src/python/confidence/__init__.py` with public exports
  - [x]Create `src/python/confidence/models.py` with dataclasses:
    - `GateResult(gate_name: str, threshold: float, actual_value: float, passed: bool, description: str)` — individual hard gate outcome
    - `ComponentScore(component_name: str, raw_value: float, normalized_score: float, weight: float, weighted_contribution: float, interpretation: str, gate_result: GateResult | None)` — per-component score in the composite
    - `ConfidenceBreakdown(components: list[ComponentScore], gates: list[GateResult], hard_gate_passed: bool, composite_score: float)` — full scoring breakdown
    - `CandidateRating` enum: `RED`, `YELLOW`, `GREEN`
    - `ConfidenceScore(candidate_id: int, optimization_run_id: str, rating: CandidateRating, composite_score: float, breakdown: ConfidenceBreakdown, scored_at: str)` — top-level result per candidate
    - `TriageSummary(candidate_id: int, rating: CandidateRating, composite_score: float, headline_metrics: dict[str, Any], dominant_edge: str, top_risks: list[str], delta_vs_baseline: dict[str, float] | None)` — Pass 1 (triage card). `delta_vs_baseline` is optional — only populated when a baseline result exists (e.g., buy-and-hold benchmark or prior optimization run)
    - `DecisionTrace(gates_used: list[GateResult], thresholds_snapshot: dict[str, float], confidence_config_hash: str, validation_config_hash: str, research_brief_versions: dict[str, str])` — immutable audit trail of scoring configuration and gate outcomes. Operator notes/decisions stored in separate `OperatorReview` artifact
    - `ValidationEvidencePack(candidate_id: int, optimization_run_id: str, strategy_id: str, confidence_score: ConfidenceScore, triage_summary: TriageSummary, decision_trace: DecisionTrace, per_stage_results: dict[str, Any], anomaly_report: AnomalyReport, narrative: NarrativeResult, visualization_refs: dict[str, str], metadata: dict[str, Any])` — complete evidence pack
    - `OperatorReview(candidate_id: int, decision: str, rationale: str, operator_notes: str, decision_timestamp: str, evidence_pack_path: str)` — separate append-only artifact for human review decisions (not part of immutable evidence pack)
    - All models must implement `to_json() -> dict` and `from_json(cls, data) -> Self` following the pattern in `analysis/models.py`
  - [x]Test: `test_confidence_models_serialization()` — round-trip JSON for every model

- [x] **Task 2: Add confidence scoring configuration** (AC: #1, #2, #3)
  - [x]Add `[confidence]` section to `config/base.toml`:
    ```toml
    [confidence]
    # Hard gates — any failure → immediate RED
    [confidence.hard_gates]
    dsr_pass_required = true          # DSR must pass (D11 mandatory >10 candidates)
    pbo_max_threshold = 0.40          # PBO ≤ 0.40 (D11)
    cost_stress_survival_multiplier = 1.5  # Must survive 1.5x cost inflation

    # Component weights for composite score (must sum to 1.0)
    [confidence.weights]
    walk_forward_oos_consistency = 0.25  # OOS Sharpe consistency across windows
    cpcv_pbo_margin = 0.15              # How far below PBO threshold
    parameter_stability = 0.15           # Mean sensitivity from perturbation
    monte_carlo_stress_survival = 0.15   # % of bootstrap/permutation/stress passing
    regime_uniformity = 0.15             # Performance spread across regimes
    in_sample_oos_coherence = 0.15       # IS vs OOS metric divergence (FR35)

    # Rating thresholds (applied after hard gates pass)
    [confidence.thresholds]
    green_minimum = 0.70               # Composite >= 0.70 → GREEN
    yellow_minimum = 0.40              # Composite >= 0.40 → YELLOW
    # Below yellow_minimum → RED (even if hard gates passed)
    ```
  - [x]Add schema validation for weights summing to 1.0 in `config/schema.toml`
  - [x]Create `src/python/confidence/config.py`:
    - `ConfidenceConfig` dataclass loaded from `config/base.toml[confidence]`
    - `HardGateConfig`, `WeightConfig`, `ThresholdConfig` sub-dataclasses
    - `load_confidence_config(config_path: Path) -> ConfidenceConfig`
  - [x]Test: `test_confidence_config_loads()`, `test_weights_sum_validation()`

- [x] **Task 3: Implement hard gate evaluator** (AC: #1, #2, #8)
  - [x]Create `src/python/confidence/gates.py`
  - [x]Function: `evaluate_hard_gates(gauntlet_manifest: dict, config: HardGateConfig) -> list[GateResult]`
    - Gate 1: DSR pass — read `gate_results.dsr_passed` from gauntlet manifest. If total_optimization_trials > 10 and DSR fails → FAIL
    - Gate 2: PBO threshold — read `gate_results.pbo_value` from gauntlet manifest. PBO > config.pbo_max_threshold → FAIL
    - Gate 3: Cost stress survival — read Monte Carlo stress test results. If strategy PnL goes negative at config.cost_stress_survival_multiplier × base costs → FAIL
    - Returns list of GateResult with gate_name, threshold, actual_value, passed, description
  - [x]Function: `any_gate_failed(results: list[GateResult]) -> bool`
  - [x]The gate evaluator reads from Story 5.4's gauntlet manifest fields: `gate_results`, `per_stage_metric_ids`
  - [x]Test: `test_dsr_gate_pass()`, `test_dsr_gate_fail()`, `test_pbo_gate_pass()`, `test_pbo_gate_fail()`, `test_cost_stress_gate_pass()`, `test_cost_stress_gate_fail()`, `test_multiple_gate_failures()`

- [x] **Task 4: Implement weighted composite scorer** (AC: #1, #2, #3)
  - [x]Create `src/python/confidence/scorer.py`
  - [x]Function: `compute_component_scores(gauntlet_manifest: dict, config: WeightConfig) -> list[ComponentScore]`
    - Walk-forward OOS consistency: normalize median OOS Sharpe across windows to 0.0–1.0 using research-calibrated floor/ceiling (e.g., -0.5 to 2.0 → 0.0 to 1.0)
    - CPCV PBO margin: normalize (threshold - actual_pbo) / threshold to 0.0–1.0
    - Parameter stability: normalize mean perturbation sensitivity (lower is better) — 1.0 - (mean_sensitivity / max_sensitivity_ceiling)
    - Monte Carlo stress survival: fraction of simulations passing across bootstrap + permutation + stress
    - Regime uniformity: 1.0 - coefficient of variation across regime-session Sharpe values (flag insufficient trade count buckets)
    - IS-OOS coherence: 1.0 - normalized absolute divergence between in-sample and OOS metrics (FR35)
  - [x]Function: `compute_composite_score(components: list[ComponentScore]) -> float` — sum of weighted contributions
  - [x]Function: `assign_rating(composite: float, hard_gates_passed: bool, config: ThresholdConfig) -> CandidateRating`
    - If not hard_gates_passed → RED
    - If composite >= green_minimum → GREEN
    - If composite >= yellow_minimum → YELLOW
    - Else → RED
  - [x]Function: `score_candidate(gauntlet_manifest: dict, config: ConfidenceConfig) -> ConfidenceScore`
    - Orchestrates: evaluate_hard_gates → compute_component_scores → compute_composite → assign_rating → build ConfidenceScore
  - [x]Test: `test_score_all_green()`, `test_score_yellow_marginal()`, `test_score_red_gate_failure()`, `test_score_red_low_composite()`, `test_component_normalization_bounds()`, `test_weights_applied_correctly()`

- [x] **Task 5: Implement two-tier anomaly detection** (AC: #7)
  - [x]Create `src/python/confidence/anomaly_layer.py`
  - [x]Reuse `AnomalyType`, `AnomalyFlag`, `AnomalyReport`, `Severity` from `analysis/models.py` — do NOT duplicate
  - [x]Add new anomaly types to `AnomalyType` enum in `analysis/models.py`:
    - `IS_OOS_DIVERGENCE` — in-sample vs OOS performance divergence (FR35)
    - `REGIME_CONCENTRATION` — performance concentrated in single regime
    - `PERTURBATION_CLIFF_CLUSTER` — multiple parameters show sensitivity cliffs
    - `WALK_FORWARD_DEGRADATION` — OOS performance degrades across later windows
    - `MONTE_CARLO_TAIL_RISK` — excessive tail risk in bootstrap distribution
  - [x]Layer A (per-candidate anomaly scoring):
    - Function: `run_layer_a(candidates_manifests: list[dict], min_population_size: int = 20) -> dict[int, list[AnomalyFlag]]`
    - Per-candidate detectors (always run): IS-OOS divergence, regime concentration, perturbation cliff clusters, walk-forward degradation, Monte Carlo tail risk
    - Cross-candidate population tests (Sharpe distribution shape, parameter clustering, OOS return correlation) only run when `len(candidates) >= min_population_size`; skipped with info log otherwise
    - Score every candidate silently; flags stored but NOT surfaced unless Layer B triggers
  - [x]Layer B (surfaced flags):
    - Function: `run_layer_b(candidates_manifests: list[dict], layer_a_scores: dict[int, list[AnomalyFlag]]) -> dict[int, AnomalyReport]`
    - Surface flag when: (a) ≥2 Layer A detectors agree for a candidate, OR (b) tier-1 academic tests trigger (DSR below threshold already in hard gates, PBO already in gates — this covers IS-OOS divergence, walk-forward degradation, regime concentration)
    - Surfaced flags include severity, description, evidence dict with metric IDs, and recommendation
  - [x]Test: `test_layer_a_silent_scoring()`, `test_layer_b_surfacing_threshold()`, `test_layer_b_academic_trigger()`, `test_no_false_surfacing_single_detector()`, `test_anomaly_report_serialization()`

- [x] **Task 6: Implement narrative engine** (AC: #5, #6)
  - [x]Create `src/python/confidence/narrative_engine.py`
  - [x]Follow `analysis/narrative.py` pattern — template-driven, NOT LLM-generated (D11 deterministic-first)
  - [x]Function: `generate_confidence_narrative(confidence_score: ConfidenceScore, gauntlet_manifest: dict, anomaly_report: AnomalyReport) -> NarrativeResult`
    - Overview: "Candidate {id} rated {GREEN/YELLOW/RED} (composite: {score:.2f}). {dominant_edge_sentence}. {top_risk_sentence}."
    - Metrics: include all component scores with their weights and interpretations
    - Strengths: components scoring above 0.8 with their metric IDs
    - Weaknesses: components scoring below 0.5 or with surfaced anomaly flags, with their metric IDs
    - Session breakdown: regime × session performance matrix (referencing chart_data_refs from gauntlet manifest)
    - Risk assessment: surfaced anomaly flags with severity and recommendation
  - [x]Every string in the narrative MUST reference a specific `per_stage_metric_id` or `chart_data_ref` from the gauntlet manifest — use format `[metric:{metric_id}]` or `[chart:{chart_ref}]`
  - [x]Reuse `NarrativeResult` dataclass from `analysis/models.py`
  - [x]Test: `test_narrative_cites_metric_ids()`, `test_narrative_no_ungrounded_claims()`, `test_narrative_green_candidate()`, `test_narrative_red_candidate()`

- [x] **Task 7: Implement two-pass evidence pack builder** (AC: #4, #8, #10)
  - [x]Create `src/python/confidence/evidence_builder.py`
  - [x]Function: `build_triage_summary(confidence_score: ConfidenceScore, gauntlet_manifest: dict) -> TriageSummary`
    - Pass 1 (triage card): rating, composite score, headline metrics (OOS Sharpe, PBO, DSR status, max drawdown, win rate, profit factor), dominant edge description, top 3 risks, optional delta vs baseline (only when baseline exists — e.g., buy-and-hold benchmark or prior optimization run)
  - [x]Function: `build_decision_trace(confidence_score: ConfidenceScore, config: ConfidenceConfig, gauntlet_manifest: dict) -> DecisionTrace`
    - Records all gate definitions and thresholds used (snapshot from config at scoring time)
    - Records PASS/FAIL with actual values per gate
    - Includes `confidence_config_hash` (hash of scoring config) and `validation_config_hash` (from gauntlet manifest)
    - Includes `research_brief_versions` from gauntlet manifest for provenance
  - [x]Function: `build_evidence_pack(candidate_id: int, confidence_score: ConfidenceScore, triage_summary: TriageSummary, decision_trace: DecisionTrace, gauntlet_manifest: dict, anomaly_report: AnomalyReport, narrative: NarrativeResult, visualization_refs: dict[str, str]) -> ValidationEvidencePack`
    - Assembles the complete evidence pack with all fields
    - Includes per_stage_results from gauntlet manifest (walk_forward, cpcv, perturbation, monte_carlo, regime)
    - Includes metadata: optimization_run_id, total_optimization_trials, candidate_rank, confidence_config_hash, validation_config_hash, scored_at timestamp
  - [x]Function: `persist_evidence_pack(evidence_pack: ValidationEvidencePack, output_dir: Path) -> Path`
    - Write as JSON via `crash_safe_write` from `artifacts/storage.py`
    - Path: `{artifacts_root}/{strategy_id}/v{NNN}/validation/evidence-pack-candidate-{id}.json`
    - Also write triage summary separately: `evidence-triage-candidate-{id}.json` for fast operator scanning
  - [x]Test: `test_triage_summary_under_60s_content()`, `test_decision_trace_completeness()`, `test_evidence_pack_round_trip()`, `test_crash_safe_persistence()`

- [x] **Task 8: Implement visualization data preparation** (AC: #11)
  - [x]Create `src/python/confidence/visualization.py`
  - [x]Function: `prepare_equity_curve_chart(gauntlet_manifest: dict) -> dict` — per-fold equity curves + aggregate, referencing Arrow IPC chart_data_refs
  - [x]Function: `prepare_walk_forward_chart(gauntlet_manifest: dict) -> dict` — per-window OOS Sharpe/PF with temporal markers (FR36, FR37)
  - [x]Function: `prepare_sensitivity_heatmap(gauntlet_manifest: dict) -> dict` — parameter name × perturbation level → metric change matrix
  - [x]Function: `prepare_monte_carlo_distribution(gauntlet_manifest: dict) -> dict` — PnL distribution from bootstrap/permutation/stress with confidence intervals
  - [x]Function: `prepare_regime_breakdown(gauntlet_manifest: dict) -> dict` — volatility tercile × session matrix with Sharpe, win rate, trade count
  - [x]Function: `prepare_all_visualizations(gauntlet_manifest: dict) -> dict[str, str]` — returns visualization_refs dict mapping chart names to Arrow IPC artifact paths from `chart_data_refs` in the gauntlet manifest. Validates referenced paths exist and assembles the ref map — does NOT read or transform Arrow data
  - [x]Individual `prepare_*` functions extract layout metadata (axis labels, series names, chart titles) from the gauntlet manifest's `per_stage_summaries` — NOT by reading Arrow IPC files. Actual chart rendering is Epic 4 (Dashboard)
  - [x]Test: `test_equity_curve_chart_structure()`, `test_walk_forward_temporal_markers()`, `test_sensitivity_heatmap_dimensions()`, `test_monte_carlo_confidence_intervals()`, `test_regime_breakdown_insufficient_trades_handling()`

- [x] **Task 9: Implement confidence scoring orchestrator** (AC: #1–#11)
  - [x]Create `src/python/confidence/orchestrator.py`
  - [x]Class: `ConfidenceOrchestrator`
    ```python
    class ConfidenceOrchestrator:
        def __init__(self, config: ConfidenceConfig):
            ...

        def score_all_candidates(
            self,
            gauntlet_results_dir: Path,
            optimization_manifest: dict,
            output_dir: Path,
        ) -> Path:
            """Score all candidates, persist each evidence pack immediately, return aggregate manifest path."""

        def score_single_candidate(
            self,
            candidate_manifest: dict,
            gauntlet_manifest: dict,
        ) -> ValidationEvidencePack:
            """Full pipeline: gates → score → anomaly → narrative → viz → evidence pack."""

        def _load_gauntlet_manifests(
            self, gauntlet_results_dir: Path
        ) -> list[dict]:
            """Load per-candidate gauntlet manifests from results directory."""

        def _persist_all_results(
            self,
            evidence_packs: list[ValidationEvidencePack],
            output_dir: Path,
        ) -> Path:
            """Write all evidence packs + summary manifest."""
    ```
  - [x]The orchestrator processes candidates sequentially (no parallelism needed — scoring is lightweight CPU work, not Rust dispatch)
  - [x]After scoring all candidates, writes:
    - Per-candidate evidence pack JSON (full)
    - Per-candidate triage summary JSON (60-second card)
    - Aggregate scoring manifest JSON with stable schema: `{optimization_run_id, confidence_config_hash, scored_at, candidates: [{candidate_id, rating, composite_score, hard_gates_passed, triage_summary_path, evidence_pack_path}]}` sorted by composite score descending. This schema is the contract for Story 5.7 E2E proof and future dashboard consumers
  - [x]Structured logging via `get_logger("confidence.orchestrator")` (D6)
  - [x]Test: `test_orchestrator_scores_multiple_candidates()`, `test_orchestrator_persists_all_artifacts()`, `test_orchestrator_handles_short_circuited_candidates()`

- [x] **Task 10: Extend pipeline state machine and /pipeline skill** (AC: #9, #10)
  - [x]Add `SCORING = "scoring"` and `SCORING_COMPLETE = "scoring-complete"` to `PipelineStage` enum in `src/python/orchestrator/pipeline_state.py`
  - [x]Add transitions: `VALIDATION_COMPLETE -> SCORING` (automatic), `SCORING -> SCORING_COMPLETE` (automatic), `SCORING_COMPLETE -> next_stage` (gated — operator review)
  - [x]Add `scoring-complete` to `gated_stages` (operator must review evidence packs before advancing)
  - [x]Create `src/python/confidence/executor.py`:
    - `ConfidenceExecutor` implementing `StageExecutor` protocol from `orchestrator/stage_runner.py` (same interface as Epic 3 executors and Story 5.4's `ValidationExecutor`)
    - Loads gauntlet results from previous stage artifacts
    - Invokes `ConfidenceOrchestrator.score_all_candidates()`
    - Returns scored evidence packs as stage output
  - [x]Extend `/pipeline` skill (Story 3.8 patterns) with "Review Optimization Results" operation:
    - Load triage summaries for all candidates
    - Present candidates sorted by composite score
    - Show: candidate_id, rating (color-coded), composite score, headline metrics, top risks
    - Allow operator: `accept {id}` (advance to next stage), `reject {id}` (record rejection + reason), `refine` (request re-optimization), `deep {id}` (load full evidence pack for 15-minute review)
    - Record operator decision in a separate `operator-review-candidate-{id}.json` artifact (append-only, does NOT mutate the immutable evidence pack)
  - [x]Test: `test_pipeline_state_scoring_stages()`, `test_scoring_executor_protocol()`, `test_operator_accept_decision()`, `test_operator_reject_decision()`

- [x] **Task 11: Write integration tests** (AC: #1–#11)
  - [x]Create `src/python/tests/test_confidence/test_integration.py`
  - [x]`test_full_scoring_pipeline()` — mock gauntlet manifest → score → evidence pack → persist → verify all artifacts
  - [x]`test_red_candidate_full_flow()` — candidate fails PBO gate → RED rating → evidence pack still assembled with failure reason
  - [x]`test_green_candidate_full_flow()` — candidate passes all gates with strong scores → GREEN → complete evidence pack
  - [x]`test_yellow_marginal_candidate()` — passes gates but low composite → YELLOW with appropriate risk warnings
  - [x]`test_multiple_candidates_ranked()` — 3+ candidates scored → sorted by composite → triage summaries generated
  - [x]`test_short_circuited_candidate_handling()` — candidate short-circuited in gauntlet (PBO > 0.40) → still gets RED evidence pack with available data
  - [x]`test_evidence_pack_two_pass_completeness()` — triage summary has all required fields; full pack has all required fields
  - [x]`test_deterministic_scoring()` — same gauntlet manifest + same config → identical scores and evidence packs (FR18)
  - [x]Create test fixtures in `src/python/tests/fixtures/gauntlet_output/`:
    - `gauntlet_manifest_green.json` — candidate with strong metrics
    - `gauntlet_manifest_yellow.json` — candidate with marginal metrics
    - `gauntlet_manifest_red.json` — candidate with PBO > 0.40
    - `gauntlet_manifest_short_circuited.json` — candidate short-circuited after CPCV

## Dev Notes

### Architecture Constraints

- **D11 (AI Analysis Layer):** Deterministic-first architecture — all confidence scores, anomaly detection, and narrative generation are pure deterministic Python code. No LLM dependencies. No stochastic components in the scoring pipeline. Narratives are template-driven from computed statistics. Two-pass evidence packs (60s triage + 5-15min deep review). DSR mandatory for >10 candidates. PBO ≤ 0.40 recommended gate. Tiered reproducibility (A/B/C).
- **D2 (Storage):** All artifacts written as JSON via `crash_safe_write` from `artifacts/storage.py` (`.partial` → `fsync` → `os.replace`). Visualization data references Arrow IPC artifact paths from Story 5.4 — confidence scoring does NOT re-read or copy Arrow IPC data, only references the paths.
- **D3 (Pipeline Orchestration):** Confidence scoring is a distinct pipeline stage (SCORING). The state machine transitions automatically from VALIDATION_COMPLETE. Scoring-complete is a gated stage requiring operator review.
- **D6 (Logging):** Structured JSON via `get_logger("confidence.xxx")` from `logging_setup/setup.py`. Schema: `{ts, level, runtime, component, stage, strategy_id, msg, ctx}`.
- **D9 (Operator Dialogue):** Operator reviews candidates via `/pipeline` skill. The evidence pack is the interface between the system and the operator's decision.
- **NFR4 (Memory Budget):** Confidence scoring is lightweight — no Rust dispatch, no large data loading. The gauntlet manifest JSON and per-stage summaries are small (< 1MB per candidate). No memory budget concerns for this story.
- **FR41 (No Profitability Gate):** A candidate with negative OOS Sharpe can still be rated GREEN if all validation metrics are strong. The scoring system evaluates robustness and validity, not profitability.
- **FR34 Implementation Location:** This story implements FR34 confidence scoring in Python, not Rust. The architecture tree mentions `validator/confidence.rs` but confidence scoring here is lightweight deterministic aggregation over JSON manifests — Python is the simpler fit. If architecture is updated to formalize this, reference this story as the origin.
- **Evidence Pack Immutability:** Evidence packs are immutable once written. Operator review decisions (accept/reject/refine with rationale) are stored in a separate `operator-review-candidate-{id}.json` artifact to preserve the boundary between machine-generated evidence and human judgment.
- **Population Anomaly Gating:** Cross-candidate population-level anomaly tests require statistical significance. With V1's expected 5-10 promoted candidates, these tests are not meaningful. Gated behind `min_population_size` config (default: 20). Per-candidate anomaly detectors always run.

### Upstream Contract: Story 5.4 Gauntlet Manifest

Story 5.5 is primarily an **aggregation, scoring, and presentation layer** consuming Story 5.4's output. It adds deterministic scoring logic (gates, weighted composite) and per-candidate anomaly detection, but MUST NOT recompute any validation-stage statistics. The gauntlet manifest provides:

| Field | Source | How 5.5 Uses It |
|-------|--------|-----------------|
| `optimization_run_id` | Story 5.3 manifest | Lineage tracing in evidence pack |
| `total_optimization_trials` | Story 5.3 manifest | DSR context (total trials, not just promoted count) |
| `candidate_rank` | Story 5.3 promoted list | Composite score context |
| `per_stage_metric_ids` | Each validator output | Cited references in narrative (every claim must cite) |
| `gate_results` | Gauntlet orchestrator | Hard gate pass/fail for RED/YELLOW/GREEN |
| `chart_data_refs` | Arrow IPC artifact paths | Chart-ready data paths for visualization |
| `config_hash` | Validation config | Reproducibility proof in decision trace |
| `research_brief_versions` | Config provenance | Traceability in decision trace |

If this story finds itself recomputing statistics that should be in the manifest, that is a signal the Story 5.4 contract is incomplete — file a follow-up rather than computing locally.

**Expected gauntlet manifest JSON structure** (per-candidate, from `validation/results.py:write_gauntlet_manifest`):
```json
{
  "candidate_id": 42,
  "optimization_run_id": "opt_20260322_abc123",
  "total_optimization_trials": 5000,
  "candidate_rank": 3,
  "dataset_hash": "abc123",
  "strategy_spec_hash": "def456",
  "config_hash": "ghi789",
  "validation_config_hash": "jkl012",
  "research_brief_versions": {"5A": "v1", "5B": "v1", "5C": "v1"},
  "gate_results": {
    "pbo_value": 0.18,
    "pbo_passed": true,
    "dsr_passed": true,
    "dsr_value": 2.31,
    "short_circuited": false,
    "hard_gate_failures": []
  },
  "per_stage_metric_ids": {
    "walk_forward": "wf_metrics_cand42",
    "cpcv": "cpcv_metrics_cand42",
    "perturbation": "pert_metrics_cand42",
    "monte_carlo": "mc_metrics_cand42",
    "regime": "regime_metrics_cand42"
  },
  "per_stage_summaries": {
    "walk_forward": {"median_oos_sharpe": 0.85, "window_count": 10, "negative_windows": 2},
    "cpcv": {"pbo": 0.18, "mean_oos_sharpe": 0.72, "combination_count": 45},
    "perturbation": {"max_sensitivity": 0.23, "mean_sensitivity": 0.11, "cliff_count": 0},
    "monte_carlo": {"bootstrap_ci_lower": 0.15, "stress_survived": true, "permutation_p_value": 0.03},
    "regime": {"weakest_sharpe": 0.21, "strongest_sharpe": 1.45, "insufficient_buckets": 1}
  },
  "chart_data_refs": {
    "equity_curves": "artifacts/.../validation/equity-curves-cand42.arrow",
    "walk_forward_windows": "artifacts/.../validation/wf-windows-cand42.arrow",
    "perturbation_results": "artifacts/.../validation/perturbation-cand42.arrow",
    "monte_carlo_results": "artifacts/.../validation/mc-results-cand42.arrow",
    "regime_results": "artifacts/.../validation/regime-cand42.arrow"
  }
}
```
The `validation_summary` Arrow IPC schema (from `contracts/arrow_schemas.toml`) provides: `candidate_id, walk_forward_sharpe, pbo, dsr, perturbation_max_sensitivity, mc_bootstrap_ci_lower, mc_stress_survived, regime_weakest_sharpe, hard_gate_failures, short_circuited`.

### Downstream: Story 5.7 E2E Proof

Story 5.7 runs the full pipeline including confidence scoring. The evidence packs produced here must be consumable by the E2E proof to verify the complete optimization → validation → scoring → operator review flow.

### Key Data Flow

```
Story 5.4 output (gauntlet_results/ directory)
    |
    v
ConfidenceExecutor.execute() loads gauntlet manifests
    |
    v
ConfidenceOrchestrator.score_all_candidates()
    |
    +-- For each candidate:
    |   +-- gates.evaluate_hard_gates() → list[GateResult]
    |   +-- scorer.compute_component_scores() → list[ComponentScore]
    |   +-- scorer.compute_composite_score() → float
    |   +-- scorer.assign_rating() → CandidateRating
    |   +-- Build ConfidenceScore
    |
    +-- anomaly_layer.run_layer_a(all_candidates) → silent scores
    +-- anomaly_layer.run_layer_b(all_candidates, layer_a) → surfaced anomalies
    |
    +-- For each candidate:
    |   +-- narrative_engine.generate_confidence_narrative() → NarrativeResult
    |   +-- visualization.prepare_all_visualizations() → viz refs
    |   +-- evidence_builder.build_triage_summary() → TriageSummary
    |   +-- evidence_builder.build_decision_trace() → DecisionTrace
    |   +-- evidence_builder.build_evidence_pack() → ValidationEvidencePack
    |   +-- evidence_builder.persist_evidence_pack() → Path
    |
    v
Aggregate scoring manifest + per-candidate evidence packs + triage summaries
    |
    v
Operator review via /pipeline → "Review Optimization Results"
```

### Short-Circuited Candidates

Story 5.4 may short-circuit candidates (e.g., PBO > 0.40 skips Monte Carlo and regime stages). When a candidate has incomplete gauntlet results:
- Hard gate evaluation still works (the failing gate is recorded)
- Missing component scores default to 0.0 with a note "stage skipped due to {gate_name} failure"
- Rating is RED (hard gate failed)
- Evidence pack is still assembled with available data + clear documentation of why stages were skipped
- This supports operator understanding of WHY the candidate failed

### Performance Considerations

- Confidence scoring is CPU-lightweight (JSON processing, simple arithmetic). No Rust dispatch needed.
- All heavy computation was done in Stories 5.3 (optimization) and 5.4 (validation gauntlet).
- Memory footprint: gauntlet manifest JSON (~10KB per candidate) × number of candidates (typically 5-10 promoted).
- The two-pass evidence pack design enables fast operator scanning: Pass 1 triage summaries are small JSON files that can be loaded and displayed instantly.

### Windows Compatibility

- Use `pathlib.Path` for all path operations (forward/backward slash agnostic)
- Use `os.replace` (not `os.rename`) for atomic file operations on Windows
- The crash-safe write pattern from `artifacts/storage.py` already handles Windows compatibility

### What to Reuse from Story 3.7 (AI Analysis Layer)

| Component | From Story 3.7 | How to Reuse |
|-----------|----------------|--------------|
| `AnomalyType` enum | `analysis/models.py` | **EXTEND** — add new types (IS_OOS_DIVERGENCE, REGIME_CONCENTRATION, PERTURBATION_CLIFF_CLUSTER, WALK_FORWARD_DEGRADATION, MONTE_CARLO_TAIL_RISK) |
| `AnomalyFlag`, `AnomalyReport` | `analysis/models.py` | **REUSE directly** — same dataclass for both layers |
| `NarrativeResult` | `analysis/models.py` | **REUSE directly** — same structure for confidence narrative |
| `Severity` enum | `analysis/models.py` | **REUSE directly** |
| `AnalysisError` exception | `analysis/models.py` | **REUSE** — raise with stage="confidence.{subcomponent}" |
| `crash_safe_write` | `artifacts/storage.py` | **REUSE directly** for all artifact persistence |
| `get_logger()` | `logging_setup/setup.py` | **REUSE** with component="confidence.xxx" |
| `compute_metrics()` | `analysis/metrics_builder.py` | **DO NOT reuse** — this story works with pre-computed gauntlet metrics, not raw trade data |
| `assemble_evidence_pack()` | `analysis/evidence_pack.py` | **DO NOT reuse** — Story 3.7's evidence pack is for single-backtest results; this story creates a different ValidationEvidencePack for multi-stage validation results |
| `generate_narrative()` | `analysis/narrative.py` | **PATTERN REFERENCE** — follow the template-driven approach but implement new templates for confidence narrative |

### What to Reuse from Story 5.4 (Validation Gauntlet)

| Component | From Story 5.4 | How to Reuse |
|-----------|----------------|--------------|
| `ValidationConfig` | `validation/config.py` | **READ** — reference stage_order and short-circuit config for understanding which stages ran |
| `GauntletResults` | `validation/gauntlet.py` | **CONSUME** — load from JSON manifest produced by Story 5.4 |
| Gauntlet manifest JSON | `validation/results.py` | **CONSUME** — primary input to confidence scoring |
| Per-stage Arrow IPC artifacts | `validation/` output dir | **REFERENCE paths only** — do not re-read; pass paths through to visualization_refs |

### Anti-Patterns to Avoid

1. **DO NOT recompute validation metrics.** Story 5.4 produces all raw metrics. If a metric is missing from the gauntlet manifest, that is a 5.4 contract gap — do not compensate by reading Arrow IPC files and computing locally.
2. **DO NOT use LLM for narrative generation.** "AI Analysis Layer" is a naming convention. All narratives are template-driven from deterministic metrics. No stochastic components.
3. **DO NOT make profitability a gate.** Negative OOS Sharpe is a finding, not a rejection criteria. FR41 requires any strategy to progress through the full pipeline.
4. **DO NOT duplicate anomaly types.** Reuse `AnomalyType` enum from `analysis/models.py` — extend it, don't create a parallel enum.
5. **DO NOT embed hardcoded thresholds.** All gate thresholds, component weights, and rating thresholds must come from `config/base.toml[confidence]`. The only exception is the normalization floor/ceiling for component scores, which are documented constants (not operator-configurable).
6. **DO NOT hold all evidence packs in memory.** Score and persist one candidate at a time, then move to the next. The aggregate manifest is built incrementally.
7. **DO NOT create a new logging pattern.** Use `get_logger("confidence.xxx")` from `logging_setup/setup.py` following D6.
8. **DO NOT skip evidence pack for RED candidates.** Every candidate gets a complete evidence pack explaining why it was rated as it was. Operator needs to see failures too.
9. **DO NOT generate visualization images.** This story prepares JSON data structures with chart-ready arrays and layout metadata. Actual rendering is Epic 4 (Dashboard). The data format must be sufficient for rendering but this story does not render.
10. **DO NOT bypass the pipeline state machine.** Confidence scoring must use `ConfidenceExecutor` implementing `StageExecutor` protocol, not run as an ad-hoc script.
11. **DO NOT assume candidates are pre-sorted.** The orchestrator sorts by composite score after scoring all candidates. Input order from gauntlet is not guaranteed.

### Project Structure Notes

**Files to CREATE:**
```
src/python/confidence/
├── __init__.py              # Public exports
├── models.py                # Task 1: Data models
├── config.py                # Task 2: Configuration loading
├── gates.py                 # Task 3: Hard gate evaluator
├── scorer.py                # Task 4: Weighted composite scorer
├── anomaly_layer.py         # Task 5: Two-tier anomaly detection
├── narrative_engine.py      # Task 6: Template-driven narrative
├── evidence_builder.py      # Task 7: Two-pass evidence pack builder
├── visualization.py         # Task 8: Visualization data preparation
├── orchestrator.py          # Task 9: Scoring orchestrator
├── executor.py              # Task 10: StageExecutor implementation

src/python/tests/test_confidence/
├── __init__.py
├── test_models.py           # Task 1: Model serialization
├── test_config.py           # Task 2: Config loading
├── test_gates.py            # Task 3: Hard gate evaluation
├── test_scorer.py           # Task 4: Composite scoring
├── test_anomaly_layer.py    # Task 5: Two-tier anomaly
├── test_narrative_engine.py # Task 6: Narrative generation
├── test_evidence_builder.py # Task 7: Evidence pack assembly
├── test_visualization.py    # Task 8: Visualization data
├── test_orchestrator.py     # Task 9: Orchestrator
├── test_integration.py      # Task 11: Integration tests

src/python/tests/fixtures/gauntlet_output/
├── gauntlet_manifest_green.json
├── gauntlet_manifest_yellow.json
├── gauntlet_manifest_red.json
├── gauntlet_manifest_short_circuited.json
```

**Files to MODIFY:**
```
src/python/analysis/models.py               # Task 5: Extend AnomalyType enum with 5 new types
src/python/orchestrator/pipeline_state.py   # Task 10: Add SCORING + SCORING_COMPLETE stages
config/base.toml                             # Task 2: Add [confidence] section
config/schema.toml                           # Task 2: Add confidence schema validation
src/python/confidence/__init__.py            # Public API exports
```

**Files to READ (not modify):**
```
src/python/analysis/evidence_pack.py        # Pattern reference for evidence assembly
src/python/analysis/narrative.py            # Pattern reference for template-driven narrative
src/python/analysis/anomaly_detector.py     # Pattern reference for anomaly detection
src/python/artifacts/storage.py             # crash_safe_write pattern to reuse
src/python/logging_setup/setup.py           # get_logger() for structured logging
contracts/arrow_schemas.toml                # Arrow schemas for validation artifacts
config/base.toml                             # Existing config structure to extend
```

### References

- [Source: _bmad-output/planning-artifacts/architecture.md — D11 AI Analysis Layer (deterministic-first, two-pass evidence packs, DSR/PBO gates)]
- [Source: _bmad-output/planning-artifacts/architecture.md — D2 Storage (Arrow IPC artifacts, crash-safe writes)]
- [Source: _bmad-output/planning-artifacts/architecture.md — D3 Pipeline Orchestration (stage transitions)]
- [Source: _bmad-output/planning-artifacts/architecture.md — D6 Logging (structured JSON)]
- [Source: _bmad-output/planning-artifacts/architecture.md — D9 Operator Dialogue Control]
- [Source: _bmad-output/planning-artifacts/architecture.md — NFR4 Memory Budget]
- [Source: _bmad-output/planning-artifacts/architecture.md — NFR5 Checkpointing]
- [Source: _bmad-output/planning-artifacts/prd.md — FR34 (aggregated confidence score RED/YELLOW/GREEN)]
- [Source: _bmad-output/planning-artifacts/prd.md — FR35 (IS vs OOS divergence flagging)]
- [Source: _bmad-output/planning-artifacts/prd.md — FR36 (temporal split visualization)]
- [Source: _bmad-output/planning-artifacts/prd.md — FR37 (walk-forward window visualization)]
- [Source: _bmad-output/planning-artifacts/prd.md — FR16-FR17 (narrative + anomaly detection)]
- [Source: _bmad-output/planning-artifacts/prd.md — FR25 (chart-led visualization)]
- [Source: _bmad-output/planning-artifacts/prd.md — FR39 (evidence pack review at each stage)]
- [Source: _bmad-output/planning-artifacts/prd.md — FR41 (no profitability gate)]
- [Source: _bmad-output/planning-artifacts/prd.md — FR58 (versioned artifact persistence)]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 5 Story 5.5 (acceptance criteria)]
- [Source: _bmad-output/planning-artifacts/research/briefs/5C/ — Validation gauntlet configuration, confidence score aggregation]
- [Source: _bmad-output/planning-artifacts/research/briefs/3C/ — Evidence pack specification, anomaly detection toolkit, narrative architecture]
- [Source: _bmad-output/implementation-artifacts/5-4-validation-gauntlet.md — Downstream Contract (Story 5.5 Interface)]
- [Source: _bmad-output/implementation-artifacts/5-4-validation-gauntlet.md — Data flow, anti-patterns]
- [Source: _bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md — Reusable models, patterns]
- [Source: src/python/analysis/models.py — Existing AnomalyType, AnomalyFlag, NarrativeResult, EvidencePack]
- [Source: src/python/analysis/evidence_pack.py — assemble_evidence_pack() pattern]
- [Source: src/python/artifacts/storage.py — crash_safe_write pattern]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Debug Log References
- Fixed yellow test fixture values to produce YELLOW range (composite 0.40-0.70)
- Fixed 3 pre-existing regression tests after adding SCORING/SCORING_COMPLETE stages to PipelineStage enum

### Completion Notes List
- Task 1: Created 10 dataclasses with full to_json/from_json round-trip serialization (12 tests)
- Task 2: Added [confidence] section to base.toml, schema.toml validation entries, config loader with weight sum validation (6 tests)
- Task 3: Implemented DSR/PBO/cost-stress hard gates reading from gauntlet manifest (13 tests)
- Task 4: Implemented 6-component weighted scorer with normalization and rating assignment (15 tests)
- Task 5: Extended AnomalyType enum with 5 new types, implemented Layer A (5 per-candidate detectors) + Layer B (surfacing threshold + academic triggers), gated population tests (9 tests)
- Task 6: Template-driven narrative with metric citations [metric:...] format (4 tests)
- Task 7: Two-pass builder (triage + full pack) with crash-safe persistence (4 tests)
- Task 8: Visualization data preparation extracting layout metadata from manifests (9 tests)
- Task 9: ConfidenceOrchestrator processing candidates sequentially with incremental persistence (3 tests)
- Task 10: Added SCORING/SCORING_COMPLETE to PipelineStage, transitions, ConfidenceExecutor, operator review recording (9 tests)
- Task 11: Full integration tests with 4 fixture types (green/yellow/red/short-circuited) (8 tests)
- Live tests: 3 @pytest.mark.live tests exercising real config, real file I/O, and operator review workflow
- All 1425 tests pass (0 regressions after fixing 3 pre-existing tests)

### Change Log
- 2026-03-23: Story 5.5 implementation complete — all 11 tasks done, 87 tests (84 unit + 3 live)

### File List
**Created:**
- src/python/confidence/__init__.py
- src/python/confidence/models.py
- src/python/confidence/config.py
- src/python/confidence/gates.py
- src/python/confidence/scorer.py
- src/python/confidence/anomaly_layer.py
- src/python/confidence/narrative_engine.py
- src/python/confidence/evidence_builder.py
- src/python/confidence/visualization.py
- src/python/confidence/orchestrator.py
- src/python/confidence/executor.py
- src/python/tests/test_confidence/__init__.py
- src/python/tests/test_confidence/test_models.py
- src/python/tests/test_confidence/test_config.py
- src/python/tests/test_confidence/test_gates.py
- src/python/tests/test_confidence/test_scorer.py
- src/python/tests/test_confidence/test_anomaly_layer.py
- src/python/tests/test_confidence/test_narrative_engine.py
- src/python/tests/test_confidence/test_evidence_builder.py
- src/python/tests/test_confidence/test_visualization.py
- src/python/tests/test_confidence/test_orchestrator.py
- src/python/tests/test_confidence/test_executor.py
- src/python/tests/test_confidence/test_integration.py
- src/python/tests/test_confidence/test_live.py
- src/python/tests/fixtures/gauntlet_output/gauntlet_manifest_green.json
- src/python/tests/fixtures/gauntlet_output/gauntlet_manifest_yellow.json
- src/python/tests/fixtures/gauntlet_output/gauntlet_manifest_red.json
- src/python/tests/fixtures/gauntlet_output/gauntlet_manifest_short_circuited.json

**Modified:**
- src/python/analysis/models.py (added 5 AnomalyType enum values)
- src/python/orchestrator/pipeline_state.py (added SCORING, SCORING_COMPLETE stages + transitions)
- config/base.toml (added [confidence] section + scoring-complete to gated_stages)
- config/schema.toml (added confidence schema validation entries)
- src/python/tests/test_orchestrator/test_gate_manager.py (updated terminal stage + progress tests)
- src/python/tests/test_orchestrator/test_pipeline_state.py (updated stage enum + terminal stage tests)
- src/python/tests/test_orchestrator/test_regression.py (updated terminal progress test)
