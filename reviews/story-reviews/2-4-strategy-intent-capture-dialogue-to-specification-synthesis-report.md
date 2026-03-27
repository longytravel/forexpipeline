# Story Synthesis: 2-4-strategy-intent-capture-dialogue-to-specification

## Codex Observations & Decisions

### 1. System Alignment — Overreaching Scope
**Codex said:** Story tries to solve intent capture, default policy, optimization-plan generation, artifact versioning, and operator-facing summary behavior in one unit. Recommend simplifying to `dialogue → structured draft intent → validated draft spec`.
**Decision:** AGREE
**Reasoning:** The story was doing too much. Optimization plan generation and cost model references belong to downstream stories (2.8 and 2.6 respectively). Human-readable review is Story 2.5's job (FR11). Narrowing to "produce a validated draft spec with provenance" is the right scope.
**Action:** Removed auto-population of `optimization_plan`. Removed `"pending"` cost_model_reference placeholder. Changed spec status to "draft". Moved review/summary presentation responsibility to Story 2.5.

### 2. PRD Challenge — Missing Clarification Policy
**Codex said:** PRD Journey 1 says "the system asks clarifying questions" but this story defaults everything instead of defining when clarification is mandatory. FR11 belongs to Story 2.5.
**Decision:** AGREE
**Reasoning:** Confirmed: PRD Journey 1 explicitly says "The system asks clarifying questions: what pair, what timeframe, any specific conditions or filters?" Defaulting strategy-identity fields (indicators, entry logic) fabricates a different strategy than intended. FR11 is explicitly assigned to Story 2.5 in the epics.
**Action:** Added a Clarification Policy table with three tiers: must-have (fail if missing: indicators, entry logic), should-have (warn + default: pair, timeframe), may-default (silent: position sizing, stop loss params). Updated AC #3 and #4 to reflect this. Removed FR11 from story scope.

### 3. Architecture Challenge — Wrong Decision References (CRITICAL)
**Codex said:** D5 is process supervision (NSSM), not reproducibility. D12 is reconciliation data flow, not SQLite artifact coordination. Defaults should be in config/, not contracts/. Skills should invoke REST API per D9.
**Decision:** AGREE (verified against architecture.md)
**Reasoning:** Confirmed every claim:
- D5 = "Process Supervision — Windows Service via NSSM" (architecture.md ~L453)
- D12 = "Reconciliation Data Flow — Augmented Re-Run with Signal Diff" (architecture.md ~L823)
- D7 explicitly states: "every config key must exist in `base.toml` with a default" and "Implicit config values" is listed as an anti-pattern
- D9 says "Skills invoke REST API endpoints for mutations"
**Action:** Fixed all decision references. Replaced `contracts/strategy_defaults.toml` with `config/strategies/defaults.toml`. Added D9 note about REST API migration when orchestrator exists. Added explicit note that D5 and D12 do not apply. Moved reproducibility guidance to its own unlabeled section with correct hash semantics.

### 4. Architecture Challenge — Hash Confusion
**Codex said:** Story confuses `config_hash` with spec/content hashing. Says "hash will differ due to timestamps" which undermines reproducibility.
**Decision:** AGREE
**Reasoning:** The story conflated two distinct concepts: `spec_hash` (content hash of specification fields, deterministic) and `config_hash` (link to pipeline configuration state at confirmation time, set during Story 2.5 locking). Timestamps should NOT be in the spec_hash.
**Action:** Separated `spec_hash` (set here, content-based, deterministic) from `config_hash` (set during Story 2.5 confirmation). Updated CaptureResult, Task 7, logging, and tests accordingly.

### 5. Story Design — Input Contract Inconsistency
**Codex said:** Story says Python receives semi-structured input from skill, but tests exercise raw NL strings like "Try an EMA strategy".
**Decision:** AGREE
**Reasoning:** The design decision is correct — Python should receive structured data from the skill, not raw NL. But the tests contradicted this. The skill (Claude's AI layer) pre-processes dialogue into structured dict; Python does deterministic mapping.
**Action:** Changed `parse_strategy_intent` signature to accept `dict` (structured input from skill). Updated all test descriptions to use "structured dict input" instead of raw NL strings. Added explicit note in Task 10 that the skill outputs a JSON dict.

### 6. Story Design — AC3 Not Testable
**Codex said:** "Sensible defaults" is subjective and not testable.
**Decision:** AGREE
**Reasoning:** Replaced subjective "sensible defaults" with explicit clarification policy (must-have/should-have/may-default) and provenance tracking. Now each default source is verifiable.
**Action:** Split old AC3 into new AC3 (must-have fields fail) and AC4 (may-default fields get provenance). Added provenance map (`field_provenance: dict[str, str]`) replacing `defaults_applied: list[str]`.

### 7. Downstream Impact — Provenance Artifact
**Codex said:** Story 2.5 will need to know what came from operator vs default vs inference. Without provenance, 2.5 must reverse-engineer it.
**Decision:** AGREE
**Reasoning:** Story 2.5 needs to present "what was assumed" vs "what you said". A provenance map is the right contract between 2.4 and 2.5.
**Action:** Added `field_provenance: dict[str, str]` (maps field → "operator"|"default"|"inferred") to StrategyIntent and CaptureResult. Added test for provenance tracking.

### 8. Downstream Impact — Fake Cost Model and Optimization Plan
**Codex said:** `"pending"` cost_model_reference and auto-populated optimization plans create artifacts that look precise without being trustworthy.
**Decision:** AGREE
**Reasoning:** Cost model is Story 2.6. Optimization setup is Story 2.8. Fabricating placeholder values violates the reproducibility principle — downstream stages might try to use them.
**Action:** Changed to leave optimization_plan empty/minimal and cost_model_reference null/unset. Added anti-patterns #11, #12 to prevent this. Added two negative tests: `test_generate_specification_no_optimization_plan` and `test_generate_specification_no_cost_model`.

### 9. Deterministic Output Tests
**Codex said:** Add deterministic tests that prove same input + config = same spec.
**Decision:** AGREE
**Reasoning:** This is the core V1 value proposition — reproducibility. A determinism test is essential.
**Action:** Added AC #9 (deterministic output requirement). Added `test_deterministic_output` test case.

### 10. Dependency on Stories 2.1/2.2
**Codex said:** Add explicit dependency/gating on Stories 2.1 and 2.2 if parser vocabulary relies on their findings.
**Decision:** DISAGREE
**Reasoning:** Stories 2.1 and 2.2 are research stories that inform the indicator vocabulary, but the dialogue parser works with a known initial set of indicators (MA, EMA, RSI, MACD, ATR, Bollinger). The indicator registry from Story 2.3 is the hard contract — if 2.1/2.2 expand it, the parser just needs more mappings added. This is not a blocking dependency.
**Action:** None. The existing soft reference in "What to Reuse from ClaudeBackTester" section is sufficient.

### 11. Route Skill Through API Boundary
**Codex said:** Route the skill through the documented orchestration boundary (REST API per D9).
**Decision:** DEFER
**Reasoning:** D9 says skills invoke REST API for mutations, which is architecturally correct. But the orchestrator API (FastAPI) doesn't exist yet — it's built in later epics. Requiring it now would create a circular dependency. Instead, document the exception and add a migration TODO.
**Action:** Added explicit D9 note in architecture constraints. Added TODO comment requirement in Task 10. Added anti-pattern note referencing future migration.

### 12. Emit a Bundle, Not Just a Spec
**Codex said:** Make Story 2.4 emit a bundle: raw input transcript, normalized intent, provenance map, validation report, and draft spec.
**Decision:** PARTIALLY AGREE
**Reasoning:** A full bundle is over-engineering for V1. But the provenance map and CaptureResult already provide the essential pieces: the spec itself, the provenance map, the spec_hash, and the saved path. Story 2.5 can reconstruct what it needs from these. Adding a formal "validation report" artifact is unnecessary — the validation either passes (spec is saved) or fails (error is raised).
**Action:** CaptureResult already includes: spec, saved_path, version, field_provenance, spec_hash. This is sufficient without creating a separate bundle format.

## Changes Applied

### Acceptance Criteria
- Split old AC3 into AC3 (must-have fields fail) + AC4 (non-identity defaults with provenance)
- Renumbered AC4→AC5 (schema validation), AC5→AC6 (D10 flow), AC6→AC7 (versioned artifact)
- Renumbered AC7→AC8 (logging, fixed D6 label)
- Added AC9 (deterministic output requirement)
- Added Clarification Policy table (must-have / should-have / may-default)

### Tasks
- Task 2: `contracts/strategy_defaults.toml` → `config/strategies/defaults.toml` (D7 compliance)
- Task 4: Changed input from `str` to `dict`. Added clarification policy enforcement. Replaced `defaults_applied` with `field_provenance`
- Task 5: Updated config path. Changed tracking to provenance map
- Task 6: Removed optimization_plan auto-population. Removed `"pending"` cost_model_reference. Added `status: "draft"`. Changed `defaults_applied` to `field_provenance`
- Task 7: Separated `spec_hash` (content hash, set here) from `config_hash` (set in Story 2.5)
- Task 8: Updated log events to include provenance fields, spec_hash, and draft status
- Task 9: Updated CaptureResult to use `field_provenance` and `spec_hash`
- Task 10: Narrowed skill scope — no review/summary (Story 2.5). Added D9 migration TODO. Changed to JSON structured input
- Task 11: 21 tests (up from 17). Added: clarification policy tests, provenance tracking, determinism, negative tests for optimization_plan and cost_model

### Dev Notes
- Fixed architecture references: removed D5 and D12 (inapplicable). Added D9 with documented exception
- Corrected hash semantics: `spec_hash` here, `config_hash` in Story 2.5
- Updated config path throughout
- Added anti-patterns #11 (no optimization plans), #12 (no fake cost_model), #13 (no review presentation)
- Updated project structure (config/strategies/defaults.toml)
- Updated references section

## Deferred Items
- D9 REST API migration: when the orchestrator API layer is built (Epic 5+), the skill should be migrated from direct Python invocation to REST API calls
- Full bundle format: if Story 2.5 implementation reveals that CaptureResult is insufficient, a formal bundle artifact can be introduced then

## Verdict
VERDICT: IMPROVED
