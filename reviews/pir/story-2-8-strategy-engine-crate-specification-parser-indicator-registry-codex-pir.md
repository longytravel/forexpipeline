# Story 2-8-strategy-engine-crate-specification-parser-indicator-registry: Story 2.8: Strategy Engine Crate — Specification Parser & Indicator Registry — Codex PIR

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-17
**Type:** Post-Implementation Review (alignment analysis)

---

**1. Objective Alignment**

Assessment: `ADEQUATE`

Specific evidence:
- Reproducibility is materially improved by constrained parsing and deterministic data structures: `deny_unknown_fields`, `BTreeMap` for indicator params/ranges, and a fixed validation pass order in [types.rs#L6](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/types.rs#L6), [types.rs#L54](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/types.rs#L54), [types.rs#L162](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/types.rs#L162), [registry.rs#L38](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/registry.rs#L38), [validator.rs#L45](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L45). That directly supports FR12/FR59/FR61 in [prd.md#L475](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L475), [prd.md#L551](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L551), [prd.md#L554](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L554).
- Operator confidence is improved by clear boundary behavior: parse errors vs semantic validation errors are separated, file-path context is added on parse-from-file, and semantic validation returns structured section/field/reason/severity findings in [parser.rs#L8](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/parser.rs#L8), [error.rs#L7](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/error.rs#L7), [validator.rs#L16](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L16). The story explicitly positions these as machine-readable outputs for evidence packs in [story 2.8#L180](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L180).
- Fidelity is served indirectly, not fully realized yet. Architecture makes this crate the shared strategy boundary for backtest/live fidelity in [architecture.md#L937](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L937), but this story deliberately stops at parsing/validation/registry, not evaluation, in [story 2.8#L187](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L187).

Concrete observations:
- This story clearly advances `reproducibility` and `operator confidence`.
- It only partially advances `artifact completeness`. The crate returns serializable outputs, but it does not itself emit a persisted validation artifact or validated-spec artifact. The only concrete evidence is test serialization in [integration_test.rs#L176](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/tests/integration_test.rs#L176).
- One design choice works against confidence/completeness: `validate_spec()` can return `Ok(ValidatedSpec)` without proving the referenced cost model artifact exists if `cost_model_path` is `None`, as allowed in [validator.rs#L45](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L45) and exercised in [validator.rs#L777](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L777) and [integration_test.rs#L27](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/tests/integration_test.rs#L27).
- It fits V1 scope well. The build is intentionally narrow: four V1 indicators only, minimal dependencies, no evaluator, no CLI, no trade simulation in [registry.rs#L252](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/registry.rs#L252), [Cargo.toml](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/Cargo.toml), and [story 2.8#L204](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L204).

**2. Simplification**

Assessment: `ADEQUATE`

Specific evidence:
- The implementation is already fairly lean: one library crate, four source modules, minimal dependencies, and no Epic 3 logic in [Cargo.toml](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/Cargo.toml), [lib.rs](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/lib.rs), and [story 2.8#L187](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L187).
- The main extra flexibility is caller-supplied registry + public `register()` extensibility in [registry.rs#L57](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/registry.rs#L57) and [validator.rs#L45](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L45).
- Some metadata exists without a current consumer in this story: `IndicatorDef.name/category/description` and `Severity::Warning` in [registry.rs#L29](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/registry.rs#L29) and [validator.rs#L8](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L8).

Concrete observations:
- A simpler V1 contract would have `validate_spec()` build/use `default_registry()` internally and keep the registry closed until a real downstream story requires runtime registration. The current design is not large, but it creates one more way for consumers to diverge.
- The cost-model lookup is more indirect than necessary. The spec stores only a version in [types.rs#L177](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/types.rs#L177), while validation reconstructs `EURUSD_<version>.json` from an injected base path in [validator.rs#L563](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L563). A resolved artifact reference would be simpler and more traceable.
- Most of the crate is not over-engineered. The raw `IndicatorParams = BTreeMap<String, toml::Value>` approach in [types.rs#L54](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/types.rs#L54) is actually the simplification here: it keeps the parser contract-shaped and avoids building a premature typed evaluator IR.

**3. Forward Look**

Assessment: `CONCERN`

Specific evidence:
- The downstream contract is explicit: `ValidatedSpec` and `Vec<ValidationError>` are the machine-readable outputs for Story 2.9/evidence packs in [story 2.8#L180](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L180), and serialization/roundtrip tests exist in [integration_test.rs#L176](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/tests/integration_test.rs#L176) and [integration_test.rs#L193](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/tests/integration_test.rs#L193).
- Architecture expects this crate to become the shared foundation for backtester and live daemon in [architecture.md#L937](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L937).
- Cross-runtime parity remains explicitly unfinished in [story 2.8#L145](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L145), and the Python live suite checks existence/build/dependency facts rather than Rust-vs-Python semantic parity in [test_live_strategy_engine.py#L125](/C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_strategy/test_live_strategy_engine.py#L125).

Concrete observations:
- The output contract is good enough for the next evidence-pack story, but it is not self-contained for reproducibility. A validated spec does not identify the resolved cost-model artifact; callers must supply a base path and the crate rebuilds the filename convention internally in [validator.rs#L563](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L563).
- The story bakes in a strong V1 assumption twice: non-`EURUSD` pairs are rejected in [validator.rs#L103](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L103), and cost-model lookup always targets `EURUSD_<version>.json` in [validator.rs#L564](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L564). That is acceptable for MVP, but it means pair expansion will require contract/validator changes, not just new data.
- The parsed model is still schema-shaped rather than evaluation-shaped: comparator, exit type, sizing method, objective function are all strings, and indicator params remain raw TOML values in [types.rs#L44](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/types.rs#L44), [types.rs#L107](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/types.rs#L107), [types.rs#L140](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/types.rs#L140), [types.rs#L149](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/types.rs#L149). Epic 3 can work with this, but it will need a normalization/interpreter layer to avoid duplicated string dispatch.
- `config_hash` is still optional in [types.rs#L26](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/types.rs#L26) and only checked when present in [validator.rs#L129](/C:/Users/ROG/Projects/Forex Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L129). That keeps the story compatible with earlier workflow stages, but full traceability is still deferred.

**Overall**

`OBSERVE`

The story is directionally aligned with BMAD Backtester’s V1 goals and is a solid foundation for reproducible, reviewable strategy specifications. The main observations are that artifact completeness is only supported, not delivered, and the downstream handoff is weaker than ideal because cost-model validation is caller-dependent and cross-runtime parity evidence is still missing.
