# Story 2.4: Strategy Intent Capture — Dialogue to Specification

Status: review

## Story

As the **operator**,
I want to describe a trading strategy through natural dialogue and have it converted to a validated specification,
So that I can create strategies without writing code or learning a specification format.

## Acceptance Criteria

1. **Given** operator provides natural language strategy description (e.g., "Try a moving average crossover on EURUSD H1, only during London session, with a chandelier exit")
   **When** strategy intent capture process runs
   **Then** a draft strategy specification is generated matching `contracts/strategy_specification.toml` schema (FR9, FR10)

2. **Given** generated draft specification
   **When** validated against schema
   **Then** dialogue elements correctly map to specification constructs: indicators, filters, exits, pair, timeframe (FR10)

3. **Given** missing elements in operator input that are strategy-identity-defining (indicators, entry logic)
   **When** specification generation is attempted
   **Then** generation fails with a clear error listing what is missing and must be provided (per clarification policy below)

4. **Given** missing elements in operator input that are non-identity (position sizing, stop loss parameters)
   **When** specification is generated
   **Then** defaults from `config/strategies/defaults.toml` are applied **and** each defaulted field is recorded with `source: "default"` in a provenance map attached to the output

5. **Given** completed specification generation
   **When** draft specification is produced
   **Then** specification passes Story 2.3 schema validation before being returned

6. **Given** D10 AI generation flow
   **When** intent capture executes
   **Then** flow follows: operator dialogue → Claude Code skill → draft specification artifact (versioned, saved)

7. **Given** specification generation completes successfully
   **When** artifact is persisted
   **Then** specification is saved as versioned draft artifact in configured artifacts directory

8. **Given** any intent capture event
   **When** logging is invoked
   **Then** structured logs capture: operator input summary, generated spec version, validation result (D6 — structured JSON logging)

9. **Given** the same normalized intent input and the same defaults configuration
   **When** specification generation runs twice
   **Then** the resulting specifications are structurally identical (deterministic output)

### Clarification Policy

| Field Category | Missing Behavior | Rationale |
|---|---|---|
| **Must have (fail if missing):** indicators, entry logic | Fail with clear error | These define strategy identity — defaulting them fabricates a different strategy |
| **Should have (warn + default):** pair, timeframe | Default (EURUSD, H1) with warning in provenance | MVP scope has only one pair/timeframe, but operator should know |
| **May default (silent default):** position sizing, stop loss params, take profit ratio | Default from config with provenance tracking | These are tuning parameters, not identity |

## Dependencies

**Hard dependency on Story 2.3 (must be DONE before this story starts):**
Story 2.3 produces the schema contract, Pydantic models, validation, storage, hashing, and indicator registry that this story imports. If Story 2.3 is not complete, this story CANNOT proceed. Verify these files exist and are functional before starting:
- `contracts/strategy_specification.toml`
- `src/python/strategy/specification.py` (StrategySpecification model)
- `src/python/strategy/loader.py` (validate_strategy_spec)
- `src/python/strategy/storage.py` (save_strategy_spec)
- `src/python/strategy/hasher.py` (compute_spec_hash)
- `src/python/strategy/indicator_registry.py`

## Tasks / Subtasks

- [x] **Task 1: Verify Story 2.3 dependencies exist** (AC: #1, #5)
  - [x] Confirm `contracts/strategy_specification.toml` exists and is valid
  - [x] Confirm `src/python/strategy/specification.py` exports `StrategySpecification`
  - [x] Confirm `src/python/strategy/loader.py` exports `validate_strategy_spec()`
  - [x] Confirm `src/python/strategy/storage.py` exports `save_strategy_spec()`
  - [x] Confirm `src/python/strategy/hasher.py` exports `compute_spec_hash()`
  - [x] Confirm `src/python/strategy/indicator_registry.py` exports indicator type lookup
  - [x] If ANY are missing → STOP and report blocker

- [x] **Task 2: Create defaults configuration file** (AC: #4)
  - [x] Create `config/strategies/defaults.toml` with all default values (per D7 — config keys live in config/, not contracts/)
  - [x] Sections: `[defaults.pair]`, `[defaults.timeframe]`, `[defaults.position_sizing]`, `[defaults.exits]`
  - [x] Each default includes `value` and `rationale` fields for transparency
  - [x] Add corresponding keys to `config/base.toml` if not already present (D7: every config key must exist in base.toml)
  - [x] This must exist BEFORE Task 4 (defaults.py loads from this file)

- [x] **Task 3: Create intent capture module structure** (AC: #5)
  - [x] Create `src/python/strategy/intent_capture.py` — main orchestration module
  - [x] Create `src/python/strategy/dialogue_parser.py` — keyword/pattern extraction from semi-structured input
  - [x] Create `src/python/strategy/defaults.py` — sensible default resolution
  - [x] Create `src/python/strategy/spec_generator.py` — assembled specification builder
  - [x] Ensure `src/python/strategy/__init__.py` exports public API

- [x] **Task 4: Implement dialogue parsing logic** (AC: #1, #2, #3)
  - [x] `def parse_strategy_intent(structured_input: dict) -> StrategyIntent` — extract structured intent from skill-provided structured data (NOT raw natural language — the Claude Code skill pre-processes dialogue into a dict)
  - [x] `class StrategyIntent` — dataclass: `pair: str | None`, `timeframe: str | None`, `indicators: list[IndicatorIntent]`, `entry_conditions: list[str]`, `exit_rules: list[ExitIntent]`, `filters: list[FilterIntent]`, `position_sizing: PositionSizingIntent | None`, `raw_description: str`, `field_provenance: dict[str, str]` (maps field name → "operator" | "default" | "inferred")
  - [x] `class IndicatorIntent` — dataclass: `type: str`, `params: dict[str, Any]`, `role: str` (signal/filter/exit)
  - [x] `class ExitIntent` — dataclass: `type: str` (stop_loss/take_profit/trailing/chandelier), `params: dict[str, Any]`
  - [x] `class FilterIntent` — dataclass: `type: str` (session/volatility/custom), `params: dict[str, Any]`
  - [x] `class PositionSizingIntent` — dataclass: `method: str` (fixed_fractional/fixed_lot), `params: dict[str, Any]`
  - [x] Map known indicator names to registry types: MA→SMA, "moving average"→SMA, EMA, ATR, Bollinger, RSI, MACD
  - [x] Map known exit types: "chandelier exit"→chandelier, "trailing stop"→trailing, "stop loss"→stop_loss
  - [x] Map known filters: "London session"→session_filter(session="london"), "high volatility"→volatility_filter
  - [x] Map timeframe aliases: "1 hour"→H1, "4 hour"→H4, "daily"→D1, "15 minute"→M15
  - [x] Normalize pair formats: `EUR_USD`→`EURUSD`, `eur/usd`→`EURUSD`, `EUR/USD`→`EURUSD` (per project data naming convention)
  - [x] Validate against Story 2.3 indicator registry — reject unknown indicator types with clear error
  - [x] Enforce clarification policy: if no indicators or entry logic provided, raise `IntentCaptureError("Strategy-defining fields missing: [indicators/entry_logic]. These cannot be defaulted — please specify.")` (AC #3)
  - [x] For "should have" fields (pair, timeframe): apply default but log a warning and mark provenance as "default"

- [x] **Task 5: Implement defaults resolution with provenance** (AC: #4)
  - [x] `def apply_defaults(intent: StrategyIntent) -> StrategyIntent` — fill missing elements, return new StrategyIntent (immutable pattern)
  - [x] Load defaults from `config/strategies/defaults.toml` via `config_loader` — NOT hardcoded in Python (D7)
  - [x] Default pair: EURUSD (MVP scope)
  - [x] Default timeframe: H1 (MVP scope)
  - [x] Default position sizing: fixed fractional 1% risk per trade
  - [x] Default stop loss: ATR-based, 2x ATR(14) if no exit specified
  - [x] Default take profit: 2:1 reward-to-risk ratio if no TP specified
  - [x] Track provenance for every field in `field_provenance: dict[str, str]` — value is "operator", "default", or "inferred"
  - [x] Defaults must be distinguishable from operator-provided values via provenance map (Story 2.5 consumes this for review)

- [x] **Task 6: Implement specification generator** (AC: #1, #2, #5)
  - [x] `def generate_specification(intent: StrategyIntent) -> StrategySpecification` — convert parsed intent to Pydantic model from Story 2.3
  - [x] Map `IndicatorIntent` → `EntryCondition` / entry_rules indicators per schema
  - [x] Map `ExitIntent` → exit_rules (stop_loss, take_profit, trailing, chandelier sections)
  - [x] Map `FilterIntent` → entry_rules filters (session_filter, volatility_filter)
  - [x] Set `metadata.name` from strategy description or auto-generate slug (e.g., "ma-crossover-eurusd-h1")
  - [x] Set `metadata.version` = "v001" for new strategies
  - [x] Set `metadata.pair`, `metadata.timeframe` from intent
  - [x] Set `metadata.created_by` = "intent_capture"
  - [x] Set `metadata.status` = "draft" (not yet confirmed — Story 2.5 handles confirmation and locking)
  - [x] Leave `optimization_plan` empty/minimal — optimization parameter ranges are set during Story 2.8 optimization setup, not during intent capture
  - [x] Leave `cost_model_reference` unset or null — cost model is created in Story 2.6; this field is populated when the spec enters the backtest stage, not at creation
  - [x] Call `validate_strategy_spec()` from Story 2.3 loader — fail-loud if invalid
  - [x] Attach `field_provenance` map to spec metadata for downstream review step (Story 2.5 consumes this)

- [x] **Task 7: Implement versioned artifact persistence** (AC: #6)
  - [x] `def save_specification(spec: StrategySpecification, artifacts_dir: Path) -> Path` — save with auto-versioning
  - [x] Delegate to Story 2.3 `save_strategy_spec()` from `src/python/strategy/storage.py` — do NOT reimplement
  - [x] Crash-safe write via `src/python/data_pipeline/utils/safe_write.py`
  - [x] Version directory: `artifacts/strategies/{strategy_slug}/v001.toml`
  - [x] Compute and embed `spec_hash` via Story 2.3 `compute_spec_hash()` — this is a content hash of the specification itself, NOT a pipeline config hash. `config_hash` (linking to pipeline configuration state) is set later during Story 2.5 confirmation/locking
  - [x] Return saved path for logging and skill output

- [x] **Task 8: Implement structured logging** (AC: #8)
  - [x] Use existing `src/python/logging_setup/setup.py` — do NOT create new logging
  - [x] Log intent capture start: `{"event": "intent_capture_start", "operator_input_summary": "<truncated to 200 chars>", "timestamp": "..."}`
  - [x] Log spec generation: `{"event": "spec_generated", "spec_version": "v001", "strategy_name": "...", "fields_defaulted": [...], "fields_from_operator": [...]}`
  - [x] Log validation result: `{"event": "spec_validated", "valid": true/false, "errors": [...], "spec_hash": "..."}`
  - [x] Log artifact saved: `{"event": "spec_saved", "path": "...", "version": "v001", "spec_hash": "...", "status": "draft"}`
  - [x] All logging calls in `intent_capture.py` orchestrator — not scattered across modules

- [x] **Task 9: Create intent capture orchestrator** (AC: #1-#7)
  - [x] `def capture_strategy_intent(dialogue: str, artifacts_dir: Path) -> CaptureResult` — main entry point
  - [x] `class CaptureResult` — dataclass: `spec: StrategySpecification`, `saved_path: Path`, `version: str`, `field_provenance: dict[str, str]`, `spec_hash: str`
  - [x] Orchestrates full flow: parse → defaults → generate → validate → save → log
  - [x] Single function the skill calls — clean interface boundary

- [x] **Task 10: Create Claude Code skill for dialogue flow** (AC: #6)
  - [x] Create `.claude/skills/strategy-capture.md` skill definition
  - [x] Skill triggers on: "create a strategy", "new strategy", "try a strategy", "define a strategy"
  - [x] Skill receives operator dialogue in natural language
  - [x] Skill uses Claude's understanding to extract structured elements from dialogue into a dict, then calls Python: `python -m src.python.strategy.intent_capture '<json_structured_input>'`
  - [x] Skill returns draft spec path, version, and provenance summary — does NOT present full human-readable review (that is Story 2.5's `/strategy-review` skill responsibility per FR11)
  - [x] Skill briefly confirms what was captured: "Draft spec saved: ma-crossover-eurusd-h1 v001. Run /strategy-review to review and confirm."
  - [x] Skill handles errors gracefully: if clarification policy rejects (missing indicators/entry logic), present the error and ask operator to provide the missing elements
  - [x] **Note on D9 boundary:** This skill calls Python directly rather than via REST API because the orchestrator API does not exist yet at this build stage. When the API layer is built (Epic 5+), this invocation path should be migrated to go through the API. Add a `# TODO(D9): migrate to REST API when orchestrator is available` comment in the skill file

- [x] **Task 11: Write tests** (AC: #1-#9)
  - [x] `test_parse_strategy_intent_ma_crossover` — structured dict input with MA crossover, EURUSD H1, London session filter, chandelier exit
  - [x] `test_parse_strategy_intent_minimal_with_indicators` — structured dict with only EMA indicator + entry logic → defaults fill the rest
  - [x] `test_parse_strategy_intent_complex` — structured dict with Bollinger breakout, RSI confirmation, volatility filter, trailing stop
  - [x] `test_parse_rejects_missing_indicators` — verify `IntentCaptureError` raised when no indicators provided (clarification policy: must-have)
  - [x] `test_parse_rejects_missing_entry_logic` — verify `IntentCaptureError` raised when no entry logic provided (clarification policy: must-have)
  - [x] `test_parse_pair_normalization` — verify EUR_USD, eur/usd, EUR/USD all normalize to EURUSD
  - [x] `test_apply_defaults_fills_missing` — verify all non-identity defaults applied when intent is sparse
  - [x] `test_apply_defaults_preserves_explicit` — verify operator-provided values not overwritten
  - [x] `test_provenance_tracking` — verify `field_provenance` map correctly records "operator" vs "default" for each field
  - [x] `test_defaults_loaded_from_toml` — verify defaults come from `config/strategies/defaults.toml`, not hardcoded
  - [x] `test_generate_specification_schema_valid` — verify output passes Story 2.3 schema validation
  - [x] `test_generate_specification_indicator_mapping` — verify structured indicators map to correct schema constructs
  - [x] `test_generate_specification_exit_mapping` — verify exit types map correctly
  - [x] `test_generate_specification_filter_mapping` — verify session/volatility filters map correctly
  - [x] `test_generate_specification_no_optimization_plan` — verify optimization_plan is empty/minimal (not auto-populated)
  - [x] `test_generate_specification_no_cost_model` — verify cost_model_reference is null/unset (populated later)
  - [x] `test_save_specification_versioned` — verify v001 directory structure and crash-safe write
  - [x] `test_save_specification_spec_hash_embedded` — verify `spec_hash` (content hash) present in saved artifact
  - [x] `test_deterministic_output` — same structured input + same config → structurally identical spec (AC #9)
  - [x] `test_logging_intent_capture_events` — verify all 4 structured log events emitted with correct fields
  - [x] `test_end_to_end_capture_strategy_intent` — full flow from structured dict to saved, validated draft artifact via `capture_strategy_intent()`
  - [x] Place all tests in `src/python/tests/test_strategy/test_intent_capture.py`

## Dev Notes

### Architecture Constraints

- **D10 (Strategy Execution Model):** This story implements the first layer of the three-layer model: Intent Capture (Claude Code dialogue) → Specification (TOML artifact) → Evaluation (Rust engine, later stories). The intent capture layer lives entirely in Python. The output MUST be a valid draft TOML specification artifact matching the schema from Story 2.3.

- **D9 (Operator Interface — Claude Code Skills Layer):** Skills are the action interface. Per architecture, skills invoke the REST API for mutations. However, since the orchestrator API does not yet exist at this build stage, this story's skill calls Python directly as a documented exception. A TODO is added for migration when the API layer exists.

- **D6 (Structured JSON Logging):** All events use existing logging infrastructure. Log format: `{"event": "...", "timestamp": "...", ...}`. Use `src/python/logging_setup/setup.py`.

- **D7 (Layered TOML Configuration):** Defaults live in `config/strategies/defaults.toml`, not hardcoded. Every config key must exist in `config/base.toml` with a default. The spec output is TOML. Configuration loading follows existing `config_loader` patterns.

- **Reproducibility:** Every generated specification must include `spec_hash` computed by Story 2.3's `compute_spec_hash()`. This is a content hash of the specification fields — it does NOT include timestamps or metadata. Same normalized input + same config = same spec_hash. The separate `config_hash` (linking to pipeline configuration state) is set during Story 2.5 confirmation/locking, not here.

- **Note:** D5 is "Process Supervision — NSSM" and D12 is "Reconciliation Data Flow" — neither applies to this story. Previous references to these decisions were incorrect.

### Technical Requirements

- **Python version:** Match project venv (check `pyproject.toml` or `.python-version`)
- **Pydantic v2:** Use BaseModel from pydantic v2 for all dataclasses that need validation. Use stdlib `dataclasses` for internal-only data structures (like `StrategyIntent`).
- **No new dependencies for parsing:** The dialogue parsing uses pattern matching and keyword extraction — NOT an LLM call. The Claude Code skill layer handles the AI interaction; the Python module receives already-structured or semi-structured text.
- **TOML library:** Use `tomli` (read) / `tomli_w` (write) — same as existing `config_loader`

### Critical Design Decision: Parsing Approach

The dialogue parser does NOT call an LLM. Instead:
1. The Claude Code **skill** (`.claude/skills/strategy-capture.md`) acts as the AI layer — it receives operator dialogue, uses Claude's understanding to extract structured elements, and calls the Python module with structured data.
2. The Python `dialogue_parser.py` handles **structured text parsing** — keyword matching, pattern extraction, alias resolution. It receives semi-structured input from the skill, not raw natural language.
3. This separation means the Python code is testable, deterministic, and does not require API keys.

### What to Reuse from Existing Codebase

| Module | Reuse Strategy |
|--------|----------------|
| `src/python/strategy/specification.py` | Import `StrategySpecification` Pydantic model (Story 2.3 output) |
| `src/python/strategy/loader.py` | Use `validate_strategy_spec()` for schema validation |
| `src/python/strategy/storage.py` | Use `save_strategy_spec()` for versioned persistence |
| `src/python/strategy/hasher.py` | Use `compute_spec_hash()` for config_hash |
| `src/python/strategy/indicator_registry.py` | Use indicator type registry for validation (Story 2.3) |
| `src/python/config_loader/loader.py` | Pattern reference for TOML loading |
| `src/python/config_loader/validator.py` | Pattern reference for validation approach |
| `src/python/data_pipeline/utils/safe_write.py` | Reuse `safe_write()` for crash-safe persistence |
| `src/python/logging_setup/setup.py` | Use `get_logger()` for structured logging |
| `src/python/artifacts/storage.py` | Reference for artifact metadata patterns |

### What to Reuse from ClaudeBackTester

Per Story 2.1 research (when completed), the ClaudeBackTester baseline uses hardcoded Rust strategy evaluation. Story 2.4 does NOT port any ClaudeBackTester code — this is a new capability. However, the indicator names and parameter conventions from the baseline catalogue (Story 2.1 output) should inform the dialogue parser's keyword mapping.

### Anti-Patterns to Avoid

1. **Do NOT call an LLM from Python code** — the Claude Code skill handles AI interpretation; Python code must be deterministic and testable
2. **Do NOT reimplement specification validation** — use Story 2.3's `validate_strategy_spec()`
3. **Do NOT reimplement versioned storage** — use Story 2.3's `save_strategy_spec()`
4. **Do NOT reimplement config hashing** — use Story 2.3's `compute_spec_hash()`
5. **Do NOT reimplement crash-safe writes** — use existing `safe_write()` utility
6. **Do NOT hardcode defaults in Python** — load from `config/strategies/defaults.toml` (D7)
7. **Do NOT create a new logging system** — use existing `logging_setup`
8. **Do NOT attempt to parse completely unstructured natural language in Python** — the skill layer provides structured dict input
9. **Do NOT add profitability checks or strategy quality gates** — per project guidance, V1 pipeline proof comes first
10. **Do NOT create a web UI or API endpoint** — this story is CLI/skill-based only (D10 flow)
11. **Do NOT auto-generate optimization plans** — optimization parameter ranges are set during optimization setup (Story 2.8), not at intent capture time
12. **Do NOT fabricate cost_model_reference** — cost model is created in Story 2.6; do not set placeholder values like `"pending"` that look like real references
13. **Do NOT implement human-readable review/summary presentation** — that is Story 2.5's responsibility (FR11). This story produces the draft spec; 2.5 presents and confirms it

### Project Structure Notes

**Files to create:**
```
src/python/strategy/intent_capture.py      # Main orchestration + capture_strategy_intent() entry point
src/python/strategy/dialogue_parser.py     # Keyword/pattern extraction + StrategyIntent dataclasses
src/python/strategy/defaults.py            # Default resolution from contracts/strategy_defaults.toml
src/python/strategy/spec_generator.py      # Intent → StrategySpecification assembly
config/strategies/defaults.toml            # Default values config (TOML, loaded at runtime per D7)
.claude/skills/strategy-capture.md         # Claude Code skill (AI layer for dialogue interpretation)
src/python/tests/test_strategy/__init__.py
src/python/tests/test_strategy/test_intent_capture.py  # 17 test methods
```

**Files that must exist first (Story 2.3 dependencies):**
```
contracts/strategy_specification.toml      # Schema contract
src/python/strategy/specification.py       # Pydantic models
src/python/strategy/loader.py             # Validation
src/python/strategy/storage.py            # Versioned persistence
src/python/strategy/hasher.py             # Config hash
src/python/strategy/indicator_registry.py  # Indicator types
```

**Existing files to import from (no modification):**
```
src/python/data_pipeline/utils/safe_write.py
src/python/logging_setup/setup.py
src/python/config_loader/loader.py
src/python/artifacts/storage.py
```

### Data Naming Note

Per project memory: ClaudeBackTester uses `EUR_USD` format, Pipeline uses `EURUSD`. The dialogue parser should accept both formats and normalize to `EURUSD` (pipeline convention). Include mapping: `EUR_USD` → `EURUSD`, `eur/usd` → `EURUSD`, `EUR/USD` → `EURUSD`.

### References

- [Source: _bmad-output/planning-artifacts/prd.md — FR9, FR10, FR11, FR12, FR38]
- [Source: _bmad-output/planning-artifacts/architecture.md — D6, D7, D9, D10]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 2, Story 2.4]
- [Source: _bmad-output/implementation-artifacts/2-3-strategy-specification-schema-contracts.md — Schema dependency]
- [Source: src/python/config_loader/ — TOML loading patterns]
- [Source: src/python/data_pipeline/utils/safe_write.py — Crash-safe write pattern]
- [Source: src/python/logging_setup/setup.py — Structured logging setup]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Debug Log References
- All 24 tests pass (21 unit + 3 live integration), 0 failures
- Full strategy test suite: 70 passed, 7 skipped, 0 regressions

### Completion Notes List
- Implemented complete intent capture pipeline: parse -> defaults -> generate -> validate -> save -> log
- Added `status` field to StrategyMetadata for draft/confirmed/locked lifecycle
- Made `optimization_plan` and `cost_model_reference` Optional in StrategySpecification to support draft specs (per anti-patterns #11, #12)
- Guarded `validate_strategy_spec()` against None optimization_plan/cost_model_reference
- Defaults loaded from `config/strategies/defaults.toml` (not hardcoded) per D7
- Clarification policy enforced: missing indicators/entry_logic raises IntentCaptureError
- Should-have fields (pair, timeframe) default with warning and provenance="default"
- Provenance tracking records "operator" vs "default" for every field
- All 4 structured log events emitted in orchestrator (intent_capture_start, spec_generated, spec_validated, spec_saved)
- Deterministic output verified: same input + config = same spec_hash
- Claude Code skill created at `.claude/skills/strategy-capture.md` with TODO(D9) migration note

### Implementation Plan
- Architecture: Skill (AI layer) -> dialogue_parser (normalization) -> defaults (config-driven) -> spec_generator (mapping) -> storage (persistence)
- All indicator aliases, exit types, filter types, timeframe aliases, and pair formats normalized via lookup dicts
- Spec generator maps IndicatorIntent -> EntryCondition with type-aware comparator/threshold defaults (crossover -> crosses_above/0.0, RSI -> >/50.0, etc.)

### File List

**New files:**
- `src/python/strategy/dialogue_parser.py` — Keyword/pattern extraction, StrategyIntent dataclasses, alias mappings
- `src/python/strategy/defaults.py` — Default resolution from TOML config with provenance tracking
- `src/python/strategy/spec_generator.py` — Intent -> StrategySpecification assembly with validation
- `src/python/strategy/intent_capture.py` — Main orchestrator, CaptureResult, structured logging
- `config/strategies/defaults.toml` — Strategy defaults configuration (D7)
- `.claude/skills/strategy-capture.md` — Claude Code skill for dialogue flow (D9)
- `src/python/tests/test_strategy/test_intent_capture.py` — 21 unit tests + 3 live integration tests

**Modified files:**
- `src/python/strategy/specification.py` — Added Optional status to metadata, made optimization_plan/cost_model_reference Optional
- `src/python/strategy/loader.py` — Guarded optimization_plan/cost_model_reference validation against None
- `src/python/strategy/__init__.py` — Added new module exports to public API
- `config/base.toml` — Added [strategy] section with artifacts_dir and defaults_file keys

## Change Log
- 2026-03-15: Story 2.4 implemented — complete intent capture pipeline from structured dialogue to validated draft specification artifact
