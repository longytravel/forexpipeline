# PIR: Story 5-3-python-optimization-orchestrator — Story 5.3: Python Optimization Orchestrator

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-22
**Type:** Post-Implementation Review (final alignment assessment)

---

## Codex Assessment Summary

Codex rated **CONCERN** on Objective Alignment, **ADEQUATE** on Simplification, and **CONCERN** on Forward Look, with an overall verdict of **REVISIT**. Key observations and my assessment:

| # | Codex Observation | My Verdict | Rationale |
|---|---|---|---|
| 1 | Artifact production is strong (results, promoted candidates, manifest) | **AGREE** | Arrow IPC results, promoted-candidates artifact, and run manifest all use crash-safe writes. Directly serves PRD artifact completeness (FR25). |
| 2 | Optimizer opaque to pipeline state per D3 | **AGREE** | Pipeline state has only OPTIMIZING + OPTIMIZATION_COMPLETE. Internal complexity (portfolio, branches, checkpoints) managed privately. Correct D3 integration. |
| 3 | Reproducibility only partial — resumed runs don't restore optimizer internals (CMA-ES covariance, DE population) | **PARTIALLY AGREE** | Real gap: checkpoint saves metadata (generation, evaluated_count, best_candidates, best_score, config_hash, pending buffers) but not CMA-ES covariance matrix or DE population vectors. However, Codex overstates the severity. The PRD's reproducibility objective is *backtest-to-live fidelity* — not bit-identical optimizer trajectory after crash resume. Fresh runs are fully seeded and deterministic. Resume provides generation-level safety with documented trajectory divergence. Synthesis explicitly defers full state serialization as HIGH action item. |
| 4 | OPTIMIZATION_COMPLETE not gated, contradicting D3 | **AGREE** | D3 explicitly states `→ OPTIMIZING → OPTIMIZATION_COMPLETE (gated) →` and the story spec's own traceability notes confirm this. If STAGE_GRAPH has this as AUTOMATIC and base.toml `gated_stages` omits it, the operator cannot review optimization results before validation begins. This is a real gap, though fixable by adding `"optimization-complete"` to `gated_stages` in config — no code change required. |
| 5 | Manifest validation overstated — executor only checks existence + row count | **AGREE** | This is a recurring pattern (lessons learned from Stories 1-9, 3-3). GateManager has `validate_artifact` wiring, but depth of validation remains shallow. For optimization specifically, verifying the Arrow file exists and has rows is a reasonable V1 check — the real provenance chain comes from the run manifest. |
| 6 | No optimization evidence-pack hook comparable to backtest | **AGREE** | True, but evidence packs are Story 5.5's responsibility (D11 analysis layer). Not a gap in this story — correct scope separation. |
| 7 | Over-built for V1: CMA-ES + DE + Sobol + UCB1 is heavy machinery | **DISAGREE** | The portfolio approach was a deliberate architectural decision from Phase 0 optimization research (documented in project memory). The story spec (AC1, AC6, AC7, AC10) explicitly requires this. The architecture (D10, FR24) mandates mixed-parameter optimization with conditional branching. This is a *spec-level* complexity choice, not implementation over-engineering. The implementation faithfully follows the spec. |
| 8 | Stage result doesn't explicitly return promoted-candidates path | **PARTIALLY AGREE** | OptimizationResult dataclass does have `promoted_candidates_path` field, and the orchestrator populates it. But if the executor's `run()` stage result to the pipeline only surfaces `all_candidates_path` and `manifest_path`, downstream must infer the promoted path by convention. This is consistent with how other pipeline artifacts work (naming convention), but could be more explicit. |
| 9 | Manifest only records master_seed, not per-instance seeds (AC13 gap) | **AGREE** | AC13 explicitly requires "RNG seeds per instance." Per-instance seeds are deterministically derivable from `master_seed + instance_index`, so reproducibility is not lost — but the manifest should record them explicitly for provenance transparency. Minor fix. |
| 10 | Config hash propagation fragile — multiple computation paths | **PARTIALLY AGREE** | Synthesis fix added config hash validation on checkpoint resume, which addresses the worst case (resume with changed config). The StageRunner→Executor path may compute independently, but both use the same config file, so divergence is unlikely in practice. |
| 11 | Generation journal deferred | **AGREE** | The journal field exists in OptimizationCheckpoint but write/read/replay logic is not implemented. Intra-generation crash recovery is deferred. Generation-level checkpoint provides adequate V1 crash safety — a crash mid-generation replays that generation, which is correct if non-optimal. |
| 12 | Branched candidates missing branch categorical in params_json | **DISAGREE** | Synthesis explicitly rejected this as "by design." Branch key stored in separate `branch` column. Downstream consumers (Story 5.4) reconstruct full parameter sets using the branch column. This is a documented, intentional contract decision. |

## Objective Alignment
**Rating:** ADEQUATE

This story serves the system's core objectives as follows:

**Artifact completeness** — STRONG. Three distinct artifact types produced: (1) streaming Arrow IPC with all evaluated candidates and per-fold scores, (2) promoted-candidates Arrow IPC for Story 5.4 intake, (3) JSON run manifest with provenance metadata. All use crash-safe write patterns. Arrow schemas documented in `contracts/arrow_schemas.toml`.

**Operator confidence** — ADEQUATE with gap. The optimization loop produces artifacts and structured logging that give the operator visibility into the search process (generation progress, best score, diversity metrics per AC12). However, the OPTIMIZATION_COMPLETE stage may auto-advance without operator review, contradicting D3's gated transition. This is a config-level fix (`gated_stages` in base.toml), not an architectural gap.

**Reproducibility** — ADEQUATE for V1. Fresh runs are fully deterministic via `master_seed` + derived instance seeds. Checkpoint resume provides generation-level crash safety with documented trajectory divergence (optimizer internal state not serialized). The PRD's core reproducibility promise is *backtest-predicts-live-fidelity*, which this story serves indirectly by ensuring optimization artifacts are complete and traceable. Bit-identical resume is a Growth-phase concern.

**Fidelity** — ADEQUATE. CV-inside-objective with embargo gaps prevents lookahead bias. Fold-aware batch dispatch to Rust evaluator maintains the same execution path as backtesting. The `mean - lambda*std` objective penalizes variance, pushing toward robust parameter sets rather than overfit peaks.

The synthesis process caught and fixed 9 material bugs including: DE convergence detection (blocking portfolio convergence), CMA-ES pending buffer loss on checkpoint, best_candidates loss on resume, instance type attribution, and strategy spec format mismatch. The codebase is in a materially better state post-review.

## Simplification
**Rating:** ADEQUATE

The implementation has 10 source files across a well-decomposed module structure: `parameter_space.py` (parsing/encoding), `portfolio.py` (algorithm instances), `branch_manager.py` (conditional splits), `fold_manager.py` (CV splits), `batch_dispatch.py` (Rust bridge), `checkpoint.py` (persistence), `results.py` (artifact writing), `orchestrator.py` (main loop), `executor.py` (stage integration), plus pipeline_state additions.

**Right complexity:**
- Optimizer internals kept out of pipeline state (D3 — correct abstraction boundary)
- Streaming results writer avoids memory accumulation (NFR1-4)
- Ask/tell protocol cleanly separates candidate generation from evaluation
- Branch manager degrades to passthrough for non-branching strategies

**Debatable complexity:**
- CMA-ES + DE + Sobol + UCB1 portfolio is heavier than V1 minimally requires — but this follows the spec, which follows research. The alternative (single optimizer) would require re-specifying and re-implementing when Growth-phase multi-family optimization arrives.
- Checkpoint model carries `journal_entries` and `portfolio_states` fields that aren't fully utilized yet — placeholder cost is negligible (empty defaults).
- Arrow schema definitions in both code and `contracts/arrow_schemas.toml` create dual-maintenance burden. However, the contract file serves cross-language documentation (Rust consumers reference it), so the duplication has purpose.

A simpler V1 *could* have used a single optimizer family, but the architecture research explicitly chose the portfolio approach for better exploration-exploitation balance on mixed-parameter spaces. The implementation complexity matches the specification complexity — no gratuitous additions observed.

## Forward Look
**Rating:** ADEQUATE

**Story 5.4 (Validation Gauntlet) handoff:**
The promoted-candidates Arrow IPC artifact is the correct contract. It contains stable `candidate_id`, `params_json`, `cv_objective`, `fold_scores`, `branch`, and `instance_type` columns. Story 5.4 can read this directly. The file path follows pipeline naming conventions consistent with other artifacts.

**Story 5.5 (Evidence Packs) handoff:**
The run manifest provides the provenance metadata (hashes, fold definitions, stop reason, generation count) that evidence pack assembly needs. The full results artifact provides the raw data for optimization visualization.

**Story 5.7 (Provenance) handoff:**
The manifest structure has the right fields. The per-instance seed gap (only `master_seed` recorded) should be filled — this is a small fix to `write_run_manifest` to pass the seed dict from `PortfolioManager`.

**Gaps to address before downstream stories rely on this:**
1. **OPTIMIZATION_COMPLETE gating** — Add `"optimization-complete"` to `gated_stages` in `config/base.toml`. Config-only fix.
2. **Per-instance seeds in manifest** — Expand `rng_seeds` dict in `write_run_manifest` call to include instance-level seeds from PortfolioManager. Small code fix.
3. **Promoted-candidates path in stage result** — Consider adding to executor's returned artifacts dict for explicit downstream discovery.

None of these gaps block Story 5.4 implementation, but items 1 and 2 should be addressed before the optimization stage is used in production pipeline runs.

## Observations for Future Stories

1. **Gated stage configuration must be verified against D3** — The pattern of auto-advancing past what should be gated transitions has appeared before (Story 5-4 lessons learned: "base.toml gated_stages missing validation-complete"). Future stories adding pipeline stages should have an explicit task: "Verify gated_stages config includes this stage if D3 marks it gated."

2. **Optimizer state serialization is a real debt** — Deferred to Growth phase, but if any story requires bit-identical resume (e.g., optimization interruption and continuation across sessions), this must be addressed first. Track as a known limitation in the operator interface.

3. **Manifest provenance should be tested against AC** — When an AC says "manifest contains X, Y, Z," the regression tests should verify each field is present and non-empty. AC13's "RNG seeds per instance" should have caught the master_seed-only recording.

4. **Dual-maintenance Arrow schemas** — The pattern of defining schemas in both `contracts/*.toml` and Python code will grow. Consider a validation test that loads the contract TOML and verifies the Python-side schema matches. This would catch drift without requiring schema generation.

5. **Synthesis process caught 9 bugs including 5 HIGH** — This validates the dual-review pipeline. The CMA-ES buffering fix, DE convergence fix, and checkpoint resume fixes were all material correctness issues that would have caused silent failures in production. Continue requiring dual review for compute-stage stories.

## Verdict

**VERDICT: OBSERVE**

The story delivers a functional, well-tested optimization orchestrator that serves the system's artifact completeness and fidelity objectives. The portfolio approach (CMA-ES + DE + Sobol + UCB1) faithfully implements the architecture research decisions. The dual-review process caught and fixed 9 material bugs, leaving the codebase in solid shape for V1 operation.

I disagree with Codex's REVISIT recommendation. Codex overweights two concerns:
1. **Resume reproducibility** — The PRD's reproducibility objective is *backtest-predicts-live*, not *identical search trajectory after crash*. Generation-level checkpoint with documented trajectory divergence is appropriate for V1.
2. **Portfolio complexity** — This follows the architecture research and story spec. It's not over-engineering; it's implementing the chosen design.

The two actionable gaps (OPTIMIZATION_COMPLETE gating and per-instance seeds in manifest) are minor fixes that don't require revisiting the story's architecture or approach. They should be addressed as part of the next story's integration tasks or as a small patch.

Overall, this story materially advances the pipeline toward its V1 goal of a complete optimization-through-validation flow, with the right artifacts at the right abstraction boundaries.
