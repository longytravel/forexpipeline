# Story Synthesis: 2-7-cost-model-rust-crate

## Codex Observations & Decisions

### 1. System Alignment — Workspace scope creep
**Codex said:** Task 1 bootstraps the whole Rust workspace including future crates (optimizer, validator, live_daemon, cost_calibrator) despite MVP "build only what's genuinely missing." Story should narrow scope.
**Decision:** AGREE (partially)
**Reasoning:** Cargo workspaces require all declared members to resolve, but there's no reason to declare crates this story doesn't need. Only cost_model, common (its dependency), and backtester (to validate D13 dep graph) are needed. Other crates should be added when their stories run.
**Action:** Trimmed Task 1 workspace members to only `crates/common`, `crates/cost_model`, `crates/backtester`. Added note that other crates are added as their stories are implemented.

### 2. System Alignment — EURUSD-only pip_value guard
**Codex said:** Hardcoded pip_value=0.0001 works against fidelity unless the story explicitly rejects non-EURUSD artifacts.
**Decision:** AGREE
**Reasoning:** Without a guard, a USDJPY artifact could be loaded and silently get wrong pip_value (0.0001 instead of 0.01). V1 is explicitly EURUSD-only. Fail-loud is the project pattern.
**Action:** Added AC #9 (pair must be "EURUSD" or fail loud). Added validation check in Task 3. Added test `test_pair_eurusd_only_v1()` in Task 6.

### 3. PRD Challenge — fill_price semantics undefined
**Codex said:** AC4 defines `apply_cost(fill_price, ...)` but never defines whether fill_price is mid, bid, ask, or pre-cost synthetic fill. This is the most dangerous real-world mistake — double-counting spread.
**Decision:** AGREE (as dev note, not as AC)
**Reasoning:** The cost model crate is a library that adjusts whatever price is passed in — it's agnostic to fill semantics by design. Defining fill_price semantics is the backtester's responsibility (Epic 3). However, documenting the expected contract prevents the double-counting mistake Codex flags.
**Action:** Added "Fill Price Semantics (downstream contract)" dev note explaining the V1 contract: fill_price is signal bar close, crate applies costs directionally, backtester must not double-count with bid/ask.

### 4. PRD Challenge — provenance field validation missing
**Codex said:** PRD traceability goals only partly reflected; validation covers pair/version/sessions but not `source` and `calibrated_at`.
**Decision:** DISAGREE
**Reasoning:** Codex appears to have missed Task 3's existing validation checks. The story already validates: `source` field against VALID_SOURCES list, `calibrated_at` against ISO 8601 regex. Both have been in the story since initial writing.
**Action:** None — already present in Task 3 validation checks.

### 5. Architecture Challenge — CLI location mismatch with D13
**Codex said:** D13 allocates CLI to `crates/cost_calibrator/`, but story puts `cost_model_cli` inline in `cost_model`. Direct architecture mismatch.
**Decision:** DISAGREE (but clarified)
**Reasoning:** The architecture's `cost_calibrator` crate is for *calibration* (building/updating cost model artifacts from market data) — Epic 7/8 scope. This story's `cost_model_cli` is for *validation and inspection* of existing artifacts — a different, simpler concern. These are two different tools. The epics file (Story 2.7 AC6) explicitly says "thin CLI binary cost_model_cli wraps the library for standalone cost model validation and inspection." However, the reconciliation was buried in a parenthetical — making it more visible is worthwhile.
**Action:** Expanded Task 5's D13 reconciliation note to clearly explain the distinction between validate/inspect (V1, inline) and calibration (cost_calibrator crate, Epic 7/8).

### 6. Architecture Challenge — HashMap vs typed session enum
**Codex said:** `HashMap<String, CostProfile>` is unnecessarily loose for 5 fixed sessions. Typed enum or fixed lookup would better fit D13's performance intent.
**Decision:** DISAGREE
**Reasoning:** Premature optimization for V1. HashMap lookup for 5 items is effectively O(1) with negligible overhead compared to actual backtest computation. The epics explicitly define `get_cost(session: &str)` — string-based API. Changing to typed enum would alter the API contract that Stories 2.8, 2.9, and Epic 3 depend on. String keys match how sessions flow through the system (JSON config → Python → Rust). A typed enum can be an internal optimization in Epic 3 if profiling warrants it.
**Action:** None.

### 7. Architecture Challenge — metadata: Option<Value> weakens contract
**Codex said:** `metadata: Option<serde_json::Value>` weakens the "artifact JSON is the contract" stance.
**Decision:** DISAGREE
**Reasoning:** The metadata field is intentionally opaque — it carries Python builder metadata (description, data_points, confidence_level) that the Rust crate stores but does not interpret. This is a forward-compatible design: the Python builder can add diagnostic info without requiring Rust crate changes. The story already documents this. Removing it would break the contract with Story 2.6's output.
**Action:** None.

### 8. Story Design — unknown field rejection
**Codex said:** Tasks never require rejecting unknown fields in JSON, only missing/invalid ones.
**Decision:** AGREE (on CostProfile, not on CostModelArtifact)
**Reasoning:** `#[serde(deny_unknown_fields)]` on CostProfile catches schema drift if the Python builder adds new cost parameters. On CostModelArtifact it would be too strict since `metadata: Option<Value>` is the intentional catch-all for forward compatibility. CostProfile has a tight 4-field contract that should be explicit.
**Action:** Added `#[serde(deny_unknown_fields)]` on CostProfile in Task 2. Added AC #10 for unknown CostProfile field rejection. Added test `test_cost_profile_unknown_fields_rejected()`.

### 9. Story Design — cross-runtime contract tests with Story 2.6 artifact
**Codex said:** Add contract tests that load the real/default Story 2.6 artifact fixture and prove Python/Rust compatibility.
**Decision:** DEFER
**Reasoning:** Story 2.9 (E2E Pipeline Proof) is explicitly designed to validate cross-story integration, including "the EURUSD cost model artifact loads successfully with session-aware profiles." The unit tests in this story already use fixtures matching Story 2.6's default artifact values. Adding a dependency on Story 2.6's actual output file would create a build-time ordering dependency that doesn't belong in unit tests.
**Action:** None — Story 2.9 covers this.

### 10. Downstream Impact — structured CLI output for evidence packs
**Codex said:** CLI output is console-only; later evidence-pack workflows will need retrofitting.
**Decision:** DISAGREE
**Reasoning:** V1 CLI is for operator inspection. Evidence-pack workflows are Epic 5+ territory. Adding `--json` output is a trivial addition later. Building for hypothetical future requirements violates the project's MVP philosophy and the anti-pattern guidelines ("do not design for hypothetical future requirements").
**Action:** None.

## Changes Applied
- **AC #9 added:** V1 EURUSD-only guard — non-EURUSD pairs fail loud with descriptive error
- **AC #10 added:** CostProfile rejects unknown fields via `deny_unknown_fields`
- **Task 1:** Trimmed workspace members to only cost_model + common + backtester (3 crates, not 8)
- **Task 2:** Added `#[serde(deny_unknown_fields)]` on CostProfile
- **Task 3:** Added `pair == "EURUSD"` V1 validation check; updated AC references to include #9, #10
- **Task 5:** Expanded D13 CLI reconciliation note (validate/inspect vs calibration distinction)
- **Task 6:** Added 2 new tests (pair guard, unknown fields); updated AC references
- **Dev Notes:** Added "Fill Price Semantics" section documenting the downstream contract

## Deferred Items
- Cross-runtime contract test loading actual Story 2.6 artifact → Story 2.9 (E2E Pipeline Proof)
- HashMap → typed session enum optimization → Epic 3 if profiling warrants
- CLI structured/JSON output → future story if evidence-pack workflows require it

## Verdict
VERDICT: IMPROVED
