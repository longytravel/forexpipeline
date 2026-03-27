# Story 5.1: ClaudeBackTester Optimizer & Validation Pipeline Review

Status: done

<!-- Validation: checklist pending -->
<!-- Scope: Research story — output is a research artifact, NOT code. Do NOT write optimizer code. -->
<!-- Pattern: Follows same structure as Story 3-1 (backtest engine review) and Story 2-1 (strategy evaluator review) -->
<!-- Prior research: Optimization methodology research (2026-03-18) already completed — this story reviews the BASELINE code against those findings -->

## Story

As the operator,
I want the existing ClaudeBackTester optimizer and validation pipeline reviewed against our opaque-optimizer architecture,
so that I know which optimization patterns, validation logic, and confidence scoring to keep, adapt, or replace before writing any code.

## Acceptance Criteria

1. **Given** the ClaudeBackTester codebase is accessible
   **When** the optimizer modules are reviewed — 5-stage parameter locking, evaluation dispatch, candidate tracking, convergence logic
   **Then** a component verdict table is produced with keep/adapt/replace per component, with rationale — specifically noting how the 5-stage model hides parameter dependencies
   _(Ref: D3 opaque optimizer, FR23-FR24)_

2. **Given** the optimizer review is complete
   **When** the existing validation pipeline is reviewed — walk-forward implementation, CPCV implementation (if any), Monte Carlo simulation, confidence scoring formula, regime analysis
   **Then** each validation component gets a verdict: keep/adapt/replace with rationale
   _(Ref: FR29-FR37, D11 candidate compressor)_

3. **Given** the validation pipeline review is complete
   **When** the existing candidate selection logic is documented
   **Then** the artifact snapshots how ClaudeBackTester currently ranks, filters, and presents optimization results, with an MVP disposition (defer/adapt/drop) per capability — noting that FR26-FR28 are Growth-phase per PRD, not V1
   _(Ref: FR26-FR28 — Growth phase; for V1, document baseline behavior only, determine minimal operator-facing candidate review)_

4. **Given** the optimizer code is available
   **When** parameter grouping or staging patterns in the baseline are documented
   **Then** the artifact records their actual behavior — do they work, do they hide dependencies, what broke in March 2026 testing
   _(Ref: optimization-methodology-research-summary.md — staged model critique)_

5. **Given** the optimizer interacts with the Rust evaluator
   **When** the current optimizer's interface with the Rust evaluator is documented
   **Then** the artifact covers how candidates are dispatched, how scores are returned, batch size handling, parallelism model
   _(Ref: D1 multi-process Arrow IPC, D3 ask/tell interface)_

6. **Given** all reviews are complete
   **When** capabilities in the baseline optimizer not covered by FR23-FR28, or the baseline validation pipeline not covered by FR29-FR37, are identified
   **Then** the artifact documents undocumented capabilities and whether they should be carried forward
   _(Ref: PRD FR23-FR37)_

7. **Given** all findings are compiled
   **When** findings contradict D1/D3/D11/D14 assumptions, reveal an incompatible baseline contract, or identify a cheaper compatible path not considered in the architecture
   **Then** the Architecture document is updated with review-justified amendments (or a note confirming no changes needed)
   _(Ref: architecture.md D3, D11. Threshold: only amend if baseline evidence contradicts architectural assumptions or reveals a materially better approach)_

8. **Given** all optimizer and validation components are reviewed
   **When** determinism and reproducibility characteristics of the baseline are assessed
   **Then** the artifact documents whether baseline optimization/validation captures enough input state, config, and per-run artifacts to reproduce a run within tolerance — and identifies gaps for the new system
   _(Ref: PRD "Deterministic reproducibility — Fix", FR18, FR42)_

## Tasks / Subtasks

- [ ] **Task 1: Locate and inventory ClaudeBackTester optimizer modules** (AC: #1, #4)
  - [ ] Clone or locate ClaudeBackTester repo (see `reference_github_repo.md` memory for URL). Search for optimizer entry point — likely `optimizer/` or `optimization/` directory in the Python layer. Record the root module path.
  - [ ] Map the 5-stage parameter locking implementation — grep for `stage`, `phase`, `lock`, `group` in optimizer code. Document which files and functions control stage transitions.
  - [ ] Document the evaluation dispatch mechanism — search for subprocess calls, IPC code, or Rust FFI bindings that send parameter sets to the evaluator. Record function signatures.
  - [ ] Identify candidate tracking data structures — search for classes/dicts storing candidate results (e.g., `population`, `candidates`, `results`). Document fields and persistence format.
  - [ ] Document convergence logic — search for `converge`, `stopping`, `max_gen`, `tolerance`, `budget` to find stopping criteria, population sizing, generation count limits
  - [ ] Record parameter grouping definitions — search for the 5-group names (Signal / Time / Risk / Management / Refinement) and document how boundaries are defined and enforced

- [ ] **Task 2: Analyze 5-stage model dependency hiding** (AC: #1, #4)
  - [ ] For each stage boundary, document which parameters are locked and which are free
  - [ ] Identify specific cross-stage parameter interactions that cannot be discovered (e.g., SL size ↔ trailing behavior, TP size ↔ partial close)
  - [ ] Reference March 2026 testing evidence from `_bmad-output/planning-artifacts/research/briefs/optimization/optimization-methodology-research-summary.md` Section 2: GA result (IS quality 35.72, OOS Sharpe -5.13, population collapsed) showing staged optimization finds deeper local optima that don't generalize
  - [ ] Compare against the optimization-methodology-research-summary.md finding: "Signal + Time separation is defensible; Risk + Management separation is NOT"
  - [ ] Document whether the 5-stage model is hardcoded or configurable

- [ ] **Task 3: Review validation pipeline components** (AC: #2)
  - [ ] Walk-forward implementation: search ClaudeBackTester for `walk_forward`, `wfo`, `rolling_window`. Document window count, anchored vs rolling, purge/embargo gaps, train/test split ratios. Compare against `src/rust/crates/backtester/src/fold.rs` FoldConfig.
  - [ ] CPCV implementation: search for `cpcv`, `combinatorial`, `purged_cv`, `pbo`. Does it exist? If so: N groups, k test groups, purge sizing, PBO calculation formula.
  - [ ] Monte Carlo simulation: search for `monte_carlo`, `bootstrap`, `permutation`, `stress`. Document bootstrap method (randomize trade order?), permutation (shuffle returns?), stress testing (spread/slippage multipliers?).
  - [ ] Confidence scoring formula: search for `confidence`, `score`, `red`, `yellow`, `green`, `aggregate`. Extract exact formula, input metrics, thresholds, weighting methodology.
  - [ ] Regime analysis: search for `regime`, `volatility`, `session`, `market_condition`. Document volatility bucketing method, session filtering, minimum trade count thresholds.

- [ ] **Task 4: Snapshot baseline candidate selection logic** (AC: #3)
  - [ ] How does ClaudeBackTester rank candidates after optimization? (metric used, sorting, filtering)
  - [ ] Does it cluster similar parameter sets? (algorithm, distance metric, merge strategy)
  - [ ] How many candidates are presented to the operator? (fixed count or threshold-based?)
  - [ ] Is there a diversity archive or MAP-Elites style mechanism?
  - [ ] What equity curve quality metrics are computed? (R², K-Ratio, Ulcer Index, Serenity Ratio, or simpler metrics?)
  - [ ] **MVP disposition:** For each capability, mark defer/adapt/drop — FR26-FR28 are Growth-phase per PRD. For V1, determine what minimal operator-facing candidate review is sufficient (e.g., simple top-N by objective score)

- [ ] **Task 5: Document optimizer-evaluator interface** (AC: #5)
  - [ ] IPC mechanism: how does the Python optimizer communicate with the Rust evaluator?
  - [ ] Batch dispatch: does it send individual candidates or batches? What batch size?
  - [ ] Score return format: aggregated single score or per-fold scores?
  - [ ] Parallelism model: how many concurrent evaluations? Thread pool or process pool?
  - [ ] Fold handling: does the evaluator accept fold boundaries as input, or are folds managed in Python?
  - [ ] Compare against D1 (multi-process Arrow IPC) and the existing `src/rust/crates/backtester/src/fold.rs` fold configuration

- [ ] **Task 6: Identify undocumented capabilities** (AC: #6)
  - [ ] Scan optimizer code for features not covered by FR23-FR28
  - [ ] Scan validation pipeline for features not covered by FR29-FR37
  - [ ] For each undocumented capability: describe it, assess its value, recommend keep/drop/defer

- [ ] **Task 7: Produce component verdict table and research artifact** (AC: #1-#7)
  - [ ] Create verdict table with columns: Component | Verdict (keep/adapt/replace) | Rationale | Effort Estimate | Downstream Impact
  - [ ] Organize findings into the Research Artifact Structure (see Dev Notes)
  - [ ] Cross-reference each verdict against: optimization-methodology-research-summary.md and architecture decisions D3/D11. Research briefs 5A/5B/5C may be used as optional context but are NOT required inputs — those are Story 5.2's domain
  - [ ] Ensure each verdict explicitly states how it aligns with or departs from the opaque-optimizer principle
  - [ ] Produce a Baseline-to-Target Compatibility Matrix (see Appendix E in Research Artifact Structure) covering: evaluator contract, per-fold scoring, checkpoint/resume, artifact outputs, operator evidence, D11 handoff suitability
  - [ ] Write downstream handoff notes for Stories 5.2-5.N with: (a) questions answered, (b) unanswered research questions, (c) non-negotiable contract requirements, (d) baseline behaviors that must NOT be carried forward

- [ ] **Task 8: Evaluate architecture document for updates** (AC: #7)
  - [ ] Compare findings against D3 (pipeline orchestration — optimizer as opaque state)
  - [ ] Compare findings against D11 (AI analysis layer — candidate compressor). Frame as: "what baseline outputs can feed D11?" not "can baseline candidate selection serve D11 as-is?"
  - [ ] If baseline evidence contradicts D1/D3/D11/D14 assumptions or reveals a cheaper compatible path: propose specific amendments with rationale
  - [ ] If no contradictions found: document confirmation note with reasoning
  - [ ] Verify `src/rust/crates/optimizer/` crate's evaluation-engine role (per D3) is compatible with baseline evaluator interface findings — do NOT propose optimizer crate design changes beyond contract compatibility

- [ ] **Task 9: Verify research completeness for downstream usefulness**
  - [ ] `verify_verdict_table_covers_all_optimizer_components` — every module from Task 1 inventory appears in verdict table with non-empty Verdict, Rationale, Effort Estimate, and Downstream Impact columns
  - [ ] `verify_validation_components_all_reviewed` — walk-forward, CPCV, Monte Carlo, confidence scoring, and regime analysis each have a verdict row with keep/adapt/replace designation
  - [ ] `verify_cross_references_complete` — every verdict row cites at least one FR (FR23-FR37) and one architecture decision (D1/D3/D11/D14)
  - [ ] `verify_downstream_handoff_sufficient` — Appendix D exists and Story 5.2 can choose research topics without reopening baseline code. Must contain: (a) questions answered, (b) unanswered research questions, (c) algorithm selection gaps, (d) "Do Not Carry Forward" items
  - [ ] `verify_reproducibility_assessment_complete` — artifact documents baseline determinism characteristics: config capture, artifact persistence, per-run reproducibility status
  - [ ] `verify_compatibility_matrix_complete` — Appendix E covers evaluator contract, per-fold scoring, checkpoint/resume, artifact outputs, operator evidence, D11 handoff suitability

- [ ] **Task 10: Assess baseline reproducibility and determinism** (AC: #8)
  - [ ] Does baseline capture optimization config (parameter ranges, population size, random seed, fold boundaries) in a reproducible artifact?
  - [ ] Does baseline persist per-run artifacts (candidate scores, convergence history, validation results) for audit?
  - [ ] Can a baseline optimization run be reproduced given the same inputs? If not, what prevents it?
  - [ ] Does the validation pipeline record enough state to reproduce its RED/YELLOW/GREEN verdict?
  - [ ] Document gaps between baseline reproducibility and the new system's requirements (FR18, FR42)

## Dev Notes

### Research Artifact Structure (10 Sections + Appendices)

The output research artifact must follow this structure:

1. **Executive Summary** — Key findings, critical decisions, overall recommendation
2. **Module Inventory** — Complete list of ClaudeBackTester optimizer + validation modules with file paths, line counts, purpose
3. **Component Verdict Table** — keep/adapt/replace per component with rationale, effort, downstream notes
4. **Optimizer Analysis** — Detailed review of 5-stage model, parameter locking, evaluation dispatch, convergence logic
5. **Validation Pipeline Analysis** — Walk-forward, CPCV, Monte Carlo, regime analysis, confidence scoring
6. **Candidate Selection Analysis** — Ranking, clustering, presentation, equity curve quality
7. **Evaluator Interface Analysis** — IPC, batching, parallelism, fold handling
8. **Gap Analysis** — Undocumented capabilities, missing FR coverage, alignment with opaque-optimizer principle
9. **March 2026 Testing Post-Mortem** — What the CMA-ES vs random search results reveal about the current optimizer
10. **Proposed Architecture Updates** — Changes to D3, D11, optimizer crate design (or confirmation no changes needed)
- **Appendix A:** Parameter group layout (all 5 stages with parameter names)
- **Appendix B:** Confidence scoring formula (exact current formula with variables)
- **Appendix C:** Cross-reference matrix — FR23-FR37 × ClaudeBackTester components
- **Appendix D:** Downstream handoff to Story 5.2 (specific questions answered, remaining questions for external research, "Do Not Carry Forward" items)
- **Appendix E:** Baseline-to-Target Compatibility Matrix (evaluator contract, per-fold scoring, checkpoint/resume, artifact outputs, operator evidence, D11 handoff suitability)
- **Appendix F:** "Do Not Carry Forward" list — baseline concepts structurally incompatible with the new system (e.g., fixed 5-stage locking if confirmed by code)

### Architecture Constraints

- **D3 (Pipeline Orchestration):** Optimizer is opaque state behind ask/tell interface. The review must assess whether ClaudeBackTester's optimizer can be adapted to this interface pattern or must be replaced
- **D11 (AI Analysis Layer):** Candidate compressor must reduce optimization output to operator-reviewable set. Review must assess whether ClaudeBackTester's candidate selection can serve this role
- **D1 (System Topology):** Multi-process with Arrow IPC. Review must document current IPC mechanism and compatibility with D1
- **D14 (Strategy Engine Crate):** Shared across backtester + optimizer. Review must assess interface compatibility
- **FR24 (Updated):** The strategy spec defines parameter ranges and conditionals; the optimizer decides internally how to structure the search. The old "strategies define their own optimization stages" framing is superseded. Review baseline staging to decide discard/adapt/isolate — do NOT reinforce the fixed-stage mental model
- **CV-inside-objective:** Primary overfitting defense (from optimization-methodology-research-summary.md). Review must document whether baseline supports per-fold scoring or only aggregated scores

### Key Prior Research to Reference

The optimization-methodology-research-summary.md (2026-03-18) already established:
- CV-inside-objective is the primary defense against overfitting — `mean(fold_scores) - λ·std(fold_scores)`
- 5-stage parameter locking is architecturally flawed (Block Coordinate Descent, hides dependencies)
- Conditional parameters reduce effective search space from 4×10^15 to 30-70M combinations
- 5 blocked time-series folds with 1% embargo (~960 bars / 40 trading days)
- Quality formula differentiation: simple metric for optimizer, composite for validation
- Three complementary tools: CV-inside-objective (during search), Walk-forward (post-opt validation), CPCV (final statistical validation)

**This story validates these findings against the actual baseline code**, not re-derives them.

### Existing Pipeline Infrastructure to Reference

The Forex Pipeline already has these relevant components built in Epics 1-3:
- `src/rust/crates/backtester/src/fold.rs` — FoldConfig with JSON boundaries `(start_bar, end_bar)` + embargo_bars
- `src/rust/crates/backtester/src/metrics.rs` — Metrics: Sharpe, Profit Factor, R², max drawdown, win_rate, etc.
- `src/rust/crates/backtester/src/engine.rs` — Backtest engine with batch evaluation readiness
- `src/rust/crates/strategy_engine/src/types.rs` — StrategySpec with OptimizationPlan (groups, dependencies, objective)
- `src/rust/crates/optimizer/` — Optimizer crate directory exists but is NOT yet implemented
- `src/python/analysis/evidence_pack.py` — Evidence pack assembly (narrative + anomalies + metrics)
- `contracts/strategy_specification.toml` — Strategy spec schema including optimization_plan with parameter groups
- `contracts/indicator_registry.toml` — Indicator registry for signal computation

### Performance Context

- Evaluation throughput: ~750 evals/sec baseline, ~350-500 effective with 5-fold CV
- Budget: 10K-100K evaluations per optimization run
- Batch size: 2048-sized batches optimal for Rust evaluator
- Memory: 64GB total, 4GB OS reserve, 60GB compute budget (D1/NFR4)

## What to Reuse from ClaudeBackTester

**Must locate and review these ClaudeBackTester components:**

| Component Area | Expected Location | What to Assess |
|---|---|---|
| Optimizer entry point | Python orchestration layer | Stage sequencing, ask/tell pattern compatibility |
| Stage definitions | Optimizer config or hardcoded | Parameter group boundaries, lock mechanism |
| Evaluation dispatch | Python-Rust bridge | Batch vs single eval, IPC mechanism |
| Candidate tracking | Optimizer state management | Data structures, ranking logic, persistence |
| Convergence logic | Optimizer loop | Stopping criteria, population management |
| Walk-forward | Validation pipeline | Window sizing, splitting, purge implementation |
| CPCV | Validation pipeline (if exists) | PBO calculation, purge/embargo, group assignment |
| Monte Carlo | Validation pipeline | Bootstrap/permutation/stress methods |
| Confidence scoring | Validation output | Formula, thresholds, RED/YELLOW/GREEN logic |
| Regime analysis | Validation pipeline | Volatility bucketing, session filtering |
| Candidate selection | Post-optimization | Ranking metrics, clustering, diversity |

**Reference:** `baseline-capability-gap-assessment-ClaudeBackTester-2026-03-13.md` has high-level verdicts (4 keep, 10 adapt, 2 replace, 1 build) — this story produces the detailed, component-level analysis.

## Anti-Patterns to Avoid

1. **Do NOT write optimizer code** — this is a research/review story. Output is a research artifact documenting findings and verdicts, not implementation.
2. **Do NOT modify architecture.md directly without documenting the rationale** — propose changes in the research artifact first, then apply only if findings clearly warrant it (AC #7).
3. **Do NOT duplicate the optimization-methodology-research-summary.md** — that research is already done. This story validates those findings against the actual ClaudeBackTester code. Reference it, don't re-derive it.
4. **Do NOT assume ClaudeBackTester's 5-stage model is correct** — research already found it architecturally flawed (Block Coordinate Descent, hides dependencies). Review the CODE to confirm or nuance this finding.
5. **Do NOT confuse ClaudeBackTester's optimizer with the Forex Pipeline optimizer crate** — ClaudeBackTester is the baseline being reviewed. The `src/rust/crates/optimizer/` directory is the NEW crate (empty). They are separate.
6. **Do NOT treat the baseline capability gap assessment as sufficient** — that assessment is high-level (4 keep/10 adapt/2 replace/1 build). This story needs component-by-component detail.
7. **Do NOT skip the evaluator interface analysis** — understanding how candidates are dispatched and scores returned is critical for the ask/tell interface design (D3).
8. **Do NOT ignore the March 2026 testing results** — the CMA-ES vs random search comparison is key evidence for the staged model critique. Document specific numbers and what they reveal.
9. **Do NOT produce verdicts without FR/architecture cross-references** — every verdict must cite which FRs it impacts and which architecture decisions it aligns with or challenges.
10. **Do NOT skip the downstream handoff to Story 5.2** — Story 5.2 (external research) depends on knowing what Story 5.1 found. The handoff must be specific: "baseline has X, we need research on Y, the gap is Z."
11. **Do NOT design candidate selection for V1 scope** — FR26-FR28 are Growth-phase per PRD ("Candidate selection pipeline" is explicitly NOT in MVP). Document baseline behavior as a snapshot, determine MVP disposition (defer/adapt/drop), but do not design around it.
12. **Do NOT let baseline staging assumptions leak into the new optimizer design** — the "Do Not Carry Forward" appendix exists to prevent flawed baseline concepts (e.g., fixed 5-stage locking) from contaminating the opaque-optimizer architecture.

### Project Structure Notes

**Research artifact output location:**
`_bmad-output/planning-artifacts/research/optimizer-validation-baseline-review.md`

**Files to READ (not modify):**
- ClaudeBackTester optimizer modules (locate via codebase search)
- ClaudeBackTester validation pipeline modules
- `_bmad-output/planning-artifacts/research/briefs/optimization/optimization-methodology-research-summary.md`
- `_bmad-output/planning-artifacts/architecture.md` (sections D3, D11, D1, D14)
- `_bmad-output/planning-artifacts/prd.md` (FR23-FR37)
- `baseline-capability-gap-assessment-ClaudeBackTester-2026-03-13.md`
- `src/rust/crates/backtester/src/fold.rs` (existing fold infrastructure)
- `src/rust/crates/backtester/src/metrics.rs` (existing metrics)
- `src/rust/crates/strategy_engine/src/types.rs` (StrategySpec with OptimizationPlan)
- `contracts/strategy_specification.toml` (optimization_plan schema)

**Files to potentially MODIFY:**
- `_bmad-output/planning-artifacts/architecture.md` — only if findings warrant D3/D11 amendments (AC #7)

**ClaudeBackTester location:** Refer to `reference_github_repo.md` memory for GitHub URL and local path.

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 5: Optimization & Validation Gauntlet, Story 5.1]
- [Source: _bmad-output/planning-artifacts/architecture.md — D3 Pipeline Orchestration, D11 AI Analysis Layer, D1 System Topology, D14 Strategy Engine Crate]
- [Source: _bmad-output/planning-artifacts/prd.md — FR23-FR28 Optimization, FR29-FR37 Validation Gauntlet, NFR1-NFR5, NFR8-NFR9]
- [Source: _bmad-output/planning-artifacts/research/briefs/optimization/optimization-methodology-research-summary.md — CV-inside-objective, staged model critique, fold design]
- [Source: _bmad-output/planning-artifacts/research/briefs/5A/ — Optimization algorithm selection research brief]
- [Source: _bmad-output/planning-artifacts/research/briefs/5B/ — Candidate selection & equity curve quality research brief]
- [Source: _bmad-output/planning-artifacts/research/briefs/5C/ — Validation gauntlet configuration research brief]
- [Source: baseline-capability-gap-assessment-ClaudeBackTester-2026-03-13.md — High-level baseline verdicts]
- [Source: _bmad-output/implementation-artifacts/3-1-claudebacktester-backtest-engine-review.md — Prior baseline review pattern]

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
