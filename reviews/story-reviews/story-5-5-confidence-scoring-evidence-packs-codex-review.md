# Story 5-5-confidence-scoring-evidence-packs: Story 5.5: Confidence Scoring & Evidence Packs — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-22
**Type:** Holistic System Alignment Review

---

**1. System Alignment**
- **Assessment:** CONCERN
- **Evidence:** [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L13), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L55), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L298), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L451), [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L83), [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L519)
- **Observations:** This clearly advances operator confidence and artifact completeness, and partly advances reproducibility through deterministic scoring. It only indirectly advances fidelity. It also contains two system-level contradictions: AC1 assumes a fully completed gauntlet, while the story later requires scoring short-circuited candidates; and it claims to be a “pure aggregation/presentation layer” while also adding population-level anomaly logic and visualization prep. That is more than V1 needs.
- **Recommendation:** Keep the gate-first scorecard and two-pass evidence pack. Reduce scope to deterministic aggregation of 5.4 outputs plus operator review. Move population-level anomaly logic and chart-data materialization out unless 5.4 explicitly publishes the required inputs.

**2. PRD Challenge**
- **Assessment:** CONCERN
- **Evidence:** [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L509), [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L517), [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L413), [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L569), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L78), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L155)
- **Observations:** FR34 and FR39 are the right problems. The overreach comes from pulling in FR16/17/25-style analysis behavior and a `delta_vs_baseline` field that looks more like Growth-phase refinement support than MVP. The real operator need is: “why did this candidate pass/fail, what are the top risks, and what exactly was the evidence?” Cross-candidate anomaly scoring for a tiny V1 candidate set looks like imagined sophistication.
- **Recommendation:** Re-decompose this story around three MVP jobs: immutable gate report, composite score with rationale, and reviewable evidence pack. Make `delta_vs_baseline` optional with an explicit baseline definition, or drop it from V1.

**3. Architecture Challenge**
- **Assessment:** CONCERN
- **Evidence:** [architecture](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L1123), [architecture](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L1126), [architecture](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L1606), [architecture](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L1812), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L260), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L288)
- **Observations:** The architecture is ambiguous about where FR34 lives. The architecture tree points at Rust `validator/confidence.rs`, while this story makes confidence scoring a Python analysis-stage concern. D9 also says skills should invoke the API/analysis layer, but Task 10 reads like the skill will load files and mutate evidence packs directly. That is unnecessary complexity and weakens boundary clarity.
- **Recommendation:** Pick one authority for scoring. For this story, Python is the simpler fit because it is light, deterministic aggregation over published artifacts. If that is the intent, update architecture references accordingly and keep the skill/API boundary consistent.

**4. Story Design**
- **Assessment:** CRITICAL
- **Evidence:** [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L13), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L205), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L217), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L251), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L275), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L446)
- **Observations:** The implementation contract is internally inconsistent. Task 8 both prepares chart JSON and only returns Arrow refs. Task 9 returns all evidence packs in memory while the anti-patterns forbid that. AC1 conflicts with short-circuited handling. “Review in under 60 seconds / 15 minutes” is not actually testable as written. The story boundary is too wide: scoring, anomaly system, narrative engine, visualization prep, pipeline integration, and operator review persistence.
- **Recommendation:** Tighten the ACs into verifiable contracts, remove contradictory tasks, and split or defer at least one of: population anomaly layer, visualization prep, or `/pipeline` review integration.

**5. Downstream Impact**
- **Assessment:** CONCERN
- **Evidence:** [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L79), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L186), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L247), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L265), [story](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/5-5-confidence-scoring-evidence-packs.md#L324), [epics](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1235), [epics](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L1372), [prd](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L552)
- **Observations:** The story does not fully protect reproducibility downstream. It snapshots thresholds, but provenance appears to use the gauntlet config hash, not a dedicated scoring config hash. It also omits Brief 3C/version provenance even though 5.5 depends on it. Mutating the evidence pack with operator decisions will blur immutable machine evidence and human review. Layer A population scoring is also a weak assumption when V1 only promotes top-N candidates.
- **Recommendation:** Add explicit scoring-config provenance, keep evidence packs immutable, store operator review as a separate append-only artifact, and require a minimum candidate count before any population-level anomaly logic is enabled.

## Overall Verdict
VERDICT: REFINE

## Recommended Changes
1. Rewrite AC1 so 5.5 accepts both fully completed and short-circuited gauntlet manifests, with explicit missing-stage handling.
2. Remove the “pure aggregation/presentation layer” claim unless Task 5 and Task 8 are cut back to manifest-only consumption.
3. Choose one visualization contract: either pass through `chart_data_refs` only, or require 5.4 to emit precomputed chart JSON. Do not specify both.
4. Add a dedicated `confidence_config_hash` and include Brief 3C / analysis-engine version provenance in `DecisionTrace` and artifact metadata.
5. Make the evidence pack immutable after scoring; persist operator decisions in a separate versioned review artifact instead of overwriting the pack.
6. Rename `/pipeline` → “Review Optimization Results” to something stage-accurate, preferably reusing the validation review path.
7. Replace the vague 60-second / 15-minute ACs with measurable proxies such as max fields, max words, required sections, and citation coverage.
8. Make `delta_vs_baseline` optional with a defined baseline source, or remove it from V1.
9. Resolve the Python-vs-Rust ownership of FR34 explicitly in the story notes so implementation does not drift from architecture.
10. Change the orchestrator contract to stream per-candidate persistence and return a summary manifest path, not an in-memory `list[ValidationEvidencePack]`.
11. Gate Layer A/B population anomaly logic behind an explicit minimum candidate count, or defer it to a later story.
12. Add a stable schema for the aggregate scoring manifest so Story 5.7 and the dashboard do not need a rewrite later.
