# Story 2-4-strategy-intent-capture-dialogue-to-specification: Story 2.4: Strategy Intent Capture — Dialogue to Specification — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-15
**Type:** Holistic System Alignment Review

---

## 1. System Alignment
**Assessment:** CONCERN

**Evidence:** The story clearly advances reproducibility and artifact persistence by requiring schema validation, versioned saves, and logs in [2-4-strategy-intent-capture-dialogue-to-specification.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md#L15), [2-4-strategy-intent-capture-dialogue-to-specification.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md#L34), and [2-4-strategy-intent-capture-dialogue-to-specification.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md#L39). It also supports operator confidence in principle via defaults visibility and a skill-driven flow in [2-4-strategy-intent-capture-dialogue-to-specification.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md#L23) and [2-4-strategy-intent-capture-dialogue-to-specification.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md#L140). But the PRD’s V1 emphasis is “same inputs -> same outputs” and evidence-backed operator review, not parser cleverness [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L100), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L189), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L83).

**Observations:** The story does not materially advance fidelity yet. More importantly, some parts work against reproducibility and operator confidence: silent strategy-shaping defaults, `"pending"` cost model references, and auto-generated optimization plans from vague dialogue create artifacts that look precise without being trustworthy. The V1 scope is mostly right, but the story is overreaching by trying to solve intent capture, default policy, optimization-plan generation, artifact versioning, and operator-facing summary behavior in one unit.

**Recommendation:** Keep the core goal, but simplify. For V1, prefer `dialogue -> structured draft intent -> validated draft spec` with explicit provenance for each field (`operator`, `default`, `inferred`). Leave optimization-plan authoring and rich summary behavior to later or to Story 2.5.

## 2. PRD Challenge
**Assessment:** CONCERN

**Evidence:** The story maps to FR9/FR10/FR12/FR38, but FR11 belongs to the next review step [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L472), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L474), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L475), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L516). The PRD journey says the system asks clarifying questions before taking over [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L151), but this story defaults missing fields instead of defining when clarification is mandatory.

**Observations:** The real operator need is not “parse anything”; it is “capture intent safely enough that I trust the resulting spec.” The story is under-specified on clarification rules and over-specified on parser heuristics and default strategy semantics. Defaulting pair/timeframe/risk/SL/TP may solve convenience, but it can also fabricate a different strategy than the operator intended.

**Recommendation:** Reframe the requirement decomposition. Critical omissions that change strategy identity should trigger clarification; low-risk omissions can default. Add an explicit rule table for `must ask`, `may default`, and `must fail`. That serves the PRD better than more alias mappings.

## 3. Architecture Challenge
**Assessment:** CRITICAL

**Evidence:** The story misstates architecture decisions. It labels `D5` as reproducibility, but architecture `D5` is process supervision via NSSM [2-4-strategy-intent-capture-dialogue-to-specification.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md#L174), [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L453). It labels `D12` as SQLite artifact coordination, but `D12` is reconciliation data flow [2-4-strategy-intent-capture-dialogue-to-specification.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md#L180), [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L823). It creates `contracts/strategy_defaults.toml`, while architecture says shared defaults live in `config/base.toml` and every config key must exist there [2-4-strategy-intent-capture-dialogue-to-specification.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md#L64), [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L1292), [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L1512). It also has the skill call Python directly, while D9 says skills invoke the REST API for control/mutations [2-4-strategy-intent-capture-dialogue-to-specification.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md#L142), [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L571), [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L607).

**Observations:** The stack choice is fine: deterministic parsing in Python is appropriate. The problem is boundary drift. The story is building its own mini-architecture instead of following the documented one. It also confuses `config_hash` with spec/content hashing by routing it through `compute_spec_hash()` and saying the hash changes due to timestamps [2-4-strategy-intent-capture-dialogue-to-specification.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md#L121), [2-4-strategy-intent-capture-dialogue-to-specification.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md#L174). That is exactly the kind of traceability confusion this system cannot afford.

**Recommendation:** Fix the decision references first. Move defaults to config, not contracts. Put intent capture behind the orchestrator/API boundary or explicitly carve out why this story is a justified exception. Separate `config_hash`, `spec_hash`, and version metadata.

## 4. Story Design
**Assessment:** CONCERN

**Evidence:** The story says Python receives semi-structured input from the skill, not raw natural language [2-4-strategy-intent-capture-dialogue-to-specification.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md#L193), but the tests exercise raw NL strings like “Try an EMA strategy” [2-4-strategy-intent-capture-dialogue-to-specification.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md#L149). It also assigns Story 2.4 responsibilities that Story 2.5 is supposed to own, including human-readable review behavior and default visibility at review time [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L726), [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L736).

**Observations:** AC3 is not testable as written because “sensible defaults” is subjective. The task list is detailed, but it misses determinism tests, provenance/source attribution, clarification-loop behavior, and dependency on Stories 2.1/2.2 outputs even though the story itself references them [2-4-strategy-intent-capture-dialogue-to-specification.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md#L213). The story boundary is also muddy: part compiler, part operator UX, part policy engine.

**Recommendation:** Tighten the story around one deliverable: compile a normalized intent payload into a draft spec plus validation/provenance artifacts. Move review presentation and modification UX cleanly into Story 2.5. Add deterministic-output tests and a clarification/default policy matrix.

## 5. Downstream Impact
**Assessment:** CRITICAL

**Evidence:** Story 2.5 needs a readable summary, modification diffs, version history, and locked-state semantics [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L734), [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L742), [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L746). Story 2.8 expects an evaluable spec with valid indicator references and cost model linkage [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L812). But 2.4 currently allows placeholder `"pending"` for `cost_model_reference` and auto-populates optimization plans [2-4-strategy-intent-capture-dialogue-to-specification.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md#L111), while Story 2.3 says `cost_model_reference` must be a valid version string [epics.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L694).

**Observations:** The downstream contract is missing a provenance artifact. Without it, Story 2.5 will have to reverse-engineer “what came from the operator vs default vs inference,” and later refinement stories will struggle to make precise diffs. Hardcoded alias tables will also become technical debt as the strategy engine registry expands.

**Recommendation:** Make Story 2.4 emit a bundle, not just a spec: raw input transcript, normalized intent payload, provenance/default map, validation report, and draft spec artifact. Do not invent fake cost model references or speculative optimization plans.

## Overall Verdict
VERDICT: REFINE

## Recommended Changes
1. Correct the architecture references in the story: `D5`, `D12`, and any hash-related notes are currently wrong.
2. Replace `contracts/strategy_defaults.toml` with configuration under `config/base.toml` or another config-layer file consistent with `D7`.
3. Define a mandatory clarification policy for strategy-defining omissions instead of defaulting everything.
4. Remove or defer automatic `optimization_plan` generation from this story.
5. Remove the `"pending"` `cost_model_reference` placeholder; use an explicit unresolved state outside the final evaluable spec or require a real reference later.
6. Split hash concepts explicitly into `config_hash`, `spec_hash`, and artifact version; stop implying timestamps should change a config hash.
7. Add a provenance artifact that records each spec field as `operator`, `default`, or `inferred`.
8. Narrow Story 2.4 to producing a draft spec and validation bundle; leave human-readable review/confirmation behavior to Story 2.5.
9. Align the input contract: either Python parses normalized semi-structured input, or it parses raw natural language, but the story and tests must agree.
10. Add deterministic tests that prove the same normalized input and config produce the same canonical spec payload.
11. Add explicit dependency/gating on Stories 2.1 and 2.2 outputs if parser vocabulary and format choices still rely on their findings.
12. Route the skill through the documented orchestration boundary, or explicitly document why direct Python invocation is acceptable here.
