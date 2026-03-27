# PIR: Story 1-5 — Data Validation & Quality Scoring

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-14
**Type:** Post-Implementation Review (final decision)

---

## Codex Assessment Summary

Codex rated Objective Alignment as CONCERN, Simplification as ADEQUATE, Forward Look as CONCERN, and gave an overall REVISIT verdict. Here is my evaluation of each observation:

### 1. timezone_issues computed but never affects report or gate
**Codex:** `timezone_issues` is computed at line 843 but never added to `all_integrity`, never passed to `_compute_quality_score`, never included in quarantine marking, and never affects `can_proceed`. The architecture specifies ERROR → "Reject and re-download" for timezone alignment failures.

**AGREE (partially on severity).** This is confirmed in the code. `_verify_timezone_alignment()` returns `List[IntegrityIssue]` (line 332-336), and `validate()` captures it at line 843, but the variable is never used again. It's not added to `all_integrity` (line 841 only combines `integrity_issues + spread_issues`), not passed to scoring, quarantine marking, or report generation. The timezone findings are truly discarded.

However, the severity depends on framing. The **story spec** AC #3 says "timezone alignment verifies all timestamps are UTC with no DST artifacts" — the detection is implemented and all ACs are met. The architecture's "Reject and re-download" action is a pipeline orchestrator concern (the orchestrator would need to trigger re-download), which arguably belongs in the Story 2.x orchestration layer, not in the quality checker itself. The quality checker's job is to *detect and report*, and it should at minimum include timezone findings in the report. That it doesn't is a real gap.

### 2. gap_severity computed but discarded
**Codex:** `gap_severity` at line 837 is computed and then unused.

**AGREE (low severity).** The classification itself (ok/warning/error) is dead code. However, the *behavioral effect* of gap severity is covered by other mechanisms: gaps are quarantined in the DataFrame (line 633-637), they contribute to `gap_penalty` in the quality score (line 848-850), and they appear in the report's gaps list (line 706-714). The dead variable is a cleanup item, not a functional gap. It should either be included in the report (e.g., as `gap_severity: "warning"`) or removed.

### 3. completeness_issues don't affect the gate
**Codex:** Completeness errors don't affect `can_proceed`. The architecture specifies ERROR → "Re-download attempt, then quarantine."

**PARTIALLY AGREE.** Completeness issues ARE included in the report (line 733-739), unlike timezone issues. They don't affect the quality score or `can_proceed`, which is true. But again, the story spec's AC #10 says "data with RED score blocks pipeline progression; YELLOW requires operator review" — the gate is explicitly score-based in the story spec. The architecture's re-download-then-quarantine action is an orchestrator-level concern. The quality checker correctly detects and reports completeness problems; acting on them (re-download) is the orchestrator's job.

### 4. validation_timestamp weakens reproducibility
**Codex:** The report includes a runtime `validation_timestamp` that makes artifacts non-identical across runs.

**DISAGREE.** A `validation_timestamp` is standard audit metadata — it records *when* the assessment was made, not *what* was assessed. The quality score, rating, penalties, gap list, and integrity issues are all deterministic for the same inputs. The report serves as an evidence artifact, and evidence artifacts should record when they were produced. This does not weaken "same inputs, same outputs" because the *actionable* outputs (score, rating, can_proceed, quarantined DataFrame) are deterministic. The JSON report's primary purpose is evidence, not reproducible computation.

### 5. config_hash blank unless explicitly supplied
**Codex:** `config_hash` defaults to `""` and `validate()` never passes it, so it's always blank.

**AGREE.** Line 686 defaults `config_hash=""` and line 877 calls `_generate_quality_report` without it. This is a real gap — the report should identify which config produced the validation. The config hash is computed by Story 1.3's `compute_config_hash()` utility and is available to the caller. The fix is straightforward: `validate()` should accept and pass through a config_hash, or compute it from the config dict it already holds.

### 6. Second crash-safe write implementation for CSV
**Codex:** The validated CSV write (lines 772-786) reimplements crash-safe write instead of using the shared `crash_safe_write` from `artifacts.storage`.

**PARTIALLY AGREE.** The JSON report correctly uses the shared utility (line 753). The CSV path can't simply call `crash_safe_write(path, content_string)` because it needs pandas' `to_csv()` with the Windows datetime workaround (lines 775-781 — converting datetime columns to strings to avoid a pandas C extension crash). This is a platform-specific necessity, not laziness. That said, the `crash_safe_write` utility could be enhanced to accept a writer callback, which would centralize the pattern. Low priority.

### 7. quarantined_periods summary missing integrity quarantines and gap bar_count=0
**Codex:** The quarantined_periods list in the report (lines 857-874) only includes gaps and stale records, not integrity-error quarantines. Gap entries hardcode `bar_count: 0`.

**AGREE.** This is the most substantive report-quality issue. The `_mark_quarantined` method (line 614) correctly quarantines all three types (gaps, integrity errors, stale records), so the **DataFrame contract is correct**. But the report's `quarantined_periods` summary omits integrity quarantines entirely, and `quarantined_bar_count` (line 691) undercounts because gap entries contribute 0. This means `quarantined_percentage` in the report is inaccurate. An operator reading the report would see fewer quarantined periods than actually exist in the data.

### 8. Dataset identity omits source and download_hash
**Codex:** Dataset identity uses `{pair}_{start}_{end}_{resolution}` instead of architecture's `{pair}_{start}_{end}_{source}_{download_hash}`.

**AGREE (minor, inherited).** This was already noted in the Story 1-4 PIR. For V1 single-source (Dukascopy), this is acceptable. The validator inherits the dataset_id from its caller; it doesn't construct a new identity model.

---

## Objective Alignment
**Rating:** ADEQUATE

The story serves all four core objectives, with caveats:

- **Reproducibility:** Quality score computation is deterministic for the same inputs. Config hash gap is a real but easily fixable omission. The `validation_timestamp` in the report is standard audit metadata, not a reproducibility problem.
- **Operator confidence:** Quality report with score, rating, penalty breakdown, and detailed issue lists gives the operator a clear picture. The gaps in `quarantined_periods` attribution (missing integrity quarantines, zero bar_count on gaps) weaken but don't eliminate confidence.
- **Artifact completeness:** Two artifacts produced (quality-report.json + validated CSV with quarantined column), both crash-safe. The report is comprehensive — it includes gaps, integrity issues, stale periods, and completeness issues as separate sections. The `quarantined_periods` summary is incomplete, but the underlying data is all present in the report.
- **Fidelity:** Mark-and-skip quarantine (not interpolation) is exactly what the architecture requires. Session-aware spread checks are config-driven. All thresholds come from config, not hardcoded.

Two items prevent STRONG:
1. Timezone findings are computed and fully discarded — not in the report, not in the gate. The operator has no visibility into timezone problems.
2. `config_hash` is always blank, weakening the report's provenance chain.

---

## Simplification
**Rating:** ADEQUATE

The overall structure is right-sized for V1:
- Single `DataQualityChecker` class with clear method-per-check decomposition
- Small `validator_cli.py` entry point
- Reusable `session_labeler.py` utility (already consumed by Story 1.6)
- Vectorized pandas operations throughout for 5M+ row performance

Minor unnecessary complexity:
1. **Dead variables:** `gap_severity` (line 837) and `timezone_issues` (line 843) are computed and discarded. Either wire them into the report/gate or remove the computation.
2. **Placeholder field:** `config_hash` exists in the report schema but is never populated. Either populate it or remove the field.
3. **CSV crash-safe reimplementation:** Justified by Windows pandas workaround, but could be cleaner with a callback-based shared utility.

No over-engineering detected. The session labeler is justified by immediate use (spread outlier checks) and downstream reuse (Story 1.6). The report schema is comprehensive without being bloated.

---

## Forward Look
**Rating:** ADEQUATE

The downstream data contract is correctly established:

- **Story 1.6 handoff:** The validated DataFrame includes the `quarantined: bool` column. Story 1.6's `arrow_converter.py` (confirmed at line 94, 408) reads this column and downstream `timeframe_converter.py` (line 111) excludes quarantined bars before aggregation. The contract works.
- **Session labeler reuse:** `assign_session()` and `assign_sessions_bulk()` are already consumed by Story 1.6 for Arrow IPC session column stamping. The utility is config-driven per D7.
- **Quality report artifact:** Saved to `{storage_path}/raw/{dataset_id}/{version}/quality-report.json` — the path convention matches Story 1.4's output structure. Downstream stories can locate it.
- **Pipeline contract test:** `test_pipeline_contracts.py` (line 113) verifies the quarantined column presence, confirming the cross-story contract is tested.

Items that need attention in future stories:
1. **Timezone findings invisible to orchestrator:** When the orchestration layer (Story 2.x) implements the pipeline workflow, it will need timezone validation results to decide whether to re-download. Currently it would need to re-run timezone checks independently, since the quality report doesn't include them.
2. **Quarantined_periods attribution gap:** The report's quarantined summary undercounts and misattributes. The evidence pack stories will need accurate quarantine attribution for operator review. This should be fixed before evidence packs are built.
3. **can_proceed is score-only:** The architecture envisions some checks (timezone, price integrity) as hard-stop ERRORs independent of score. The current score-only gate is correct per the story spec, but the orchestrator may need to augment it with additional check-specific gates. This is an orchestrator concern, not a quality_checker bug.

---

## Observations for Future Stories

1. **Don't compute and discard.** If a method is called and its return value is unused, either wire it into the output contract or don't call it. `gap_severity` and `timezone_issues` being computed and discarded creates false confidence that these checks influence the gate. (Echoes Story 1-4 lesson about dead code discipline.)

2. **Report summaries must account for all sources.** When building a summary (like `quarantined_periods`), ensure it covers all contributing mechanisms. The DataFrame quarantine correctly includes integrity errors, but the report summary doesn't — creating a discrepancy between what the data shows and what the report says. Rule: if a mechanism marks data, the report must explain every mark.

3. **Placeholder fields erode trust.** A `config_hash: ""` in every report looks like a bug to an operator reviewing evidence. Either populate it or don't include the field. Never ship a placeholder that appears in production artifacts.

4. **Distinguish detection from action.** The quality checker's job is detection and reporting. Actions like "reject and re-download" or "halt pipeline" belong in the orchestrator. Story specs should clarify this boundary — some of the architecture's "Action" column items (re-download, reject batch) imply orchestrator behavior, not checker behavior. Future story specs should explicitly state which actions the checker owns vs. which it delegates.

---

## Verdict

**VERDICT: OBSERVE**

Story 1.5 delivers its core value: a comprehensive data quality validation framework with gap detection, price integrity checks, spread outlier detection (session-aware, config-driven), stale quote detection, completeness checks, and a quality scoring system matching the architecture's formula. The quarantined column on the DataFrame — the critical downstream contract — is correctly populated and tested. The quality report artifact is crash-safe written with detailed issue listings.

Codex's REVISIT verdict overstates the severity. The observations are real but fall into two categories:

1. **Cleanup items** (dead variables, placeholder config_hash, quarantined_periods attribution): These are code quality issues, not alignment failures. The underlying data and behavior are correct; the report summary has gaps that should be fixed but don't block the pipeline.

2. **Spec boundary issues** (timezone/completeness not affecting gate, can_proceed score-only): These reflect a tension between the architecture's action column and the story spec's ACs. The implementation correctly follows the story spec. The architecture's "Reject and re-download" actions belong in the orchestrator layer, not the quality checker. Future orchestration stories should consume timezone and completeness findings from the report.

The one item closest to a real concern — timezone findings being completely invisible in the report — should be addressed as a minor fix. All other observations are worth tracking for future stories but don't compromise system objectives at the V1 scope.
