# Story 2.3: Strategy Specification Schema & Contracts

Status: review

## Story

As the operator,
I want the strategy specification format defined with schema validation and contract enforcement,
so that every strategy is constrained, reproducible, and machine-verifiable before it enters the pipeline.

## Acceptance Criteria

1. **Given** the research-determined specification format (D10, Phase 0 output from Story 2.2)
   **When** the strategy specification schema is created
   **Then** a schema definition exists in `contracts/strategy_specification.toml` covering all D10 specification sections:
   - metadata
   - entry_rules
   - exit_rules
   - position_sizing
   - optimization_plan
   - cost_model_reference (FR12)

2. **Given** the schema definition exists
   **When** evaluating schema coverage
   **Then** the schema supports the minimum representable constructs from D10:
   - trend indicators (MA, EMA, etc.)
   - volatility indicators (ATR, Bollinger, etc.)
   - exit types (stop_loss, take_profit, trailing, chandelier)
   - session filters (Asian, London, NY, overlap, off-hours)
   - volatility filters
   - timeframe, pair, position sizing (FR12)

3. **Given** the strategy specification schema
   **When** defining optimization_plan sections
   **Then** optimization_plan supports:
   - parameter_groups with ranges/step sizes
   - group_dependencies
   - objective_function
   - allowing strategies to define their own optimization stages (FR13)

4. **Given** a strategy specification
   **When** the Python schema validator is invoked
   **Then** it fails loud on any specification that doesn't conform to the contract

5. **Given** a candidate strategy specification
   **When** validation is performed
   **Then** the validator checks:
   - all referenced indicator types are recognized
   - parameter ranges are valid (min < max, step > 0)
   - required fields are present
   - cost_model_reference points to a valid version string

6. **Given** a strategy specification is saved
   **When** it is saved again with modifications
   **Then** specification versioning works:
   - each save creates a new version (v001, v002, ...)
   - previous versions are immutable (FR12)

7. **Given** a specification version is being persisted
   **When** the specification is saved to disk
   **Then** specification files are written using crash-safe write pattern (NFR15)

8. **Given** Epic 2 completion requirements
   **When** Story 2.3 is delivered
   **Then** a sample MA crossover strategy specification exists as a reference implementation

## Tasks / Subtasks

- [x] **Task 1: Consume Story 2.2 Research Artifact** (AC: #1)
  - [x] Read Story 2.2 research output: `_bmad-output/planning-artifacts/research/strategy-definition-format-cost-modeling-research.md` (primary — produced by Story 2.2 implementation). If not found, fall back to Story 2.2 spec: `_bmad-output/implementation-artifacts/2-2-strategy-definition-format-cost-modeling-research.md` for requirements context.
  - [x] Extract the recommended specification format (TOML expected per D10/D7)
  - [x] Extract the constraint validation timing recommendation (spec-definition-time vs runtime)
  - [x] Extract the minimum representable constructs confirmed by research
  - [x] Note any architecture decision updates proposed by 2.2

- [x] **Task 2: Create TOML Schema Contract** (AC: #1, #2, #3)
  - [x] Create `contracts/strategy_specification.toml` following existing contract format (see `contracts/arrow_schemas.toml` pattern)
  - [x] Define `[metadata]` section: schema_version (utf8, required, default="1"), name (utf8, required), version (utf8, required, pattern=`v\d{3}`), pair (utf8, required, enum=EURUSD — V1 single-pair; extend via config when adding pairs), timeframe (utf8, required, enum=M1|M5|M15|H1|H4|D1), created_by (utf8, required), config_hash (utf8, optional — populated by Story 2.5 at confirmation/lock time, not required for draft specs)
  - [x] Define `[entry_rules]` section: conditions array with indicator (utf8, required), parameters (table), threshold (float64), comparator (utf8, enum=>|<|==|>=|<=|crosses_above|crosses_below); filters array with type (utf8, enum=session|volatility|day_of_week), params (table); confirmation array (optional)
  - [x] Define `[exit_rules]` section: stop_loss with type (utf8, enum=fixed_pips|atr_multiple|percentage) + value (float64); take_profit same pattern; trailing with type (utf8, enum=trailing_stop|chandelier) + params (table)
  - [x] Define `[position_sizing]` section: method (utf8, enum=fixed_risk|fixed_lots), risk_percent (float64, min=0.1, max=10.0), max_lots (float64, min=0.01, max=100.0)
  - [x] Define `[optimization_plan]` section: parameter_groups array with name, parameters list, ranges (min/max/step per param); group_dependencies array; objective_function (utf8, enum=sharpe|calmar|profit_factor|expectancy)
  - [x] Define `[cost_model_reference]` section: version (utf8, required, pattern=`v\d{3}`)

- [x] **Task 3: Create Pydantic Specification Models** (AC: #1, #2, #3, #4, #5)
  - [x] Create `src/python/strategy/specification.py` with Pydantic v2 BaseModel classes:
    - `StrategyMetadata(BaseModel)`: schema_version, name, version, pair, timeframe, created_by, config_hash (Optional[str]) fields with validators
    - `EntryCondition(BaseModel)`: indicator, parameters, threshold, comparator with field validators
    - `EntryFilter(BaseModel)`: type, params with discriminated union by filter type
    - `EntryConfirmation(BaseModel)`: indicator, parameters, threshold, comparator
    - `EntryRules(BaseModel)`: conditions list, filters list, confirmation list (optional)
    - `ExitStopLoss(BaseModel)`: type, value with type-specific validation
    - `ExitTakeProfit(BaseModel)`: type, value
    - `ExitTrailing(BaseModel)`: type, params
    - `ExitRules(BaseModel)`: stop_loss, take_profit, trailing (optional)
    - `PositionSizing(BaseModel)`: method, risk_percent, max_lots with cross-field validation
    - `ParameterRange(BaseModel)`: min, max, step with `@field_validator` ensuring min < max, step > 0
    - `ParameterGroup(BaseModel)`: name, parameters, ranges dict[str, ParameterRange]
    - `OptimizationPlan(BaseModel)`: parameter_groups list, group_dependencies list, objective_function
    - `CostModelReference(BaseModel)`: version with pattern validator
    - `StrategySpecification(BaseModel)`: metadata, entry_rules, exit_rules, position_sizing, optimization_plan, cost_model_reference — top-level model
  - [x] Add `model_config = ConfigDict(strict=True)` for fail-loud behavior
  - [x] Add custom validators for cross-field rules (e.g., indicator type exists in registry, parameter names match between groups and ranges)

- [x] **Task 4: Create Specification Loader** (AC: #4, #5)
  - [x] Create `src/python/strategy/loader.py` with functions:
    - `load_strategy_spec(spec_path: Path) -> StrategySpecification`: load TOML file, parse into Pydantic model, fail-loud on validation errors
    - `validate_strategy_spec(spec: StrategySpecification) -> list[str]`: semantic validation beyond schema (indicator types recognized, parameter ranges sensible, cost_model_reference format valid)
    - `validate_or_die_strategy(spec_path: Path) -> StrategySpecification`: load + validate + sys.exit(1) on failure — follows `validate_or_die()` pattern from `config_loader/validator.py`
  - [x] Reuse existing pattern: collect all errors, print all, then exit (not first-error-exit)
  - [x] Use `tomllib` (stdlib 3.11+) for TOML parsing — same as `config_loader/loader.py`

- [x] **Task 5: Create Specification Hasher** (AC: #6)
  - [x] Create `src/python/strategy/hasher.py` with functions:
    - `compute_spec_hash(spec: StrategySpecification) -> str`: canonical JSON (sorted keys, no whitespace) → SHA-256 — follows `compute_config_hash()` pattern from `config_loader/hasher.py`
    - `verify_spec_hash(spec: StrategySpecification, expected_hash: str) -> bool`: compare computed vs stored hash
  - [x] Strip internal/transient fields before hashing (prefix with `_` convention)
  - [x] Hash must be deterministic: same spec → same hash always

- [x] **Task 6: Create Specification Storage with Versioning** (AC: #6, #7)
  - [x] Create `src/python/strategy/storage.py` with functions:
    - `save_strategy_spec(spec: StrategySpecification, strategy_dir: Path) -> Path`: auto-increment version (v001→v002), write TOML using crash-safe pattern, return path to saved file
    - `load_latest_version(strategy_dir: Path) -> tuple[StrategySpecification, str]`: find highest vXXX, load it, return (spec, version_string)
    - `list_versions(strategy_dir: Path) -> list[str]`: list all vXXX versions
    - `is_version_immutable(strategy_dir: Path, version: str) -> bool`: check version exists (all saved versions are immutable)
  - [x] Reuse `crash_safe_write()` from `src/python/data_pipeline/utils/safe_write.py` — DO NOT reinvent
  - [x] Reuse `clean_partial_files()` from `src/python/artifacts/storage.py` for startup cleanup
  - [x] Version directory layout: `artifacts/strategies/{strategy_name}/v001.toml`, `v002.toml`, etc.

- [x] **Task 7: Create Indicator Type Registry** (AC: #2, #5)
  - [x] Create `src/python/strategy/indicator_registry.py` with:
    - `KNOWN_INDICATORS: dict[str, IndicatorMeta]`: registry of recognized indicator types — **must be seeded from Story 2.1's indicator catalogue output** (not invented independently)
    - `IndicatorMeta(BaseModel)`: name, category (trend|volatility|momentum|volume), required_params list, optional_params list
    - `is_indicator_known(indicator_type: str) -> bool`
    - `get_indicator_params(indicator_type: str) -> IndicatorMeta`
    - Seed with minimum D10 constructs: SMA, EMA, ATR, BollingerBands, RSI, MACD
  - [x] Registry must be extensible (add indicators without code changes — data-driven)
  - [x] Registry data source: load from a TOML file (`contracts/indicator_registry.toml`) so that Story 2.8's Rust registry can consume the same source — single source of truth for indicator definitions

- [x] **Task 8: Create MA Crossover Reference Specification** (AC: #8)
  - [x] Create `artifacts/strategies/ma-crossover/v001.toml` as reference implementation
  - [x] Include: metadata (name="ma-crossover", version="v001", pair="EURUSD", timeframe="H1")
  - [x] Entry rules: SMA(20) crosses_above SMA(50), session filter = London only (aligns with Epic 2.9 canonical example)
  - [x] Exit rules: chandelier exit at 3x ATR (primary), fixed take_profit (3:1 R:R)
  - [x] Position sizing: fixed_risk at 1%, max_lots=1.0
  - [x] Optimization plan: fast_period (5-50, step=5), slow_period (20-200, step=10), atr_multiplier (1.0-5.0, step=0.5)
  - [x] Cost model reference: v001
  - [x] Verify it loads and validates cleanly through the full pipeline

- [x] **Task 9: Extend Error Codes** (AC: #4, #5)
  - [x] Add `[strategy]` section to `contracts/error_codes.toml` (if not present) with:
    - `SPEC_SCHEMA_INVALID = {severity = "fatal", recoverable = false, action = "Fix specification and retry"}`
    - `SPEC_INDICATOR_UNKNOWN = {severity = "fatal", recoverable = false, action = "Add indicator to registry or fix spec"}`
    - `SPEC_PARAM_RANGE_INVALID = {severity = "fatal", recoverable = false, action = "Fix parameter ranges (min < max, step > 0)"}`
    - `SPEC_COST_MODEL_REF_INVALID = {severity = "fatal", recoverable = false, action = "Fix cost_model_reference version string"}`
    - `SPEC_VERSION_CONFLICT = {severity = "fatal", recoverable = false, action = "Version already exists; save creates new version"}`

- [x] **Task 10: Create Test Fixtures** (AC: #1-#8)
  - [x] Create `src/python/tests/test_strategy/fixtures/valid_ma_crossover.toml` — the reference MA crossover spec (mirrors `artifacts/strategies/ma-crossover/v001.toml`)
  - [x] Create `src/python/tests/test_strategy/fixtures/invalid_missing_metadata.toml` — spec missing `[metadata]` section
  - [x] Create `src/python/tests/test_strategy/fixtures/invalid_bad_param_range.toml` — spec with min > max and step = 0
  - [x] Create `src/python/tests/test_strategy/fixtures/invalid_unknown_indicator.toml` — spec referencing indicator not in registry
  - [x] Create `src/python/tests/test_strategy/fixtures/invalid_bad_cost_ref.toml` — spec with malformed cost_model_reference

- [x] **Task 11: Write Tests** (AC: #1-#8)
  - [x] Create `src/python/tests/test_strategy/__init__.py`
  - [x] Create `src/python/tests/test_strategy/test_specification.py`:
    - `test_valid_ma_crossover_spec_loads()`: load reference spec, assert all fields parsed
    - `test_invalid_spec_missing_metadata_fails()`: missing metadata → ValidationError
    - `test_invalid_spec_missing_entry_rules_fails()`: missing entry_rules → ValidationError
    - `test_invalid_param_range_min_gt_max_fails()`: min > max → ValidationError
    - `test_invalid_param_range_step_zero_fails()`: step=0 → ValidationError
    - `test_unknown_indicator_type_fails()`: indicator not in registry → validation error
    - `test_invalid_cost_model_ref_fails()`: bad version format → validation error
    - `test_spec_roundtrip_toml_to_model_to_toml()`: load → serialize → reload → assert equal
  - [x] Create `src/python/tests/test_strategy/test_hasher.py`:
    - `test_spec_hash_deterministic()`: same spec → same hash
    - `test_spec_hash_changes_on_modification()`: modified spec → different hash
    - `test_spec_hash_verify_roundtrip()`: compute → verify returns True
  - [x] Create `src/python/tests/test_strategy/test_storage.py`:
    - `test_save_creates_v001_first_time()`: first save → v001.toml
    - `test_save_increments_version()`: second save → v002.toml
    - `test_previous_versions_immutable()`: v001 unchanged after v002 save
    - `test_load_latest_version()`: returns highest version
    - `test_list_versions_ordered()`: returns sorted list
    - `test_crash_safe_write_partial_cleanup()`: .partial file cleaned on startup
  - [x] Create `src/python/tests/test_strategy/test_indicator_registry.py`:
    - `test_known_indicators_include_d10_minimum()`: SMA, EMA, ATR, BollingerBands all known
    - `test_unknown_indicator_returns_false()`: random string → False
    - `test_indicator_meta_has_required_params()`: SMA has "period", ATR has "period"

## Dev Notes

### Architecture Constraints

- **D10 (Strategy Execution Model)**: Three-layer model (intent → spec → evaluator). This story implements the **specification layer**. Spec is a versioned, deterministic, constrained strategy definition as a TOML artifact. It is NOT code — it is structured data that the Rust evaluator interprets. The spec format is Phase 0 research output from Story 2.2.
- **D7 (Configuration — TOML with Schema Validation)**: Fail-loud validation at load time. Config hash embedded in manifest for reproducibility. TOML chosen for: no implicit type coercion, deterministic parsing, human-readable/diffable.
- **D13 (Cost Model Crate)**: Schema must include `cost_model_reference` field pointing to a versioned cost model artifact. Format: `v\d{3}` pattern matching cost model versions in `artifacts/cost_models/{pair}/`.
- **D14 (Strategy Engine Shared Crate)**: Rust crate will consume validated specifications. The Python-side schema/validator is the gatekeeper — Rust trusts that specs passing Python validation are well-formed. Story 2.8 builds the Rust consumer.
- **NFR15 (Data Integrity)**: All writes use crash-safe pattern: write to `.partial` → `flush()` → `fsync()` → `os.replace()` atomic rename. Partial files never overwrite complete ones.
- **FR12**: Strategies represented as constrained, versioned, reproducible, testable specifications.
- **FR13**: Strategies define own optimization stages with parameter groupings.
- **FR18/FR61**: Deterministic reproducibility — same spec + same data → same results. Config hash is part of audit trail.

### Scope Boundary: 2.3 vs 2.5 Versioning

Story 2.3 owns **persistence primitives**: save (auto-increment version), load, list versions, immutability enforcement. Story 2.5 owns **operator-facing lifecycle**: confirmation, locking, version history display, diff summaries, config_hash population, manifest records. The `storage.py` in this story is a low-level utility; 2.5 builds workflow on top of it.

### D10 Filter Vocabulary Note

D10's contract tree lists `filters[] (session, regime, day_of_week)` but D10's minimum representable constructs table lists `session` filters and `volatility` filters separately. This story follows the **table** (more detailed/authoritative), implementing `session`, `volatility`, and `day_of_week` filter types. `regime` is a valid future filter type (Growth Phase, FR69) but is not required for V1.

### config_hash Lifecycle

`config_hash` is defined in the schema as an **optional** field. Story 2.3 creates the schema slot; Story 2.5 populates it when the operator confirms/locks the specification. Draft specs may omit it. Hashing (Task 5) computes a **spec** hash for content identity — this is distinct from `config_hash` which links to pipeline configuration state (FR59).

### Technical Requirements

- **Python 3.11+** — use `tomllib` (stdlib) for TOML reading, `tomli_w` for TOML writing
- **Pydantic v2** — `BaseModel` with `ConfigDict(strict=True)` for validation
- **No new dependencies** beyond `tomli_w` (for TOML serialization — `tomllib` is read-only)
- **Naming**: `EURUSD` format (not `EUR_USD` per baseline). Pair enum must use pipeline convention.

### Existing Utilities — MUST REUSE (Do Not Reinvent)

| Utility | Location | Reuse For |
|---------|----------|-----------|
| `validate_or_die()` | `src/python/config_loader/validator.py` | Pattern for `validate_or_die_strategy()` — collect all errors, print all, sys.exit(1) |
| `load_config()` | `src/python/config_loader/loader.py` | Pattern for TOML loading with `tomllib` |
| `compute_config_hash()` | `src/python/config_loader/hasher.py` | Pattern for `compute_spec_hash()` — canonical JSON, sorted keys, SHA-256 |
| `crash_safe_write()` | `src/python/data_pipeline/utils/safe_write.py` | Direct import for crash-safe spec writes |
| `clean_partial_files()` | `src/python/artifacts/storage.py` | Direct import for startup .partial cleanup |
| `load_arrow_schema()` | `src/python/data_pipeline/schema_loader.py` | Pattern for loading TOML contracts |
| Contract TOML format | `contracts/arrow_schemas.toml` | Follow same structure for `strategy_specification.toml` |
| Error codes format | `contracts/error_codes.toml` | Extend `[strategy]` section, same `{severity, recoverable, action}` format |

### Data Naming Convention

ClaudeBackTester uses `EUR_USD`; this pipeline uses `EURUSD`. All pair references in schemas, validators, and sample specs use `EURUSD` format. If consuming ClaudeBackTester data, mapping is the consumer's responsibility (not this story's scope).

### Dependencies

- **Requires completed**: Story 2.1 (indicator catalogue) and Story 2.2 (format recommendation, construct list)
- **Input artifacts**: `_bmad-output/planning-artifacts/research/strategy-definition-format-cost-modeling-research.md` (from 2.2)
- **Blocks**: Story 2.4 (intent capture outputs specs), 2.5 (review loads specs), 2.8 (Rust parses specs), 2.9 (E2E proof)

### Project Structure Notes

**New files to create:**
```
contracts/
  strategy_specification.toml          # TOML schema contract (AC #1)
  indicator_registry.toml             # Shared indicator definitions (Python + Rust consume this)

src/python/strategy/
  specification.py                     # Pydantic v2 models (AC #1-#5)
  loader.py                            # Load + validate specs (AC #4, #5)
  hasher.py                            # Deterministic spec hashing (AC #6)
  storage.py                           # Versioned persistence (AC #6, #7)
  indicator_registry.py                # Known indicator types (AC #2, #5) — loads from contracts/indicator_registry.toml

artifacts/strategies/
  ma-crossover/
    v001.toml                          # Reference implementation (AC #8)

src/python/tests/test_strategy/
  __init__.py
  fixtures/                            # Positive and negative test fixtures
    valid_ma_crossover.toml
    invalid_missing_metadata.toml
    invalid_bad_param_range.toml
    invalid_unknown_indicator.toml
    invalid_bad_cost_ref.toml
  test_specification.py                # Schema validation tests
  test_hasher.py                       # Hash determinism tests
  test_storage.py                      # Versioning + crash-safe tests
  test_indicator_registry.py           # Registry coverage tests
```

**Files to modify:**
```
contracts/error_codes.toml             # Add [strategy] error codes
src/python/strategy/__init__.py        # Export new modules
```

**Existing directory structure confirmed:**
- `contracts/` exists with `arrow_schemas.toml`, `session_schema.toml`, `error_codes.toml`
- `src/python/strategy/` exists with `__init__.py` (empty placeholder)
- `src/python/tests/` exists with `conftest.py`
- `config/strategies/` exists with `.gitkeep` (for runtime strategy configs, not schema)
- `artifacts/` directory may need creation for `strategies/`

### References

- [Source: _bmad-output/planning-artifacts/architecture.md — D10: Strategy Execution Model]
- [Source: _bmad-output/planning-artifacts/architecture.md — D7: Configuration — TOML with Schema Validation]
- [Source: _bmad-output/planning-artifacts/architecture.md — D13: Cost Model Crate]
- [Source: _bmad-output/planning-artifacts/architecture.md — D14: Strategy Engine Shared Crate]
- [Source: _bmad-output/planning-artifacts/prd.md — FR12: Strategy Specification & Versioning]
- [Source: _bmad-output/planning-artifacts/prd.md — FR13: Strategy Parameter Grouping & Optimization]
- [Source: _bmad-output/planning-artifacts/prd.md — FR18: Deterministic Reproducibility]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR15: Data Integrity & Crash-Safe Writes]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 2: Strategy Definition & Cost Model]
- [Source: _bmad-output/planning-artifacts/baseline-to-architecture-mapping.md — Strategy Engine Mapping]
- [Source: src/python/config_loader/validator.py — validate_or_die() pattern]
- [Source: src/python/config_loader/hasher.py — compute_config_hash() pattern]
- [Source: src/python/data_pipeline/utils/safe_write.py — crash_safe_write() utility]
- [Source: src/python/artifacts/storage.py — clean_partial_files() utility]
- [Source: contracts/arrow_schemas.toml — TOML contract format pattern]
- [Source: contracts/error_codes.toml — Error code format pattern]

## Anti-Patterns to Avoid

1. **Do NOT reinvent crash-safe writes** — import `crash_safe_write()` from `data_pipeline/utils/safe_write.py`
2. **Do NOT reinvent hashing** — follow `compute_config_hash()` pattern exactly (canonical JSON, sorted keys, SHA-256)
3. **Do NOT create a custom DSL parser** — D10 steers to structured data (TOML), not code generation or general-purpose interpreters
4. **Do NOT use flat spread constants** — cost_model_reference must point to session-aware versioned artifact (FR21)
5. **Do NOT hardcode indicator types** — use data-driven registry extensible without code changes
6. **Do NOT use `EUR_USD` format** — pipeline convention is `EURUSD`; mapping is consumer's responsibility
7. **Do NOT validate on first error only** — collect ALL errors, report ALL, then fail (matches `validate_or_die()` pattern)
8. **Do NOT create runtime strategy configs in `config/strategies/`** — that directory is for D7 pipeline config; specification artifacts go in `artifacts/strategies/`
9. **Do NOT modify architecture.md** — if research (2.2) proposed changes, they should already be applied before this story
10. **Do NOT conflate strategy specification (D10) with pipeline configuration (D7)** — different schemas, different validation, different storage
11. **Do NOT skip the reference implementation** — MA crossover sample is AC #8 and is the proof that the full pipeline (schema → load → validate → hash → save) works
12. **Do NOT make versions mutable** — once v001.toml is saved, it must never be overwritten; modifications create v002
13. **Do NOT let Python and Rust indicator registries diverge** — both must consume the same source data (`contracts/indicator_registry.toml`); Story 2.8's Rust registry reads this same file. If you add an indicator to one side, it must be added to the shared source.
14. **Do NOT treat this story's versioning as the full lifecycle** — save/load/list/increment are persistence primitives only; confirmation, locking, version history display, and diff summaries are Story 2.5

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

### Completion Notes List

- Task 1: Consumed Story 2.2 research artifact. Confirmed TOML format (score 8.45/10), hybrid 3-layer validation (Python definition-time + Rust load-time + shared contracts), 19 indicators from 2.1 catalogue, session/volatility/day_of_week filter types.
- Task 2: Created `contracts/strategy_specification.toml` covering all D10 sections: metadata, entry_rules (conditions/filters/confirmation), exit_rules (stop_loss/take_profit/trailing), position_sizing, optimization_plan, cost_model_reference. Follows arrow_schemas.toml pattern.
- Task 3: Created Pydantic v2 models in `specification.py` with `ConfigDict(strict=True)`. 16 model classes with field validators for version patterns, parameter range (min < max, step > 0), filter type discrimination, trailing type params, and parameter group/range cross-validation.
- Task 4: Created `loader.py` with `load_strategy_spec()`, `validate_strategy_spec()` (collect-all-errors semantic validation), and `validate_or_die_strategy()` following existing pattern.
- Task 5: Created `hasher.py` with `compute_spec_hash()` (canonical JSON, sorted keys, SHA-256) and `verify_spec_hash()`. Strips internal `_` prefixed keys before hashing.
- Task 6: Created `storage.py` with versioned persistence. Reuses `crash_safe_write()` and `clean_partial_files()` directly. Auto-increments v001→v002, immutable versions.
- Task 7: Created `indicator_registry.py` loading from shared `contracts/indicator_registry.toml`. 19 indicators (3 trend + 6 volatility + 6 momentum + 4 structure). Data-driven, extensible without code changes.
- Task 8: Created MA crossover reference spec at `artifacts/strategies/ma-crossover/v001.toml`. Verified full pipeline: load → validate → hash. SMA(20/50), London session filter, chandelier exit, sharpe optimization.
- Task 9: Extended `contracts/error_codes.toml` with 5 new strategy error codes: SPEC_SCHEMA_INVALID, SPEC_INDICATOR_UNKNOWN, SPEC_PARAM_RANGE_INVALID, SPEC_COST_MODEL_REF_INVALID, SPEC_VERSION_CONFLICT.
- Task 10: Created 5 test fixtures (1 valid, 4 invalid covering missing metadata, bad param range, unknown indicator, bad cost ref).
- Task 11: Created 35 unit tests across 4 test files + 4 live integration tests. All pass. Full regression suite: 364 passed, 0 failed.

### Change Log

- 2026-03-15: Implemented strategy specification schema & contracts (Tasks 1-11). Created TOML schema contract, Pydantic v2 models, loader, hasher, versioned storage, indicator registry, MA crossover reference spec, error codes, test fixtures, and comprehensive test suite.

### File List

**New files created:**
- `contracts/strategy_specification.toml` — TOML schema contract (AC #1)
- `contracts/indicator_registry.toml` — Shared indicator registry (AC #2, #5)
- `src/python/strategy/specification.py` — Pydantic v2 models (AC #1-#5)
- `src/python/strategy/loader.py` — Load + validate specs (AC #4, #5)
- `src/python/strategy/hasher.py` — Deterministic spec hashing (AC #6)
- `src/python/strategy/storage.py` — Versioned persistence (AC #6, #7)
- `src/python/strategy/indicator_registry.py` — Indicator type registry (AC #2, #5)
- `artifacts/strategies/ma-crossover/v001.toml` — Reference implementation (AC #8)
- `src/python/tests/test_strategy/__init__.py`
- `src/python/tests/test_strategy/fixtures/valid_ma_crossover.toml`
- `src/python/tests/test_strategy/fixtures/invalid_missing_metadata.toml`
- `src/python/tests/test_strategy/fixtures/invalid_bad_param_range.toml`
- `src/python/tests/test_strategy/fixtures/invalid_unknown_indicator.toml`
- `src/python/tests/test_strategy/fixtures/invalid_bad_cost_ref.toml`
- `src/python/tests/test_strategy/test_specification.py`
- `src/python/tests/test_strategy/test_hasher.py`
- `src/python/tests/test_strategy/test_storage.py`
- `src/python/tests/test_strategy/test_indicator_registry.py`
- `src/python/tests/test_strategy/test_live_strategy.py`

**Modified files:**
- `contracts/error_codes.toml` — Added 5 strategy error codes (AC #4, #5)
- `src/python/strategy/__init__.py` — Added exports
