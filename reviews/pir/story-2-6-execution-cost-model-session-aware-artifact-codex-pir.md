# Story 2-6-execution-cost-model-session-aware-artifact: Story 2.6: Execution Cost Model — Session-Aware Artifact — Codex PIR

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-16
**Type:** Post-Implementation Review (alignment analysis)

---

**1. Objective Alignment**

Assessment: `ADEQUATE`

- This story clearly advances **artifact completeness**. It defines an explicit contract, persists a versioned artifact plus manifest, and the shipped EURUSD baseline is present as a reviewable file on disk in [cost_model_schema.toml#L5](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/cost_model_schema.toml#L5), [storage.py#L56](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/storage.py#L56), [v001.json#L1](/c/Users/ROG/Projects/Forex%20Pipeline/artifacts/cost_models/EURUSD/v001.json#L1), [manifest.json#L1](/c/Users/ROG/Projects/Forex%20Pipeline/artifacts/cost_models/EURUSD/manifest.json#L1). That directly supports the PRD requirement that every stage emit a persisted, reviewable artifact in [prd.md#L99](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L99) and [prd.md#L551](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L551).

- It also advances **fidelity** well. The implementation is session-aware, uses config-backed session definitions, and models per-session mean/std spread and slippage rather than flat constants in [builder.py#L175](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/builder.py#L175), [builder.py#L221](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/builder.py#L221), [sessions.py#L31](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/sessions.py#L31), [config/base.toml#L24](/c/Users/ROG/Projects/Forex%20Pipeline/config/base.toml#L24). That matches the system’s “not hardcoded constants” objective in [prd.md#L97](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L97) and FR20/FR21 in [prd.md#L489](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L489).

- It improves **operator confidence** indirectly, mainly through approval semantics and safer defaults. Consumers now resolve through `latest_approved_version`, not raw newest files, in [storage.py#L183](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/storage.py#L183), [__main__.py#L127](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/__main__.py#L127), [__main__.py#L165](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/__main__.py#L165), which aligns with the story contract in [2-6-execution-cost-model-session-aware-artifact.md#L55](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-6-execution-cost-model-session-aware-artifact.md#L55). That reduces the risk of draft artifacts silently driving the pipeline.

- What works against objectives: reproducibility proof is weaker than it looks for tick-analysis artifacts, because the CLI hashes the **tick-data path string**, not the dataset contents, in [__main__.py#L118](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/__main__.py#L118). Also, direct operator inspection is still raw JSON/CLI output, not a human-friendly evidence pack, in [__main__.py#L140](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/__main__.py#L140). So this helps confidence structurally, but not yet experientially for a non-coder.

- V1 scope fit is good. The story deliberately keeps V1 deterministic by storing `std_*` values for future use while downstream V1 consumers use means directly, as specified in [2-6-execution-cost-model-session-aware-artifact.md#L273](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-6-execution-cost-model-session-aware-artifact.md#L273). The live-calibration path is only a stub in [builder.py#L243](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/builder.py#L243), which is appropriate rather than overbuilt.

**2. Simplification**

Assessment: `ADEQUATE`

- The clearest simplification is session labeling. The code hardcodes `_LABEL_BOUNDARIES` and then separately validates config against them in [sessions.py#L22](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/sessions.py#L22) and [sessions.py#L96](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/sessions.py#L96). A simpler design would derive the non-overlapping label boundaries from `config/base.toml` once and use that derived structure everywhere. Current behavior is safe, but it duplicates authority.

- There is also unnecessary semantic surface in exposing both raw-latest and approved-latest loaders publicly in [storage.py#L170](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/storage.py#L170), [storage.py#L183](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/storage.py#L183), [__init__.py#L27](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/__init__.py#L27). The story explicitly says downstream consumers must not use raw latest in [2-6-execution-cost-model-session-aware-artifact.md#L126](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-6-execution-cost-model-session-aware-artifact.md#L126), so keeping `load_latest_cost_model()` public invites the wrong behavior.

- The CLI orchestration is somewhat duplicated. `create-default` and `create` both build, save, hash, and register artifacts separately in [__main__.py#L57](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/__main__.py#L57) and [__main__.py#L84](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/__main__.py#L84). A single “save and register” path would reduce moving parts and centralize reproducibility behavior.

- I do not see major dead weight. Schema, builder, storage, manifest approval, and default EURUSD baseline all map to explicit downstream needs in Story 2.7/2.9 and the architecture’s D13 contract in [architecture.md#L901](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L901). The future-facing pieces are restrained, not bloated.

**3. Forward Look**

Assessment: `ADEQUATE`

- The output contract is mostly set up correctly for the next stories. The JSON artifact structure matches the planned Rust consumer contract, and the approved-version manifest pointer matches the E2E proof expectation in [2-6-execution-cost-model-session-aware-artifact.md#L271](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-6-execution-cost-model-session-aware-artifact.md#L271), [architecture.md#L906](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L906), [manifest.json#L3](/c/Users/ROG/Projects/Forex%20Pipeline/artifacts/cost_models/EURUSD/manifest.json#L3).

- The main missing piece for future reproducibility is **true input fingerprinting** for tick-analysis. Right now `input_hash` can represent only the directory path string in [__main__.py#L118](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/__main__.py#L118), while FR60 expects tracking of actual input changes in [prd.md#L553](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L553). As the pipeline grows, that will make provenance weaker than the manifest suggests.

- Another forward assumption is that session taxonomy is fixed. The code assumes exactly five sessions and fixed label boundaries in [sessions.py#L15](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/sessions.py#L15) and [sessions.py#L22](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/cost_model/sessions.py#L22). That is fine for V1, but if later epics evolve session definitions, this becomes a code change, not a config-only change.

- Provenance is also split across artifact and manifest. The artifact itself does not carry `config_hash` or session-schedule provenance in [v001.json#L1](/c/Users/ROG/Projects/Forex%20Pipeline/artifacts/cost_models/EURUSD/v001.json#L1); only the manifest does in [manifest.json#L10](/c/Users/ROG/Projects/Forex%20Pipeline/artifacts/cost_models/EURUSD/manifest.json#L10). That is acceptable if every downstream tool always goes through the manifest, but weaker if artifacts are ever copied or inspected standalone.

**Overall**

Assessment: `OBSERVE`

This story is materially aligned with BMAD Backtester’s objectives, especially artifact completeness and session-aware fidelity, and it sets up Story 2.7/2.9 on the right contract. The main observations are: input provenance for tick-analysis is not strong enough yet, session-boundary authority is duplicated, and operator confidence is improved by safety semantics more than by human-friendly evidence presentation.
