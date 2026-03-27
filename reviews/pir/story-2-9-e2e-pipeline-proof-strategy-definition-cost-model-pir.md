# PIR: Story 2-9-e2e-pipeline-proof-strategy-definition-cost-model — Story 2.9: E2E Pipeline Proof — Strategy Definition & Cost Model

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-17
**Type:** Post-Implementation Review (final alignment decision)

---

## Codex Assessment Summary

Codex rated this story **REVISIT** with Objective Alignment: ADEQUATE, Simplification: CONCERN, Forward Look: CONCERN. Key observations and my independent evaluation:

### 1. Test-side enrichment for optimization_plan and cost_model_reference — **AGREE (mitigated)**
Codex correctly identifies that `_enrich_spec_file()` patches the saved spec with fields `spec_generator.py` doesn't produce (`optimization_plan`, `cost_model_reference`). This means the "proven contract" includes test-injected content. However, the synthesis report (M5) addressed this by adding a detailed docstring to the enrichment function explaining the gap and tracking it for Epic 3. The workaround is visible, not hidden. The alternative — extending the generator now — is out of scope for an E2E proof story. **Mitigated, not resolved.**

### 2. Operator review not persisted in proof path — **PARTIALLY AGREE**
The summary is generated via `generate_summary()` + `format_summary_text()` and verified in memory for readability, provenance tracking, and content completeness. It is not saved as a standalone artifact in the proof. Codex is right that this weakens artifact completeness for auditability. However, the proof manifest does record the confirmation timestamp and config hash, and the summary generation logic is proven to work. For a connectivity proof, in-memory verification is acceptable. **Minor gap, not blocking.**

### 3. Structured logging contract not delivered — **AGREE (correctly handled)**
The structured log test correctly attempts to extract D6 required fields (`stage`, `strategy_id`, `correlation_id`) from log records, and `xfail`s with clear documentation when they're absent. The synthesis report (H1) rewrote this test from the original substring-matching approach to proper structured field extraction. The xfail pattern is exactly right — it documents the gap without pretending it works, and will auto-promote to a real failure when production code adds `LogContext` support. **Well-handled known gap.**

### 4. Simplification: _enrich_spec_file is unnecessary abstraction — **DISAGREE**
Codex frames this as an "unnecessary abstraction." It's not — it's a necessary workaround for a production code gap. The function exists because the generator doesn't produce these fields yet. Removing the enrichment would mean the proof can't verify AC#2 (schema validation with optimization_plan) or AC#9 (cost_model_reference cross-linking). The simpler design Codex proposes (generator emits full contract natively) is correct architecturally but belongs in a production code story, not the E2E proof.

### 5. Rust proof path complexity with gap filtering — **AGREE (pragmatic)**
The Rust strategy_engine tests filter `sma_crossover` and `group_dependencies` validation errors. This is complexity driven by real upstream gaps: the Rust registry has individual indicators (`sma`, `ema`) but not Python-side composites (`sma_crossover`), and `group_dependencies` arrow notation isn't parsed. The synthesis report's rejection of Codex AC8 is well-reasoned — the core AC8 intent (parse spec, validate indicators, cross-validate cost model) IS met. The filtering is clearly documented in test comments and story dev notes.

### 6. Forward look: Rust not consuming same dialect as Python — **PARTIALLY AGREE**
Codex is right that Epic 3 will inherit a proof where Rust consumers are protected from Python-side contract details. But the gaps are specific and enumerated: composite indicator support, group_dependencies expression parsing, and cost model path format. These are tracked in the story's "Known gaps documented" section with explicit Epic 3 ownership. The forward risk is manageable because the gaps are visible, not hidden.

### 7. Contract-language mismatch (locked vs confirmed) — **DISAGREE**
The synthesis report correctly rejected this. Story 2.5 established `confirmed` as the terminal state. The AC says "locked and versioned with config hash" — the test verifies `status == "confirmed"`, `config_hash` present, `version == "v002"`. The semantic intent is fully met. Terminology alignment between story prose and implementation is a documentation concern, not a contract concern.

### 8. Dataset linkage not enforced — **DISAGREE**
Codex flagged that `has_dataset` is computed but not asserted. The test correctly treats dataset presence as best-effort because Epic 1 datasets may not exist in all environments (CI, fresh clones). The strategy-spec ↔ cost-model cross-linking (pair, version, manifest) IS verified. Dataset linkage is deferred to Epic 3 where backtesting actually consumes it. Asserting on files that might not exist would make the proof environment-dependent.

### Observations Codex missed:

- **Determinism test quality improved significantly**: After synthesis, the determinism test uses fresh isolated temp dirs for both runs, verifies enriched spec hashes (not just capture-stage), and checks cost model artifact hash. This addresses AC#12 far more thoroughly than Codex's assessment acknowledged.
- **Regression test guards**: The synthesis added 4 regression tests that guard against re-introduction of fixed issues. This is good practice not seen in earlier E2E proof stories.
- **HashMap→BTreeMap fix applied**: The cost_model crate's `sessions` field was changed from `HashMap` to `BTreeMap` during synthesis, aligning with the project convention from Story 2.8. Codex's PIR didn't note this was already fixed.

---

## Objective Alignment
**Rating:** ADEQUATE

The story serves all four system objectives, with caveats:

**Reproducibility (FR60, FR61):** Strong. Hash determinism is verified for raw spec, enriched spec, and cost model artifact across independent runs in isolated temp directories. The pipeline runs in an isolated workspace with copied config and cost artifacts. The enrichment function is deterministic (same static optimization_plan and cost_model_reference). Manifest timestamps are correctly noted as non-deterministic.

**Operator Confidence (FR11):** Adequate. The human-readable summary is generated, verified for content completeness (pair, timeframe, indicators, session, exit logic), and checked for provenance disclosure (operator vs default sources). The review is not persisted as a standalone artifact, but the confirmation with config_hash and operator_confirmation_timestamp provides the audit trail.

**Artifact Completeness:** Adequate. Strategy specs (v001 draft, v002 confirmed), cost model artifact, strategy manifest, cost model manifest, and proof manifest are all produced and verified. The proof manifest is lightweight (records `test_results: "all_passed"` rather than per-artifact hashes), which is a simplification that could be richer. Reference fixtures are saved and verified loadable with crash-safe write pattern.

**Fidelity (Cost Model):** Strong. All 5 session profiles verified with positive values. London session exact values asserted. Rust crate loads the real artifact, returns correct session-specific costs, and applies directional cost adjustment (buy price > fill > sell price). Builder API surface check confirms three input modes exist.

**What works against objectives:** The enrichment workaround means the "proven" spec is not the same contract the production generator emits. The structured logging gap means D6 observability is not yet operational. Neither is disqualifying for a connectivity proof, but both must be resolved before Epic 3 backtesting builds on this foundation.

---

## Simplification
**Rating:** ADEQUATE

The implementation is appropriately scoped for an E2E proof. 22 Python tests + 6 Rust tests covering 12 ACs is proportional. The test code is well-organized with clear AC mapping in docstrings and a module-scoped pipeline fixture that runs the flow once and shares state across tests.

**Complexity that could be simpler:**
- The enrichment function adds a layer that wouldn't exist if the generator were complete. But this is upstream debt, not this story's over-engineering.
- The Rust gap filtering (sma_crossover, group_dependencies) adds conditional logic to tests. A cleaner approach would be a dedicated test fixture that uses only simple indicators the Rust registry understands. But that would mean the proof doesn't exercise the canonical MA crossover strategy, which defeats the purpose.
- The proof manifest is both simpler than ideal (string test_results) and more complex than needed (schema_version, config_hash fields that aren't consumed by anything yet). This is minor.

**What is NOT over-engineered:**
- The conftest workspace isolation (copy config, copy cost artifacts to temp dir) is necessary for reproducibility
- The regression tests from synthesis are justified by the specific bugs they guard
- The error path tests (4 tests for invalid spec, unknown indicator, incomplete cost model, version mismatch) are minimal and directly map to ACs

---

## Forward Look
**Rating:** ADEQUATE

**What serves downstream well:**
- The TOML spec format is stable and both Python and Rust consume it successfully
- The cost model JSON artifact format is proven round-trippable (Python creates, Rust loads, Python reloads)
- The confirmation flow produces versioned, hashed artifacts with manifest tracking
- The cross-validation pattern (spec.cost_model_reference.version == cost_model.version, spec.pair == cost_model.pair) establishes the contract Epic 3 backtesting will enforce

**Known gaps with Epic 3 impact:**
1. **spec_generator.py must produce optimization_plan and cost_model_reference natively** — currently test-injected. Without this, the first real Epic 3 consumer will hit the same gap.
2. **Rust registry needs composite indicator support** (sma_crossover) — currently filtered in validation. The backtester crate will need to evaluate this indicator.
3. **Rust validator path construction** (expects `EURUSD_v001.json`, actual layout is `v001.json`) — currently worked around with manual cross-validation. Must be fixed before the backtester's validate_spec path works end-to-end.
4. **group_dependencies arrow notation** needs expression parsing in Rust — currently treated as literal string. Optimization in Epic 3 will depend on this.
5. **Structured logging (D6)** — pipeline stages must populate LogContext before operational monitoring is meaningful.

All five gaps are documented in the story's dev notes and synthesis action items. The risk is not that they're unknown — it's that they're spread across multiple tracking locations (story notes, synthesis report, test xfails, code comments). Epic 3 story specs should reference these explicitly as prerequisites.

---

## Observations for Future Stories

1. **Production code gaps surfaced by E2E proofs must have explicit tracking tickets, not just code comments.** The enrichment workaround, Rust registry gaps, and structured logging absence are documented in at least 4 different places (story dev notes, synthesis report, test docstrings, code comments) but don't have a single authoritative tracking entry. Future E2E proof stories should produce a "gap register" as a first-class output artifact.

2. **E2E proofs should exercise the exact production path, or explicitly mark where they diverge.** The `_enrich_spec_file()` workaround is well-documented after synthesis, but the original implementation had no xfail or tracking marker. Lesson from Story 1-9 (lessons-learned): "When an E2E proof works around a production code gap, mark the workaround with xfail or a tracked TODO." This story learned the lesson during synthesis but not during initial implementation.

3. **Rust integration tests that filter known failures need an expiry mechanism.** The `sma_crossover` and `group_dependencies` filters in the Rust E2E tests will silently suppress real regressions if those strings appear in unrelated error messages. Consider a `#[cfg(feature = "strict_validation")]` flag or a counter that asserts exactly N known failures, so new failures are detected.

4. **Cross-language contract testing should be a first-class story, not embedded in E2E proofs.** This proof embeds Python↔Rust contract verification (spec parsing, cost model loading) within a larger E2E test. A dedicated cross-language contract test (similar to Story 2-8's parity test intent) would be more maintainable and independently runnable.

5. **The synthesis process continues to add significant value.** The synthesis caught and fixed real issues: a tautological version-mismatch test (H2), an unused golden-file fixture (M1), incomplete determinism checks (AC12), and HashMap convention violation (M6). The dual-review + synthesis pipeline is working as intended.

---

## Verdict

**VERDICT: OBSERVE**

The story clearly serves system objectives: it proves the strategy definition → cost model pipeline end-to-end with hash determinism, operator-readable review, versioned artifacts, cross-language integration, and error path verification. The implementation is pragmatic and well-documented after synthesis.

Codex's REVISIT verdict was too aggressive. The gaps Codex identified are real but are upstream production code issues, not this story's E2E proof failures. The proof correctly exercises the pipeline as it exists today, documents where it falls short, and tracks gaps for Epic 3. The synthesis process addressed the most significant review findings (structured log test rewrite, determinism expansion, golden-file comparison, HashMap→BTreeMap fix).

The observations worth carrying forward: (1) the five documented Python↔Rust gaps must be resolved early in Epic 3 before backtesting stories build on them, and (2) the enrichment workaround in spec_generator.py is the single most important production code fix needed before the strategy pipeline can be considered truly end-to-end without test scaffolding.
