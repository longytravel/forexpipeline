# Story 2-9-e2e-pipeline-proof-strategy-definition-cost-model: Story 2.9: E2E Pipeline Proof — Strategy Definition & Cost Model — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-17
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

**HIGH findings**
- AC8 is not actually satisfied. The Rust E2E test explicitly accepts validation failures for `sma_crossover` and `group_dependencies` instead of requiring a clean `ValidatedSpec`, and it loads a static `v001` spec rather than the pipeline-produced locked artifact. The underlying implementation still has the same gaps: the default registry does not register crossover indicators, and cost-model cross-validation builds the wrong filename. Refs: [`e2e_integration.rs#L86`](/c/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/strategy_engine/tests/e2e_integration.rs#L86), [`e2e_integration.rs#L136`](/c/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/strategy_engine/tests/e2e_integration.rs#L136), [`registry.rs#L252`](/c/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/strategy_engine/src/registry.rs#L252), [`validator.rs#L524`](/c/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/strategy_engine/src/validator.rs#L524), [`v001.toml#L5`](/c/Users/ROG/Projects/Forex%20Pipeline/artifacts/strategies/ma-crossover/v001.toml#L5)
- AC2 is only met by test-side mutation, not by generation. The E2E harness writes `optimization_plan` and `cost_model_reference` into the saved TOML before validation, while the real generator emits both as `None`. That means the generated spec itself does not satisfy the story contract. Refs: [`test_epic2_pipeline_proof.py#L93`](/c/Users/ROG/Projects/Forex%20Pipeline/tests/e2e/test_epic2_pipeline_proof.py#L93), [`test_epic2_pipeline_proof.py#L120`](/c/Users/ROG/Projects/Forex%20Pipeline/tests/e2e/test_epic2_pipeline_proof.py#L120), [`spec_generator.py#L195`](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/spec_generator.py#L195)
- AC10 is not implemented as specified. The structured logger emits `ts`/`msg`, not `timestamp`, has no `correlation_id` field anywhere, and only populates `stage`/`strategy_id` if callers use `LogContext` or pass those extras, which these pipeline paths do not. The E2E test then checks only message substrings from raw `LogRecord`s, so schema violations would still pass. Refs: [`setup.py#L17`](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/logging_setup/setup.py#L17), [`intent_capture.py#L57`](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/intent_capture.py#L57), [`conftest.py#L30`](/c/Users/ROG/Projects/Forex%20Pipeline/tests/e2e/conftest.py#L30), [`test_epic2_pipeline_proof.py#L602`](/c/Users/ROG/Projects/Forex%20Pipeline/tests/e2e/test_epic2_pipeline_proof.py#L602)
- AC9 is not proven and is currently broken in practice. The test treats the Epic 1 dataset as optional, computes `has_dataset`, and never asserts it; this workspace also has no `artifacts/raw` dataset directory. On top of that, the Python pipeline uses a temp-workspace slug from capture, while the Rust test uses a separate static artifact path, so the “linked trio” is not a single consistent input set. Refs: [`test_epic2_pipeline_proof.py#L552`](/c/Users/ROG/Projects/Forex%20Pipeline/tests/e2e/test_epic2_pipeline_proof.py#L552), [`test_epic2_pipeline_proof.py#L568`](/c/Users/ROG/Projects/Forex%20Pipeline/tests/e2e/test_epic2_pipeline_proof.py#L568), [`test_epic2_pipeline_proof.py#L117`](/c/Users/ROG/Projects/Forex%20Pipeline/tests/e2e/test_epic2_pipeline_proof.py#L117), [`e2e_integration.rs#L30`](/c/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/strategy_engine/tests/e2e_integration.rs#L30)
- AC12 is not met. The determinism test reruns only `capture_strategy_intent` and compares one `spec_hash`; it never reruns modification, confirmation, manifest generation, or fixture persistence, and it never computes or compares manifest/fixture hashes. Refs: [`test_epic2_pipeline_proof.py#L641`](/c/Users/ROG/Projects/Forex%20Pipeline/tests/e2e/test_epic2_pipeline_proof.py#L641), [`test_epic2_pipeline_proof.py#L662`](/c/Users/ROG/Projects/Forex%20Pipeline/tests/e2e/test_epic2_pipeline_proof.py#L662), [`test_epic2_pipeline_proof.py#L700`](/c/Users/ROG/Projects/Forex%20Pipeline/tests/e2e/test_epic2_pipeline_proof.py#L700)
- AC5 is only partially implemented. `confirm_specification()` sets `status = "confirmed"` and rewrites the same file, but there is no locked state or lock enforcement anywhere, despite the schema explicitly distinguishing `confirmed` and `locked`. The test also accepts “confirmed” as sufficient. Refs: [`confirmer.py#L166`](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/confirmer.py#L166), [`test_epic2_pipeline_proof.py#L389`](/c/Users/ROG/Projects/Forex%20Pipeline/tests/e2e/test_epic2_pipeline_proof.py#L389)

**MEDIUM findings**
- AC3 is only partially met. The summary is readable, but the review output has no place to disclose which defaults were applied; the test checks provenance out-of-band instead of requiring the rendered summary to say it. Refs: [`reviewer.py#L86`](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/reviewer.py#L86), [`reviewer.py#L252`](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/reviewer.py#L252), [`test_epic2_pipeline_proof.py#L309`](/c/Users/ROG/Projects/Forex%20Pipeline/tests/e2e/test_epic2_pipeline_proof.py#L309)
- AC11 fixture integrity is sloppy. The test writes the confirmed `v002` spec into `reference_ma_crossover_v001.toml`, so the filename and embedded version disagree. That is an avoidable source of downstream confusion. Refs: [`test_epic2_pipeline_proof.py#L685`](/c/Users/ROG/Projects/Forex%20Pipeline/tests/e2e/test_epic2_pipeline_proof.py#L685), [`reference_ma_crossover_v001.toml#L1`](/c/Users/ROG/Projects/Forex%20Pipeline/tests/e2e/fixtures/reference_ma_crossover_v001.toml#L1)
- AC7’s Rust `apply_cost` E2E coverage is weak. It only checks directionality and a broad `< 10 pips` bound, so a regression that drops either spread or slippage could still pass. Refs: [`e2e_integration.rs#L106`](/c/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/tests/e2e_integration.rs#L106)

**Acceptance Criteria Scorecard**

| AC | Status | Notes |
|---|---|---|
| 1 | Fully Met | Fixture-driven capture produces the intended EURUSD/H1/London/chandelier strategy. |
| 2 | Partially Met | Required fields are injected after generation, not produced by the generator itself. |
| 3 | Partially Met | Readable summary exists, but default disclosure is missing from the rendered review. |
| 4 | Fully Met | Deterministic `3.0 -> 4.0` modification and diff flow are covered. |
| 5 | Partially Met | Versioning and config hash exist, but lock semantics are absent. |
| 6 | Fully Met | EURUSD cost model loads with all 5 required sessions. |
| 7 | Fully Met | Rust crate loads the artifact and exposes working `get_cost`/`apply_cost` APIs. |
| 8 | Not Met | Rust strategy engine cannot validate the reference spec cleanly; tests whitelist failures. |
| 9 | Not Met | Dataset presence and full artifact linkage/hash matching are not enforced. |
| 10 | Not Met | Required structured-log fields/schema are missing and unverified. |
| 11 | Partially Met | Reference fixtures are saved, but the strategy fixture versioning is inconsistent. |
| 12 | Not Met | Only capture-stage spec hash is checked on rerun. |

**Test Coverage Gaps**
- `tests/e2e/fixtures/expected_ma_crossover_spec.toml` is never used, so there is no canonical fixture-vs-generated-spec regression check.
- There is no happy-path Rust E2E proving the actual pipeline-produced locked spec validates to `ValidatedSpec`.
- The error-path checks for unknown indicator, incomplete cost model, and cost-model version mismatch are mostly Python substitutes; they do not exercise the Rust crates the story calls out.
- Determinism coverage never measures manifest hash or saved fixture hashes.
- Artifact linkage coverage does not require an Epic 1 dataset to exist, nor does it verify schema-version/hash alignment across all three artifacts.

Summary: 4 of 12 criteria are fully met, 4 are partially met, and 4 are not met. Findings: 6 HIGH, 3 MEDIUM.
