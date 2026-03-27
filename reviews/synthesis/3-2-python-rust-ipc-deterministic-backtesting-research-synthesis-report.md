# Review Synthesis: Story 3-2-python-rust-ipc-deterministic-backtesting-research

## Reviews Analyzed
- BMAD: available (Claude Opus 4.6, adversarial code review)
- Codex: available (GPT-5.4, read-only static analysis)

## Accepted Findings (fixes applied)

### 1. Equity curve contract contradiction (Codex H2 — HIGH)
**Source:** Codex
**Severity:** HIGH
**Description:** The CLI output contract (§9.1) defined `equity_{trial_idx}.arrow` with bar-level columns (`bar_index`, `timestamp_us`, `cumulative_pnl`), but Open Question #3 recommended per-trade granularity for V1. Downstream stories 3.5/3.6 would receive contradictory guidance.
**Fix:** Updated CLI output table to per-trade columns (`trade_index`, `exit_timestamp_us`, `cumulative_pnl`, `drawdown_pct`). Marked Open Question #3 as RESOLVED with cross-reference to updated §9.1.
**Regression test:** `test_equity_curve_contract_is_per_trade` — verifies equity curve uses `trade_index`, not `bar_index`.

### 2. Memory budget numerical inconsistency (Codex M1 — MEDIUM)
**Source:** Codex
**Severity:** MEDIUM
**Description:** Executive summary claimed "~2.4GB active" but the detailed budget table totaled ~1,065MB heap / ~1,465MB including mmap. The discrepancy weakens credibility of the resource model.
**Fix:** Updated executive summary to "~1.1GB heap + ~400MB mmap" with itemized breakdown matching the detailed table.
**Regression test:** `test_memory_budget_exec_summary_matches_table` — asserts exec summary does not contain the old "~2.4GB active" claim.

### 3. Single-backtest checkpoint clarity (Codex H1 — downgraded to MEDIUM)
**Source:** Codex (flagged as HIGH, downgraded to MEDIUM)
**Severity:** MEDIUM (documentation clarity, not missing functionality)
**Description:** The recommended checkpoint strategy said per-trade state was "not persisted — only for crash-safe resume within a single batch," which reads as if single backtests have NO crash-resume strategy at all. The granularity table already documented per-N-bars as viable for long backtests, but the recommendation summary didn't connect the dots.
**Why downgraded:** The strategies for both use cases were present in the granularity table (§5.1); the issue was that the recommendation summary was ambiguous, not that the research was incomplete. AC3 was functionally met.
**Fix:** Expanded recommended strategy to three explicit cases: (1) optimization runs → per-batch persisted, (2) short backtests ≤10min → re-run is faster, (3) long backtests >10min → per-N-bars persisted checkpointing.
**Regression test:** `test_single_backtest_checkpoint_strategy_documented` — verifies "single backtest" is explicitly addressed in the checkpoint section.

### 4. Incomplete PRD cross-reference in Appendix A (BMAD M1 — MEDIUM)
**Source:** BMAD
**Severity:** MEDIUM
**Description:** Task 8 specifies cross-referencing FR14–FR19, FR42, FR58–FR61, NFR1–NFR5, NFR10–NFR15. Appendix A omitted FR16, FR17, FR19, NFR2, NFR3, NFR12, NFR13, NFR14 — not even marked N/A.
**Fix:** Added all missing entries with "N/A — Not in scope" explanations noting which downstream story addresses each.
**Regression test:** `test_appendix_a_has_na_entries_for_out_of_scope` + parametrized `test_appendix_a_fr_referenced` and `test_appendix_a_nfr_referenced` covering all specified ranges.

### 5. Incomplete architecture cross-reference in Appendix B (BMAD M2 — MEDIUM)
**Source:** BMAD
**Severity:** MEDIUM
**Description:** Task 8 says "D1–D14" but Appendix B only listed 7 of 15 decisions (D1, D2, D3, D8, D13, D14, D15). D4–D7 and D9–D12 were absent.
**Fix:** Added all missing decisions (D4–D12) with "N/A — Not directly addressed" explanations.
**Regression test:** `test_appendix_b_has_all_decisions` + parametrized `test_appendix_b_decision_referenced` covering D1–D15.

### 6. Misleading docstring on TestArchitectureAlignmentComplete (BMAD L1 — LOW)
**Source:** BMAD
**Severity:** LOW
**Description:** Class docstring said "Verify D1-D14 referenced" but `ARCH_DECISIONS` only contains 6 decisions. Misleading impression of broader coverage.
**Fix:** Updated docstring to "Verify D1, D2, D3, D8, D13, D14 referenced" with note that AC #5 requires these 6 specifically.

### 7. Weak exit code test logic (BMAD L2 — LOW)
**Source:** BMAD
**Severity:** LOW
**Description:** `test_cli_contract_has_exit_codes` used redundant OR logic that would pass if "exit code" appeared anywhere, without verifying both success (0) and failure codes existed.
**Fix:** Rewrote test to assert: (1) exit code 0 exists in a table row, (2) at least one non-zero exit code exists in a table row.

### 8. No test coverage for appendix completeness (BMAD L3 — LOW)
**Source:** BMAD
**Severity:** LOW
**Description:** No tests validated that Appendix A and B exist or are complete.
**Fix:** Added `TestAppendixCompleteness` class with 36 parametrized tests covering both appendices.

## Rejected Findings (disagreed)

### 1. Executive summary has only 8 bullet points (BMAD L4 — LOW)
**Source:** BMAD
**Severity:** LOW
**Description:** BMAD noted the executive summary has 8 items, suggesting items 9-10 could be added.
**Why rejected:** The current artifact has 10 numbered items (verified in the file). BMAD may have miscounted or reviewed an earlier state. The constraint is "≤10 bullet points" which is satisfied with the existing 10.

### 2. Shallow test assertions as systemic issue (BMAD M3 / Codex M2 — MEDIUM)
**Source:** Both
**Severity:** MEDIUM
**Description:** Both reviewers noted that tests are primarily substring-based and don't validate semantic consistency.
**Why rejected as systemic fix:** This is an inherent limitation of testing research artifact content — the artifact is prose, not structured data. The specific test weaknesses (L1, L2, L3) were fixed individually. The new regression tests (5 tests in `TestRegressionReviewSynthesis`) demonstrate section-scoped assertions rather than whole-document keyword searches, which is the practical improvement both reviewers suggested. A full rewrite of all 78 original tests to use section-scoped parsing is disproportionate effort for a research story and deferred.

## Action Items (deferred)

1. **MEDIUM — Section-scoped test assertions:** Consider refactoring existing tests to parse sections and validate content within the correct section, not just anywhere in the document. The `artifact_sections` fixture already exists but is underutilized. Low priority for a research story.
2. **LOW — Executive summary optimization:** Items 9-10 could be made more concise. No action needed — current content is complete.

## Test Results

```
119 passed, 3 skipped in 0.14s
```

- 78 original unit tests: all passing
- 36 new appendix completeness tests: all passing
- 5 new regression tests: all passing
- 3 live tests: skipped (require `pytest -m live`)
- Total: 119 passed, 3 skipped, 0 failed

## Files Modified

- `_bmad-output/planning-artifacts/research/3-2-ipc-determinism-research.md` — Fixed equity curve contract, memory budget, checkpoint clarity, Appendix A, Appendix B
- `src/python/tests/test_research/test_story_3_2_ipc_determinism_research.py` — Fixed docstring, exit code test; added TestAppendixCompleteness (36 tests), TestRegressionReviewSynthesis (5 tests)

## Verdict

All 7 acceptance criteria remain fully met. The 3 HIGH/MEDIUM findings from Codex were real issues (equity curve contradiction, memory budget inconsistency, checkpoint ambiguity) but all were documentation/consistency problems in the research artifact — not gaps in research quality. All fixes applied, all tests pass, regression tests guard against recurrence.

**APPROVED**
