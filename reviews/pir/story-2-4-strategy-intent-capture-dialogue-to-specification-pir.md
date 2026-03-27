# PIR: Story 2-4-strategy-intent-capture-dialogue-to-specification — Story 2.4: Strategy Intent Capture — Dialogue to Specification

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-16
**Type:** Post-Implementation Review (alignment analysis)

---

## Codex Assessment Summary

Codex rated: Objective Alignment ADEQUATE, Simplification ADEQUATE, Forward Look CONCERN, Overall OBSERVE.

### 1. Provenance is transient, not artifactized
**AGREE — but severity is lower than implied.** Codex correctly observes that `field_provenance` lives on `CaptureResult` (in-memory return value) and in structured log events, but is not persisted in the saved TOML artifact. The architecture's "saved, reviewable artifact at every stage" principle would ideally want provenance on disk. However, examining Story 2.5's actual implementation reveals that `reviewer.py` generates its summary directly from `StrategySpecification` fields loaded from disk — it does not consume `field_provenance` at all. The provenance data served its purpose during the session (logged as structured events per AC8, returned to the skill for operator confirmation). The gap is real but does not create a functional problem for the current pipeline. If future stories need cross-session provenance inspection, a sidecar file would be the right solution. **Observation, not a blocker.**

### 2. atr_period lost in stop-loss contract
**AGREE — but this is a Story 2.3 schema limitation, not a 2.4 defect.** The `defaults.toml` configures `atr_period = 14` for stop-loss, but `ExitRules.stop_loss` in `specification.py` only stores `type` and `value`. The `atr_period` assumption is consumed during spec generation but not representable in the persisted schema. This matters when the Rust strategy engine needs to know which ATR period to use — but Story 2.8's strategy engine crate will need to address indicator parameter resolution regardless. The correct fix location is the schema (Story 2.3), not the consumer (Story 2.4). **Noted for Epic 3 spec design.**

### 3. Redundant config resolution paths
**PARTIALLY AGREE.** There are multiple mechanisms for finding defaults: `_find_defaults_path()` walks CWD, `defaults_path` parameter allows injection, `config/base.toml` declares the path, and the skill hardcodes it. In practice, the injected parameter is used by all tests and the skill, while CWD walking is a development convenience fallback. This is adequate for V1's single-operator model. The synthesis report correctly deferred this as Action Item M4.

### 4. Skill boundary hardcodes paths and calls Python directly
**AGREE — appropriately documented.** The skill has `TODO(D9): migrate to REST API when orchestrator is available`. The direct Python invocation is a documented exception matching the story spec's architecture constraints. The `__main__` block was added during synthesis to make this path actually functional. **Acceptable for V1.**

### 5. Some parsed data has no durable downstream consumer
**PARTIALLY DISAGREE.** Codex flags `entry_conditions` and `raw_description` as having no consumer. `raw_description` is logged in structured events (truncated to 200 chars) — it serves as an audit trail. `entry_conditions` text descriptions are human-readable documentation of what the indicators do; the indicators themselves drive spec generation. This is a reasonable design choice, not wasted work.

## Objective Alignment
**Rating:** STRONG

This story directly advances all four system objectives:

- **Reproducibility:** Deterministic by construction. The parser consumes structured input, defaults load from TOML, the spec is hashed with lifecycle fields stripped. Test `test_deterministic_output` verifies same input + config = same `spec_hash`. No randomness, no LLM calls in Python code.

- **Operator confidence:** The clarification policy is well-implemented. Identity-defining fields (indicators, entry logic) fail-fast with clear error messages. Should-have fields (pair, timeframe) default with explicit warnings. May-default fields (position sizing, exits) apply silently with provenance tracking. The operator always knows what happened.

- **Artifact completeness:** A versioned, validated, crash-safe TOML artifact is produced at `artifacts/strategies/{slug}/v001.toml`. The spec passes Story 2.3 schema validation before persistence. The saved artifact is loadable by Story 2.5's reviewer. The one gap (provenance not persisted alongside the spec) is minor — provenance is captured in structured logs and returned to the calling skill.

- **Fidelity:** Explicit defaults with rationale in `defaults.toml`, provenance tracking distinguishing "operator" from "default", and fail-loud validation on unknown indicators/timeframes all protect against silent assumption drift. The `atr_period` gap is the one exception (see Codex observation #2).

## Simplification
**Rating:** STRONG

The four-module split (`dialogue_parser` → `defaults` → `spec_generator` → `intent_capture` orchestrator) maps directly to the pipeline's data flow. Each module has a single responsibility and a clean interface:

- `dialogue_parser.py`: Structured input → `StrategyIntent` (alias resolution, validation, normalization)
- `defaults.py`: `StrategyIntent` → `StrategyIntent` with gaps filled (immutable pattern, provenance tracking)
- `spec_generator.py`: `StrategyIntent` → `StrategySpecification` (mapping to Pydantic models)
- `intent_capture.py`: Orchestrator binding the above + hashing + storage + logging

This is not abstraction for abstraction's sake — each module is independently testable, and the separation enforces that defaults cannot be confused with parsing, nor generation with persistence. The synthesis report removed 17 hardcoded fallback values that undermined D7, leaving the code cleaner and more honest about its configuration dependencies.

No dead code, no unused abstractions, no premature extensibility. The `optimization_plan` and `cost_model_reference` fields are correctly set to `None` rather than invented placeholders.

## Forward Look
**Rating:** ADEQUATE

**What works well:**
- Draft status is explicit (`metadata.status = "draft"`), correctly deferring confirmation to Story 2.5.
- `optimization_plan = None` and `cost_model_reference = None` leave clean extension points for Stories 2.6 and 2.8.
- The output TOML artifact is the contract — Story 2.5's reviewer loads it from disk and generates a human-readable summary. Story 2.8's Rust strategy engine crate parses the same TOML format. The contract is working.
- The `__init__.py` exports are clean — downstream consumers import `capture_strategy_intent`, `CaptureResult`, and all dataclasses.

**Observations:**
- **Provenance gap:** `field_provenance` is not persisted in the TOML artifact or a sidecar file. Story 2.5's reviewer does not consume it — it works from the spec alone. If a future story needs to answer "was this field defaulted or operator-specified?" across sessions, the data isn't available from disk. Recommend adding a `_provenance.json` sidecar if this need materializes.
- **atr_period gap:** The stop-loss schema cannot represent `atr_period`, so the Rust engine will need to either (a) extend the schema, or (b) use its own configured default for ATR period. Story 2.8 already handles this by defining indicator parameters in the Rust-side registry. Not a blocker.
- **Skill invocation path:** The `python -m strategy.intent_capture` path works after synthesis fixes, but the PYTHONPATH setup in the skill is fragile. When the REST API exists (Epic 5+), this entire path gets replaced.

## Observations for Future Stories

1. **Persisted provenance pattern:** If any downstream story needs cross-session provenance (e.g., "show me what was defaulted vs. operator-specified across all my strategies"), define a sidecar artifact format rather than retrofitting provenance into the strategy specification schema.

2. **Alias-to-registry validation at test time:** The synthesis caught `keltner_channels` vs `keltner_channel` string typos. Future stories with alias/lookup tables should include a test that verifies every alias target exists in the canonical source (registry, schema enum, etc.).

3. **Formatter-aware logging tests:** The synthesis revealed that structured log fields were silently dropped because the test asserted on log message strings, not on the serialized JSON output. Future stories with AC requirements on structured logging should test the actual formatter output.

4. **`__main__` blocks for skill-invoked modules:** Any Python module invoked by a Claude Code skill via `python -m` must have a `__main__` block, and the exact invocation command from the skill should be tested during development.

5. **D7 enforcement:** `.get("key", fallback)` is a D7 violation disguised as defensive coding. Future stories should use direct `["key"]` access for config-loaded values so missing keys fail immediately.

## Verdict
VERDICT: ALIGNED

The story clearly serves all four system objectives. The implementation is deterministic, config-driven, fail-loud, and produces a valid versioned artifact that downstream stories (2.5, 2.8) successfully consume. The synthesis process caught and fixed all critical issues (hardcoded defaults, broken skill path, silent log field drops, placeholder tests). The provenance transience and atr_period gaps are real but bounded: provenance is captured in logs and in-session returns, and atr_period is a schema-level concern owned by Story 2.3. No significant alignment concerns remain.
