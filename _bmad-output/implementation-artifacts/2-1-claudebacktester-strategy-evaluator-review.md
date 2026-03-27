# Story 2.1: ClaudeBackTester Strategy Evaluator Review

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the **operator**,
I want the existing Rust strategy evaluator reviewed against our specification-driven architecture,
so that I know which indicator implementations, strategy patterns, and evaluator logic to keep, adapt, or replace before writing any code.

## Acceptance Criteria

1. **Given** the ClaudeBackTester codebase is accessible
   **When** the Rust evaluator modules are reviewed (indicator implementations, strategy logic, signal generation, filter chains, exit rules)
   **Then** a component verdict table is produced with keep/adapt/replace per component, with rationale citing specific source files/modules for each verdict
   _(Ref: D10, D14, FR9-FR13)_

2. **Given** the Rust evaluator is reviewed
   **When** all existing indicator implementations are catalogued
   **Then** each indicator has documented: canonical name, parameter signatures with types, computation logic, input/output types and output shape, warm-up/lookback behavior, supported price sources, and dependencies on other indicators
   _(Ref: D14 — indicators.rs registry feeds Story 2.8; naming convention differences like EUR_USD vs EURUSD noted)_

3. **Given** the ClaudeBackTester workflow is accessible
   **When** the existing strategy authoring workflow is reviewed
   **Then** a document describes the current authoring workflow as evidenced by code, config files, and repo documentation — listing explicit unknowns where repo evidence is insufficient for operator follow-up
   _(Ref: FR9-FR10 — intent capture must solve authoring pain)_

4. **Given** the Rust engine strategy loading is accessible
   **When** the current strategy representation format is reviewed
   **Then** a document describes how strategies are defined, stored, and loaded by the Rust engine
   _(Ref: D10 three-layer model — spec format is Phase 0 research gate)_

5. **Given** the component catalogue and architecture are available
   **When** baseline evaluator capabilities are compared against D10 and FR9-FR13
   **Then** any capabilities NOT covered by D10 or FR9-FR13 are documented with recommendations
   _(Ref: D10 minimum representable constructs table)_

6. **Given** the three-layer model (intent -> spec -> evaluator) is defined in D10
   **When** baseline evaluator patterns are compared against the three-layer model
   **Then** any baseline patterns that demonstrably improve one or more system objectives (reproducibility, operator confidence, artifact completeness, fidelity) are flagged with evidence and a recommendation to adopt or hybridize
   _(Ref: D10 Phase 0 research determines format and evaluator approach)_

7. **Given** findings from ACs 1-6 are complete
   **When** any finding meets one or more of: (a) baseline capability demonstrably improves a system objective vs D10 approach, (b) D10 minimum representable constructs table missing a baseline capability used in production strategies, (c) D14 crate decomposition does not match baseline module boundaries AND the mismatch would harm a system objective, (d) baseline evaluator pattern incompatible with spec-driven interface without architecture change
   **Then** a Proposed Architecture Updates section is added to the research artifact with specific D10/D14 change descriptions, system objective justification, and rationale for operator review
   _(Ref: D10, D14 — do NOT modify architecture.md directly; baseline structure is evidence, not authority)_

8. **Given** the ClaudeBackTester codebase is accessed
   **When** the review begins
   **Then** the research artifact records the baseline repo path, branch, and commit hash for traceability
   _(Ref: reproducibility — review must be reproducible against a pinned baseline)_

9. **Given** the evaluator signal generation logic is reviewed
   **When** determinism and fidelity risks are assessed
   **Then** any statefulness, randomness, time dependence, floating-point sensitivity, or backtest/live drift risks are documented with severity and mitigation notes
   _(Ref: FR19 — signal fidelity between backtest and live is a core system objective)_

10. **Given** the evaluator and backtester modules are reviewed
    **When** any execution cost logic (spread, slippage, commission) is found
    **Then** its location, approach, and compatibility with D13 (session-aware cost model) are documented; if no cost logic exists, that absence is documented
    _(Ref: D13, FR20-FR22 — cost model is a first-class pipeline artifact)_

## Tasks / Subtasks

- [x] **Task 1: Access and inventory ClaudeBackTester Rust evaluator** (AC: #1, #2)
  - [x] Clone or access ClaudeBackTester repo at https://github.com/longytravel/forexpipeline (or local clone if available)
  - [x] Record baseline repo path, branch, and commit hash in research artifact header (AC #8)
  - [x] Locate Rust workspace: identify crates directory structure
  - [x] Inventory all Rust source files in strategy evaluation crates (`strategy_engine/`, `backtester/`, related modules)
  - [x] Document file list with line counts and brief purpose descriptions

- [x] **Task 2: Catalogue indicator implementations** (AC: #2)
  - [x] For each indicator (MA, EMA, ATR, Bollinger, etc.): document parameter signature with types
  - [x] Document computation logic (formula, lookback periods, edge cases)
  - [x] Document input sources (which OHLC fields used, multi-timeframe support)
  - [x] Document output types (single value, tuple, series)
  - [x] Note any indicator dependencies (e.g., ATR used by chandelier exit)
  - [x] Compare against D10 minimum representable constructs table:
    - Trend indicators (MA crossover)
    - Volatility indicators (chandelier exit, ATR-based stops)
    - Exit types (SL, TP, trailing, chandelier)
    - Session filters
    - Volatility filters

- [x] **Task 3: Review strategy logic and signal generation** (AC: #1)
  - [x] Document entry rule evaluation flow (condition checks, filter chains, confirmations)
  - [x] Document exit rule evaluation flow (stop loss, take profit, trailing stop types)
  - [x] Document signal generation pipeline (per-bar evaluation order, state management)
  - [x] Document position sizing logic (if present)
  - [x] Assess: is evaluation deterministic? (same inputs = same signals)
  - [x] Assess fidelity risks: statefulness, randomness, time dependence, floating-point sensitivity, backtest/live drift vectors (AC #9)

- [x] **Task 4: Document strategy authoring workflow** (AC: #3)
  - [x] Review how strategies are currently defined (config files? code? manual Rust edits?)
  - [x] Document the operator experience: steps to create a new strategy
  - [x] Document the operator experience: steps to modify an existing strategy
  - [x] Identify pain points (what was painful, error-prone, or limiting)
  - [x] Identify what worked well (patterns to preserve in new dialogue flow)

- [x] **Task 5: Document strategy representation format** (AC: #4)
  - [x] Document current format: JSON, TOML, Rust structs, or other
  - [x] Document schema/structure: fields, nesting, required vs optional
  - [x] Document loading mechanism: how Rust engine reads and parses strategy definitions
  - [x] Document validation: what checks exist on strategy definitions
  - [x] Compare against D10 specification schema (metadata, entry_rules[], exit_rules[], position_sizing, optimization_plan, cost_model_reference)

- [x] **Task 6: Gap analysis — baseline vs D10/FR9-FR13** (AC: #5, #6)
  - [x] List all baseline capabilities NOT covered by D10 minimum representable constructs
  - [x] List all D10 requirements NOT present in baseline (gaps to build)
  - [x] Assess baseline vs three-layer model (intent -> spec -> evaluator):
    - Does baseline separate intent from specification?
    - Does baseline separate specification from evaluation?
    - Are there baseline patterns superior to three-layer model?
  - [x] For each gap/finding: recommend keep, adapt, replace, or build-new with rationale
  - [x] Assess D10 Phase 0 open questions against baseline evidence:
    - Strategy spec format constraints from baseline evidence (what the baseline uses, what works/doesn't) — format selection is Story 2.2's scope
    - Complex strategy logic mapping to primitives — does baseline handle this?
    - Indicator extensibility model — how does baseline add new indicators?

- [x] **Task 7: Produce component verdict table** (AC: #1)
  - [x] Create verdict table with columns: Component | Baseline Status | Verdict (keep/adapt/replace) | Rationale | Effort | Notes for Story 2.8
  - [x] Components to assess:
    - Indicator computation modules
    - Signal generation / evaluator core
    - Filter chain implementation
    - Exit rule evaluation
    - Strategy loading/parsing
    - Position sizing logic
    - Evaluator-facing optimization metadata support (parameter ranges, grouping hints)
  - [x] For "adapt" verdicts: specify what needs to change and which D10/D14 interface it must conform to
  - [x] For "replace" verdicts: explain why unsalvageable and what the replacement must do

- [x] **Task 8: Write research artifact and propose architecture updates** (AC: #7)
  - [x] Write research artifact to `_bmad-output/planning-artifacts/research/strategy-evaluator-baseline-review.md`
  - [x] Follow 9-section research artifact structure (see Dev Notes)
  - [x] If findings warrant D10 or D14 changes: add Proposed Architecture Updates section with specific change descriptions and rationale
  - [x] Do NOT modify architecture.md directly — proposed changes go in research artifact for operator review
  - [x] Include 1-2 representative baseline strategy configurations as regression/fidelity seed examples for downstream stories
  - [x] Document baseline cost model presence/absence and D13 compatibility (AC #10)

## Dev Notes

### Story Type: Research

This is a **research story** — deliverable is a research artifact document only, no production code. Follow the pattern established by Story 1-1 (data pipeline review).

- **Output:** `_bmad-output/planning-artifacts/research/strategy-evaluator-baseline-review.md`
- **No code deliverables** — do not create or modify any `src/` files
- Architecture change proposals go in the research artifact only (see Anti-Pattern #2)

### Research Artifact Structure (9 Sections)

Follow this structure (proven in Story 1-1):

1. **Executive Summary** — 1-2 paragraphs: overall assessment, key findings
2. **Module Inventory** — file list with descriptions from ClaudeBackTester Rust crates
3. **Component Verdict Table** — keep/adapt/replace per component with rationale + effort estimates
4. **Detailed Component Analysis** — one subsection per component (indicators, evaluator, filters, exits, strategy loading)
5. **Indicator Catalogue** — NEW for 2-1: full catalogue with parameter signatures, computation logic, input/output types (feeds Story 2.8 indicator registry)
6. **Strategy Authoring Workflow** — how operator currently creates/modifies strategies, pain points, what worked
7. **Strategy Representation Format** — current format, schema, loading mechanism, validation
8. **Gap Analysis** — baseline vs D10/FR9-FR13 + baseline vs three-layer model + Phase 0 research questions
9. **Proposed Architecture Updates** — specific changes to D10 or D14 if warranted, with rationale

### Architecture Decisions to Review Against

- **D10 (Strategy Execution Model):** Three-layer model (intent -> spec -> evaluator). Specification-driven with AI generation. Minimum representable constructs: trend indicators, volatility indicators, exit types, session/volatility filters, timeframe, pair, position sizing, optimization parameters. Evaluator is a rule engine, not general-purpose interpreter. Deterministic by construction.
- **D14 (Strategy Engine Shared Crate):** `strategy_engine` crate with evaluator.rs, indicators.rs, filters.rs, exits.rs. Shared between backtester and live_daemon for signal fidelity (FR19, FR52). Pure computation — no I/O, no state management.
- **D13 (Cost Model Crate):** Library consumed by backtester. Session-aware spread/slippage profiles. Relevant context: does baseline have any cost modeling?
- **D1 (System Topology):** Multi-process with Arrow IPC. Python orchestrator, Rust compute.
- **D2 (Artifact Schema):** Arrow IPC / SQLite / Parquet hybrid. Strategy artifacts stored per `artifacts/{strategy_id}/v001/`.

### Key PRD Requirements for Comparison

- **FR9:** Natural language strategy generation via dialogue
- **FR10:** Intent understanding — map dialogue to specification constructs
- **FR11:** Operator review — human-readable summary without raw spec exposure
- **FR12:** Specification versioning and locking with config_hash
- **FR13:** Optimization plan with parameter_groups, dependencies, objective_function
- **FR20-FR22:** Cost model artifact format, session-aware profiles, builder sources
- **FR60:** Cost model versioning

### D10 Minimum Representable Constructs (Comparison Checklist)

| Construct | Examples | Check Against Baseline |
|---|---|---|
| Trend indicators | MA crossover | Does baseline have MA types, periods, price sources? |
| Volatility indicators | Chandelier exit, ATR stops | Does baseline have ATR, Bollinger, multiplier params? |
| Exit types | SL, TP, trailing, chandelier | Does baseline support all exit types? |
| Session filters | London/NY/Asian | Does baseline filter by session? |
| Volatility filters | ATR/Bollinger threshold | Does baseline filter by volatility? |
| Timeframe | H1, configurable | How does baseline handle timeframes? |
| Pair | EURUSD | How does baseline handle pair config? |
| Position sizing | Risk %, max lots | Does baseline have position sizing? |
| Optimization params | Parameter groups, ranges, steps | Does baseline support optimization parameter definition? |

### D14 Crate Structure (Target Architecture to Map Against)

```
crates/strategy_engine/
  src/
    lib.rs
    evaluator.rs    — Build evaluator from spec, per-bar signal evaluation
    indicators.rs   — Indicator computation (MA, EMA, ATR, Bollinger, etc.)
    filters.rs      — Session filter, volatility filter, day-of-week filter
    exits.rs        — Stop loss, take profit, trailing stop, chandelier exit
```

The indicator catalogue produced by Task 2 directly feeds Story 2.8 (Strategy Engine Crate — Specification Parser & Indicator Registry). Document indicators with enough detail that 2.8 can implement the registry.

### Data Naming Convention

ClaudeBackTester uses `EUR_USD` format; Pipeline uses `EURUSD`. Note any naming differences found in the evaluator for future mapping work.

### Previous Story Intelligence (Story 1-1 Pattern)

Story 1-1 (data pipeline review) established the research story pattern:
- All 5 data pipeline components assessed as "Adapt" — core logic reusable but needs Architecture compliance wrapping
- No "Keep" verdicts (nothing usable as-is without changes)
- Key surprise: `dukascopy-python` library discovery changed Story 1.4 approach
- Be prepared for similar surprises in the strategy evaluator

### Anti-Patterns to Avoid

1. **Do NOT write code** — this is a research story, deliverable is documentation only
2. **Do NOT modify architecture.md directly** — proposed changes go in research artifact for operator review
3. **Do NOT skip the indicator catalogue** — Story 2.8 depends on it for the registry
4. **Do NOT assume baseline components are usable as-is** — Story 1-1 found all components needed "Adapt" treatment
5. **Do NOT ignore pain points in authoring workflow** — FR9/FR10 dialogue flow must solve these
6. **Do NOT overlook cost model presence/absence** — document whether baseline has any cost modeling for D13 context
7. **Do NOT be superficial** — read actual Rust source code, not just file names. Document computation logic, not just function signatures
8. **Do NOT conflate "exists" with "good"** — assess quality and Architecture compliance, not just presence
9. **Do NOT treat baseline module boundaries as authority for D14 structure** — baseline is evidence, not blueprints; architecture changes require system objective justification
10. **Do NOT make format selection recommendations** — identify baseline constraints and evidence only; JSON/TOML/DSL selection is Story 2.2's scope

### Cross-Artifact Note

`epics.md` Story 2.1 AC6 states "architecture document is updated." This is superseded by this story's AC7 which requires proposed updates in the research artifact only, not direct `architecture.md` modifications.

### Project Structure Notes

**Output location:** `_bmad-output/planning-artifacts/research/strategy-evaluator-baseline-review.md`

This follows the research artifact convention established by Story 1-1:
```
_bmad-output/
  planning-artifacts/
    research/
      data-pipeline-baseline-review.md          # Story 1-1 output
      strategy-evaluator-baseline-review.md     # Story 2-1 output (THIS)
```

**No source tree changes** — research stories do not create or modify files under `src/`.

### What to Reuse from ClaudeBackTester

**Per baseline-to-architecture-mapping.md:**
- `crates/strategy_engine/` — **Exists** in baseline. Rust evaluation layer documented as working. Direction: keep core, wrap with new spec-driven interface (D14).
- `crates/backtester/` — **Exists** in baseline. Rust-backed batch evaluation. Direction: adapt to use strategy_engine crate + cost_model lib.
- `crates/optimizer/` — **Exists** in baseline. Staged optimization documented.
- `crates/validator/` — **Exists** in baseline. Walk-forward, CPCV, Monte Carlo, confidence scoring.
- **Strategy authoring** — Replace / add new layer. Identified as "major unresolved gap" in baseline.

**Key guidance:** "Core reusable asset. Current evaluation works; new spec-driven interface wraps it." The review must determine exactly WHAT is reusable and HOW it maps to D14's evaluator.rs/indicators.rs/filters.rs/exits.rs structure.

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 2: Strategy Definition & Cost Model]
- [Source: _bmad-output/planning-artifacts/architecture.md — D10: Strategy Execution Model]
- [Source: _bmad-output/planning-artifacts/architecture.md — D13: Cost Model Crate]
- [Source: _bmad-output/planning-artifacts/architecture.md — D14: Strategy Engine Shared Crate]
- [Source: _bmad-output/planning-artifacts/prd.md — FR9-FR13: Strategy Definition Requirements]
- [Source: _bmad-output/planning-artifacts/prd.md — FR20-FR22: Cost Model Requirements]
- [Source: _bmad-output/planning-artifacts/baseline-to-architecture-mapping.md — Strategy Evaluation Components]
- [Source: _bmad-output/implementation-artifacts/1-1-claudebacktester-data-pipeline-review.md — Research Story Pattern]
- [Source: MEMORY reference_github_repo.md — ClaudeBackTester repo location]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

None — clean execution, no halts or blockers.

### Completion Notes List

- **Task 1 Complete:** Accessed ClaudeBackTester at `C:\Users\ROG\Projects\ClaudeBackTester`, branch `master`, commit `2084beb`. Critical discovery: no `crates/` directory. Project is Python-first (15,491 lines) with Rust PyO3 extension (1,646 lines). Documented full module inventory with line counts in Section 2.
- **Task 2 Complete:** Catalogued all 18 indicators in Section 5 with full parameter signatures, computation logic, input/output types, warm-up behavior, dependencies, and price sources. All indicators are stateless pure numpy functions suitable for Rust porting.
- **Task 3 Complete:** Documented the "precompute-once, filter-many" evaluation pattern in Sections 4.2-4.4. Two Rust execution modes (basic SL/TP and full management). 10 registered strategies. Determinism verified; fidelity risks documented in Appendix B.
- **Task 4 Complete:** Documented code-based authoring workflow in Section 6. Key pain points: Python programming required, PL_ encoding complexity, dual-language sync burden, no validation. Key strength: precompute pattern, module composition, mandatory ATR, parameter grouping.
- **Task 5 Complete:** Documented in Section 7. No declarative format exists — strategies are Python classes. Checkpoint JSON is the only persisted representation. No schema validation, no type checking, no structural validation. Major gap vs D10 spec schema.
- **Task 6 Complete:** Full gap analysis in Section 8. 8 baseline capabilities not in D10 constructs (sub-bar resolution, stale exit, partial close, breakeven, max bars, etc.). 9 D10 requirements not in baseline (spec format, NL generation, cost model, etc.). Three-layer model assessment: baseline partially separates spec from evaluation but not intent from spec. Precompute pattern identified as superior to naive three-layer approach.
- **Task 7 Complete:** Component verdict table in Section 3. 10 components assessed: 2 Keep (metrics, verification), 6 Adapt (indicators, signal gen, filters, exits, sizing, optimization metadata), 1 Replace (strategy loading/parsing), 1 Build New (cost modeling).
- **Task 8 Complete:** Full 9-section research artifact written to `_bmad-output/planning-artifacts/research/strategy-evaluator-baseline-review.md`. 4 proposed architecture updates (D14 phased Rust migration, D10 exit type extensions, sub-bar resolution requirement, precompute pattern). Includes representative strategy config (Appendix A), fidelity assessment (Appendix B), cost model assessment (Appendix C), and naming convention observations (Appendix D).

### Change Log

- 2026-03-15: Created research artifact `strategy-evaluator-baseline-review.md` with full 9-section analysis covering all 10 ACs. 4 proposed architecture updates for D10/D14. Critical finding: baseline is Python-first, not Rust-crate-based as D14 assumed.

### File List

- `_bmad-output/planning-artifacts/research/strategy-evaluator-baseline-review.md` (new) — Research artifact: strategy evaluator baseline review
- `_bmad-output/implementation-artifacts/2-1-claudebacktester-strategy-evaluator-review.md` (modified) — Story file: tasks marked complete, Dev Agent Record updated
