# PIR: Story 2-8-strategy-engine-crate-specification-parser-indicator-registry — Story 2.8: Strategy Engine Crate — Specification Parser & Indicator Registry

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-17
**Codex Assessment Available:** Yes

## Codex Assessment Summary

Codex rated Objective Alignment ADEQUATE, Simplification ADEQUATE, Forward Look CONCERN, Overall OBSERVE. Key observations and my evaluation:

### 1. ValidatedSpec does not persist a validation artifact — only test serialization proves it works
**AGREE — acceptable boundary.** Codex correctly notes that the crate returns `ValidatedSpec` and `Vec<ValidationError>` as in-memory contracts but does not itself write a validation artifact to disk. This is the right boundary. The crate is a library (no CLI, no I/O beyond spec loading per D14). Persistence is the orchestration layer's job, and Story 2.9's E2E proof will exercise serialization. The integration tests do verify JSON roundtrip of `ValidationError` and TOML re-serialization of `ValidatedSpec`, confirming the contract is serialization-ready.

### 2. validate_spec() can return Ok without proving cost model artifact exists (cost_model_path is optional)
**AGREE — by design, well-justified.** The synthesis report's rejected finding #4 explains this clearly: Task 5 explicitly says "If `cost_model_path` is provided, attempt..." The optionality enables test contexts where cost model artifacts are not available. In production, the orchestrator will supply the path. This matches the library pattern from Story 2.7's cost_model crate, where the caller controls I/O context.

### 3. Simpler V1 would have validate_spec() build default_registry() internally, keeping registry closed
**DISAGREE — injectable registry is the right design.** The injectable `IndicatorRegistry` parameter serves testability (tests can construct registries with specific indicators) and matches the story spec's explicit Task 5 signature. The overhead is one extra parameter. Closing the registry internally would force consumers to fork or monkey-patch to test edge cases. The current design is not over-engineered — it's the minimum needed for testable validation.

### 4. Cost model lookup reconstructs filename convention internally (EURUSD_<version>.json)
**AGREE — minor coupling, acceptable for V1.** The validator reconstructs the artifact path from a version string and a base directory. This embeds the naming convention in two places (validator + whatever produces the artifacts). For V1 with a single pair, this is tolerable. Multi-pair expansion (Epic 3+) will need either a manifest lookup or an explicit path in the spec. The pattern is isolated to a single function, making it easy to change.

### 5. Cross-runtime parity test remains unfinished
**AGREE — the most significant gap, but properly tracked.** The parity test was honestly unchecked in the story spec during synthesis (finding #1). The Python live tests verify crate existence, build success, and dependency facts — not semantic parity. This gap matters because the architecture (D14) positions this crate as the shared strategy boundary for backtest/live fidelity. However: (a) the parity test was always a "best-effort" item given that Python and Rust validators have different structures, and (b) Story 2.9's E2E proof will exercise the Rust parser on the same fixtures the Python pipeline produces, providing de-facto parity evidence.

### 6. Parsed model is schema-shaped, not evaluation-shaped (strings for comparators, exit types, etc.)
**AGREE — correct for this story's scope.** The story spec explicitly states "NO per-bar evaluation logic." Schema-shaped types (string comparators, BTreeMap params) are exactly right for a parser/validator. Epic 3 will need a normalization/interpreter layer to dispatch on these strings, but that's evaluation-layer responsibility. Building typed enums now would prematurely couple the parser to the evaluator's internal representation.

### 7. config_hash is optional, full traceability deferred
**AGREE — acceptable.** Earlier pipeline stages (intent capture, review) may produce specs before a config hash is computed. Making it optional keeps the crate compatible with all workflow stages. The validator checks it when present. Full traceability is a system-level concern that the orchestration layer will enforce.

## Objective Alignment
**Rating:** STRONG

This story advances the core system objectives effectively:

- **Reproducibility (FR12, FR59, FR61):** `deny_unknown_fields` on all 15 structs rejects schema drift at parse time. `BTreeMap` for indicator params and registry entries ensures deterministic ordering. The validation pass order is fixed (metadata → entry_rules → exit_rules → filters → position_sizing → optimization_plan → cost_model_reference), producing reproducible error output. The `ValidatedSpec` newtype wrapper guarantees the spec passed all checks — consumers cannot construct one without going through `validate_spec()`.

- **Operator confidence (D8, FR58):** Parse errors and validation errors are cleanly separated: `ParseError` for structural failures (fail-fast, single error with file/line context), `ValidationErrors` for semantic failures (collect-all, structured section/field/reason/severity). This gives operators a complete diagnostic view in one pass. The `Display` impl on `ValidationError` produces readable `[ERROR] section.field: reason` output. Serializable `ValidationError` enables machine-readable evidence packs.

- **Artifact completeness:** The crate produces serialization-ready outputs (`ValidatedSpec` serializes to TOML, `ValidationError` serializes to JSON via `serde::Serialize`), but does not itself persist artifacts. This is the correct boundary for a library crate — persistence is the orchestrator's responsibility.

- **Fidelity (FR19, D14):** This crate is the shared parsing/validation layer that both `backtester` and `live_daemon` will depend on. By ensuring both runtimes parse and validate against the same types, registry, and rules, it provides the foundation for signal fidelity. The actual fidelity guarantee comes when Epic 3 builds the evaluator on top of this foundation.

The synthesis report shows 9 genuine validation gaps were caught and fixed with regression tests, including contract-bound enforcement (risk_percent [0.1, 10.0], max_lots [0.01, 100.0]), version pattern validation (v\d{3}), V1 pair constraint (EURUSD), and bidirectional optimization param/ranges cross-validation. This demonstrates the review process working as intended.

## Simplification
**Rating:** STRONG

The implementation is lean and appropriately scoped:

- **Module count:** 4 source files (`types.rs`, `parser.rs`, `registry.rs`, `validator.rs`) plus `error.rs` and `lib.rs`. No unnecessary abstractions.
- **Dependencies:** `serde`, `toml`, `thiserror`, workspace crates only. `serde_json` is dev-only (for test serialization). No runtime JSON processing.
- **Type design:** `IndicatorParams = BTreeMap<String, toml::Value>` is the key simplification — it keeps the parser generic while the registry validates per-indicator constraints. This avoids a premature typed indicator parameter IR.
- **No evaluation code:** The story correctly stops at parsing/validation/registry. No evaluator, no indicator computation, no trade simulation. Zero Epic 3 scope creep.
- **IndicatorDef metadata** (`name`, `category`, `description`): Codex flagged these as having no current consumer. I view this as negligible overhead (3 string fields per indicator definition, 4 indicators total) that will serve diagnostic output in Epic 3.

One area where simplification could improve: the `Severity::Warning` variant exists but no code currently emits warnings. This is dead code today but will activate when non-critical validation findings are needed (e.g., "config_hash is empty" could be a warning). The cost is one enum variant — acceptable.

## Forward Look
**Rating:** ADEQUATE

The output contract is well-defined for downstream consumption, with a few tracked gaps:

**Strengths:**
- `ValidatedSpec` and `Vec<ValidationError>` are the explicit machine-readable outputs for Story 2.9 and evidence packs. Integration tests verify serialization roundtrip.
- The public API surface (`parse_spec_from_file`, `parse_spec_from_str`, `validate_spec`, `default_registry`) is stable and matches what Epic 3 consumers need.
- The dependency graph is correct: `strategy_engine → common + cost_model` only. No circular deps. The `backtester` and `live_daemon` can depend on it without cycles.
- Types align with `contracts/strategy_specification.toml` (source of truth). The contract-first approach means downstream stories consume a stable schema.

**Gaps to monitor:**
- **Parity test deferred:** Cross-runtime parity between Rust and Python validators is the single largest forward-looking gap. Story 2.9's E2E proof will provide partial evidence, but an explicit parity test should be scheduled for Epic 3 setup. The shared TOML fixtures provide the mechanism — what's missing is the automated comparison.
- **EURUSD hardcoding:** The validator rejects non-EURUSD pairs and the cost model lookup assumes `EURUSD_<version>.json`. This is correct for V1 but means multi-pair expansion requires validator changes, not just new data. This is documented and expected.
- **Schema-shaped types for Epic 3:** Comparators, exit types, sizing methods, and objective functions are all strings validated against constant arrays. Epic 3 will need dispatch logic (match on string → typed behavior). This is a deliberate design choice: the parser shouldn't know about evaluation semantics. The constant arrays (`VALID_COMPARATORS`, `VALID_STOP_LOSS_TYPES`, etc.) provide a centralized source of truth for both validation and future dispatch.

## Observations for Future Stories

1. **Schedule an explicit parity test in Epic 3 setup.** The mechanism exists (shared TOML fixtures, both runtimes parse the same format). What's needed is an automated test that parses the same fixture in both Python and Rust and asserts they accept/reject it for the same reasons. This was deferred from Story 2.8 for pragmatic reasons, but it's load-bearing for the D14 fidelity guarantee.

2. **Contract-bound enforcement should be a review checklist item.** The synthesis caught 4 cases where the validator enforced looser bounds than the contract specified (risk_percent, max_lots, version pattern, pair values). Future stories with validators should include "verify all contract bounds are enforced exactly" as a mandatory review check.

3. **Version pattern validation reuse.** The `is_valid_version_pattern()` helper is now used for both `metadata.version` and `cost_model_reference.version`. If other crates need the same pattern, consider promoting it to the `common` crate.

4. **Cost model path resolution convention.** The `EURUSD_<version>.json` convention is currently embedded in the validator. When multi-pair support arrives, extract this into a shared path-resolution function (or use a manifest lookup) to avoid duplicating the convention across crates.

5. **Deferred-task tracking discipline is improving.** The synthesis correctly caught and fixed the false completion claim on the parity test checkbox. The lessons-learned entry reinforces: "When deferring a task, immediately uncheck it." This pattern should continue.

## Verdict
VERDICT: ALIGNED

The story delivers a solid, well-scoped parsing/validation/registry foundation for the strategy engine. It serves reproducibility (deterministic types, deny_unknown_fields, BTreeMap ordering), operator confidence (structured errors, collect-all validation), and sets up downstream fidelity (shared crate architecture per D14). The synthesis process caught and fixed 9 genuine validation gaps with regression tests. The deferred parity test is the main gap, but it's honestly tracked and partially addressed by shared fixtures. The implementation is lean (4 modules, minimal deps, zero Epic 3 scope creep) and the output contract (ValidatedSpec + ValidationError) is serialization-ready for Story 2.9's E2E proof. No significant alignment concerns.
