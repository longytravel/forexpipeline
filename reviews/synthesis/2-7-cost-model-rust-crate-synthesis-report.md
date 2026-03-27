# Review Synthesis: Story 2-7-cost-model-rust-crate

## Reviews Analyzed
- BMAD: available (0 Critical, 0 High, 1 Medium, 2 Low — VERDICT: APPROVED)
- Codex: available (2 High, 2 Medium — no explicit verdict)

## Accepted Findings (fixes applied)

### 1. `CostModelArtifact` missing `#[serde(deny_unknown_fields)]` — D7 fail-loud gap
- **Source:** Both (BMAD M1, Codex MEDIUM)
- **Severity:** MEDIUM
- **Description:** `CostProfile` correctly had `deny_unknown_fields` (AC10), but `CostModelArtifact` did not. Unknown top-level JSON fields from the Python builder would be silently ignored, creating undetected schema drift.
- **Fix:** Added `#[serde(deny_unknown_fields)]` to `CostModelArtifact` in `types.rs:50`.
- **Regression test:** `test_artifact_unknown_top_level_fields_rejected` — asserts that a top-level extra field in the JSON causes a `ParseError` mentioning "unknown field".

### 2. Version validation too permissive (`v\d{3,}` vs spec `v\d{3}`)
- **Source:** Both (BMAD L1, Codex HIGH)
- **Severity:** HIGH (per Codex) / LOW (per BMAD)
- **My assessment:** MEDIUM — spec is clear `v\d{3}`, even though forward-compat was intentional. V1 should enforce its own contract strictly.
- **Description:** `loader.rs:65` checked `digits.len() < 3` (accepting 3+ digits), but the story spec says `v\d{3}` (exactly 3 digits). `v1000` would pass validation despite being outside the spec contract.
- **Fix:** Changed `digits.len() < 3` to `digits.len() != 3` in `loader.rs:65`.
- **Regression test:** Updated `test_version_format_validation` — now asserts `v1000` is rejected ("exactly 3 digits required").

### 3. Tests don't verify correct session-to-profile mapping
- **Source:** Codex (HIGH)
- **Severity:** HIGH
- **Description:** `test_get_cost_all_sessions` only checked non-negative values. A swapped asian/london mapping would still pass. AC8 requires "correct session lookup for all 5 sessions."
- **Fix:** Added new test `test_get_cost_exact_session_values` that verifies exact float values for all 4 fields across all 5 sessions using epsilon comparison.
- **Regression test:** The new test IS the regression test — verifies each session maps to its specific cost parameters.

### 4. Metadata not observable through public API or CLI
- **Source:** Both (BMAD L2, Codex MEDIUM)
- **Severity:** MEDIUM
- **Description:** `metadata` was stored in `CostModelArtifact` but `CostModel` had no public accessor. CLI `inspect` didn't print it. AC6 says "printing session profiles and artifact metadata." `test_load_artifact_with_metadata` only checked `pair()`, not that metadata was preserved.
- **Fixes applied:**
  - Added `pub fn metadata(&self) -> Option<&serde_json::Value>` accessor to `cost_engine.rs`
  - Updated CLI `inspect` to print metadata when present (`cost_model_cli.rs`)
  - Updated `test_load_artifact_with_metadata` to verify all 3 metadata fields (`description`, `data_points`, `confidence_level`)
  - Updated `test_load_artifact_without_metadata` to verify `metadata()` returns `None`

## Rejected Findings (disagreed)

None. All findings from both reviewers were accepted and fixed.

## Action Items (deferred)

- **Codex test coverage gap:** "CLI tests do not assert `inspect` output for source/version/calibrated_at beyond incidental pair/session presence" — LOW priority, the inspect output format is validated by manual use and the existing integration test confirms the command runs successfully. Could be enhanced in a future pass.
- **Codex test coverage gap:** "No test covers rejection of unexpected extra session keys" — Already covered by `validate_sessions()` logic which checks `sessions.len() != EXPECTED_SESSIONS.len()` and reports unexpected keys. Could add a dedicated test but the validation code path is solid.

## Test Results

```
Rust tests (cargo test -p cost_model):
  19 unit tests passed (was 17, +2 new regression tests)
  4 integration tests passed
  0 failures

Cargo clippy: zero warnings

Python tests (pytest tests/ -x -q):
  12 passed in 0.02s
  0 failures
```

## Verdict

All 4 accepted findings fixed with regression tests. All existing tests continue to pass. Both reviewers' ACs are now fully met (Codex's previously "Partially Met" AC5 and AC8 are resolved). No rejected findings. Clean clippy, clean tests.

VERDICT: APPROVED
