# Story 2-3-strategy-specification-schema-contracts: Story 2.3: Strategy Specification Schema & Contracts — Codex PIR

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-15
**Type:** Post-Implementation Review (alignment analysis)

---

**1. Objective Alignment**

Assessment: **STRONG**

Specific evidence:
- Reproducibility is materially improved by strict contract enforcement and deterministic persistence: unknown fields are forbidden in the Pydantic models, the loader validates TOML into a typed spec, hashing uses canonical sorted JSON plus SHA-256, and storage auto-versions with crash-safe writes and immutable prior versions. See [specification.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L37), [specification.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L324), [loader.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/loader.py#L23), [hasher.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/hasher.py#L29), [storage.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/storage.py#L43), [storage.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/storage.py#L53), [storage.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/storage.py#L58), [storage.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/storage.py#L64).
- It directly serves V1 scope rather than drifting beyond it: pair is constrained to `EURUSD`, timeframe is bounded, and the PRD explicitly says V1 is one strategy family on one pair/timeframe and is not gated on profitability. See [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L58), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L119), [strategy_specification.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/strategy_specification.toml#L12), [strategy_specification.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/strategy_specification.toml#L13), [specification.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L22).
- It helps operator confidence by making the spec human-readable TOML, providing a canonical reference artifact, and using collect-all-errors fail-loud validation rather than silent coercion. See [loader.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/loader.py#L4), [loader.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/loader.py#L171), [loader.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/loader.py#L179), [v001.toml](/c/Users/ROG/Projects/Forex%20Pipeline/artifacts/strategies/ma-crossover/v001.toml#L1), [test_live_strategy.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_strategy/test_live_strategy.py#L38).
- It supports fidelity indirectly by making the cost model reference explicit and by aligning the spec with the shared Rust strategy engine path expected downstream. See [strategy_specification.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/strategy_specification.toml#L142), [2-3-strategy-specification-schema-contracts.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-3-strategy-specification-schema-contracts.md#L199), [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L939).

Concrete observations:
- This story clearly advances `FR12`, `FR13`, `FR18`, `FR58`, and `FR61`; it gives the pipeline a constrained, versioned strategy artifact instead of ad hoc logic. See [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L475), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L476), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L484), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L551), [prd.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/prd.md#L554).
- The main thing working against operator confidence is that validation output is still developer-shaped stderr text, not structured operator evidence. Error codes were added, but the loader does not emit or persist them; it prints free-form messages and exits. See [error_codes.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/error_codes.toml#L15), [loader.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/loader.py#L171), [loader.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/loader.py#L179).
- Artifact completeness is only partial at this story boundary: the spec artifact is persisted, but the validation decision itself is not yet saved as a review artifact. That is consistent with the story’s own boundary, which defers operator-facing lifecycle and manifest records to Story 2.5. See [storage.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/storage.py#L3), [2-3-strategy-specification-schema-contracts.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-3-strategy-specification-schema-contracts.md#L205).

**2. Simplification**

Assessment: **ADEQUATE**

Specific evidence:
- The biggest redundancy is that the TOML contract declares itself the single source of truth, but Python does not derive validation from it; the schema is re-expressed manually as Literals and Pydantic fields. See [strategy_specification.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/strategy_specification.toml#L3), [strategy_specification.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/strategy_specification.toml#L4), [specification.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L22), [specification.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L23), [specification.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L30).
- `group_dependencies` is implemented as a mini string DSL (`"entry_timing -> exit_levels"`) rather than a structured object, which adds parsing/authoring friction for little V1 benefit. See [strategy_specification.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/strategy_specification.toml#L133), [strategy_specification.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/strategy_specification.toml#L134), [specification.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L278), [specification.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L286), [v001.toml](/c/Users/ROG/Projects/Forex%20Pipeline/artifacts/strategies/ma-crossover/v001.toml#L49).
- Error codes exist as a second mechanism, but there is no current consumer in this story’s runtime path. See [error_codes.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/error_codes.toml#L15), [loader.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/loader.py#L171).

Concrete observations:
- A simpler shape would have been either:
  1. truly drive Python/Rust validation from the contract, or
  2. keep the Pydantic schema as the executable truth for now and defer the separate TOML schema until Story 2.8.
- The current implementation is not wildly over-engineered for V1; versioning, hashing, registry loading, and crash-safe writes are all justified by the system objectives.
- The one area that feels more awkward than necessary is how crossover semantics are represented. The synthesis fix had to introduce `sma_crossover` as a special indicator because the base condition model only supports `indicator + numeric threshold`. That is pragmatic for V1, but it shows the contract is still a little indirect. See [synthesis-report.md](/c/Users/ROG/Projects/Forex%20Pipeline/reviews/synthesis/2-3-strategy-specification-schema-contracts-synthesis-report.md#L9), [strategy_specification.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/strategy_specification.toml#L26), [specification.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L66), [indicator_registry.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/indicator_registry.toml#L30).

**3. Forward Look**

Assessment: **ADEQUATE**

Specific evidence:
- The story sets up downstream Rust consumption correctly in one important place: the indicator registry is genuinely shared contract data loaded from `contracts/indicator_registry.toml`, matching the architecture’s cross-runtime intent. See [indicator_registry.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/indicator_registry.py#L20), [indicator_registry.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/indicator_registry.py#L40), [2-3-strategy-specification-schema-contracts.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-3-strategy-specification-schema-contracts.md#L138), [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L2120).
- The reference artifact is sufficient for the next slice: a real MA crossover spec exists, validates end to end, and matches the canonical example expected by later stories. See [v001.toml](/c/Users/ROG/Projects/Forex%20Pipeline/artifacts/strategies/ma-crossover/v001.toml#L14), [test_live_strategy.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/tests/test_strategy/test_live_strategy.py#L57).
- The main missing generality is optimization parameter addressing. Semantic validation only treats entry-condition params, confirmation params, and trailing-exit params as optimizable; stop-loss, take-profit, and filter params are excluded. See [loader.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/loader.py#L116), [loader.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/loader.py#L122), [loader.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/loader.py#L126).
- Reproducibility proof is not complete until later stories attach `config_hash` and manifest records; this story correctly leaves the slot, but downstream must finish the chain. See [strategy_specification.toml](/c/Users/ROG/Projects/Forex%20Pipeline/contracts/strategy_specification.toml#L15), [specification.py](/c/Users/ROG/Projects/Forex%20Pipeline/src/python/strategy/specification.py#L45), [2-3-strategy-specification-schema-contracts.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/implementation-artifacts/2-3-strategy-specification-schema-contracts.md#L207), [architecture.md](/c/Users/ROG/Projects/Forex%20Pipeline/_bmad-output/planning-artifacts/architecture.md#L524).

Concrete observations:
- Story 2.4 and Story 2.8 get what they need for the V1 path: a constrained TOML spec, a shared indicator vocabulary, a canonical example, and deterministic persistence primitives.
- The largest forward risk is schema drift: the indicator registry is shared mechanically, but the main strategy schema is only shared by convention. If the TOML contract, Python model, and Rust consumer change at different speeds, later stories can diverge.
- Another growth assumption is that entry conditions are fundamentally `indicator vs numeric threshold`. That is enough for the current strategy family, but broader strategy families may force either more pseudo-indicators like `sma_crossover` or a richer comparison model.

**OVERALL**

Assessment: **OBSERVE**

The story is aligned with the system’s V1 objectives and is a meaningful step toward reproducible, reviewable strategy artifacts. The main observations are structural rather than blocking: the executable schema is duplicated instead of truly contract-driven, operator-facing validation evidence is not yet artifactized, and optimization/general condition semantics will likely need widening as the pipeline expands.

I did not execute tests in this PIR; the assessment relies on the checked-in source, test files, and the implementation synthesis report.
