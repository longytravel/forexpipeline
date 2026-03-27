# Story 2-3-strategy-specification-schema-contracts: Story 2.3: Strategy Specification Schema & Contracts — Holistic System Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-15
**Type:** Holistic System Alignment Review

---

**1. System Alignment**
- **Assessment:** CONCERN
- **Evidence:** [PRD scope](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L58), [PRD FR12-FR18](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L475), [Story 2.3 ACs](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-3-strategy-specification-schema-contracts.md#L13), [Epic 2.5](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L726)
- **Observations:** This story strongly advances reproducibility and artifact completeness, and it partially supports operator confidence by enforcing machine-valid specs. It barely touches fidelity directly. It also works against reproducibility by creating three likely sources of truth: TOML contract, Pydantic models, and a Python indicator registry, while [Story 2.8](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L802) adds a Rust parser/registry. It overreaches V1 by hardcoding multi-pair growth paths and by taking on versioning/locking-adjacent behavior that Epic 2.5 already owns.
- **Recommendation:** Narrow 2.3 to schema contract, preflight validation, and reference fixtures. Treat lock/version history/diff as 2.5 concerns and runtime evaluability/registry as 2.8 concerns.

**2. PRD Challenge**
- **Assessment:** CONCERN
- **Evidence:** [PRD FR12-FR13](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L475), [PRD FR58-FR61](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L551), [Epic mapping](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L249), [Story tasks](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-3-strategy-specification-schema-contracts.md#L120)
- **Observations:** FR12 and FR13 are the right problems. The problem is decomposition: the story pulls in FR59-style config linkage and artifact persistence mechanics early, even though epics map full artifact management and deterministic behavior to Epic 3, and 2.5 explicitly owns confirmed/locked version history. The operator’s real need is “I can trust the spec and understand what will run”; 2.3 mostly serves developer-facing structure, not operator-facing confidence.
- **Recommendation:** Reframe 2.3 as “make specs valid and portable,” not “solve strategy lifecycle.” Keep FR12/13 here; move lock/version history/config-hash finalization to 2.5, and keep full artifact-management semantics aligned with Epic 3.

**3. Architecture Challenge**
- **Assessment:** CONCERN
- **Evidence:** [Architecture D10](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L625), [Architecture contract fields](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L641), [Story schema task](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-3-strategy-specification-schema-contracts.md#L76), [Architecture structure](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L1572), [Architecture FR12 mapping](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L1949)
- **Observations:** The story hardcodes TOML/Pydantic shape even though D10 says the exact format is Phase 0 research-dependent. More importantly, D10 lists `session, regime, day_of_week` filters, but the story implements `session, volatility, day_of_week`; that is a direct contract mismatch. The architecture also expects contracts to be the shared boundary and the Rust `strategy_engine` to own evaluability, yet 2.3 duplicates semantic validation and registry logic in Python.
- **Recommendation:** Align the story exactly to D10’s agreed interface, or update D10 first. Keep Python as thin gatekeeping around the shared contract; do not let Python and Rust each invent separate semantic truth.

**4. Story Design**
- **Assessment:** CONCERN
- **Evidence:** [Story ACs](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-3-strategy-specification-schema-contracts.md#L11), [Task 7 registry](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-3-strategy-specification-schema-contracts.md#L130), [Task 8 sample spec](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-3-strategy-specification-schema-contracts.md#L139), [Epic 2.9 example](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L838)
- **Observations:** The ACs are directionally testable, but several are not implementation-tight enough. “Supports minimum representable constructs” needs fixture-based proofs, not prose. The story says the registry must be data-driven and extensible without code changes, then defines a hardcoded `KNOWN_INDICATORS` dict. The MA crossover reference spec conflicts with Epic 2.9’s canonical example: London+NY plus 2x ATR/3:1 TP here vs London-only and 3x ATR chandelier there.
- **Recommendation:** Convert vague ACs into contract tests with positive and negative fixtures. Remove contradictions in registry design. Pick one canonical reference strategy and use it across 2.3, 2.4, 2.5, and 2.9.

**5. Downstream Impact**
- **Assessment:** CONCERN
- **Evidence:** [Story dependencies](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-3-strategy-specification-schema-contracts.md#L221), [Epic 2.4](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L702), [Epic 2.5](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L734), [Epic 2.8](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/epics.md#L810)
- **Observations:** Downstream stories need a stable schema, canonical serialization, predictable error taxonomy, and a shared understanding of indicator/filter semantics. This story does not define `schema_version`, migration expectations, or a shared registry source, so future contract changes will likely force rewrites in 2.4, 2.5, and 2.8. `cost_model_reference` as only `v001` is also weak for future multi-pair growth.
- **Recommendation:** Add explicit downstream outputs: canonical schema version, valid/invalid fixture set, error contract, and a shared registry source or registry artifact. Strengthen `cost_model_reference` semantics before later epics depend on it.

## Overall Verdict
VERDICT: REFINE

## Recommended Changes
1. Re-scope Story 2.3 so its core deliverable is the spec contract, validation rules, and reference fixtures; move operator-facing lock/version history/diff behavior to Story 2.5.
2. Resolve the D10 mismatch by choosing one filter vocabulary and using it consistently everywhere: `regime` or `volatility`, not both.
3. Replace hardcoded growth-oriented enums like `EURUSD|GBPUSD|...` with values sourced from Story 2.2 research or config; keep V1 defaults aligned to one pair/timeframe.
4. Remove ownership of the indicator registry from 2.3, or make it a shared artifact sourced from Story 2.1 that both Python and Rust consume.
5. Add `schema_version` to the strategy spec contract and require canonical serialization rules for cross-runtime stability.
6. Clarify `config_hash` semantics and when it becomes mandatory; if it is only meaningful for a locked artifact, make it a 2.5 requirement rather than a 2.3 schema requirement.
7. Add contract tests based on fixture files for every minimum representable construct, plus negative fixtures for expected validation failures.
8. Make the MA crossover reference spec identical across Story 2.3 and Epic 2.9.
9. If versioning utilities remain in 2.3, state explicitly that they are persistence primitives only; confirmation, locking, version history, and diff summaries remain owned by 2.5.
10. Add an anti-pattern warning against schema drift between `contracts/strategy_specification.toml`, Python validation, and the later Rust `strategy_engine` parser.
