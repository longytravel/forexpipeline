# Story Synthesis: 2-2-strategy-definition-format-cost-modeling-research

**Synthesizer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-15
**Codex Verdict:** REFINE → **Synthesis Verdict:** IMPROVED

---

## Codex Observations & Decisions

### 1. FR11 Operator Reviewability Missing from Evaluation Criteria
**Codex said:** The comparison criteria emphasize expressiveness, tooling, AI suitability, and Rust parseability, but not human reviewability/diffability — despite FR11 being core to operator confidence.
**Decision:** AGREE
**Reasoning:** FR11 is listed in the PRD Requirements table but has zero weight in the Decision Framework. For a non-coder operator, reviewability is a first-class concern, not an afterthought.
**Action:** Added "Operator reviewability & diffability (FR11)" as criterion #4 at 15% weight. Rebalanced: Rust parseability 25%, AI-generation 25%, Expressiveness 20%, Reviewability 15%, Tooling 15%. Also added to AC#3 comparison coverage and to the example matrix row.

### 2. Hybrid Expression-Language Option Conflicts with D10
**Codex said:** The optional hybrid expression-language path reintroduces interpreter-like complexity, pushing against D10's constrained rule-engine model.
**Decision:** AGREE
**Reasoning:** D10 explicitly states "Evaluator is rule engine, not general-purpose interpreter." The hybrid option is worth investigating only as a last resort if simpler options can't represent D10 minimum constructs.
**Action:** Reframed Task 2 Option D as "architecture-exception path" with explicit note that it conflicts with D10 and requires architecture-change justification if recommended. Added anti-pattern #12 codifying this.

### 3. FR22 Scope Creep — Live Auto-Update Methodology
**Codex said:** FR22 is mapped to a later reconciliation epic, but Story 2.2 pulls it directly into research scope.
**Decision:** AGREE
**Reasoning:** FR22's full auto-update methodology belongs in the reconciliation epic. This story should only define artifact versioning fields and calibration interface hooks so the format supports future updates without restructuring.
**Action:** Updated AC#2 source reference to clarify "FR22 scoped to calibration hooks only." Added Task 3 subtask for calibration hooks with explicit note: "Do NOT design full auto-update methodology." Removed FR22 from direct scope.

### 4. Architecture Not Actually Format-Neutral — Fake Optionality
**Codex said:** D7, D10, and downstream stories already assume TOML, but Story 2.2 pretends format neutrality. This creates fake optionality.
**Decision:** PARTIALLY AGREE
**Reasoning:** The architecture does bias toward TOML, and pretending otherwise wastes research effort. However, genuine evaluation of alternatives has value — it either validates the assumption or surfaces a legitimate better option. The framing should be honest: "validate TOML-first hypothesis."
**Action:** Added a "Research framing" note to the Decision Framework: "Frame research as 'validate TOML-first hypothesis, evaluate alternatives as counterpoints.' If research recommends non-TOML, document downstream rewrite implications."

### 5. D13 Mean/Std Representation May Be Insufficient
**Codex said:** D13 may be under-specified for fidelity — the story asks whether extra fields are needed but doesn't force a decision on whether mean/std is even the right model shape.
**Decision:** AGREE
**Reasoning:** Mean/std assumes normally distributed costs. Spread spikes during news events have fat tails. The research should explicitly decide whether this matters for V1 fidelity or is an acceptable known limitation.
**Action:** Added new AC#11 requiring explicit decision on mean/std vs quantiles/tails with documented tradeoffs. Added corresponding Task 3 subtask.

### 6. Story 2.1 Dependency Path Is Wrong
**Codex said:** Task 1 references `strategy-evaluator-baseline-review.md` but the actual file is `2-1-claudebacktester-strategy-evaluator-review.md`.
**Decision:** AGREE
**Reasoning:** This is a factual bug. The path doesn't match the actual output file.
**Action:** Fixed the path to `_bmad-output/implementation-artifacts/2-1-claudebacktester-strategy-evaluator-review.md`.

### 7. ACs Verify Topic Coverage, Not Decision Quality
**Codex said:** ACs like "research covers..." don't ensure decision quality — they allow shallow research to pass.
**Decision:** AGREE
**Reasoning:** Research stories must produce decisions, not just coverage. The Story 2-1 pattern showed that explicit decision records (verdict tables) produced actionable output.
**Action:** Added new AC#10 requiring decision records with: chosen option, rejected options with reasons, evidence sources, unresolved assumptions, downstream contract impact, and known limitations. Added corresponding Task 4 subtask.

### 8. Word-Count Cap Too Restrictive
**Codex said:** The 2000-3000 word cap incentivizes superficial output while demanding two major research domains plus architecture refinements plus a build plan.
**Decision:** PARTIALLY AGREE
**Reasoning:** Some constraint prevents over-scoping, but two research domains with decision records genuinely need more space. The solution is to keep a concise executive summary with a longer evidence body.
**Action:** Relaxed to "Executive summary under 1000 words; full artifact including evidence sections target 3000-5000 words. Anything over 6000 words is over-scoped." Added note that artifact should have two independently reviewable sections.

### 9. Split Into Two Stories
**Codex said:** Strategy-format research and cost-model research are related but block different downstream stories. Should be two stories or two separately sign-off-able artifacts.
**Decision:** DISAGREE
**Reasoning:** For a one-person operator, the coordination overhead of splitting outweighs the benefit. The two domains are interrelated — format recommendation affects cost model artifact format (D13 JSON vs TOML choice flows from the strategy format decision). Two independently reviewable sections within one artifact is the right middle ground.
**Action:** Added stop condition note requiring two independently reviewable sections. Did not split the story.

### 10. Mark Story Blocked Until 2.1 Exists
**Codex said:** Mark story blocked until 2.1 artifact path is corrected or actual output exists.
**Decision:** DISAGREE
**Reasoning:** The path was wrong (fixed now), but the story's status is `ready-for-dev` which already implies the prerequisite story (2-1) has been completed. The issue was the file reference, not the dependency itself. Blocking is unnecessary once the path is corrected.
**Action:** Fixed the path (observation #6). No status change needed.

### 11. Story 2.5 Missing from Downstream Consumers
**Codex said:** Story 2.5 (Strategy Review & Diff) directly depends on format choice for diffability, but is not listed.
**Decision:** AGREE
**Reasoning:** Format diffability directly determines how Story 2.5 implements review/diff functionality. This is a clear omission.
**Action:** Added Story 2.5 to the downstream consumers list.

### 12. Required Outputs Not Explicit Enough
**Codex said:** Downstream stories need more specific outputs than currently guaranteed: parser constraints, schema invariants, summary/diff requirements, cost-model field decisions.
**Decision:** AGREE
**Reasoning:** The decision-record AC (#10) addresses most of this by requiring downstream contract impact documentation. The build plan confirmation (AC#9) covers per-story impact. Together these are sufficient without adding a separate required-outputs section that would duplicate AC content.
**Action:** Addressed via AC#10 (decision records with downstream impact) and Task 4 section 10 (downstream rewrite risk). No separate section added.

### 13. Cost Model Provenance Requirements
**Codex said:** Cost research should document data provenance: broker/account type, sample window, timezone/session mapping, calibration method.
**Decision:** AGREE
**Reasoning:** Without provenance, downstream stories (2.6, 2.7) may encode false precision. The operator needs to know what the cost numbers represent and their limitations.
**Action:** Added provenance to AC#2 ("data provenance: broker/account type, sample window, timezone/session mapping"). Added Task 3 subtask for documenting provenance per source.

### 14. FR10 Spec Generation vs Code Generation Clarification
**Codex said:** FR10's wording says "generate executable strategy code," but D10 steers toward executable specifications, not free-form code generation.
**Decision:** AGREE
**Reasoning:** This distinction matters for research framing — the format should optimize for structured data generation (high reliability) not code generation (low reliability).
**Action:** Added anti-pattern #11 clarifying this distinction.

### 15. Rewrite Risk Section in Research Artifact
**Codex said:** Require a "rewrite risk" section if the recommendation deviates from downstream assumptions.
**Decision:** AGREE
**Reasoning:** If research recommends non-TOML, Stories 2.3, 2.4, 2.8 would need rewriting. This should be quantified.
**Action:** Added section 10 "Downstream Rewrite Risk" to Task 4 artifact structure.

### 16. Replace "covers/includes" AC Language with Testable Quality Gates
**Codex said:** Replace vague AC language with decision-record ACs including minimum evidence provenance and source attribution.
**Decision:** PARTIALLY AGREE
**Reasoning:** AC#10 (decision records) addresses the quality-gate concern. Rewriting all existing ACs would be over-engineering — the existing "covers" language combined with the new decision-record AC creates a sufficient quality bar.
**Action:** Addressed via AC#10. Existing ACs retained but strengthened by new decision-record requirement.

---

## Changes Applied

1. **AC#2** — Added data provenance requirements; reframed FR22 to "calibration hooks only"
2. **AC#3** — Added "operator reviewability/diffability (FR11)" to comparison coverage
3. **ACs 7-9** — Reordered from 8,9,7 to correct sequential order 7,8,9
4. **AC#10 (NEW)** — Decision record requirement: chosen/rejected options, evidence, assumptions, downstream impact
5. **AC#11 (NEW)** — D13 mean/std sufficiency decision requirement
6. **Task 1** — Fixed 2.1 artifact path from `strategy-evaluator-baseline-review.md` to actual filename
7. **Task 2 Option D** — Reframed as "architecture-exception path" with D10 conflict warning
8. **Task 3** — Added mean/std vs quantiles subtask, provenance documentation subtask, FR22 calibration hooks subtask
9. **Task 4** — Added section 10 (Downstream Rewrite Risk) and decision-record subtask
10. **Decision Framework** — Added criterion #4 "Operator reviewability & diffability" at 15%; rebalanced weights; added TOML-first research framing note
11. **Example Matrix** — Added "Operator reviewability" row
12. **Stop Conditions** — Relaxed word cap to 3000-5000 (exec summary under 1000); added two-section reviewability note
13. **Anti-patterns** — Added #11 (FR10 spec vs code distinction) and #12 (DSL/hybrid as exception paths)
14. **Downstream Consumers** — Added Story 2.5 (Strategy Review & Diff)

## Deferred Items

- **Full FR22 auto-update methodology** — Deferred to reconciliation epic as documented in AC#2 reframe
- **Story splitting** — Codex suggested splitting into two stories; rejected for one-person operator coordination overhead; mitigated by two independently reviewable artifact sections

## Verdict
VERDICT: IMPROVED
