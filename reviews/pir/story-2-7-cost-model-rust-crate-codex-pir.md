# Story 2-7-cost-model-rust-crate: Story 2.7: Cost Model Rust Crate — Codex PIR

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-16
**Type:** Post-Implementation Review (alignment analysis)

---

1. **OBJECTIVE ALIGNMENT**

Assessment: **ADEQUATE**

Specific evidence:
- The story materially advances **reproducibility** and **fidelity** inside the cost path. Loading is fail-loud, schema drift is rejected at both profile and top level, exact session keys are enforced, and `apply_cost()` is deterministic because it uses only mean spread + mean slippage with no randomness. [loader.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/loader.rs#L17) [types.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/types.rs#L20) [cost_engine.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/cost_engine.rs#L22) [prd.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L97) [prd.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L100)
- It supports **operator confidence** indirectly by exposing `validate` and `inspect`, including pair/version/source/calibrated_at and optional metadata. [cost_model_cli.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/bin/cost_model_cli.rs#L30) [cost_engine.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/cost_engine.rs#L40)
- It fits **V1 scope** well: EURUSD-only enforcement and hardcoded `PIP_VALUE` deliberately avoid fake multi-pair generality, and the story explicitly keeps stochastic sampling out of V1. [types.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/types.rs#L15) [loader.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/loader.rs#L33) [2-7-cost-model-rust-crate.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md#L225)

Concrete observations:
- This story is strongest on **deterministic behavior** and **explicit artifact contract enforcement**.
- It is weaker on **artifact completeness** for operator review: the CLI only prints to stdout and does not emit a saved evidence artifact or machine-readable report, so FR39/FR58 still depend on orchestration around this crate. [cost_model_cli.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/bin/cost_model_cli.rs#L33) [prd.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L517) [prd.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L551)
- One thing works slightly against strict reproducibility: the Rust toolchain is pinned to floating `stable`, not an exact compiler version. [rust-toolchain.toml](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/rust-toolchain.toml#L1)

2. **SIMPLIFICATION**

Assessment: **ADEQUATE**

Specific evidence:
- The hot-path implementation is already very small: O(1) session lookup plus one directional price adjustment. There is no extra abstraction layer in the runtime path. [cost_engine.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/cost_engine.rs#L6)
- The story intentionally avoided heavy dependencies and future-scope features such as stochastic sampling or `clap`, which is the right simplification for V1. [src/rust/crates/cost_model/Cargo.toml](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/Cargo.toml#L6) [2-7-cost-model-rust-crate.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md#L117) [2-7-cost-model-rust-crate.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md#L253)
- The clearest unnecessary moving part today is the empty `common` crate and dependency; it exists, but nothing in the crate currently uses it. The `backtester` stub is also scaffolding purely for dependency-graph validation. [src/rust/crates/cost_model/Cargo.toml](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/Cargo.toml#L10) [src/rust/crates/common/src/lib.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/common/src/lib.rs#L1) [src/rust/crates/backtester/src/lib.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/src/lib.rs#L1)

Concrete observations:
- There is **not** obvious over-engineering in the cost-model logic itself.
- The only real simplification opportunity is trimming scaffolding that exists for future workspace shape rather than current behavior.
- I would not remove the thin CLI in V1; it is small and it adds inspection value for operators, even if it is not yet a full evidence-pack mechanism.

3. **FORWARD LOOK**

Assessment: **ADEQUATE**

Specific evidence:
- The downstream code contract is mostly right: `load_from_file()`, `get_cost()`, `apply_cost()`, and accessors for pair/version/source/calibrated_at/metadata are enough for `strategy_engine` and `backtester` to consume the artifact and cross-check references. [loader.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/loader.rs#L10) [cost_engine.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/cost_engine.rs#L8) [2-7-cost-model-rust-crate.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md#L233)
- The story correctly sets up the dependency direction for Epic 3 integration. [src/rust/crates/backtester/Cargo.toml](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/backtester/Cargo.toml#L6) [architecture.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L901)
- Two important concerns are still outside this crate: manifest/hash-based provenance, and saved operator-facing evidence. The story explicitly says the crate receives a resolved file path and does not read manifests. [2-7-cost-model-rust-crate.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md#L223) [prd.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L552)

Concrete observations:
- The biggest baked-in assumption is `fill_price` semantics. The story documents that the caller must pass the pre-cost fill price and must not double-count bid/ask, but the API does not encode that constraint. That is acceptable for now, but it is a real downstream fidelity risk if later callers are inconsistent. [cost_engine.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/cost_engine.rs#L15) [2-7-cost-model-rust-crate.md](/C:/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md#L187)
- The EURUSD-only gate is the right V1 choice, but it is also the main growth assumption that will need explicit redesign for multi-pair support. [loader.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/loader.rs#L33) [types.rs](/C:/Users/ROG/Projects/Forex%20Pipeline/src/rust/crates/cost_model/src/types.rs#L15)
- If later stories need reviewable evidence packs rather than terminal output, they will need either a machine-readable CLI mode or orchestration that persists inspection results.

**OVERALL**

Assessment: **OBSERVE**

The story is system-aligned on deterministic session-aware cost application and fail-loud artifact consumption, which is exactly what V1 needs. The main observations are that reproducibility is still partially outsourced to orchestration/provenance handling, operator evidence is not yet persisted, and the floating Rust `stable` channel is weaker than the system’s reproducibility goal.
