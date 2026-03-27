# Story 2.8: Strategy Engine Crate — Specification Parser & Indicator Registry

Status: review

## Story

As the **operator**,
I want the strategy engine crate to parse strategy specifications and maintain an indicator registry,
So that the Rust compute engine can validate and prepare strategies for evaluation in Epic 3.

## Acceptance Criteria

1. **Given** strategy specifications exist in the research-determined format (Story 2.3 schema at `contracts/strategy_specification.toml`)
   **When** the strategy engine crate is implemented
   **Then** a `src/rust/crates/strategy_engine/` library crate exists with a public API to load and validate strategy specifications
   [Source: architecture.md — D14; epics.md — Story 2.8 AC1; FR12]

2. **Given** a strategy specification artifact on disk
   **When** the crate parses it
   **Then** all sections are deserialized into in-memory representations: `metadata`, `entry_rules`, `exit_rules`, `position_sizing`, `optimization_plan`, `cost_model_reference`
   [Source: architecture.md — D10 specification contract; epics.md — Story 2.8 AC2]

3. **Given** the crate is initialized
   **When** the indicator registry is queried
   **Then** an `IndicatorRegistry` enumerates all supported indicator types (MA, EMA, ATR, Bollinger Bands) with their parameter signatures — matching the catalogue from Story 2.1's research output
   [Source: architecture.md — D10 minimum representable constructs; epics.md — Story 2.8 AC3]

4. **Given** a parsed strategy specification
   **When** indicator validation is performed
   **Then** every indicator referenced in `entry_rules` and `exit_rules` exists in the registry and has valid parameters (correct types, ranges within bounds)
   [Source: epics.md — Story 2.8 AC4; architecture.md — D10 rule engine]

5. **Given** a parsed strategy specification with filter definitions
   **When** filter validation is performed
   **Then** all filter types (`session`, `volatility`, `day_of_week`) reference valid configuration values — session filters use the canonical 5 session labels (asian, london, new_york, london_ny_overlap, off_hours)
   [Source: epics.md — Story 2.8 AC5; architecture.md — D10 session filters]

6. **Given** a parsed strategy specification with `cost_model_reference`
   **When** cross-validation is performed
   **Then** the crate validates that `cost_model_reference` points to a loadable cost model artifact by calling `cost_model::CostModel::load_from_file()` from Story 2.7's crate
   [Source: epics.md — Story 2.8 AC6; architecture.md — D13, D14]

7. **Given** a parsed strategy specification with one or more validation issues
   **When** `validate_spec(spec: &StrategySpec) -> Result<ValidatedSpec, Vec<ValidationError>>` is called
   **Then** ALL validation errors are collected and returned at once (not fail-on-first), each with a structured error type identifying the section, field, and reason
   [Source: epics.md — Story 2.8 AC7; architecture.md — D8 error handling]

8. **Given** the Cargo workspace configuration
   **When** the dependency graph is inspected
   **Then** `strategy_engine` depends on `common` and `cost_model` (for cross-validation), and is a standalone library crate that `backtester` and `live_daemon` will depend on in later epics
   [Source: architecture.md — D14 dependency graph; epics.md — Story 2.8 AC8]

## Tasks / Subtasks

- [x] **Task 1: Cargo workspace + crate initialization** (AC: #1, #8)
  - [x] Create `src/rust/crates/strategy_engine/Cargo.toml` with dependencies: `common` (path), `cost_model` (path), `serde`, `toml` (for TOML spec parsing), `thiserror` — `serde_json` not needed (TOML only per Story 2.3 contract)
  - [x] Create `src/rust/crates/strategy_engine/src/lib.rs` — re-export public API: `StrategySpec`, `ValidatedSpec`, `ValidationError`, `IndicatorRegistry`, `parse_spec_from_file()`, `parse_spec_from_str()`, `validate_spec()`
  - [x] Add `strategy_engine` to workspace members in `src/rust/Cargo.toml`
  - [x] Verify `cargo check --workspace` passes with the new crate

- [x] **Task 2: Type definitions — specification model** (AC: #2)
  - [x] Create `src/rust/crates/strategy_engine/src/types.rs` — types MUST align exactly with `contracts/strategy_specification.toml` schema from Story 2.3 (contract is source of truth, not this crate):
    - `StrategySpec` — top-level: `metadata: Metadata`, `entry_rules: Vec<EntryRule>`, `exit_rules: ExitRules`, `position_sizing: PositionSizing`, `optimization_plan: OptimizationPlan`, `cost_model_reference: String`
    - `Metadata` — `name: String`, `version: String`, `pair: String`, `timeframe: String`, `created_by: String`, `config_hash: String`
    - `EntryRule` — `condition: Condition`, `filters: Vec<Filter>`, `confirmation: Vec<Condition>`
    - `Condition` — `indicator: String`, `params: IndicatorParams`, `threshold: f64`, `comparator: Comparator` (enum: `GT`, `LT`, `CrossAbove`, `CrossBelow`, `EQ`)
    - `Filter` — enum: `Session { include: Vec<String> }`, `Volatility { indicator: String, params: IndicatorParams, threshold: f64, direction: FilterDirection }`, `DayOfWeek { include: Vec<u8> }`
    - `ExitRules` — `stop_loss: ExitConfig`, `take_profit: Option<ExitConfig>`, `trailing: Option<TrailingConfig>`
    - `ExitConfig` — `exit_type: ExitType` (enum: `FixedPips`, `AtrMultiple`, `Percentage`), `value: f64`
    - `TrailingConfig` — `trailing_type: TrailingType` (enum: `TrailingStop`, `ChandelierExit`), `params: IndicatorParams`
    - `PositionSizing` — `method: SizingMethod` (enum: `FixedRisk`, `FixedLots`), `risk_percent: Option<f64>`, `max_lots: f64`
    - `OptimizationPlan` — `parameter_groups: Vec<ParameterGroup>`, `group_dependencies: Vec<GroupDependency>`, `objective_function: ObjectiveFunction`
    - `ParameterGroup` — `name: String`, `parameters: Vec<OptParam>`
    - `OptParam` — `name: String`, `min: f64`, `max: f64`, `step: f64`
    - `GroupDependency` — `group_a: String`, `group_b: String`
    - `ObjectiveFunction` — `metric: String`, `direction: OptDirection` (enum: `Maximize`, `Minimize`)
    - `IndicatorParams` — struct with optional fields: `period: Option<u32>`, `period_fast: Option<u32>`, `period_slow: Option<u32>`, `price_source: Option<PriceSource>` (enum: `Close`, `Open`, `High`, `Low`, `HL2`), `multiplier: Option<f64>`. Each indicator type uses a subset of these fields; the registry's `validate_params()` enforces which fields are required/valid per indicator.
    - `ValidatedSpec` — newtype wrapper around `StrategySpec` (guarantees validation passed)
  - [x] Derive `serde::Deserialize`, `serde::Serialize`, `Debug`, `Clone` on all types
  - [x] Use `#[serde(deny_unknown_fields)]` on all structs to reject unknown keys (fail-loud per D7)

- [x] **Task 3: Specification parser — load and deserialize** (AC: #2)
  - [x] Create `src/rust/crates/strategy_engine/src/parser.rs`:
    - `pub fn parse_spec_from_file(path: &Path) -> Result<StrategySpec, StrategyEngineError>` — reads TOML file, deserializes (TOML is the only format locked by Story 2.3 contract)
    - `pub fn parse_spec_from_str(content: &str) -> Result<StrategySpec, StrategyEngineError>` — parses TOML from string
  - [x] Use `thiserror` for `StrategyEngineError`: `IoError`, `ParseError { details: String }` (schema/parse — fail-fast, single error), `ValidationErrors(Vec<ValidationError>)` (semantic — collect-all). These two error categories are distinct: parse errors are structural failures caught by serde/toml deserializer; validation errors are semantic failures caught by the validator.
  - [x] Fail-loud on malformed input: descriptive error messages with file path, line/field context where possible

- [x] **Task 4: Indicator registry** (AC: #3, #4)
  - [x] Create `src/rust/crates/strategy_engine/src/registry.rs`:
    - `IndicatorRegistry` struct with `BTreeMap<String, IndicatorDef>` (BTreeMap not HashMap — deterministic iteration order for reproducible validation output and enumeration)
    - `IndicatorDef` — `name: String`, `params: Vec<ParamDef>`, `description: String`
    - `ParamDef` — `name: String`, `param_type: ParamType` (enum: `Period`, `Multiplier`, `PriceSource`), `required: bool`, `default: Option<f64>`, `min: Option<f64>`, `max: Option<f64>`
    - `pub fn default_registry() -> IndicatorRegistry` — returns registry with all supported indicators pre-registered
    - `pub fn get(&self, name: &str) -> Option<&IndicatorDef>` — O(1) lookup
    - `pub fn validate_params(&self, indicator_name: &str, params: &IndicatorParams) -> Vec<ValidationError>` — checks params against registry definition
  - [x] Pre-register indicators matching D10 minimum representable constructs and Story 2.1 catalogue:
    - **Trend:** `MA` (period: 1-1000, price_source: close/open/high/low/hl2), `EMA` (same params)
    - **Volatility:** `ATR` (period: 1-1000), `BollingerBands` (period: 1-1000, multiplier: 0.1-10.0)
  - [x] Registry is extensible: `pub fn register(&mut self, name: &str, def: IndicatorDef)` for future indicators from Phase 0 research

- [x] **Task 5: Validation engine — collect-all-errors approach** (AC: #4, #5, #6, #7)
  - [x] Create `src/rust/crates/strategy_engine/src/validator.rs`:
    - `pub fn validate_spec(spec: &StrategySpec, registry: &IndicatorRegistry, cost_model_path: Option<&Path>) -> Result<ValidatedSpec, Vec<ValidationError>>`
    - `ValidationError` — `section: String`, `field: String`, `reason: String`, `severity: Severity` (enum: `Error`, `Warning`). Derive `serde::Serialize` on `ValidationError` and `Severity` for machine-readable output (Story 2.9, evidence packs)
  - [x] Validation checks (all accumulated, never fail-on-first):
    - **Metadata:** `name` non-empty, `pair` non-empty, `timeframe` valid (M1/M5/M15/M30/H1/H4/D1/W1), `config_hash` non-empty
    - **Entry rules:** At least one entry rule exists; each indicator name is in registry; params validated via `registry.validate_params()`; comparator is valid for indicator type
    - **Exit rules:** `stop_loss` is required (always); `exit_type` is valid; `value` > 0; trailing params validated if present; chandelier exit validated against ATR params
    - **Filters:** session filter labels must be in canonical set `{asian, london, new_york, london_ny_overlap, off_hours}`; volatility filter indicator must be in registry; day_of_week values in 0-6
    - **Position sizing:** `risk_percent` in (0.0, 100.0] if method is `FixedRisk`; `max_lots` > 0
    - **Optimization plan:** `min < max` for all param ranges; `step > 0`; `step <= (max - min)`; group names in dependencies must exist in parameter_groups; objective metric is non-empty
    - **Cost model reference:** If `cost_model_path` is provided, attempt `cost_model::CostModel::load_from_file(resolved_path)` — if it fails, add `ValidationError` (do NOT panic)
  - [x] Return `Ok(ValidatedSpec(spec.clone()))` if zero errors; `Err(errors)` if any errors exist

- [x] **Task 6: Unit + integration tests** (AC: #1-#8)
  - [x] Create test fixtures in `src/rust/crates/strategy_engine/tests/test_data/`:
    - `valid_ma_crossover.toml` — complete MA crossover strategy spec (reference from Story 2.3/2.9)
    - `invalid_unknown_indicator.toml` — references indicator not in registry
    - `invalid_bad_params.toml` — has out-of-range params (period: 0, step: 0, multiplier: -1.0) — note: period is `u32` so negative values are parse errors, not semantic validation errors; use period=0 and other boundary values for semantic validation testing
    - `invalid_missing_fields.toml` — missing required fields (no stop_loss, no entry_rules)
    - `invalid_bad_session.toml` — references session label "tokyo" (should be "asian")
    - `invalid_multi_error.toml` — has 3+ distinct errors to verify collect-all behavior
  - [x] Unit tests in `src/rust/crates/strategy_engine/src/registry.rs` (`#[cfg(test)]` module):
    - `test_default_registry_contains_all_indicators` — MA, EMA, ATR, BollingerBands all present
    - `test_registry_lookup_unknown_returns_none` — unknown indicator returns `None`
    - `test_validate_params_valid_ma` — valid MA params pass
    - `test_validate_params_invalid_period` — period=0 returns error (period is `u32`, so -1 is a parse error not a validation error)
    - `test_registry_is_extensible` — register new indicator, verify lookup works
  - [x] Unit tests in `src/rust/crates/strategy_engine/src/parser.rs`:
    - `test_parse_valid_toml_spec` — valid TOML deserializes to `StrategySpec`
    - `test_parse_malformed_toml_fails` — invalid TOML returns `ParseError` (not `ValidationErrors`)
    - `test_parse_unknown_fields_rejected` — extra fields cause `deny_unknown_fields` failure (returns `ParseError`)
    - `test_parse_error_is_distinct_from_validation_error` — parse failure returns `StrategyEngineError::ParseError`, not `ValidationErrors`
  - [x] Unit tests in `src/rust/crates/strategy_engine/src/validator.rs`:
    - `test_validate_valid_spec_returns_ok` — fully valid spec returns `Ok(ValidatedSpec)`
    - `test_validate_unknown_indicator_error` — unknown indicator produces `ValidationError`
    - `test_validate_bad_params_error` — out-of-range params produce error
    - `test_validate_missing_stop_loss_error` — no stop_loss produces error
    - `test_validate_bad_session_label_error` — "tokyo" instead of "asian" produces error
    - `test_validate_bad_optimization_ranges` — min >= max produces error
    - `test_validate_collects_all_errors` — spec with 3+ errors returns all of them (not fail-on-first)
    - `test_validate_cost_model_reference_valid` — valid cost model path passes
    - `test_validate_cost_model_reference_invalid` — bad path produces `ValidationError` (not panic)
  - [ ] Cross-runtime parity test in `src/rust/crates/strategy_engine/tests/parity_test.rs`:
    - `test_rust_agrees_with_python_on_valid_spec` — parse the same `valid_ma_crossover.toml` fixture that Story 2.3's Python validator uses; assert both accept it (verify by running Python validator in test setup if available, or by sharing the same test fixture files and comparing results manually during development)
    - `test_rust_agrees_with_python_on_invalid_spec` — parse a known-invalid fixture; assert both reject it for the same reasons
  - [x] Integration test in `src/rust/crates/strategy_engine/tests/integration_test.rs`:
    - `test_full_parse_and_validate_roundtrip` — load `valid_ma_crossover.toml` from test_data, parse, validate, assert `ValidatedSpec` returned
    - `test_cargo_workspace_dependency_graph` — verify `strategy_engine` depends on `common` and `cost_model` only (parse Cargo.toml)

- [x] **Task 7: Workspace dependency graph verification** (AC: #8)
  - [x] Verify `strategy_engine` Cargo.toml declares: `common = { path = "../common" }`, `cost_model = { path = "../cost_model" }`
  - [x] Verify `strategy_engine` does NOT depend on `backtester`, `optimizer`, `validator`, or `live_daemon` (it's a leaf dependency, not a consumer)
  - [x] Run `cargo check --workspace` to confirm no circular dependencies
  - [x] Run `cargo test -p strategy_engine` to confirm all tests pass

## Dev Notes

### Architecture Constraints

- **D14 (Strategy Engine Shared Crate):** This crate is the CORE of signal fidelity. Both `backtester` and `live_daemon` will depend on it in later epics. The public API must be stable. It is pure computation — NO I/O except spec loading, NO state management beyond the parsed spec.
- **D10 (Specification-Driven Execution):** Strategies are structured specifications, NOT code. The crate parses specification data and validates it. The evaluator (Epic 3) will interpret specs at runtime. This story builds the parsing and validation layer; the per-bar evaluation engine comes in Epic 3.
- **D13 (Cost Model Cross-Validation):** The `cost_model_reference` field in specs must be cross-validated against Story 2.7's `cost_model` crate. Import `cost_model` as a Cargo dependency and call its public API: `cost_model::CostModel::load_from_file(path: &Path) -> Result<CostModel, CostModelError>`. The cost_model_reference string in the spec should resolve to a file path (e.g., `data/cost_models/EURUSD_v003.json`). If `load_from_file` returns `Err`, add a `ValidationError` — do NOT propagate the error directly.
- **D8 (Error Handling):** Fail-loud at boundaries. Use `thiserror` for structured errors. The `validate_spec` function collects ALL errors (not fail-on-first) — this is a deliberate architectural decision for better developer experience.
- **D7 (Configuration):** Use `#[serde(deny_unknown_fields)]` on all deserialized structs. No silent defaults. If a field is unexpected, fail immediately with a clear error.

### Error Category Distinction (Parse vs Semantic)

Parse/schema errors and semantic validation errors are **distinct categories** with different behaviors:
- **Parse errors** (`StrategyEngineError::ParseError`): Structural failures from serde/TOML deserialization. Fail-fast — a single error is returned because the spec cannot be deserialized into typed structures.
- **Semantic validation errors** (`StrategyEngineError::ValidationErrors`): Logical failures caught by `validate_spec()`. Collect-all — every error is accumulated so the operator sees all issues at once.

Callers should expect: `parse_spec_from_file()` returns `ParseError` on structural issues; `validate_spec()` returns `ValidationErrors` on semantic issues. A spec that parses successfully may still fail validation.

### Contract Alignment — Source of Truth

The Rust types in `types.rs` MUST align exactly with `contracts/strategy_specification.toml` from Story 2.3. The contract file is the source of truth. If the contract changes, the Rust types must change to match — not the other way around. Any field, section, or enum in the Rust model that doesn't exist in the contract (or vice versa) is a bug.

### Validation Output as Machine-Readable Contract

`ValidatedSpec` and `Vec<ValidationError>` are the machine-readable output of this crate. Story 2.9's E2E proof and later evidence packs (FR39, FR58) will serialize these. Ensure:
- `ValidationError` derives `serde::Serialize` so it can be persisted as JSON
- `ValidatedSpec` round-trip (deserialize TOML → validate → serialize TOML) should produce deterministic output tied to spec version and `config_hash`
- Error output order is deterministic (BTreeMap registry + ordered validation checks)

### Scope Boundaries — What This Story Does NOT Do

- **NO per-bar evaluation logic** — that's Epic 3 (`backtester` crate). This story only parses, validates, and registers. Do NOT create `evaluator.rs`, `indicators.rs` (computation), `filters.rs`, or `exits.rs` — those files are Epic 3 scope per D14. This story's modules are: `types.rs`, `parser.rs`, `registry.rs`, `validator.rs`.
- **NO indicator computation** — the `indicators.rs` file in D14's architecture describes the indicator EVALUATION code (Epic 3). This story creates the indicator REGISTRY (what indicators exist, their parameter definitions). Actual MA/EMA/ATR computation is Epic 3.
- **NO trade simulation** — that's the `backtester` crate in Epic 3.
- **NO CLI binary** — unlike Story 2.7's `cost_model_cli`, this crate is library-only for V1. A CLI can be added later if needed.

### Pattern Continuity from Story 2.7

Follow the same patterns established in the `cost_model` crate (Story 2.7):
- **Crate structure:** `Cargo.toml` → `src/lib.rs` (re-exports) → `src/*.rs` (modules)
- **Error handling:** `thiserror` derive macros, structured error enums
- **Validation:** Fail-loud, descriptive errors, all-at-once collection
- **Dependencies:** Minimal — `serde`, `toml`, `thiserror`, workspace crates only. Add `serde_json` as a dev-dependency only (for serializing `ValidationError` in tests)
- **Testing:** Fixtures in `tests/test_data/`, unit tests as `#[cfg(test)]` modules, integration tests in `tests/`
- **Serde:** `#[serde(deny_unknown_fields)]` on all structs, `#[serde(rename_all = "snake_case")]` on enums

### V1 Scope Constraints

- **EURUSD only** — V1 supports a single pair. The `Metadata.pair` field should accept any string (for future multi-pair), but test fixtures and validation examples should use `EURUSD`.
- **Single strategy** — V1 runs one strategy through the pipeline. No multi-strategy registry or concurrent spec management needed.
- **Indicator set is minimal** — Only MA, EMA, ATR, BollingerBands. The registry is extensible but do NOT add indicators beyond these four.

### Data Naming Convention

Per project memory: ClaudeBackTester uses `EUR_USD`, Pipeline uses `EURUSD`. The `pair` field in `Metadata` should use the Pipeline convention (`EURUSD`). Any mapping to ClaudeBackTester format is a consumer-side concern, not this crate's responsibility.

### Session Labels — Canonical Set

The 5 canonical session labels (from D10, D13, and Story 2.6/2.7):
- `asian`
- `london`
- `new_york`
- `london_ny_overlap`
- `off_hours`

Session filter validation MUST reject any label not in this set. These are defined in `contracts/` and shared across Python and Rust.

### What to Reuse from ClaudeBackTester

Per baseline-to-architecture-mapping.md:
- **Strategy engine: KEEP & WRAP** — The baseline Rust evaluator is a core reusable asset. The indicator catalogue (MA, EMA, ATR, Bollinger) from Story 2.1's review should inform the registry's initial indicator set.
- **DO NOT** copy evaluation logic into this story — only catalogue what exists. Evaluation logic port happens in Epic 3.
- **Parameter signatures** from the baseline evaluator should match what the registry expects (period ranges, multiplier ranges, price source options).

## Anti-Patterns to Avoid

1. **Do NOT implement per-bar evaluation** — This story is parsing + validation only. The temptation to "get ahead" and implement indicator computation will create untested code that Epic 3 will need to rework.
2. **Do NOT fail-on-first in validation** — The architecture explicitly requires collecting ALL errors. Using `?` early-return in validate_spec is wrong. Use a `Vec<ValidationError>` accumulator.
3. **Do NOT hardcode indicator params in parser** — The parser deserializes from the spec file. The registry defines what's valid. Keep these concerns separate.
4. **Do NOT create a CLI binary** — This is a library crate only. Story 2.7 had a CLI (`cost_model_cli`) because it needed standalone validation. This crate's validation is programmatic only.
5. **Do NOT import backtester or live_daemon** — This crate is a LEAF dependency. It depends on `common` and `cost_model` only. Never create circular dependencies.
6. **Do NOT use `unwrap()` or `expect()` in library code** — All errors must be propagated via `Result`. Only use `unwrap` in tests.
7. **Do NOT silently ignore unknown fields** — `deny_unknown_fields` is mandatory. If a spec has an extra field, that's an error, not a warning.
8. **Do NOT invent indicator types beyond the D10 minimum** — Stick to MA, EMA, ATR, BollingerBands for V1. The registry is extensible by design; additional indicators come from Phase 0 research.

## Project Structure Notes

### Files to Create

```
src/rust/crates/strategy_engine/
├── Cargo.toml                    # depends on: common, cost_model, serde, toml, thiserror (no serde_json — TOML only)
├── src/
│   ├── lib.rs                    # Re-exports: StrategySpec, ValidatedSpec, ValidationError, IndicatorRegistry, parse_spec_from_file, validate_spec
│   ├── types.rs                  # All specification types: StrategySpec, Metadata, EntryRule, ExitRules, etc.
│   ├── parser.rs                 # parse_spec_from_file(), parse_spec_from_str(), SpecFormat
│   ├── registry.rs               # IndicatorRegistry, IndicatorDef, ParamDef, default_registry()
│   └── validator.rs              # validate_spec(), ValidationError, validation checks
└── tests/
    ├── test_data/
    │   ├── valid_ma_crossover.toml
    │   ├── invalid_unknown_indicator.toml
    │   ├── invalid_bad_params.toml
    │   ├── invalid_missing_fields.toml
    │   ├── invalid_bad_session.toml
    │   └── invalid_multi_error.toml
    └── integration_test.rs        # Full parse-and-validate roundtrip tests
```

### Files to Modify

- `src/rust/Cargo.toml` — Add `"crates/strategy_engine"` to workspace members

### Alignment with Architecture

- File structure matches D14 layout exactly (architecture.md line 1660-1667)
- Note: `evaluator.rs`, `indicators.rs` (computation), `filters.rs`, `exits.rs` from D14 are Epic 3 scope. This story creates the foundation (`types.rs`, `parser.rs`, `registry.rs`, `validator.rs`) that those modules will build upon.

## References

- [Source: architecture.md — Decision 10: Strategy Execution Model] — Three-layer model, specification contract, minimum representable constructs, rule engine evaluator
- [Source: architecture.md — Decision 14: Strategy Engine Shared Crate] — Crate responsibilities, file layout, signal fidelity rationale
- [Source: architecture.md — Decision 13: Cost Model Crate] — Cross-validation dependency, load_from_file API
- [Source: architecture.md — Decision 8: Error Handling] — Fail-loud at boundaries, structured error types
- [Source: architecture.md — Decision 7: Configuration] — deny_unknown_fields, fail-loud validation
- [Source: architecture.md — Project Structure (lines 1650-1667)] — Exact file paths for strategy_engine crate
- [Source: epics.md — Story 2.8 (line 802)] — Acceptance criteria, user story
- [Source: epics.md — Story 2.3] — Strategy specification schema, TOML contract, validator patterns
- [Source: epics.md — Story 2.1] — Indicator catalogue from ClaudeBackTester review
- [Source: epics.md — Story 2.9] — E2E proof requirements — this crate must parse locked specifications
- [Source: prd.md — FR9-FR13] — Strategy definition functional requirements
- [Source: prd.md — FR12] — Versioned, constrained specification requirement
- [Source: prd.md — FR19] — Signal fidelity (backtest = live)
- [Source: implementation-artifacts/2-7-cost-model-rust-crate.md] — Rust crate patterns, testing approach, cost_model public API
- [Source: implementation-artifacts/2-3-strategy-specification-schema-contracts.md] — Schema sections, validator logic, TOML contract
- [Source: baseline-to-architecture-mapping.md] — Strategy engine: KEEP & WRAP, indicator catalogue reuse

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

- Zero compiler warnings throughout implementation
- All 27 Rust tests pass (18 unit + 9 integration)
- All 10 Python @pytest.mark.live tests pass
- Full workspace test suite passes with no regressions

### Completion Notes List

- **Task 1:** Created `strategy_engine` crate scaffold with Cargo.toml (deps: common, cost_model, serde, toml, thiserror). Added to workspace members. `cargo check --workspace` passes.
- **Task 2:** Defined all specification types in `types.rs` aligned with `contracts/strategy_specification.toml` (source of truth). Used `IndicatorParams = BTreeMap<String, toml::Value>` for generic parameter handling (anti-pattern #3). All structs derive `Serialize`, `Deserialize`, `Debug`, `Clone` with `deny_unknown_fields`. Filter and TrailingConfig use adjacently tagged enums (`#[serde(tag = "type", content = "params")]`). Key contract alignment: comparator values match contract strings (`>`, `<`, `crosses_above`, etc.), indicator names match contract keys (`sma`/`ema`/`atr`/`bollinger_bands`), optimization objective is a string enum, cost_model_reference is a struct with `version` field.
- **Task 3:** Implemented TOML parser with `parse_spec_from_file()` and `parse_spec_from_str()`. `StrategyEngineError` has distinct `ParseError` (structural, fail-fast) and `ValidationErrors` (semantic, collect-all) variants.
- **Task 4:** Built `IndicatorRegistry` using BTreeMap for deterministic order. Pre-registered 4 V1 indicators matching `contracts/indicator_registry.toml`: sma, ema (period 1-1000), atr (period 1-1000), bollinger_bands (period 1-1000, num_std 0.1-10.0). Registry extensible via `register()`.
- **Task 5:** Implemented collect-all validation engine. Validates: metadata (name, pair, timeframe, config_hash), entry rules (indicator in registry, params validated, comparator valid), exit rules (type valid, value > 0, trailing params), filters (session labels in canonical set, volatility indicator in registry, day_of_week 0-6), position sizing (method, risk_percent bounds, max_lots > 0), optimization plan (min < max, step > 0, step <= range, group deps exist, objective valid), cost model cross-validation via `cost_model::load_from_file()`.
- **Task 6:** Created 6 test fixtures and 27 Rust tests. Integration tests cover full parse-validate roundtrip, all invalid fixtures, dependency graph verification, ValidationError JSON serialization, and TOML re-serialization roundtrip. Parity test deferred to manual verification (Python validator uses different structure).
- **Task 7:** Verified dependency graph: strategy_engine depends only on common + cost_model. No circular deps. `cargo check --workspace` and `cargo test --workspace` pass with zero warnings and zero failures.

### Implementation Plan

Types aligned to contract (not story type descriptions) per "contract is source of truth" rule. Used generic BTreeMap for indicator params to keep parser/registry concerns separate. Adjacently tagged serde enums for Filter and TrailingConfig match TOML's `type`+`params` structure. String-based comparators/exit_types validated in validator (not parser) to maintain clean parse vs validation error categories.

### Change Log

- 2026-03-16: Implemented Story 2.8 — strategy_engine crate with spec parser, indicator registry, and collect-all validation engine. 27 Rust tests + 10 Python live tests. Zero warnings.

### File List

**New files:**
- `src/rust/crates/strategy_engine/Cargo.toml`
- `src/rust/crates/strategy_engine/src/lib.rs`
- `src/rust/crates/strategy_engine/src/types.rs`
- `src/rust/crates/strategy_engine/src/parser.rs`
- `src/rust/crates/strategy_engine/src/error.rs`
- `src/rust/crates/strategy_engine/src/registry.rs`
- `src/rust/crates/strategy_engine/src/validator.rs`
- `src/rust/crates/strategy_engine/tests/integration_test.rs`
- `src/rust/crates/strategy_engine/tests/test_data/valid_ma_crossover.toml`
- `src/rust/crates/strategy_engine/tests/test_data/invalid_unknown_indicator.toml`
- `src/rust/crates/strategy_engine/tests/test_data/invalid_bad_params.toml`
- `src/rust/crates/strategy_engine/tests/test_data/invalid_missing_fields.toml`
- `src/rust/crates/strategy_engine/tests/test_data/invalid_bad_session.toml`
- `src/rust/crates/strategy_engine/tests/test_data/invalid_multi_error.toml`
- `src/python/tests/test_strategy/test_live_strategy_engine.py`

**Modified files:**
- `src/rust/Cargo.toml` — added `crates/strategy_engine` to workspace members
