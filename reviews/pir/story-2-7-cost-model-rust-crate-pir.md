# PIR: Story 2-7-cost-model-rust-crate — Story 2.7: Cost Model Rust Crate

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-16
**Codex Assessment Available:** Yes

---

## Codex Assessment Summary

Codex rated all three dimensions ADEQUATE with an overall OBSERVE verdict. Key observations:

### 1. CLI outputs to stdout only — no saved evidence artifact (FR39/FR58)
**AGREE — acceptable boundary.** Codex correctly notes the CLI prints to stdout and does not emit a persisted evidence pack. However, this is explicitly by design: the story spec defines the CLI as a "validation and inspection" tool (AC6), not an evidence generator. FR39/FR58 evidence packs are the orchestration layer's responsibility — the crate is a library consumed in-process, and the CLI is a lightweight operator convenience. The crate provides all the accessors (`pair()`, `version()`, `source()`, `calibrated_at()`, `metadata()`, `sessions()`) that an orchestrator needs to build evidence. **No action needed for this story.**

### 2. Floating `stable` Rust toolchain weakens reproducibility
**DISAGREE — non-concern for V1.** The `rust-toolchain.toml` pins `channel = "stable"`, not an exact compiler version like `1.77.0`. Codex flags this as weaker than the system's reproducibility goal. However, Rust's stability guarantee means `stable` produces identical runtime behavior across versions — IEEE 754 arithmetic doesn't change between compiler releases. The concern would matter for binary-level reproducibility (same compiled bytes), which is a CI/deployment concern outside this story's scope. The cost model's reproducibility guarantee is at the *semantic* level: same artifact + same inputs = same output, which is fully met by the deterministic `apply_cost()` implementation. **Low priority — pin exact version when CI is set up in Epic 3.**

### 3. Empty `common` crate and `backtester` stub are scaffolding
**AGREE — justified.** These exist solely to validate the D13 dependency graph (AC7: `backtester → cost_model`). They cost nothing (empty libs) and verify a real architectural constraint. The `backtester` stub even re-exports `cost_model` to prove the dependency compiles. This is the right amount of scaffolding.

### 4. `fill_price` semantics not encoded in the API
**AGREE — acceptable for V1.** The caller must pass a pre-cost fill price and not double-count bid/ask spread. This is documented in the story spec's Dev Notes but not enforced by the type system. For V1 with a single caller (the backtester in Epic 3), documentation is sufficient. If multiple callers emerge, a newtype wrapper (e.g., `PreCostFillPrice(f64)`) could make the contract explicit. **Monitor in Epic 3.**

### 5. EURUSD-only gate is the main growth assumption
**AGREE — by design.** V1 hardcodes `PIP_VALUE = 0.0001` and rejects non-EURUSD pairs with a descriptive error explaining the pip value limitation. The TODO comment marks this for Epic 3 generalization. This is the right V1 choice per the PRD's "build only what's genuinely needed" principle.

## Objective Alignment
**Rating:** STRONG

This story serves all four core system objectives effectively:

- **Reproducibility (FR59, FR61):** `apply_cost()` is fully deterministic — it uses only `mean_spread_pips` and `mean_slippage_pips`, with no randomness or external state. The same artifact and inputs always produce the same output. `deny_unknown_fields` on both `CostProfile` and `CostModelArtifact` (post-synthesis fix) prevents silent schema drift between Python builder and Rust consumer.

- **Fidelity (FR21):** Session-aware cost application with 5 distinct profiles replaces flat spread assumptions from the baseline. Directional adjustment (buys pay more, sells receive less) correctly models real execution. The V1 deterministic approach is the right choice — stochastic sampling would introduce noise that makes backtest-to-live comparison harder, which directly undermines the core promise.

- **Operator confidence (FR39, FR20):** The CLI provides immediate artifact validation and inspection with formatted output showing all session profiles and metadata. `validate` exits with code 1 on failure (fail-loud). `inspect` displays pair, version, source, calibrated_at, metadata, and all session cost parameters in a formatted table. Post-synthesis fix added the `metadata()` accessor and CLI metadata display, completing AC6.

- **Artifact completeness (FR58):** The crate validates the D13 JSON artifact format exhaustively: pair (EURUSD-only), version (exactly `v\d{3}`), source (valid components), calibrated_at (ISO 8601), sessions (exactly 5 expected keys), all numeric fields (non-negative, finite). Any deviation fails loudly with a descriptive error. The artifact contract between Python builder (Story 2.6) and Rust consumer (this story) is enforced at both boundaries.

## Simplification
**Rating:** STRONG

The implementation is minimal and focused:

- **Dependencies:** Only `serde`, `serde_json`, `thiserror` (plus `tempfile` for dev). No `clap`, `tokio`, `arrow`, `chrono`, or other heavy crates.
- **Hot path:** O(1) HashMap lookup + one addition + one multiplication. No allocations, no branching beyond the buy/sell match.
- **CLI:** Uses `std::env::args()` directly — ~80 lines total, no framework.
- **Validation:** Comprehensive but proportionate — each check is a simple predicate with a descriptive error message.
- **Code volume:** ~140 lines of library code (types + loader + engine + error), ~80 lines of CLI, ~350 lines of tests. The ratio is healthy.

The only arguable excess is the `common` crate dependency in `cost_model/Cargo.toml`, which exists for workspace topology but contributes nothing to this story. This is cosmetic — it compiles to nothing.

## Forward Look
**Rating:** STRONG

The output contract serves downstream stories well:

- **Story 2.8 (strategy_engine):** The public API (`load_from_file()`, `get_cost()`, `pair()`, `version()`, `source()`, `calibrated_at()`, `metadata()`) provides everything the strategy engine needs for cross-validation of `cost_model_reference`. The crate is a library dependency — no IPC boundary.

- **Story 2.9 (E2E pipeline proof):** The crate can load the default EURUSD artifact created by Story 2.6. The `validate` CLI command provides a standalone verification step for the E2E proof.

- **Epic 3 (backtester integration):** `apply_cost(fill_price, session, direction)` is the exact interface the per-trade hot path needs. O(1) lookup meets the performance requirement. The `Direction` enum and deterministic semantics are stable.

- **Dependency graph:** `backtester → cost_model` is verified by AC7 and the integration tests. The workspace is correctly structured for future crate additions.

The fill_price semantics documentation is clear and sufficient for V1's single-caller scenario. The EURUSD-only gate has a clean upgrade path (parameterize pip_value by pair).

## Observations for Future Stories

1. **Pin Rust toolchain version when CI is established.** Change `channel = "stable"` to `channel = "1.XX.Y"` in `rust-toolchain.toml` during Epic 3 setup. This is low priority but aligns with the system's reproducibility posture.

2. **Evidence pack generation belongs in orchestration, not library crates.** The CLI's stdout output is appropriate for this crate's scope. When Story 2.9 or Epic 3 needs persisted evidence, the orchestrator should call the library API and format/save the results. Don't bloat library crates with I/O concerns.

3. **The `common` crate needs purpose.** It's currently empty. If shared types or utilities emerge across `cost_model`, `strategy_engine`, and `backtester`, they should land here. If nothing materializes by Epic 3, consider removing the dependency.

4. **Synthesis process worked well for this story.** The 4 findings (deny_unknown_fields on artifact, version validation strictness, session mapping test, metadata accessor) were all legitimate and caught real gaps. The post-fix test count (19 unit + 4 integration) is comprehensive. This validates the dual-reviewer synthesis model.

## Verdict

**VERDICT: ALIGNED**

Story 2.7 is one of the cleanest implementations in the pipeline. It delivers exactly what the architecture requires: a minimal, deterministic, fail-loud Rust library crate that loads session-aware cost model artifacts and applies costs in the per-trade hot path. The synthesis process caught and fixed the 4 real issues. The API contract is stable and sufficient for all downstream consumers (Stories 2.8, 2.9, Epic 3). No significant concerns about alignment with system objectives.
