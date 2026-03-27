# PIR: Story 2-6-execution-cost-model-session-aware-artifact — Story 2.6: Execution Cost Model — Session-Aware Artifact

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-16
**Type:** Post-Implementation Review (final decision-maker)

---

## Codex Assessment Summary

Codex rated all three dimensions ADEQUATE with an overall **OBSERVE** verdict. My evaluation of each key observation:

### 1. Tick-analysis input_hash hashes path string, not dataset contents
**AGREE — confirmed in source.** `__main__.py:119` computes `input_hash = _compute_string_hash(str(Path(args.tick_data).resolve()))`. This means two different datasets at the same path produce identical `input_hash` values, undermining FR60's "input change tracking" requirement. However, severity is bounded for V1: the default EURUSD baseline (used by Story 2.9 E2E proof) hashes the actual research data dict (`json.dumps(_EURUSD_DEFAULTS, sort_keys=True)` at line 70), so the pipeline proof path has genuine provenance. The weakness only activates in tick_analysis mode, which becomes important in Epic 7. **Should be strengthened before tick_analysis is used in production.**

### 2. Session boundary authority is duplicated
**AGREE — mitigated adequately.** `_LABEL_BOUNDARIES` in `sessions.py:22` hardcodes the priority-resolved boundaries while `config/base.toml` defines the raw market-presence windows. The synthesis added `validate_config_matches_boundaries()` called at builder init, which fails fast if config diverges. This is a pragmatic V1 solution — the code is safe because the validation catches drift, even though deriving boundaries from config would be architecturally cleaner. **Acceptable for V1; recommend config-derived boundaries if session taxonomy evolves.**

### 3. `load_latest_cost_model()` still public, inviting wrong behavior
**AGREE — low severity.** `__init__.py` exports both `load_latest_cost_model` and `load_approved_cost_model`. The story spec anti-pattern #18 says downstream consumers "MUST NOT use raw latest file." The synthesis fixed all CLI code paths to use `load_approved_cost_model()`, so the internal API is correct. But keeping the raw loader in `__all__` is a pit-of-failure API design — a future consumer could import the wrong function. The naming convention (`approved` vs `latest`) is clear enough for V1's single-developer scenario. **Consider prefixing with underscore or removing from `__all__` in a future cleanup.**

### 4. CLI orchestration duplication between create-default and create
**PARTIALLY DISAGREE.** The two commands have genuinely different workflows: `create-default` uses hardcoded EURUSD defaults and auto-approves, while `create` supports multiple sources with different hash computation logic. The duplication is in the save-manifest-approve sequence, which is ~5 lines. Abstracting this would add indirection without meaningful value for V1.

### 5. Provenance split between artifact and manifest
**AGREE — acceptable tradeoff.** The JSON artifact (`v001.json`) contains only the cost model data (pair, version, source, sessions, metadata). Provenance fields (config_hash, artifact_hash, input_hash) live only in `manifest.json`. This is acceptable because `load_approved_cost_model()` always resolves through the manifest, and downstream consumers (Story 2.7 Rust crate, Story 2.9 E2E proof) are documented to use this path. If artifacts were ever shared or inspected standalone (e.g., copied to another machine), provenance would be lost. **For V1's local pipeline, this is fine. Consider embedding provenance in the artifact header for multi-environment scenarios.**

### 6. Session taxonomy is fixed (5 sessions, hardcoded)
**AGREE — by design.** The architecture explicitly defines 5 sessions with specific UTC boundaries. Adding/removing sessions is a deliberate architectural change, not a config-only operation. Hardcoding this in V1 is the right call — making session count dynamic adds complexity that no requirement justifies.

### Observation Codex missed

**7. `from_tick_data()` EURUSD fallback for non-EURUSD pairs.** The synthesis fixed this (added `_log.warning()` for non-EURUSD fallback), but the underlying design decision is worth noting: when a session has no tick data for a non-EURUSD pair, the builder silently injects EURUSD research defaults for slippage. This is documented in the story spec (slippage from research estimates until live calibration) but the EURUSD-specific values may not be appropriate for exotic pairs. V1 only targets EURUSD, so this is bounded.

## Objective Alignment
**Rating:** STRONG

This story serves all four core system objectives:

- **Artifact completeness (FR20, FR58):** The cost model is a fully persisted, versioned artifact at `artifacts/cost_models/{PAIR}/v{NNN}.json` with a manifest tracking version history, approval status, and hashes. The EURUSD baseline (`v001.json`) exists on disk with all 5 session profiles, matching D13's exact format. Schema validation runs before every save (AC5). This directly fulfills the PRD requirement that "every stage emit a persisted, reviewable artifact."

- **Fidelity (FR21):** Session-aware statistical distributions (mean + std for both spread and slippage) replace flat constants. Values vary realistically across sessions: tightest during London/NY overlap (0.6 pip spread), widest during off-hours (1.5 pip spread). The story spec's Dev Notes values are faithfully reproduced in `builder.py:_EURUSD_DEFAULTS` and the saved artifact. V1 consumers use means deterministically; std values are stored for future stochastic sampling (Story 2.7 doc).

- **Operator confidence (FR20, AC9):** The `latest_approved_version` manifest pointer ensures downstream consumers never accidentally use an unreviewed artifact. `load_approved_cost_model()` encapsulates this pattern. `approve_version()` uses `max()`-based pointer computation (Story 2.5 lesson), preventing regression if earlier versions are approved out of order.

- **Reproducibility (FR60):** All three hashes (config_hash, artifact_hash, input_hash) are populated with `sha256:` prefix (self-describing format, consistent with Story 1-10 lesson). The config_hash correctly hashes `base.toml` file contents. Research-mode input_hash correctly hashes the data dict. Tick-analysis input_hash has the path-vs-content weakness noted above, bounded to a mode not exercised in V1.

Nothing in the implementation works against an objective.

## Simplification
**Rating:** ADEQUATE

The implementation is well-scoped for V1 with minor API surface observations:

- **Module structure is clean:** 5 modules (schema, sessions, builder, storage, `__main__`) with clear separation. Schema defines contracts, sessions handles time boundaries, builder creates artifacts, storage handles persistence, CLI orchestrates. No module does more than one thing.

- **No over-engineering:** The `from_live_calibration` stub is appropriately minimal (raises `NotImplementedError` with Epic 7 message). No premature abstractions for multi-pair scenarios. The JPY pip multiplier (added during synthesis) is the only pair-specific logic, and it's justified by the tick_analysis requirement.

- **Minor API surface observation:** Both `load_latest_cost_model` and `load_approved_cost_model` are public exports. The former is an internal utility that anti-pattern #18 says consumers should avoid. This creates a minor pit-of-failure. Not worth a code change now, but downstream story specs should reference `load_approved_cost_model` explicitly.

- **Test suite is proportionate:** ~89 tests (76 unit + 13 regression) across 6 test files covering schema validation, session logic, builder modes, storage versioning, E2E flow, and live integration. No test bloat — each test maps to a specific AC or synthesis finding.

## Forward Look
**Rating:** STRONG

The output contract serves downstream stories well:

- **Story 2.7 (Cost Model Rust Crate):** The JSON artifact at `v001.json` has the exact structure D13 specifies for serde deserialization: `pair`, `version`, `source`, `calibrated_at`, `sessions` map with `SessionProfile` fields. The Rust crate needs O(1) session-to-cost lookup — the flat session map provides this directly.

- **Story 2.8 (Strategy Engine):** Strategy specs reference cost models via `cost_model_reference`. The `load_approved_cost_model()` function and `list_versions()` enable validation that a referenced version exists.

- **Story 2.9 (E2E Pipeline Proof):** The default EURUSD baseline is auto-approved (`latest_approved_version: "v001"` in manifest), with all three hashes populated. The E2E proof can load via manifest, verify artifact_hash, and confirm the Python-built artifact is loadable by Rust.

- **Epic 7 (Live Calibration):** The `from_live_calibration` interface stub and the versioned storage pattern mean live-calibrated cost models will slot into the existing version chain with no structural changes. The `source` field distinguishes calibration origin.

**One forward concern:** The tick_analysis `input_hash` path-hashing weakness (observation #1) will need to be fixed before Epic 7 introduces production tick analysis workflows. This should be called out in Epic 7 story specs as a prerequisite fix.

## Observations for Future Stories

1. **Tick-analysis input provenance (Epic 7):** When tick_analysis mode is used in production, `input_hash` must hash dataset contents (or a manifest thereof), not the directory path string. A practical approach: hash the concatenation of Parquet file hashes in the tick data directory.

2. **Consumer API guardrails (Story 2.7/2.9):** Story specs should reference `load_approved_cost_model()` by name and explicitly warn against `load_latest_cost_model()`. Consider adding a deprecation warning to `load_latest_cost_model()` when called from outside the cost_model package.

3. **Provenance embedding (Epic 3+):** If cost model artifacts are ever shared across environments or inspected standalone (e.g., by operators reviewing a strategy's cost assumptions), consider embedding `config_hash` and `input_hash` directly in the artifact JSON alongside the existing `metadata` section.

4. **Session taxonomy evolution:** If future epics need to add sessions (e.g., "sydney" for AUD pairs), the hardcoded `_LABEL_BOUNDARIES` and `REQUIRED_SESSIONS` will need to become config-derived. The existing `validate_config_matches_boundaries()` will correctly fail-fast, signaling the developer to update the code. This is adequate as a guardrail.

5. **Cross-pair slippage defaults:** The EURUSD research defaults used as fallback for non-EURUSD pairs in `from_tick_data()` should be replaced with pair-specific research values when non-EURUSD cost models are needed. Story specs for multi-pair support should require pair-specific research inputs.

## Verdict

**VERDICT: OBSERVE**

Story 2.6 clearly serves all four system objectives — artifact completeness, fidelity, operator confidence, and reproducibility. The implementation is well-structured, appropriately scoped for V1, and thoroughly tested (89 passed, 0 failures after synthesis fixes). The JSON artifact format correctly establishes the Python-to-Rust contract for Story 2.7. The manifest approval pattern correctly follows Story 2.5's `latest_confirmed_version` precedent.

The tick_analysis `input_hash` weakness is the only substantive concern, and it is bounded: V1's pipeline proof path (create-default with research data) has genuine content-based provenance. The issue affects only tick_analysis mode, which is not exercised until Epic 7. All other Codex observations are valid but appropriately scoped for V1.

**Alignment trajectory:** This is the fifth consecutive Epic 2 story (2.2 through 2.6) rated OBSERVE or better, with each story building correctly on the patterns established by prior stories (manifest pattern from 2.5, schema validation from 2.3, config-driven architecture from 2.4). The pipeline's artifact layer is maturing consistently toward the E2E proof in Story 2.9.
