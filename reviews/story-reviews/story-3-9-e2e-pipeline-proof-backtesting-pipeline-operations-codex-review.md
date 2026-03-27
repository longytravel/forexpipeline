# Story 3-9-e2e-pipeline-proof-backtesting-pipeline-operations: Story 3.9: E2E Pipeline Proof — Backtesting & Pipeline Operations — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-18
**Type:** Holistic System Alignment Review

---

**1. System Alignment**
- **Assessment:** CONCERN
- **Evidence:** The story strongly advances reproducibility and artifact completeness through deterministic reruns, manifest linkage, and persisted fixtures ([story AC9-12](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-9-e2e-pipeline-proof-backtesting-pipeline-operations.md#L31), [PRD pipeline completeness/reproducibility](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L99), [architecture cross-cutting reproducibility](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L80)). It only partially advances operator confidence because PRD says visual evidence and dashboard review are MVP-required ([PRD](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L293), [PRD FR62-FR65](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L558)), but the story validates JSON artifacts and status calls, not the visual review path. It barely touches fidelity; that objective lives in reconciliation and attribution, not this proof.
- **Observations:** The core outcome is right for Epic 3: prove the backtest slice before optimization. The overreach is in how much gets packed into one proof: happy-path E2E, deterministic regression, checkpoint recovery, log audit, and downstream fixture publication. Task 1.7 also works against the system’s “explicit config, no implicit drift” principle by proposing edits to `config/base.toml` during test setup ([story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-9-e2e-pipeline-proof-backtesting-pipeline-operations.md#L52), [PRD](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L191)).
- **Recommendation:** Keep the story as the Epic 3 vertical-slice proof, but narrow it to one official operator-facing happy path plus reproducibility. Move config setup to a test-local overlay, and either add a minimum dashboard verification or explicitly state that visual review is deferred and this is not yet full operator-confidence proof.

**2. PRD Challenge**
- **Assessment:** CONCERN
- **Evidence:** FR16 requires chart-first review, FR39/FR40 require coherent evidence and status “what passed, what failed, and why,” and FR41/FR42 require no profitability gate and resume support ([PRD FR16-FR18](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L482), [PRD FR38-FR42](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L516)). The story checks accept-path advancement and status shape, but not the visual/chart-first requirement and not much of the “why/failed/blocking” dimension. It also pulls NFR5 into backtest resume even though PRD states NFR5 specifically for long-running optimization runs ([PRD](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L605)).
- **Observations:** The real problem is “can the operator trust and advance a reviewed backtest run?” The story spends too much space on internal representation details like exact JSON field lists, file names, and fixture copying, which are contract-test concerns, not operator concerns. Requirement decomposition would be cleaner as: operator proof, artifact contract proof, and resilience proof.
- **Recommendation:** Reframe the story around operator trust outcomes. Push schema-shape assertions down into Stories 3.6/3.7 contract tests, clarify whether checkpointing is a generic batch requirement or optimization-specific, and add explicit coverage for chart-first evidence or stop claiming FR16 is satisfied here.

**3. Architecture Challenge**
- **Assessment:** CONCERN
- **Evidence:** D1, D2, D3, and D11 are well matched to this story. The main mismatch is D9: architecture says Claude Code skills invoke the REST API for pipeline control ([architecture D9](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L569), [analysis via REST](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L807)), but the story’s proof path calls `operator_actions.*` directly while claiming `/pipeline` review and advancement ([story AC7](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-9-e2e-pipeline-proof-backtesting-pipeline-operations.md#L27), [story tasks 6.2-6.4](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-9-e2e-pipeline-proof-backtesting-pipeline-operations.md#L119)).
- **Observations:** The stack is not the problem. The seam being tested is. Right now this proves an internal Python integration surface, not the architected operator boundary. That lowers confidence that the real operator path works end-to-end.
- **Recommendation:** Pick one official boundary for this proof and be consistent. If `/pipeline` is the product boundary, test it. If REST API is the automation boundary, test that and stop claiming skill-level E2E. Keep D1/D2/D3; reduce complexity by moving WAL/log/schema detail checks to lower-level suites.

**4. Story Design**
- **Assessment:** CRITICAL
- **Evidence:** The story contradicts itself on determinism: AC9 requires the “same manifest hash” ([story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-9-e2e-pipeline-proof-backtesting-pipeline-operations.md#L31)), while Task 7.4 excludes `run_id` and timestamps from manifest comparison ([story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-9-e2e-pipeline-proof-backtesting-pipeline-operations.md#L138)). It also drifts from upstream contracts: Story 3.6 names `results.arrow`, `equity-curve.arrow`, `trade-log.arrow` ([epics](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1018)), but this story expects `trade_log.arrow`, `equity_curve.arrow`, `metrics.arrow` ([story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-9-e2e-pipeline-proof-backtesting-pipeline-operations.md#L77)). Story 3.7 saves `narrative.json` ([epics](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1052)), while this story expects `evidence_pack.json` ([story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-9-e2e-pipeline-proof-backtesting-pipeline-operations.md#L101)).
- **Observations:** This is not implementation-ready as written. “Likely filename” and “if section names differ, discover them” tasks are discovery work, not delivery work. The story also repeats a lot of component-level acceptance detail that should already be covered by 3.3/3.6/3.7 rather than testing the handoffs between them.
- **Recommendation:** Resolve the upstream contracts first, then rewrite this as an integration proof against fixed interfaces. Split happy-path proof from resilience/fixture publication, or at minimum separate them into distinct task groups with distinct pass criteria.

**5. Downstream Impact**
- **Assessment:** CONCERN
- **Evidence:** AC12 and Task 10 make this run the reference for all future epic proofs ([story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-9-e2e-pipeline-proof-backtesting-pipeline-operations.md#L37), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-9-e2e-pipeline-proof-backtesting-pipeline-operations.md#L166)). Architecture says reproducibility should hinge on config/data hashes and stable contracts, not incidental runtime fields ([architecture D7](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L501), [architecture reproducibility locations](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L1893)).
- **Observations:** Downstream stories need stable contract fixtures, not raw copied runtime outputs with volatile timestamps and run IDs. Freezing today’s inconsistent artifact names will create avoidable debt in Epic 4+. The current approach is likely to force rewrites when schemas or filenames are normalized.
- **Recommendation:** Publish sanitized reference fixtures with volatile fields stripped, schema versions pinned, and loader helpers defined. Make downstream epics depend on those contract fixtures, not on a copied runtime directory layout.

## Overall Verdict
VERDICT: REFINE

## Recommended Changes
1. Replace direct `operator_actions.*` proof steps with the actual architected boundary: `/pipeline` skill or REST API. Do not claim skill-level E2E while testing internal helpers.
2. Remove Task 1.7’s mutation of `config/base.toml`; use a test-local config overlay/fixture so reproducibility does not depend on editing global base config.
3. Fix the determinism contract: either compare a sanitized manifest or add a separate reproducibility hash. Do not require “same manifest hash” if `run_id` and timestamps are expected to differ.
4. Reconcile artifact contracts across Stories 3.6, 3.7, and 3.9: pick one canonical naming scheme for Arrow outputs and one canonical evidence-pack filename.
5. Replace discovery-language tasks (“likely filename”, “if names differ, discover”) with explicit prerequisite contracts or references to fixture manifests.
6. Trim component-level assertions from this story and keep the E2E focus on stage handoff, operator reviewability, and deterministic rerun.
7. Split checkpoint/resume fault-injection into a separate resilience proof or clearly isolate it from the main happy-path E2E run.
8. Add minimal MVP visual-evidence verification, or explicitly remove FR16/MVP dashboard claims from this story.
9. Either test reject/refine gate behavior here or narrow the story’s claim to accept-path validation only.
10. Change Task 10 from copying raw runtime artifacts to publishing stable reference fixtures with volatile fields stripped and schema versions pinned.
