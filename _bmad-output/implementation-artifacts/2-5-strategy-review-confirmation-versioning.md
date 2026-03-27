# Story 2.5: Strategy Review, Confirmation & Versioning

Status: review

## Story

As the **operator**,
I want to review a human-readable summary of what a generated strategy does, confirm it matches my intent, and have it locked for pipeline use,
So that I understand exactly what the system will execute before committing to backtesting.

## Acceptance Criteria

1. **Given** a strategy specification has been generated (Story 2.4)
   **When** the strategy review process runs
   **Then** a human-readable summary is presented: what indicators are used, entry/exit logic in plain English, filters applied, position sizing, pair, timeframe — without exposing the raw specification format
   *(FR11 — operator reviews summary without code visibility)*

2. **Given** the operator reviews the summary
   **When** the operator confirms the strategy
   **Then** the specification version is locked for pipeline use with status changed from `draft` to `confirmed`
   *(FR12 — versioned, immutable specification)*

3. **Given** a strategy specification exists (draft or confirmed)
   **When** the operator requests modifications (e.g., "try wider stops", "add a session filter")
   **Then** a new specification version is created with the changes applied — the modification follows the D10 modification flow
   *(FR73 — operator-directed modifications; D10 — specification-driven strategy model)*

4. **Given** a modification is applied
   **When** the new version is saved
   **Then** a new versioned artifact is created (e.g., v001 → v002) and the previous version is preserved, never overwritten
   *(FR12 — versioning and immutability)*

5. **Given** a modification creates a new version
   **When** the diff summary is generated
   **Then** it shows what changed between versions in plain English (e.g., "Stop loss changed from 1.5x ATR to 2.0x ATR")
   *(FR11 — human-readable review)*

6. **Given** a specification is confirmed
   **When** the lock is applied
   **Then** the specification includes a `config_hash` linking it to the pipeline configuration state at time of confirmation
   *(FR59 — explicit configuration traceability and reproducibility)*

7. **Given** a strategy has one or more specification versions
   **When** the manifest is queried
   **Then** it records: version history, creation timestamp per version, operator confirmation timestamp, linked config hash, spec hash, and `latest_confirmed_version` pointer identifying the pipeline-approved spec
   *(FR58 — versioned, persisted artifacts; FR59 — configuration traceability)*

8. **Given** a strategy review or version diff is generated
   **When** the output is formatted
   **Then** the formatted text is persisted as an artifact alongside the spec version (review summary in `reviews/`, diff in `diffs/`)
   *(FR39 — operator gate evidence trail; FR58 — artifact persistence)*

## Tasks / Subtasks

- [x] **Task 1: Verify Story 2.3 and 2.4 dependencies exist** (AC: all)
  - [x]Confirm these Story 2.3 files exist and export expected functions:
    - `contracts/strategy_specification.toml`
    - `src/python/strategy/specification.py` → `StrategySpecification` model
    - `src/python/strategy/loader.py` → `validate_strategy_spec()`
    - `src/python/strategy/storage.py` → `save_strategy_spec()`
    - `src/python/strategy/hasher.py` → `compute_spec_hash()`
    - `src/python/strategy/indicator_registry.py`
  - [x]Confirm these Story 2.4 files exist:
    - `src/python/strategy/intent_capture.py`
    - `src/python/strategy/spec_generator.py`
  - [x]Confirm `src/python/config_loader/hasher.py` exists with `compute_config_hash()` (from Story 1.3). If missing, create minimal implementation: hash `config/base.toml` + active environment TOML content → SHA-256 hex digest
  - [x]Confirm `src/python/data_pipeline/utils/safe_write.py` exports `safe_write()`
  - [x]Confirm `src/python/logging_setup/setup.py` exports `get_logger()`
  - [x]**STOP and report blocker if ANY Story 2.3/2.4 dependency missing**

- [x] **Task 2: Create reviewer module** (AC: #1)
  - [x]Create `src/python/strategy/reviewer.py`
  - [x]Dataclass `StrategySummary` with fields: `strategy_name: str`, `pair: str`, `timeframe: str`, `indicators: list[str]`, `entry_logic: str`, `exit_logic: str`, `filters: list[str]`, `position_sizing: str`, `version: str`, `status: str`
  - [x]`generate_summary(spec: StrategySpecification) -> StrategySummary`:
    - Extract indicator names and parameters → plain English (e.g., "SMA with period 20 on close" not `{"type": "SMA", "params": {"period": 20}}`)
    - Translate entry conditions → readable logic (e.g., "Enter long when fast SMA crosses above slow SMA")
    - Translate exit rules → readable description (e.g., "Stop loss at 2.0x ATR(14), take profit at 2:1 reward-to-risk ratio")
    - List filters in plain English (e.g., "Only trade during London session")
    - Describe position sizing (e.g., "Fixed fractional: risk 1% of account per trade")
    - Include pair and timeframe
  - [x]`format_summary_text(summary: StrategySummary) -> str`:
    - Multi-line formatted text with clear section headers
    - Must NOT expose raw specification format — no TOML, no JSON, no dict repr
  - [x]`save_summary_artifact(summary_text: str, strategy_slug: str, version: str, artifacts_dir: Path) -> Path`: Save formatted summary to `artifacts/strategies/{slug}/reviews/{version}_summary.txt` via `safe_write()`. Persisted for evidence trail (FR39 operator gate pattern)
  - [x]Export `generate_summary`, `format_summary_text`, `save_summary_artifact`, `StrategySummary` from module

- [x] **Task 3: Create versioner module** (AC: #4, #5, #7)
  - [x]Create `src/python/strategy/versioner.py`
  - [x]Dataclass `FieldChange` with fields: `field_path: str`, `old_value: str`, `new_value: str`, `description: str`
  - [x]Dataclass `VersionDiff` with fields: `old_version: str`, `new_version: str`, `changes: list[FieldChange]`
  - [x]Dataclass `VersionEntry` with fields: `version: str`, `status: str`, `created_at: str`, `confirmed_at: str | None`, `config_hash: str | None`, `spec_hash: str`
  - [x]Dataclass `SpecificationManifest` with fields: `strategy_slug: str`, `versions: list[VersionEntry]`, `current_version: str`, `latest_confirmed_version: str | None`
  - [x]`increment_version(current_version: str) -> str`: `"v001"` → `"v002"`, `"v099"` → `"v100"`. Zero-padded 3 digits.
  - [x]`compute_version_diff(old_spec: StrategySpecification, new_spec: StrategySpecification) -> VersionDiff`:
    - Deep-compare specification fields (entry_rules, exit_rules, filters, position_sizing, metadata)
    - For each changed field, create `FieldChange` with human-readable description
    - Ignore metadata fields that are expected to differ (version, timestamps, spec_hash)
    - Compare nested structures recursively
  - [x]`save_diff_artifact(diff_text: str, strategy_slug: str, old_version: str, new_version: str, artifacts_dir: Path) -> Path`: Save formatted diff to `artifacts/strategies/{slug}/diffs/{old_version}_{new_version}_diff.txt` via `safe_write()`. Persisted for audit trail.
  - [x]`format_diff_text(diff: VersionDiff) -> str`: Render diff as plain English change list. Example output:
    ```
    Changes (v001 → v002):
    • Stop loss: ATR multiplier changed from 1.5x to 2.0x
    • Filter added: London session filter (08:00-16:00 UTC)
    • Position sizing: Risk per trade unchanged (1%)
    ```
  - [x]`load_manifest(strategy_slug: str, artifacts_dir: Path) -> SpecificationManifest | None`: Load `artifacts/strategies/{slug}/manifest.json`. Return None if not exists.
  - [x]`save_manifest(manifest: SpecificationManifest, artifacts_dir: Path) -> Path`: Save to `artifacts/strategies/{slug}/manifest.json`. Use `safe_write()` for crash-safe persistence.
  - [x]`create_manifest(strategy_slug: str, version_entry: VersionEntry) -> SpecificationManifest`: Create new manifest with initial version entry.
  - [x]`update_manifest_version(manifest: SpecificationManifest, version_entry: VersionEntry) -> SpecificationManifest`: Add or update version entry.
  - [x]Manifest serialized as JSON (not TOML) — it's metadata about artifacts, not configuration (D7 scope is config only)

- [x] **Task 4: Create confirmer module** (AC: #2, #6, #7)
  - [x]Create `src/python/strategy/confirmer.py`
  - [x]Dataclass `ConfirmationResult` with fields: `spec: StrategySpecification`, `saved_path: Path`, `version: str`, `config_hash: str`, `spec_hash: str`, `confirmed_at: str`, `manifest_path: Path`
  - [x]`confirm_specification(strategy_slug: str, version: str, artifacts_dir: Path, config_dir: Path) -> ConfirmationResult`:
    1. Load spec from `artifacts/strategies/{slug}/{version}.toml`
    2. Verify status is `draft`. If already `confirmed`: return existing `ConfirmationResult` (idempotent — same version, same result, no side effects)
    3. Compute `config_hash` via `config_loader/hasher.py` → `compute_config_hash(config_dir)`
    4. Set `spec.metadata.status = "confirmed"`
    5. Set `spec.metadata.config_hash = config_hash`
    6. Set `spec.metadata.confirmed_at` = UTC ISO 8601 with second precision (e.g., `"2026-03-15T10:05:00Z"`)
    7. Compute `spec_hash` via Story 2.3 `compute_spec_hash(spec)` (content hash, excludes timestamps/status)
    8. Save spec via Story 2.3 `save_strategy_spec()` — same version file (status change is metadata update, not content change, so same file is OK)
    9. Load or create manifest, add/update version entry with confirmation timestamp and config_hash. Set `manifest.latest_confirmed_version` to this version
    10. Save manifest via `save_manifest()`
    11. Return `ConfirmationResult`
  - [x]If `config_loader/hasher.py` does not exist (checked in Task 1), implement `compute_config_hash(config_dir: Path) -> str`:
    - Read `config/base.toml` content
    - Detect active environment from env var or default to `local`
    - Read `config/environments/{env}.toml` if exists
    - Concatenate sorted content → SHA-256 hex digest (first 16 chars)
    - Place in `src/python/config_loader/hasher.py`

- [x] **Task 5: Create modifier module** (AC: #3, #4, #5)
  - [x]Create `src/python/strategy/modifier.py`
  - [x]Dataclass `ModificationIntent` with fields: `field_path: str`, `action: str` (set/add/remove), `new_value: Any`, `description: str`
  - [x]Dataclass `ModificationResult` with fields: `old_spec: StrategySpecification`, `new_spec: StrategySpecification`, `old_version: str`, `new_version: str`, `diff: VersionDiff`, `saved_path: Path`, `manifest_path: Path`
  - [x]`parse_modification_intent(structured_input: dict) -> list[ModificationIntent]`:
    - Input from Claude Code skill: `{"strategy_slug": "...", "modifications": [{"field": "exit_rules.stop_loss.value", "action": "set", "value": 2.0, "description": "wider stops"}]}`
    - Validate field paths exist in specification schema
    - Return list of `ModificationIntent`
  - [x]`apply_single_modification(spec: StrategySpecification, mod: ModificationIntent) -> StrategySpecification`:
    - `set`: update field value at path
    - `add`: add entry to list field (e.g., add filter to filters list)
    - `remove`: remove entry from list field
    - Return modified copy (do NOT mutate original)
  - [x]`apply_modifications(strategy_slug: str, modifications: list[ModificationIntent], artifacts_dir: Path) -> ModificationResult`:
    1. Load latest version spec from `artifacts/strategies/{slug}/`
    2. Store as `old_spec`
    3. Apply each modification sequentially via `apply_single_modification()`
    4. Increment version via `versioner.increment_version()`
    5. Update spec metadata: new version, status=`draft`, new `created_at` timestamp
    6. Validate modified spec via Story 2.3 `validate_strategy_spec()` — fail-loud if invalid
    7. Compute new `spec_hash` via Story 2.3 `compute_spec_hash()`
    8. Save as new versioned artifact via Story 2.3 `save_strategy_spec()`
    9. Compute diff via `versioner.compute_version_diff(old_spec, new_spec)`
    10. Update manifest with new version entry
    11. Return `ModificationResult`
  - [x]Helper `find_latest_version(strategy_slug: str, artifacts_dir: Path) -> tuple[str, Path]`: Scan `artifacts/strategies/{slug}/v*.toml`, return highest version string and path
  - [x]Version collision guard: before saving new version, verify target file does NOT already exist — fail-loud if collision detected (prevents silent overwrites from concurrent runs or manual edits)

- [x] **Task 6: Create CLI entrypoints and Claude Code skills** (AC: #1, #2, #3)
  - [x]Create `src/python/strategy/__main__.py` — CLI dispatcher:
    - `python -m src.python.strategy review <strategy_slug> [--version v001]` → calls `generate_summary()` + `format_summary_text()`, prints to stdout, saves artifact via `save_summary_artifact()`
    - `python -m src.python.strategy confirm <strategy_slug> <version>` → calls `confirm_specification()`, prints confirmation result
    - `python -m src.python.strategy modify <strategy_slug> --input '<json>'` → calls `apply_modifications()`, prints diff, saves diff artifact
    - `python -m src.python.strategy manifest <strategy_slug>` → prints manifest summary
    - Uses `argparse` — no new dependencies
  - [x]Create `.claude/skills/strategy_review.md` (architecture D9, snake_case naming):
    - Triggers: "review strategy", "show strategy", "what does this strategy do", "confirm strategy", "lock strategy"
    - Review flow: skill calls `python -m src.python.strategy review <strategy_slug> [--version v001]`
    - Displays formatted summary to operator
    - Asks operator: "Confirm this strategy for pipeline use? (yes/no/modify)"
    - If yes: calls `python -m src.python.strategy confirm <strategy_slug> <version>`
    - If modify: asks what to change, then invokes strategy-update flow
    - D9 boundary note: calls Python CLI directly (REST API not yet available — TODO for API migration when orchestrator lands)
  - [x]Create `.claude/skills/strategy_update.md` (architecture D10, snake_case naming):
    - Triggers: "try wider stops", "change the timeframe", "add a filter", "modify strategy", "update strategy"
    - Skill interprets operator's natural language → structured modification JSON
    - Calls `python -m src.python.strategy modify <strategy_slug> --input '<json>'`
    - Displays diff summary to operator
    - Brief confirmation: "Modified ma-crossover-eurusd-h1: v001 → v002. Changes: [diff]. Run /strategy-review to review and confirm."
    - D9 boundary note: calls Python CLI directly — TODO for REST API migration

- [x] **Task 7: Implement structured logging** (AC: all)
  - [x]Use `src/python/logging_setup/setup.py` → `get_logger()` (do NOT create new logging)
  - [x]Log events in each module orchestrator function (not scattered):
    - `strategy_review_start` — strategy_slug, version
    - `strategy_review_complete` — strategy_slug, version, summary_length
    - `strategy_confirmed` — strategy_slug, version, config_hash, spec_hash
    - `strategy_modification_start` — strategy_slug, modifications_count
    - `strategy_modification_complete` — strategy_slug, old_version, new_version, changes_count
    - `manifest_updated` — strategy_slug, version, event_type (created/confirmed/modified)
  - [x]D6 format: all log calls go through `get_logger()` which handles D6's structured JSON schema. Log the event name and context fields as `extra` kwargs — do NOT manually construct JSON log lines

- [x] **Task 8: Write tests** (AC: #1-#8)
  - [x]Create `src/python/tests/test_strategy/test_reviewer.py`:
    - `test_summary_includes_indicators` — summary contains indicator names and params in plain English
    - `test_summary_includes_entry_logic` — entry conditions rendered as readable text
    - `test_summary_includes_exit_logic` — stop loss, take profit described in plain English
    - `test_summary_includes_filters` — session/volatility filters listed
    - `test_summary_includes_position_sizing` — sizing method described
    - `test_summary_includes_pair_timeframe` — pair and timeframe present
    - `test_summary_no_raw_spec_format` — output contains no TOML/JSON/dict syntax
    - `test_summary_complex_strategy` — Bollinger+RSI+filters rendered correctly
    - `test_summary_artifact_persisted` — `save_summary_artifact()` writes file to expected path
  - [x]Create `src/python/tests/test_strategy/test_versioner.py`:
    - `test_increment_version_v001_to_v002` — basic increment
    - `test_increment_version_v099_to_v100` — boundary
    - `test_increment_version_v999_to_v1000` — overflow to 4 digits
    - `test_diff_stop_loss_change` — diff detects stop loss value change
    - `test_diff_filter_added` — diff detects new filter
    - `test_diff_filter_removed` — diff detects removed filter
    - `test_diff_multiple_changes` — diff captures all changes
    - `test_diff_no_changes` — empty changes list when specs identical
    - `test_diff_ignores_metadata` — version/timestamp changes not in diff
    - `test_format_diff_plain_english` — formatted diff is human-readable
    - `test_manifest_create` — new manifest with initial version
    - `test_manifest_update_version` — add new version entry
    - `test_manifest_confirmation_recorded` — confirmed_at and config_hash present
    - `test_manifest_roundtrip_json` — save and load produces identical manifest
    - `test_manifest_latest_confirmed_version` — `latest_confirmed_version` updated on confirmation, remains stable after new draft created
  - [x]Create `src/python/tests/test_strategy/test_confirmer.py`:
    - `test_confirm_sets_status_confirmed` — status changes from draft to confirmed
    - `test_confirm_attaches_config_hash` — config_hash present and non-empty
    - `test_confirm_attaches_confirmation_timestamp` — confirmed_at is valid ISO timestamp
    - `test_confirm_computes_spec_hash` — spec_hash present via Story 2.3 hasher
    - `test_confirm_rejects_already_confirmed` — raise error or return existing confirmation
    - `test_confirm_updates_manifest` — manifest contains confirmed version entry
    - `test_confirm_crash_safe_write` — uses safe_write pattern
    - `test_confirm_sets_latest_confirmed_version` — manifest `latest_confirmed_version` points to confirmed version
  - [x]Create `src/python/tests/test_strategy/test_modifier.py`:
    - `test_parse_modification_stop_loss` — structured input parsed to ModificationIntent
    - `test_parse_modification_add_filter` — add action parsed correctly
    - `test_parse_modification_remove_filter` — remove action parsed correctly
    - `test_parse_modification_invalid_field` — raises error for unknown field path
    - `test_apply_creates_new_version` — v001 → v002
    - `test_apply_preserves_previous_version` — v001 file unchanged after modification
    - `test_apply_validates_modified_spec` — modified spec passes Story 2.3 validation
    - `test_apply_diff_shows_changes` — diff accurately describes modifications
    - `test_apply_multiple_modifications` — multiple changes in one call
    - `test_apply_modification_to_confirmed_spec` — creates new draft version from confirmed
    - `test_find_latest_version` — correctly identifies highest version
  - [x]Create `src/python/tests/test_strategy/test_review_e2e.py`:
    - `test_e2e_review_confirm_flow` — generate summary → confirm → verify locked status + config_hash + manifest
    - `test_e2e_modify_review_confirm_flow` — create v001 → modify → v002 → review → confirm → verify diff + manifest
    - `test_e2e_modification_chain` — v001 → v002 → v003, all preserved, manifest tracks all
  - [x]**Test location:** `src/python/tests/test_strategy/` (same directory as Story 2.4 tests)
  - [x]**Test fixtures:** Create helpers for building test `StrategySpecification` instances — reuse Story 2.3/2.4 fixture patterns

## Dev Notes

### Architecture Constraints

- **D10 — Strategy Execution Model:** Three-layer model. This story operates at the Specification layer. Review translates spec → human-readable. Confirmation locks spec for Evaluation layer. Modification creates new spec version. The AI layer (Claude Code skill) handles natural language; Python handles deterministic spec manipulation.
- **D10 — Modification Flow (FR73):** Operator: "try wider stops" → Claude Code `/strategy-update` skill → reads current spec → identifies stop_loss parameter → creates new spec version → saves as new versioned artifact → operator reviews diff and confirms. Python code MUST be deterministic and testable; the skill handles AI interpretation.
- **D7 — Configuration:** Config hash computed from `config/base.toml` + active environment TOML. Hash embedded in confirmed specification for reproducibility verification. Config hash is NOT spec_hash (content hash) — they serve different purposes.
- **D6 — Structured Logging:** JSON log lines via `logging_setup/setup.py`. Events logged in orchestrator functions, not scattered across utilities.
- **D9 — Operator Interface:** Skills call Python CLI entrypoints directly (no REST API yet). This is a deliberate V1 temporary exception — REST migration happens when the orchestrator/API layer lands. TODO comments in skills mark this.
- **NFR15 — Crash-Safe Writes:** All file writes via `safe_write()` — write to `.partial`, fsync, atomic rename. Never overwrite complete artifact with partial data.
- **FR12 — Immutability:** Previous specification versions NEVER overwritten. Modifications always create new versions. Confirmation updates status metadata in-place (same version file) but this is a status change, not content change.
- **FR73 — Modification Scope:** FR73 is Growth phase in the PRD. This story implements the *deterministic structured modification primitives* (Task 5) needed for versioning to function. The natural-language interpretation lives in the Claude Code skill (Task 6), not Python. Full NL modification orchestration is Growth scope.
- **Manifest Location:** V1 places manifest logic in `strategy/versioner.py` because `artifacts/` shared infrastructure doesn't exist yet. Architecture specifies `artifacts/manifest.py` for cross-pipeline manifest management — migrate when other stages need manifests (Epic 3+).
- **Downstream Contract:** Downstream consumers (Epic 3 backtesting) MUST read `latest_confirmed_version` from the manifest to identify the pipeline-approved spec. `current_version` tracks the latest version (which may be draft). Never use `current_version` as the pipeline input pointer.

### Technical Requirements

- **Python version:** Match project venv (3.11+)
- **Pydantic v2:** Use `BaseModel` for dataclasses that need validation (`ModificationIntent`, `ConfirmationResult`). Use stdlib `dataclasses` for internal-only structures (`StrategySummary`, `FieldChange`).
- **No new dependencies:** Pure Python string formatting for summaries, `json` stdlib for manifest, `hashlib` for config hashing.
- **TOML:** Use existing `tomli`/`tomli_w` patterns from `config_loader`.
- **Determinism:** `format_summary_text()` must produce identical output for identical specs. `compute_version_diff()` must produce identical diffs for identical spec pairs. No timestamps in diff output — only in manifest.

### Specification Status Lifecycle

```
draft ──── confirm_specification() ────→ confirmed
  │                                          │
  │   apply_modifications()                  │   apply_modifications()
  │   (creates v002 draft)                   │   (creates v002 draft from confirmed v001)
  ↓                                          ↓
draft (v002) ── confirm ──→ confirmed (v002)
```

- `draft`: Created by Story 2.4 intent capture or by modification in this story
- `confirmed`: Locked by operator confirmation. Has `config_hash` and `confirmed_at`
- Modifications always produce new `draft` version regardless of source version's status
- Each version file retains its own status independently

### Version File Layout

```
artifacts/strategies/{strategy_slug}/
├── v001.toml          # Draft from Story 2.4 intent capture
├── v002.toml          # Modified version (Story 2.5)
├── v003.toml          # Another modification
├── manifest.json      # Version history, timestamps, hashes
├── reviews/
│   ├── v001_summary.txt   # Persisted human-readable review
│   └── v002_summary.txt
└── diffs/
    └── v001_v002_diff.txt # Persisted version diff
```

### Manifest JSON Schema

```json
{
  "strategy_slug": "ma-crossover-eurusd-h1",
  "current_version": "v002",
  "latest_confirmed_version": "v001",
  "versions": [
    {
      "version": "v001",
      "status": "confirmed",
      "created_at": "2026-03-15T10:00:00Z",
      "confirmed_at": "2026-03-15T10:05:00Z",
      "config_hash": "a1b2c3d4e5f6g7h8",
      "spec_hash": "f8e7d6c5b4a39281"
    },
    {
      "version": "v002",
      "status": "draft",
      "created_at": "2026-03-15T11:00:00Z",
      "confirmed_at": null,
      "config_hash": null,
      "spec_hash": "1a2b3c4d5e6f7g8h"
    }
  ]
}
```

### Critical Design Decisions

1. **Summary generation is pure text transformation** — no LLM calls from Python. The spec structure is known; map each field to English template. E.g., `{"type": "SMA", "params": {"period": 20, "source": "close"}}` → `"Simple Moving Average (period: 20, source: close)"`.
2. **Diff comparison is field-by-field** — compare entry_rules, exit_rules, filters, position_sizing recursively. Use `deepdiff`-style comparison but implement inline (no new dependency). Ignore metadata fields (version, timestamps, hashes).
3. **Config hash scope:** Hash `base.toml` + active environment config only. Do NOT hash strategy-specific config (that's the spec itself). This links the spec to the pipeline infrastructure state.
4. **Manifest is JSON, not TOML:** The manifest is artifact metadata, not configuration. D7 (TOML for config) does not apply. JSON is more natural for structured metadata with nullable fields.

### What to Reuse (Existing Codebase)

| Module | Function | Strategy |
|--------|----------|----------|
| `src/python/strategy/specification.py` | `StrategySpecification` | Import model — review, diff, and modify operate on this |
| `src/python/strategy/loader.py` | `validate_strategy_spec()` | Validate after modification — do NOT reimplement |
| `src/python/strategy/storage.py` | `save_strategy_spec()`, `load_strategy_spec()` | Save/load versioned specs — do NOT reimplement |
| `src/python/strategy/hasher.py` | `compute_spec_hash()` | Content hash for specs — do NOT reimplement |
| `src/python/strategy/indicator_registry.py` | Indicator metadata | Use for plain English indicator names in summary |
| `src/python/config_loader/hasher.py` | `compute_config_hash()` | Pipeline config hash — use if exists, create if missing |
| `src/python/config_loader/loader.py` | Config loading patterns | Reference for TOML loading approach |
| `src/python/data_pipeline/utils/safe_write.py` | `safe_write()` | Crash-safe file writes — do NOT reimplement |
| `src/python/logging_setup/setup.py` | `get_logger()` | Structured logging — do NOT create new logger |

### What to Reuse from ClaudeBackTester

Story 2.5 is entirely new architecture — ClaudeBackTester has no review/confirmation/versioning capability. The baseline mapping confirms: "Strategy Authoring: Replace / add new layer — Major unresolved gap." No baseline code to port.

However, indicator display names from the Story 2.1 baseline catalogue (SMA, EMA, ATR, RSI, MACD, Bollinger) should inform the reviewer's plain English indicator descriptions.

### Anti-Patterns to Avoid

1. **Do NOT call LLM from Python** — Claude Code skill handles AI interpretation; Python must be deterministic and testable
2. **Do NOT reimplement spec validation** — use Story 2.3's `validate_strategy_spec()`
3. **Do NOT reimplement versioned storage** — use Story 2.3's `save_strategy_spec()` / `load_strategy_spec()`
4. **Do NOT reimplement spec hashing** — use Story 2.3's `compute_spec_hash()`
5. **Do NOT reimplement crash-safe writes** — use `safe_write()` from data_pipeline utils
6. **Do NOT create new logging system** — use existing `logging_setup`
7. **Do NOT expose raw spec format in summary** — the entire point of FR11 is human-readable, no code visibility
8. **Do NOT mutate specs in place** — modifications create copies; original preserved for diff
9. **Do NOT overwrite previous versions** — FR12 requires immutability; always create new version file
10. **Do NOT add profitability checks or quality gates** — V1 pipeline proof comes first (project feedback)
11. **Do NOT create web UI or API endpoints** — CLI/skill-based only per D9/D10 at this stage
12. **Do NOT implement strategy retirement/kill logic** — that's FR79-FR82, Epic 8 scope
13. **Do NOT implement optimization_plan or cost_model_reference** — Story 2.8 and 2.6 respectively handle those
14. **Do NOT add a `deepdiff` or similar dependency** — implement field comparison inline, specs are simple nested dicts
15. **Do NOT skip hash verification** — when loading a spec, recompute `spec_hash` and compare to stored value; mismatch indicates file corruption or manual tampering
16. **Do NOT use string paths** — always use `Path(...).resolve()` for artifact paths to ensure Windows/Git Bash cross-platform compatibility (project feedback: Windows compat)

### Project Structure Notes

**Files to create:**
- `src/python/strategy/reviewer.py`
- `src/python/strategy/versioner.py`
- `src/python/strategy/confirmer.py`
- `src/python/strategy/modifier.py`
- `src/python/strategy/__main__.py`
- `.claude/skills/strategy_review.md`
- `.claude/skills/strategy_update.md`
- `src/python/tests/test_strategy/test_reviewer.py`
- `src/python/tests/test_strategy/test_versioner.py`
- `src/python/tests/test_strategy/test_confirmer.py`
- `src/python/tests/test_strategy/test_modifier.py`
- `src/python/tests/test_strategy/test_review_e2e.py`

**Files to create conditionally:**
- `src/python/config_loader/hasher.py` — only if missing from Story 1.3

**Existing files to import from (no modification):**
- `src/python/strategy/specification.py` (Story 2.3)
- `src/python/strategy/loader.py` (Story 2.3)
- `src/python/strategy/storage.py` (Story 2.3)
- `src/python/strategy/hasher.py` (Story 2.3)
- `src/python/strategy/indicator_registry.py` (Story 2.3)
- `src/python/data_pipeline/utils/safe_write.py` (Story 1.x)
- `src/python/logging_setup/setup.py` (Story 1.3)
- `src/python/config_loader/loader.py` (Story 1.3)

**Existing files to update:**
- `src/python/strategy/__init__.py` — export new modules (`reviewer`, `versioner`, `confirmer`, `modifier`)

### Data Naming Note

ClaudeBackTester uses `EUR_USD`; Pipeline uses `EURUSD`. The reviewer's summary should display the Pipeline convention (`EURUSD`). All spec fields already use `EURUSD` per Story 2.4's normalization.

### References

- [Source: _bmad-output/planning-artifacts/prd.md — FR11, FR12, FR38, FR41, FR58, FR59, FR61, FR73]
- [Source: _bmad-output/planning-artifacts/architecture.md — D6 (Logging), D7 (Configuration), D9 (Operator Interface), D10 (Strategy Execution Model), NFR15 (Crash-Safe Writes)]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 2, Story 2.5]
- [Source: _bmad-output/implementation-artifacts/2-3-strategy-specification-schema-contracts.md — Schema, validation, storage, hashing contracts]
- [Source: _bmad-output/implementation-artifacts/2-4-strategy-intent-capture-dialogue-to-specification.md — Intent capture flow, dependency list, parsing patterns]
- [Source: _bmad-output/planning-artifacts/baseline-to-architecture-mapping.md — Strategy authoring gap assessment]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Debug Log References
- Fixed manifest bootstrap in modifier.py: when no manifest exists and a modification is applied, the old version entry is now added to the manifest before the new one, ensuring complete version history.

### Completion Notes List
- Task 1: All Story 2.3/2.4 dependencies verified present including config_loader/hasher.py
- Task 2: Created reviewer.py with generate_summary(), format_summary_text(), save_summary_artifact(). Pure text transformation, no LLM calls. Maps indicators to human-readable names, translates entry/exit/filter logic to plain English.
- Task 3: Created versioner.py with increment_version(), compute_version_diff(), format_diff_text(), manifest CRUD (load/save/create/update). Field-level recursive diff comparison ignoring metadata fields.
- Task 4: Created confirmer.py with confirm_specification(). Idempotent confirmation: loads config, computes config_hash, sets status=confirmed, updates manifest with latest_confirmed_version pointer.
- Task 5: Created modifier.py with parse_modification_intent(), apply_single_modification(), apply_modifications(). Supports set/add/remove actions. Creates new version, validates via Story 2.3, saves diff artifact, updates manifest. Version collision guard prevents silent overwrites.
- Task 6: Created __main__.py CLI dispatcher (review/confirm/modify/manifest commands) and two Claude Code skills (strategy_review.md, strategy_update.md).
- Task 7: All modules use get_logger() from logging_setup. Events logged: strategy_review_artifact_saved, version_diff_artifact_saved, manifest_updated, strategy_confirmation_start, strategy_confirmed, strategy_modification_start, strategy_modification_complete.
- Task 8: 54 unit tests + 3 live integration tests across 5 test files. Full regression suite: 124 passed, 0 failures.

### Change Log
- 2026-03-16: Implemented Story 2.5 — Strategy Review, Confirmation & Versioning. Created 4 core modules (reviewer, versioner, confirmer, modifier), CLI entrypoints, 2 Claude Code skills, and comprehensive test suite (57 tests total).

### File List
**New files:**
- `src/python/strategy/reviewer.py`
- `src/python/strategy/versioner.py`
- `src/python/strategy/confirmer.py`
- `src/python/strategy/modifier.py`
- `src/python/strategy/__main__.py`
- `.claude/skills/strategy_review.md`
- `.claude/skills/strategy_update.md`
- `src/python/tests/test_strategy/test_reviewer.py`
- `src/python/tests/test_strategy/test_versioner.py`
- `src/python/tests/test_strategy/test_confirmer.py`
- `src/python/tests/test_strategy/test_modifier.py`
- `src/python/tests/test_strategy/test_review_e2e.py`

**Modified files:**
- `src/python/strategy/__init__.py` — added exports for reviewer, versioner, confirmer, modifier
