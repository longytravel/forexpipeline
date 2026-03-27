# PIR: Story 2-3-strategy-specification-schema-contracts — Story 2.3: Strategy Specification Schema & Contracts

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-15
**Codex PIR available:** Yes

---

## Codex Assessment Summary

Codex rated Objective Alignment as STRONG, Simplification as ADEQUATE, Forward Look as ADEQUATE, with an overall OBSERVE verdict. My evaluation of each key observation:

### 1. Reproducibility materially improved by strict contract enforcement
**AGREE.** Verified in source: all 15 Pydantic models carry `ConfigDict(strict=True, extra="forbid")` (specification.py), hashing uses canonical sorted-key JSON → SHA-256 (hasher.py:29), storage auto-increments immutable versions with crash-safe writes reusing `crash_safe_write()` from `data_pipeline/utils/safe_write.py` (storage.py:43-64). These directly serve FR12 (versioned specs), FR18/FR61 (deterministic reproducibility).

### 2. V1 scope adherence — pair constrained to EURUSD, no drift
**AGREE.** `PairType = Literal["EURUSD"]` (specification.py:22) and bounded timeframes match the PRD's "one strategy on one pair/timeframe" V1 scope. No over-reach.

### 3. Validation output is developer-shaped, not structured operator evidence
**AGREE.** Error codes were added to `contracts/error_codes.toml` (5 codes: SPEC_SCHEMA_INVALID through SPEC_VERSION_CONFLICT) but the loader's `validate_or_die_strategy()` prints free-form stderr messages (loader.py:171-179) without referencing these codes. The codes are currently dead contract surface area. This is a minor gap — Story 2.5's operator-facing lifecycle is the natural place to wire structured error reporting, but the gap should be flagged so 2.5 doesn't miss it.

### 4. Schema duplication — TOML contract vs Pydantic models are manually synchronized
**AGREE, but pragmatic for V1.** `contracts/strategy_specification.toml` declares itself the "single source of truth" but Python re-expresses the schema as Literals and field validators. Generating Pydantic models from TOML at V1 would be over-engineering — the risk is maintainability as the schema evolves. The indicator registry avoids this problem by being genuinely data-driven (Python loads `contracts/indicator_registry.toml` at runtime via `indicator_registry.py`). The strategy schema could follow the same pattern in a future iteration, but for V1 with one strategy family the manual sync is acceptable.

### 5. `group_dependencies` string DSL adds friction
**AGREE, minor.** The `"entry_timing -> exit_levels"` format is slightly awkward, but the synthesis added proper validation (specification.py:278-286) that parses the format and verifies referenced group names exist. For V1 with one optimization plan, the friction is minimal.

### 6. Optimization parameter addressing is incomplete
**AGREE.** Loader cross-validation (loader.py:116-126) collects optimizable params from entry conditions, confirmations, and trailing exit params, but excludes stop-loss value, take-profit value, and filter params. For the MA crossover reference spec this is sufficient — the optimization plan only targets `fast_period`, `slow_period`, and `atr_multiplier`, all of which are covered. But broader strategy families will need expanded addressing. This is a forward observation, not a current gap.

### 7. Schema drift risk between Python and Rust consumers
**AGREE — this is the largest forward risk.** The indicator registry is mechanically shared (both runtimes read `contracts/indicator_registry.toml`), which is correct. But the strategy specification schema is shared only by convention — no conformance test exists between the TOML contract and the Pydantic models, and Story 2.8 (Rust consumer) will need to parse the same TOML format independently. The prior PIR for Story 2-2 flagged "dual-validator conformance testing" as needed — this remains unaddressed and should be explicitly specified in Story 2.8.

### 8. Crossover semantics required special indicator workaround
**AGREE.** The synthesis correctly identified that `EntryCondition` only supports `indicator vs numeric threshold`. The fix (adding `sma_crossover` with `fast_period`/`slow_period` as a built-in composite indicator) is pragmatic and mirrors the existing `ema_crossover` pattern. But it reveals that the condition model cannot natively express cross-indicator comparison. If future strategies need arbitrary indicator-vs-indicator conditions, this will need a richer comparison model. For V1 with one strategy family, the workaround is adequate.

## Objective Alignment
**Rating:** STRONG

This story serves all four system objectives:

- **Reproducibility:** Deterministic hashing (canonical JSON → SHA-256), immutable versioning (v001 never overwritten), crash-safe persistence (NFR15), `extra="forbid"` on all models. The synthesis hardened this by fixing metadata version sync in storage (v002.toml now correctly contains `metadata.version = "v002"` instead of inheriting "v001").
- **Operator confidence:** Human-readable TOML format, fail-loud collect-all-errors validation, reference MA crossover spec as canonical example. The synthesis fixed the broken crossover semantics (two SMA conditions with threshold=0.0 → single `sma_crossover` condition), which would have undermined confidence in the reference artifact.
- **Artifact completeness:** Versioned spec files persisted to `artifacts/strategies/{name}/vNNN.toml`, error codes contract extended. Partial — validation decision not yet artifactized, but correctly deferred to Story 2.5.
- **Fidelity:** Cost model reference field (`cost_model_reference.version`) links spec to versioned cost model. Shared indicator registry ensures Python and Rust agree on indicator vocabulary. Architecture D14's cross-runtime contract is served by `contracts/indicator_registry.toml`.

The story advances FR12 (constrained, versioned specs), FR13 (optimization stages with parameter groupings), FR18/FR61 (deterministic reproducibility), and FR58 (artifact management via versioned persistence).

Nothing in this implementation works against a system objective.

## Simplification
**Rating:** ADEQUATE

The implementation is appropriately scoped for V1:

- **Justified complexity:** Versioning, hashing, crash-safe writes, and the indicator registry are all required by architecture decisions (D7, D10, NFR15). None are speculative.
- **Acceptable duplication:** The TOML contract and Pydantic models express the same schema in two places. This is a known tradeoff — the TOML contract serves as documentation and Rust reference, while the Pydantic models are the executable validator. Collapsing them would require either code generation or runtime contract parsing, both disproportionate for V1.
- **Unused contract surface:** Error codes in `error_codes.toml` exist but are not emitted by the loader. These were specified by the story's AC and are forward-compatible with Story 2.5's structured error reporting, but they are technically unused code today.
- **Could be simpler:** The `sma_crossover` workaround reveals a condition model limitation. A simpler schema might have supported `indicator_a` vs `indicator_b` comparison natively. However, adding a second comparison mode would expand the schema surface area more than adding a composite indicator type — the chosen approach is the simpler of the two options.

No significant over-engineering detected. The 53 tests across 5 files (including 14 regression tests from synthesis) are proportionate to the validation surface area.

## Forward Look
**Rating:** ADEQUATE

**What downstream stories get:**
- Story 2.4 (intent capture): A validated spec model and loader to target when converting operator intent to specification.
- Story 2.5 (operator review): Persistence primitives (`save_strategy_spec`, `load_latest_version`, `list_versions`), version immutability, and the `config_hash` slot ready for population.
- Story 2.8 (Rust consumer): `contracts/indicator_registry.toml` as a shared data source, `contracts/strategy_specification.toml` as a reference schema, and `artifacts/strategies/ma-crossover/v001.toml` as a concrete test case.
- Story 2.9 (E2E proof): Full pipeline proof (load → validate → hash → save) already demonstrated in `test_live_strategy.py`.

**Forward risks to track:**
1. **Schema drift (HIGH):** The strategy specification contract is shared by convention, not mechanism. Story 2.8 must include conformance tests between the TOML contract and both the Python Pydantic models and Rust parser. This was flagged in Story 2-2's PIR and remains unaddressed.
2. **Error code wiring (LOW):** Story 2.5 should wire error codes into validation output for operator-facing structured evidence. The codes exist but are dormant.
3. **Condition model limitation (LOW):** The `indicator vs numeric threshold` model works for V1 but will need expansion for strategy families requiring arbitrary indicator comparison. Track as a growth-phase concern.
4. **Optimization parameter completeness (LOW):** Stop-loss, take-profit, and filter params are not optimizable. Sufficient for V1 MA crossover but may need expanding for broader strategy families.

## Observations for Future Stories

1. **Story 2.5 must wire error codes:** The `[strategy]` section in `error_codes.toml` defines 5 codes that the loader never emits. When 2.5 builds operator-facing lifecycle, it should reference these codes in structured validation output — not just inherit the current free-form stderr pattern.

2. **Story 2.8 must include dual-validator conformance tests:** Python's Pydantic models and Rust's parser must be tested against the same corpus of valid/invalid specs. The test fixtures created here (5 valid/invalid TOML files) are a natural starting point. This was flagged in Story 2-2's PIR and is now actionable.

3. **The synthesis process proved its value:** 9 material issues caught post-implementation (1 critical, 4 high, 4 medium), all fixed with 14 regression tests. The broken MA crossover semantics (critical) would have propagated to downstream stories as a fundamentally invalid reference artifact. The dual-review pipeline is working as designed.

4. **Lessons learned are well-captured:** The `lessons-learned.md` entry for this story extracts 5 concrete rules from accepted findings. The most impactful: "When the AC says 'fail loud,' `strict=True` is necessary but not sufficient — `extra='forbid'` is what catches unknown fields." This rule should be referenced in any future story that creates Pydantic contract models.

5. **Data-driven registries work well:** The indicator registry pattern (load from shared TOML at runtime) is the right model for cross-runtime contracts. Consider applying the same pattern to the strategy schema itself in a growth-phase story to eliminate the manual duplication.

## Verdict

**VERDICT: OBSERVE**

Story 2.3 is clearly aligned with the system's V1 objectives. It delivers a constrained, versioned, deterministically-hashable strategy specification format that advances reproducibility, operator confidence, and artifact completeness. The synthesis process hardened it significantly — the pre-synthesis state had a critically broken reference artifact and multiple validation gaps that are now fixed with regression tests.

The observations are structural and forward-looking rather than blocking:
- Schema duplication between TOML contract and Pydantic models is pragmatic for V1 but creates drift risk for 2.8
- Error codes are defined but unused — a dormant contract that 2.5 must activate
- The condition model's indicator-vs-threshold limitation is adequate for V1's single strategy family but will need expansion

Maintaining OBSERVE (rather than upgrading to ALIGNED) because the schema drift risk flagged in Story 2-2's PIR remains structurally unaddressed — it is deferred to Story 2.8 rather than mitigated here. This is the correct boundary decision, but it means the risk accumulates silently until 2.8 explicitly picks it up. The story spec for 2.8 should reference this observation.
