# PIR: Story 5-2b-optimization-search-space-schema-range-proposal — Story 5.2b: Optimization Search Space Schema & Intelligent Range Proposal

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-22
**Type:** Post-Implementation Review (final alignment assessment)

---

## Codex Assessment Summary

Codex rated Objective Alignment ADEQUATE, Simplification ADEQUATE, Forward Look CONCERN, overall REVISIT. Key observations and my evaluation:

| # | Codex Observation | My Verdict | Reasoning |
|---|---|---|---|
| 1 | Reproducibility strongly served by versioned schema, typed SearchParameters, DAG validation, deterministic hashing | **AGREE** | `schema_version = Literal[2]`, `SchemaVersionError` for legacy detection, DFS cycle detection in `validate_condition_dag`, Pydantic v2 strict+extra=forbid — all directly serve PRD reproducibility goals |
| 2 | Operator confidence partially served — pipeline skill commands not integrated (AC #9) | **AGREE, but less severe** | The synthesis report shows this was blocked by file permissions, not a design gap. The underlying functions (`propose_ranges()`, `persist_proposal()`) are callable. The gap is operational convenience, not capability |
| 3 | Artifact completeness partial — `persist_proposal()` exists but not in the emitted artifact chain | **AGREE** | The function works and is tested (`test_proposal_artifact_persisted`), but no on-disk artifact accompanies v002.toml. This is correctly deferred to when the pipeline skill commands are wired up |
| 4 | Flat registry is a genuine simplification over staged groups | **AGREE** | `SearchParameter` with optional `ParameterCondition` is the minimal abstraction needed. No simpler design supports D10 mixed types + conditional chains |
| 5 | Forward Look CONCERN: parameter_space.py uses flat `list[ParameterSpec]` while contract doc defines `shared_params`/`branches` dict structure | **DISAGREE — downgrade to observation** | `parameter_space.py` already exists with working `parse_strategy_params()` and `detect_branches()` that handle schema_version=2. The contract doc is forward-looking by design. Story 5-3 will reconcile the two shapes. This is expected integration work, not a structural concern |
| 6 | Missing override tracking in saved proposal artifact fields | **AGREE, minor** | Override tracking requires the pipeline skill workflow to exist first. Cannot persist overrides before the override mechanism is wired. Correct sequencing |
| 7 | Proposals keyed by raw parameter name, V1-only naming convention assumed | **AGREE, acceptable** | Component-prefixed naming (`fast_period`, `sl_atr_multiplier`) is documented and demonstrated in v002. Post-V1 dotted paths are explicitly deferred. No action needed now |

**Codex observations I found missing:**
- `parameter_space.py` already exists with working code that consumes the new schema — Codex treated the contract doc as the only handoff, but there's also functioning bridge code
- The hash fix (#1951, version field excluded from hash computation) is important for reproducibility across version bumps
- The ATR computation is mathematically correct (TR formula, EMA(14), warmup skip) — this matters for fidelity of the L3 intelligence layer
- The synthesis review caught and fixed 6 real issues (clamping logic, condition metadata preservation, source layer attribution, field naming), demonstrating robust review coverage

## Objective Alignment
**Rating:** STRONG

This story serves the PRD's core objectives well:

**Reproducibility (strong):** The schema is now explicit, versioned, and structurally validated. `OptimizationPlan` with `Literal[2]` schema version, `SearchParameter` with typed bounds, and DFS-based DAG cycle detection ensure that any search space specification is unambiguous and deterministically validatable. Legacy v1 format triggers a clear `SchemaVersionError` with migration instructions (`loader.py:47-52`). Deterministic spec hashing (`hasher.py`) reinforces this.

**Fidelity (strong):** The range proposal engine implements five intelligence layers (L1: indicator registry, L2: timeframe scaling, L3: ATR from real Parquet data, L4: physical constraints, L5: cross-parameter relationships). ATR computation uses correct True Range formula with EMA(14) and warmup period skip (`range_proposal.py`). The synthesis review fixed source layer attribution so dimensionless multipliers are correctly attributed to L1, not L3 — preventing provenance misrepresentation.

**Operator confidence (adequate):** The schema is reviewable in TOML (`v002.toml` is clean and readable). All underlying functions are callable. The gap is AC #9's skill commands (blocked by file permissions), which means the operator must currently edit TOML directly rather than using guided commands. This is a workflow convenience gap, not a capability gap.

**Artifact completeness (adequate):** `persist_proposal()` writes JSON with all required provenance fields (timestamp, pair, timeframe, ATR stats with source tag, indicator registry hash, engine version, per-parameter source layer). The function is tested. The gap is that no on-disk artifact accompanies v002.toml yet — correctly deferred to skill command integration.

The two partial ratings (operator confidence, artifact completeness) reflect workflow integration gaps, not design or alignment problems. The structural foundation is complete and correct.

## Simplification
**Rating:** STRONG

The design is appropriately minimal:

- **Flat registry replaces staged groups:** One `dict[str, SearchParameter]` replaces the old `parameter_groups` + `group_dependencies` structure. This is a genuine simplification that still supports D10's full taxonomy (continuous, integer, categorical, conditional).
- **Right abstraction level:** `SearchParameter` captures exactly what the optimizer needs (type, bounds, step, choices, condition) without leaking optimizer internals. `ParameterCondition` is two fields (parent, value). No unnecessary layers.
- **DAG validation is O(V+E):** DFS cycle detection with three-color marking. For the expected parameter counts (<100), this is instant. No external graph library needed.
- **Minor duplication acceptable:** `OptimizationPlan.validate_condition_dag()` validates condition references; `validate_strategy_spec()` does complementary semantic checks (indicator existence, parameter name resolution). These check different things and run at different times (schema load vs semantic validation). Not redundant.
- **`persist_proposal()` built slightly ahead of need:** The function exists but has no producing command yet. This is the only piece that feels premature, but it's small (~40 lines) and tested, so the cost is negligible.

I see no simpler design that would still satisfy the requirements. The implementation is clean.

## Forward Look
**Rating:** ADEQUATE

**What works well for downstream:**
- `contracts/optimization_space.md` clearly defines the `parse_strategy_params()` contract with `ParameterSpace` containing `shared_params`, `branches`, `branch_categoricals`, and `total_dims`. Story 5-3 has a precise specification to implement against.
- `parameter_space.py` already exists with a working `parse_strategy_params()` that reads schema_version=2 and a `detect_branches()` that handles conditional parameters. Story 5-3 has functioning bridge code to extend, not build from scratch.
- The v002 reference strategy validates that the full pipeline (TOML → Pydantic → semantic validation → hash) works end-to-end.
- The `OptimizationPlan` model is the clean input interface — Story 5-3 consumes this directly.

**Shape mismatch to reconcile:** The contract doc specifies `shared_params: dict[str, SearchParameter]` with `branches: dict[tuple[str, str], dict[str, SearchParameter]]`, but the existing `parameter_space.py` uses `ParameterSpace(parameters: list[ParameterSpec])` with `detect_branches()` returning `dict[str, ParameterSpace]`. Story 5-3 will need to choose: adapt the existing code to match the contract, or evolve the contract to match the existing code. Both paths are viable. This is normal integration work, not a design flaw.

**Conditional branches untested end-to-end:** The v002 reference strategy has no conditional parameters (all 7 params are unconditional). Conditional branch decomposition is proven only via unit tests with synthetic data (`test_optimization_plan_nested_three_deep`, `test_optimization_plan_circular_dependency`). This means Story 5-3's first real conditional strategy will be the integration test. Risk is low — the validation logic is solid — but it's worth noting.

**`detect_branches()` first-branch-only limitation:** The existing code comments acknowledge "branch on the first branching categorical found (multi-level branching can be extended later)." Story 5-3 must decide if multi-level branching is needed for V1 or can remain deferred.

## Observations for Future Stories

1. **Story 5-3 shape reconciliation:** The `ParameterSpace` dataclass in `parameter_space.py` uses a flat list while the contract doc defines a dict-based decomposition. Story 5-3 should resolve this in one direction and update whichever artifact loses. Don't maintain both shapes.

2. **Pipeline skill integration (AC #9):** The three optimization commands (Propose/Review/Adjust) have content written per the synthesis report. When the file permission issue is resolved, this should be wired up. Until then, operators edit TOML directly — functional but not the intended experience.

3. **First conditional strategy will be the real integration test:** When a strategy with type-selector parameters (e.g., `exit_type` → conditional params) is created, that will exercise the DAG validation and branch decomposition in a production context. Write a more complex reference strategy at that point.

4. **Proposal artifact provenance:** The current artifact records ATR summary statistics but not dataset identity (which Parquet files, date range, bar count by session). For full reproducibility of "why were these ranges proposed?", consider adding dataset fingerprint in a future enhancement.

5. **Lesson pattern:** Story 5-2b demonstrates good separation between schema definition (this story) and schema consumption (Story 5-3), following D3's opaque optimizer boundary. Future stories should maintain this pattern — the schema owner defines the data shape contract, the consumer implements the usage policy.

## Verdict
**VERDICT: ALIGNED**

The story clearly serves system objectives. The flat parameter registry with typed `SearchParameter`, DAG-validated conditions, and five-layer intelligent range proposal is well-designed, thoroughly tested (189 passed + 5 regression tests), and structurally sound. The two deferred items (pipeline skill commands, on-disk proposal artifact) are workflow integration gaps caused by a file permission issue, not design or alignment problems.

I disagree with Codex's REVISIT recommendation. Codex weighted the pipeline skill and artifact gaps as structural alignment concerns; I assess them as operational convenience issues that do not affect the schema's correctness, the validation's completeness, or the forward contract's clarity. The core design — flat registry, condition DAG, range proposal engine, v002 reference — is aligned with PRD objectives and ready for Story 5-3 to consume.
