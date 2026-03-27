# Story 2-9-e2e-pipeline-proof-strategy-definition-cost-model: Story 2.9: E2E Pipeline Proof — Strategy Definition & Cost Model — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-15
**Type:** Holistic System Alignment Review

---

**1. System Alignment**
- Assessment: `CONCERN`
- Evidence: The story clearly advances reproducibility/versioning and artifact persistence through config hashes, manifests, crash-safe writes, logs, and saved fixtures ([story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L23), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L31), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L130), [PRD](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L99), [PRD](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L100)). But it says Story 2.9 proves only intent capture -> spec artifact and excludes evaluation/backtesting ([story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L155), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L218)), while Tasks 7-9 pull in Rust crate builds, parity, and “ready for backtesting” checks ([story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L97), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L107), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L119)).
- Observations: It advances `REPRODUCIBILITY` and `ARTIFACT COMPLETENESS` well, touches `OPERATOR CONFIDENCE` only partially, and barely touches `FIDELITY` beyond session-aware cost inputs. The main problem is not wrong direction; it is scope drift.
- Recommendation: Keep the golden-path proof, but trim this story to “operator intent -> locked spec -> cost artifact -> linked manifest/evidence.” Treat deeper Rust/parity/backtest-readiness checks as prerequisites or a separate smoke story.

**2. PRD Challenge**
- Assessment: `CONCERN`
- Evidence: The PRD still says FR10 is “generate executable strategy code” ([PRD](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L473)), while the architecture and story are explicitly spec-driven ([architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L625), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L155)). FR22 is about automatic updates from live reconciliation ([PRD](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L491), [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L823)), but this story only checks that three builder modes exist ([story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L94)).
- Observations: FR9/11/12/20/21/58/59/61 are the real fit. FR10 is misworded for the architecture you actually chose. FR22 is premature here. FR13 is also a bit over-specified for a proof story because it forces full optimization-plan structure before optimization exists.
- Recommendation: In the story, remap emphasis to FR9/11/12/20/21/58/59/61; note FR10 is satisfied via executable specification, not raw code; drop FR22 assertions from this proof.

**3. Architecture Challenge**
- Assessment: `CONCERN`
- Evidence: D3 requires the proof to follow real stage transitions with a JSON state file ([story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L152), [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L394)), but the tasks never verify `pipeline-state.json`, gate transitions, or resume behavior. Architecture also expects evidence packs at gates ([architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L761), [architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L771)), yet the story checks only summary text and logs ([story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L19), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L33)). The testing pyramid is 70/20/10 ([architecture](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L2010)), but this story expects a large cross-runtime suite ([story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L171)).
- Observations: D10, D13, and D14 are good choices for this domain. The issue is that the story bypasses the most important architectural behavior, which is the operator gate/state-machine path.
- Recommendation: Make the proof run through the real orchestrator/gate path, and reduce crate-specific checks to minimal smoke validation of published APIs.

**4. Story Design**
- Assessment: `CONCERN`
- Evidence: Several ACs are not objectively testable: “readable summary matching the dialogue intent,” “suitable for operator who has never seen code,” and “ready for backtesting” ([story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L19), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L31), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L71)). The prompt says “moving average crossover,” but AC2 hardcodes MA+EMA as “correct” ([story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L15), [story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L17)). Story 2.4 requires defaults to be explicitly visible in review ([epics](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md#L716)), but this story does not assert that.
- Observations: The task breakdown misses deterministic rerun checks, evidence-pack artifact checks, manifest-history checks, and state-machine assertions. The modification prompt “try wider stops” is too vague for a stable expected diff.
- Recommendation: Tighten ACs to explicit artifacts and fields; define one exact modification; add rerun-determinism and default-disclosure checks; either split the story or clearly mark the Rust build/parity work as out of scope here.

**5. Downstream Impact**
- Assessment: `CONCERN`
- Evidence: Story 1.9 required reruns to produce identical hashes ([epics](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md#L616)); Story 2.9 does not. Story 2.5 requires manifest history and confirmation metadata ([epics](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md#L748)); Story 2.9 checks only config hash/lock status ([story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L79)). Task 9 links pair only, not timeframe/session-config/schema version ([story](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md#L125)).
- Observations: Downstream backtesting and reconciliation will need stronger linkage than “same pair.” They need spec version, schema version, dataset identity, timeframe, session schedule/config hash, and cost-model version/hash. “Canonical fixtures for all subsequent epic proofs” is risky if the schema evolves.
- Recommendation: Save schema-versioned contract fixtures, not timeless canon. Add linkage assertions for timeframe and session/config provenance now, or Epic 3 will have to retrofit them.

## Overall Verdict
VERDICT: `REFINE`

## Recommended Changes
1. Add an AC and task that rerunning the proof with identical dialogue/config/artifacts produces identical spec hash, manifest hash, and saved fixture hashes.
2. Replace ad-hoc E2E framing with an explicit requirement that the proof runs through the real D3 state machine and writes/updates `pipeline-state.json`.
3. Add an operator evidence-pack artifact check, not just summary text: summary, defaults used, diff, recommendation, and decision record.
4. Remove the FR22 “three input modes” assertion from this story, or move it to a lower-level Story 2.6 contract test.
5. Either split Tasks 7-9 into a separate compute-contract smoke story or demote them to prerequisite verification rather than core acceptance.
6. Make the modification deterministic; specify the exact field change, for example chandelier `atr_multiplier: 3.0 -> 4.0`.
7. Stop hardcoding MA+EMA as the only “correct” interpretation of “moving average crossover” unless the prompt itself is updated to say SMA/EMA; otherwise assert disclosed defaults.
8. Add manifest assertions from Story 2.5: version history, creation timestamp, operator confirmation timestamp, locked status, config hash.
9. Expand artifact linkage checks to include timeframe, schema version, session/config hash, and cost-model hash/version, not pair only.
10. Replace “canonical fixtures for all subsequent epic pipeline proofs” with schema-versioned reference fixtures scoped to Epic 2.
11. Tighten the structured-logging AC to required events/fields/correlation IDs instead of “present and correctly formatted.”
12. Add an anti-pattern forbidding hidden defaults and another forbidding bypassing the production orchestrator/gate path in the proof.
