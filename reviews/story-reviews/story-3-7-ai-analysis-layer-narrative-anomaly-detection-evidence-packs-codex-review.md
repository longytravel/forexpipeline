# Story 3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs: Story 3.7: AI Analysis Layer — Narrative, Anomaly Detection & Evidence Packs — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-17
**Type:** Holistic System Alignment Review

---

**1. System Alignment**  
Assessment: `CONCERN`  
Evidence: The story clearly serves chart-first review, anomaly flagging, and persisted stage artifacts ([prd.md#L155](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L155), [prd.md#L517](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L517), [3-7 story#L15](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L15), [3-7 story#L42](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L42)). It works against artifact completeness and operator confidence by allowing `review-pending` progression even if evidence-pack generation fails ([3-7 story#L126](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L126), [architecture.md#L85](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L85)).  
Observations:  
- It advances `operator confidence` and `artifact completeness` well enough.  
- It only weakly advances `reproducibility`; the pack is persisted, but provenance hashes/manifest linkage are not required in the ACs.  
- It barely touches `fidelity`; these are sanity checks, not divergence attribution/tolerance handling.  
- `Parameter sensitivity cliff` is overreach for a backtest-stage MVP story because it depends on optimization data and is already marked “skip gracefully if unavailable” ([3-7 story#L100](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L100)).  
Recommendation: Keep narrative + anomaly + evidence-pack assembly, but narrow 3.7 to backtest-stage review only. Do not let missing review artifacts behave like a valid gate output.

**2. PRD Challenge**  
Assessment: `CONCERN`  
Evidence: The PRD wants MVP chart-first review with anomalies and evidence packs ([prd.md#L117](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L117), [prd.md#L482](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L482), [prd.md#L483](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L483), [prd.md#L551](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L551)). It also explicitly keeps advanced analytics/refinement work for growth ([prd.md#L130](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L130), [prd.md#L411](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L411)).  
Observations:  
- FR16/17/39/58 are the right requirements for this story.  
- The operator’s real MVP need is a trustworthy review packet, not a bulky JSON dump of raw curve points.  
- The story is under-specified on visual review and recommendation support, even though the PRD says the dashboard is MVP-required ([prd.md#L293](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L293)).  
- The story is over-specified on threshold details in prose; those tolerances should be versioned config, not living only in documents.  
Recommendation: Reframe the requirement as “deterministic stage review packet with provenance + visual references,” and defer optimization-derived analytics to later stories.

**3. Architecture Challenge**  
Assessment: `CONCERN`  
Evidence: D11 defines the evidence pack as narrative + anomalies + metrics + chart URLs + recommendation ([architecture.md#L771](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L771)). The story instead embeds `equity_curve_data` and a trade-log path ([3-7 story#L37](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L37), [3-7 story#L70](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L70)). It also references `equity_curve.arrow` and `trades.arrow`, while Story 3.6 established `equity-curve.arrow` and `trade-log.arrow` ([3-7 story#L112](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L112), [3-7 story#L115](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L115), [epics.md#L1018](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1018)).  
Observations:  
- Python-only analysis is the right stack choice.  
- The artifact contract is drifting from both D11 and Story 3.6.  
- The story asks for `v{NNN}` output paths, but the documented `backtest_id` and `backtest_runs` schema do not expose artifact version resolution ([3-7 story#L58](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L58), [3-7 story#L187](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L187), [3-7 story#L193](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L193)).  
- Thresholds living in Markdown are architecturally weak for a system that claims explicit, reproducible tolerances.  
Recommendation: Make the evidence pack a thin, stable wrapper over canonical artifacts/manifest, fix filename/path contracts, and move anomaly thresholds into versioned config/contracts.

**4. Story Design**  
Assessment: `CONCERN`  
Evidence: AC6 says the pack is sufficient for accept/reject/refine decisions without raw data ([3-7 story#L47](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L47)), but the test only checks field presence ([3-7 story#L151](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L151)). The story also forbids unbounded memory ([3-7 story#L257](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L257)) while serializing full `equity_curve_data` into JSON ([3-7 story#L70](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L70)); architecture sizes one equity curve at ~125 MB ([architecture.md#L105](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L105)).  
Observations:  
- AC6 is not truly testable.  
- AC8 is an implementation-shape assertion, not a user-facing acceptance criterion ([3-7 story#L57](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L57)).  
- `NarrativeResult.metrics` and top-level `EvidencePack.metrics` duplicate the same concept and can drift ([3-7 story#L67](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L67), [3-7 story#L70](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L70)).  
- The narrative is supposed to be “chart-first,” but the narrative task does not clearly consume the equity-curve artifact; the pack assembler does.  
Recommendation: Replace AC6 with explicit measurable contents, demote AC8 to dev notes, add one shared metrics builder, and avoid full-curve JSON materialization.

**5. Downstream Impact**  
Assessment: `CRITICAL`  
Evidence: Story 3.8 and 3.9 rely on this artifact for review and progression ([epics.md#L1074](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1074), [epics.md#L1076](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1076), [epics.md#L1110](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1110)). This story changes `narrative.json` to `evidence_pack.json` and only notes that 3.8 should be updated ([epics.md#L1052](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1052), [3-7 story#L168](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L168), [3-7 story#L170](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md#L170)).  
Observations:  
- This will create downstream breakage unless the contract is updated in planning artifacts, not just in story notes.  
- Missing manifest/hash linkage now will force rework when later stages need consistent cross-stage evidence packs ([epics.md#L1024](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1024), [epics.md#L1106](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1106), [epics.md#L1114](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1114)).  
- Letting `review-pending` exist without a reviewable artifact breaks the operator gate pattern.  
- A backtest-specific pack shape without a generic envelope increases the chance of incompatible evidence artifacts in later epics.  
Recommendation: Lock the evidence-pack schema now, propagate filename/schema changes upstream, and require provenance + schema version so later stages can reuse the same gate contract.

## Overall Verdict
VERDICT: `REFINE`

## Recommended Changes
1. Remove `sensitivity_cliff` from Story 3.7, or explicitly move it to optimization/validation stories where neighboring parameter results exist.
2. Replace full `equity_curve_data` embedding with chart references, dashboard deep links, or a bounded/downsampled summary.
3. Fix artifact filename/path contracts to match Story 3.6, or update Story 3.6/3.8/3.9 together as one contract change.
4. Add explicit provenance fields to the acceptance criteria and models: manifest path, config hash, data hash, strategy spec version, cost model version, schema version.
5. Change failure semantics so anomaly flags remain non-blocking, but missing evidence packs do not silently advance as a valid review-ready stage.
6. Rewrite AC6 into measurable criteria instead of “enough information to decide.”
7. Demote AC8 from acceptance criteria into tasks/dev notes.
8. Add a single shared metrics builder so narrative, anomaly logic, and evidence pack cannot compute conflicting numbers.
9. Specify how `v{NNN}` is resolved from `backtest_id`, or require manifest lookup as the authoritative source.
10. Move anomaly thresholds from document prose into versioned config/contracts so they are explicit, hashable, and reproducible.
11. Add chart/recommendation fields so the story matches D11 and the PRD’s MVP visual-review requirement.
12. Update planning artifacts, not just this story, if `evidence_pack.json` is the new contract.
