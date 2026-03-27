# Review Synthesis: Story 2-1-claudebacktester-strategy-evaluator-review

## Reviews Analyzed
- BMAD: available (0 Critical, 0 High, 0 Medium, 2 Low — APPROVED)
- Codex: available (3 High, 1 Medium — 4/10 AC Fully Met, 6/10 Partially Met)

Note: This is synthesis round 2. Round 1 addressed 7 findings from the initial BMAD/Codex reviews. Round 2 addresses 4 new findings from a second Codex review pass against the corrected artifact.

## Round 1 Accepted Findings (previously fixed)

1. **AC2 Indicator Catalogue Incomplete** (Codex HIGH) — Added 6 missing indicators (5.13–5.18), updated all counts from 12→18
2. **AC2 ATR Computation Semantics** (Codex HIGH) — Corrected from EMA to Wilder's smoothing
3. **AC2 Donchian Output Shape** (Codex HIGH) — Corrected from 2-tuple to 3-tuple
4. **AC4 Loading Mechanism Misstated** (Codex HIGH) — Corrected get() vs create() semantics and referential validation
5. **AC3 Explicit Unknowns Missing** (Both) — Added Explicit Unknowns subsection with 6 items
6. **AC2 Missing Price Sources Fields** (Codex MEDIUM) — Added Price Sources to 3 entries
7. **Verdict Count Error** (BMAD MEDIUM) — Fixed "7 Adapt" → "6 Adapt" in completion notes

## Round 2 Accepted Findings (fixes applied)

### 8. Checkpoint schema field names incorrect (Codex HIGH-1)
- **Source:** Codex
- **Severity:** HIGH
- **Description:** Research artifact's JSON examples used `partial_enabled`, `partial_pct`, `hours_start`, `hours_end`, `days_bitmask` — but the real checkpoint.json uses `partial_close_enabled`, `partial_close_pct`, `partial_close_trigger_pips`, `allowed_hours_start`, `allowed_hours_end`, `allowed_days` (a list, not a bitmask). Bitmask conversion happens internally in `encoding.py`.
- **Fix:** Corrected all field names in both Section 7 checkpoint example and Appendix A representative config. Changed `days_bitmask: 31` to `allowed_days: [0, 1, 2, 3, 4]`. Added missing `partial_close_pct` and `partial_close_trigger_pips` fields to Section 7 example.
- **Regression test:** `test_checkpoint_field_names_match_source`

### 9. Entry timing semantics wrong (Codex HIGH-2)
- **Source:** Codex
- **Severity:** HIGH
- **Description:** Artifact documented `Signal.entry_price` as "price at signal bar close" and said backtest uses signal-bar close while live uses next-bar open. Verified against `ema_crossover.py:163`, `rsi_mean_reversion.py:139`, `bollinger_reversion.py:146` — all use `open[next_idx]` with close only as last-bar fallback.
- **Fix:** Updated Signal dataclass comment in Section 4.2 to "Price at next bar open (signal bar close as last-bar fallback only)". Updated Appendix B fidelity risk table to reflect correct timing semantics.
- **Regression test:** `test_entry_price_documented_as_next_bar_open`

### 10. Precompute pattern missing causality constraint (Codex HIGH-3)
- **Source:** Codex
- **Severity:** HIGH
- **Description:** Artifact recommended "precompute-once, filter-many" pattern for D10 adoption without mentioning the `SignalCausality` enum and `REQUIRES_TRAIN_FIT` guard that makes the optimization safe. Verified in `base.py:282` (enum), `engine.py:212` (rejection), `test_causality.py` (tests).
- **Fix:** Added causality constraint paragraph to Section 8.3. Added required causality guard to Section 9.4 proposed architecture update. Added causality contract as a new row in Section 8.1 baseline capabilities table.
- **Regression test:** `test_causality_constraint_documented`

### 11. Authoring workflow omits vectorized path (Codex MEDIUM-1)
- **Source:** Codex
- **Severity:** MEDIUM
- **Description:** Section 6 documented only `generate_signals()`/`filter_signals()`/`calc_sl_tp()` but omitted `generate_signals_vectorized()`, `management_modules()`, and `optimization_stages()` — all actively used by concrete strategies like `ema_crossover.py:84`.
- **Fix:** Added `generate_signals_vectorized()`, `signal_causality()`, `management_modules()`, and `optimization_stages()` to the strategy creation workflow in Section 6. Updated Section 8.3 spec/evaluation separation description to reference the vectorized path.
- **Regression test:** `test_vectorized_authoring_path_documented`

## Rejected Findings (disagreed)

### Round 1 Rejections (retained)

- **No git repo** (BMAD LOW) — Infrastructure issue outside story scope.
- **AC1 says "Rust evaluator" but it's Python-first** (BMAD LOW) — Informational. The review correctly discovered and documented the reality.

### Round 2 Rejections

None. All 4 findings from Codex round 2 were verified against source code and accepted.

## Action Items (deferred)

- **LOW:** Add a second representative strategy config from a different family (e.g., RSI mean reversion) to Appendix A (BMAD LOW-1)
- **LOW:** Add cross-reference from Appendix D to `project_data_naming.md` memory entry (BMAD LOW-2)

## Test Results

```
============================= test session starts =============================
platform win32 -- Python 3.12.12, pytest-9.0.2, pluggy-1.6.0
collected 12 items

tests/test_story_2_1_regression.py::test_all_public_indicators_catalogued PASSED [  8%]
tests/test_story_2_1_regression.py::test_indicator_count_matches PASSED  [ 16%]
tests/test_story_2_1_regression.py::test_atr_not_documented_as_ema PASSED [ 25%]
tests/test_story_2_1_regression.py::test_donchian_documented_as_three_tuple PASSED [ 33%]
tests/test_story_2_1_regression.py::test_loading_mechanism_distinguishes_get_create PASSED [ 41%]
tests/test_story_2_1_regression.py::test_referential_validation_documented PASSED [ 50%]
tests/test_story_2_1_regression.py::test_explicit_unknowns_section_exists PASSED [ 58%]
tests/test_story_2_1_regression.py::test_all_indicator_entries_have_price_sources PASSED [ 66%]
tests/test_story_2_1_regression.py::test_checkpoint_field_names_match_source PASSED [ 75%]
tests/test_story_2_1_regression.py::test_entry_price_documented_as_next_bar_open PASSED [ 83%]
tests/test_story_2_1_regression.py::test_causality_constraint_documented PASSED [ 91%]
tests/test_story_2_1_regression.py::test_vectorized_authoring_path_documented PASSED [100%]

============================= 12 passed in 0.04s ==============================
```

Note: `src/python/tests/test_artifacts/test_storage.py` has a pre-existing import error (`ModuleNotFoundError: No module named 'artifacts.storage'`) unrelated to Story 2-1 changes.

## Verdict

All 11 accepted findings across 2 rounds have been fixed in the research artifact. 12 regression tests pass (8 from round 1 + 4 from round 2). 2 LOW findings deferred. No rejected findings in round 2.

VERDICT: APPROVED
