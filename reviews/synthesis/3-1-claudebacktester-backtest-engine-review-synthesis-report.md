# Review Synthesis: Story 3-1-claudebacktester-backtest-engine-review

## Reviews Analyzed
- BMAD: available (0 Critical, 0 High, 1 Medium, 2 Low — VERDICT: APPROVED)
- Codex: available (0 Critical, 3 High, 2 Medium — 8/11 AC Fully Met, 3 Partially Met)

## Accepted Findings (fixes applied)

### 1. max_spread_pips misstatement (Codex MEDIUM)
**Source:** Codex
**Severity:** MEDIUM
**Description:** The gap-analysis cost section (line 673) stated `max_spread_pips` is "not in Rust; in Python engine." However, `lib.rs:319-324` clearly applies this filter inside `batch_evaluate()` — skipping signals where spread exceeds the threshold or is NaN. This is a data-integrity error in a research artifact guiding future porting.
**Fix applied:** Corrected the statement to document that `max_spread_pips` is enforced in **both** Rust (`lib.rs:319-324`) and Python, with Rust as the authoritative enforcement point.

### 2. AC6 persisted-vs-recomputed not clearly documented (Codex HIGH, downgraded to MEDIUM)
**Source:** Codex
**Severity:** MEDIUM (downgraded from HIGH — the information was present implicitly but not structured per AC requirement)
**Description:** AC6 explicitly requires documenting "what state is persisted vs recomputed." The checkpoint section documented what's saved and how resume works, but didn't explicitly separate persisted items from recomputed items.
**Fix applied:** Added a structured "Persisted vs Recomputed on Resume" table with 7 entries covering: completed stage list, validation results, optimization candidates, pipeline config (persisted) vs BacktestEngine instance, encoding spec, in-progress work (recomputed/lost).

### 3. AC11 downstream handoff inconsistent for Stories 3-6 through 3-9 (Codex HIGH, downgraded to MEDIUM)
**Source:** Codex
**Severity:** MEDIUM (downgraded from HIGH — the handoff content was substantive but missing structural subsections)
**Description:** AC11 requires each downstream story to include: interface candidates, migration boundaries, V1 port decisions, deferred/no-port items, and open questions. Stories 3-2 through 3-5 had all fields; Stories 3-6 through 3-9 were missing one or more of: V1 port decisions, deferred/no-port items, open questions.
**Fix applied:** Added the missing subsections to all four stories (3-6, 3-7, 3-8, 3-9) with substantive content derived from the review findings.

### 4. Tests give false confidence — keyword-presence only (Both BMAD L1 + Codex MEDIUM)
**Source:** Both
**Severity:** MEDIUM (BMAD rated LOW, Codex rated MEDIUM — splitting the difference)
**Description:** Tests only check if keywords exist in artifact text, which can't detect structural gaps like missing subsections or factual errors. This is why the AC6/AC11 gaps and the max_spread_pips error were not caught.
**Fix applied:** Added 3 regression tests:
- `test_persisted_vs_recomputed_documented` — verifies AC6 has explicit persisted/recomputed content
- `test_downstream_story_has_required_fields` — parametrized across all 8 downstream stories, verifies each has migration boundary and V1 port decisions
- `test_max_spread_pips_documents_rust_enforcement` — verifies the artifact mentions Rust enforcement near max_spread_pips discussion

### 5. Test execution not verified (BMAD MEDIUM)
**Source:** BMAD
**Severity:** MEDIUM
**Description:** verify-manifest.json had empty `verify_commands`. No evidence tests were run.
**Fix applied:** Tests executed as part of this synthesis — 118 passed, 11 skipped (live markers). Results documented below.

## Rejected Findings (disagreed)

### 1. AC1 partially satisfied — inventory lacks per-file paths (Codex HIGH)
**Source:** Codex
**Severity:** HIGH (rejected)
**Reason:** The inventory tables are grouped under explicit directory headings (e.g., "Rust Extension (`rust/src/` — 1,646 lines)"), making the full path for each file unambiguously derivable. Adding redundant path prefixes to every row would reduce table readability. Module relationships are documented in the Purpose column and detailed in Sections 4-7. BMAD independently rated this AC as Fully Met. The AC requirement is satisfied in substance.

### 2. Baseline traceability commit hash accepts outdated value (Codex test coverage gap)
**Source:** Codex (test coverage gaps section)
**Severity:** LOW observation, not a finding
**Reason:** The test accepts either `012ae57` (actual HEAD) or `2084beb` (story spec reference). The dev agent documented the discrepancy and verified no backtester code changes between the commits. This is correct behavior — the test is flexible by design.

## Action Items (deferred)

- **LOW:** Consider adding cross-validation tests that check artifact claims against actual ClaudeBackTester source files (Codex suggestion). Would require test infrastructure to access the external repo, which is out of scope for a research story test suite.
- **LOW:** Story spec line counts remain vastly inflated (BMAD L2). This is a story-authoring quality issue — should be addressed in the story-writing pipeline, not in this story's implementation.

## Test Results

```
118 passed, 11 skipped in 0.16s
```

All unit tests pass. 11 live-marker tests skipped (require explicit `--run-live` flag). 3 new regression tests included in the 118 passing tests.

## Verdict

All CRITICAL and HIGH findings have been addressed (2 Codex HIGHs fixed, 1 rejected with justification). All MEDIUM findings fixed. The research artifact is comprehensive, well-structured, and now correctly documents:
- max_spread_pips Rust enforcement
- Explicit persisted-vs-recomputed state table
- Complete downstream handoff for all 8 stories

VERDICT: APPROVED
