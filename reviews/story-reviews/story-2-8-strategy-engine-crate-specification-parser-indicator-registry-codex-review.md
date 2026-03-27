# Story 2-8-strategy-engine-crate-specification-parser-indicator-registry: Story 2.8: Strategy Engine Crate — Specification Parser & Indicator Registry — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-15
**Type:** Holistic System Alignment Review

---

## 1. System Alignment
- **Assessment:** CONCERN
- **Evidence:** D14 defines `strategy_engine` as the shared evaluator core with `evaluator.rs`, `indicators.rs`, `filters.rs`, and `exits.rs` for signal fidelity [architecture](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L937), but this story explicitly bans those modules and limits scope to parser/registry/validator [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L166). The story also adds `cost_model` as a direct dependency [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L55), while the architecture structure shows `strategy_engine` depending on `common` only [architecture](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L1660).
- **Observations:** This advances reproducibility and fidelity indirectly through constrained parsing and validation, but it barely touches operator confidence and does not materially advance artifact completeness. Supporting both TOML and JSON parsing is also broader than V1 needs; Story 2.3 already locks a contract artifact, and the system goal is one deterministic path, not format flexibility.
- **Recommendation:** Resolve the boundary first. Either make this a `strategy_spec`/runtime-model story, or keep the `strategy_engine` name and align it to D14 by establishing the shared-crate shape now. Remove unnecessary multi-format support unless Story 2.2 explicitly locked both.

## 2. PRD Challenge
- **Assessment:** CONCERN
- **Evidence:** The relevant PRD goals are FR12-FR13 and indirectly FR18-FR19 [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L472) [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L484). But FR39 and FR58-FR61 require coherent evidence packs, persisted artifacts, and deterministic traceability [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L517) [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L551).
- **Observations:** The story is over-specified on internal Rust shapes and under-specified on the operator-facing outcome. It hard-codes model details such as `IndicatorParams`, comparator enums, and file-path loading, but never defines the stable validation artifact/report that later evidence packs need. It is solving a real problem, but also some imagined ones: dual-format parsing and arbitrary file-path resolution are not operator needs.
- **Recommendation:** Reframe the story around the real PRD outcome: a deterministic, contract-aligned runtime spec plus a machine-readable validation report that downstream stages can persist and explain.

## 3. Architecture Challenge
- **Assessment:** CRITICAL
- **Evidence:** D10’s contract includes `filters[] (session, regime, day_of_week)` and `cost_model_reference` as a version of the cost model to use [architecture](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L637). Story 2.3 also says `cost_model_reference` must point to a valid version string [epics](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L684), but this story changes that to a loadable file path and direct `cost_model::load_from_file()` call [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L38) [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L160).
- **Observations:** This is the biggest system-level flaw. The story introduces contract drift, extra coupling, and I/O into a crate D14 describes as pure computation. It also uses `HashMap` for registry storage [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L90) even though the architecture explicitly warns about nondeterminism from `HashMap` iteration [architecture](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L1310).
- **Recommendation:** Keep Rust for this concern, but simplify the architecture usage: `strategy_engine` should stay pure and contract-driven, `cost_model_reference` should remain an artifact/version reference, and any artifact resolution/loading should happen outside the shared evaluator core.

## 4. Story Design
- **Assessment:** CONCERN
- **Evidence:** Several ACs are only partially testable: “matching the catalogue from Story 2.1” has no pinned local contract [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L23), “valid comparator for indicator type” has no rule table [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L107), and cost-model resolution lacks a defined lookup base. The fixture `period: -1` is also inconsistent with `u32`, so it will fail parse-time rather than semantic validation [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-8-strategy-engine-crate-specification-parser-indicator-registry.md#L117).
- **Observations:** The task list covers implementation mechanics, but it misses contract-parity tests with the Python validator from Story 2.3 and does not distinguish schema/parse failures from semantic validation failures. The dev notes are not sufficient because they themselves contradict the architecture on crate scope.
- **Recommendation:** Tighten the ACs around a single locked format, explicit semantic rules, and deterministic outputs. Add parity tests against the Story 2.3 contract and separate parse errors from collect-all validation errors.

## 5. Downstream Impact
- **Assessment:** CONCERN
- **Evidence:** Epic 2.9 expects this crate to confirm the locked specification is evaluable and linked with the cost model and dataset [epics](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L828). D14 is the foundation for backtester/live shared logic [architecture](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L937).
- **Observations:** The current type model is brittle. `IndicatorParams` as a bag of optional fields and `Condition` as `indicator + threshold + comparator` will force rewrites as soon as the pipeline needs richer constructs or even cleaner representation of MA crossover. The missing `regime` filter support is an early warning of that drift. Direct `cost_model` coupling also means `live_daemon` may inherit a dependency it does not need.
- **Recommendation:** Make the output of this story a stable, contract-aligned `ValidatedSpec` plus deterministic validation diagnostics, not a prematurely frozen internal AST. If the AST stays, it should be driven by the contract, not hand-invented here.

## Overall Verdict
VERDICT: REFINE

## Recommended Changes
1. Resolve the D14 contradiction: either rename/split this into a spec-runtime crate/story, or update the story so `strategy_engine` still matches the shared-crate boundary defined in architecture.
2. Remove direct `cost_model` loading from `strategy_engine`; keep `cost_model_reference` as a versioned artifact reference, not a file path.
3. Change parser scope from `TOML/JSON` to the single format locked by Story 2.3.
4. Replace “hand-written Rust model is the source of truth” with “Rust model must align exactly to `contracts/strategy_specification.toml`”.
5. Add cross-runtime parity tests against the Story 2.3 Python validator and sample spec.
6. Add or explicitly defer `regime` filter support; do not leave the current `session/volatility/day_of_week` mismatch.
7. Replace `HashMap` registry enumeration with deterministic ordering or require sorted output.
8. Split parse/schema failures from semantic validation failures in the ACs and tests.
9. Add a stable machine-readable validation report/output contract for Story 2.9 and later evidence packs.
10. Rework `IndicatorParams`/`Condition` so extensibility is real, not nominal.
11. Remove the claim that `strategy_engine` should depend on `cost_model` unless architecture is updated to match.
12. Add an acceptance criterion for deterministic serialized identity of `ValidatedSpec` tied to spec version and `config_hash`.
