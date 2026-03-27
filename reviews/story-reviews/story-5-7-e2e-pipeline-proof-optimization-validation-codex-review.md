# Story 5-7-e2e-pipeline-proof-optimization-validation: Story 5.7: E2E Pipeline Proof — Optimization & Validation — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-22
**Type:** Holistic System Alignment Review

---

**1. System Alignment**  
Assessment: `CONCERN`  
Evidence: [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L53), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L58), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L162), [prd](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L99), [prd](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L119), [prd](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L253)  
Observations:
- This story strongly advances reproducibility, artifact completeness, and some operator confidence through determinism, resume, manifests, evidence packs, and status checks.
- It does not materially advance fidelity. In the PRD, fidelity is about backtest/live agreement and divergence attribution, which belongs to reconciliation and deployment later, not this proof.
- It partially works against operator confidence because it proves JSON/loadability, not the chart-led visual review path the PRD treats as MVP-critical.
- It is over-scoped for a single V1 story: it combines happy-path integration, resilience, determinism, upstream contract audit, and downstream fixture generation.
Recommendation:
- Keep the integration proof goal, but reduce this story to one happy-path proof plus one deterministic rerun plus one resume proof.
- Move upstream contract verification and Epic 6 fixture scaffolding out of core acceptance criteria.
- Add at least a thin verification of operator-visible review artifacts, not just backend JSON presence.

**2. PRD Challenge**  
Assessment: `CONCERN`  
Evidence: [prd](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L495), [prd](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L497), [prd](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L517), [prd](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L518), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L15), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L73)  
Observations:
- `FR23`/`FR24` are valid product capabilities, but at E2E-proof level they are too internal. The real operator need is “the optimizer runs and produces reviewable candidates,” not “this proof re-verifies optimizer portfolio/config internals.”
- `FR25` is under-served here. The PRD says chart-led visualization; this story traces to `FR25` but never proves the visual review surface.
- `FR40` says status must show what passed, failed, and why; this story mostly checks progression and timestamps.
- `AC13` is not a product requirement. Saving a fixture for Epic 6 is test harness plumbing, and mapping it to `FR42` is incorrect.
Recommendation:
- Reframe this story around outcome-level FRs: `FR39`, `FR40`, `FR42`, `FR58`, `FR59`, `FR61`.
- Treat `FR23`-`FR34` as dependencies proven by the integrated run, not as internals to re-specify.
- Either add explicit visualization proof or stop claiming `FR25` is covered here.

**3. Architecture Challenge**  
Assessment: `CONCERN`  
Evidence: [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L414), [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L620), [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L647), [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L815), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L130), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L150), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L199)  
Observations:
- The story bypasses the primary operator boundary. Architecture says the operator surface is skills/API; this proof drives `operator_actions.py` directly.
- The interruption model is mismatched to runtime ownership. Optimization search is Python-owned and scoring is pure Python, so “interrupt subprocess and resume” is not the right proof shape for every stage.
- The story is too white-box for an E2E proof: it checks specific helper modules, write patterns, and internal reuse choices rather than just stable boundary behavior.
Recommendation:
- Run operator-review proof through the pipeline API/skill boundary, not direct module calls.
- Make resume tests runtime-specific: orchestrator checkpoint/resume for Python-owned stages, subprocess interruption only where the Rust process is actually the thing being proved.
- Replace internal implementation checks with contract assertions on produced artifacts and state transitions.

**4. Story Design**  
Assessment: `CRITICAL`  
Evidence: [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L30), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L120), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L132), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L135), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L188), [epics](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md#L1269), [epics](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md#L1297), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L425)  
Observations:
- Hard conflict: Story 5.7 requires gauntlet order `walk-forward -> CPCV -> perturbation -> Monte Carlo -> regime`, but Story 5.4 defines optimized order with short-circuiting starting from perturbation.
- Hard-gate coverage is incomplete. The task checks `PBO` and `DSR`, but Story 5.5 and the hard-gates table also require cost-stress survival.
- `AC7` says accept/reject/refine; tasks only prove accept/reject.
- `AC4`/Task 3 assume every candidate gets all five stage artifacts, but the story itself acknowledges short-circuited candidates still get RED evidence packs with truncated analysis.
- “Reasonable wall-clock budget” is not testable as written.
- This is epic-sized, not story-sized.
Recommendation:
- Fix the gauntlet-order contradiction first.
- Add the refine path, or remove it from the AC.
- Add cost-stress to hard-gate tests.
- Allow short-circuit outcomes explicitly in the ACs.
- Split this story into happy-path proof and resilience/provenance proof, or shrink it aggressively.

**5. Downstream Impact**  
Assessment: `CONCERN`  
Evidence: [prd](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L187), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L118), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L168), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/5-7-e2e-pipeline-proof-optimization-validation.md#L422), [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L825), [epics](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md#L1392)  
Observations:
- The story correctly identifies `scoring_manifest.json` as the stable downstream contract, but then introduces a separate Epic 6 fixture artifact. That risks two handoff contracts.
- Downstream deployment needs a minimal, production-shaped “promotable candidate” contract, not a test-only bundle with ad hoc fields.
- If short-circuited candidates remain valid evidence-pack outputs, downstream stories must not assume all candidates have full five-stage artifacts.
- The story does not explicitly define what an accepted candidate must expose for the next epic beyond “save a fixture.”
Recommendation:
- Make `scoring_manifest.json` the single downstream handoff contract.
- Define the minimal accepted-candidate payload Epic 6 needs: candidate ID, decision, rating, gate outcomes, artifact refs, provenance hashes.
- Generate the Epic 6 fixture from that production contract, not as a separate bespoke schema.

## Overall Verdict
VERDICT: `REFINE`

## Recommended Changes
1. Replace the hardcoded gauntlet order with “configured Story 5.4 order, including short-circuit behavior.”
2. Remove direct `operator_actions.py` calls from the E2E proof path and drive operator actions through the pipeline API/skill boundary.
3. Add explicit coverage for the `refine` decision path, or remove `refine` from the acceptance criteria.
4. Expand hard-gate verification to include cost-stress survival, not just `PBO` and `DSR`.
5. Stop requiring full five-stage artifacts for every candidate; allow short-circuited RED candidates with truncated evidence packs.
6. Move upstream contract verification and Epic 6 fixture plumbing out of core acceptance criteria into QA/dev notes or a separate compatibility story.
7. Replace `AC13` with a real downstream handoff criterion based on the stable `scoring_manifest.json` contract.
8. Add a thin operator-visibility check for chart/deep-link evidence, or stop tracing this story to `FR25`.
9. Specify a concrete timeout/budget if wall-clock performance remains an acceptance criterion.
10. Consider splitting this into two stories: `happy-path integration proof` and `reproducibility/resume/provenance proof`.
