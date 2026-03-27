# Story Synthesis: 5-2b-optimization-search-space-schema-range-proposal

## Codex Observations & Decisions

### 1. System Alignment — Persisted Proposal Artifact & Fallback Handling
**Codex said:** Story lacks persisted proposal artifact with input hashes, per-parameter rationale, and provenance. Hardcoded ATR/spread fallbacks weaken fidelity. "40+ parameters" target is beyond V1 minimum.
**Decision:** PARTIALLY AGREE
**Reasoning:** Persisted proposal artifact with provenance is a genuine reproducibility gap — accepted. Hardcoded ATR/spread fallbacks are practical for a solo operator who may not have all data downloaded yet; requiring formal review states for data availability is over-engineering. The "40+ parameters" is a capability statement for schema design, not a V1 gate — the schema must support the taxonomy now even though V1 only exercises the reference strategy.
**Action:** Added AC11 (persisted proposal artifact with provenance metadata). Updated AC5 to explicitly log warnings and mark fallback sources as `source: "default"`. Added `persist_proposal()` to Task 4.

### 2. PRD Challenge — FR13/FR24 Contradiction & Searchable-vs-Fixed
**Codex said:** FR13 and FR24 are internally conflicted about stages vs flat. Story needs searchable-vs-fixed parameter selection and proposal provenance.
**Decision:** PARTIALLY AGREE
**Reasoning:** The FR13/FR24 tension was already resolved by Story 5.2 optimization research — the spec defines searchable parameters, the optimizer owns grouping. This is correct but was implicit in the story. The searchable-vs-fixed distinction is clear by design (listed in `parameters` = searchable, not listed = fixed) but deserves explicit documentation. Rewriting PRD wording is out of scope for this story.
**Action:** Added "FR13/FR24 Resolution" dev note section explaining the research resolution. Added "Parameter Naming Convention" section making the searchable-vs-fixed design explicit.

### 3. Architecture Challenge — Optimizer Internals Leaking Into Schema
**Codex said:** Story leaks optimizer internals (ParameterSpace branch decomposition, UCB1 budget allocation) into schema layer, violating D3. Skills should go through API/orchestrator per D9. Hardcoded pip/spread should be in contracts.
**Decision:** PARTIALLY AGREE
**Reasoning:** The UCB1/budget allocation details in the contract doc and dev notes do leak 5-3 implementation concerns — accepted, removed. The `parse_strategy_params()` contract doc defining the data shape is appropriate (this story defines what 5-3 consumes). Pipeline skill operating directly on TOML files is correct for V1 — D9's API/orchestrator route is post-V1 architecture. Moving pip/spread to contract files adds scope without V1 benefit.
**Action:** Updated AC10 to explicitly state "data shape contract only, NOT optimizer search policy." Rewrote `parse_strategy_params()` contract summary to remove UCB1/budget references. Updated D3 constraint note to emphasize boundary. Added D9 note clarifying V1 skill commands operate directly on files.

### 4. Story Design — Vague ACs, Self-Contradiction, Story Size, Legacy Handling
**Codex said:** "Sensible," "pair-appropriate," and "operator can review" are vague and untestable. Story contradicts itself on hardcoding. Should split into two stories. Legacy handling is weak.
**Decision:** PARTIALLY AGREE
**Reasoning:**
- Vague ACs: Valid — tightened with concrete bounds and testability criteria. Accepted.
- Hardcoding contradiction: Not actually a contradiction — anti-pattern #2 means "don't hardcode strategy-specific ranges in Python," while the timeframe tables and ATR defaults are engine infrastructure constants. But the distinction was unclear. Clarified anti-pattern #2 with explicit explanation. Accepted.
- Split into two stories: DISAGREE. The schema and proposal engine are tightly coupled — the engine's purpose is to populate the schema. Splitting creates artificial dependencies and coordination overhead for a solo operator. The story is large but well-structured with clear task boundaries.
- Legacy handling: Added schema_version field (AC12) and SchemaVersionError for v1 format detection. Accepted.
**Action:** Tightened AC4 with testability criteria. Tightened AC5 with explicit fallback behavior. Tightened AC6 with concrete review mechanisms. Added AC12 for schema versioning. Clarified anti-pattern #2. Updated Tasks 1, 2, 5 for schema_version. Added 3 new test cases for legacy format handling.

### 5. Downstream Impact — Parameter ID Collisions, ParameterSpace Weakness, Provenance
**Codex said:** Flat dict has no canonical parameter ID scheme — names will collide across entry/exit/filters. `branches[(categorical, choice)]` is too weak for multiple independent top-level categoricals. Proposal output lacks provenance.
**Decision:** PARTIALLY AGREE
**Reasoning:**
- Parameter ID collisions: Real concern for complex strategies, but V1's reference strategy uses distinct prefixed names (fast_period, sl_atr_multiplier, etc.). Adding canonical dotted paths (entry.fast_ma.period) is over-engineering for V1. A naming convention dev note is sufficient — the pattern is demonstrated in v002.
- ParameterSpace weakness: This is Story 5-3's problem, not this story's. The flat parameter registry handles multiple categoricals fine — how the optimizer decomposes them is 5-3's domain per D3.
- Provenance: Addressed via AC11 (observation 1).
**Action:** Added "Parameter Naming Convention" dev note with component-prefix convention and explicit deferral of canonical dotted paths to post-V1. Noted that ParameterSpace complexity is 5-3's domain.

### 6. Recommended Change: Rewrite story goal (Codex #1)
**Codex said:** Rewrite the story goal so the primary deliverable is a flat, deterministic search-space contract; make intelligent range proposal a separate advisory artifact.
**Decision:** DISAGREE
**Reasoning:** The story already treats the schema as primary and the proposal engine as advisory (AC6: "not a mandate", anti-pattern #3: "not a gate"). Splitting into separate stories creates artificial dependencies. The story goal accurately describes both deliverables. The added AC11 (persisted proposal artifact) makes the advisory nature even more explicit.
**Action:** None — story goal is accurate as-is.

### 7. Recommended Change: Pipeline commands through orchestrator/API (Codex #8)
**Codex said:** Move pipeline command changes into a separate story, or require commands to call the orchestrator/API.
**Decision:** DISAGREE
**Reasoning:** V1 is a solo operator CLI tool. Pipeline skill commands that directly edit TOML files are the simplest correct approach. The API/orchestrator layer doesn't exist yet and adding it for three search-space commands is premature. Task 7 is small (3 commands) and directly serves the story's operator workflow.
**Action:** None — Task 7 stays. Added D9 dev note clarifying V1 direct-file approach.

### 8. Recommended Change: Canonical parameter paths (Codex #4)
**Codex said:** Add canonical parameter ID/path scheme such as `entry.fast_ma.period`.
**Decision:** DEFER
**Reasoning:** Valid concern for future complex strategies with duplicate parameter names across components. For V1 with one strategy family, component-prefixed names (fast_period, sl_atr_multiplier) are sufficient and simpler. The naming convention dev note documents this decision and the migration path. Adding dotted paths now would complicate the TOML schema, Pydantic models, and TOML file readability without V1 benefit.
**Action:** Added dev note documenting naming convention and explicit deferral to post-V1.

### 9. Recommended Change: Searchable vs fixed parameter marking (Codex #5)
**Codex said:** Add explicit mechanism to mark parameters as searchable vs fixed.
**Decision:** DISAGREE
**Reasoning:** The flat `parameters` dict IS the searchable parameter set. Parameters listed = searchable with the declared bounds. Parameters not listed = fixed at their spec values. This is the simplest possible design and doesn't need an additional `searchable: bool` field. The FR13/FR24 Resolution dev note makes this explicit.
**Action:** Added dev note clarifying the inclusion/exclusion design.

## Changes Applied

1. **AC4** — Added testability criteria: deterministic output, concrete range constraints, layer-by-layer verification
2. **AC5** — Added explicit fallback behavior: WARNING log, `source: "default"` marking in proposal output
3. **AC6** — Added concrete review mechanisms: TOML editing, pipeline skill commands
4. **AC10** — Scoped to "data shape contract only," removed optimizer search policy language
5. **AC11 (new)** — Persisted proposal artifact with provenance: timestamp, ATR stats source, per-parameter source layer, indicator registry hash
6. **AC12 (new)** — Schema versioning: `schema_version = 2` field, `SchemaVersionError` for legacy format detection
7. **Task 1** — Added schema_version field to TOML contract, linked to AC12
8. **Task 2** — Added `schema_version: Literal[2]` to OptimizationPlan Pydantic model
9. **Task 4** — Added `persist_proposal()` function, linked to AC11
10. **Task 5** — Added schema_version to v002.toml, linked to AC12
11. **Task 6** — Rewrote contract doc to "data shape only," removed UCB1/budget allocation language
12. **Task 8** — Added 5 new test cases: schema_version validation (3), proposal artifact persistence (2)
13. **Dev Notes: D3** — Strengthened to explicitly prohibit leaking optimizer internals
14. **Dev Notes: D9** — Clarified V1 direct-file approach for pipeline skills
15. **Dev Notes: FR13/FR24 Resolution** — New section explaining research-phase resolution
16. **Dev Notes: Parameter Naming Convention** — New section with component-prefix convention and post-V1 deferral
17. **Anti-pattern #2** — Clarified distinction between strategy ranges (must not hardcode) and engine metadata (acceptable constants)
18. **parse_strategy_params() Contract Summary** — Removed UCB1/budget allocation details, scoped to data shape
19. **Files to Create** — Added optimization_proposal.json artifact

## Deferred Items

- **Canonical dotted parameter paths** (e.g., `entry.fast_ma.period`) — deferred to post-V1 if complex multi-indicator strategies require disambiguation beyond component-prefix naming
- **Pip/spread metadata in contract files** — valid concern about hardcoded instrument metadata in Python code, but moving to contracts adds scope without V1 benefit. Revisit when supporting >8 pairs.
- **Pipeline skill commands through API/orchestrator** — valid architecture concern per D9, but API layer doesn't exist in V1. Revisit when API routes are implemented (Epic 6+).
- **ParameterSpace handling of multiple independent top-level categoricals** — Story 5-3's domain per D3. Flag to 5-3 implementor to design for this case.

## Verdict
VERDICT: IMPROVED
