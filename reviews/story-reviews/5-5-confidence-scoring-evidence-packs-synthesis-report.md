# Story Synthesis: 5-5-confidence-scoring-evidence-packs

## Codex Observations & Decisions

### 1. System Alignment — AC1 contradiction + scope creep
**Codex said:** AC1 assumes fully completed gauntlet while the story later requires scoring short-circuited candidates. Story claims to be "pure aggregation/presentation layer" while also adding population-level anomaly logic and visualization prep — more than V1 needs.
**Decision:** AGREE
**Reasoning:** AC1 explicitly said "completed the full validation gauntlet" but Dev Notes (Short-Circuited Candidates section) and Task 11 both handle incomplete gauntlet results. This is a genuine internal contradiction. The "pure aggregation" label is inaccurate — the story adds scoring logic, anomaly detection, and narrative generation, which are valid but not "pure aggregation." Population-level anomaly tests across 5-10 V1 candidates are statistically meaningless.
**Action:**
- Rewrote AC1 to accept both complete and short-circuited gauntlet manifests
- Changed "pure aggregation/presentation layer" to "aggregation, scoring, and presentation layer"
- Gated cross-candidate population anomaly tests behind `min_population_size` (default: 20)
- Per-candidate anomaly detectors still always run (FR17 compliance)

### 2. PRD Challenge — `delta_vs_baseline` and FR16/17 scope
**Codex said:** FR16/17/25-style analysis is overreach. `delta_vs_baseline` looks like Growth-phase refinement, not MVP.
**Decision:** PARTIALLY AGREE
**Reasoning:** FR16/FR17 are explicitly assigned to this story in the epics — they are NOT scope creep. However, `delta_vs_baseline` requires a baseline definition that doesn't exist in V1 (single strategy, no prior optimization runs to compare against). Making it optional with a clear baseline source definition is the right call. Buy-and-hold benchmark is a reasonable future baseline but not required for V1.
**Action:**
- Made `delta_vs_baseline` optional (`dict[str, float] | None`) in TriageSummary model
- Added explicit documentation that it's only populated when a baseline exists
- FR16/FR17 references kept — they are assigned scope, not overreach

### 3. Architecture Challenge — Python vs Rust ownership of FR34
**Codex said:** Architecture tree points at Rust `validator/confidence.rs` while this story implements in Python. Task 10's skill reads like it loads files and mutates evidence packs directly.
**Decision:** AGREE
**Reasoning:** Verified the architecture does mention `confidence.rs` in the validator crate. However, FR34 in the PRD is neutral on implementation location. Confidence scoring in this story is lightweight deterministic aggregation over JSON manifests — Python is unambiguously the simpler fit. The skill/evidence pack mutation concern is valid — Task 10 was recording operator decisions by mutating the evidence pack, which blurs immutable machine evidence and human judgment.
**Action:**
- Added explicit dev note "FR34 Implementation Location" explaining Python choice and origin
- Separated operator review decisions into a separate `OperatorReview` model and `operator-review-candidate-{id}.json` artifact
- Evidence packs are now immutable once written

### 4. Story Design — Internal inconsistencies (CRITICAL)
**Codex said:** Task 8 both prepares chart JSON and returns Arrow refs. Task 9 returns all evidence packs in memory while anti-patterns forbid that. AC1 conflicts with short-circuited handling. 60s/15min ACs not testable.
**Decision:** AGREE
**Reasoning:** All four inconsistencies confirmed:
- Task 8's `prepare_*` functions returned `dict` while `prepare_all_visualizations` returned `dict[str, str]` (refs) — unclear contract
- Task 9's `score_all_candidates()` returned `list[ValidationEvidencePack]` directly contradicting anti-pattern #6 "DO NOT hold all evidence packs in memory"
- AC1 contradiction already addressed above
- "review in under 60 seconds / 15 minutes" is aspirational design intent, not a testable acceptance criterion
**Action:**
- Task 8: Clarified that `prepare_all_visualizations` validates and assembles ref map from `chart_data_refs` — does NOT read Arrow data. Individual functions extract layout metadata from `per_stage_summaries`
- Task 9: Changed `score_all_candidates()` to accept `output_dir: Path` and return `Path` (aggregate manifest path). Each evidence pack persisted immediately.
- AC4: Replaced time-based language with structural proxies (≤10 headline fields, ≤3 risk items, ≤200 words, citation coverage)
- Added stable aggregate manifest schema for downstream consumers (Story 5.7, dashboard)

### 5. Downstream Impact — Provenance and immutability gaps
**Codex said:** No dedicated scoring config hash. Mutating evidence packs with operator decisions blurs immutable evidence. Layer A population scoring weak for small V1 candidate set.
**Decision:** AGREE
**Reasoning:** The story used `config_hash` from the gauntlet manifest but had no hash for the confidence scoring configuration itself. Since scoring thresholds/weights are independent of validation config, a separate `confidence_config_hash` is needed for reproducibility. Evidence pack immutability and population anomaly gating already addressed above.
**Action:**
- Added `confidence_config_hash` and `validation_config_hash` to DecisionTrace model (replacing generic `config_hash`)
- Updated Task 7's `build_decision_trace` to compute and include both hashes
- Updated evidence pack metadata to include both config hashes
- Removed `operator_notes` and `operator_decision` from DecisionTrace (now in separate OperatorReview)
- Added `OperatorReview` dataclass to Task 1 models
- Added "Evidence Pack Immutability" and "Population Anomaly Gating" dev notes

## Codex Recommendations Disposition

| # | Recommendation | Decision | Notes |
|---|---------------|----------|-------|
| 1 | Rewrite AC1 for short-circuited handling | AGREE | Applied |
| 2 | Remove "pure aggregation" claim | AGREE | Qualified to "aggregation, scoring, and presentation" |
| 3 | Choose one visualization contract | AGREE | Clarified: ref map assembly only, no Arrow reads |
| 4 | Add `confidence_config_hash` + brief provenance | AGREE | Applied to DecisionTrace and metadata |
| 5 | Make evidence pack immutable, separate operator review | AGREE | Applied — new OperatorReview model |
| 6 | Rename `/pipeline` operation | DISAGREE | "Review Optimization Results" is already stage-accurate per existing `/pipeline` patterns |
| 7 | Replace 60s/15min ACs with measurable proxies | AGREE | Applied structural proxies |
| 8 | Make `delta_vs_baseline` optional | AGREE | Applied with baseline source definition |
| 9 | Resolve Python-vs-Rust FR34 ownership | AGREE | Added dev note |
| 10 | Stream per-candidate persistence, return manifest path | AGREE | Applied |
| 11 | Gate population anomaly logic behind min candidate count | AGREE | Applied (default: 20) |
| 12 | Add stable schema for aggregate scoring manifest | AGREE | Applied inline in Task 9 |

## Changes Applied
- AC1: Rewritten to accept both complete and short-circuited gauntlet manifests
- AC4: Time-based language replaced with structural proxies (field counts, word limits, citation coverage)
- AC7: Population-level anomaly tests gated behind configurable `min_population_size` (default: 20)
- AC8: Added `confidence_config_hash`, removed operator fields (moved to separate artifact)
- AC9: Operator decisions stored in separate append-only artifact, not mutating evidence pack
- User story: Removed time-based language
- Task 1 models: `TriageSummary.delta_vs_baseline` made optional; `DecisionTrace` split into immutable trace + separate `OperatorReview`; added `OperatorReview` dataclass
- Task 5: Layer A split into per-candidate detectors (always run) and cross-candidate population tests (gated)
- Task 7: `build_decision_trace` updated for dual config hashes and removed operator fields
- Task 8: Clarified visualization functions as ref-map assembly + layout metadata extraction, not Arrow data reading
- Task 9: `score_all_candidates()` now returns `Path` (manifest) not `list[ValidationEvidencePack]`; stable aggregate manifest schema defined
- Task 10: Operator decisions recorded in separate artifact
- Dev Notes: Removed "pure aggregation" claim; added FR34 Python ownership, evidence pack immutability, and population anomaly gating notes

## Deferred Items
- Architecture update to formalize FR34 Python ownership (currently architecture tree shows `confidence.rs` in Rust validator crate)
- Brief 3C/version provenance — Codex flagged this but the story already includes `research_brief_versions` from the gauntlet manifest, which covers it
- Stable dashboard-ready visualization schema — deferred to Epic 4 dashboard story; this story provides Arrow refs + layout metadata only

## Verdict
VERDICT: IMPROVED
