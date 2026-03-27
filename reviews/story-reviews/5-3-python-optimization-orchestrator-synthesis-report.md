# Story Synthesis: 5-3-python-optimization-orchestrator

## Codex Observations & Decisions

### 1. System Alignment — Operator Confidence Gap
**Codex said:** Story advances reproducibility and fidelity but barely advances operator confidence. PRD requires chart-led review and evidence packs. CMA-ES + DE + Sobol + branch decomposition + UCB1 is more sophistication than V1 needs.
**Decision:** PARTIALLY AGREE
**Reasoning:** The operator confidence concern is valid but misattributed. D11 and Story 5.5 explicitly own evidence packs, chart-led visualization, and operator review. Story 5.3 is the optimizer core — its job is to produce high-quality artifacts that Story 5.5 can consume. Adding a run manifest (accepted) strengthens that handoff. However, the claim that the CMA-ES + DE + Sobol portfolio is "more than V1 needs" is wrong — Brief 5A research + HuggingFace Codex review specifically recommended this portfolio. UCB1 branch allocation is the only arguably optional piece, but it's trivial to implement and research-backed for conditional parameter handling.
**Action:** Added run manifest to AC #13 for downstream provenance. Added Requirement Traceability Notes section clarifying FR25 scope split between this story (artifact generation) and Story 5.5 (visualization/evidence packs). Portfolio composition left unchanged as research-backed.

### 2. PRD Challenge — FR13/FR24 Wording Conflict
**Codex said:** PRD still says "strategies define optimization stages and groupings" (FR13) while Epic 5 research update says optimizer decides internally. Story follows research update, not original PRD. FR25 requires chart-led visualization but story only produces Arrow output.
**Decision:** AGREE (on wording tension), DISAGREE (on FR25 scope)
**Reasoning:** The FR13/FR24 tension is real and should be explicitly acknowledged so the implementing agent doesn't get confused. The story correctly follows the research update — this is the authoritative interpretation per architecture D3/D10. On FR25: visualization is Story 5.5's job, not an omission here.
**Action:** Added "Requirement Traceability Notes" dev notes section with explicit FR13/FR24 clarification, FR25 scope split explanation, and D3 stage model rationale.

### 3. Architecture Challenge — D3 State Boundary Drift (CRITICAL)
**Codex said:** D3 says single opaque `OPTIMIZING` state, but Task 1 adds `OPTIMIZATION_READY`, `OPTIMIZATION_COMPLETE`, and pipeline checkpoint fields for optimizer internals.
**Decision:** AGREE (on OPTIMIZATION_READY removal), PARTIALLY DISAGREE (on OPTIMIZATION_COMPLETE)
**Reasoning:** D3 explicitly shows `→ OPTIMIZING → OPTIMIZATION_COMPLETE (gated) → VALIDATING`. So `OPTIMIZATION_COMPLETE` IS part of D3's state model — Codex was wrong to suggest removing it. However, `OPTIMIZATION_READY` is not in D3 and adds unnecessary intermediate state. The pipeline checkpoint fields for optimizer internals clearly violate D3's separation principle.
**Action:** Removed `OPTIMIZATION_READY` from Task 1. Kept `OPTIMIZING` + `OPTIMIZATION_COMPLETE` per D3. Replaced pipeline checkpoint fields with explicit note that optimizer owns its own checkpoint files. Updated Pipeline State Machine integration point description. Added anti-pattern #15.

### 4. Story Design — Size, Memory Contradiction, Streaming Gap (CRITICAL)
**Codex said:** Story too large (13 tasks, 9 modules). Memory contradiction (AC11 ~5.5GB vs config 4096 MB). Anti-pattern #4 forbids accumulation but Task 10 uses `all_candidates: list[dict]`. Missing deterministic seeds and generation journal for crash safety.
**Decision:** DISAGREE (on splitting), AGREE (on contradictions and gaps)
**Reasoning:** This is a single-operator project where stories are implementation units for AI dev agents. 13 well-decomposed tasks is appropriate for this workflow — splitting would create artificial boundaries and integration overhead. However, the specific contradictions are real bugs: (a) memory_budget_mb = 4096 doesn't match NFR4's ~5.5GB modeling, (b) `all_candidates: list[dict]` contradicts anti-pattern #4, (c) missing deterministic seeds and generation journal are legitimate gaps that affect reproducibility and crash safety.
**Action:** Fixed memory_budget_mb to 5632 (~5.5GB). Replaced `all_candidates: list[dict]` with `StreamingResultsWriter` append-mode pattern. Added AC #16 for deterministic RNG seeds. Added generation journal to Task 9 orchestrator. Added anti-patterns #13 (generation journal) and #14 (stable candidate IDs). Added integration tests for deterministic seeds and journal crash recovery.

### 5. Downstream Impact — Provenance and Contract Gaps
**Codex said:** Story 5.4 expects ranked deterministic candidates. Story 5.7 expects manifests with hashes. Current result schema lacks provenance. AC15 targets wrong consumer.
**Decision:** AGREE
**Reasoning:** The downstream contract gaps are real. Story 5.4 needs stable candidate IDs to trace candidates through validation. Story 5.7 needs provenance (hashes, seeds, fold definitions) for reproducibility proof. The current result schema was too lean. AC15's "presented for operator review" was also misleading — V1 promotion feeds validation, not direct operator go/no-go (that's Story 5.5's job).
**Action:** Added run manifest to AC #13 with all provenance fields (dataset_hash, strategy_spec_hash, config_hash, fold_definitions, rng_seeds, stop_reason, branch_metadata). Revised AC #15 to target Story 5.4 validation intake with stable candidate IDs. Added `write_run_manifest()` and `promoted_candidates` Arrow IPC to Task 10. Added tests for provenance and streaming.

### 6. Codex Recommendation: Split into smaller stories
**Codex said:** Split into optimizer core, Rust dispatch/fold handling, and results/provenance/pipeline integration.
**Decision:** DISAGREE
**Reasoning:** V1 is NOT gated on profitability — it's gated on reproducibility and evidence quality. This is a one-person operation where stories are executed by AI dev agents. Splitting this story would create artificial integration seams, increase coordination overhead, and slow delivery without proportional quality benefit. The 13 tasks are already well-decomposed with clear dependencies and test coverage.
**Action:** None. Story scope unchanged.

### 7. Codex Recommendation: Replace absolute memory AC with preflight budget
**Codex said:** Replace `~5.5GB peak` AC with a preflight budget contract.
**Decision:** AGREE
**Reasoning:** An absolute memory number is not verifiable as an AC. A preflight budget check that reduces batch size if the run doesn't fit is both testable and matches NFR4's guidance ("reduce batch size before starting, not mid-run").
**Action:** Rewrote AC #11 to specify preflight budget validation with automatic batch size reduction, plus bounded streaming during execution.

### 8. Codex Recommendation: Make DE/UCB1/branch decomposition optional
**Codex said:** Make multi-algorithm portfolio, UCB1 branch allocation, and secondary optimizers optional or deferred.
**Decision:** DISAGREE
**Reasoning:** Brief 5A research + HuggingFace Codex review specifically recommended the CMA-ES + DE + Sobol portfolio for complementary search characteristics. DE (TwoPointsDE) is 3 instances vs CMA-ES's 10 — it's a minor addition with proven benefit for parameter spaces with multiple basins. Branch decomposition is required for D10 conditional parameters (exit_type branches). UCB1 is the simplest multi-armed bandit for branch budget allocation. None of these are premature — they're the researched V1 architecture.
**Action:** None. Portfolio composition unchanged. This is the research-backed design.

### 9. Codex Recommendation: Deterministic seeds and stable candidate IDs
**Codex said:** Add ACs for deterministic seeds, stable candidate IDs, canonical ordering, and reproducibility tests.
**Decision:** AGREE
**Reasoning:** FR18 requires identical outputs from identical inputs. Without deterministic seeds and stable IDs, optimization runs aren't reproducible and downstream stories can't trace candidates.
**Action:** Added AC #16 for deterministic RNG seeds. Added anti-pattern #14 for stable candidate IDs. Added integration tests for seed reproducibility and journal crash recovery.

### 10. Codex Recommendation: Generation journal for crash safety
**Codex said:** No explicit journal/phase model for crashes between ask, dispatch, and tell — duplicate or lost evaluations are likely.
**Decision:** AGREE
**Reasoning:** This is a real gap. If the process crashes after dispatching to Rust but before telling scores back, resume would re-dispatch the same batch (wasting compute) or skip it (losing evaluations). A simple generation journal solves this.
**Action:** Added generation journal to Task 9 orchestrator design. Added anti-pattern #13 requiring the journal. Added integration test `test_generation_journal_crash_recovery`.

## Changes Applied

1. **AC #11:** Replaced absolute ~5.5GB memory assertion with preflight budget check + automatic batch size reduction
2. **AC #13:** Added run manifest with full provenance (dataset_hash, strategy_spec_hash, config_hash, fold_definitions, rng_seeds, stop_reason, branch_metadata)
3. **AC #15:** Changed promotion target from "operator review" to "Story 5.4 validation gauntlet intake" with stable candidate IDs
4. **AC #16 (new):** Deterministic RNG seeds per instance, derived from master seed, persisted in checkpoints
5. **Task 1:** Removed `OPTIMIZATION_READY` stage (D3 violation). Removed pipeline checkpoint fields for optimizer internals. Added explicit D3 separation note
6. **Task 2:** Fixed memory_budget_mb from 4096 to 5632 to match NFR4 data volume modeling
7. **Task 9:** Added generation journal for crash-safe ask/dispatch/tell cycle. Added stop_reason to OptimizationResult
8. **Task 10:** Replaced `all_candidates: list[dict]` with `StreamingResultsWriter` append-mode pattern. Added `write_run_manifest()`. Added `promoted_candidates` Arrow IPC artifact. Added 2 new tests
9. **Task 12:** Added 2 integration tests: deterministic seed reproducibility, generation journal crash recovery. Fixed state transition test to match D3 stages
10. **Dev Notes:** Added "Requirement Traceability Notes" section clarifying FR13/FR24 tension, FR25 scope split, D3 stage model
11. **Anti-patterns:** Added #13 (generation journal required), #14 (stable candidate IDs), #15 (optimizer state separation from pipeline state)
12. **Pipeline State Machine integration point:** Updated to match D3 two-stage model
13. **Files to modify:** Removed `contracts/pipeline_checkpoint.toml`, updated descriptions

## Deferred Items

- **Evidence pack for optimization gate:** Valid concern but belongs to Story 5.5 (D11 analysis layer). Story 5.3's run manifest provides the data Story 5.5 needs to assemble the evidence pack.
- **PRD FR13 text update:** The PRD still says "strategies define their own optimization stages." This should be updated to match the research update, but that's a PRD maintenance task, not a story-level change.
- **Story splitting:** Codex recommended splitting into 3 stories. Rejected for this one-person/AI-agent workflow, but noted in case team size changes.

## Verdict
VERDICT: IMPROVED
