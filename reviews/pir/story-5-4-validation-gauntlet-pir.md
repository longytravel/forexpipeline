# PIR: Story 5-4-validation-gauntlet — Story 5.4: Validation Gauntlet

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-23
**Type:** Post-Implementation Review (alignment assessment)

---

## Codex Assessment Summary

Codex rated this story `REVISIT` with `CONCERN` on Objective Alignment and Forward Look, `ADEQUATE` on Simplification. Key observations and my independent assessment:

### 1. Monte Carlo / Regime skipped in executor path (Codex: CONCERN)
**Codex says:** `ValidationExecutor` calls the gauntlet without `trade_results` or `market_data_table`, so Monte Carlo and regime analysis are effectively optional — skipped by design.

**I PARTIALLY AGREE.** The skip is real but the framing is too strong. Walk-forward evaluates candidates via the Rust dispatcher which returns summary metrics, not per-trade tables. Producing trade-level records from walk-forward OOS windows requires the backtester to return them — a cross-story concern that touches Story 3-5's trade simulation engine. The gauntlet correctly accepts `trade_results` as an optional external injection and skips gracefully with structured logging (`metrics={"skipped": True, "reason": "no_trade_results"}`). For V1's scope of "pipeline proof, not profitability gating," having Monte Carlo/regime as data-available enhancers rather than mandatory gates is defensible. However, Story 5.5 must not silently omit these from evidence packs — their absence must be visible to the operator.

### 2. StageRunner context key mismatch (Codex: CONCERN)
**Codex says:** StageRunner provides `strategy_spec_path`, `cost_model_path`, `output_directory` but executor expects in-memory `strategy_spec`, `cost_model`, `output_dir`, and `optimization_artifact_path`.

**I AGREE this is a real integration seam** but DISAGREE it's a story-level concern. The synthesis report explicitly defers this: "Executor context key alignment with StageRunner — needs coordination when Story 5.5 wires integration." The StageRunner's `_build_executor_context()` was written for the backtesting stage; extending it for VALIDATING is properly Story 5.5's responsibility. The executor correctly documents its expected context keys in the docstring.

### 3. Manifest missing dataset_hash, strategy_spec_hash, validation_config_hash (Codex: CONCERN)
**Codex says:** The spec requires these fields but the manifest omits them.

**I PARTIALLY AGREE.** The synthesis pass (Pass 2) added `config_hash` (SHA-256 of validation config), `candidate_rank`, `per_stage_metric_ids`, and `chart_data_refs`. However:
- `dataset_hash`: requires upstream provenance from the data pipeline — the gauntlet genuinely doesn't have this information. The executor could pass it from context, but StageRunner doesn't supply it yet.
- `strategy_spec_hash`: the gauntlet has the `strategy_spec` dict — computing `hashlib.sha256(json.dumps(spec, sort_keys=True))` would be trivial. This is a real gap that should have been fixed.
- `validation_config_hash`: this IS implemented as `config_hash` — Codex missed the rename.

### 4. Optimization filename convention mismatch (Codex: CONCERN)
**Codex says:** Optimization writes `promoted-candidates.arrow` and `run-manifest.json`; validation looks for `promoted_candidates.arrow` and `optimization_manifest.json`.

**I AGREE this is a real integration bug.** The `_load_optimization_output()` function in `executor.py` uses underscore-separated names while optimization's `results.py` writes hyphen-separated names. This will fail at runtime when the pipeline connects. However, since no E2E test yet exercises this path, it's a known-deferred integration concern.

### 5. WalkForwardResult lacks trade tables (Codex: CONCERN)
**Codex says:** Walk-forward produces only summary/window metrics, not trade tables, so Monte Carlo depends on external injection.

**I AGREE with the observation but DISAGREE with the severity.** This is by design for this story. The spec says Monte Carlo's input is "trade results from walk-forward OOS windows" (Task 6), but walk-forward in this story evaluates via dispatcher and receives summary metrics. The gauntlet's architecture correctly separates data acquisition from analysis — when trade-level data becomes available (from a fuller dispatcher or the Rust backtester), Monte Carlo slots in without redesign.

### 6. GauntletState dead fields, validation_summary no writer (Codex: ADEQUATE)
**Codex says:** `completed_results`, `rng_state` are unpopulated. `validation_summary` schema exists in `arrow_schemas.toml` but has no writer.

**I AGREE these are minor dead surfaces.** `completed_results` was designed for richer checkpoint resume (serializing full results) but the simpler progress-tracking approach was chosen. `rng_state` was for capturing numpy RNG state but deterministic seeding makes it unnecessary. The `validation_summary` Arrow schema without a writer is unused scaffolding — low cost, but should either be implemented or removed.

### 7. Run ID determinism insufficient (Codex: CONCERN)
**Codex says:** Run ID is `sha256(seed_base + n_candidates)[:8]` which doesn't include candidate content, data slice, or spec identity.

**I AGREE this is a gap.** Two runs with the same seed and same number of candidates but *different* candidate parameters produce the same run_id. For V1 with single-strategy sequential runs this won't collide in practice, but it violates the spirit of AC13 (deterministic results). The hash should incorporate candidate parameter hashes.

---

## Objective Alignment
**Rating:** ADEQUATE

The validation gauntlet serves the PRD's core objectives well:

**Reproducibility (FR18):** Deterministic seeding throughout — each candidate gets `seed_base + candidate_index`, each stage gets consistent RNG. Run ID is deterministic (though insufficiently scoped). Checkpointing enables resume without rerunning expensive stages. Walk-forward window generation is deterministic.

**Operator confidence:** Hard gates are strictly on validity (PBO, DSR), never on profitability (FR41 compliant). Short-circuit only on validity failures. The operator sees a clear gate pass/fail for each candidate. Suspicious performance flagging (IS-vs-OOS divergence on both Sharpe and profit factor) provides early warning without blocking.

**Artifact completeness:** Each stage produces Arrow IPC artifact + markdown summary. The gauntlet manifest links all artifacts with optimization provenance. The synthesis pass fixed the manifest to include `config_hash`, `candidate_rank`, `per_stage_metric_ids`, and `chart_data_refs`. Gap: `dataset_hash` and `strategy_spec_hash` are missing — the former needs upstream plumbing, the latter is a fixable omission.

**Fidelity:** CPCV PBO now uses proper IS-vs-OOS ranking (Bailey et al.), not simplified OOS-median fraction. DSR accounts for total optimization trials from the upstream manifest. Perturbation tests parameter sensitivity without conflating it with hard gating. Regime analysis uses volatility tercile x session cross-tabulation per the architecture's V1 scope.

**Non-profitability gating (V1 principle):** The system explicitly does not gate on Sharpe thresholds or profitability metrics. Only statistical validity (PBO indicating overfitting, DSR below threshold) triggers hard gates. This directly honors the "pipeline proof comes first" principle.

The primary alignment gap is that Monte Carlo and regime analysis are effectively optional in the integrated pipeline path. This is architecturally sound (they're data-available enhancers) but operationally means V1 evidence packs will have holes unless Story 5.5 makes their absence explicit to the operator.

---

## Simplification
**Rating:** ADEQUATE

The five-stage gauntlet *is* the story — it cannot be simpler than having the five validators the spec requires. Each validator is a focused module with a single public entry point and a result dataclass. The gauntlet orchestrator handles ordering, seeding, checkpointing, and short-circuit logic without over-abstraction.

Observations:
- **Config-driven stage ordering** is appropriate — the operator can reorder/skip stages via `base.toml` without code changes.
- **GauntletState dead fields** (`completed_results`, `rng_state`) are minor dead weight. Not harmful but should be pruned if V2 doesn't use them.
- **validation_summary** Arrow schema declared in `contracts/arrow_schemas.toml` but never written. Should be implemented (the data is available in the gauntlet results) or removed.
- **Checkpoint granularity** (per candidate-stage) is the right level — not over-engineered compared to per-iteration or per-window alternatives.

No fundamental over-engineering. The module boundaries are clean and each component is independently testable.

---

## Forward Look
**Rating:** ADEQUATE

**Downstream contract (Story 5.5):** The manifest includes most required fields. Story 5.5's evidence pack generation can consume `optimization_run_id`, `total_optimization_trials`, `candidate_rank`, `per_stage_metric_ids`, `gate_results`, `chart_data_refs`, and `config_hash` without recomputation. Remaining gaps:
- `dataset_hash`: needs upstream data pipeline provenance — Story 5.5 will need to source this from the data split manifest.
- `strategy_spec_hash`: trivially computable from the spec dict the executor already has. Should be added.
- `research_brief_versions`: not present but is a provenance field that depends on the research brief system, which is outside validation scope.

**Integration seams (known and manageable):**
1. **Filename convention mismatch** (`promoted-candidates.arrow` vs `promoted_candidates.arrow`): Will fail at runtime integration. Story 5.5 must standardize on one convention.
2. **StageRunner context key alignment**: The executor documents its expected keys; StageRunner's `_build_executor_context()` needs extension for VALIDATING. Clear boundary.
3. **Walk-forward → Monte Carlo data flow**: When trade-level data becomes available from the dispatcher, the gauntlet's architecture accepts it without redesign via the `trade_results` parameter.

**Pipeline state machine:** VALIDATING and VALIDATION_COMPLETE are correctly wired into `STAGE_ORDER` and `STAGE_GRAPH` with automatic transitions. `validation-complete` is in `gated_stages`, giving the operator a review checkpoint. Tests verify ordering and transition types.

**Arrow schemas:** All six validation schemas (`walk_forward_results`, `cpcv_results`, `perturbation_results`, `monte_carlo_results`, `regime_results`, `validation_summary`) are declared in `contracts/arrow_schemas.toml`. Five have writers; `validation_summary` does not. The schemas include the columns specified in the story spec.

---

## Observations for Future Stories

1. **Story 5.5 must handle Monte Carlo/regime absence explicitly.** When these stages are skipped (no trade data), the evidence pack should show "Not Evaluated — trade-level data not available" rather than silently omitting them. Operator confidence requires visible completeness, even when entries are "N/A."

2. **Standardize optimization-to-validation filename conventions** before Story 5.5 integration. The hyphen-vs-underscore mismatch (`promoted-candidates.arrow` vs `promoted_candidates.arrow`) is a trivial fix but will cause runtime failures if not addressed.

3. **Add `strategy_spec_hash` to the gauntlet manifest.** The spec dict is already available in the executor context — hashing it is a one-line fix. Do this in Story 5.5's integration pass.

4. **Run ID should incorporate candidate content.** Replace `sha256(seed_base + n_candidates)` with `sha256(seed_base + n_candidates + sorted_candidate_param_hashes)` to avoid collisions when the same count of different candidates is validated.

5. **The `validation_summary` Arrow schema needs a writer or should be removed.** If Story 5.5 consumes it for dashboard display, implement the writer in Story 5.5. If not needed, remove the schema declaration to avoid dead contracts.

6. **Lessons from prior PIRs apply here:** The Story 1-10 lesson about `config_hash` format consistency (`sha256:` prefix vs bare hex) should be checked. The gauntlet's `config_hash` uses bare hex — ensure consistency with other manifests.

---

## Verdict

**VERDICT: OBSERVE**

The validation gauntlet's statistical core is correctly implemented and well-tested (1333 passed, 133 skipped; 7 regression tests from synthesis). All critical and high-severity findings from both reviewers were resolved across two synthesis passes. The module serves reproducibility, operator confidence, and artifact completeness within V1's "pipeline proof" scope.

The remaining integration seams (filename conventions, context key alignment, missing hash fields, Monte Carlo/regime data flow) are real but appropriately deferred to Story 5.5 where E2E integration happens. They are documented in the synthesis report's deferred items and in this PIR's observations.

I diverge from Codex's `REVISIT` verdict because:
- The module-level implementation is sound and complete for its story scope
- The integration gaps are *between* stories, not *within* this story
- The synthesis pass fixed the critical PBO algorithm and manifest contract issues
- Monte Carlo/regime being optional is architecturally appropriate for V1 (data-available enhancers, not mandatory gates)

The story earns `OBSERVE` rather than `ALIGNED` because the run_id determinism gap, missing `strategy_spec_hash`, and `validation_summary` writer absence are real omissions that should have been caught during implementation. These are minor enough to fix during Story 5.5 integration rather than requiring a revisit of this story.
