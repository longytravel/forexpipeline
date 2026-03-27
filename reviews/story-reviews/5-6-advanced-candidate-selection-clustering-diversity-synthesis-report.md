# Story Synthesis: 5-6-advanced-candidate-selection-clustering-diversity

## Codex Observations & Decisions

### 1. System Alignment — Reproducibility of exploratory selection
**Codex said:** 20% exploratory randomness lacks a first-class recorded seed/config field. Manifest is too thin for attribution or replay. Recommends simplifying to deterministic-only or deferring exploration.
**Decision:** AGREE (seed/manifest gaps) / DISAGREE (defer exploration)
**Reasoning:** The seed concern is valid — `SelectionConfig` mentioned seed in Dev Notes anti-pattern #5 but lacked an explicit `random_seed` field. The manifest was indeed missing provenance fields needed for replay. However, deferring MAP-Elites/exploratory selection would contradict FR28's explicit requirement for "mathematically principled methodology" and Brief 5B research findings. The 80/20 split is a deliberate design choice from research, not scope creep.
**Action:** Added `random_seed: int | None` to `SelectionConfig` (defaults to `optimization_run_id` hash). Added `random_seed_used` to `SelectionManifest`. Added AC #8 for deterministic rerun reproducibility. Added `test_selection_deterministic_rerun` test.

### 2. PRD Challenge — Over-prescriptive methodology
**Codex said:** Story hard-codes HDBSCAN, Gower, TOPSIS, CRITIC, MAP-Elites, UMAP — too much implementation prescription. Should be outcome-based requirements.
**Decision:** DISAGREE
**Reasoning:** This is an implementation story, not a product requirement. Story 5.2 (research) already evaluated methodology options and Brief 5B locked the specific algorithms. An implementation spec SHOULD prescribe exact algorithms — that's the entire point of having a research phase feed into implementation. "Leave the ranking stack configurable" would just punt validated decisions to dev time, creating ambiguity where research already provided clarity. The PRD states the outcomes; the story translates them into buildable tasks.
**Action:** None — story correctly operationalizes research findings into implementation tasks.

### 3. Architecture Challenge — D11 location mismatch and new pipeline stages
**Codex said:** D11 places candidate compression at `analysis/candidate_compressor.py`. Story creates a new `selection/` subsystem and adds `SELECTING`/`SELECTION_COMPLETE` pipeline stages, breaking documented architecture. Also flags a potential cycle: Task 4 depends on scoring outputs while positioning itself "after optimization."
**Decision:** AGREE (architecture must be updated first) / DISAGREE (breaking architecture — this is Growth expansion)
**Reasoning:** Codex correctly identifies that D11 envisions a single file, not a 9-file subsystem. However, the scope of Growth-phase candidate selection (clustering, ranking, diversity archive, visualization, executor) genuinely exceeds single-file scope. Every other pipeline capability at this complexity level (confidence/, validation/, optimization/) has its own subsystem. The resolution is: update architecture D11 and D3 BEFORE implementation, not as a side effect. Re: pipeline stage position — the story is correctly positioned POST-scoring (it consumes scoring manifest as input), not pre-validation. Codex's claim about "output ready for validation gauntlet" mischaracterizes AC7, which says "diverse candidates are emitted" for forward-testing. Re: dependency cycle — there is none. Pipeline flow is: optimization → validation → scoring → selection. Selection consumes scoring outputs; it doesn't feed back into validation.
**Action:** Expanded Task 10 to require D11 file structure update AND D3 stage graph update as explicit prerequisites BEFORE implementation begins. Updated D11 Dev Notes constraint to clarify the architectural expansion rationale.

### 4. Story Design — Testability gaps and memory contradiction
**Codex said:** ACs are partly testable at unit level but not as stage contract. Missing determinism tests, resource-budget tests, operator evidence artifacts, pipeline skill integration. Memory claims contradict: 2.4 GB Gower matrix vs. 50 MB peak.
**Decision:** AGREE (memory contradiction, missing determinism AC, missing memory tests) / DISAGREE (pipeline skill integration, operator evidence)
**Reasoning:** The memory contradiction is the most actionable finding — the story claimed ~50 MB peak while acknowledging a 2.4 GB dense distance matrix. This was genuinely misleading. Fixed with explicit chunked computation strategy and pre-filtering guard. The missing determinism AC is valid — reproducibility is a core project value and deserved an explicit AC. However, pipeline skill integration (`/pipeline` command) is Epic 4/dashboard scope, not this story. Operator evidence packs are already addressed via visualization data (Task 6) and the enriched manifest — a separate "evidence pack" story is not needed here.
**Action:** Fixed memory budget section: replaced contradictory 50 MB claim with explicit chunked float32 strategy (~1.2 GB) and pre-filtering option (~120 MB). Added `max_clustering_candidates` config field (default 5000). Added AC #8 for deterministic reruns. Added `test_memory.py` with chunked computation and pre-filter tests. Added anti-pattern #10 about dense Gower matrix without chunking.

### 5. Downstream Impact — Thin manifest
**Codex said:** `SelectionManifest` needs upstream artifact refs, CRITIC weights, gate outcomes, exclusion reasons, seed, selected-vs-rejected trace for downstream dashboard/audit/evidence work.
**Decision:** AGREE (provenance fields, CRITIC weights, gate summary, seed) / DISAGREE (full rejected-candidate trace)
**Reasoning:** Valid concern. Downstream consumers (dashboard, evidence packs, audit) should be able to explain selections from the manifest alone without re-running the funnel. CRITIC weights explain "why these objectives matter more"; gate failure summary explains "how many candidates failed each gate." Upstream refs with hashes enable replay verification. However, a full selected-vs-rejected trace (listing every rejected candidate with reason) would bloat a JSON manifest for 10K candidates. The funnel_stats already provide aggregate counts; per-candidate rejection belongs in a separate debug artifact if needed.
**Action:** Added `UpstreamRefs`, `critic_weights`, `gate_failure_summary`, `random_seed_used` to `SelectionManifest` model. Updated downstream contract schema with all new fields. Added note that manifest is a provenance-rich decision artifact — downstream consumers should NOT need to re-derive.

## Changes Applied
- Added `random_seed: int | None` to `SelectionConfig` (Task 1)
- Added `max_clustering_candidates: int` to `SelectionConfig` (Task 8 config)
- Expanded `SelectionManifest` with `UpstreamRefs`, `critic_weights`, `gate_failure_summary`, `random_seed_used` (Task 1 models)
- Added new AC #8: deterministic rerun reproducibility
- Renumbered old AC #8 to AC #9, expanded to include D11 file structure and D3 stage graph updates
- Expanded Task 10: now covers D11 file structure, D3 stage graph, and is marked as a prerequisite before implementation
- Fixed memory budget section: removed contradictory 50 MB claim, added chunked float32 strategy, pre-filtering guard, memory monitoring requirement
- Added anti-pattern #10: dense Gower matrix without chunking
- Added `test_selection_deterministic_rerun` and `test_selection_manifest_upstream_refs_populated` to executor tests
- Added `test_memory.py` with `test_gower_chunked_computation` and `test_pre_filter_large_candidate_set`
- Updated downstream contract schema with all provenance fields and explainability note
- Updated D11 architecture constraint Dev Note to clarify subsystem expansion rationale and prerequisite status
- Updated test file counts in project structure

## Deferred Items
- Full per-candidate rejection trace artifact (valid for audit, but too large for JSON manifest — could be a separate `selection/rejected_trace.arrow` in future)
- Pipeline skill (`/pipeline`) integration for operator review entry point (Epic 4 / dashboard scope)
- Separate operator evidence pack assembly (already partially addressed by viz data + enriched manifest; could be formalized in a future story)

## Verdict
VERDICT: IMPROVED

The story's architecture, pipeline position, and algorithm choices are sound — they follow directly from Brief 5B research and the established pipeline pattern. Codex's most valuable contributions were: (1) the memory budget contradiction, which was genuinely misleading and now resolved with explicit chunked strategy; (2) the manifest thinness, addressed with provenance fields enabling downstream explainability; (3) the missing determinism AC, which codifies a core project value; (4) the architecture prerequisite, ensuring D11/D3 are updated before implementation rather than as an afterthought. Codex's RETHINK verdict was too aggressive — the story doesn't need fundamental redesign, but the targeted improvements meaningfully strengthen reproducibility, explainability, and architecture alignment.
