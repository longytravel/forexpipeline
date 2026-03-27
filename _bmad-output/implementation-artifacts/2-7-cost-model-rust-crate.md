# Story 2.7: Cost Model Rust Crate

Status: review

## Story

As the **operator**,
I want the execution cost model implemented as a Rust library crate that the backtester can consume,
So that session-aware transaction costs are applied efficiently in the per-trade hot path.

## Acceptance Criteria

1. **Given** cost model artifacts exist in D13 JSON format (produced by Story 2.6's Python builder)
   **When** the Rust cost model crate is implemented
   **Then** a `src/rust/crates/cost_model/` library crate exists with a public API to load a cost model artifact and query session-aware costs
   [Source: architecture.md — D13; epics.md — Story 2.7 AC1]

2. **Given** a cost model JSON artifact on disk
   **When** the crate loads it at job start
   **Then** the artifact is parsed and an in-memory session lookup table (`HashMap<String, CostProfile>`) is built for O(1) access
   [Source: architecture.md — D13; FR21]

3. **Given** a loaded cost model
   **When** `get_cost(session: &str) -> CostProfile` is called
   **Then** it returns the spread and slippage distribution parameters (mean_spread_pips, std_spread, mean_slippage_pips, std_slippage) for the given session in O(1) time
   [Source: epics.md — Story 2.7 AC3; FR21]

4. **Given** a loaded cost model, a fill price, session label, and trade direction
   **When** `apply_cost(fill_price: f64, session: &str, direction: Direction) -> f64` is called
   **Then** the fill price is adjusted by session-aware spread and slippage — buys pay spread + slippage above fill, sells pay spread + slippage below fill
   [Source: epics.md — Story 2.7 AC4; FR14, FR21]

5. **Given** a cost model JSON artifact with invalid or missing fields
   **When** the crate attempts to load it
   **Then** loading fails with a descriptive error (fail-loud pattern) — no silent defaults, no partial loads
   [Source: architecture.md — D7 fail-loud validation; epics.md — Story 2.7 AC5]

6. **Given** the library crate is complete
   **When** a thin CLI binary `cost_model_cli` is built
   **Then** it wraps the library for standalone cost model validation (`validate` subcommand) and inspection (`inspect` subcommand), printing session profiles and artifact metadata
   [Source: architecture.md — D13; epics.md — Story 2.7 AC6]

7. **Given** the Cargo workspace
   **When** the dependency graph is inspected
   **Then** it matches D13: `backtester` depends on `cost_model` as a library — the crate is ready for Epic 3 integration
   [Source: architecture.md — D13; epics.md — Story 2.7 AC7]

8. **Given** the crate implementation
   **When** `cargo test` is run
   **Then** unit tests pass covering: correct session lookup for all 5 sessions, cost application math for buy/sell directions, artifact schema validation acceptance/rejection, graceful error handling on missing/corrupt/malformed artifacts
   [Source: epics.md — Story 2.7 AC8]

9. **Given** a cost model JSON artifact with `pair` != "EURUSD"
   **When** the crate attempts to load it
   **Then** loading fails with a descriptive error explaining that V1 only supports EURUSD (pip_value is hardcoded to 0.0001; JPY pairs require 0.01)
   [Source: architecture.md — D13; prd.md — MVP approach: build only what's genuinely needed for V1 EURUSD pipeline]

10. **Given** a `CostProfile` JSON object with unknown fields beyond the 4 defined parameters
    **When** the crate deserializes it
    **Then** deserialization fails with an error identifying the unknown field — preventing silent schema drift between Python builder and Rust consumer
    [Source: architecture.md — D7 fail-loud validation; Story 2.6 contract alignment]

## Tasks / Subtasks

- [x] **Task 1: Initialize Cargo workspace and cost_model crate** (AC: #1, #7)
  - [x] Create `src/rust/rust-toolchain.toml` pinning a stable Rust version (e.g., `channel = "stable"`) for reproducibility per architecture
  - [x] Create `src/rust/Cargo.toml` workspace manifest with `resolver = "2"`, including only the crate members needed by this story: `crates/common`, `crates/cost_model`, `crates/backtester` — other crates (strategy_engine, optimizer, validator, live_daemon, cost_calibrator) will be added to the workspace manifest as their stories are implemented
  - [x] Create `src/rust/crates/cost_model/Cargo.toml` with: `name = "cost_model"`, `edition = "2021"`, dependencies: `serde = { version = "1", features = ["derive"] }`, `serde_json = "1"`, `thiserror = "2"`, `common = { path = "../common" }`, dev-dependencies: `tempfile = "3"`
  - [x] Create `src/rust/crates/cost_model/src/lib.rs` with module declarations: `mod types;`, `mod loader;`, `mod cost_engine;`, `mod error;`, public re-exports
  - [x] Create stub `src/rust/crates/common/Cargo.toml` (name = "common", edition = "2021") so workspace resolves — this crate is not implemented in this story but must exist for workspace
  - [x] Create stub `src/rust/crates/backtester/Cargo.toml` with `cost_model` as a dependency: `cost_model = { path = "../cost_model" }` — validates D13 dependency graph
  - [x] Verify `cargo check --workspace` succeeds with stubs

- [x] **Task 2: Define types and data structures** (AC: #1, #2, #3)
  - [x] Create `src/rust/crates/cost_model/src/types.rs`:
    - `pub struct CostProfile { pub mean_spread_pips: f64, pub std_spread: f64, pub mean_slippage_pips: f64, pub std_slippage: f64 }`
    - `pub enum Direction { Buy, Sell }` with `serde::Deserialize`
    - `pub struct CostModelArtifact { pub pair: String, pub version: String, pub source: String, pub calibrated_at: String, pub sessions: HashMap<String, CostProfile>, pub metadata: Option<serde_json::Value> }` with `serde::Deserialize` — the `metadata` field is opaque data from the Python builder (description, data_points, confidence_level); the Rust crate stores but does not interpret it
    - `pub struct CostModel` (loaded, validated, ready-to-query wrapper holding the artifact data)
  - [x] Derive `Debug, Clone, serde::Deserialize, serde::Serialize` on all public types
  - [x] Add `#[serde(rename_all = "snake_case")]` on `CostModelArtifact` and `CostProfile` for explicit snake_case JSON field mapping
  - [x] Add `#[serde(deny_unknown_fields)]` on `CostProfile` to catch schema drift between Python builder and Rust consumer — if Story 2.6 adds a new cost parameter, this crate must be updated explicitly (AC #10)
  - [x] Implement `std::fmt::Display` for `CostProfile`: `spread: {mean}±{std} pips, slippage: {mean}±{std} pips` — used by CLI `inspect` subcommand
  - [x] Document expected session keys as constants: `ASIAN`, `LONDON`, `NEW_YORK`, `LONDON_NY_OVERLAP`, `OFF_HOURS` — matching `contracts/session_schema.toml` values exactly

- [x] **Task 3: Implement artifact loader with fail-loud validation** (AC: #2, #5, #9, #10)
  - [x] Create `src/rust/crates/cost_model/src/error.rs`:
    - `pub enum CostModelError` using `thiserror::Error`: `IoError(#[from] std::io::Error)`, `ParseError(#[from] serde_json::Error)`, `ValidationError(String)`, `SessionNotFound(String)`
  - [x] Create `src/rust/crates/cost_model/src/loader.rs`:
    - `pub fn load_from_file(path: &Path) -> Result<CostModel, CostModelError>` — reads JSON, deserializes, validates, returns loaded CostModel
    - `pub fn load_from_str(json: &str) -> Result<CostModel, CostModelError>` — for testing without filesystem
    - Validation checks (fail-loud on ANY failure):
      - `pair` field is non-empty
      - `pair` field equals "EURUSD" — V1 only supports EURUSD; fail loud with descriptive error for other pairs explaining pip_value limitation (AC #9)
      - `version` field matches pattern `v\d{3}` (e.g., v001)
      - `source` field is one of: `research`, `tick_analysis`, `live_calibration`, or a `+`-separated combination (e.g., `research+live_calibration`) — matches Story 2.6's `VALID_SOURCES`
      - `calibrated_at` field is a valid ISO 8601 datetime string — validate with a regex `\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z` (avoid adding `chrono` dependency just for this)
      - `sessions` map contains exactly the 5 expected session keys (asian, london, new_york, london_ny_overlap, off_hours)
      - All CostProfile fields are non-negative (spreads/slippage cannot be negative)
      - All `std_*` fields are non-negative (standard deviations)
      - No NaN or Infinity values — use `f64::is_finite()` check on every numeric field; serde_json deserializes NaN/Infinity as `null` by default so also guard the deserialization path

- [x] **Task 4: Implement cost engine (get_cost + apply_cost)** (AC: #3, #4)
  - [x] Create `src/rust/crates/cost_model/src/cost_engine.rs`:
    - `impl CostModel`:
      - `pub fn get_cost(&self, session: &str) -> Result<&CostProfile, CostModelError>` — O(1) HashMap lookup, returns `Err(SessionNotFound)` for unknown sessions
      - `pub fn apply_cost(&self, fill_price: f64, session: &str, direction: Direction) -> Result<f64, CostModelError>` — applies mean spread + mean slippage to fill price:
        - **Buy:** `fill_price + (mean_spread_pips + mean_slippage_pips) * pip_value` (worse fill = higher price)
        - **Sell:** `fill_price - (mean_spread_pips + mean_slippage_pips) * pip_value` (worse fill = lower price)
        - Pip value: use standard forex pip = 0.0001 for most pairs (hardcode for now; Epic 3 can generalize for JPY pairs where pip = 0.01)
      - `pub fn pair(&self) -> &str` — returns the pair this model covers
      - `pub fn version(&self) -> &str` — returns artifact version
      - `pub fn sessions(&self) -> &HashMap<String, CostProfile>` — returns all session profiles

- [x] **Task 5: Implement CLI binary** (AC: #6)
  - [x] Create `src/rust/crates/cost_model/src/bin/cost_model_cli.rs` as an inline `[[bin]]` in cost_model's Cargo.toml
    - **D13 reconciliation:** Architecture allocates `cost_calibrator/` crate for the CLI wrapping cost_model lib. That crate's purpose is _calibration_ (building/updating artifacts from market data — Epic 7/8 scope). This story's `cost_model_cli` serves a different, simpler purpose: _validation and inspection_ of existing artifacts. V1 decision: inline validate/inspect as a `[[bin]]` in cost_model; calibration CLI deferred to cost_calibrator crate when Epic 7/8 is implemented.
  - [x] Subcommands (use `std::env::args` — no need for clap in V1):
    - `validate <path>` — loads artifact, prints "Valid" + pair/version/session count, or prints validation error and exits with code 1
    - `inspect <path>` — loads artifact, prints formatted table: pair, version, source, calibrated_at, then each session with its 4 cost parameters
  - [x] Register binary in `Cargo.toml` via `[[bin]]` section: `name = "cost_model_cli"`, `path = "src/bin/cost_model_cli.rs"`

- [x] **Task 6: Write unit tests** (AC: #8, #9, #10)
  - [x] In `src/rust/crates/cost_model/src/lib.rs` or dedicated test modules via `#[cfg(test)]`:
    - `test_load_valid_artifact()` — load a valid JSON string, verify all fields parsed correctly
    - `test_load_invalid_missing_session()` — JSON missing one session key → `ValidationError`
    - `test_load_invalid_negative_spread()` — negative mean_spread_pips → `ValidationError`
    - `test_load_invalid_json()` — malformed JSON → `ParseError`
    - `test_load_missing_file()` — non-existent path → `IoError`
    - `test_get_cost_all_sessions()` — verify each of the 5 sessions returns correct CostProfile
    - `test_get_cost_unknown_session()` — unknown session name → `SessionNotFound`
    - `test_apply_cost_buy()` — verify buy direction adds cost to fill price
    - `test_apply_cost_sell()` — verify sell direction subtracts cost from fill price
    - `test_apply_cost_symmetry()` — buy and sell adjustments are symmetric in magnitude
    - `test_version_format_validation()` — version "v001" passes, "1" fails, "v1" fails
    - `test_load_artifact_with_metadata()` — valid JSON with metadata object parses correctly, metadata preserved
    - `test_load_artifact_without_metadata()` — valid JSON without metadata field parses correctly (metadata defaults to None)
    - `test_source_field_validation()` — "research" passes, "research+live_calibration" passes, "invalid_source" fails
    - `test_calibrated_at_validation()` — valid ISO 8601 passes, malformed datetime fails
    - `test_pair_eurusd_only_v1()` — pair "EURUSD" passes, pair "USDJPY" fails with descriptive error about V1 pip_value limitation
    - `test_cost_profile_unknown_fields_rejected()` — JSON CostProfile with extra field (e.g., "max_spread": 2.0) fails deserialization due to `deny_unknown_fields`
  - [x] Create `src/rust/crates/cost_model/tests/integration_test.rs`:
    - `test_load_from_file()` — write a valid artifact to tempfile, load via `load_from_file`, verify round-trip
    - `test_cli_validate_valid()` — spawn `cost_model_cli validate` on a valid artifact file, check exit code 0
    - `test_cli_validate_invalid()` — spawn on invalid artifact, check exit code 1
    - `test_cli_inspect()` — spawn `cost_model_cli inspect`, verify output contains pair and session names

- [x] **Task 7: Verify workspace dependency graph** (AC: #7)
  - [x] Run `cargo check --workspace` — all crates (with stubs) must compile
  - [x] Verify `backtester/Cargo.toml` has `cost_model = { path = "../cost_model" }` dependency
  - [x] Run `cargo tree -p backtester` and confirm `cost_model` appears as dependency
  - [x] Run `cargo test -p cost_model` — all tests pass
  - [x] Run `cargo clippy -p cost_model -- -D warnings` — zero warnings

## Dev Notes

### Architecture Constraints (MUST follow)

- **D13 (Cost Model Crate):** This is a **library crate**, not a binary. The backtester imports it directly — no process boundary. The cost model artifact is loaded once at job start and queried per fill in the hot path. Performance is critical.
- **D13 (Cargo Dependency Graph):** `backtester → cost_model` (lib). `optimizer → backtester`. `validator → backtester`. The cost_model crate must NOT depend on backtester, strategy_engine, or any other crate except `common` (if needed).
- **D7 (Fail-Loud Validation):** All schema validation must fail loudly on invalid data. No silent defaults. No partial loads. If the artifact is invalid, the entire load operation fails with a descriptive error.
- **D2 (Artifact Format):** Cost model artifacts are JSON files (not Arrow IPC). Arrow IPC is for compute outputs (backtest results, equity curves). The cost model is a configuration artifact, not a compute artifact.
- **D14 (Strategy Engine):** Story 2.8 will add `strategy_engine` crate that cross-validates `cost_model_reference` against this crate. The public API must be stable enough for that dependency.

### Cost Model Artifact Format (D13 — canonical reference)

```json
{
  "pair": "EURUSD",
  "version": "v003",
  "source": "research+live_calibration",
  "calibrated_at": "2026-03-13T14:00:00Z",
  "sessions": {
    "asian":             { "mean_spread_pips": 1.2, "std_spread": 0.3, "mean_slippage_pips": 0.1, "std_slippage": 0.05 },
    "london":            { "mean_spread_pips": 0.8, "std_spread": 0.2, "mean_slippage_pips": 0.05, "std_slippage": 0.03 },
    "new_york":          { "mean_spread_pips": 0.9, "std_spread": 0.25, "mean_slippage_pips": 0.06, "std_slippage": 0.03 },
    "london_ny_overlap": { "mean_spread_pips": 0.6, "std_spread": 0.15, "mean_slippage_pips": 0.03, "std_slippage": 0.02 },
    "off_hours":         { "mean_spread_pips": 2.0, "std_spread": 0.8, "mean_slippage_pips": 0.2, "std_slippage": 0.1 }
  }
}
```

### Session Keys (authoritative source: `contracts/session_schema.toml`)

The 5 session keys are: `asian`, `london`, `new_york`, `london_ny_overlap`, `off_hours`. These must match exactly — the Rust crate validates against these during artifact load. Session time ranges are in `config/base.toml` under `[sessions]` but the crate does NOT need to know about time ranges — it only maps session labels to cost profiles. Session classification (timestamp → session label) happens elsewhere (backtester or Python orchestrator).

### Fill Price Semantics (downstream contract)

The `apply_cost(fill_price, ...)` function does NOT define what `fill_price` represents — it adjusts whatever price is passed in. The caller (backtester in Epic 3) is responsible for determining fill_price semantics. The expected V1 contract: `fill_price` is the **signal bar's close price** (the price at which the backtester determines a fill would occur before costs). Spread and slippage are then applied on top to simulate realistic execution. This crate is agnostic — it only applies `(mean_spread + mean_slippage) * pip_value` directionally. The backtester must not double-count by also modeling bid/ask separately.

### Pip Value

Standard forex pip = 0.0001 for most pairs. JPY pairs use 0.01. For V1, hardcode 0.0001 since the default pair is EURUSD. Add a `pip_value` field to CostModelArtifact or CostModel in the future if multi-pair support requires it. Mark this with a `// TODO: Epic 3 — generalize pip_value for JPY pairs` comment.

### Existing Project State

- **Rust workspace:** `src/rust/crates/` directory exists with empty subdirectories for all crates (cost_model, common, backtester, strategy_engine, optimizer, validator, live_daemon, cost_calibrator). No `Cargo.toml` files exist yet — this story creates the workspace.
- **Contracts:** `contracts/session_schema.toml` exists and defines session values. `contracts/cost_model_schema.toml` does NOT exist yet (Story 2.6 creates it on the Python side).
- **Config:** `config/base.toml` exists with `[sessions]` section defining session time ranges in UTC.
- **Artifacts:** `artifacts/` directory exists at project root. Cost model artifacts will be at `artifacts/cost_models/{PAIR}/v{NNN}.json` (created by Story 2.6's Python builder).

### Previous Story Intelligence (from Story 2.6)

Story 2.6 creates the Python-side cost model builder and JSON artifacts that this crate consumes. Key learnings:

- **Artifact JSON is the contract** between Python (builder) and Rust (consumer). The JSON schema defined in Story 2.6 is authoritative — this crate's `serde::Deserialize` types must match exactly.
- **Default EURUSD artifact** is created and auto-approved as v001 by Story 2.6. Use these values for test fixtures:
  ```json
  {
    "pair": "EURUSD",
    "version": "v001",
    "source": "research",
    "calibrated_at": "2026-03-15T00:00:00Z",
    "sessions": {
      "asian":             { "mean_spread_pips": 1.2, "std_spread": 0.4, "mean_slippage_pips": 0.1, "std_slippage": 0.05 },
      "london":            { "mean_spread_pips": 0.8, "std_spread": 0.3, "mean_slippage_pips": 0.05, "std_slippage": 0.03 },
      "london_ny_overlap": { "mean_spread_pips": 0.6, "std_spread": 0.2, "mean_slippage_pips": 0.03, "std_slippage": 0.02 },
      "new_york":          { "mean_spread_pips": 0.9, "std_spread": 0.3, "mean_slippage_pips": 0.06, "std_slippage": 0.03 },
      "off_hours":         { "mean_spread_pips": 1.5, "std_spread": 0.6, "mean_slippage_pips": 0.15, "std_slippage": 0.08 }
    }
  }
  ```
- **Manifest pattern:** Story 2.6 uses `latest_approved_version` pointer in manifest.json (same pattern as Story 2.5's versioner.py). The Rust crate does NOT read manifests — it receives a resolved file path from the orchestrator.
- **Pair naming convention:** EURUSD (no underscores). ClaudeBackTester uses EUR_USD — do NOT follow that pattern.
- **V1 deterministic semantics:** Story 2.6 explicitly states "V1 consumer uses mean_spread_pips and mean_slippage_pips directly (deterministic). std_spread and std_slippage stored for future stochastic sampling but NOT consumed in V1."
- **`safe_write()` pattern:** Story 2.6 uses write-then-rename for crash safety. Not applicable to this crate (read-only consumer), but the pattern is established for when `cost_calibrator` writes updated artifacts in Epic 7/8.

### Cross-Story Dependencies

| Story | Relationship | What This Story Needs/Provides |
|---|---|---|
| **2.6** (prerequisite) | Produces cost model JSON artifacts | This story's crate **consumes** those artifacts. The JSON schema must match D13 format exactly. |
| **2.8** (downstream) | strategy_engine cross-validates cost_model_reference | This story's public API (`load_from_file`) must be callable from strategy_engine. |
| **2.9** (downstream) | E2E pipeline proof | The cost_model crate must successfully load the default EURUSD artifact created by Story 2.6. |
| **Epic 3** (downstream) | Backtester integration | The backtester crate will call `apply_cost()` in the per-trade hot path. API must be stable. |

### What to Reuse from ClaudeBackTester

**None** — cost model is entirely new. Baseline uses flat spread assumptions, not session-aware profiles.

## Anti-Patterns to Avoid

1. **DO NOT add process boundaries.** The cost model is a library crate consumed via `use cost_model::CostModel`. Do NOT create a subprocess, gRPC service, or any IPC mechanism. D13 explicitly states this would "destroy performance."

2. **DO NOT silently default missing sessions.** If the artifact is missing a session key, fail loud. Do not insert a fallback "default" session profile. D7 pattern.

3. **DO NOT use floating-point comparison with `==`.** When testing cost application math, use an epsilon-based comparison (e.g., `(a - b).abs() < 1e-10`). Floating-point arithmetic is not exact.

4. **DO NOT hardcode artifact file paths.** The crate takes a `&Path` argument — it does not know where artifacts live. Path resolution is the caller's responsibility.

5. **DO NOT add runtime dependencies on `config/base.toml`.** The crate loads a cost model artifact (JSON). It does not read TOML config. Session time ranges and config are the orchestrator's concern.

6. **DO NOT add stochastic cost sampling in this story.** The `std_spread` and `std_slippage` fields exist for future Monte Carlo simulation (Epic 5). The `apply_cost()` function uses ONLY `mean_spread_pips` and `mean_slippage_pips`. The `std_*` fields are stored but unused by cost_engine in this story. Do not add random number generation.

7. **DO NOT pull in heavy dependencies.** This is a focused library crate. Dependencies should be minimal: `serde`, `serde_json`, `thiserror`. No `tokio`, no `arrow`, no `clap` (use raw `std::env::args` for CLI).

8. **DO NOT implement session classification (timestamp → session label).** This crate maps session labels to cost profiles. The logic that determines which session a trade falls in lives elsewhere.

## Project Structure Notes

### Files to Create

```
src/rust/
├── rust-toolchain.toml                     # Pinned Rust version (NEW)
├── Cargo.toml                              # Workspace manifest (NEW)
├── crates/
│   ├── cost_model/
│   │   ├── Cargo.toml                      # Library crate manifest (NEW)
│   │   ├── src/
│   │   │   ├── lib.rs                      # Public API re-exports (NEW)
│   │   │   ├── types.rs                    # CostProfile, Direction, CostModelArtifact, CostModel (NEW)
│   │   │   ├── loader.rs                   # load_from_file, load_from_str, validation (NEW)
│   │   │   ├── cost_engine.rs              # get_cost, apply_cost impl (NEW)
│   │   │   ├── error.rs                    # CostModelError enum (NEW)
│   │   │   └── bin/
│   │   │       └── cost_model_cli.rs       # CLI binary (NEW)
│   │   └── tests/
│   │       └── integration_test.rs         # Integration tests (NEW)
│   ├── common/
│   │   ├── Cargo.toml                      # Stub manifest (NEW)
│   │   └── src/
│   │       └── lib.rs                      # Empty stub (NEW)
│   └── backtester/
│       ├── Cargo.toml                      # Stub manifest with cost_model dep (NEW)
│       └── src/
│           └── lib.rs                      # Empty stub (NEW)
```

### Files NOT to Modify

- `contracts/session_schema.toml` — read-only reference, do not modify
- `config/base.toml` — read-only reference, do not modify
- Any Python source in `src/python/` — this is a pure Rust story

### Alignment with Architecture

- Crate path `src/rust/crates/cost_model/` matches architecture directory layout (architecture.md — project structure section)
- Empty crate directories already exist — do NOT create additional crate directories beyond what exists
- Workspace members list should include all existing crate directories even if they're stubs

## References

- [Source: architecture.md — Decision 13: Cost Model Crate Resolution] — D13 defines the crate as a library, Cargo dependency graph, artifact format, CLI wrapper
- [Source: architecture.md — Decision 14: Strategy Engine Shared Crate] — D14 dependency graph showing strategy_engine → cost_model cross-validation
- [Source: architecture.md — Decision 7: Configuration & Validation] — D7 fail-loud validation pattern
- [Source: architecture.md — Decision 2: Artifact Schema & Storage] — D2 artifact directory structure
- [Source: epics.md — Story 2.7: Cost Model Rust Crate] — Full acceptance criteria
- [Source: epics.md — Story 2.8: Strategy Engine Crate] — Downstream dependency, cross-validates cost_model_reference
- [Source: epics.md — Story 2.9: E2E Pipeline Proof] — Uses cost model for pipeline proof
- [Source: contracts/session_schema.toml] — Authoritative session key values
- [Source: config/base.toml — [sessions]] — Session time ranges (UTC)
- [Source: baseline-mapping.md — Compute Tier] — Cost model is "build new" (not in baseline)
- [Source: prd.md — FR20, FR21, FR22] — Execution cost modeling functional requirements

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Debug Log References
- cargo check --workspace: clean build, no warnings
- cargo test -p cost_model: 17 unit tests + 4 integration tests = 21 Rust tests, all passing
- cargo clippy -p cost_model -- -D warnings: zero warnings
- cargo tree -p backtester: confirms cost_model dependency (D13 graph)
- pytest -m live tests/test_cost_model/test_rust_crate.py: 7 live tests, all passing

### Completion Notes List
- ✅ Task 1: Workspace initialized with rust-toolchain.toml (stable), Cargo.toml (resolver=2), cost_model/common/backtester crate manifests. cargo check --workspace passes.
- ✅ Task 2: types.rs defines CostProfile (deny_unknown_fields), Direction, CostModelArtifact (with optional metadata), CostModel wrapper. Session constants exported. Display impl for CostProfile.
- ✅ Task 3: error.rs defines CostModelError with 4 variants (IoError, ParseError, ValidationError, SessionNotFound). loader.rs implements load_from_file/load_from_str with comprehensive fail-loud validation: pair (EURUSD-only V1), version (v\d{3}+), source (valid components), calibrated_at (ISO 8601), sessions (exactly 5 expected keys), CostProfile fields (non-negative, finite).
- ✅ Task 4: cost_engine.rs implements get_cost (O(1) HashMap lookup), apply_cost (deterministic mean spread+slippage * PIP_VALUE, directional), plus accessors pair/version/sessions/source/calibrated_at.
- ✅ Task 5: cost_model_cli binary with validate and inspect subcommands. Uses std::env::args (no clap). Registered as [[bin]] in Cargo.toml.
- ✅ Task 6: 17 unit tests in lib.rs #[cfg(test)] covering all specified scenarios. 4 integration tests in tests/integration_test.rs covering file I/O and CLI binary invocation.
- ✅ Task 7: cargo check --workspace, cargo tree -p backtester (confirms D13 graph), cargo test -p cost_model (21 pass), cargo clippy (zero warnings) — all verified.

### File List

**New files:**
- src/rust/rust-toolchain.toml — Pinned stable Rust toolchain
- src/rust/Cargo.toml — Workspace manifest (resolver=2, 3 member crates)
- src/rust/crates/cost_model/Cargo.toml — Library crate manifest with [[bin]]
- src/rust/crates/cost_model/src/lib.rs — Public API re-exports + 17 unit tests
- src/rust/crates/cost_model/src/types.rs — CostProfile, Direction, CostModelArtifact, CostModel, session constants
- src/rust/crates/cost_model/src/error.rs — CostModelError enum (thiserror)
- src/rust/crates/cost_model/src/loader.rs — load_from_file, load_from_str, fail-loud validation
- src/rust/crates/cost_model/src/cost_engine.rs — get_cost, apply_cost, accessor methods
- src/rust/crates/cost_model/src/bin/cost_model_cli.rs — CLI binary (validate, inspect)
- src/rust/crates/cost_model/tests/integration_test.rs — 4 Rust integration tests
- src/rust/crates/common/Cargo.toml — Stub crate manifest
- src/rust/crates/common/src/lib.rs — Stub lib
- src/rust/crates/backtester/Cargo.toml — Stub with cost_model dependency
- src/rust/crates/backtester/src/lib.rs — Stub lib re-exporting cost_model
- src/python/tests/test_cost_model/test_rust_crate.py — 7 @pytest.mark.live integration tests

## Change Log
- 2026-03-16: Story 2.7 implemented — Rust cost_model library crate with types, loader (fail-loud validation), cost engine (get_cost/apply_cost), CLI binary (validate/inspect), comprehensive test suite (21 Rust tests + 7 Python live tests). Workspace initialized with common and backtester stubs validating D13 dependency graph.
