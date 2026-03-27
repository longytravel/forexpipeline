# PIR: Story 3-3-pipeline-state-machine-checkpoint-infrastructure — Story 3.3: Pipeline State Machine & Checkpoint Infrastructure

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-18
**Type:** Post-Implementation Review (alignment analysis)

---

## Codex Assessment Summary

Codex rated **Objective Alignment: ADEQUATE**, **Simplification: ADEQUATE**, **Forward Look: CONCERN**, overall **OBSERVE**.

| # | Codex Observation | My Assessment |
|---|---|---|
| 1 | Artifact completeness not enforced — `NoOpExecutor` and missing-executor-skip could mask incomplete pipelines | **AGREE with nuance.** Both escape hatches serve legitimate testing needs, and production usage will register real executors. However, Codex is right that there is no runtime guard distinguishing "test mode" from "production mode." Downstream stories (3-4 through 3-7) will wire real executors, making this a transient concern. The risk is low but worth noting. |
| 2 | Within-stage resume not wired through to executor — `execute()` receives only `artifacts_dir`, not checkpoint data | **AGREE.** This is explicitly deferred per story spec Dev Notes: "Recovery logic in this story is limited to reading and validating existing checkpoints." Story 3-4 will need to extend the `StageExecutor.execute()` signature or have executors load checkpoints themselves. The infrastructure (checkpoint reading, recovery module) is in place; the handoff protocol is the gap. |
| 3 | Unused config surface — `checkpoint_enabled`, `gated_stages`, `checkpoint_granularity` loaded but not consumed | **AGREE.** `PipelineConfig` extracts these from TOML and stores them, but the orchestrator never branches on `checkpoint_enabled` (checkpoints are always active), ignores `gated_stages` (using `STAGE_GRAPH` as SSOT), and doesn't pass `checkpoint_granularity` to executors. This is premature configuration — not harmful, but adds surface that could mislead operators. |
| 4 | Checkpoint contract is stronger than reader — TOML defines `min`/`max`/`allowed` but Python recovery does not validate bounds | **AGREE.** `recover_from_checkpoint()` deserializes JSON into `WithinStageCheckpoint` without checking `progress_pct` bounds (0–100), `total_batches >= 1`, or `stage` against allowed values. If Rust writes a malformed checkpoint, the Python side will silently accept it. This is a minor gap given Rust is the only writer, but it means the contract is aspirational rather than enforced. |
| 5 | `refine` hard-coded to re-enter at `backtest-running` | **AGREE but acceptable.** For V1's linear pipeline this is the only sensible re-entry point. When Epic 5 adds optimization loops, the refine target will need parameterization. The current implementation is correct for scope. |
| 6 | Evidence-pack assembly is placeholder only | **AGREE.** `GateDecision.evidence_pack_ref` is nullable and never populated. This is by design — Story 3-7 owns evidence packs. The slot exists; the content doesn't yet. Correctly scoped. |
| 7 | Two testing escape hatches (`NoOpExecutor` + missing-executor-skip) overlap | **PARTIALLY DISAGREE.** These serve different purposes: `NoOpExecutor` is an explicit test double with a real `StageResult`; missing-executor-skip allows the orchestrator to run partial pipelines (e.g., only some stages have executors). The skip behavior logs clearly. The concern about "pipeline appearing healthy without evidence" is valid for production but acceptable for infrastructure-stage testing. |

## Objective Alignment

**Rating:** STRONG

This story directly serves the four core system objectives:

1. **Reproducibility:** `config_hash` is computed from the full config dict and persisted in state (FR59). Every `run()` and `resume()` generates a unique `run_id` (FR60). Config hash mismatch on resume triggers a logged warning. State file is the single source of truth for pipeline progression.

2. **Operator Confidence:** `PipelineStatus` exposes stage, progress (with within-stage interpolation from checkpoints), gate status, decision required, blocking reason, error, `run_id`, and `config_hash` — a comprehensive "where am I / why am I blocked" view (FR40). Gate decisions support `accept`/`reject`/`refine` with recorded reasons (FR39). No profitability gate (FR41).

3. **Crash Safety / Fidelity:** All state mutations use `crash_safe_write` (write → flush → fsync → atomic rename). Startup cleanup correctly orders: read checkpoints first, exclude referenced partials, then clean (NFR15). Resume verifies last artifact via executor delegation (NFR11). Recovery module is correctly separated from state management.

4. **Artifact Integrity:** Precondition checks validate artifact existence and manifest hash via executor (AC #2, fixed during synthesis). Resume validates the last completed stage's artifact using the correct executor (fixed during synthesis — was incorrectly using current-stage executor).

The story does NOT work against any objective. The "artifact completeness not enforced" concern is a testing escape hatch, not an architectural flaw — production executors will be registered by downstream stories.

## Simplification

**Rating:** ADEQUATE

The module decomposition is clean and maps to architecture responsibilities:
- `pipeline_state.py`: data model + persistence
- `stage_runner.py`: orchestration + retry
- `gate_manager.py`: gating + status
- `recovery.py`: crash recovery
- `errors.py`: D8 error classification

**Minor concerns:**

1. **Config fields that nothing reads.** `checkpoint_enabled`, `gated_stages`, and `checkpoint_granularity` are loaded, schema-validated, and stored but never consumed. This is ~15 lines of config surface that could mislead. Not harmful now, but downstream stories should either consume them or remove them.

2. **Two-checkpoint model is justified.** `pipeline-state.json` (cross-stage, Python-owned) and `checkpoint-{stage}.json` (within-stage, Rust-written/Python-read) serve clearly different recovery layers. This matches the architecture's D3 separation. Not over-engineering.

3. **`_classify_exception` heuristics are reasonable.** Mapping `OSError`/`ConnectionError`/`TimeoutError` to `external_failure`, `MemoryError` to `resource_pressure`, and everything else to `data_logic` is a pragmatic default. Executors can override via `pipeline_error` attribute on exceptions. No simplification needed.

4. **The `save_fn` lambda pattern** in `_execute_stage` (passing `lambda: state.save(self._state_path)` to `handle_error`) avoids circular imports between `errors.py` and `pipeline_state.py`. Pragmatic, if slightly unusual.

## Forward Look

**Rating:** ADEQUATE

**What's well-positioned for downstream:**

- **Story 3-4 (IPC Binary):** `StageExecutor` protocol is ready. `WithinStageCheckpoint` dataclass and `contracts/pipeline_checkpoint.toml` define the cross-runtime contract. Story 3-4 needs to: (a) implement `execute()` and `validate_artifact()` for the Rust batch stage, and (b) either extend `execute()` to accept checkpoint data or have the executor load checkpoints from disk itself. The infrastructure is in place; only the handoff convention needs agreement.

- **Story 3-5 (Rust Backtester):** Checkpoint writing is consumer-side ready. The Rust binary writes `checkpoint-{stage}.json` per the TOML contract; Python reads on resume.

- **Story 3-6 (Results Storage):** `CompletedStage.artifact_path` and `manifest_ref` provide lineage hooks. SQLite ingest can use these references.

- **Story 3-7 (Evidence Packs):** `GateDecision.evidence_pack_ref` is the integration slot. `gate_decisions` history provides full audit trail.

- **Story 3-8 (Operator Skills):** `PipelineStatus` is the query contract for `/pipeline-status`. All required fields are present.

- **Epic 5 (Optimization):** `PipelineStage` enum and `STAGE_GRAPH` dict are designed for extension — add an `OPTIMIZING` state and one graph entry. The refine re-entry target will need parameterization.

**Gaps to watch:**

1. **Checkpoint handoff protocol** (Codex's biggest concern): `execute()` only receives `strategy_id` and `context: dict`. Story 3-4 will need to pass checkpoint state somehow. Options: (a) add `checkpoint` to context dict, (b) extend protocol signature, (c) have executor read checkpoint from disk. Option (c) is simplest and avoids protocol changes — the executor knows its own `artifacts_dir` and can call `recover_from_checkpoint()`.

2. **Checkpoint validation gap:** Python-side recovery trusts checkpoint JSON without validating against the TOML contract bounds. If a downstream Rust story assumes Python enforces those bounds, there's a silent contract violation. Low risk (Rust is the only writer), but a validation function matching the TOML spec would close it.

3. **Unused config could drift.** If `gated_stages` in config diverges from `STAGE_GRAPH` (the actual SSOT), an operator might be confused by the mismatch. Downstream should either wire config into the graph or remove it.

## Observations for Future Stories

1. **Story 3-4 should document which checkpoint handoff approach it uses** (context dict, protocol extension, or executor-side loading). The PIR for 3-4 should verify this choice is clean and doesn't create a second checkpoint-reading path.

2. **Consider adding checkpoint validation to recovery.** A `validate_checkpoint(data, contract)` function that checks TOML-defined bounds would close the contract-enforcement gap Codex identified. This could live in `recovery.py` or a shared `contracts/` module.

3. **Unused config fields** (`checkpoint_enabled`, `gated_stages`, `checkpoint_granularity`) should be consumed or removed by the story that would naturally own them. `checkpoint_granularity` → 3-4 (batch size config for Rust binary). `gated_stages` → either wire into `STAGE_GRAPH` construction or remove as redundant. `checkpoint_enabled` → either branch on it or remove.

4. **The synthesis process was effective.** 6 of 7 findings were accepted and fixed with regression tests. The 3 rejected findings had sound reasoning (deferred scope, prior fixes, design choice). This validates the dual-review pipeline's ability to catch real issues.

5. **Test coverage is comprehensive.** 92 orchestrator tests including 14 regression tests from synthesis, plus 867 full-suite pass with 0 regressions. The test structure (unit per module + e2e + live + regression) is a good pattern for future stories.

## Verdict

**VERDICT: ALIGNED**

Story 3.3 delivers the core pipeline orchestration infrastructure that directly serves reproducibility (config hash, run ID, deterministic state), operator confidence (comprehensive status, gated decisions, no profitability blocking), crash safety (crash-safe writes, ordered cleanup, artifact verification), and artifact integrity (manifest validation, single verification path). The module decomposition is clean and maps to architecture decisions D3/D6/D7/D8. The synthesis process caught and fixed 6 real issues. Downstream stories have clear integration points (executor protocol, checkpoint contract, gate decision slots, status query contract).

The minor observations — unused config surface, checkpoint validation gap, and resume handoff protocol — are all within the expected scope of an infrastructure story that intentionally defers execution to downstream stories. None of them represent alignment concerns; they are integration details for 3-4 through 3-7 to close.
