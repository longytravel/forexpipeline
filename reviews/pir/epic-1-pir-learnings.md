# Epic 1 PIR Learnings

**Date:** 2026-03-15
**Scope:** Retroactive Post-Implementation Review of Stories 1-4 through 1-8
**Method:** Codex GPT-5.4 (adversarial analysis) → Claude (synthesis & judgment)
**Overall:** All 5 stories OBSERVE — aligned with system objectives, observations noted

---

## Rating Summary

| Story | Title | Alignment | Simplification | Forward Look | Claude | Codex |
|-------|-------|-----------|----------------|--------------|--------|-------|
| 1-4 | Data Download | ADEQUATE | ADEQUATE | STRONG | OBSERVE | REVISIT |
| 1-5 | Validation & Quality | ADEQUATE | ADEQUATE | ADEQUATE | OBSERVE | REVISIT |
| 1-6 | Parquet/Arrow Storage | ADEQUATE | ADEQUATE | ADEQUATE | OBSERVE | REVISIT |
| 1-7 | Timeframe Conversion | STRONG | STRONG | ADEQUATE | OBSERVE | REVISIT |
| 1-8 | Data Splitting | ADEQUATE | ADEQUATE | ADEQUATE | OBSERVE | REVISIT |

Story 1-7 is the strongest implementation. Stories 1-4 and 1-5 carry the most dead code debt. Story 1-6 has the most impactful integration bug.

---

## Recurring Anti-Patterns

### 1. Compute-and-Discard (Stories 1-4, 1-5)

Methods or values are implemented, computed at runtime, and then silently discarded. Creates false confidence that checks are operational.

- **1-4:** ~125 lines of dead incremental helpers (`_detect_existing_data`, `_compute_missing_ranges`, `_validate_merge_boundary`, `_merge_data`) — implemented but never called
- **1-5:** `timezone_issues` computed at line 843 but never added to report or scoring. `gap_severity` computed at line 837, also unused

**Rule:** If a method is called and its return value unused, either wire it into the output or don't call it. Dead computation is worse than dead code — it actively misleads.

### 2. Cosmetic Config / Placeholder Fields (Stories 1-4, 1-5, 1-6)

Config keys that don't influence runtime behavior. Placeholder fields shipped with empty values.

- **1-4:** `_timeout` and `_backoff_factor` stored but never passed to `dk.fetch()`
- **1-5:** `config_hash` always blank (`""`) in quality reports
- **1-6:** Config keys `[data_pipeline.storage]` and `[data_pipeline.parquet]` not in `schema.toml`

**Rule:** Every config key must influence runtime behavior. Never ship placeholder fields — they erode operator trust. If one knob is fake, which others are?

### 3. Sound Core Logic, Broken CLI Wiring (Stories 1-5, 1-6)

The programmatic API works correctly, but the CLI (operator-facing entry point) has integration bugs.

- **1-6:** `converter_cli.py` looks for validated data at `raw/.../validated-data.csv` but `quality_checker.py` saves to `validated/.../{dataset_id}_validated.csv` — CLI will always fail on real runs

**Rule:** Integration tests must include CLI-to-CLI chain tests, not just API-level chaining.

### 4. Missing Manifest Lineage (Stories 1-6, 1-7, 1-8)

No stage manifest links back to the previous stage's manifest. The "reviewable artifact chain" goal is not yet achieved.

- **1-6:** Manifest has quality_score/rating but no reference to quality report path
- **1-7:** Produces no manifest at all
- **1-8:** Manifest has filenames but no per-file content hashes

**Rule:** Each stage's manifest should reference the previous stage's manifest (path + hash). This is a system concern — address in orchestrator, not per-story.

### 5. Hardcoded Value Sets vs. Contract Files (Stories 1-6, 1-7)

`VALID_SESSIONS` hardcoded as a frozenset when `arrow_schemas.toml` already defines the allowed values (including `"mixed"`). Two sources of truth that will drift.

**Rule:** Load enum values from contract files. One source of truth.

### 6. Existence-Only Idempotency (Stories 1-7, 1-8)

Skip-on-file-existence without content hash verification. Stale artifacts can be reused if source data changes without changing date ranges.

- **1-7:** `output_path.exists()` without hash check
- **1-8:** `dataset_id` excludes `config_hash` — reuse check ignores config changes

**Rule:** Idempotent skip needs hash-aware staleness detection. Compare source content hashes, not just file existence.

---

## Forward-Looking: What Must Be Addressed for Epic 2

### Critical (before or during Epic 2)

1. **CLI path mismatch in 1-6** — converter CLI cannot find 1-5's output. Must be fixed before orchestrator wires stages together.

2. **Timezone findings invisible to orchestrator** — 1-5 computes timezone issues but they appear nowhere in the quality report. Orchestrator cannot make re-download decisions without them.

3. **Config-aware cache invalidation** — when Epic 2 introduces multiple configurations (walk-forward, different parameters), the reuse check in `run_data_splitting()` must verify `config_hash`. Currently a one-line fix in `check_existing_dataset()`.

4. **Shared artifact write utilities** — three independent crash-safe write implementations should be consolidated before adding more stages.

### Important (should be tracked)

5. **`quarantined_periods` undercount** — report omits integrity-error quarantines and hardcodes `bar_count: 0` for gaps. `quarantined_percentage` is inaccurate. Evidence pack stories need accurate attribution.

6. **Manifest lineage chain** — formalize in orchestrator or artifact management stories.

7. **Contract-loaded enum values** — replace hardcoded `VALID_SESSIONS` frozenset with contract-file loading.

8. **`config_hash` must be populated** in quality reports — currently always blank.

---

## Simplification Opportunities

| Item | Story | Lines | Action |
|------|-------|-------|--------|
| Dead incremental helpers | 1-4 | ~125 | Remove or wire in |
| Dead `gap_severity` / `timezone_issues` | 1-5 | ~10 | Wire into report or remove calls |
| Cosmetic config keys | 1-4 | ~5 | Wire into `dk.fetch()` or remove |
| Placeholder `config_hash: ""` | 1-5 | ~3 | Populate or remove field |
| Duplicate crash-safe write | 1-5, 1-6, 1-7 | ~90 total | Consolidate to shared utility |
| 3-source config path fallback | 1-6 | ~20 | Single canonical path |
| CWD-walking `_find_contracts_path()` | 1-6 | ~15 | Config-resolved path |

---

## Where Codex Added Real Value

The adversarial pattern proved its worth. Five specific findings that might not have surfaced without Codex:

1. **Timezone findings fully discarded (1-5)** — not just not gating, but not even in the report. Silent data loss.
2. **CLI path mismatch (1-6)** — integration bug invisible to API-level testing.
3. **`quarantined_periods` undercount (1-5)** — DataFrame correct but report lies about it.
4. **Config-blind reuse (1-8)** — `dataset_id` excluding `config_hash` allows stale artifact reuse.
5. **Missing manifest lineage (1-6, 1-7)** — repeated flagging established it as systemic, not isolated.

Codex consistently rated REVISIT where Claude rated OBSERVE. Claude's reasoning: V1's single-pair, fixed-config envelope mitigates theoretical risks, and many concerns belong to future stories. Both perspectives have merit — Codex forces explicit acknowledgment of debt, Claude contextualises severity.

---

## PIR Process Assessment

**Cost:** ~44 minutes for 5 stories (~9 min/story: 6 min Codex + 3 min Claude)
**Reports:** 10 files generated (2 per story), ~120KB total
**Value:** Surfaced 6 recurring anti-patterns, 4 critical forward items, and 7 simplification opportunities that code reviews did not catch because they review code correctness, not system alignment.

**Recommendation:** Keep PIR in the pipeline for all future stories. The cost is low (~9 min) relative to the full story cycle (~32 min), and it catches a class of issues — "right code, wrong thing" — that no other pipeline step addresses.

---

## Remediation

All findings from this PIR have been consolidated into a remediation story:

**Story 1.10: Epic 1 PIR Remediation**
- **Location:** `_bmad-output/implementation-artifacts/1-10-epic1-pir-remediation.md`
- **Status:** ready-for-dev
- **Scope:** 4 critical fixes, 3 important fixes, 4 cleanup items across 8 tasks
- **Priority:** Tasks 1-4 (critical) must complete before Epic 2 orchestrator wiring

| Task | Type | What |
|------|------|------|
| 1 | Critical | Fix CLI path mismatch (1-6 → 1-5 output) |
| 2 | Critical | Surface timezone findings in quality report |
| 3 | Critical | Config-aware cache invalidation + populate config_hash |
| 4 | Critical | Consolidate crash-safe write to shared utility |
| 5 | Important | Fix quarantine undercount in reports |
| 6 | Important | Contract-loaded enum values (replace hardcoded frozensets) |
| 7 | Cleanup | Remove dead code (1-4 helpers, 1-5 gap_severity, cosmetic config) |
| 8 | Cleanup | Path cleanup (3-source fallback, CWD-walking) |
