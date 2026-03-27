# Story 2.2: Strategy Definition Format & Cost Modeling Research

Status: review

## Story

As the **operator**,
I want strategy definition formats and execution cost modeling researched,
so that the strategy pipeline uses proven formats and realistic cost assumptions rather than guesses.

## Acceptance Criteria

1. **Given** Story 2.1's verdict table identifies what needs research
   **When** strategy definition formats research is conducted (DSL vs config/TOML vs template-driven)
   **Then** a research artifact is produced covering: strategy definition approaches, indicator specification patterns, and constraint validation approaches
   [Source: epics.md — Epic 2, Story 2.2 AC#1; FR12]

2. **Given** cost modeling research is conducted
   **When** execution cost sources are investigated
   **Then** the research covers: broker-published spread data sources, session-aware cost profiles (Asian/London/NY/overlap/off-hours), slippage research methodology, tick-data-derived cost estimation, and data provenance (broker/account type, sample window, timezone/session mapping)
   [Source: epics.md — Epic 2, Story 2.2 AC#2; FR20-FR21; FR22 scoped to calibration hooks only — full auto-update methodology deferred to reconciliation epic]

3. **Given** at least 3 strategy definition format options are evaluated
   **When** tradeoffs are documented
   **Then** comparison covers: expressiveness, tooling availability, AI-generation suitability, Rust parseability, and operator reviewability/diffability (FR11)
   [Source: epics.md — Epic 2, Story 2.2 AC#3; D10; FR11]

4. **Given** recommendations are produced
   **When** they are compared against architecture decisions
   **Then** alignment or proposed refinements to D10 (strategy execution model), D13 (cost model crate), and D14 (strategy engine shared crate) are documented
   [Source: epics.md — Epic 2, Story 2.2 AC#4; architecture.md D10, D13, D14]

5. **Given** session-aware cost profiles are researched
   **When** market microstructure data is analyzed
   **Then** research includes bid-ask dynamics across FX sessions, broker spread sheets/historical data, and slippage estimation from tick data or published research
   [Source: epics.md — Epic 2, Story 2.2 AC#5; D13]

6. **Given** cost model patterns are found in baseline or academic research
   **When** they are evaluated
   **Then** they are compared with our planned approach (D13 — session-aware spread/slippage lib)
   [Source: epics.md — Epic 2, Story 2.2 AC#6; baseline-to-architecture-mapping.md]

7. **Given** constraint validation approaches are researched
   **When** the tradeoffs are documented
   **Then** the research identifies whether constraint validation (parameter bounds, indicator combinations, exit rule conflicts) should be done at spec-definition time or runtime
   [Source: epics.md — Epic 2, Story 2.2 AC#7; D10 rule engine model]

8. **Given** research findings may warrant architecture changes
   **When** the research is complete
   **Then** proposed refinements to D10, D13, or D14 are documented in the research artifact for operator review before architecture.md is updated
   [Source: epics.md — Epic 2, Story 2.2 AC#5; Story 2-1 pattern: changes in artifact first]

9. **Given** all format and cost model research is complete
   **When** the research artifact is finalized
   **Then** a build plan for Stories 2.3-2.9 is included, confirming per-story whether implementation ports baseline code or builds new
   [Source: epics.md — Epic 2, Story 2.2 AC#6]

10. **Given** each research domain produces a recommendation
    **When** the recommendation is documented
    **Then** it includes a decision record with: chosen option, rejected options with reasons, evidence sources cited, unresolved assumptions, downstream contract impact (which stories are affected and how), and known limitations
    [Source: Codex review — decision quality gates; Story 2-1 pattern]

11. **Given** D13 specifies mean/std per session as the cost model shape
    **When** cost model representation is evaluated
    **Then** the research explicitly decides whether mean/std is sufficient for V1 fidelity or whether percentiles/tail distributions are needed, documenting the tradeoff and limitations of whichever approach is retained
    [Source: architecture.md D13; FR18 determinism; FR21 session-aware]

## Tasks / Subtasks

- [x] **Task 1: Consume Story 2.1 Research Artifact** (AC: #1)
  - [x] Read `_bmad-output/implementation-artifacts/2-1-claudebacktester-strategy-evaluator-review.md` (Story 2.1 output)
  - [x] Extract component verdict table — identify components marked "replace" or "adapt" that need format research
  - [x] Extract indicator catalogue — parameter signatures, computation patterns, input/output types
  - [x] Extract current strategy representation format — how strategies are defined/stored/loaded by the Rust engine
  - [x] Extract strategy authoring workflow — pain points to solve, patterns to preserve
  - [x] Extract gap analysis findings — baseline capabilities not in D10/FR9-FR13
  - [x] Summarize what 2.1 tells us the new format MUST support vs. what is open for research

- [x] **Task 2: Strategy Definition Format Research** (AC: #1, #3, #7) — Research only, NO code output
  - [x] Research Option A — **TOML/Config-driven**: serde_toml parsing in Rust, Python tomllib reading, schema validation via TOML structure, expressiveness for indicator specs, AI generation patterns
  - [x] Research Option B — **JSON Schema-driven**: serde_json in Rust, Python json/jsonschema, JSON Schema validation, expressiveness, AI generation patterns
  - [x] Research Option C — **Custom DSL**: Rust parser (pest/nom/lalrpop), Python transpiler/generator, expressiveness ceiling, tooling cost, AI generation complexity
  - [x] Research Option D (optional, architecture-exception path) — **Hybrid approaches**: e.g., TOML metadata + embedded expression language for conditions. NOTE: This conflicts with D10's constrained rule-engine model ("not general-purpose interpreter"). Only recommend if evidence shows Options A-C cannot represent D10 minimum constructs — document architecture-change justification if so.
  - [x] For each option, evaluate against D10 minimum representable constructs: trend indicators (MA, EMA), volatility indicators (ATR, Bollinger), exit types (SL, TP, trailing, chandelier), session filters, volatility filters, timeframe, pair, position sizing, optimization parameter groups with ranges/step sizes/dependencies/objective function
  - [x] For each option, evaluate AI-generation suitability: can Claude Code reliably generate valid specs from natural dialogue? Error rate, validation feedback loop
  - [x] For each option, evaluate Rust parseability: parsing speed, error messages, schema evolution
  - [x] Produce comparison matrix with scored tradeoffs
  - [x] Research constraint validation timing: spec-definition-time validation (fail on save) vs. runtime validation (fail on load/evaluate) — tradeoffs for operator experience, error detection speed, evaluator simplicity
  - [x] Recommend primary format with rationale citing D10 alignment

- [x] **Task 3: Execution Cost Modeling Research** (AC: #2, #5, #6) — Research only, NO code output
  - [x] Research broker-published spread data sources:
    - [x] Dukascopy historical tick data (already our data source — `dukascopy-python` v4.0.1) — spread derivation from bid+ask
    - [x] OANDA historical spreads API
    - [x] Other retail broker spread publications (FXCM, IC Markets)
    - [x] Document data availability, granularity, access method per source
  - [x] Research session-aware cost profile construction:
    - [x] Define session boundaries per `config/base.toml` sessions: Asian (00:00-08:00 UTC), London (08:00-16:00), NY (13:00-21:00), London-NY overlap (13:00-16:00), off-hours (21:00-00:00)
    - [x] Methodology: aggregate tick-level spread data by session → compute mean_spread_pips, std_spread per session
    - [x] Research market microstructure: bid-ask dynamics across FX sessions, liquidity patterns, spread widening events
  - [x] Research slippage estimation:
    - [x] Tick-data-derived methodology: fill timing variance, price movement between order and fill
    - [x] Published academic research on retail FX slippage (cite papers/sources)
    - [x] Institutional vs. retail slippage differences
    - [x] Methodology for deriving mean_slippage_pips, std_slippage per session
  - [x] Research cost model artifact structure:
    - [x] Validate D13 JSON format: `{pair, version, source, calibrated_at, sessions: {session: {mean_spread_pips, std_spread, mean_slippage_pips, std_slippage}}}`
    - [x] Assess whether additional fields needed (e.g., commission, swap, execution delay)
    - [x] Research cost model versioning and calibration methodology
    - [x] **Decide: mean/std vs quantiles/tails** — Is mean/std sufficient for V1 fidelity? Or do tail distributions (e.g., p95, p99 spread spikes) matter for realistic backtest cost? Document tradeoff and limitation of chosen approach (AC#11)
    - [x] **CRITICAL LEARNING from Epic 1 E2E proof (2026-03-15):** The quality checker quarantines ticks where spread exceeds 10x median (`spread_multiplier_threshold`). In 2025 EURUSD tick data, 7,391 ticks (0.03%) were quarantined as spread outliers. The timeframe converter then EXCLUDES quarantined bars before aggregation. This means the cost model would never see wide-spread events (news, low liquidity, market open) — exactly the conditions that matter most for realistic cost modeling. Research MUST address:
      - [x] Whether spread outliers should be quarantined at all, or only flagged for visibility
      - [x] Whether the cost model should consume raw (pre-quarantine) tick data to capture true spread distribution including tails
      - [x] Whether `std_spread` must reflect real variance including wide-spread events, not just "normal" market conditions
      - [x] The downstream implication: if the backtester uses a cost model trained on sanitized data, it will underestimate real execution costs and produce unrealistically good backtest results that fail in live trading
  - [x] Document data provenance requirements per source: broker/account type (ECN vs market maker), sample window (date range), timezone/session mapping methodology, and calibration method
  - [x] Define calibration hooks for future FR22 live-update — artifact versioning fields, interface stub for live fill data ingestion. Do NOT design full auto-update methodology (deferred to reconciliation epic)
  - [x] Compare findings with D13 planned approach — assess alignment or propose refinements
  - [x] Check if ClaudeBackTester has any cost model patterns (Story 2.1 AC#10 confirms absence — document gap)

- [x] **Task 4: Produce Research Artifact** (AC: #1-#7)
  - [x] Write research artifact to `_bmad-output/planning-artifacts/research/strategy-definition-format-cost-modeling-research.md`
  - [x] Structure with sections:
    1. Executive Summary (key findings and recommendations)
    2. Story 2.1 Findings Summary (verdict table highlights, indicator catalogue summary, format analysis)
    3. Strategy Definition Format Comparison (3+ options with scored matrix)
    4. Format Recommendation (primary choice with D10 alignment analysis)
    5. Constraint Validation Analysis (spec-time vs. runtime recommendation)
    6. Execution Cost Modeling Research (sources, methodology, session profiles)
    7. Cost Model Artifact Assessment (D13 alignment, proposed refinements)
    8. Proposed Architecture Updates (D10/D14 changes if warranted — in artifact only, NOT architecture.md)
    9. Build Plan Confirmation (Stories 2.3-2.9 scope: porting baseline vs. building new)
    10. Downstream Rewrite Risk (if recommendation deviates from downstream TOML assumptions, quantify impact)
  - [x] Each recommendation section must include a decision record: chosen option, rejected options, evidence, unresolved assumptions, downstream impact (AC#10)
  - [x] Include comparison table for strategy definition formats (minimum 3 options)
  - [x] Include cost model source comparison table
  - [x] Include session-aware profile template with example data
  - [x] Cite all architecture decisions by number (D10, D13, D14) and PRD requirements (FR9-FR13, FR20-FR22)

- [x] **Task 5: Validate and Cross-Reference** (AC: #4, #6, #8, #9)
  - [x] Verify format recommendation aligns with D10 three-layer model (intent → spec → evaluator)
  - [x] Verify cost model research aligns with D13 crate design (library consumed by backtester, session-aware, per-trade lookup)
  - [x] Verify constraint validation recommendation is consistent with D10 rule engine model
  - [x] Confirm build plan for Stories 2.3-2.9: which stories port baseline code vs. build new
  - [x] Document any architecture decision updates proposed (changes stay in research artifact per Story 2.1 pattern)

## Dev Notes

### Story Type
**Research** — output is a research artifact document, NOT production code.

### Architecture Decisions (Must Reference)

**D10 — Strategy Execution Model (Specification-Driven with AI Generation):**
- Three-layer model: Intent capture (Claude Code skill) → Specification (JSON/TOML artifact) → Evaluation (Rust engine)
- Strategy specification contract:
  ```
  Strategy Specification
  ├── metadata (name, version, pair, timeframe, created_by, config_hash)
  ├── entry_rules[] (condition: indicator/threshold/comparator, filters[], confirmation[])
  ├── exit_rules[] (stop_loss, take_profit, trailing)
  ├── position_sizing (method, risk_percent, max_lots)
  ├── optimization_plan (parameter_groups[], group_dependencies[], objective_function)
  └── cost_model_reference (version of cost model to use)
  ```
- Minimum representable constructs: trend indicators (MA, EMA), volatility indicators (ATR, Bollinger), exit types (SL, TP, trailing, chandelier), session filters, volatility filters, timeframe, pair, position sizing, optimization parameter groups
- Evaluator is rule engine, not general-purpose interpreter — specification defines finite composable primitives
- Specification format is Phase 0 research output (THIS STORY decides it)
- Why spec-driven, not code generation: deterministic, reviewable, tested once, diffable, AI reliable at structured data
[Source: architecture.md — Decision 10, lines 625-748]

**D13 — Cost Model Crate (Library Consumed by Backtester):**
- Rust library crate (`crates/cost_model/`), not separate binary
- Backtester depends on it directly (inner-loop, FR21)
- Session-aware spread/slippage per trade during backtesting
- Cost model artifact loaded once at job start, queried per fill
- Artifact format (JSON):
  ```json
  {
    "pair": "EURUSD",
    "version": "v003",
    "source": "research+live_calibration",
    "calibrated_at": "...",
    "sessions": {
      "asian":             { "mean_spread_pips": 1.2, "std_spread": 0.3, "mean_slippage_pips": ..., "std_slippage": ... },
      "london":            { ... },
      "new_york":          { ... },
      "london_ny_overlap": { ... },
      "off_hours":         { ... }
    }
  }
  ```
- Standalone calibration CLI binary uses same library
- Cargo: `backtester → cost_model (lib)`, `optimizer → backtester`, `validator → backtester`
[Source: architecture.md — Decision 13, lines 901-935]

**D14 — Strategy Engine Shared Crate:**
- `strategy_engine` crate: evaluator.rs, indicators.rs, filters.rs, exits.rs
- Shared between backtester and live_daemon — signal fidelity (FR19, FR52)
- Parses strategy specification, maintains indicator registry, validates parameters
[Source: architecture.md — Decision 14, lines 937-958]

**D7 — Configuration (TOML with Schema Validation):**
- Layered TOML configs validated at startup
- `config/strategies/ma-cross-v3.toml` — strategy-specific, versioned
- Schema validation at startup — fail loud
- Config hash embedded in every artifact manifest
- TOML: no implicit type coercion, deterministic parsing
[Source: architecture.md — Decision 7, lines 501-528]

**D12 — Reconciliation Data Flow:**
- Cost model feedback loop: live fills → actual spread/slippage → update cost model artifact → next backtest uses updated model (FR22)
- Attribution categories: spread widening, slippage, fill timing, data latency, signal mismatch
[Source: architecture.md — Decision 12, lines 823-866]

### PRD Requirements (Must Satisfy)

| Requirement | Description | Relevance to Story 2.2 |
|---|---|---|
| FR9 | Natural dialogue strategy direction | Format must support AI-generation from dialogue |
| FR10 | Autonomous strategy code generation | Format must be LLM-generatable |
| FR11 | Operator review without seeing code | Format must produce human-readable summaries |
| FR12 | Constrained, versioned, reproducible specs | Format must support versioning + config_hash |
| FR13 | Strategies define own optimization stages | Format must support parameter_groups, objective_function |
| FR14 | Backtest with researched cost model | Cost model format must support backtester inner-loop lookup (D13) |
| FR18 | Identical results from identical inputs | Cost model must be deterministic |
| FR20 | Execution cost model as background artifact | Cost model sourced from research |
| FR21 | Session-aware spread/slippage (not flat) | Session profiles required |
| FR22 | Auto-update cost model from live data | Cost model versioning/calibration needed |
| FR58 | Versioned artifact at every stage | Strategy spec and cost model are artifacts |
| FR61 | Deterministic, consistent, no drift | Both formats must be deterministic |

### Session Definitions (from architecture.md D13 / config/base.toml planned)

| Session | UTC Start | UTC End | Cost Profile Expectation |
|---|---|---|---|
| Asian | 00:00 | 08:00 | Wider spreads (~1.2 pips EURUSD), higher slippage |
| London | 08:00 | 16:00 | Tight spreads (~0.8 pips), low slippage |
| New York | 13:00 | 21:00 | Moderate spreads (~0.9 pips) |
| London-NY Overlap | 13:00 | 16:00 | Tightest spreads (~0.6 pips), lowest slippage |
| Off-Hours | 21:00 | 00:00 | Widest spreads (~2.0 pips), highest slippage |

### Data Naming Convention
ClaudeBackTester uses `EUR_USD`; Pipeline uses `EURUSD`. Research should use `EURUSD` format and note mapping requirement for baseline references.

### Stop Conditions
- Format comparison: 3-4 options is sufficient. Do NOT research more than 5.
- Cost data sources: 3-4 broker sources is sufficient. Do NOT build a comprehensive market data survey.
- Academic slippage research: 2-3 cited papers is sufficient. Do NOT write a literature review.
- Total research artifact: Executive summary under 1000 words; full artifact including evidence sections target 3000-5000 words. Anything over 6000 words is over-scoped.
- The artifact should have two independently reviewable sections: (1) Strategy Definition Format and (2) Execution Cost Modeling, each with its own recommendation and decision record.

### Decision Framework for Format Recommendation
Weight the comparison criteria as follows:
1. Rust parseability (25%) — D14 must consume it; parsing complexity directly impacts Story 2.8
2. AI-generation suitability (25%) — Claude Code must reliably generate valid specs (FR9, FR10)
3. Expressiveness (20%) — Must represent all D10 minimum constructs
4. Operator reviewability & diffability (15%) — FR11: operator must review without seeing code; format must support human-readable summaries, meaningful diffs, and clear error messages
5. Tooling availability (15%) — Ecosystem support for validation, editing, diffing

**Research framing:** D7 and D10 already bias toward TOML/JSON; downstream stories (2.3, 2.8) assume TOML contracts. Frame research as "validate TOML-first hypothesis, evaluate alternatives as counterpoints." If research recommends non-TOML, document downstream rewrite implications.

### Example Comparison Matrix Row (for reference)
| Criterion | TOML | JSON Schema | Custom DSL |
|---|---|---|---|
| Rust parseability | serde_toml, mature, fast | serde_json, mature, fast | pest/nom, custom parser required |
| Operator reviewability | Human-readable, diffable | Verbose, harder to scan | Readable if well-designed, no standard diff |
| Score | 9/10 | 7/10 | 5/10 |
| Notes | Native config format (D7 precedent) | Verbose for nested rules | High expressiveness ceiling, high build cost |

### Performance Constraints
- Cost model loaded once at job start → format must support fast deserialization
- Per-trade lookup during backtesting inner loop → session lookup must be O(1)
- Strategy spec loaded once per job → parsing speed less critical than correctness
- 10K optimization candidates × backtest → cost model artifact shared across candidates

### Previous Story Intelligence (Story 2-1)

**Key patterns from Story 2-1 and Epic 1 research stories:**
- Research stories output standalone artifact documents to `_bmad-output/planning-artifacts/research/`
- Use keep/adapt/replace verdict framework with effort estimates
- Expect surprise discoveries that change downstream story scope (Story 1-1 found dukascopy-python; Story 2-1 may find unexpected strategy patterns)
- Gap analysis compares baseline vs. architecture decisions
- Proposed architecture updates go in research artifact, NOT directly in architecture.md
- Pin all baseline references (repo path, branch, commit hash)
- Story 2-1 confirmed: `crates/cost_model/` does NOT exist in baseline — build new, research-first
- Story 2-1 confirmed: `crates/strategy_engine/` EXISTS — wrap with spec-driven interface
- Story 2-1 anti-pattern: "Do NOT make format selection recommendations" — that's Story 2.2's job (THIS story)

**Story 1-1 learning:** All 5 data pipeline components assessed as "Adapt" — nothing usable as-is. Expect similar findings for strategy evaluator. Surprise discovery (`dukascopy-python` library) changed downstream scope.

### What to Reuse from ClaudeBackTester

| Baseline Asset | Status | Action for Story 2.2 |
|---|---|---|
| `crates/strategy_engine/` | Exists — Rust evaluator | Review current strategy representation format from 2.1 artifact; research format must wrap this |
| `crates/cost_model/` | Does NOT exist | No baseline — pure research, build from scratch |
| Strategy authoring workflow | Exists but gaps | Use 2.1's workflow doc to identify pain points format must solve |
| Indicator implementations | Exist in evaluator | Use 2.1's catalogue to verify format can express all existing indicators |
| Current strategy format | Exists (documented in 2.1) | Use as one of the comparison options / baseline reference |

### Anti-Patterns to Avoid

1. **Do NOT write production code** — this is a research story; output is a documented artifact only
2. **Do NOT modify architecture.md directly** — proposed changes go in the research artifact (per Story 2-1 pattern, AC#7)
3. **Do NOT recommend a format without evaluating against D10 minimum constructs** — all 3+ options must be tested against the full indicator/filter/exit/optimization spec
4. **Do NOT use flat spread constants** — FR21 explicitly requires session-aware profiles; research must produce per-session methodology
5. **Do NOT ignore the baseline format** — Story 2.1 AC#4 documents the current representation format; it must be one of the compared options (or explicitly documented as inadequate with reasons)
6. **Do NOT skip Rust parseability assessment** — the strategy_engine crate (D14) must consume the chosen format; parsing complexity directly impacts Story 2.8 effort
7. **Do NOT conflate strategy config with pipeline config** — D7 covers pipeline TOML config; D10 covers strategy specification format — these are separate concerns
8. **Do NOT recommend without citing D10/D13/D14** — every recommendation must reference the architecture decision it satisfies or proposes to refine
9. **Do NOT skip slippage research** — spread alone is insufficient; slippage methodology is explicitly required (AC#5)
10. **Do NOT assume EURUSD only** — cost model format must support multiple pairs (growth phase: 7 pairs per architecture scale estimates)
11. **Do NOT confuse "executable strategy code" (FR10 wording) with free-form code generation** — D10 steers toward executable *specifications* (structured data consumed by rule engine), not arbitrary code. Research should optimize for spec generation and review, not code generation.
12. **Do NOT treat custom DSL or hybrid-expression options as equal default candidates** — D10's constrained rule-engine model explicitly avoids general-purpose interpreter complexity. These options require explicit architecture-change justification with system-objective evidence if recommended.

### Project Structure Notes

**Output file (research artifact):**
```
_bmad-output/
  planning-artifacts/
    research/
      data-pipeline-baseline-review.md              # Story 1-1 (existing)
      strategy-evaluator-baseline-review.md         # Story 2-1 (existing)
      strategy-definition-format-cost-modeling-research.md  # Story 2-2 (THIS)
```

**No source tree changes** — research stories do NOT create/modify files under `src/`, `crates/`, `config/`, or `contracts/`.

**Input files to read:**
- `_bmad-output/planning-artifacts/research/strategy-evaluator-baseline-review.md` — Story 2.1 output (MUST consume)
- `_bmad-output/planning-artifacts/architecture.md` — D10, D13, D14, D7
- `_bmad-output/planning-artifacts/prd.md` — FR9-FR13, FR20-FR22
- `_bmad-output/planning-artifacts/baseline-to-architecture-mapping.md` — Phase 0 research dependencies
- `_bmad-output/planning-artifacts/epics.md` — Epic 2 story details and dependencies

**Downstream consumers of this research:**
- Story 2.3 (Schema & Contracts) — uses format recommendation to create `contracts/strategy_specification.toml`
- Story 2.4 (Intent Capture) — uses format to build dialogue → specification flow
- Story 2.5 (Strategy Review & Diff) — uses format choice to determine diffability and human-readable summary generation
- Story 2.6 (Cost Model Artifact) — uses cost model research to build session-aware artifacts
- Story 2.7 (Cost Model Rust Crate) — uses artifact format to build `crates/cost_model/`
- Story 2.8 (Strategy Engine Crate) — uses format recommendation to build Rust spec parser
- Story 2.9 (E2E Proof) — validates all format and cost model choices work end-to-end

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 2: Strategy Definition & Cost Model, Story 2.2]
- [Source: _bmad-output/planning-artifacts/architecture.md — Decision 10: Strategy Execution Model]
- [Source: _bmad-output/planning-artifacts/architecture.md — Decision 13: Cost Model Crate]
- [Source: _bmad-output/planning-artifacts/architecture.md — Decision 14: Strategy Engine Shared Crate]
- [Source: _bmad-output/planning-artifacts/architecture.md — Decision 7: Configuration TOML]
- [Source: _bmad-output/planning-artifacts/architecture.md — Decision 12: Reconciliation Data Flow]
- [Source: _bmad-output/planning-artifacts/prd.md — FR9-FR13: Strategy Definition]
- [Source: _bmad-output/planning-artifacts/prd.md — FR20-FR22: Execution Cost Model]
- [Source: _bmad-output/planning-artifacts/prd.md — FR14, FR18: Backtesting with Cost Model]
- [Source: _bmad-output/planning-artifacts/prd.md — FR58-FR61: Artifact Management]
- [Source: _bmad-output/planning-artifacts/baseline-to-architecture-mapping.md — Phase 0 Research Dependencies]
- [Source: _bmad-output/implementation-artifacts/2-1-claudebacktester-strategy-evaluator-review.md — Previous Story]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

None — research story, no debug logs.

### Completion Notes List

- **Task 1 (Story 2.1 Consumption):** Consumed full 916-line research artifact. Extracted: 10-component verdict table (all Adapt), 18-indicator catalogue with signatures, current code-only format (no declarative spec), 5 pain points, gap analysis (9 baseline capabilities not in D10, 9 D10 requirements absent from baseline). Summarized MUST-support vs. open-for-research scope.
- **Task 2 (Format Research):** Evaluated 4 options against 5 weighted criteria. TOML scored 8.45/10 (best), JSON 7.90, DSL 5.35, Hybrid rejected. Concrete TOML examples demonstrated for all D10 constructs. Hybrid three-layer constraint validation recommended (definition-time Pydantic + load-time Rust serde + shared contracts).
- **Task 3 (Cost Research):** Investigated 4 broker spread sources (Dukascopy primary). Documented session-aware aggregation methodology. Cited 3 academic references (Hussain 2011, Ito et al. 2020, BIS 2020). Recommended mean/std + p95/p99 percentiles. Critical finding: cost model MUST consume pre-quarantine raw data to capture true spread distribution. D13 schema extended with commission, provenance, percentiles. Baseline gap quantified: ~900 pips/year unmodeled costs (corrected: $3.50/side × 2 = 0.70 pips commission per round-trip).
- **Task 4 (Research Artifact):** Wrote 10-section research artifact (~4,500 words) with full decision records, comparison matrices, example schemas, and build plan for Stories 2.3-2.9.
- **Task 5 (Validation):** Verified all 11 ACs satisfied. Cross-referenced D10 (three-layer preserved), D13 (additive refinements), D14 (no change). Zero downstream rewrite risk.

### Implementation Plan

Research story — no production code implemented. Research artifact produced at `_bmad-output/planning-artifacts/research/strategy-definition-format-cost-modeling-research.md`.

### File List

- `_bmad-output/planning-artifacts/research/strategy-definition-format-cost-modeling-research.md` — NEW (research artifact, primary deliverable)
- `_bmad-output/implementation-artifacts/2-2-strategy-definition-format-cost-modeling-research.md` — MODIFIED (task checkboxes, Dev Agent Record, Status)

### Change Log

- 2026-03-15: Story 2.2 research completed — TOML confirmed as strategy spec format (8.45/10), D13 cost model schema extended with percentiles + commission + provenance, quarantine interaction documented, build plan for 2.3-2.9 confirmed; review synthesis corrected matrix arithmetic and commission calculation
