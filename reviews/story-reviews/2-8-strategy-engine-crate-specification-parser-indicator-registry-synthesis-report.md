# Story Synthesis: 2-8-strategy-engine-crate-specification-parser-indicator-registry

## Codex Observations & Decisions

### 1. D14 Contradiction — Rename/Split Crate or Align to Shared-Crate Boundary
**Codex said:** D14 defines `strategy_engine` with `evaluator.rs`, `indicators.rs`, `filters.rs`, `exits.rs`, but this story bans those modules. Either rename/split into a `strategy_spec` crate, or align to D14's full scope.
**Decision:** DISAGREE
**Reasoning:** The story's scoping is deliberate and correct. D14's full module list spans multiple epics — this story implements the foundation modules (types, parser, registry, validator), and Epic 3 will ADD the evaluation modules to the same crate. The epics.md Story 2.8 description is specifically "Specification Parser & Indicator Registry." Renaming the crate would cause confusion since Epic 3 builds on top of it. The story already documents this explicitly in "Scope Boundaries" and "Alignment with Architecture" sections (lines 252-253).
**Action:** None.

### 2. Remove Direct cost_model Loading / Dependency
**Codex said:** `cost_model_reference` should remain a versioned artifact reference, not a file path. Remove `cost_model` as a dependency to keep `strategy_engine` pure.
**Decision:** DISAGREE
**Reasoning:** Epics.md Story 2.8 AC6 explicitly states: "cross-validates cost_model_reference against a loadable cost model artifact (via cost_model crate dependency)." Removing this would contradict the epics. The story already handles this pragmatically — `validate_spec()` takes `cost_model_path: Option<&Path>`, making cross-validation optional. The "pure computation" aspect of D14 refers to the per-bar evaluation phase (Epic 3), not the one-time validation phase. Validation naturally needs to verify references. The coupling is minimal and justified.
**Action:** None. The existing optional pattern is sufficient.

### 3. Single Format — Remove JSON Support
**Codex said:** Story 2.3 locks a TOML contract. Supporting JSON is unnecessary scope creep.
**Decision:** AGREE
**Reasoning:** Story 2.3 locks the contract as `contracts/strategy_specification.toml`. V1 has one deterministic path. JSON support adds untested code paths and no operator value. If JSON is needed later, it can be added trivially.
**Action:** Removed `SpecFormat` enum, JSON parsing, `serde_json` from main dependencies (kept as dev-dependency for ValidationError serialization in tests). Simplified parser API to TOML-only.

### 4. Rust Model Must Align to Contract File
**Codex said:** Replace "hand-written Rust model is the source of truth" with "Rust model must align exactly to `contracts/strategy_specification.toml`."
**Decision:** AGREE
**Reasoning:** The contract from Story 2.3 is the source of truth. Rust types should mirror it, not independently invent structure. This prevents contract drift between Python and Rust.
**Action:** Added note to Task 2 that types MUST align exactly with Story 2.3 contract. Added "Contract Alignment — Source of Truth" dev note section.

### 5. Cross-Runtime Parity Tests Against Story 2.3 Python Validator
**Codex said:** Add parity tests ensuring Rust and Python validators agree.
**Decision:** AGREE
**Reasoning:** Both Story 2.3 (Python) and Story 2.8 (Rust) validate the same specification format. They must agree on what's valid/invalid. Shared test fixtures and cross-validation prevent silent divergence that would undermine signal fidelity (FR19).
**Action:** Added `parity_test.rs` test file with two test cases: `test_rust_agrees_with_python_on_valid_spec` and `test_rust_agrees_with_python_on_invalid_spec`.

### 6. Add or Defer Regime Filter Support
**Codex said:** D10 mentions `filters[] (session, regime, day_of_week)` but the story only has session, volatility, day_of_week. Missing `regime` filter.
**Decision:** DEFER
**Reasoning:** Story 2.3's contract (AC2) explicitly lists "session filters" and "volatility filters" — no regime filter in V1 scope. The architecture's "regime detection" is a session-awareness concern used in analytics (Growth scope), not a strategy filter for V1's minimum representable constructs. Adding it now would be scope creep with no V1 consumer.
**Action:** None. Valid for future consideration when regime-based strategies enter the pipeline.

### 7. Replace HashMap with Deterministic Ordering
**Codex said:** Architecture warns about HashMap nondeterminism. Registry uses HashMap for indicator lookup.
**Decision:** AGREE
**Reasoning:** While the registry's primary operation is O(1) lookup (where HashMap vs BTreeMap doesn't matter for correctness), the registry also supports enumeration (AC3: "enumerates all supported indicator types"). Deterministic enumeration order ensures reproducible validation error output and testable behavior. BTreeMap provides both O(log n) lookup and deterministic iteration. With only 4 indicators in V1, the performance difference is negligible.
**Action:** Changed `HashMap<String, IndicatorDef>` to `BTreeMap<String, IndicatorDef>` in Task 4.

### 8. Split Parse/Schema Failures from Semantic Validation Failures
**Codex said:** ACs and tests don't clearly distinguish parse errors from semantic validation errors.
**Decision:** AGREE
**Reasoning:** Parse errors (structural, from serde/TOML deserializer) are fail-fast single errors. Semantic validation errors (from `validate_spec()`) are collect-all. These are fundamentally different categories with different caller expectations. Conflating them leads to confusing error handling.
**Action:** Added "Error Category Distinction" dev note section. Updated `StrategyEngineError` description in Task 3 to explicitly distinguish `ParseError` (fail-fast) from `ValidationErrors` (collect-all). Added `test_parse_error_is_distinct_from_validation_error` test. Fixed `invalid_bad_params.toml` fixture note (period: -1 is a parse error for `u32`, not a semantic validation error — use period: 0 instead).

### 9. Machine-Readable Validation Report for Story 2.9
**Codex said:** Add a stable machine-readable validation output contract for downstream evidence packs.
**Decision:** AGREE (partially)
**Reasoning:** `ValidatedSpec` and `Vec<ValidationError>` are already the machine-readable outputs. No separate "report" struct is needed — that's orchestration-layer concern. But `ValidationError` should derive `Serialize` so Story 2.9 and evidence packs can persist it as JSON.
**Action:** Added `serde::Serialize` derive requirement on `ValidationError` and `Severity`. Added "Validation Output as Machine-Readable Contract" dev note section covering serialization, deterministic output, and round-trip identity.

### 10. Rework IndicatorParams/Condition for Real Extensibility
**Codex said:** `IndicatorParams` as a bag of optional fields and `Condition` as `indicator + threshold + comparator` is brittle and will force rewrites.
**Decision:** DISAGREE
**Reasoning:** The current design is pragmatic for V1 with exactly 4 indicators. The bag-of-optionals pattern + registry validation is a reasonable V1 approach — the registry enforces which fields are required per indicator type. A more sophisticated type system (trait objects, enum variants per indicator type) adds compile-time complexity without V1 benefit. If Epic 3's evaluation needs force a rework, it can happen then with real usage patterns to guide the design. Premature abstraction is an anti-pattern this project explicitly avoids.
**Action:** None.

### 11. Remove cost_model Dependency Unless Architecture Updated
**Codex said:** Same concern as observation 2 — strategy_engine should depend on common only per architecture.
**Decision:** DISAGREE
**Reasoning:** Same as observation 2. The epics explicitly require this dependency for cross-validation. The architecture's project structure listing may show `common` only as the primary dependency, but D13 explicitly describes cross-validation between strategy specifications and cost models, and the epics operationalize this as a crate dependency.
**Action:** None.

### 12. Deterministic Serialized Identity of ValidatedSpec
**Codex said:** Add an AC for deterministic serialized identity tied to spec version and config_hash.
**Decision:** AGREE (partially — as dev note, not AC)
**Reasoning:** Deterministic round-trip serialization supports reproducibility (FR19). The `config_hash` in Metadata already handles identity. Adding a full AC would over-specify — but a dev note ensuring round-trip determinism is valuable guidance.
**Action:** Added to "Validation Output as Machine-Readable Contract" dev note: round-trip (deserialize → validate → serialize) should produce deterministic output.

## Changes Applied
1. **Task 2:** Added note that types MUST align exactly with `contracts/strategy_specification.toml` from Story 2.3
2. **Task 1:** Removed `serde_json` from main dependencies (TOML-only per Story 2.3)
3. **Task 3:** Simplified parser to TOML-only — removed `SpecFormat` enum and JSON parsing. Added explicit parse vs validation error distinction
4. **Task 4:** Changed `HashMap` to `BTreeMap` for deterministic registry enumeration
5. **Task 6:** Fixed `invalid_bad_params.toml` fixture (period: 0 not -1 for semantic validation). Removed `test_parse_valid_json_spec`. Added `test_parse_error_is_distinct_from_validation_error`. Added cross-runtime parity test file
6. **Dev Notes:** Added three new sections: "Error Category Distinction", "Contract Alignment — Source of Truth", "Validation Output as Machine-Readable Contract"
7. **Pattern Continuity:** Updated dependencies list to reflect TOML-only
8. **Project Structure:** Updated Cargo.toml comment to reflect no serde_json
9. **Validator Task 5:** Added `serde::Serialize` derive requirement on `ValidationError` and `Severity`

## Deferred Items
- **Regime filter support** — Valid concern but not in V1 scope per Story 2.3 contract. Note for future when regime-based strategies enter the pipeline.
- **IndicatorParams/Condition rework** — Monitor during Epic 3 evaluation implementation. If the bag-of-optionals pattern causes friction, refactor then with real usage patterns.

## Verdict
VERDICT: IMPROVED
