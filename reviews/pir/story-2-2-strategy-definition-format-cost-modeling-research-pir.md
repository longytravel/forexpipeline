# PIR: Story 2-2-strategy-definition-format-cost-modeling-research — Story 2.2: Strategy Definition Format & Cost Modeling Research

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-15
**Type:** Post-Implementation Review (final decision)

---

## Codex Assessment Summary

Codex rated Objective Alignment as STRONG, Simplification as ADEQUATE, Forward Look as ADEQUATE, with an overall OBSERVE verdict.

### 1. Fidelity is where the story adds the most value — quarantine interaction finding
**Codex:** Identifying that post-quarantine data systematically understates real execution cost is the critical finding. D13 extended with commission, provenance, and percentile fields.

**AGREE.** This is the single highest-value finding in the story. The quarantine interaction (Section 6.4) directly prevents a systematic optimism bias in all future backtests. Without this finding, every strategy evaluation would use cost models trained on sanitized data that excludes the exact spread conditions (news events, low liquidity, market opens) that cause real execution costs to spike. The commission correction caught by synthesis (0.35 → 0.70 pips round-trip, cascading to ~900 pips/year unmodeled costs) reinforces the fidelity value. This finding alone justifies the research story.

### 2. Operator confidence tension: commented TOML is not yet the non-coder evidence pack
**Codex:** TOML with comments satisfies FR11 better than Python classes, but the PRD envisions a non-coder summary — raw TOML is not that.

**AGREE, but correctly scoped.** The research artifact positions TOML as a *prerequisite* for operator reviewability (comments, diffability, section headers), not as the complete FR11 solution. Story 2.5 is explicitly tasked with "Operator review, diff, confirmation, version locking" — that's where the human-readable summary layer gets built. The build plan (Section 9) confirms this dependency. The research correctly identifies what the format must support (FR11 compatibility) without over-promising that the format alone satisfies FR11.

### 3. Dual-validator drift risk (Python Pydantic + Rust serde)
**Codex:** The three-layer validation introduces a future reproducibility/confidence risk if Python and Rust validators diverge.

**AGREE.** The artifact explicitly acknowledges this risk in Section 5 ("Two-validator maintenance burden — Python and Rust validators must be updated in lockstep when contracts change"). The shared contracts layer (Layer 3) is the proposed mitigation. Whether this mitigation is sufficient is measurable only after Stories 2.3 and 2.8 implement both sides. For V1 (where both validators are being built fresh against the same contracts), drift risk is minimal. The risk grows over time as the schema evolves. This is a legitimate item to watch.

### 4. Three-layer validation is the main complexity hotspot
**Codex:** Most schema refinements are cheap; the validation stack (definition-time Pydantic + load-time Rust serde + shared contracts) is where complexity concentrates.

**AGREE.** The three-layer approach is the most architecturally ambitious recommendation. However, it's defensible: Layer 1 (Python Pydantic) gives immediate feedback during AI-assisted generation (critical for FR9/FR10 workflow speed), Layer 2 (Rust serde) catches cross-artifact and data-dependent issues at job start, and Layer 3 (shared contracts) provides a single source of truth. The simpler alternative (Rust-only validation) would break the AI correction loop by deferring all errors to job start. Since this is a research recommendation (not implemented code), downstream stories can simplify if warranted.

### 5. Missing contract: no "validated raw" data interface for cost calibration
**Codex:** The artifact says the calibrator must use pre-quarantine raw data, but doesn't define the artifact/interface that preserves "validated raw" alongside sanitized bars.

**AGREE — this is the most significant forward gap.** The research correctly identifies WHAT the calibrator needs (pre-quarantine data with full spread distribution), but not WHERE it gets that data from. The current pipeline flow is: raw → validated → quarantine-excluded. The cost model calibrator needs to tap in at "validated but not quarantine-excluded" — but no artifact or interface provides that view today. Story 2.6 must define this boundary, and the Story 2.6 spec should be updated to make this explicit. Without it, the Story 2.6 implementer will need to discover this requirement independently, risking either: (a) using post-quarantine data (defeats the purpose), or (b) inventing an ad-hoc solution.

### 6. Missing operator-facing review format for Story 2.5
**Codex:** TOML is diffable but Story 2.5 still needs a formal summary/evidence artifact for the non-coder workflow.

**PARTIALLY AGREE.** The research establishes the necessary conditions (TOML supports comments, clean diffs, section headers) but the sufficient conditions (what the actual operator summary looks like) are correctly Story 2.5's scope. This is less of a gap than #5 because Story 2.5's AC already covers "operator can review without seeing code." The research provides the foundation; the implementation story defines the presentation.

### 7. Baked-in assumptions reasonable for V1
**Codex:** Dukascopy ECN as calibration base, session-only lookup abstraction, and validator sync across Python/Rust are baked-in assumptions.

**AGREE.** These assumptions are explicitly documented (Dukascopy in Section 6.1, session lookup in Section 6.2, validator sync in Section 5) with known limitations called out. The Dukascopy ECN bias (20-30% tighter than retail) is documented with the `data_source` provenance field specifically designed to make this visible. Session-only lookup is the right V1 abstraction — continuous time-of-day curves are explicitly deferred. All three assumptions are reasonable for V1 and correctly flagged for future review.

---

## Objective Alignment
**Rating:** STRONG

This story serves all four system objectives:

- **Reproducibility:** TOML format with `version`, `config_hash`, and `cost_model_reference` directly serves FR12 (constrained, versioned, reproducible specs) and FR58 (versioned artifact at every stage). The cost model artifact includes `schema_version`, `data_range`, and `calibration_method` for full provenance tracking. Deterministic TOML parsing (no implicit type coercion, per D7) supports FR18 and FR61.

- **Operator confidence:** TOML's human-readability, comment support, and diffability establish the prerequisites for FR11. The format comparison matrix (Section 3.5) explicitly scores operator reviewability as a 15%-weighted criterion. The research correctly identifies that TOML is the foundation, not the complete operator experience — Story 2.5 builds on this. The cost model's commission quantification (~900 pips/year unmodeled in baseline) gives the operator concrete evidence of what the system catches that the baseline misses.

- **Artifact completeness:** 10-section research artifact with decision records, comparison matrices, concrete TOML and JSON schema examples, session-aware cost profile methodology, and a per-story build plan for 2.3-2.9. Validated by 47 tests (including 7 regression tests added during synthesis). The dual-review process (BMAD + Codex) caught 4 substantive errors (matrix arithmetic, commission calculation, two missing decision record sections) — all fixed with regression tests.

- **Fidelity:** The quarantine interaction finding (Section 6.4) is the story's crown jewel. It prevents systematic optimism bias in cost modeling by requiring pre-quarantine raw data for calibration. The D13 schema extension (percentiles p95/p99, commission, provenance) transforms the cost model from a simple mean/std lookup into a distribution-aware artifact that reflects real market conditions. The ~900 pips/year unmodeled cost quantification (Section 7.6) makes the fidelity case concrete and undeniable.

---

## Simplification
**Rating:** ADEQUATE

- **Appropriately scoped:** The artifact is ~4,500 words within the 3,000-5,000 target. Four format options evaluated (TOML, JSON, DSL, Hybrid), two hard-rejected with clear rationale citing D10. No production code written. No architecture files modified.

- **D13 refinements are additive and cheap:** Commission, provenance, percentiles, and sample_count fields are computed once during calibration and cost nothing in runtime or storage. They provide significant fidelity and debuggability value at near-zero implementation cost.

- **Complexity concern — three-layer validation:** The recommended three-layer validation (Pydantic definition-time + Rust load-time + shared contracts) is the most architecturally ambitious output. Codex's observation about the simpler alternative (Rust as sole authoritative validator, Python as thin preflight) is reasonable. However, the research artifact properly documents the tradeoff: single-layer runtime validation breaks the AI generation correction loop (FR9/FR10), which is a core workflow. The three-layer recommendation is defensible as the research output; downstream stories can scope down if implementation reveals the shared contracts layer is unnecessary.

- **No dead work:** Every section maps to at least one AC. The build plan ties each recommendation to a specific downstream consumer. The synthesis report confirms no findings about over-engineering or unnecessary content.

---

## Forward Look
**Rating:** ADEQUATE

**Strong forward elements:**
- Explicit per-story dependency map in Section 9 (2.3 gets TOML contracts, 2.6 gets calibration methodology, 2.7 gets load/query API shape, 2.8 gets parser + indicator porting)
- Cost model lineage hooks (`schema_version`, `data_source`, `data_range`, `calibration_method`) correctly set up FR22 live-update path
- Sprint status aligned — all dependent Epic 2 stories staged as `ready-for-dev`
- Zero downstream rewrite risk (TOML aligns with all existing architecture assumptions)

**Forward gaps to watch:**

1. **"Validated raw" data interface (affects Story 2.6).** The research mandates pre-quarantine data for cost calibration but doesn't specify how the calibrator accesses it. The current pipeline stages (download → validate → quality-check → convert) quarantine at the quality-check stage. Story 2.6 needs either: (a) an explicit "validated-not-quarantined" output from the quality checker, or (b) the ability to read the validated stage output before quarantine is applied. Story 2.6's spec should be checked for this requirement.

2. **Operator summary format (affects Story 2.5).** The research establishes TOML's prerequisites for FR11 but doesn't define the operator-facing summary shape. This is less urgent — Story 2.5's AC already covers it — but the Story 2.5 implementer should know that "diffable TOML" is the input, not the deliverable.

3. **Validator sync testing strategy.** The shared contracts (Story 2.3) and Rust validator (Story 2.8) need a cross-language conformance test suite to catch divergence. The research recommends shared contracts as the sync mechanism but doesn't specify how conformance is verified. Story 2.8 should include this in its testing plan.

---

## Observations for Future Stories

1. **Research stories should define data access interfaces, not just data requirements.** This story correctly identifies that the cost calibrator needs pre-quarantine data, but stops at "MUST consume pre-quarantine raw data" without specifying the pipeline stage/artifact/path that provides it. Future research stories that recommend cross-stage data flows should include at minimum: source stage, artifact format, and access pattern. This prevents downstream implementers from having to reverse-engineer the data flow.

2. **The synthesis process continues to demonstrate strong error-catching value.** The matrix arithmetic errors (three incorrect weighted totals) and commission half-counting (0.35 → 0.70 pips) are exactly the kind of errors that propagate silently through decision artifacts. The regression test pattern (extracting scores from the matrix, recomputing totals, asserting equality) is an effective innovation that should be standard for any research story containing quantitative claims.

3. **Decision record completeness degrades across sections.** Both reviewers found that Sections 5 and 7.3 were missing AC#10 elements (evidence sources, unresolved assumptions, downstream impact, known limitations) that Section 4 had. This is a fatigue pattern — the first decision record gets full treatment, subsequent ones get abbreviated. Future story specs should include a structural test (like `TestDecisionRecordCompleteness`) as a required deliverable, not just a synthesis-round addition.

4. **The quarantine interaction finding pattern should be actively sought in future research.** The most valuable finding in this story was not about the research topic (format selection) but about a cross-cutting pipeline interaction (quarantine excluding data the cost model needs). Future research stories should include a task: "Identify pipeline-stage interactions that could undermine the research output's assumptions." This is how research stories catch surprises that justify their existence.

5. **Dual-validator architectures need explicit conformance testing plans from the start.** The three-layer validation recommendation creates a maintenance obligation. Story 2.3 (which creates the shared contracts) should include conformance test infrastructure that Story 2.8 inherits. Without this, validator drift becomes a latent reproducibility risk that accumulates silently.

---

## Verdict

**VERDICT: OBSERVE**

Story 2.2 delivers strong research output that advances all four system objectives — especially fidelity (quarantine interaction finding, D13 schema extension) and artifact completeness (10-section artifact with decision records, validated by 47 tests). The TOML format selection is well-justified with concrete examples demonstrating all D10 minimum constructs. The cost model methodology is grounded in real pipeline data (Dukascopy M1 bid+ask), academic literature (3 cited references), and the critical insight that post-quarantine data systematically understates execution costs.

The synthesis process caught and fixed all four material errors (matrix arithmetic ×3, commission calculation ×1, missing decision record elements ×2) with regression tests — validating the dual-review pipeline's value.

Maintaining Codex's OBSERVE (rather than upgrading to ALIGNED) because two forward contract gaps deserve tracking:

1. **The "validated raw" data interface** is undefined — Story 2.6 needs this boundary specified, and the gap is non-obvious enough that it could be missed without explicit flagging.
2. **The dual-validator conformance testing strategy** is recommended but not planned — without it, the three-layer validation's drift risk grows silently.

Neither gap requires rework of this story's output. Both are actionable items for downstream story specs (2.6 and 2.3/2.8 respectively). The research artifact itself is thorough, well-structured, and operationally actionable — these are observations about what it sets up, not what it delivers.
