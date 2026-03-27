# Story 5.2: Optimization Algorithm, Candidate Selection & Validation Gauntlet Research

Status: done

## Story

As the **operator**,
I want optimization algorithms, candidate selection methodology, and validation gauntlet configuration researched against our specific architecture,
So that implementation stories use proven, research-backed approaches rather than guesses.

**Story Type:** research (no production code — output is a research artifact)

**Depends On:** Story 5.1 (ClaudeBackTester Optimizer & Validation Pipeline Review — produces verdict table identifying research gaps)

## Acceptance Criteria

1. **Given** Story 5.1's verdict table identifies what needs external research
   **When** the completed research briefs (5A, 5B, 5C) are synthesized against Story 5.1's findings
   **Then** a research artifact recommends: primary algorithm (from CMA-ES CMAwM, DE, TPE, hybrid candidates), Python library for batch-native ask/tell implementation with CV-inside-objective, population sizing, convergence detection, and handling of mixed parameter types (continuous, integer, categorical, conditional)
   [Ref: FR23-FR25, D3 opaque optimizer, D1 fold-aware batch evaluation]

2. **And** candidate selection research covers: equity curve quality metrics (Ulcer Index, K-Ratio, R-squared, Serenity Ratio, and others), multi-objective ranking framework, parameter space clustering methodology (algorithm, distance metric, cluster count), and diversity archive design (MAP-Elites or post-hoc)
   [Ref: FR26-FR28, D11 candidate compressor]

3. **And** validation gauntlet configuration research covers: walk-forward window sizing for forex M1 data (anchored vs rolling, number of windows, purge/embargo gaps), CPCV parameterization (N groups, k test groups, purge sizing, PBO threshold), Monte Carlo simulation parameters (sim counts for bootstrap/permutation/stress, stress levels for cost model), parameter perturbation methodology, and regime analysis configuration (volatility bucketing, session interaction, minimum trade counts)
   [Ref: FR29-FR33, FR35-FR37, D11 validation guidance]

4. **And** confidence score aggregation research covers: how to combine walk-forward + CPCV + stability + Monte Carlo + regime results into RED/YELLOW/GREEN rating, weighting methodology, hard gates vs continuous scoring, and threshold calibration
   [Ref: FR34, D11 confidence scoring]

5. **And** recommendations are compared against Architecture decisions (D3 opaque optimizer, D11 candidate compressor, D1 fold-aware batch evaluation, CV-inside-objective from optimization research) and against FR23-FR28, FR29-FR37
   [Ref: architecture.md — all D-numbers]

6. **And** reproducibility specifications are provided for all stochastic components: RNG seeding policy for CMA-ES/DE, checkpoint/resume determinism for optimization state, Monte Carlo repeatability via fixed seeds, and tolerance classification (exact vs statistical reproducibility) per component
   [Ref: FR18, NFR5, D1 deterministic evaluation]

7. **And** the DBSCAN (D11) vs HDBSCAN (5B research) discrepancy is explicitly resolved with a recommendation and, if warranted, a D11 architecture amendment proposal
   [Ref: architecture.md D11, research brief 5B]

8. **And** downstream implementation contracts are specified: optimizer I/O schema (ask/tell payloads), per-fold score fields, confidence-score breakdown schema, candidate artifact schema, required config keys, and checkpoint format — so Stories 5.3+ have concrete interfaces to implement against
   [Ref: D3 optimizer contract, D11 candidate compressor inputs]

9. **And** architecture amendment proposals are produced (if research warrants changes) as a separate appendix — actual edits to `architecture.md` are applied only after operator review of the research artifact
   [Ref: architecture.md revision protocol]

10. **And** a build plan for Stories 5.3+ is produced with: each story's scope, research-backed approach, FR coverage, architecture decisions it must follow, and MVP vs Growth classification — with a V1 fallback path for candidate selection (manual/simple promotion) so MVP stories can proceed without advanced FR26-FR28 capabilities
    [Ref: epics.md — Epic 5 story breakdown, PRD MVP scope]

## Tasks / Subtasks

- [ ] **Task 1: Load Story 5.1 Verdict Table** (AC: #1, #5)
  - [ ] **PREREQUISITE CHECK:** Verify Story 5.1's research artifact exists at `_bmad-output/planning-artifacts/research/optimizer-validation-baseline-review.md`. If it does not exist, HALT and report: "Story 5.2 depends on Story 5.1's completed research artifact. Run Story 5.1 first."
  - [ ] Read Story 5.1's completed research artifact
  - [ ] Extract the Component Verdict Table (keep/adapt/replace per component)
  - [ ] Extract Appendix D: Downstream handoff to Story 5.2 (specific research gaps identified)
  - [ ] Extract Appendix E: Baseline-to-Target Compatibility Matrix
  - [ ] Extract Appendix F: "Do Not Carry Forward" list
  - [ ] Compile the list of open questions Story 5.1 flagged for external research

- [ ] **Task 2: Synthesize Research Brief 5A — Optimization Algorithm Selection** (AC: #1)
  - [ ] Read all 6 files in `_bmad-output/planning-artifacts/research/briefs/5A/`:
    - `epic5-brief-5A-optimization-algorithm-selection.txt` (original brief)
    - `Optimization Algorithm and Library Recommendation.txt` (algorithm recommendation)
    - `deep-research-report (5).md` (deep research)
    - `compass_artifact_wf-161ef0eb*.md` (implementation compass)
    - `Hugging Face Optimization Research Brief.txt` (HuggingFace survey — Shiwa/NGOpt meta-optimizer, algorithm comparison matrix)
    - `codex-huggingface-review.md` (Codex comparative review: HuggingFace vs existing research — verdict: existing recommendation stands, HuggingFace adds context but no material changes needed)
  - [ ] Cross-reference findings against Story 5.1's verdict on existing optimizer
  - [ ] Note: Codex review confirmed CatCMAwM (GECCO 2025) is state-of-the-art for mixed-variable optimization — HuggingFace only references older CMAwM. Multi-instance portfolio architecture preferred over single NGOpt meta-optimizer for diversity control. Noise-robust CMA-ES variants (LRA/PSA/RA) in `cmaes` library address noise concerns.
  - [ ] Validate recommendation (CMA-ES CatCMAwM primary, DE fallback via Nevergrad TwoPointsDE, `cmaes` + Nevergrad libraries) against D3 opaque optimizer requirements
  - [ ] Confirm ask/tell interface compatibility with Python orchestrator contract from D3
  - [ ] Document: primary algorithm, fallback, library, population sizing (10 instances × pop=128 for 2048 batch), convergence detection, mixed parameter type handling (continuous, integer, categorical, conditional via CMAwM)
  - [ ] Flag any conflicts between research recommendations and Architecture decisions
  - [ ] Document rejected alternatives (e.g., TPE, Bayesian optimization, plain CMA-ES without CMAwM) with evidence-backed rationale for why they were not selected
  - [ ] Specify reproducibility requirements: RNG seeding policy, checkpoint/resume format, tolerance class (exact vs statistical)
  - [ ] Write Section 2 of research artifact: "Algorithm Recommendation" (primary/fallback algorithm, library, batch config, convergence, mixed types, rejected alternatives, reproducibility)

- [ ] **Task 3: Synthesize Research Brief 5B — Candidate Selection & Equity Curve Quality** (AC: #2)
  - [ ] Read all 4 files in `_bmad-output/planning-artifacts/research/briefs/5B/`:
    - `epic5-brief-5B-candidate-selection-equity-curve-quality.txt` (original brief)
    - `Quant Strategy Selection Research Brief.txt` (selection methodology)
    - `deep-research-report (6).md` (deep research)
    - `compass_artifact_wf-99d43cbd*.md` (implementation compass)
  - [ ] Cross-reference against Story 5.1's candidate selection snapshot and D11 candidate compressor
  - [ ] Document equity curve metrics: K-Ratio, Ulcer Index, DSR, Gain-to-Pain Ratio, Serenity Ratio — with formulas and thresholds
  - [ ] Document multi-objective ranking: TOPSIS with CRITIC weights, 4-stage filtering funnel (hard gates → TOPSIS → stability → Pareto)
  - [ ] Document clustering: Gower distance + HDBSCAN, K-medoids medoid selection, 10-35 candidate output
  - [ ] Document diversity archive: MAP-Elites for behavioral diversity, 80/20 deterministic-exploratory split
  - [ ] Determine MVP scope for candidate selection — FR26-FR28 are Growth-phase per Story 5.1 and PRD
  - [ ] Define V1 fallback: manual/simple candidate promotion method so MVP stories (5.3-5.5) can proceed without advanced candidate selection
  - [ ] Resolve DBSCAN (D11) vs HDBSCAN (5B research) discrepancy — recommend the better algorithm with evidence and draft D11 amendment if warranted
  - [ ] Document rejected alternatives for ranking/clustering with evidence-backed rationale
  - [ ] Write Section 3 of research artifact: "Candidate Selection Specification" (metrics, ranking, clustering, diversity, MVP vs Growth scope, V1 fallback, DBSCAN/HDBSCAN resolution)

- [ ] **Task 4: Synthesize Research Brief 5C — Validation Gauntlet Configuration** (AC: #3, #4)
  - [ ] Read all 4 files in `_bmad-output/planning-artifacts/research/briefs/5C/`:
    - `epic5-brief-5C-validation-gauntlet-configuration.txt` (original brief)
    - `Validation Gauntlet Configuration & Confidence Score.txt` (gauntlet spec)
    - `deep-research-report (8).md` (deep research)
    - `compass_artifact_wf-68e1ddb0*.md` (implementation compass)
  - [ ] Cross-reference against Story 5.1's validation pipeline verdicts and D11 validation guidance
  - [ ] Document walk-forward config: 2-4yr IS, 3-6mo OOS, 8 windows for EURUSD M1, anchored vs rolling, purge/embargo gaps, WFE ≥60% threshold
  - [ ] Document CPCV config: N=10-12 groups, k=2 test groups (45 combinations), purge sizing, PBO ≤0.40 threshold
  - [ ] Document Monte Carlo: bootstrap (randomize trade order), permutation (shuffle returns), stress testing (1.5x/2.0x/3.0x spreads), simulation counts
  - [ ] Document parameter perturbation: Sobol sequence, 200-500 perturbations, Morris screening → Sobol sensitivity two-stage approach
  - [ ] Document regime analysis: ATR-14 terciles (high/medium/low volatility) + ADX-14 trend classification, minimum trade counts per regime
  - [ ] Document confidence scoring: geometric weighted aggregation, hard gates, GT-Score >0.80 deployment threshold, RED/YELLOW/GREEN rating
  - [ ] Document gauntlet ordering: hard gates → parameter stability → parallel block (WF/CPCV/MC/Regime) → confidence score, with short-circuit rules
  - [ ] Document rejected alternatives for each validation component with evidence-backed rationale
  - [ ] Specify Monte Carlo reproducibility: fixed seed policy, simulation count vs statistical stability tradeoff
  - [ ] Write Sections 4-5 of research artifact: "Validation Gauntlet Configuration" and "Confidence Score Aggregation" (walk-forward, CPCV, MC, perturbation, regime, scoring, rejected alternatives, reproducibility)

- [ ] **Task 5: Architecture Compatibility Cross-Check** (AC: #5, #6)
  - [ ] Read `_bmad-output/planning-artifacts/architecture.md`
  - [ ] Verify all research recommendations against each relevant decision:
    - **D1 (System Topology):** fold-aware batch evaluation, library-with-subprocess-wrapper, windowed evaluation compatibility
    - **D3 (Pipeline Orchestration):** opaque optimizer contract (input: strategy spec, market data, cost model, fold boundaries, compute budget → output: ranked candidates, Arrow IPC artifacts), ask/tell interface fit
    - **D11 (AI Analysis Layer):** candidate compressor inputs, anomaly detection thresholds, DSR mandatory for >10 candidates, PBO ≤0.40 gate, tiered reproducibility, two-pass evidence packs
    - **D13 (Cost Model):** session-aware spread/slippage integration with Monte Carlo stress testing
    - **D10 (Strategy Execution Model):** Conditional parameters, mixed types (continuous, integer, categorical, conditional) — optimizer must handle the full D10 parameter taxonomy
    - **D14 (Strategy Engine):** Phase 1 Python indicators, Phase 2 Rust migration — impact on optimization loop
  - [ ] Check CV-inside-objective compatibility: mean-λ·std aggregation, 1.3-2.5x cost with early stopping
  - [ ] Check NFR compatibility: NFR1 (80%+ CPU), NFR2 (memory-aware scheduling), NFR3 (bounded pools, streaming results), NFR4 (deterministic memory budgeting ~5.5GB peak), NFR5 (incremental checkpointing)
  - [ ] Document any conflicts or required architecture amendments
  - [ ] If amendments needed: draft specific D-number changes with rationale
  - [ ] Write Section 6 of research artifact: "Architecture Compatibility Assessment" (per-decision alignment, conflicts, amendment proposals)

- [ ] **Task 6: FR Coverage Matrix** (AC: #5)
  - [ ] Create matrix mapping each FR23-FR28, FR29-FR37 to specific research recommendation
  - [ ] For each FR, note: recommended approach, research source, MVP vs Growth scope
  - [ ] Flag any FRs not covered by research or needing additional investigation
  - [ ] Write Section 7 of research artifact: "FR Coverage Matrix" (FR-to-recommendation mapping with MVP/Growth tags)

- [ ] **Task 7: Build Plan for Stories 5.3+** (AC: #7)
  - [ ] Based on synthesized research, propose story breakdown for implementation:
    - Story 5.3: Python optimization orchestrator — ask/tell interface via Nevergrad, CMA-ES CMAwM + DE algorithm config, batch dispatch to Rust evaluator crate, CV-inside-objective fold management
    - Story 5.4: Validation gauntlet — walk-forward, CPCV, Monte Carlo, parameter perturbation, regime analysis
    - Story 5.5: Confidence scoring — aggregation, RED/YELLOW/GREEN, hard gates, GT-Score
    - Story 5.6: Candidate selection — equity metrics, TOPSIS ranking, clustering, diversity archive (**Growth-phase** — FR26-FR28 are explicitly post-MVP per PRD)
    - Story 5.7: E2E proof — optimization → validation → confidence pipeline (MVP scope; uses V1 simple candidate promotion, not advanced selection)
  - [ ] For each proposed story: specify which research recommendations it implements, which FRs it covers, which architecture decisions it must follow
  - [ ] Note which stories are MVP vs Growth-phase — Story 5.6 is Growth, Stories 5.3-5.5 and 5.7 are MVP
  - [ ] Define V1 fallback candidate promotion method (e.g., top-N by objective value + manual operator review) so Stories 5.3-5.5/5.7 do not depend on Story 5.6
  - [ ] Write Section 8 of research artifact: "Build Plan for Stories 5.3+" (story breakdown with FR/D-number mapping, MVP/Growth classification, V1 fallback path)

- [ ] **Task 8: Write Final Research Artifact** (AC: #1-#7)
  - [ ] Compile all sections into unified research artifact
  - [ ] Output location: `_bmad-output/planning-artifacts/research/optimization-algorithm-candidate-validation-research.md`
  - [ ] Structure:
    1. Executive Summary (key decisions, primary recommendations)
    2. Algorithm Recommendation (from Task 2) — including rejected alternatives and reproducibility specs
    3. Candidate Selection Specification (from Task 3) — including V1 fallback, DBSCAN/HDBSCAN resolution
    4. Validation Gauntlet Configuration (from Task 4) — including reproducibility specs
    5. Confidence Score Aggregation (from Task 4)
    6. Architecture Compatibility Assessment (from Task 5)
    7. FR Coverage Matrix (from Task 6)
    8. Build Plan for Stories 5.3+ (from Task 7) — with MVP/Growth classification and V1 fallback path
    9. Decision Table: chosen method, alternatives considered, evidence source, rationale, and open risks per major area (algorithm, candidate selection, each validation component, confidence scoring)
    10. Open Questions & Risks
    - Appendix A: Research Source Index (all briefs, reports, compass artifacts)
    - Appendix B: Story 5.1 Handoff Integration Log
    - Appendix C: Architecture Amendment Proposals (if any — for operator review before applying)
    - Appendix D: Downstream Implementation Contracts (optimizer I/O schema, per-fold score fields, confidence-score breakdown, candidate artifact schema, config keys, checkpoint format)
    - Appendix E: Reproducibility Specifications (seeding policy, tolerance classes, checkpoint/resume format per stochastic component)

- [ ] **Task 9: Update Architecture Document** (AC: #7, #9)
  - [ ] If Task 5 identified amendments: draft specific changes in Appendix C of research artifact
  - [ ] Include DBSCAN→HDBSCAN amendment if Task 3 recommends it
  - [ ] Apply changes to `_bmad-output/planning-artifacts/architecture.md` — amendments are documented in research artifact Appendix C for operator review
  - [ ] Update revision note with date and change summary
  - [ ] If no amendments needed: document confirmation in research artifact Section 6

- [ ] **Task 10: Create Stories 5.3+ in Epics File** (AC: #7)
  - [ ] Note: Epic 5 currently has only Stories 5.1 and 5.2 defined in epics.md — Stories 5.3+ do not exist yet and must be CREATED (not updated)
  - [ ] Add each proposed story (5.3-5.7) to `_bmad-output/planning-artifacts/epics.md` under Epic 5, following the existing story format (user story statement, acceptance criteria, technical requirements, source hints)
  - [ ] Ensure each story 5.3+ has clear scope, FRs, and research-backed approach
  - [ ] Add corresponding entries to `_bmad-output/implementation-artifacts/sprint-status.yaml` with status "backlog"

## Dev Notes

### This is a RESEARCH Story — No Production Code

The output is a research artifact document, not code. The dev agent must:
1. Read and synthesize existing research briefs (already completed by external research tool)
2. Cross-reference against Story 5.1's baseline review findings
3. Validate against architecture decisions
4. Produce a unified recommendation document
5. Confirm the implementation story breakdown

### Architecture Constraints

- **D3 (Opaque Optimizer):** Optimizer is a state machine behind ask/tell interface. Python orchestrator owns the search algorithm; Rust crate is the evaluator. The optimizer must NOT prescribe fixed staging or parameter grouping — this was the core architectural flaw in ClaudeBackTester's 5-stage model. Architecture revision (2026-03-18) explicitly states "optimization is opaque to state machine."
- **D11 (AI Analysis Layer / Candidate Compressor):** Deterministic-first approach — all metrics computed deterministically, LLM narrates results. DSR mandatory for >10 candidates. PBO ≤0.40 recommended gate. Tiered reproducibility (A/B/C). Two-pass evidence packs (60s triage + 5-15min deep review).
- **D1 (System Topology):** Fold-aware batch evaluation with per-fold scores returned (not aggregated). Library-with-subprocess-wrapper pattern. Windowed evaluation (multiple batches within single process lifetime).
- **CV-inside-objective:** Mean-λ·std aggregation is DRO-optimal. 1.3-2.5x cost with early stopping, not 5x. This is the PRIMARY overfitting defense per research (2026-03-18). Do NOT recommend alternatives that bypass this.
- **FR24 Clarification:** Architecture must NOT prescribe fixed-stage optimization. Strategies define their own stages. The optimizer treats parameter space as opaque. Do NOT reinforce the 5-stage mental model from ClaudeBackTester.

### MVP vs Growth Scope

- **MVP (V1):** FR23-FR25 (optimizer core), FR29-FR34 (validation gauntlet core), FR35-FR37 (visualization basics). Stories 5.3-5.5 and 5.7 are MVP.
- **Growth:** FR26-FR28 (advanced candidate selection — clustering, diversity archives, mathematically principled forward-test selection). Story 5.1 and the PRD both document these as Growth-phase. Story 5.6 is Growth-phase. Research should cover them fully but implementation stories must flag MVP vs Growth clearly.
- **V1 Fallback:** MVP stories must define a simple candidate promotion path (top-N by objective + operator review) that works without FR26-FR28 capabilities, so Stories 5.3-5.5/5.7 are not blocked by the Growth-phase Story 5.6.

### Research Brief Locations (All Completed)

| Brief | Directory | Files | Topic |
|-------|-----------|-------|-------|
| 5A | `research/briefs/5A/` | 4 files | Algorithm selection: CMA-ES CMAwM, DE, TPE, Nevergrad |
| 5B | `research/briefs/5B/` | 4 files | Candidate selection: equity metrics, TOPSIS, HDBSCAN, MAP-Elites |
| 5C | `research/briefs/5C/` | 4 files | Validation gauntlet: walk-forward, CPCV, Monte Carlo, regime, confidence |
| Prior | `research/briefs/optimization/` | 3 files | CV-objective framework, staged-vs-joint, methodology summary |
| 3B | `research/briefs/3B/` | varies | Deterministic backtesting, validation methodology |
| 3C | `research/briefs/3C/` | varies | Results analysis, anomaly detection, evidence packs |

### Key Research Findings to Validate (from Briefs)

**5A Algorithm Selection:**
- Primary: CMA-ES with Margin (CMAwM) — handles mixed parameter types natively
- Fallback: L-SHADE DE for population diversity
- Library: Nevergrad for orchestration (ask/tell interface)
- Batch strategy: 10 CMA-ES instances × pop=128, filling 2048 batch capacity
- BIPOP restarts, relaxed tolerances for noisy objectives

**5B Candidate Selection:**
- Five key metrics: K-Ratio, Ulcer Index, DSR, Gain-to-Pain Ratio, Serenity Ratio
- 4-stage funnel: hard gates → TOPSIS (CRITIC weights) → stability check → Pareto front
- Clustering: Gower distance + HDBSCAN on parameter space
- Diversity: MAP-Elites for behavioral diversity, 80/20 deterministic-exploratory split
- Output: 10-35 candidates

**5C Validation Gauntlet:**
- Walk-forward: 2-4yr IS, 3-6mo OOS, 8 windows, WFE ≥60%
- CPCV: N=10, k=2 (45 combinations), PBO ≤0.40
- Perturbation: Two-stage Morris → Sobol, 200-500 samples
- Monte Carlo: bootstrap + permutation + stress (1.5x/2.0x/3.0x spreads)
- Regime: ATR-14 terciles + ADX-14 trend, minimum trade counts
- Confidence: Geometric weighted GT-Score >0.80, hard gates, RED/YELLOW/GREEN
- Ordering: hard gates → stability → parallel block → confidence, short-circuit on failure

### Technical Requirements

- **Python 3.10+** (tomllib native)
- **Rust** latest stable (pinned in rust-toolchain.toml)
- **Arrow IPC** for data exchange (mmap-enabled, zero-copy)
- **SQLite WAL** for query/persistence
- **Memory budget:** ~5.5 GB peak (16 P-cores × 8 MB stacks + buffers + OS reserve 4 GB)
- **NFR1:** 80%+ CPU utilization target
- **NFR5:** Incremental checkpointing for optimization resume

### What to Reuse from ClaudeBackTester

Story 5.1's verdict table (once completed) will specify keep/adapt/replace per component. Key areas likely relevant:
- **Validation pipeline logic** (walk-forward, confidence scoring) — likely adapt
- **Evaluator interface** (Rust IPC, batch dispatch) — likely keep/adapt
- **5-stage optimizer** — likely replace (architecturally flawed per research)
- **Candidate ranking** — likely replace with research-backed methodology

**Do NOT carry forward** (anticipated from Story 5.1):
- Fixed 5-stage parameter locking model
- Any assumption that parameter groups are independent
- Block Coordinate Descent mental model

### Reproducibility Requirements

Research must specify reproducibility policy for every stochastic component:
- **CMA-ES/DE optimization:** RNG seeding strategy (per-run seed vs per-instance seed), checkpoint format for resume-from-interruption
- **Monte Carlo simulations:** Fixed seed policy for bootstrap/permutation/stress, minimum simulation counts for statistical stability
- **CPCV:** Deterministic fold assignment (not stochastic — but document the contract)
- **Tolerance classes:** Classify each component as "exact reproducibility" (identical results given same seed) or "statistical reproducibility" (results within confidence interval given different seeds)
This feeds into NFR5 (incremental checkpointing) and FR18 (identical results given identical inputs).

### Anti-Patterns to Avoid

1. **Do NOT write optimizer code** — this is a research synthesis story, not implementation
2. **Do NOT re-derive research findings** — the briefs are completed; synthesize and cross-reference, don't redo the research
3. **Do NOT reinforce the 5-stage model** — FR24 and D3 explicitly reject fixed staging; ensure all recommendations support opaque optimization
4. **Do NOT assume FR26-FR28 are MVP** — they are Growth-phase; research should cover them but flag the scope boundary clearly
5. **Do NOT ignore Story 5.1's handoff** — AC#1 explicitly requires building on Story 5.1's verdict table and research gaps
6. **Do NOT produce vague recommendations** — every recommendation needs: specific algorithm/library/parameter, rationale, FR coverage, architecture decision alignment
7. **Do NOT skip the build plan** — AC#7 requires confirming story breakdown for 5.3+; implementation stories depend on this
8. **Do NOT put search algorithms in Rust** — D3 explicitly states: "search algorithm runs in Python." The Rust crate is the evaluation engine only. Nevergrad/CMA-ES/DE run in Python orchestrator; Rust receives candidate batches and returns per-fold scores
9. **Do NOT confuse DBSCAN (D11) with HDBSCAN (5B research)** — Architecture D11 says DBSCAN; research brief 5B recommends HDBSCAN. This discrepancy must be explicitly resolved in the research artifact — recommend the better algorithm and propose a D11 amendment if warranted

### Project Structure Notes

**Files to CREATE:**
- `_bmad-output/planning-artifacts/research/optimization-algorithm-candidate-validation-research.md` — main research artifact

**Files to READ (not modify unless AC#6 triggers):**
- `_bmad-output/planning-artifacts/research/optimizer-validation-baseline-review.md` — Story 5.1 output
- `_bmad-output/planning-artifacts/research/briefs/5A/` — 4 files (algorithm selection)
- `_bmad-output/planning-artifacts/research/briefs/5B/` — 4 files (candidate selection)
- `_bmad-output/planning-artifacts/research/briefs/5C/` — 4 files (validation gauntlet)
- `_bmad-output/planning-artifacts/research/briefs/optimization/` — prior CV-objective research
- `_bmad-output/planning-artifacts/architecture.md` — architecture decisions
- `_bmad-output/planning-artifacts/prd.md` — FR23-FR37 requirements
- `_bmad-output/planning-artifacts/epics.md` — Epic 5 story structure

**Files to POTENTIALLY MODIFY (only if research warrants — AC#6, AC#7):**
- `_bmad-output/planning-artifacts/architecture.md` — if amendments needed
- `_bmad-output/planning-artifacts/epics.md` — if story breakdown changes

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 5: Optimization & Validation Gauntlet]
- [Source: _bmad-output/planning-artifacts/architecture.md — D1 System Topology, D3 Pipeline Orchestration, D11 AI Analysis Layer, D13 Cost Model, D14 Strategy Engine]
- [Source: _bmad-output/planning-artifacts/architecture.md — Phase 0 Research Status Table]
- [Source: _bmad-output/planning-artifacts/prd.md — FR23-FR28 Optimization, FR29-FR37 Validation Gauntlet]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR1-NFR5, NFR8-NFR9 Performance & Research Requirements]
- [Source: _bmad-output/planning-artifacts/research/briefs/5A/ — Optimization Algorithm Selection Research]
- [Source: _bmad-output/planning-artifacts/research/briefs/5B/ — Candidate Selection & Equity Curve Quality Research]
- [Source: _bmad-output/planning-artifacts/research/briefs/5C/ — Validation Gauntlet Configuration Research]
- [Source: _bmad-output/planning-artifacts/research/briefs/optimization/ — CV-Objective Framework, Staged-vs-Joint Research]
- [Source: _bmad-output/implementation-artifacts/5-1-claudebacktester-optimizer-validation-pipeline-review.md — Story 5.1 Baseline Review]

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Completion Notes List

### Change Log

### File List
