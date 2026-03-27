# Story Synthesis: 2-3-strategy-specification-schema-contracts

**Synthesizer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-15
**Codex Review Verdict:** REFINE
**Synthesis Verdict:** IMPROVED

---

## Codex Observations & Decisions

### 1. Re-scope Story 2.3 — move lock/version history/diff to 2.5
**Codex said:** Story 2.3 overreaches by taking on versioning/locking-adjacent behavior that Epic 2.5 already owns. Should narrow to schema contract, preflight validation, and reference fixtures.
**Decision:** PARTIALLY AGREE
**Reasoning:** The story already correctly scopes versioning as persistence primitives (save/increment/immutability in `storage.py`). It does NOT include locking, confirmation, diff summaries, or manifest records — those are clearly in Story 2.5's ACs. The concern is valid in spirit but the story doesn't actually overreach. However, the boundary should be explicitly stated to prevent developer confusion.
**Action:** Added "Scope Boundary: 2.3 vs 2.5 Versioning" dev note clarifying that save/load/list/increment are persistence primitives; confirmation/locking/diff/manifest are 2.5. Added anti-pattern #14 reinforcing this.

### 2. D10 filter vocabulary mismatch — `regime` vs `volatility`
**Codex said:** D10 lists `session, regime, day_of_week` filters, but the story implements `session, volatility, day_of_week` — a direct contract mismatch.
**Decision:** PARTIALLY AGREE
**Reasoning:** Codex is right that D10's contract tree says `regime`, but D10's own minimum representable constructs table explicitly defines "Volatility filters" with `Filter type = volatility`. The tree and table are internally inconsistent within D10. The story follows the table (more detailed, more authoritative). `regime` is a Growth Phase concept (FR69) not needed for V1. However, the discrepancy should be documented for the developer.
**Action:** Added "D10 Filter Vocabulary Note" dev note explaining the tree vs table discrepancy and confirming the story follows the table.

### 3. Replace hardcoded multi-pair enums with V1 defaults
**Codex said:** Hardcoding `EURUSD|GBPUSD|...` is multi-pair growth path scope creep for V1.
**Decision:** AGREE
**Reasoning:** V1 is explicitly one pair (EURUSD). Hardcoding a multi-pair enum is premature. The pair set should be extensible through config, not schema changes.
**Action:** Changed pair enum in Task 2 from `enum=EURUSD|GBPUSD|...` to `enum=EURUSD — V1 single-pair; extend via config when adding pairs`.

### 4. Remove indicator registry ownership or make it a shared artifact
**Codex said:** Python and Rust will each invent separate semantic truth for indicator types, creating drift risk. Remove registry from 2.3 or make it a shared artifact.
**Decision:** PARTIALLY AGREE
**Reasoning:** Removing the registry would eliminate preflight validation, which is a core story purpose (AC #5: "all referenced indicator types are recognized"). However, Codex is right that Python and Rust registries will diverge if they're independently maintained. The fix is a shared source file that both consume.
**Action:** Added `contracts/indicator_registry.toml` as a shared source file. Updated Task 7 to load from this TOML file instead of hardcoding. Updated indicator_registry.py to source from Story 2.1's catalogue output. Added anti-pattern #13 about registry drift. Updated Project Structure Notes.

### 5. Add `schema_version` to the strategy spec contract
**Codex said:** No `schema_version` means future contract changes will force rewrites in 2.4, 2.5, and 2.8 with no migration path.
**Decision:** AGREE
**Reasoning:** This is a low-cost addition with high value for forward compatibility. Every serialization format benefits from a version field.
**Action:** Added `schema_version` to metadata section in Task 2 and Pydantic model in Task 3.

### 6. Clarify `config_hash` semantics — 2.3 vs 2.5
**Codex said:** If `config_hash` is only meaningful for a locked artifact, make it a 2.5 requirement rather than a 2.3 schema requirement.
**Decision:** AGREE
**Reasoning:** `config_hash` links the spec to pipeline configuration state at confirmation time (FR59). A draft spec doesn't have this yet. Making it required in the schema means draft specs would need a placeholder value, which is semantically wrong.
**Action:** Changed `config_hash` from required to optional in Task 2 metadata and Task 3 Pydantic model. Added "config_hash Lifecycle" dev note explaining the distinction between spec hash (content identity, Task 5) and config_hash (pipeline config linkage, Story 2.5).

### 7. Add contract tests with fixture files
**Codex said:** "Supports minimum representable constructs" needs fixture-based proofs, not prose. Add positive and negative fixtures.
**Decision:** AGREE
**Reasoning:** Fixture-based tests are more rigorous and serve as living documentation of the contract. The current test list references programmatic test creation but not explicit fixture files.
**Action:** Added new Task 10 (Create Test Fixtures) with 5 explicit fixture files: valid_ma_crossover.toml plus 4 negative fixtures covering missing metadata, bad param ranges, unknown indicators, and bad cost model refs. Renumbered original Task 10 to Task 11. Updated Project Structure Notes with fixtures directory.

### 8. Make MA crossover reference spec identical across Story 2.3 and Epic 2.9
**Codex said:** Story 2.3 has London+NY and 2x ATR stop; Epic 2.9 has London only and 3x ATR chandelier. These contradict.
**Decision:** AGREE
**Reasoning:** The canonical E2E proof in 2.9 defines the reference strategy. The 2.3 reference spec should match exactly so the E2E proof doesn't require modifications.
**Action:** Changed Task 8 entry rules from "session filter = London + NY" to "session filter = London only (aligns with Epic 2.9 canonical example)". Changed exit rules from "ATR-based stop_loss (2x ATR)" to "chandelier exit at 3x ATR (primary)". Changed optimization plan atr range to match.

### 9. State explicitly that versioning utilities are persistence primitives only
**Codex said:** If versioning utilities remain in 2.3, state explicitly that they are persistence primitives; confirmation/locking/version history/diff remain owned by 2.5.
**Decision:** AGREE
**Reasoning:** Subsumed by decision #1 above. The boundary should be explicit.
**Action:** Covered by the dev note and anti-pattern added in decision #1.

### 10. Add anti-pattern warning against schema drift
**Codex said:** Add warning against drift between `contracts/strategy_specification.toml`, Python validation, and the later Rust `strategy_engine` parser.
**Decision:** AGREE
**Reasoning:** This is a real risk. The TOML contract is the source of truth; Python and Rust must both derive from it, not evolve independently.
**Action:** Covered by anti-pattern #13 (indicator registry drift) and the shared `contracts/indicator_registry.toml` approach. The TOML contract already serves as the shared boundary per D10's design.

## Changes Applied

1. **Task 2 (metadata):** Added `schema_version` field, narrowed `pair` enum to EURUSD for V1, changed `config_hash` from required to optional
2. **Task 3 (Pydantic):** Updated `StrategyMetadata` to include `schema_version` and `config_hash` as `Optional[str]`
3. **Task 7 (registry):** Added instruction to source from `contracts/indicator_registry.toml` shared file, seeded from Story 2.1 catalogue output
4. **Task 8 (MA crossover):** Aligned with Epic 2.9 canonical example — London only, chandelier exit at 3x ATR
5. **New Task 10:** Added explicit test fixture creation task with 5 fixture files (1 valid, 4 invalid)
6. **Dev Notes:** Added 3 new sections — Scope Boundary (2.3 vs 2.5), D10 Filter Vocabulary Note, config_hash Lifecycle
7. **Anti-Patterns:** Added #13 (Python/Rust registry drift) and #14 (versioning scope creep)
8. **Project Structure:** Added `contracts/indicator_registry.toml` and `fixtures/` directory with 5 test fixture files

## Deferred Items

- **D10 tree/table reconciliation:** The D10 contract tree says `regime` but the table says `volatility`. This should be reconciled in the architecture document during a future architecture review, not in the story.
- **Multi-pair enum expansion:** When V1 proves out and additional pairs are needed, the pair enum should be driven by pipeline configuration, not schema hardcoding. This is a Growth Phase concern.

## Verdict

VERDICT: IMPROVED

The story was already well-structured. Key improvements: schema_version for forward compatibility, shared indicator registry source to prevent Python/Rust drift, explicit scope boundary with Story 2.5, MA crossover alignment with Epic 2.9 canonical example, and fixture-based contract tests. No scope changes — all improvements strengthen existing content without adding complexity.
