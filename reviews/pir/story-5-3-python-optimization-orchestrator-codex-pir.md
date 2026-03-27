# Story 5-3-python-optimization-orchestrator: Story 5.3: Python Optimization Orchestrator — Codex PIR

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-22
**Type:** Post-Implementation Review (alignment analysis)

---

**1. Objective Alignment**

Assessment: `CONCERN`

Evidence:
- Artifact production is strong. The story writes incremental optimization results, a promoted-candidates artifact, and a run manifest, all as persisted outputs: [results.py#L45](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/results.py#L45), [results.py#L137](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/results.py#L137), [results.py#L181](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/results.py#L181), [arrow_schemas.toml#L86](/C:/Users/ROG/Projects/Forex Pipeline/contracts/arrow_schemas.toml#L86), [arrow_schemas.toml#L98](/C:/Users/ROG/Projects/Forex Pipeline/contracts/arrow_schemas.toml#L98). This aligns with PRD artifact completeness: [prd.md#L99](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L99), [prd.md#L551](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L551).
- The optimizer is correctly kept opaque to pipeline state, which matches D3 and helps keep orchestration understandable: [pipeline_state.py#L26](/C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/pipeline_state.py#L26), [architecture.md#L432](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L432), [story 5.3 spec#L103](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L103).
- Reproducibility is only partial. Fresh runs are seeded deterministically through `master_seed` and derived instance seeds: [portfolio.py#L410](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L410), [test_e2e_optimization.py#L234](/C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_optimization/test_e2e_optimization.py#L234). But resumed runs do not restore actual optimizer internals; only metadata-like state is restored: [portfolio.py#L188](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L188), [portfolio.py#L202](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L202), [portfolio.py#L306](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L306), [portfolio.py#L317](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/portfolio.py#L317), [checkpoint.py#L20](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/checkpoint.py#L20), [synthesis-report.md#L83](/C:/Users/ROG/Projects/Forex Pipeline/reviews/synthesis/5-3-python-optimization-orchestrator-synthesis-report.md#L83).
- Operator confidence is weakened by state-machine behavior. The story spec says `OPTIMIZATION_COMPLETE` is gated: [story 5.3 spec#L98](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L98), [story 5.3 spec#L304](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L304). The implementation auto-advances from `OPTIMIZATION_COMPLETE` to `VALIDATING`, and the configured gated stages omit optimization entirely: [pipeline_state.py#L100](/C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/pipeline_state.py#L100), [stage_runner.py#L87](/C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L87), [base.toml#L63](/C:/Users/ROG/Projects/Forex Pipeline/config/base.toml#L63).
- Manifest-based trust is overstated. `GateManager` says it validates artifact integrity via manifest hash, but the optimization executor only checks that the Arrow file exists and has rows: [gate_manager.py#L158](/C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/gate_manager.py#L158), [executor.py#L114](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/executor.py#L114).

Concrete observations:
- This story clearly advances `artifact completeness`.
- It advances `operator confidence` at the pipeline-status level, but not yet at the optimization-review level; there is no optimization evidence-pack hook comparable to the backtest hook: [stage_runner.py#L482](/C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L482).
- It does not fully satisfy the system’s strongest reproducibility promise because crash/resume can change the search trajectory.
- It fits V1 in one important way: promotion is intentionally simple top-N rather than clustering, which matches V1 scope: [story 5.3 spec#L85](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L85), [results.py#L181](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/results.py#L181).
- It is somewhat over-built for V1 in search strategy complexity: CMA-ES + DE + Sobol + UCB1 branching is a lot of machinery for a release whose gate is evidence quality, not optimizer sophistication.

**2. Simplification**

Assessment: `ADEQUATE`

Evidence:
- Branching support is only partial, but the implementation still introduces full branch-management and UCB1 machinery: [parameter_space.py#L128](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/parameter_space.py#L128), [parameter_space.py#L154](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/parameter_space.py#L154), [branch_manager.py#L69](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/branch_manager.py#L69).
- The output contract downstream is simple: ranked candidates plus promoted candidates. Nothing in that contract requires multiple optimizer families or UCB1 allocation: [arrow_schemas.toml#L86](/C:/Users/ROG/Projects/Forex Pipeline/contracts/arrow_schemas.toml#L86), [arrow_schemas.toml#L98](/C:/Users/ROG/Projects/Forex Pipeline/contracts/arrow_schemas.toml#L98), [architecture.md#L288](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L288).
- There is contract duplication. The Arrow schemas are defined both in code and in `contracts/arrow_schemas.toml`: [results.py#L23](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/results.py#L23), [arrow_schemas.toml#L86](/C:/Users/ROG/Projects/Forex Pipeline/contracts/arrow_schemas.toml#L86).
- The checkpoint model carries fields that the orchestrator does not actually use for this flow, notably `portfolio_states` and `journal_entries`: [checkpoint.py#L23](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/checkpoint.py#L23), [checkpoint.py#L32](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/checkpoint.py#L32), [orchestrator.py#L272](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/orchestrator.py#L272).

Concrete observations:
- A simpler V1 path was available: one deterministic optimizer family plus Sobol, explicit branch splitting only when needed, and a thinner checkpoint model.
- The current implementation is not gratuitous everywhere. Keeping optimizer internals outside pipeline state is the right simplification.
- The biggest simplification opportunity is not fewer files; it is fewer promises. Right now the code advertises journaled resumability and manifest validation more strongly than it actually delivers.

**3. Forward Look**

Assessment: `CONCERN`

Evidence:
- The promoted-candidates artifact is the right basic handoff for Story 5.4: [results.py#L181](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/results.py#L181), [arrow_schemas.toml#L98](/C:/Users/ROG/Projects/Forex Pipeline/contracts/arrow_schemas.toml#L98), [pipeline_state.py#L100](/C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/pipeline_state.py#L100).
- But the stage result does not explicitly return the promoted-candidates path, only the full results path and manifest: [executor.py#L96](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/executor.py#L96). Downstream consumers will have to infer `promoted-candidates.arrow` by convention.
- Provenance is incomplete for future reproducibility work. The manifest records only `master_seed`, not per-instance seeds promised by the story: [orchestrator.py#L314](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/orchestrator.py#L314), [results.py#L150](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/results.py#L150), [story 5.3 spec#L90](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L90).
- Config provenance is fragile. `StageRunner` computes a config hash and passes it in context, but `OptimizationExecutor` ignores that context value and reloads config independently, while the orchestrator reads `config["pipeline"]["config_hash"]`: [stage_runner.py#L559](/C:/Users/ROG/Projects/Forex Pipeline/src/python/orchestrator/stage_runner.py#L559), [executor.py#L54](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/executor.py#L54), [orchestrator.py#L140](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/orchestrator.py#L140), [base.toml#L58](/C:/Users/ROG/Projects/Forex Pipeline/config/base.toml#L58).
- The generation journal required by the story is still deferred, so downstream stages cannot assume crash-resume yields a lossless candidate ledger: [story 5.3 spec#L245](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-3-python-optimization-orchestrator.md#L245), [synthesis-report.md#L76](/C:/Users/ROG/Projects/Forex Pipeline/reviews/synthesis/5-3-python-optimization-orchestrator-synthesis-report.md#L76).
- Branched candidate payloads are only self-consistent if downstream code merges `params_json` with the separate `branch` column; the branch-defining categorical is removed from the branch subspace before encoding: [parameter_space.py#L160](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/parameter_space.py#L160), [orchestrator.py#L219](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/orchestrator.py#L219), [arrow_schemas.toml#L91](/C:/Users/ROG/Projects/Forex Pipeline/contracts/arrow_schemas.toml#L91).
- The orchestrator guesses the strategy-spec path instead of carrying the upstream artifact path through cleanly: [executor.py#L45](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/executor.py#L45), [orchestrator.py#L369](/C:/Users/ROG/Projects/Forex Pipeline/src/python/optimization/orchestrator.py#L369).

Concrete observations:
- Story 5.4 can probably consume what is here, but only if it relies on conventions that are not explicit in the stage contract.
- The next stories will inherit weak provenance unless config-hash propagation and per-instance seed recording are tightened.
- The branching model assumes “one top-level conditional split,” which is reasonable for current forex examples but likely not durable as strategy specs grow.

**Overall**

Assessment: `REVISIT`

The story materially improves artifact generation and pipeline integration, but it falls short on two of the system’s core objectives: true reproducible resume and operator-confidence-at-gate. The largest reasons are the non-gated `OPTIMIZATION_COMPLETE` stage, incomplete resume semantics, and a handoff contract that is good enough by convention rather than explicit proof.
