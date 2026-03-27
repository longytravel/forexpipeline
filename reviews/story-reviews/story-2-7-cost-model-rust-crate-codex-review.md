# Story 2-7-cost-model-rust-crate: Story 2.7: Cost Model Rust Crate — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-15
**Type:** Holistic System Alignment Review

---

**1. System Alignment**
- **Assessment:** CONCERN
- **Evidence:** The story clearly advances session-aware cost application and hot-path consumption ([story:13](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md:13), [story:28](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md:28), [prd:480](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md:480), [prd:489](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md:489), [arch:901](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md:901)). But Task 1 expands into bootstrapping the whole Rust workspace and future crates ([story:55](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md:55)) despite the MVP philosophy being “build only what’s genuinely missing” ([prd:354](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md:354)).
- **Observations:** This helps reproducibility and fidelity. It only lightly helps operator confidence via CLI inspection, and it barely touches artifact completeness. The strongest misalignment is scope creep: a focused cost-model library story is being used to stand up `optimizer`, `validator`, `live_daemon`, and `cost_calibrator` scaffolding. The hardcoded `pip_value = 0.0001` also works against fidelity unless the story explicitly rejects non-EURUSD artifacts ([story:174](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md:174)).
- **Recommendation:** Keep the library; shrink the story boundary. Either make this story `cost_model` plus the minimum workspace bootstrap, or split bootstrap out. Add an explicit V1 guard: only EURUSD is supported, fail loud otherwise.

**2. PRD Challenge**
- **Assessment:** ADEQUATE
- **Evidence:** FR20-FR21 are the right requirements for this story ([prd:489](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md:489), [prd:490](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md:490)); FR22 is a later feedback-loop concern ([prd:491](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md:491), [epics:764](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md:764)).
- **Observations:** The PRD is asking for a real thing, not an imagined one: session-aware costs are core to fidelity. The gap is not the FRs; it is the missing contract around fill semantics. The PRD says MT5 fill semantics must be modeled accurately ([prd:226](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md:226)), but the story never defines what `fill_price` means before spread/slippage are applied. Also, the PRD’s traceability goals ([prd:551](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md:551), [prd:554](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md:554)) are only partly reflected: validation covers pair/version/sessions, but not provenance fields like `source` and `calibrated_at`.
- **Recommendation:** Keep FR20-FR21 as-is, but add a requirement note to this story defining pre-cost fill semantics and provenance validation. Explicitly mark FR22 out of scope here.

**3. Architecture Challenge**
- **Assessment:** CONCERN
- **Evidence:** D13 says the library is wrapped by a thin calibration CLI and the architecture allocates that to `crates/cost_calibrator/` ([arch:903](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md:903), [arch:1066](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md:1066), [arch:1677](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md:1677)). The story instead puts `cost_model_cli` inside `cost_model` and redefines it as validate/inspect-only ([story:103](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md:103)).
- **Observations:** That is a direct story/architecture mismatch. Also, `HashMap<String, CostProfile>` is an unnecessarily loose hot-path representation for five fixed sessions ([story:20](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md:20), [story:94](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md:94)). A typed session enum or fixed lookup table would better fit D13’s performance intent. Finally, `metadata: Option<Value>` weakens the “artifact JSON is the contract” stance ([story:68](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md:68), [story:187](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md:187)).
- **Recommendation:** Resolve the D13 contradiction before implementation. Either change the story to use a separate `cost_calibrator` crate stub, or amend architecture so inline validate/inspect is the approved V1 design. Internally, prefer typed session keys over string hashing in the hot path.

**4. Story Design**
- **Assessment:** CONCERN
- **Evidence:** AC4 and Task 4 define `apply_cost(fill_price, session, direction)` but never define whether `fill_price` is mid, bid, ask, or pre-cost synthetic fill ([story:28](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md:28), [story:95](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md:95)). The story also says the JSON contract must “match exactly” ([story:187](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md:187)) but the tasks never require rejecting unknown fields.
- **Observations:** The ACs are unit-testable, but not system-verifiable enough for fidelity. The anti-patterns are good, but they miss the most dangerous real-world mistake here: double-counting or miscounting spread because fill semantics are ambiguous. The task list is too heavy on workspace scaffolding and too light on cross-runtime contract tests against Story 2.6 output.
- **Recommendation:** Add ACs for fill-price semantics, unknown-field rejection, provenance-field validation, and loading the real default artifact fixture from Story 2.6. Move unrelated workspace scaffolding out or reduce it sharply.

**5. Downstream Impact**
- **Assessment:** CONCERN
- **Evidence:** Story 2.8 will cross-validate `cost_model_reference` through this crate ([story:214](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md:214), [epics:822](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md:822)); Story 2.9 depends on successful artifact loading ([story:215](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md:215), [epics:848](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/epics.md:848)); Epic 3 will use `apply_cost()` in the hot path ([story:216](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/2-7-cost-model-rust-crate.md:216), [arch:1001](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md:1001)).
- **Observations:** If pair handling stays implicit, Epic 3 either inherits an EURUSD-only assumption silently or takes an API break later. If validation stays permissive, Story 2.8/2.9 will be where schema drift finally surfaces. If CLI output is only console text, later evidence-pack workflows will need retrofitting.
- **Recommendation:** Make the crate’s downstream contract explicit now: supported pairs, pip semantics, strict schema behavior, and structured validation output. That reduces rewrite risk in Epics 2.8, 2.9, and 3.

## Overall Verdict
VERDICT: REFINE

## Recommended Changes
1. Narrow Task 1 so this story bootstraps only `cost_model` plus the minimum required workspace pieces, or split workspace bootstrap into a separate foundational story.
2. Resolve the D13 mismatch: either move the CLI concern to `crates/cost_calibrator` or explicitly amend architecture to allow inline `cost_model_cli` for V1.
3. Add an acceptance criterion defining what `fill_price` represents and whether spread is applied relative to mid, bid, or ask.
4. Add an acceptance criterion that V1 either supports only EURUSD and rejects other pairs, or derives `pip_value` from artifact data now.
5. Replace `HashMap<String, CostProfile>` in the hot path with a typed session enum/id or fixed lookup structure; if strings stay public, convert once at the boundary.
6. Strengthen schema validation to reject unknown fields, not just missing/invalid ones.
7. Validate provenance fields explicitly: `source` non-empty and `calibrated_at` valid RFC3339/ISO-8601.
8. Reconsider `metadata: Option<serde_json::Value>`; either define it in the contract or remove it from the core type.
9. Add contract tests that load the real/default Story 2.6 artifact fixture and prove Python/Rust compatibility.
10. Make CLI validation/inspection able to emit structured output or a saved report artifact for later operator evidence packs.
