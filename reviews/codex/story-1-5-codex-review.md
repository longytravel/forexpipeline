# Story 1.5: Data Validation & Quality Scoring — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-14
**Method:** Static analysis (no pytest execution — sandbox policy)

---

## HIGH Findings

### 1. Gap severity computed then discarded
Gap severity is computed and then discarded, so the required gap `WARNING`/`ERROR` state never affects the report or pipeline outcome. `validate()` assigns `gap_severity` and never uses it in scoring, reporting, or `can_proceed`.

Also, the implementation and tests invert the written warning rule: code warns on `> 10` gaps/year, while the story says `WARNING if < 10 gaps/year`.

- `quality_checker.py:830` — gap_severity assigned
- `quality_checker.py:890` — can_proceed ignores gap_severity
- `quality_checker.py:157` — inverted threshold
- `test_quality_checker.py:181` — test matches inverted logic
- `epics.md:522` — story spec

### 2. Timezone validation does not satisfy the AC
Tz-naive timestamps are silently localized to UTC instead of being rejected or proven UTC. The resulting `timezone_issues` list is never included in the report or used to block progression.

- `quality_checker.py:365` — silent UTC localization
- `quality_checker.py:836` — timezone_issues computed
- `quality_checker.py:870` — not included in report
- `quality_checker.py:890` — not used in can_proceed

### 3. Quality report omits quarantine data and misreports totals
Integrity-based quarantines are added to the dataframe but never added to `quarantined_periods`. Gap entries are recorded with `bar_count: 0`. Report totals are derived from that incomplete list instead of from the actual `quarantined` column.

- `quality_checker.py:645` — integrity quarantines added to df
- `quality_checker.py:850` — not added to quarantined_periods
- `quality_checker.py:858` — gap entries have bar_count: 0
- `quality_checker.py:691` — totals from incomplete list
- `quality_checker.py:742` — report uses incomplete data

---

## MEDIUM Findings

### 4. Gap duration off by one bar/minute
Gap duration uses the raw difference between surrounding valid timestamps. A 5-missing-bar M1 gap is treated as 6 minutes and a 30-minute missing segment becomes 31, distorting detection and the `> 30 min` escalation threshold.

- `quality_checker.py:85`
- `quality_checker.py:91`
- `quality_checker.py:151`

### 5. Completeness is not forex-session-aware
Uses a rough business-day heuristic treating every business day as expecting ~1440 M1 bars and warns below 720. Will false-flag holidays and partial Monday/Friday trading days.

- `quality_checker.py:496`
- `quality_checker.py:516`

### 6. Staleness scoring exceeds AC scope
Penalizes `frozen_price` OHLC runs beyond the AC's `bid=ask` / `spread=0` specification.

- `quality_checker.py:430`
- `quality_checker.py:577`

---

## Acceptance Criteria Scorecard

| Criterion | Status | Notes |
|-----------|--------|-------|
| Gap detection (>5 bars, WARNING/ERROR thresholds) | Partial | Thresholds inverted vs story, severity not enforced |
| Price integrity (bid>0, ask>bid, spread 10x) | **Fully met** | `quality_checker.py:176,188,269` |
| Timezone UTC alignment | **Not met** | Silently localized, not gating |
| Stale quote detection (bid=ask, spread=0, >5 bars) | **Fully met** | `quality_checker.py:421,648` |
| Completeness checks (no missing weekdays) | Partial | Not session-aware, false-flags holidays |
| Quality score formula (1.0 - penalties) | **Fully met** | `quality_checker.py:538` |
| GREEN/YELLOW/RED ratings | **Fully met** | `quality_checker.py:601` |
| Quarantined column (bool) | **Fully met** | `quality_checker.py:628` |
| Quality report artifact | Partial | Missing tz issues, wrong quarantine counts |
| RED blocks pipeline / YELLOW requires review | **Fully met** | `quality_checker.py:890`, `validator_cli.py:96,109` |
| Crash-safe writes (NFR15) | **Fully met** | `storage.py:10`, `quality_checker.py:752,775` |

---

## Test Coverage Gaps

- `validator_cli.run_validation` untested — pipeline-blocking contract not verified
- Timezone tests only check non-monotonic timestamps, not UTC enforcement or DST — `test_quality_checker.py:316`
- Report assertions check few top-level fields, not full quarantined-period fidelity — `test_quality_checker.py:539,575`

---

## Summary

**6 of 11 criteria fully met, 4 partially met, 1 not met.** The core scoring and detection machinery works, but three validation categories (timezone, gap severity, completeness) are computed without affecting the pipeline outcome. The quarantine report has data integrity issues. Gap thresholds are inverted relative to the story specification.
