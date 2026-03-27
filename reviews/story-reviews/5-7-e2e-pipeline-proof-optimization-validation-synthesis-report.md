# Story Synthesis: 5-7-e2e-pipeline-proof-optimization-validation

## Codex Observations & Decisions

### 1. System Alignment — Over-scoped for V1
**Codex said:** Story combines happy-path, resilience, determinism, contract audit, and fixture generation — too much for one story. Recommends splitting.
**Decision:** DISAGREE
**Reasoning:** This follows the established E2E proof pattern from Epics 1-3 (stories 1-9, 2-9, 3-9). All previous E2E proofs combine the same scope categories. Splitting would break the pattern and create artificial boundaries between tests that must run as one pipeline.
**Action:** None — story scope maintained.

### 2. System Alignment — Doesn't advance fidelity
**Codex said:** Fidelity (backtest/live agreement) is not materially advanced.
**Decision:** AGREE (but not actionable)
**Reasoning:** Fidelity is about reconciliation and deployment, which belongs to Epic 6. This is correct behavior for an Epic 5 proof.
**Action:** None — fidelity is out of scope for this proof.

### 3. System Alignment — JSON-only operator proof
**Codex said:** Proves JSON/loadability, not chart-led visual review path that PRD treats as MVP-critical.
**Decision:** AGREE
**Reasoning:** FR25 chart-led visualization is a dashboard concern, not a backend pipeline concern. This E2E proof verifies data artifacts are correctly produced; visualization is proven by dashboard implementation.
**Action:** Added FR25 partial coverage note to AC1. Added "E2E Proof Boundary Clarification" dev note section explaining visualization boundary.

### 4. PRD Challenge — FR23/FR24 too internal
**Codex said:** At E2E-proof level, FR23/FR24 are too internal. The real need is "optimizer runs and produces reviewable candidates."
**Decision:** DISAGREE
**Reasoning:** E2E proofs in this project explicitly verify architecture decision compliance (D1, D3, D6, etc.). Checking that the optimizer dispatches through the Rust bridge (D1) and uses the configured algorithm portfolio (D3) is the appropriate level for an integration proof. Previous E2E proofs (1-9, 2-9, 3-9) follow the same pattern.
**Action:** None.

### 5. PRD Challenge — FR25 not proven
**Codex said:** Story traces to FR25 but never proves the visual review surface. Either add visualization proof or stop claiming FR25.
**Decision:** AGREE
**Reasoning:** FR25 is "run optimization across parameter space AND present results with chart-led visualization." Only the first half is proven here.
**Action:** Updated AC1 to note FR25 partial coverage — optimization execution proven here, chart-led visualization proven by dashboard.

### 6. PRD Challenge — FR40 only checks progression/timestamps
**Codex said:** FR40 says status must show what passed, failed, and why. Story mostly checks progression and timestamps.
**Decision:** AGREE
**Reasoning:** FR40 explicitly requires "what passed, what failed, and why." AC8 was underspecified.
**Action:** Strengthened AC8 to include "per-stage pass/fail status and failure reasons where applicable."

### 7. PRD Challenge — AC13 incorrectly maps to FR42
**Codex said:** Saving a fixture for Epic 6 is test harness plumbing, not FR42 (which is about resume from checkpoint).
**Decision:** AGREE
**Reasoning:** FR42 is "resume interrupted pipeline runs from checkpoint without data loss." Saving a downstream fixture is a different concern entirely.
**Action:** Changed AC13 reference from `[FR42]` to `[E2E proof pattern]`. Reframed to derive fixture from `scoring_manifest.json` contract.

### 8. Architecture Challenge — Bypasses operator boundary
**Codex said:** Architecture says operator surface is skills/API; this proof drives `operator_actions.py` directly. Should use pipeline API/skill boundary.
**Decision:** DISAGREE
**Reasoning:** `operator_actions.py` IS the programmatic API boundary that Claude Code skills invoke (D9 architecture). Skills are `.md` files in `.claude/skills/` that call these Python entry points. The E2E proof tests the system boundary, not the presentation layer. All previous E2E proofs (3-9 especially) follow this same pattern of calling `operator_actions` directly.
**Action:** Added "E2E Proof Boundary Clarification" dev note explaining this design choice.

### 9. Architecture Challenge — Interrupt model mismatched to runtime
**Codex said:** Optimization search is Python-owned and scoring is pure Python, so "interrupt subprocess and resume" isn't right for every stage.
**Decision:** AGREE
**Reasoning:** Valid distinction. Optimization uses Rust subprocess (SIGTERM appropriate), validation is mixed (Rust batch dispatch within Python orchestration), scoring is pure Python (orchestrator cancellation, not subprocess signal).
**Action:** Updated Task 7 to differentiate interrupt mechanisms per runtime. Updated checkpoint/resume dev notes with runtime-specific interrupt strategies.

### 10. Architecture Challenge — Too white-box for E2E proof
**Codex said:** Story checks specific helper modules, write patterns, and internal reuse choices rather than boundary behavior.
**Decision:** DISAGREE
**Reasoning:** Architecture compliance checks (crash_safe_write pattern from D2, BatchDispatcher reuse from D3, structured logging from D6) are appropriate for E2E proofs that verify architecture decisions are honored end-to-end. This is the established pattern — previous proofs check the same level of detail.
**Action:** None.

### 11. Story Design — Gauntlet order contradiction (CRITICAL)
**Codex said:** Story 5.7 requires walk-forward → CPCV → perturbation → Monte Carlo → regime, but Story 5.4 defines cheapest-first order starting from perturbation.
**Decision:** AGREE
**Reasoning:** Story 5.4 AC8 explicitly defines the optimized order as `perturbation → walk_forward → cpcv → monte_carlo → regime` with config-driven `stage_order`. Story 5.7 AC4 contradicted this. This is a hard conflict.
**Action:** Fixed AC4 to reference Story 5.4's config-driven cheapest-first order. Fixed Task 3 to list stages in correct order. Fixed Task 7 interrupt example to use correct stage order.

### 12. Story Design — Hard-gate coverage incomplete
**Codex said:** Task checks PBO and DSR but Story 5.5 requires three hard gates including cost-stress survival.
**Decision:** AGREE
**Reasoning:** Story 5.5 AC1 explicitly lists three hard gates: "DSR pass, PBO ≤ 0.40, cost stress survival at 1.5x." The hard gates table in Story 5.7 dev notes already included all three, but AC5 and Task 4 only mentioned two.
**Action:** Updated AC5 to list all three hard gates with application order. Updated Task 4 to verify all three gates. Updated test name to reflect full coverage.

### 13. Story Design — AC7 says refine but tasks only test accept/reject
**Codex said:** Add explicit coverage for the refine decision path, or remove refine from AC.
**Decision:** AGREE
**Reasoning:** FR39 explicitly says "accept, reject, or refine decisions." The epics AC7 also says refine. Tasks must test all three paths.
**Action:** Added refine path simulation to Task 5 (verify pipeline state resets to OPTIMIZATION). Added `test_operator_refine_resets_to_optimization()` test.

### 14. Story Design — Short-circuit not allowed in ACs
**Codex said:** AC4/Task 3 assume every candidate gets all five stage artifacts, but short-circuit is acknowledged elsewhere.
**Decision:** AGREE
**Reasoning:** Story 5.4 AC8 defines short-circuit behavior. Story 5.5 AC1 handles short-circuited candidates. AC4 must allow this.
**Action:** Updated AC4 to explicitly allow short-circuited candidates with truncated manifests. Updated Task 3 to verify short-circuit behavior and add specific test. Added dev note that downstream must not assume full five-stage artifacts.

### 15. Story Design — "Reasonable wall-clock budget" not testable
**Codex said:** Not testable as written.
**Decision:** AGREE
**Reasoning:** Must have a concrete number for testability.
**Action:** Changed to `@pytest.mark.timeout(1800)` (30 minutes default) with config override via `[e2e].epic5_timeout_seconds`.

### 16. Story Design — Epic-sized, not story-sized
**Codex said:** This is too large for a single story. Consider splitting into happy-path proof and resilience/provenance proof.
**Decision:** DISAGREE
**Reasoning:** This follows the established E2E proof pattern. Stories 1-9, 2-9, 3-9 all have comparable scope (9 tasks, full pipeline coverage, determinism proof, resume proof, fixture generation). Splitting would create artificial boundaries — the determinism proof requires running the happy path twice; the resume proof requires running partial happy paths. They share 80% of their setup.
**Action:** None — maintained as single story per established pattern.

### 17. Downstream Impact — Two handoff contracts
**Codex said:** Story introduces scoring_manifest.json + separate Epic 6 fixture, risking two contracts.
**Decision:** AGREE
**Reasoning:** `scoring_manifest.json` should be the single stable downstream contract. The Epic 6 fixture should be a thin wrapper around it, not a separate bespoke schema.
**Action:** Rewrote AC13 to derive fixture from scoring_manifest. Updated Task 8 to make fixture a thin wrapper augmented with operator decision and artifact directory path. Added dev note about single downstream contract.

### 18. Downstream Impact — Minimal accepted-candidate payload undefined
**Codex said:** Downstream deployment needs a minimal, production-shaped "promotable candidate" contract.
**Decision:** AGREE
**Reasoning:** AC13 was vague about what Epic 6 actually needs.
**Action:** AC13 now explicitly lists the minimal payload: candidate IDs, decisions, ratings, gate outcomes, artifact refs, and provenance hashes.

## Changes Applied
1. **AC1:** Added FR25 partial coverage note (optimization execution only, not visualization)
2. **AC4:** Fixed gauntlet order to match Story 5.4 cheapest-first; added short-circuit allowance with FR41 reference
3. **AC5:** Added all three hard gates (DSR, PBO, cost stress) with application order
4. **AC8:** Strengthened to include per-stage pass/fail status and failure reasons per FR40
5. **AC13:** Reframed from FR42 to E2E proof pattern; fixture derived from scoring_manifest contract with explicit minimal payload
6. **Task 3:** Fixed stage order, added short-circuit verification, added `test_gauntlet_short_circuit_on_validity_failure()` test
7. **Task 4:** Updated hard gate verification to include all three gates; updated test description
8. **Task 5:** Added refine path simulation and `test_operator_refine_resets_to_optimization()` test; strengthened status check
9. **Task 7:** Differentiated interrupt mechanisms per runtime (Rust subprocess vs Python orchestrator cancellation)
10. **Task 8:** Epic 6 fixture reframed as thin wrapper around scoring_manifest
11. **Task 9:** Concrete timeout (30 minutes, configurable)
12. **Dev Notes:** Added "E2E Proof Boundary Clarification" section (operator boundary, visualization boundary, Epic 6 contract)
13. **Dev Notes:** Updated checkpoint/resume details with runtime-specific interrupt strategies

## Deferred Items
- FR25 chart-led visualization proof — deferred to dashboard implementation story
- Operator review through Claude Code skill boundary (vs. direct `operator_actions.py`) — could be tested in a separate skill integration test, but not appropriate for E2E pipeline proof
- Story splitting — maintained as single story per established pattern; revisit if implementation exceeds 3-day estimate

## Verdict
VERDICT: IMPROVED
