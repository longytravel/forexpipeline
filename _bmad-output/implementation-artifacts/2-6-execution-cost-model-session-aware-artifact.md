# Story 2.6: Execution Cost Model — Session-Aware Artifact

Status: review

## Story

As a the operator,
I want a researched execution cost model with session-aware spread and slippage profiles,
So that backtesting uses realistic transaction costs instead of flat assumptions.

## Acceptance Criteria

1. **Given** execution cost research data (broker-published spreads, historical tick data analysis, session profiles)
   **When** the cost model artifact is created for a currency pair
   **Then** the artifact follows D13's format: pair, version, source, calibrated_at, and per-session profiles (Asian, London, New York, London/NY overlap, off-hours)
   [Source: architecture.md — D13; FR20]

2. **Given** a cost model artifact with per-session profiles
   **When** any session profile is inspected
   **Then** it contains statistical distribution parameters: mean_spread_pips, std_spread, mean_slippage_pips, std_slippage — not flat constants
   [Source: architecture.md — D13; FR21]

3. **Given** the Python cost model builder
   **When** creating a cost model artifact
   **Then** the builder supports three input modes: research data (manual input), historical tick data analysis (automated), and live calibration data (interface only — actual live data comes in Epic 7)
   [Source: epics.md — Story 2.6 AC3; FR22]

4. **Given** an existing cost model artifact at version vNNN
   **When** a new cost model artifact is created for the same pair
   **Then** the new artifact is versioned (v001 → v002) and previous versions are preserved, never overwritten
   [Source: architecture.md — D2; FR20, FR60]

5. **Given** the contracts directory
   **When** the cost model schema is defined
   **Then** a schema definition exists at `contracts/cost_model_schema.toml` and cost model artifacts are validated against it before saving
   [Source: epics.md — Story 2.6 AC5]

6. **Given** the pipeline proof requirements
   **When** the default cost model is needed
   **Then** a default EURUSD cost model artifact is created from research data as a baseline for pipeline proofs (Story 2.9)
   [Source: epics.md — Story 2.6 AC6]

7. **Given** any cost model artifact write operation
   **When** the artifact is saved to disk
   **Then** the crash-safe write pattern is used (write to .partial, fsync, atomic rename)
   [Source: architecture.md — NFR15]

8. **Given** the cost model builder completing artifact creation
   **When** creation is finished
   **Then** the builder logs session profile statistics and data sources used via structured logging
   [Source: architecture.md — D6]

9. **Given** a cost model manifest
   **When** downstream consumers (Story 2.7 Rust crate, Story 2.9 E2E proof) need to load a cost model
   **Then** the manifest contains a `latest_approved_version` pointer identifying the pipeline-approved artifact, and consumers use this pointer — not raw "latest file"
   [Source: Story 2.5 `latest_confirmed_version` pattern; architecture.md — D7 config hash in manifests]

10. **Given** a cost model manifest version entry
    **When** the entry is inspected
    **Then** it contains: version, status, created_at, approved_at, config_hash, artifact_hash, and input_hash for reproducibility verification
    [Source: architecture.md — D7 line 518; FR60]

## Tasks / Subtasks

- [x] **Task 1: Verify dependencies and establish cost model package** (AC: all)
  - [x]Confirm `src/python/data_pipeline/utils/safe_write.py` exists with `safe_write()` function
  - [x]Confirm `src/python/logging_setup/setup.py` exists with `get_logger()` function
  - [x]Confirm `config/base.toml` exists and contains session definitions (Asian, London, New York, London/NY overlap, off-hours) with UTC time boundaries
  - [x]If session definitions are missing from config/base.toml, create them following D7 config pattern
  - [x]Confirm Story 2.2 research artifact exists at expected location — if not, note that default EURUSD values will use reasonable broker-published defaults
  - [x]Create `src/python/cost_model/__init__.py` exporting public API
  - [x]STOP and report blocker if safe_write or logging dependencies missing

- [x] **Task 2: Create cost model schema definition and dataclasses** (AC: #1, #2, #5)
  - [x]Create `contracts/cost_model_schema.toml` defining:
    - Required fields: pair (string), version (string, pattern "v\d{3,}"), source (string, enum: "research", "tick_analysis", "live_calibration"), calibrated_at (string, ISO 8601 UTC), sessions (table)
    - Required session keys: asian, london, new_york, london_ny_overlap, off_hours
    - Per-session required fields: mean_spread_pips (float, ≥0), std_spread (float, ≥0), mean_slippage_pips (float, ≥0), std_slippage (float, ≥0)
    - Optional metadata: description (string), data_points (int), confidence_level (string)
  - [x]Create `src/python/cost_model/schema.py` with:
    - `@dataclass SessionProfile`: mean_spread_pips (float), std_spread (float), mean_slippage_pips (float), std_slippage (float)
    - `@dataclass CostModelArtifact`: pair (str), version (str), source (str), calibrated_at (str), sessions (dict[str, SessionProfile]), metadata (dict | None)
    - Function `validate_cost_model(artifact: CostModelArtifact, schema_path: Path) -> list[str]`: validate artifact against TOML schema, return list of validation errors (empty = valid)
    - Function `load_schema(schema_path: Path) -> dict`: load and parse contracts/cost_model_schema.toml
    - Constants: `VALID_SOURCES = ("research", "tick_analysis", "live_calibration")`, `REQUIRED_SESSIONS = ("asian", "london", "new_york", "london_ny_overlap", "off_hours")`
  - [x]Export: SessionProfile, CostModelArtifact, validate_cost_model, load_schema, VALID_SOURCES, REQUIRED_SESSIONS

- [x] **Task 3: Create session management module** (AC: #1, #2)
  - [x]Create `src/python/cost_model/sessions.py` with:
    - Function `load_session_definitions(config_path: Path) -> dict[str, dict]`: load session time boundaries from config/base.toml, return dict mapping session name → {start_utc, end_utc, description}
    - Function `validate_session_coverage(sessions: dict[str, dict]) -> list[str]`: verify all 5 required sessions are defined and time boundaries don't have gaps
    - Function `get_session_for_time(hour_utc: int, session_defs: dict) -> str`: return session label for a given UTC hour
    - Constants: `SESSION_NAMES = ("asian", "london", "new_york", "london_ny_overlap", "off_hours")`
  - [x]Session time boundaries (from config/base.toml — architecture authoritative):
    - asian: 00:00–08:00 UTC
    - london: 08:00–13:00 UTC (London-only hours; London market runs 08:00–16:00 but 13:00–16:00 is classified as overlap)
    - london_ny_overlap: 13:00–16:00 UTC (both London and NY markets open)
    - new_york: 16:00–21:00 UTC (NY-only hours; NY market runs 13:00–21:00 but 13:00–16:00 is classified as overlap)
    - off_hours: 21:00–00:00 UTC
  - [x]Note: config/base.toml defines overlapping market presence (London 08:00–16:00, NY 13:00–21:00). The session LABEL assignment uses priority resolution: overlap > specific session > off_hours. A bar at 14:00 UTC gets label "london_ny_overlap", not "london" or "new_york".
  - [x]Export: load_session_definitions, validate_session_coverage, get_session_for_time, SESSION_NAMES

- [x] **Task 4: Create cost model builder** (AC: #1, #2, #3, #6, #8)
  - [x]Create `src/python/cost_model/builder.py` with:
    - `class CostModelBuilder`:
      - `__init__(self, config_path: Path, contracts_path: Path, artifacts_dir: Path)`: load session definitions, schema
      - `from_research_data(self, pair: str, research_data: dict[str, dict]) -> CostModelArtifact`: create artifact from manual research data dict mapping session → {mean_spread_pips, std_spread, mean_slippage_pips, std_slippage}
      - `from_tick_data(self, pair: str, tick_data_path: Path) -> CostModelArtifact`: create artifact by analyzing historical bid/ask tick data, computing per-session spread/slippage distributions
      - `from_live_calibration(self, pair: str, calibration_data: dict) -> CostModelArtifact`: interface stub — raises NotImplementedError with message "Live calibration data integration available in Epic 7 (FR22)"
      - `_build_artifact(self, pair: str, source: str, sessions: dict[str, SessionProfile]) -> CostModelArtifact`: internal — assemble artifact with version, timestamp, validate against schema
      - `build_default_eurusd(self) -> CostModelArtifact`: create default EURUSD cost model using research-based values (see Dev Notes for values)
    - All builder methods validate output against schema before returning
    - All builder methods log via get_logger() (D6): cost_model_build_start, cost_model_build_complete with session statistics
  - [x]Export: CostModelBuilder

- [x] **Task 5: Create versioned storage module** (AC: #4, #7)
  - [x]Create `src/python/cost_model/storage.py` with:
    - Function `save_cost_model(artifact: CostModelArtifact, artifacts_dir: Path) -> Path`: save artifact as JSON to `artifacts/cost_models/{pair}/v{NNN}.json` via safe_write(), return saved path
    - Function `load_cost_model(pair: str, version: str, artifacts_dir: Path) -> CostModelArtifact`: load artifact from JSON, validate against schema
    - Function `load_latest_cost_model(pair: str, artifacts_dir: Path) -> CostModelArtifact | None`: find highest version for pair, load it
    - Function `get_next_version(pair: str, artifacts_dir: Path) -> str`: scan existing versions, return next (e.g., "v002" if v001 exists)
    - Function `list_versions(pair: str, artifacts_dir: Path) -> list[str]`: return sorted list of existing versions
    - Function `save_manifest(pair: str, artifact: CostModelArtifact, artifacts_dir: Path, config_hash: str | None = None) -> Path`: create/update manifest.json with version history following Story 2.5 manifest pattern. Each version entry includes: version, status ("draft"|"approved"), created_at, approved_at (None until approved), config_hash, artifact_hash (SHA-256 of artifact JSON content), input_hash (SHA-256 of input data used to build the artifact)
    - Function `approve_version(pair: str, version: str, artifacts_dir: Path) -> Path`: set version status to "approved", update `latest_approved_version` pointer in manifest. For V1, `build_default_eurusd` auto-approves since it's the baseline.
    - Function `load_manifest(pair: str, artifacts_dir: Path) -> dict | None`: load manifest.json
    - Manifest must include `latest_approved_version` pointer — downstream consumers (Story 2.7, 2.9) MUST use this, never raw "latest file" (following Story 2.5 `latest_confirmed_version` pattern)
    - All writes use safe_write() from data_pipeline/utils/safe_write.py (NFR15)
    - Never overwrite existing version files — fail-loud if version collision detected
  - [x]Artifact directory layout:
    ```
    artifacts/cost_models/{pair}/
    ├── v001.json
    ├── v002.json
    └── manifest.json
    ```
  - [x]Export: save_cost_model, load_cost_model, load_latest_cost_model, get_next_version, list_versions, save_manifest, load_manifest, approve_version

- [x] **Task 6: Create default EURUSD cost model** (AC: #6, #9, #10)
  - [x]In builder.py `build_default_eurusd()`, use research-based values (see Dev Notes for EURUSD defaults)
  - [x]Save default artifact to `artifacts/cost_models/EURUSD/v001.json`
  - [x]Create manifest.json for EURUSD with config_hash, artifact_hash, input_hash
  - [x]Auto-approve v001 as `latest_approved_version` (it's the baseline for pipeline proofs)
  - [x]Create CLI command or script to generate default: `python -m src.python.cost_model create-default`
  - [x]If Story 2.2 research artifact exists, use its values instead of hardcoded defaults

- [x] **Task 7: Create CLI entrypoint** (AC: #3, #8)
  - [x]Create `src/python/cost_model/__main__.py` — CLI dispatcher using argparse:
    - `python -m src.python.cost_model create-default` → build and save default EURUSD cost model
    - `python -m src.python.cost_model create <pair> --source research --data '<json>'` → create from research data
    - `python -m src.python.cost_model create <pair> --source tick_analysis --tick-data <path>` → create from tick data
    - `python -m src.python.cost_model show <pair> [--version v001]` → display cost model artifact
    - `python -m src.python.cost_model list <pair>` → list versions
    - `python -m src.python.cost_model validate <pair> [--version v001]` → validate against schema
  - [x]No new dependencies — argparse, json, pathlib only

- [x] **Task 8: Implement structured logging** (AC: #8)
  - [x]Use `src/python/logging_setup/setup.py` → `get_logger()` (do NOT create new logging)
  - [x]Log events in builder orchestrator functions:
    - `cost_model_build_start`: pair, source, session_count
    - `cost_model_build_complete`: pair, version, source, session_stats (per-session mean_spread summary)
    - `cost_model_validated`: pair, version, validation_errors_count
    - `cost_model_saved`: pair, version, path, manifest_updated
    - `cost_model_load`: pair, version, path
  - [x]D6 format: all log calls via get_logger() which handles structured JSON schema

- [x] **Task 9: Write tests** (AC: #1–#8)
  - [x]Create `src/python/tests/test_cost_model/__init__.py`
  - [x]Create `src/python/tests/test_cost_model/test_schema.py`:
    - `test_session_profile_creation` — valid SessionProfile
    - `test_session_profile_negative_values_rejected` — validation catches negative spreads
    - `test_cost_model_artifact_creation` — valid CostModelArtifact with all required fields
    - `test_cost_model_missing_session_rejected` — validation catches missing required sessions
    - `test_cost_model_invalid_source_rejected` — validation catches invalid source enum
    - `test_schema_loading` — contracts/cost_model_schema.toml loads correctly
    - `test_validate_cost_model_valid` — valid artifact passes validation
    - `test_validate_cost_model_invalid` — invalid artifact returns errors list
  - [x]Create `src/python/tests/test_cost_model/test_sessions.py`:
    - `test_load_session_definitions` — loads from config/base.toml
    - `test_session_coverage_complete` — all 24 hours covered
    - `test_session_coverage_gaps_detected` — missing session flagged
    - `test_get_session_for_time` — correct session label for various UTC hours
    - `test_get_session_overlap_priority` — 14:00 UTC returns "london_ny_overlap", not "london" or "new_york"
    - `test_all_required_sessions_present` — 5 sessions defined
  - [x]Create `src/python/tests/test_cost_model/test_builder.py`:
    - `test_from_research_data_valid` — creates valid artifact from dict
    - `test_from_research_data_missing_session` — fails with clear error
    - `test_from_tick_data_valid` — creates artifact from tick data file
    - `test_from_live_calibration_raises` — NotImplementedError with Epic 7 message
    - `test_build_default_eurusd` — creates valid EURUSD with all 5 sessions
    - `test_builder_validates_output` — schema validation runs before return
    - `test_builder_logs_events` — structured log events emitted
  - [x]Create `src/python/tests/test_cost_model/test_storage.py`:
    - `test_save_cost_model_creates_json` — file created at correct path
    - `test_save_cost_model_crash_safe` — uses safe_write (write .partial, rename)
    - `test_load_cost_model_roundtrip` — save then load preserves all data
    - `test_load_latest_version` — returns highest version
    - `test_get_next_version_empty` — returns "v001" when no versions exist
    - `test_get_next_version_increment` — returns "v002" when v001 exists
    - `test_version_collision_rejected` — saving existing version fails
    - `test_manifest_creation` — manifest.json created on first save
    - `test_manifest_update` — manifest.json updated on subsequent saves
    - `test_manifest_latest_approved_version` — `latest_approved_version` updated on approval, stable after new draft created
    - `test_approve_version` — sets status to "approved", updates pointer
    - `test_manifest_contains_hashes` — config_hash, artifact_hash, input_hash present in version entries
    - `test_list_versions` — returns sorted version list
    - `test_previous_versions_preserved` — v001 unchanged after v002 created
  - [x]Create `src/python/tests/test_cost_model/test_e2e.py`:
    - `test_create_default_eurusd_e2e` — full flow: build → validate → save → load → verify
    - `test_version_chain_e2e` — create v001, create v002, both loadable, manifest correct
    - `test_cli_create_default` — CLI command produces valid artifact file

## Dev Notes

### Architecture Constraints

- **D13 (Cost Model Crate):** Cost model is a Rust library crate at `crates/cost_model/`. Story 2.6 creates the Python builder and JSON artifacts. Story 2.7 creates the Rust crate that reads these artifacts. The JSON artifact format is the CONTRACT between Python (builder) and Rust (consumer) — do not deviate from the schema.
- **D2 (Artifact Schema):** Three-format hybrid (Arrow IPC / SQLite / Parquet). Cost model artifacts are JSON — they are metadata/config artifacts, not bulk data. Manifests are also JSON.
- **D7 (Configuration):** Session time boundaries defined in `config/base.toml`. Use `tomllib` (Python 3.11+) to load. Cost model artifacts are NOT config — they are pipeline artifacts stored in `artifacts/` directory.
- **D6 (Structured Logging):** All logging via `get_logger()` from `logging_setup/setup.py`. JSON structured log lines. Log at orchestrator boundaries, not scattered.
- **D8 (Error Handling):** Fail-fast at boundaries. Invalid schema = fail-loud. Missing required session = fail-loud. Never silently skip.
- **D12 (Reconciliation):** Cost model auto-updates from observed execution data via `cost_model_updater.py` — this is Epic 7/8 scope. Story 2.6 only creates the artifact format and builder. The `from_live_calibration` interface stub enables this future integration.
- **NFR15 (Crash-Safe Writes):** All file writes via `safe_write()` — write to `.partial`, fsync, atomic rename.

### Default EURUSD Research Values

Use these research-based defaults for the EURUSD cost model (typical major pair ECN broker conditions). If Story 2.2 research artifact exists with refined values, use those instead.

```
asian:              mean_spread=1.2, std_spread=0.4, mean_slippage=0.1, std_slippage=0.05
london:             mean_spread=0.8, std_spread=0.3, mean_slippage=0.05, std_slippage=0.03
london_ny_overlap:  mean_spread=0.6, std_spread=0.2, mean_slippage=0.03, std_slippage=0.02
new_york:           mean_spread=0.9, std_spread=0.3, mean_slippage=0.06, std_slippage=0.03
off_hours:          mean_spread=1.5, std_spread=0.6, mean_slippage=0.15, std_slippage=0.08
```

These values reflect: tightest spreads during London/NY overlap (peak liquidity), wider during Asian session, widest during off-hours (low liquidity). Values are in pips.

### Pair Naming Convention

Architecture uses EURUSD format (no separator). ClaudeBackTester uses EUR_USD. This project uses EURUSD consistently. Do NOT use underscore separators.

### Cost Model Artifact Format (JSON)

Per D13, the artifact is JSON with this structure:
```json
{
  "pair": "EURUSD",
  "version": "v001",
  "source": "research",
  "calibrated_at": "2026-03-15T00:00:00Z",
  "sessions": {
    "asian": {
      "mean_spread_pips": 1.2,
      "std_spread": 0.4,
      "mean_slippage_pips": 0.1,
      "std_slippage": 0.05
    },
    "london": { ... },
    "london_ny_overlap": { ... },
    "new_york": { ... },
    "off_hours": { ... }
  },
  "metadata": {
    "description": "Research-based EURUSD cost model — ECN broker typical conditions",
    "data_points": null,
    "confidence_level": "research_estimate"
  }
}
```

### Downstream Consumers

- **Story 2.7 (Cost Model Rust Crate):** Will parse this JSON artifact with serde, build O(1) session → cost lookup. The JSON schema is the Rust ↔ Python interface contract. **V1 consumer semantics:** The Rust consumer uses `mean_spread_pips` and `mean_slippage_pips` directly (deterministic). `std_spread` and `std_slippage` are stored for future stochastic sampling (seeded RNG for reproducibility) but NOT consumed in V1 backtesting. This ensures V1 backtests are fully deterministic with no seed management complexity.
- **Story 2.8 (Strategy Engine):** Validates that `cost_model_reference` in strategy specs points to a valid cost model version.
- **Story 2.9 (E2E Pipeline Proof):** Loads default EURUSD cost model via `latest_approved_version` from manifest, verifies round-trip: Python builds → JSON artifact → Rust loads.
- **Story 2.5 (Manifest Pattern):** Follow the same manifest.json pattern established in Story 2.5 versioner.py — version entries with status, timestamps, hashes, and `latest_approved_version` pointer (analogous to `latest_confirmed_version`).

### Tick Data Analysis Mode

The `from_tick_data` method works with M1 bid+ask bar data from the existing Dukascopy pipeline (Story 1.4/1.6). Spread per bar = ask - bid. For each session:
1. Filter M1 bars by session time boundaries (from config/base.toml), using the priority resolution: overlap > specific session > off_hours
2. Compute spread distribution: mean and std of (ask - bid) across all bars in that session
3. Slippage cannot be computed from historical bar data alone — use conservative research-based estimates (scaled relative to spread) until live calibration data is available in Epic 7. **The artifact metadata must indicate which values are empirical vs. research-estimated** (e.g., `"slippage_source": "research_estimate"`)
4. Data format: load from Parquet files at `data/{pair}/m1/*.parquet` with columns including `bid_open`, `bid_close`, `ask_open`, `ask_close`, `timestamp`
5. **Dependency note:** `from_tick_data` uses pyarrow (already a project dependency from Epic 1 data pipeline). The "no new dependencies" constraint in Task 7 applies to the CLI entrypoint and core schema/builder/storage modules, not to tick analysis which inherently needs Parquet reading.

### Session Architecture Integration

Sessions are a first-class architectural dimension (architecture.md lines 146-222):
- `data_pipeline/arrow_converter.py` stamps session label on every M1 bar in Arrow IPC
- `cost_model/spread_model.rs` (Story 2.7) loads session cost profiles from these artifacts
- `backtester/trade_simulator.rs` passes session label to cost model per fill
- Strategy specs support session filters: `{"filter": {"type": "session", "include": ["london"]}}`

Session definitions in `config/base.toml` are authoritative. The cost model sessions map must use the same session names as config.

**Session overlap resolution for label assignment:**
The config defines overlapping market presence (London 08:00–16:00 and NY 13:00–21:00). For assigning a SINGLE session label to each bar/hour, use priority resolution:
1. If hour falls in `london_ny_overlap` range (13:00–16:00) → label = "london_ny_overlap"
2. Else if hour falls in a specific session range → label = that session
3. Else → label = "off_hours"

This yields non-overlapping label assignments: asian 00:00–08:00, london 08:00–13:00, london_ny_overlap 13:00–16:00, new_york 16:00–21:00, off_hours 21:00–00:00. The `get_session_for_time()` function implements this priority resolution.

### What to Reuse from ClaudeBackTester

**Nothing.** Baseline-to-architecture mapping confirms: "cost_model crate — Does not exist — Build new." ClaudeBackTester has no cost modeling capability. This is fully greenfield.

### Project Structure Notes

**Files to CREATE:**
```
contracts/cost_model_schema.toml
src/python/cost_model/__init__.py
src/python/cost_model/schema.py
src/python/cost_model/builder.py
src/python/cost_model/sessions.py
src/python/cost_model/storage.py
src/python/cost_model/__main__.py
src/python/tests/test_cost_model/__init__.py
src/python/tests/test_cost_model/test_schema.py
src/python/tests/test_cost_model/test_builder.py
src/python/tests/test_cost_model/test_sessions.py
src/python/tests/test_cost_model/test_storage.py
src/python/tests/test_cost_model/test_e2e.py
artifacts/cost_models/EURUSD/v001.json        (generated by build_default_eurusd)
artifacts/cost_models/EURUSD/manifest.json    (generated by save_manifest)
```

**Existing files to IMPORT (no modification):**
```
src/python/data_pipeline/utils/safe_write.py   — safe_write() for crash-safe writes
src/python/logging_setup/setup.py              — get_logger() for structured logging
config/base.toml                               — session time boundary definitions
```

**Artifact directory convention:** `artifacts/cost_models/{PAIR}/v{NNN}.json` — follows D2 artifact schema pattern.

## Anti-Patterns to Avoid

1. Do NOT use flat spread/slippage constants — every session must have statistical distribution parameters (mean + std)
2. Do NOT hardcode session time boundaries in Python — load from config/base.toml (D7)
3. Do NOT create the Rust crate — that is Story 2.7 scope
4. Do NOT implement live calibration data processing — only create the interface stub (Epic 7)
5. Do NOT implement cost model auto-update from reconciliation — that is Epic 7/8 (D12)
6. Do NOT use TOML for the artifact format — D13 specifies JSON
7. Do NOT reimplement safe_write() — import from data_pipeline/utils/safe_write.py
8. Do NOT reimplement logging — use get_logger() from logging_setup/setup.py
9. Do NOT overwrite previous artifact versions — immutable versioning (FR60)
10. Do NOT use string paths — always use `Path(...).resolve()` for Windows/Git Bash compatibility
11. Do NOT add profitability checks or quality gates — V1 pipeline proof first
12. Do NOT use underscore in pair names (EUR_USD) — use EURUSD format consistently
13. Do NOT skip schema validation before saving — every artifact must validate against contracts/cost_model_schema.toml
14. Do NOT create a web UI or REST API — CLI only at this stage (D9 V1 exception)
15. Do NOT add dependencies beyond stdlib for core modules — json, tomllib, pathlib, dataclasses, argparse only (exception: `from_tick_data` may use pyarrow, already a project dependency)
16. Do NOT diverge session boundaries from config/base.toml — the architecture defines overlapping market presence (London 08:00–16:00, NY 13:00–21:00) with priority resolution for label assignment. Never hardcode different boundaries.
17. Do NOT create new versions for unchanged inputs without awareness — log a warning if input_hash matches the latest version's input_hash. The operator should know they're creating a duplicate.
18. Do NOT let downstream consumers load "latest file" — always go through manifest's `latest_approved_version` pointer. Raw latest = unreviewed artifact risk.

## References

- [Source: _bmad-output/planning-artifacts/architecture.md — D13 Cost Model Crate]
- [Source: _bmad-output/planning-artifacts/architecture.md — D2 Artifact Schema & Storage]
- [Source: _bmad-output/planning-artifacts/architecture.md — D6 Structured Logging]
- [Source: _bmad-output/planning-artifacts/architecture.md — D7 Configuration]
- [Source: _bmad-output/planning-artifacts/architecture.md — D8 Error Handling]
- [Source: _bmad-output/planning-artifacts/architecture.md — D12 Reconciliation Data Flow]
- [Source: _bmad-output/planning-artifacts/architecture.md — Session Architecture (lines 146-222)]
- [Source: _bmad-output/planning-artifacts/prd.md — FR20 Execution Cost Model]
- [Source: _bmad-output/planning-artifacts/prd.md — FR21 Session-Aware Spread/Slippage]
- [Source: _bmad-output/planning-artifacts/prd.md — FR22 Cost Model Update]
- [Source: _bmad-output/planning-artifacts/prd.md — FR58 Versioned Artifacts]
- [Source: _bmad-output/planning-artifacts/prd.md — FR60 Input Change Tracking]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR15 Crash-Safe Writes]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 2 Story 2.6]
- [Source: _bmad-output/planning-artifacts/baseline-to-architecture-mapping.md — Cost Model Gap]
- [Source: _bmad-output/implementation-artifacts/2-5-strategy-review-confirmation-versioning.md — Manifest/Versioning Patterns]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

- Initial test run: 19 failed due to `parents[3]` → `parents[4]` path resolution (test files are 4 levels deep from project root)
- Fixed all 5 test files, re-run: 76/76 passed
- Live test CLI failure: e2e test left artifacts in real project dir; fixed with idempotent cleanup (shutil.rmtree before create)
- Final regression: 549 passed, 52 skipped, 0 failures

### Completion Notes List

- **Task 1**: Verified safe_write.py (crash_safe_write), logging_setup (get_logger), config/base.toml (all 5 sessions). No Story 2.2 research artifact — using hardcoded defaults. Created cost_model package.
- **Task 2**: Created contracts/cost_model_schema.toml and schema.py with SessionProfile/CostModelArtifact dataclasses, validate_cost_model(), load_schema(). Version pattern supports 3+ digits (Story 2.5 lesson).
- **Task 3**: Created sessions.py with priority-resolved label boundaries (overlap > specific > off_hours). get_session_for_time() implements architecture spec. Loads from config/base.toml.
- **Task 4**: Created builder.py with CostModelBuilder: from_research_data, from_tick_data (pyarrow Parquet analysis with research-estimated slippage), from_live_calibration (stub → Epic 7), build_default_eurusd. All methods validate against schema before return.
- **Task 5**: Created storage.py with versioned save/load, crash-safe writes via crash_safe_write(), manifest with latest_approved_version pointer (max()-based, not last-touched — Story 2.5 lesson), sha256-prefixed hashes, immutable versioning with fail-loud collision detection. Numeric sorting for 4+ digit versions.
- **Task 6**: build_default_eurusd() uses spec research values. CLI create-default auto-approves v001 as pipeline baseline.
- **Task 7**: Created __main__.py CLI: create-default, create, show, list, validate, approve commands. No new dependencies.
- **Task 8**: Structured logging via get_logger("cost_model.*") at orchestrator boundaries: build_start, build_complete, validated, saved, load events with ctx dicts.
- **Task 9**: 76 unit tests across test_schema (15), test_sessions (17), test_builder (11), test_storage (19), test_e2e (3), plus 3 @pytest.mark.live integration tests. Tests include Story 2.5 lessons: v999→v1000 boundary, max()-based pointer, numeric sorting.

### Change Log

- 2026-03-16: Story 2.6 implementation complete — execution cost model with session-aware artifacts, versioned storage, CLI, structured logging, 79 tests (76 unit + 3 live)

### File List

**Created:**
- contracts/cost_model_schema.toml
- src/python/cost_model/__init__.py
- src/python/cost_model/schema.py
- src/python/cost_model/sessions.py
- src/python/cost_model/builder.py
- src/python/cost_model/storage.py
- src/python/cost_model/__main__.py
- src/python/tests/test_cost_model/__init__.py
- src/python/tests/test_cost_model/test_schema.py
- src/python/tests/test_cost_model/test_sessions.py
- src/python/tests/test_cost_model/test_builder.py
- src/python/tests/test_cost_model/test_storage.py
- src/python/tests/test_cost_model/test_e2e.py
- src/python/tests/test_cost_model/test_live.py
- artifacts/cost_models/EURUSD/v001.json (generated by live test)
- artifacts/cost_models/EURUSD/manifest.json (generated by live test)
