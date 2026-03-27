# Story 1.3: Project Structure, Config & Logging Foundation

Status: done

## Story

As the **operator**,
I want the project directory structure, configuration system, and structured logging established,
So that all subsequent development has a validated foundation to build on.

## Acceptance Criteria

1. **Given** the project directory layout follows the Architecture's structure pattern (D7, D6)
   **When** the project is initialized
   **Then** the directory structure matches the Architecture specification (src/python/, src/rust/, dashboard/, config/, contracts/, artifacts/, logs/)

2. **And** a `config/base.toml` exists with schema validation that fails loud at startup on invalid config (D7)

3. **And** environment-specific config layering works (local.toml, vps.toml)

4. **And** structured JSON logging writes to `logs/` with the unified log schema (D6) — timestamp, level, runtime, component, stage, strategy_id, msg

5. **And** the contracts directory skeleton exists with initial `arrow_schemas.toml` (including both bar and tick data schemas), `sqlite_ddl.sql`, `error_codes.toml`, `session_schema.toml`

6. **And** the crash-safe write pattern (write -> flush -> rename) is implemented as a shared utility

7. **And** a `.env.example` exists for secrets (MT5 credentials)

8. **And** config hash computation works — same config produces same hash

## Tasks / Subtasks

This is a **code story** — the deliverables are working code, config files, and contract files.

- [x] Task 1: Create the project directory structure (AC: #1)
  - [x]1.1: Create the top-level directory layout:
    ```
    forex-pipeline/
    ├── .env.example
    ├── .gitignore
    ├── CLAUDE.md
    ├── config/
    │   ├── base.toml
    │   ├── schema.toml
    │   └── environments/
    │       ├── local.toml
    │       └── vps.toml
    ├── contracts/
    ├── src/
    │   ├── python/
    │   │   ├── pyproject.toml
    │   │   ├── main.py
    │   │   ├── config_loader/
    │   │   ├── logging_setup/
    │   │   ├── artifacts/
    │   │   ├── orchestrator/
    │   │   ├── data_pipeline/
    │   │   ├── strategy/
    │   │   ├── rust_bridge/
    │   │   ├── api/
    │   │   ├── risk/
    │   │   ├── monitoring/
    │   │   ├── mt5_integration/
    │   │   ├── analysis/
    │   │   ├── reconciliation/
    │   │   └── tests/
    │   ├── rust/
    │   │   ├── Cargo.toml
    │   │   ├── rust-toolchain.toml
    │   │   └── crates/
    │   │       ├── common/
    │   │       ├── strategy_engine/
    │   │       ├── cost_model/
    │   │       ├── cost_calibrator/
    │   │       ├── backtester/
    │   │       ├── optimizer/
    │   │       ├── validator/
    │   │       └── live_daemon/
    │   └── dashboard/
    ├── artifacts/
    ├── logs/
    └── scripts/
    ```
  - [x]1.2: Create `__init__.py` files in every Python package directory
  - [x]1.3: Create placeholder `__init__.py` files in all `src/python/` subdirectories (orchestrator, data_pipeline, strategy, rust_bridge, api, risk, monitoring, mt5_integration, analysis, reconciliation, artifacts, config_loader, logging_setup) — these are empty stubs that will be filled in later stories
  - [x]1.4: Create a `.gitignore` with entries for: `logs/`, `artifacts/`, `.env`, `__pycache__/`, `*.pyc`, `target/` (Rust), `node_modules/`, `*.partial` (crash-safe write temp files), `*.egg-info/`, `.venv/`
  - [x]1.5: Create `artifacts/.gitkeep` and `logs/.gitkeep` to ensure empty directories are tracked

- [x] Task 2: Create `.env.example` (AC: #7)
  - [x]2.1: Create `.env.example` with placeholder entries:
    ```
    # MT5 Credentials (NFR16: never in config files, never in git)
    MT5_LOGIN=
    MT5_PASSWORD=
    MT5_SERVER=
    MT5_PATH=

    # Environment selection
    FOREX_PIPELINE_ENV=local
    ```
  - [x]2.2: Ensure `.env` is in `.gitignore`

- [x] Task 3: Create `config/base.toml` with full pipeline defaults (AC: #2, #8)
  - [x]3.1: Create `config/base.toml` with all configuration keys that have defaults. Every config key must exist here (Architecture rule: "every config key must exist in base.toml with a default"). Include:
    ```toml
    [project]
    name = "forex-pipeline"
    version = "0.1.0"

    [data]
    storage_path = "G:\\My Drive\\BackTestData"
    default_pair = "EURUSD"
    default_timeframe = "M1"
    supported_timeframes = ["M1", "M5", "H1", "D1", "W"]

    [data.download]
    source = "dukascopy"
    timeout_seconds = 30
    max_retries = 3
    retry_delay_seconds = 5

    [data.quality]
    gap_threshold_bars = 5
    gap_warning_per_year = 10
    gap_error_per_year = 50
    gap_error_minutes = 30
    spread_multiplier_threshold = 10.0
    stale_consecutive_bars = 5
    score_green_threshold = 0.95
    score_yellow_threshold = 0.80

    [sessions]
    timezone = "UTC"

    [sessions.asian]
    start = "00:00"
    end = "08:00"
    label = "Asian"

    [sessions.london]
    start = "08:00"
    end = "16:00"
    label = "London"

    [sessions.new_york]
    start = "13:00"
    end = "21:00"
    label = "New York"

    [sessions.london_ny_overlap]
    start = "13:00"
    end = "16:00"
    label = "London/NY Overlap"

    [sessions.off_hours]
    start = "21:00"
    end = "00:00"
    label = "Off Hours"

    [logging]
    level = "INFO"
    log_dir = "logs"
    max_file_size_mb = 50
    retention_days = 30

    [pipeline]
    artifacts_dir = "artifacts"
    checkpoint_enabled = true

    [execution]
    enabled = false
    mode = "practice"
    ```
  - [x]3.2: Ensure the session schedule matches the Architecture's session definitions exactly
  - [x]3.3: Ensure all data quality thresholds match the Architecture's Data Quality Gate Specifications

- [x] Task 4: Create `config/schema.toml` for config validation (AC: #2)
  - [x]4.1: Create `config/schema.toml` that defines the expected structure, types, and constraints for every key in `base.toml`. The schema must support:
    - Required vs optional keys
    - Type validation (string, int, float, bool, array, table)
    - Value constraints (min/max for numbers, allowed values for enums)
    - Nested table validation
  - [x]4.2: Example schema entries:
    ```toml
    [schema.data.storage_path]
    type = "string"
    required = true
    description = "Root directory for market data storage"

    [schema.data.quality.gap_threshold_bars]
    type = "integer"
    required = true
    min = 1
    max = 100
    description = "Number of consecutive missing M1 bars to flag as a gap"

    [schema.sessions]
    type = "table"
    required = true
    description = "Trading session schedule definitions"
    ```

- [x] Task 5: Create environment-specific config overrides (AC: #3)
  - [x]5.1: Create `config/environments/local.toml`:
    ```toml
    # Local development environment overrides
    [execution]
    enabled = false
    mode = "practice"

    [logging]
    level = "DEBUG"
    ```
  - [x]5.2: Create `config/environments/vps.toml`:
    ```toml
    # VPS production environment overrides
    [execution]
    enabled = true
    mode = "practice"

    [logging]
    level = "INFO"

    [monitoring]
    heartbeat_interval_ms = 5000
    alert_on_disconnect = true
    ```

- [x] Task 6: Implement config loader with layered TOML loading and validation (AC: #2, #3, #8)
  - [x]6.1: Create `src/python/config_loader/__init__.py` that exports `load_config`, `validate_config`, `compute_config_hash`
  - [x]6.2: Create `src/python/config_loader/loader.py`:
    - Function `load_config(env: str = None) -> dict`:
      1. Load `config/base.toml` using `tomllib` (Python 3.11+ stdlib)
      2. Determine environment from `env` parameter, or `FOREX_PIPELINE_ENV` env var, or default to `"local"`
      3. Load `config/environments/{env}.toml` and deep-merge over base config (environment overrides base)
      4. Return the merged config dict
    - Deep merge logic: nested dicts merge recursively, scalars and lists are overwritten by the override
  - [x]6.3: Create `src/python/config_loader/validator.py`:
    - Function `validate_config(config: dict, schema_path: str = "config/schema.toml") -> list[str]`:
      1. Load the schema from `schema.toml`
      2. Walk the config dict and validate every key against the schema
      3. Return a list of validation errors (empty list = valid)
    - Function `validate_or_die(config: dict)`:
      1. Call `validate_config`
      2. If errors, log each error and raise `SystemExit(1)` with a clear message — "Config validation failed at startup"
      3. This implements D7's "fail loud at startup" requirement
  - [x]6.4: Create `src/python/config_loader/hasher.py`:
    - Function `compute_config_hash(config: dict) -> str`:
      1. Serialize the config dict to a canonical JSON string (sorted keys, no whitespace)
      2. Compute SHA-256 hash of the serialized string
      3. Return the hex digest
    - The hash must be deterministic — same config dict always produces the same hash, regardless of insertion order
    - This implements FR8/FR61's reproducibility requirement

- [x] Task 7: Implement structured JSON logging (AC: #4)
  - [x]7.1: Create `src/python/logging_setup/__init__.py` that exports `setup_logging`, `get_logger`
  - [x]7.2: Create `src/python/logging_setup/setup.py`:
    - Function `setup_logging(config: dict) -> None`:
      1. Read log config from `config["logging"]`
      2. Create `logs/` directory if it doesn't exist
      3. Configure Python's `logging` module with a custom JSON formatter
      4. Log file name format: `logs/python_{date}.jsonl` (one file per day, JSONL format — one JSON object per line)
      5. Set log level from config
    - Custom JSON formatter that produces log lines matching the Architecture's unified schema:
      ```json
      {
        "ts": "2026-03-13T14:22:00.123Z",
        "level": "INFO",
        "runtime": "python",
        "component": "config_loader",
        "stage": null,
        "strategy_id": null,
        "msg": "Configuration loaded successfully",
        "ctx": {}
      }
      ```
    - Function `get_logger(component: str) -> logging.Logger`:
      1. Return a logger pre-configured with the component name
      2. The component name is embedded in every log line's `component` field
    - The `stage` and `strategy_id` fields can be set per-log-call via the `extra` dict or a context manager
  - [x]7.3: Ensure the log format matches D6 exactly: fields are `ts`, `level`, `runtime`, `component`, `stage`, `strategy_id`, `msg`, `ctx`
  - [x]7.4: Ensure `ts` is ISO 8601 UTC with millisecond precision (matching the Architecture's timestamp format specification)
  - [x]7.5: Add a `LogContext` context manager or similar mechanism for setting `stage` and `strategy_id` on a block of code without passing them to every log call

- [x] Task 8: Create the contracts directory skeleton (AC: #5)
  - [x]8.1: Create `contracts/arrow_schemas.toml` with the market_data schema from the Architecture AND a tick_data schema:
    ```toml
    [market_data]
    description = "M1 bar data with session and quarantine columns"
    columns = [
      { name = "timestamp", type = "int64", nullable = false, description = "Epoch microseconds UTC" },
      { name = "open", type = "float64", nullable = false },
      { name = "high", type = "float64", nullable = false },
      { name = "low", type = "float64", nullable = false },
      { name = "close", type = "float64", nullable = false },
      { name = "bid", type = "float64", nullable = false },
      { name = "ask", type = "float64", nullable = false },
      { name = "session", type = "utf8", nullable = false, values = ["asian", "london", "new_york", "london_ny_overlap", "off_hours"] },
      { name = "quarantined", type = "bool", nullable = false, default = false },
    ]

    [tick_data]
    description = "Individual bid/ask ticks for scalping strategies"
    columns = [
      { name = "timestamp", type = "int64", nullable = false, description = "Epoch microseconds UTC" },
      { name = "bid", type = "float64", nullable = false },
      { name = "ask", type = "float64", nullable = false },
      { name = "bid_volume", type = "float64", nullable = true },
      { name = "ask_volume", type = "float64", nullable = true },
      { name = "session", type = "utf8", nullable = false, values = ["asian", "london", "new_york", "london_ny_overlap", "off_hours"] },
      { name = "quarantined", type = "bool", nullable = false, default = false },
    ]

    [backtest_trades]
    description = "Trade records from backtest engine"
    columns = [
      { name = "trade_id", type = "int64", nullable = false },
      { name = "strategy_id", type = "utf8", nullable = false },
      { name = "direction", type = "utf8", nullable = false, values = ["long", "short"] },
      { name = "entry_time", type = "int64", nullable = false },
      { name = "exit_time", type = "int64", nullable = false },
      { name = "entry_price", type = "float64", nullable = false },
      { name = "exit_price", type = "float64", nullable = false },
      { name = "spread_cost_pips", type = "float64", nullable = false },
      { name = "slippage_cost_pips", type = "float64", nullable = false },
      { name = "pnl_pips", type = "float64", nullable = false },
      { name = "session", type = "utf8", nullable = false },
      { name = "lot_size", type = "float64", nullable = false },
    ]

    [optimization_candidates]
    description = "Optimization candidate results"
    columns = [
      { name = "candidate_id", type = "int64", nullable = false },
      { name = "params_json", type = "utf8", nullable = false, description = "JSON-encoded parameter set" },
      { name = "total_trades", type = "int64", nullable = false },
      { name = "profit_factor", type = "float64", nullable = false },
      { name = "sharpe_ratio", type = "float64", nullable = false },
      { name = "max_drawdown_pct", type = "float64", nullable = false },
      { name = "win_rate", type = "float64", nullable = false },
      { name = "net_pnl_pips", type = "float64", nullable = false },
    ]
    ```
  - [x]8.2: Create `contracts/sqlite_ddl.sql` with the table definitions from the Architecture:
    ```sql
    -- Forex Pipeline SQLite Schema
    -- WAL mode enabled at connection time, not in DDL

    CREATE TABLE IF NOT EXISTS backtest_runs (
        run_id          TEXT PRIMARY KEY,
        strategy_id     TEXT NOT NULL,
        config_hash     TEXT NOT NULL,
        data_hash       TEXT NOT NULL,
        spec_version    TEXT NOT NULL,
        started_at      TEXT NOT NULL,
        completed_at    TEXT,
        total_trades    INTEGER,
        status          TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed', 'checkpointed'))
    );

    CREATE TABLE IF NOT EXISTS trades (
        trade_id        INTEGER PRIMARY KEY,
        strategy_id     TEXT NOT NULL,
        backtest_run_id TEXT NOT NULL,
        direction       TEXT NOT NULL CHECK(direction IN ('long', 'short')),
        entry_time      TEXT NOT NULL,
        exit_time       TEXT NOT NULL,
        entry_price     REAL NOT NULL,
        exit_price      REAL NOT NULL,
        spread_cost     REAL NOT NULL,
        slippage_cost   REAL NOT NULL,
        pnl_pips        REAL NOT NULL,
        session         TEXT NOT NULL,
        lot_size        REAL NOT NULL,
        candidate_id    INTEGER,
        FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(run_id)
    );

    CREATE INDEX IF NOT EXISTS idx_trades_strategy_id ON trades(strategy_id);
    CREATE INDEX IF NOT EXISTS idx_trades_session ON trades(session);
    CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
    CREATE INDEX IF NOT EXISTS idx_trades_candidate_id ON trades(candidate_id);
    ```
  - [x]8.3: Create `contracts/error_codes.toml` with the error code registry from the Architecture:
    ```toml
    [resource]
    RESOURCE_MEMORY_PRESSURE = { severity = "warning", recoverable = true, action = "throttle" }
    RESOURCE_THERMAL_THROTTLE = { severity = "warning", recoverable = true, action = "throttle" }
    RESOURCE_DISK_FULL = { severity = "error", recoverable = false, action = "stop" }

    [data]
    DATA_CORRUPT_ARROW = { severity = "error", recoverable = false, action = "stop" }
    DATA_SCHEMA_MISMATCH = { severity = "error", recoverable = false, action = "stop" }
    DATA_QUALITY_FAILED = { severity = "warning", recoverable = true, action = "alert" }

    [strategy]
    STRATEGY_SPEC_INVALID = { severity = "error", recoverable = false, action = "stop" }
    STRATEGY_EVAL_FAILED = { severity = "error", recoverable = false, action = "stop" }
    STRATEGY_ZERO_TRADES = { severity = "warning", recoverable = true, action = "alert" }

    [external]
    EXTERNAL_MT5_DISCONNECT = { severity = "warning", recoverable = true, action = "retry" }
    EXTERNAL_DUKASCOPY_TIMEOUT = { severity = "warning", recoverable = true, action = "retry" }
    EXTERNAL_MT5_ORDER_REJECTED = { severity = "error", recoverable = false, action = "alert" }
    ```
  - [x]8.4: Create `contracts/session_schema.toml` with the session column contract from the Architecture:
    ```toml
    [session_column]
    name = "session"
    type = "utf8"
    nullable = false
    values = ["asian", "london", "new_york", "london_ny_overlap", "off_hours"]
    description = "Session label computed from bar timestamp and config schedule"
    ```

- [x] Task 9: Implement the crash-safe write utility (AC: #6)
  - [x]9.1: Create `src/python/artifacts/__init__.py` that exports `crash_safe_write`, `crash_safe_write_bytes`
  - [x]9.2: Create `src/python/artifacts/storage.py`:
    - Function `crash_safe_write(filepath: str | Path, content: str, encoding: str = "utf-8") -> None`:
      1. Write content to `{filepath}.partial`
      2. Flush the file handle
      3. Call `os.fsync(f.fileno())` to ensure data is on disk
      4. Atomic rename `{filepath}.partial` to `{filepath}` using `os.replace()` (atomic on Windows for same-volume renames)
    - Function `crash_safe_write_bytes(filepath: str | Path, content: bytes) -> None`:
      1. Same pattern but for binary content (Arrow IPC, Parquet files)
    - Function `clean_partial_files(directory: str | Path) -> list[str]`:
      1. Scan directory for `*.partial` files
      2. Delete them (these are from crashed writes)
      3. Return list of deleted files for logging
      4. Called on startup as part of crash recovery
  - [x]9.3: Ensure `os.replace()` is used (not `os.rename()`) because `os.replace()` is atomic and overwrites the destination on Windows

- [x] Task 10: Create `pyproject.toml` with Python project config (AC: #1)
  - [x]10.1: Create `src/python/pyproject.toml`:
    ```toml
    [project]
    name = "forex-pipeline"
    version = "0.1.0"
    requires-python = ">=3.11"
    dependencies = []

    [project.optional-dependencies]
    dev = [
      "pytest>=7.0",
      "pytest-cov>=4.0",
    ]

    [tool.pytest.ini_options]
    testpaths = ["tests"]
    python_files = ["test_*.py"]
    python_classes = ["Test*"]
    python_functions = ["test_*"]
    ```
  - [x]10.2: Note: No external dependencies yet — `tomllib` is stdlib in Python 3.11+, `logging` is stdlib, `json` is stdlib, `hashlib` is stdlib, `os` is stdlib. External dependencies will be added by later stories as needed.

- [x] Task 11: Create `src/python/main.py` entry point (AC: #2, #4)
  - [x]11.1: Create `src/python/main.py` that demonstrates the foundation works:
    ```python
    """Forex Pipeline — main entry point.

    Loads config, validates schema, sets up structured logging,
    and verifies the foundation is working.
    """
    import sys
    from config_loader import load_config, validate_or_die, compute_config_hash
    from logging_setup import setup_logging, get_logger
    from artifacts.storage import clean_partial_files

    def main():
        # 1. Load and validate config
        config = load_config()
        validate_or_die(config)

        # 2. Setup structured logging
        setup_logging(config)
        logger = get_logger("main")

        # 3. Compute and log config hash
        config_hash = compute_config_hash(config)
        logger.info("Forex Pipeline starting", extra={
            "ctx": {"config_hash": config_hash, "env": config.get("_env", "local")}
        })

        # 4. Clean any partial files from previous crashes
        cleaned = clean_partial_files(config["pipeline"]["artifacts_dir"])
        if cleaned:
            logger.warning("Cleaned partial files from previous crash", extra={
                "ctx": {"files": cleaned}
            })

        logger.info("Foundation verified — config, logging, and crash-safe writes operational")

    if __name__ == "__main__":
        main()
    ```

- [x] Task 12: Write tests (AC: all)
  - [x]12.1: Create `src/python/tests/conftest.py` with shared test fixtures:
    - `tmp_config_dir` fixture that creates a temporary directory with base.toml and environment files
    - `sample_config` fixture that returns a valid config dict
  - [x]12.2: Create `src/python/tests/test_config/test_loader.py`:
    - `test_load_base_config()` — verifies base.toml loads correctly
    - `test_load_with_env_override()` — verifies environment config overrides base values
    - `test_deep_merge()` — verifies nested dict merging works correctly (override scalar, merge nested table)
    - `test_missing_base_config_fails()` — verifies helpful error when base.toml is missing
    - `test_missing_env_config_uses_base()` — verifies graceful fallback when env config doesn't exist
  - [x]12.3: Create `src/python/tests/test_config/test_validator.py`:
    - `test_valid_config_passes()` — verifies a correct config passes validation
    - `test_missing_required_key_fails()` — verifies validation catches missing required keys
    - `test_wrong_type_fails()` — verifies validation catches type mismatches (e.g., string where int expected)
    - `test_out_of_range_fails()` — verifies validation catches values outside min/max constraints
    - `test_validate_or_die_exits()` — verifies `validate_or_die` calls `sys.exit(1)` on invalid config
  - [x]12.4: Create `src/python/tests/test_config/test_hasher.py`:
    - `test_same_config_same_hash()` — verifies deterministic hashing
    - `test_different_config_different_hash()` — verifies different configs produce different hashes
    - `test_key_order_independent()` — verifies hash is the same regardless of dict key insertion order
  - [x]12.5: Create `src/python/tests/test_logging/test_setup.py`:
    - `test_log_output_is_json()` — verifies log lines are valid JSON
    - `test_log_schema_fields()` — verifies log lines contain all required fields (ts, level, runtime, component, stage, strategy_id, msg, ctx)
    - `test_log_file_created()` — verifies log file is created in logs/ directory
    - `test_log_timestamp_is_utc()` — verifies timestamp is ISO 8601 UTC
    - `test_component_name_in_logs()` — verifies `get_logger("foo")` produces logs with `component: "foo"`
  - [x]12.6: Create `src/python/tests/test_artifacts/test_storage.py`:
    - `test_crash_safe_write_creates_file()` — verifies the file is created at the final path
    - `test_crash_safe_write_no_partial_left()` — verifies no `.partial` file remains after successful write
    - `test_crash_safe_write_content_correct()` — verifies file content matches what was written
    - `test_crash_safe_write_bytes()` — verifies binary content write
    - `test_clean_partial_files()` — verifies cleanup of `.partial` files
    - `test_crash_safe_write_overwrites_existing()` — verifies atomic overwrite of existing file

## Dev Notes

### Architecture Constraints

These Architecture decisions MUST be followed exactly:

- **D6 (Logging):** "Each runtime writes structured JSON log lines to logs/, one file per runtime per day." The log schema is defined as: `{"ts", "level", "runtime", "component", "stage", "strategy_id", "msg", "ctx"}`. Log files are named per-runtime per-day. No write contention between runtimes. [Source: architecture.md, Decision 6]

- **D7 (Configuration):** "Layered TOML configs validated at startup. Environment variables for secrets only." Config structure is `base.toml` + `environments/{env}.toml` + `strategies/{name}.toml`. Schema validation at startup — fail loud before any stage runs. Config hash embedded in every artifact manifest. "TOML: no implicit type coercion, deterministic parsing, native in Rust (serde) and Python (tomllib)." [Source: architecture.md, Decision 7]

- **D8 (Error Handling):** "Structured error type" with code, category, severity, recoverable, action, component, runtime, context, msg. Error codes are defined in `contracts/error_codes.toml`. [Source: architecture.md, Decision 8]

- **Crash-Safe Write Pattern:** "All artifact writes across all runtimes follow: 1. Write to {filename}.partial, 2. Flush / fsync, 3. Atomic rename to {filename}. Never overwrite a complete artifact with a partial one. If .partial exists on startup, it's from a crash — delete it and re-run." [Source: architecture.md, Process Patterns section]

- **Configuration Access Pattern:** "Config is loaded once at process startup, validated against schema, and frozen. No runtime config modification — restart to pick up changes. Config hash computed at load time, embedded in all artifact manifests." [Source: architecture.md, Process Patterns section]

- **Naming Conventions:** All file/directory names use `snake_case`. Python functions/variables use `snake_case`, classes use `PascalCase`, constants use `UPPER_SNAKE_CASE`. JSON fields use `snake_case`. TOML keys use `snake_case`. [Source: architecture.md, Naming Patterns]

- **Enforcement Guidelines:** "Validate config at startup — fail immediately with a clear message, not silently mid-run." "Every config key must exist in base.toml with a default." [Source: architecture.md, Enforcement Guidelines]

### Technical Requirements

- **Python version:** 3.11+ required (for `tomllib` stdlib support)
- **No external dependencies** for this story — use only stdlib modules: `tomllib`, `logging`, `json`, `hashlib`, `os`, `pathlib`, `datetime`, `sys`
- **Testing:** `pytest` (the only external dependency, in dev extras)
- **Config loading:** Use `tomllib` (read-only TOML parser, stdlib since 3.11)
- **Hash computation:** Use `hashlib.sha256`
- **Atomic rename:** Use `os.replace()` (not `os.rename()`)
- **Timestamp format:** ISO 8601 UTC with millisecond precision, always ending with `Z`
- **Log format:** JSONL (JSON Lines — one JSON object per line, not a JSON array)

### What to Reuse from ClaudeBackTester

From the baseline-to-architecture mapping:

| Component | Mapping Direction | Notes |
|---|---|---|
| `config_loader/` | **Build new** | "Config exists but not schema-validated. New deterministic config with hash-based reproducibility." |
| `logging_setup/` | **Adapt** | "Logging exists. Switch to structured JSON, per-runtime files." |

[Source: baseline-to-architecture-mapping.md, Orchestration Tier table]

Both components are effectively **build new** for this story:
- The baseline config system is not schema-validated and doesn't use layered TOML — building fresh is cleaner than adapting
- The baseline logging is not structured JSON — building the JSON formatter from scratch is simpler than adapting existing formatters
- Story 1.1's review may identify patterns from the baseline worth adopting, but this story should not block on 1.1 — the Architecture provides complete specifications

### Anti-Patterns to Avoid

1. **DO NOT use `pydantic` or `dataclasses` for config** — keep it as a plain dict loaded from TOML. This matches the Architecture's pattern ("Config is loaded once at process startup, validated against schema, and frozen") and avoids adding external dependencies for this foundational story. Later stories may introduce type-safe wrappers if needed.

2. **DO NOT use `os.rename()` for crash-safe writes** — use `os.replace()`. On Windows, `os.rename()` fails if the destination exists; `os.replace()` atomically replaces it.

3. **DO NOT add optional fields to the log schema** — every log line MUST have all 8 fields (`ts`, `level`, `runtime`, `component`, `stage`, `strategy_id`, `msg`, `ctx`). Use `null` for fields that don't apply to a given log line.

4. **DO NOT create the Rust workspace files beyond placeholder directories** — later stories handle Rust initialization. This story creates the directory structure only.

5. **DO NOT add dashboard package.json or dependencies** — later stories handle dashboard initialization.

6. **DO NOT use `yaml` or `json` for config files** — the Architecture mandates TOML specifically (D7).

7. **DO NOT hardcode any config values in Python code** — every configurable value must come from the TOML config. If a value is used in code, it must have a key in `base.toml`.

8. **DO NOT use `print()` for any output** — all output goes through the structured logging system after it's initialized. Before logging is initialized (during config load), use `sys.stderr.write()` for critical errors only.

9. **DO NOT create a `config/strategies/` file yet** — strategy configs depend on the strategy definition format (Phase 0 research). Create the directory but leave it empty.

10. **DO NOT use `datetime.now()` in log timestamps** — use `datetime.now(datetime.timezone.utc)` to ensure UTC.

### Project Structure Notes

All files are relative to the project root: `C:\Users\ROG\Projects\Forex Pipeline\`

Key file locations:
- Config system: `src/python/config_loader/loader.py`, `validator.py`, `hasher.py`
- Logging system: `src/python/logging_setup/setup.py`
- Crash-safe writes: `src/python/artifacts/storage.py`
- Entry point: `src/python/main.py`
- Config files: `config/base.toml`, `config/schema.toml`, `config/environments/*.toml`
- Contract files: `contracts/arrow_schemas.toml`, `contracts/sqlite_ddl.sql`, `contracts/error_codes.toml`, `contracts/session_schema.toml`
- Tests: `src/python/tests/test_config/`, `src/python/tests/test_logging/`, `src/python/tests/test_artifacts/`

### References

- [Source: planning-artifacts/epics.md#Story 1.3 — lines 482-500]
- [Source: planning-artifacts/architecture.md#Decision 6 — lines 473-497]
- [Source: planning-artifacts/architecture.md#Decision 7 — lines 499-526]
- [Source: planning-artifacts/architecture.md#Decision 8 — lines 528-565]
- [Source: planning-artifacts/architecture.md#Crash-Safe Write Pattern — lines 1258-1265]
- [Source: planning-artifacts/architecture.md#Configuration Access Pattern — lines 1267-1272]
- [Source: planning-artifacts/architecture.md#Naming Patterns — lines 1073-1098]
- [Source: planning-artifacts/architecture.md#Structure Patterns — lines 1101-1149]
- [Source: planning-artifacts/architecture.md#Complete Project Directory Structure — lines 1479-1755]
- [Source: planning-artifacts/architecture.md#Contracts Directory Content — lines 1367-1477]
- [Source: planning-artifacts/architecture.md#Session-Awareness Architecture — lines 146-222]
- [Source: planning-artifacts/architecture.md#Data Quality Gate Specifications — lines 224-260]
- [Source: planning-artifacts/architecture.md#Enforcement Guidelines — lines 1274-1293]
- [Source: planning-artifacts/architecture.md#Testing Strategy — lines 1294-1365]
- [Source: planning-artifacts/baseline-to-architecture-mapping.md — config_loader and logging_setup rows]
- [Source: planning-artifacts/prd.md#FR8 — line 468, FR58-FR61]
- [Source: planning-artifacts/prd.md#NFR15 — crash-safe writes]
- [Source: planning-artifacts/prd.md#NFR16 — no plaintext credentials]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Completion Notes List
- All 12 tasks completed with 28/28 tests passing
- Project directory structure created per Architecture D7/D6 specifications
- Config loader: layered TOML loading (base.toml + env overlay), deep-merge, schema validation (fail loud at startup), deterministic SHA-256 hashing
- Structured JSON logging: JSONL format with all 8 required fields (ts, level, runtime, component, stage, strategy_id, msg, ctx), UTC timestamps with ms precision, LogContext context manager for stage/strategy_id
- Crash-safe write utility: write -> flush -> fsync -> os.replace() pattern for both text and binary
- Contracts directory: arrow_schemas.toml (market_data, tick_data, backtest_trades, optimization_candidates), sqlite_ddl.sql, error_codes.toml, session_schema.toml
- Config files: base.toml with full pipeline defaults, schema.toml with type/range/allowed validation, local.toml and vps.toml environment overrides
- main.py entry point demonstrates full foundation: load config -> validate -> setup logging -> compute hash -> clean partials
- Virtual environment created at .venv/ with Python 3.12.12, pytest 9.0.2
- No external dependencies beyond pytest (dev only) — all stdlib: tomllib, logging, json, hashlib, os, pathlib

### Change Log
- 2026-03-14: Story 1.3 implemented — all 12 tasks, 28 tests passing

### File List
- .env.example (new)
- .gitignore (new)
- config/base.toml (new)
- config/schema.toml (new)
- config/environments/local.toml (new)
- config/environments/vps.toml (new)
- contracts/arrow_schemas.toml (new)
- contracts/sqlite_ddl.sql (new)
- contracts/error_codes.toml (new)
- contracts/session_schema.toml (new)
- src/python/pyproject.toml (new)
- src/python/main.py (new)
- src/python/config_loader/__init__.py (new)
- src/python/config_loader/loader.py (new)
- src/python/config_loader/validator.py (new)
- src/python/config_loader/hasher.py (new)
- src/python/logging_setup/__init__.py (new)
- src/python/logging_setup/setup.py (new)
- src/python/artifacts/__init__.py (new)
- src/python/artifacts/storage.py (new)
- src/python/tests/conftest.py (new)
- src/python/tests/test_config/test_loader.py (new)
- src/python/tests/test_config/test_validator.py (new)
- src/python/tests/test_config/test_hasher.py (new)
- src/python/tests/test_logging/test_setup.py (new)
- src/python/tests/test_artifacts/test_storage.py (new)
- artifacts/.gitkeep (new)
- logs/.gitkeep (new)
- Multiple __init__.py placeholder files in all src/python/ subdirectories (new)
