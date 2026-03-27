# Story 3.4: Python-Rust Bridge — Batch Evaluation Dispatch

Status: review

## Research Update Note (2026-03-18)

This story has been updated to reflect architecture research findings from Stories 3-1/3-2, Research Briefs 3A-3C, and optimization methodology research.

**Key changes:**
- **D1 (Fold-Aware Batch Evaluation):** Rust evaluator must accept fold boundary definitions and return per-fold scores for CV-inside-objective optimization. `BacktestJob` extended with optional fold parameters. CLI contract extended with fold/window arguments.
- **D1 (Windowed Evaluation):** Support loading data once and evaluating multiple parameter batches within a single process lifetime to avoid reloading 400MB data per batch.
- **D1 (Library-with-Subprocess-Wrapper):** Rust backtester built as library crate with thin binary wrapper — enables zero-cost PyO3 migration path in future phases.
- **D14 (Pre-Computed Signals):** Phase 1 indicators stay in Python. Pre-computed signals are passed via Arrow IPC to Rust. Rust does NOT compute indicators in Epic 3.

**References:** architecture.md Research Updates to D1, D14; Research Brief 3A; optimization-methodology-research-summary.md

## Story

As the **operator**,
I want Python to dispatch backtest jobs to the Rust batch binary with Arrow IPC data exchange,
so that the pipeline orchestrator can invoke high-performance Rust backtesting without serialization overhead.

## Acceptance Criteria

1. **Given** a valid strategy spec, market data, and cost model on disk,
   **When** Python invokes the Rust backtester binary via subprocess,
   **Then** it passes structured job parameters: strategy spec path (TOML), market data path (Arrow IPC), cost model path (JSON), output directory, and config hash.
   *(FR14, D1)*

2. **Given** an Arrow IPC market data file,
   **When** the Rust binary starts,
   **Then** it opens the market data file via memory-mapped I/O, verified by a startup log entry recording the mmap file path and size.
   *(D1, D2)*

3. **Given** a completed backtest evaluation,
   **When** the Rust binary finishes,
   **Then** it writes results as Arrow IPC files to the specified output directory — trade log, equity curve, per-trade metrics — using crash-safe write semantics (write → fsync → atomic rename from `.partial`).
   *(D2, NFR15)*

4. **Given** an error occurs in the Rust binary (validation, OOM, data issue),
   **When** the error is raised,
   **Then** Rust exits with a structured JSON error on stderr matching the D8 error schema (`{error_type, category, message, context}`), and Python captures and routes it to the orchestrator's error handling.
   *(D8, AC#9 of Story 3-3)*

5. **Given** a running Rust backtest process,
   **When** Python sends a cancellation signal (SIGTERM on Unix, CTRL_BREAK on Windows),
   **Then** Rust checkpoints current progress and exits gracefully within 5 seconds.
   *(NFR5)*

6. **Given** a long-running backtest,
   **When** the Rust binary processes bars,
   **Then** it writes periodic progress updates (bars processed, total bars, estimated time remaining) to a progress file that Python polls for pipeline status display.
   *(FR40)*

7. **Given** job parameters include a memory budget,
   **When** the Rust binary starts,
   **Then** it logs allocated MB and chosen batch size at startup, pre-allocating within the budget per NFR4 — if the workload exceeds budget, it reduces batch size before starting (logged), never mid-run, never crashes.
   *(NFR4)*

8. **Given** a Rust binary crash (segfault, panic),
   **When** the crash occurs,
   **Then** the Python orchestrator detects the non-zero exit code, captures stderr, and continues running without itself crashing — process isolation is maintained.
   *(D1, NFR10)*

9. **Given** identical job parameters (same strategy spec, same market data, same cost model, same config hash),
   **When** the bridge dispatches the same job twice,
   **Then** the deterministic output files (`trade-log.arrow`, `equity-curve.arrow`, `metrics.arrow`) are byte-identical per the reproducibility contract from Story 3-2. Ephemeral runtime files (`progress.json`, checkpoint files) are excluded from the reproducibility contract.
   *(FR18, FR61)*

## Tasks / Subtasks

**IMPORTANT — Infrastructure Prerequisites:** The `common` crate is currently a stub (1 line). Files `error_types.rs` and `arrow_schemas.rs` do not exist yet. The `rust_bridge/__init__.py` is empty. The `test_rust_bridge/` test directory does not exist. Tasks 5-6 must create common crate infrastructure before other Rust tasks can proceed. Task execution order: **Task 6 → Task 5 → Tasks 7-10 → Tasks 1-4 → Task 11 → Task 12**.

- [x] **Task 1: Python `BatchRunner` class** (AC: #1, #8, #9)
  - [x] Create `src/python/rust_bridge/batch_runner.py`
  - [x] Implement `BatchRunner` class:
    ```python
    @dataclass
    class BacktestJob:
        strategy_spec_path: Path      # TOML file
        market_data_path: Path        # Arrow IPC file (mmap-ready)
        cost_model_path: Path         # JSON file
        output_directory: Path        # Results written here
        config_hash: str              # For artifact tracing
        memory_budget_mb: int         # Pre-allocation constraint
        checkpoint_path: Path | None  # Resume from checkpoint if set
        # Research Update: Fold-aware batch evaluation support
        fold_boundaries: list[tuple[int, int]] | None  # [(start_bar, end_bar), ...] per fold
        embargo_bars: int | None      # Embargo size at fold boundaries
        window_start: int | None      # Windowed evaluation start bar index
        window_end: int | None        # Windowed evaluation end bar index
        parameter_batch: list[dict] | None  # Multiple parameter sets for batch evaluation

    class BatchRunner:
        def __init__(self, binary_path: Path, timeout: int | None = None):
            ...

        async def dispatch(self, job: BacktestJob) -> BatchResult:
            """Spawn Rust binary as subprocess, return result."""
            ...

        async def cancel(self, job_id: str) -> None:
            """Signal Rust process to checkpoint and exit."""
            ...

        def get_progress(self, job: BacktestJob) -> ProgressReport | None:
            """Read progress file for status display."""
            ...
    ```
  - [x] Use `asyncio.create_subprocess_exec` for non-blocking dispatch
  - [x] Pass job parameters as CLI arguments to binary (not stdin)
  - [x] CLI contract: `forex_backtester --spec <path> --data <path> --cost-model <path> --output <path> --config-hash <hash> --memory-budget <mb> [--checkpoint <path>] [--fold-boundaries <json>] [--embargo-bars <n>] [--window-start <bar>] [--window-end <bar>] [--param-batch <json-path>]`
  - [x] Note: `--fold-boundaries` accepts JSON array of [start, end] pairs. `--param-batch` accepts path to JSON file with parameter set array. All fold/window/batch args are optional — single-run evaluation remains the default.
  - [x] Capture stdout for structured logs, stderr for error JSON
  - [x] Handle Windows-specific subprocess spawning: `process.terminate()` sends CTRL_BREAK on Windows. Wrap in try/except — if terminate fails, fall back to `process.kill()`. Set a 5-second timeout after terminate before escalating to kill.
  - [x] Pre-check system memory before spawning Rust binary; fail immediately with clear error if insufficient for requested memory_budget_mb
  - [x] Normalize all file paths to forward slashes before passing as CLI arguments (Windows compatibility)
  - [x] Return `BatchResult` with exit code, output paths, elapsed time, error if any

- [x] **Task 2: Python `ErrorParser` module** (AC: #4, #8)
  - [x] Create `src/python/rust_bridge/error_parser.py`
  - [x] Implement error parsing from Rust stderr JSON:
    ```python
    @dataclass
    class RustError:
        error_type: str       # e.g., "validation_error", "resource_exhaustion"
        category: str         # "resource_pressure" | "data_logic" | "external_failure"
        message: str          # Human-readable description
        context: dict         # Stage, strategy_id, additional details

    def parse_rust_error(stderr: str) -> RustError | None:
        """Parse structured JSON error from Rust stderr."""
        ...

    def map_to_pipeline_error(rust_error: RustError) -> PipelineError:
        """Map Rust error to orchestrator's PipelineError type (from Story 3-3)."""
        ...
    ```
  - [x] Handle malformed stderr gracefully (Rust panic output, non-JSON)
  - [x] Map error categories to orchestrator recovery actions per Story 3-3 Task 6:
    - `resource_pressure` → throttle (reduce concurrency/batch size)
    - `data_logic` → stop + checkpoint (no retry)
    - `external_failure` → retry with backoff

- [x] **Task 3: Python `OutputVerifier` module** (AC: #3)
  - [x] Create `src/python/rust_bridge/output_verifier.py`
  - [x] Implement output file verification and lightweight reference return:
    ```python
    @dataclass
    class BacktestOutputRef:
        output_dir: Path
        trade_log_path: Path       # Path to trade-log.arrow
        equity_curve_path: Path    # Path to equity-curve.arrow
        metrics_path: Path         # Path to metrics.arrow
        config_hash: str           # From job parameters, for traceability

    def verify_output(output_dir: Path, config_hash: str) -> BacktestOutputRef:
        """Verify expected Arrow IPC files exist and schemas match contracts.
        If fold-aware evaluation was used, also verify per-fold score files."""
        ...

    def validate_schemas(output_dir: Path) -> bool:
        """Validate Arrow schemas against contracts/arrow_schemas.toml."""
        ...

    def verify_fold_scores(output_dir: Path, expected_folds: int) -> bool:
        """Research Update: Verify per-fold score output exists and has correct fold count."""
        ...
    ```
  - [x] Validate expected files exist: `trade-log.arrow`, `equity-curve.arrow`, `metrics.arrow`
  - [x] Verify Arrow schemas match contracts defined in `contracts/arrow_schemas.toml` (the cross-runtime SSOT)
  - [x] Return file path references, NOT materialized tables — full ingestion and manifest creation is Story 3.6's responsibility

- [x] **Task 4: Python `StageExecutor` implementation for BACKTEST_RUNNING** (AC: #1, #4, #8)
  - [x] Create `src/python/rust_bridge/backtest_executor.py`
  - [x] Implement `StageExecutor` protocol (defined in Story 3-3 Task 4):
    ```python
    class BacktestExecutor:
        """StageExecutor for the backtest-running pipeline stage."""

        def __init__(self, runner: BatchRunner, verifier: OutputVerifier):
            ...

        def execute(self, strategy_id: str, context: dict) -> StageResult:
            """
            Build BacktestJob from context, dispatch via BatchRunner,
            verify output files, return StageResult with output references.
            """
            ...

        def validate_artifact(self, artifact_path: Path, manifest_ref: Path) -> bool:
            """Verify artifact file exists and Arrow schema matches contracts/arrow_schemas.toml.
            Note: Full manifest-based hash validation is Story 3.6's responsibility.
            Return True if valid. Raise PipelineError on validation failure."""
            ...
    ```
  - [x] Extract job parameters from pipeline context dict (populated by prior stages): expects keys `strategy_spec_path`, `market_data_path`, `cost_model_path`, `config_hash`, `memory_budget_mb`
  - [x] Wire to `StageRunner` from Story 3-3 for orchestration — register as executor for `PipelineStage.BACKTEST_RUNNING`
  - [x] Return `StageResult` with artifact_path (output directory), manifest_ref (None — manifest created by Story 3.6), outcome, metrics, error
  - [x] Note: `BatchRunner.dispatch()` is async; `StageExecutor.execute()` is sync per Story 3-3 protocol. Bridge the async/sync boundary with `asyncio.run()` or run within an existing event loop
  - [x] On error: wrap `RustError` → `PipelineError` via `error_parser.map_to_pipeline_error()`, set outcome="failed"

- [x] **Task 5: Rust binary CLI argument parser** (AC: #1, #2, #7)
  - [x] Create `src/rust/crates/backtester/src/bin/forex_backtester.rs`
  - [x] Use `clap` for CLI argument parsing:
    ```rust
    #[derive(Parser)]
    struct Args {
        #[arg(long)]
        spec: PathBuf,           // Strategy spec TOML
        #[arg(long)]
        data: PathBuf,           // Arrow IPC market data
        #[arg(long)]
        cost_model: PathBuf,     // Cost model JSON
        #[arg(long)]
        output: PathBuf,         // Output directory
        #[arg(long)]
        config_hash: String,     // Artifact tracing
        #[arg(long)]
        memory_budget: u64,      // MB pre-allocation
        #[arg(long)]
        checkpoint: Option<PathBuf>,  // Resume from checkpoint
        // Research Update: Fold-aware batch evaluation
        #[arg(long)]
        fold_boundaries: Option<String>,  // JSON: [[start, end], ...]
        #[arg(long)]
        embargo_bars: Option<u64>,        // Embargo size at fold boundaries
        #[arg(long)]
        window_start: Option<u64>,        // Windowed eval start bar
        #[arg(long)]
        window_end: Option<u64>,          // Windowed eval end bar
        #[arg(long)]
        param_batch: Option<PathBuf>,     // JSON file with parameter batch
    }
    ```
  - [x] Validate all input paths exist before starting evaluation
  - [x] Load strategy spec via `strategy_engine::parser::parse_spec_from_file`
  - [x] Load cost model via `cost_model::loader::load_from_file`
  - [x] Open Arrow IPC market data via mmap (`arrow::io::ipc::read::FileReader` with mmap)
  - [x] Pre-allocate memory budget at startup per NFR4

- [x] **Task 6: Rust common crate infrastructure + structured error output** (AC: #4)
  - [x] Create `crates/common/src/error_types.rs` (file does not exist yet — common crate is a stub):
    ```rust
    use serde::Serialize;
    use thiserror::Error;

    /// D8 error schema — structured JSON errors on stderr for cross-process error propagation.
    /// Categories MUST match architecture D8 exactly. Python error_parser.py reads these.
    #[derive(Serialize)]
    pub struct StructuredError {
        pub error_type: String,
        pub category: ErrorCategory,
        pub message: String,
        pub context: serde_json::Value,
    }

    #[derive(Serialize)]
    #[serde(rename_all = "snake_case")]
    pub enum ErrorCategory {
        ResourcePressure,  // → Python orchestrator: throttle (reduce concurrency)
        DataLogic,         // → Python orchestrator: stop + checkpoint (no retry)
        ExternalFailure,   // → Python orchestrator: retry with backoff
    }

    impl StructuredError {
        pub fn write_to_stderr(&self) {
            eprintln!("{}", serde_json::to_string(self).unwrap());
        }
    }

    /// Unified error type for backtester binary, wrapping crate-specific errors
    #[derive(Error, Debug)]
    pub enum BacktesterError {
        #[error("Strategy engine error: {0}")]
        StrategyEngine(#[from] strategy_engine::error::StrategyEngineError),
        #[error("Cost model error: {0}")]
        CostModel(#[from] cost_model::error::CostModelError),
        #[error("Arrow IPC error: {0}")]
        ArrowWrite(String),
        #[error("Memory budget exceeded: requested {requested_mb}MB, available {available_mb}MB")]
        OomError { requested_mb: u64, available_mb: u64 },
        #[error("Cancellation signal received")]
        SignalReceived,
        #[error("IO error: {0}")]
        Io(#[from] std::io::Error),
    }
    ```
  - [x] Update `crates/common/src/lib.rs` to declare `pub mod error_types;`
  - [x] Add `serde`, `serde_json`, `thiserror` to common crate's `Cargo.toml`
  - [x] Install panic hook in binary main that converts panic info to `StructuredError` JSON on stderr before aborting
  - [x] Wire all error paths in forex_backtester binary: convert `BacktesterError` → `StructuredError` → stderr JSON, then `std::process::exit(1)`

- [x] **Task 7: Rust progress reporting** (AC: #6)
  - [x] Write progress every N bars (default N=10000) OR every T seconds (default T=1), whichever comes first — prevents I/O thrashing on high-frequency data
  - [x] Implement progress file writer in `crates/backtester/src/progress.rs`:
    ```rust
    #[derive(Serialize)]
    pub struct ProgressReport {
        pub bars_processed: u64,
        pub total_bars: u64,
        pub estimated_seconds_remaining: f64,
        pub memory_used_mb: u64,
        pub updated_at: String,  // ISO 8601
    }

    pub fn write_progress(output_dir: &Path, report: &ProgressReport) -> io::Result<()> {
        // Crash-safe: write to .partial, fsync, rename
    }
    ```
  - [x] Progress file location: `{output_dir}/progress.json`
  - [x] Use crash-safe write pattern (`.partial` → rename)

- [x] **Task 8: Rust Arrow schema validation + crash-safe output** (AC: #3, #9)
  - [x] Create `crates/common/src/arrow_schemas.rs` (file does not exist yet) — Rust-side schema definitions generated from / validated against `contracts/arrow_schemas.toml` (the cross-runtime SSOT). Update `crates/common/src/lib.rs` to declare `pub mod arrow_schemas;`
  - [x] Implement output writer in `crates/backtester/src/output.rs`:
    ```rust
    pub fn write_results(
        output_dir: &Path,
        trades: &RecordBatch,
        equity_curve: &RecordBatch,
        metrics: &RecordBatch,
        config_hash: &str,
    ) -> Result<(), BacktesterError> {
        // For each result:
        // 1. Write to {name}.arrow.partial
        // 2. fsync
        // 3. Rename to {name}.arrow
        // Write config_hash to {output_dir}/run_metadata.json for traceability
    }
    ```
  - [x] Ensure deterministic output for AC#9: sort trade records by `(timestamp, trade_id)` before writing, use deterministic datetime formatting (ISO 8601 UTC), set any PRNG seed from config_hash at startup
  - [x] Deterministic output files: `trade-log.arrow`, `equity-curve.arrow`, `metrics.arrow`. No manifest.json — manifest creation is Python's artifact layer responsibility (Story 3.6)
  - [x] Arrow schemas in Rust MUST match `contracts/arrow_schemas.toml` — add a build-time or startup validation check
  - [x] Ephemeral `run_metadata.json`: config_hash and binary version only (for traceability, not for reproducibility contract)

- [x] **Task 9: Rust graceful cancellation** (AC: #5)
  - [x] Implement signal handler in binary main:
    ```rust
    // Register handler for SIGTERM (Unix) / CTRL_BREAK (Windows)
    // On signal: set AtomicBool flag, checked in main evaluation loop
    // When flag detected: write checkpoint, write partial results, exit 0
    ```
  - [x] Checkpoint file: `{output_dir}/checkpoint.json` conforming to Story 3-2's within-stage checkpoint contract (`contracts/pipeline_checkpoint.toml`). Must include at minimum: `stage`, `progress_pct`, `last_completed_batch`, `total_batches`, `partial_artifact_path`, `checkpoint_at` (ISO 8601)
  - [x] Exit within 5 seconds of signal receipt
  - [x] Windows-specific: handle `CTRL_BREAK_EVENT` via `ctrlc` crate (cross-platform). If signal registration fails at startup, log warning and continue with graceful degradation (no cancellation support)

- [x] **Task 10: Rust memory budget enforcement** (AC: #7)
  - [x] Implement in `crates/backtester/src/memory.rs`:
    ```rust
    pub struct MemoryBudget {
        total_mb: u64,
        allocated: AtomicU64,
    }

    impl MemoryBudget {
        pub fn new(budget_mb: u64) -> Self { ... }
        pub fn allocate(&self, bytes: u64) -> Result<(), ResourceError> { ... }
        pub fn available_mb(&self) -> u64 { ... }
    }
    ```
  - [x] At startup: check system memory, validate budget fits within available
  - [x] Pre-allocate trade buffers within budget (per D3: P-core count × buffer size)
  - [x] If workload exceeds budget → reduce batch parallelism, log decision, never crash
  - [x] Windows system memory query: use `sysinfo` crate (`System::new_all().total_memory()`)

- [x] **Task 11: Integration test — full bridge round-trip** (AC: #1–#9)
  - [x] Create `src/python/tests/test_rust_bridge/test_batch_runner.py`
  - [x] `test_dispatch_backtest_job_success` — happy path: dispatch job, verify Arrow IPC output files exist and schemas match `contracts/arrow_schemas.toml`
  - [x] `test_dispatch_with_invalid_spec_returns_structured_error` — bad strategy spec, verify D8 JSON error on stderr
  - [x] `test_dispatch_with_missing_data_returns_structured_error` — missing Arrow file
  - [x] `test_cancel_running_job_produces_checkpoint` — start long job, cancel, verify checkpoint file
  - [x] `test_progress_reporting_updates_file` — verify progress.json written during execution
  - [x] `test_process_crash_isolation` — trigger intentional `panic!()` in test binary variant (not segfault), verify Python detects non-zero exit code, captures structured error on stderr, and continues running
  - [x] `test_deterministic_output` — run same job twice, compare deterministic output files (`trade-log.arrow`, `equity-curve.arrow`, `metrics.arrow`) byte-for-byte; ignore ephemeral files
  - [x] `test_memory_budget_reduces_parallelism` — set low budget, verify reduced batch size in logs
  - [x] `test_crash_safe_write_no_partial_on_success` — verify no `.partial` files remain after success
  - [x] `test_dispatch_with_fold_boundaries` — dispatch job with fold boundaries, verify per-fold score output
  - [x] `test_dispatch_with_window_bounds` — dispatch job with window start/end, verify only windowed data evaluated
  - [x] `test_dispatch_with_param_batch` — dispatch job with multiple parameter sets, verify batch results
  - [x] Create `src/rust/crates/backtester/tests/test_bridge_cli.rs` for Rust-side CLI integration tests

- [x] **Task 12: Update `__init__.py` and wire modules** (AC: #1)
  - [x] Update `src/python/rust_bridge/__init__.py` to export: `BatchRunner`, `BacktestJob`, `BatchResult`, `ErrorParser`, `OutputVerifier`, `BacktestOutputRef`, `BacktestExecutor`
  - [x] Update `src/rust/crates/backtester/Cargo.toml` with all required dependencies:
    ```toml
    [dependencies]
    clap = { version = "4", features = ["derive"] }
    arrow = "53"
    sysinfo = "0.32"
    ctrlc = { version = "3", features = ["termination"] }
    serde = { version = "1", features = ["derive"] }
    serde_json = "1"
    sha2 = "0.10"
    strategy_engine = { path = "../strategy_engine" }
    cost_model = { path = "../cost_model" }
    common = { path = "../common" }
    ```
  - [x] Verify `pyarrow` is in Python dependencies (requirements.txt / pyproject.toml)

## Dev Notes

### Architecture Constraints

- **D1 (Multi-Process):** Python spawns Rust as subprocess — NO PyO3/FFI. This is a deliberate architectural shift from ClaudeBackTester's in-process PyO3 model. The bridge MUST use subprocess + Arrow IPC files. **Research Update:** Rust evaluator must support fold-aware batch evaluation (accept fold boundaries, return per-fold scores), windowed evaluation (load data once, evaluate multiple parameter batches), and library-with-subprocess-wrapper pattern for zero-cost PyO3 migration path.
- **D14 (Pre-Computed Signals):** Phase 1 (Epic 3) indicators stay in Python — pre-computed signals passed via Arrow IPC to Rust. Rust does NOT compute indicators in Epic 3. The bridge passes signal data alongside market data.
- **D2 (Arrow IPC):** All data exchange via Arrow IPC files. Market data read via mmap. Results written as Arrow IPC. No JSON/CSV for bulk data. Schema SSOT: `contracts/arrow_schemas.toml`.
- **D3 (Pipeline Orchestration):** Each strategy gets an independent sequential state machine. Parallelism lives within stages (Rayon inside Rust), not between stages. Orchestrator decides admission and concurrency; Rust enforces its local memory budget once launched.
- **D8 (Error Schema):** Structured JSON errors on stderr: `{error_type, category, message, context}`. Categories: `resource_pressure`, `data_logic`, `external_failure`.
- **NFR4 (Memory):** Pre-allocate at startup, no dynamic heap on hot paths. Reduce batch size if budget exceeded — never crash.
- **NFR5 (Checkpointing):** Configurable granularity. Resume from last checkpoint on restart.
- **NFR10 (Crash Isolation):** Rust crash must NOT take down Python orchestrator.
- **NFR15 (Crash-Safe Writes):** Write → fsync → atomic rename. `.partial` suffix pattern.

### Technical Requirements

- **Async Python:** Use `asyncio.create_subprocess_exec` for non-blocking dispatch
- **Windows Compatibility:** No SIGTERM on Windows — use `process.terminate()` (sends CTRL_BREAK). Use `ctrlc` crate on Rust side for cross-platform signal handling. File paths use forward slashes internally.
- **Existing Rust Crates Already Available:**
  - `strategy_engine::parser::parse_spec_from_file(path)` → `StrategySpec`
  - `cost_model::loader::load_from_file(path)` → `CostModel`
  - `cost_model::cost_engine::CostModel::apply_cost(fill_price, session, direction)` → `f64`
  - Error types use `thiserror` crate throughout
  - `StrategySpec` and `CostModelArtifact` use `#[serde(deny_unknown_fields)]`
- **Arrow Schemas:** Must align with `crates/common/src/arrow_schemas.rs` — check what schemas exist and extend as needed for trade-log, equity-curve, metrics

### Story 3-3 Interface Compliance

Story 3-4 MUST implement the `StageExecutor` protocol from Story 3-3:
```python
class StageExecutor(Protocol):
    def execute(self, strategy_id: str, context: dict) -> StageResult: ...
    def validate_artifact(self, artifact_path: Path, manifest_ref: Path) -> bool: ...

@dataclass
class StageResult:
    artifact_path: str | None
    manifest_ref: str | None
    outcome: str  # "success" | "failed"
    metrics: dict
    error: PipelineError | None
```

The `BacktestExecutor` participates in the `backtest-running` pipeline stage. It is called by `StageRunner` from Story 3-3. Errors must propagate as `PipelineError` objects.

### Story 3-2 Research Dependency

Story 3-2 research outputs define contracts this story must implement:
- **IPC mechanism:** Subprocess + Arrow IPC (validates D1)
- **Reproducibility contract:** Defines what "identical output" means (bit-identical vs tolerance)
- **Checkpoint schema:** `contracts/pipeline_checkpoint.toml` (cross-runtime SSOT)
- **Within-stage checkpoint contract:**
  ```python
  @dataclass
  class WithinStageCheckpoint:
      stage: PipelineStage
      progress_pct: float
      last_completed_batch: int
      total_batches: int
      partial_artifact_path: str | None
      checkpoint_at: str  # ISO 8601
  ```
- **Memory budget model:** System inventory → reserve 2-4GB OS margin → pre-allocate remainder

**IMPORTANT:** Stories 3-1, 3-2, 3-3 are research/infrastructure stories that MUST complete before 3-4 implementation. Their outputs define contracts this story implements. If those stories change contracts, this story must adapt.

### Published Outputs vs Runtime Working Files

This story produces two categories of files. The distinction is critical for reproducibility (FR18/FR61) and downstream story boundaries:

| Category | Files | Deterministic? | Owner |
|----------|-------|----------------|-------|
| **Deterministic outputs** | `trade-log.arrow`, `equity-curve.arrow`, `metrics.arrow` | Yes — byte-identical across identical runs | Rust binary writes; Python verifies schemas |
| **Ephemeral runtime files** | `progress.json`, `checkpoint.json`, `run_metadata.json` | No — contain timestamps, elapsed time | Rust binary writes; Python reads for status |
| **Artifact metadata** | `manifest.json` (config hash, file hashes, versions) | N/A — created after run | Python artifact layer (Story 3.6) |

Story 3.4 owns dispatch and raw output verification. Story 3.6 owns manifest creation, versioned artifact storage, and SQLite ingest.

### Project Structure Notes

**Files to CREATE:**
```
src/python/rust_bridge/batch_runner.py     # BatchRunner, BacktestJob, BatchResult
src/python/rust_bridge/error_parser.py     # RustError, parse_rust_error, map_to_pipeline_error
src/python/rust_bridge/output_verifier.py  # BacktestOutputRef, verify_output, validate_schemas
src/python/rust_bridge/backtest_executor.py # BacktestExecutor (StageExecutor impl)
src/rust/crates/backtester/src/bin/forex_backtester.rs  # CLI binary entry point
src/rust/crates/backtester/src/progress.rs   # ProgressReport, write_progress
src/rust/crates/backtester/src/output.rs     # Arrow IPC result writer
src/rust/crates/backtester/src/memory.rs     # MemoryBudget enforcement
src/python/tests/test_rust_bridge/test_batch_runner.py  # Integration tests
src/rust/crates/backtester/tests/test_bridge_cli.rs     # Rust CLI integration tests
```

**Files to CREATE (common crate infrastructure — Task 6, Task 8 prerequisites):**
```
src/rust/crates/common/src/error_types.rs  # StructuredError, ErrorCategory, BacktesterError (NEW — does not exist)
src/rust/crates/common/src/arrow_schemas.rs # Rust-side schemas validated against contracts/arrow_schemas.toml (NEW — does not exist)
```

**Files to MODIFY:**
```
src/python/rust_bridge/__init__.py         # Export new modules (currently empty)
src/rust/crates/backtester/Cargo.toml      # Add clap, arrow, ctrlc, sysinfo, serde, strategy_engine, cost_model, common deps
src/rust/crates/common/Cargo.toml          # Add serde, serde_json, thiserror deps
src/rust/crates/common/src/lib.rs          # Add pub mod error_types; pub mod arrow_schemas; (currently 1-line stub)
```

**Alignment with project structure (from architecture):**
- Python bridge code: `src/python/rust_bridge/` (D1-D3: IPC boundary)
- Rust backtester binary: `src/rust/crates/backtester/src/bin/` (Rust workspace layout)
- Shared types: `src/rust/crates/common/` (common crate, validates against `contracts/`)
- Test location: `src/python/tests/test_rust_bridge/` (architecture test structure)
- Artifacts output: `artifacts/{strategy_id}/v{NNN}/backtest/` (architecture artifact layout)

## What to Reuse from ClaudeBackTester

| Component | ClaudeBackTester Location | Action | Rationale |
|-----------|--------------------------|--------|-----------|
| Parameter layout (64-slot `PL_*`) | `rust/src/constants.rs` | **Do NOT port** — replaced by TOML `StrategySpec` | D14 moves to typed specs, not flat arrays |
| PyO3 `batch_evaluate()` | `rust/src/lib.rs` | **Do NOT port** — replaced by subprocess CLI | D1 mandates multi-process, not in-process FFI |
| Trade simulation logic | `rust/src/trade_basic.rs`, `trade_full.rs` | **Port to `crates/backtester/`** (Story 3-5) | Clean stateless Rust — direct port candidate |
| Numpy array marshalling | `rust/src/lib.rs` (PyO3 glue) | **Do NOT port** — replaced by Arrow IPC mmap | D2 mandates Arrow, not numpy arrays |
| Subprocess pattern | N/A (ClaudeBackTester uses in-process) | **Build new** | D1 requires subprocess architecture |
| Metrics computation | `rust/src/metrics.rs` | **Port to `crates/backtester/`** (Story 3-5) | Inline, efficient — direct port |

**Key lesson from 3-1 review:** ClaudeBackTester is Python-first (15.5K+ lines) with a small Rust PyO3 extension (1.6K lines). The new architecture inverts this — Rust handles all compute as standalone binaries, Python only orchestrates.

## Anti-Patterns to Avoid

1. **Do NOT use PyO3/FFI** — D1 mandates subprocess architecture. The entire point of this story is the process boundary.
2. **Do NOT serialize data as JSON/CSV for bulk transfer** — Arrow IPC with mmap is the only acceptable bulk data format (D2).
3. **Do NOT use `subprocess.Popen` with `shell=True`** — security risk and Windows compatibility issue. Use `asyncio.create_subprocess_exec` with explicit argument list.
4. **Do NOT poll subprocess with busy-wait loops** — use `asyncio` process communication (`communicate()` or stream reading).
5. **Do NOT catch-and-swallow Rust errors** — all errors must propagate as structured `PipelineError` to the orchestrator for proper recovery action.
6. **Do NOT allocate dynamically on the Rust hot path** — NFR4 requires pre-allocation. Trade buffers sized at startup.
7. **Do NOT write output files without crash-safe semantics** — always write → fsync → atomic rename. No partial files left on success.
8. **Do NOT hardcode file paths or binary names** — use configuration. Binary path should be discoverable (e.g., `cargo build` output or config).
9. **Do NOT implement trade simulation in this story** — that's Story 3-5. This story builds the bridge/dispatch layer only. The backtester binary can start as a stub that reads inputs and writes minimal valid output.
10. **Do NOT ignore Windows subprocess semantics** — no SIGTERM, use CTRL_BREAK. Test on Windows (Git Bash).
11. **Do NOT use pandas for bulk result ingestion** — use `pyarrow.ipc.open_file()` with mmap for memory-mapped reads. Pandas materializes entire tables in memory, negating Arrow IPC benefits.
12. **Do NOT assume common crate infrastructure exists** — `error_types.rs` and `arrow_schemas.rs` must be created in Task 6 before other Rust tasks can compile.

## References

- [Source: _bmad-output/planning-artifacts/architecture.md — D1 Process Boundaries]
- [Source: _bmad-output/planning-artifacts/architecture.md — D2 Data Exchange Format]
- [Source: _bmad-output/planning-artifacts/architecture.md — D3 Resource Management]
- [Source: _bmad-output/planning-artifacts/architecture.md — D8 Error Handling]
- [Source: _bmad-output/planning-artifacts/architecture.md — D14 Strategy Engine Shared Crate]
- [Source: _bmad-output/planning-artifacts/prd.md — FR14, FR15, FR18, FR40, FR41, FR61]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR1, NFR4, NFR5, NFR10, NFR15]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 3, Story 3.4]
- [Source: _bmad-output/implementation-artifacts/3-1-claudebacktester-backtest-engine-review.md — batch_evaluate() interface, V1 port boundary]
- [Source: _bmad-output/implementation-artifacts/3-2-python-rust-ipc-deterministic-backtesting-research.md — IPC contracts, reproducibility, checkpoint schema, memory model]
- [Source: _bmad-output/implementation-artifacts/3-3-pipeline-state-machine-checkpoint-infrastructure.md — StageExecutor protocol, error handling, crash-safe writes]
- [Source: src/rust/crates/strategy_engine/src/parser.rs — parse_spec_from_file]
- [Source: src/rust/crates/cost_model/src/loader.rs — load_from_file]
- [Source: src/rust/crates/cost_model/src/cost_engine.rs — CostModel::apply_cost]
- [Source: src/rust/crates/common/src/error_types.rs — to be created in Task 6]
- [Source: contracts/arrow_schemas.toml — cross-runtime Arrow schema SSOT]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

- Windows `sysinfo v0.32` crate caused STATUS_ACCESS_VIOLATION during compilation — replaced with direct Win32 FFI `GlobalMemoryStatusEx` call
- Windows file lock issue on `std::fs::rename` after `File::open` for fsync — fixed by using `File::create` for write+fsync in single handle, dropping before rename

### Completion Notes List

- ✅ Task 6: Created `common/src/error_types.rs` (StructuredError, ErrorCategory, BacktesterError, panic hook) and `common/src/arrow_schemas.rs` (trade-log, equity-curve, metrics schemas validated against contracts/arrow_schemas.toml). Added serde, serde_json, thiserror deps to common crate.
- ✅ Task 5: Created `backtester/src/bin/forex_backtester.rs` CLI binary with clap-derived Args struct matching the full CLI contract (--spec, --data, --cost-model, --output, --config-hash, --memory-budget, plus optional fold/window/batch args). Input path validation, structured error output on stderr, panic hook installed.
- ✅ Task 7: Created `backtester/src/progress.rs` — ProgressReport struct, crash-safe write_progress(), should_report() throttling function.
- ✅ Task 8: Created `backtester/src/output.rs` — crash-safe write_results() with .partial→fsync→rename pattern, deterministic stub output files, verify_no_partials(), run_metadata.json with config_hash.
- ✅ Task 9: Signal handling via ctrlc crate with AtomicBool flag. Checkpoint written on cancellation. Graceful degradation if signal registration fails.
- ✅ Task 10: Created `backtester/src/memory.rs` — MemoryBudget with system memory check (Win32 GlobalMemoryStatusEx / /proc/meminfo), batch size reduction on tight budget, allocation tracking.
- ✅ Task 1: Created `rust_bridge/batch_runner.py` — BacktestJob, BatchResult, ProgressReport dataclasses. BatchRunner with async dispatch, cancellation (CTRL_BREAK on Windows), progress polling, path normalization.
- ✅ Task 2: Created `rust_bridge/error_parser.py` — RustError dataclass, parse_rust_error() (handles D8 JSON, malformed stderr, empty), map_to_pipeline_error() mapping categories to orchestrator actions.
- ✅ Task 3: Created `rust_bridge/output_verifier.py` — BacktestOutputRef, verify_output(), validate_schemas(), verify_fold_scores(). Returns path references only (no data materialization).
- ✅ Task 4: Created `rust_bridge/backtest_executor.py` — BacktestExecutor implementing StageExecutor protocol. Bridges async/sync boundary. Builds BacktestJob from context dict, dispatches, verifies output, maps errors.
- ✅ Task 11: Created 33 unit tests + 9 live integration tests in Python, 4 Rust CLI integration tests. All 42 Python tests pass, all Rust tests pass, 935 total regression suite passes.
- ✅ Task 12: Updated `rust_bridge/__init__.py` with all exports. Updated backtester/Cargo.toml with all dependencies.

### Change Log

- 2026-03-18: Story 3-4 fully implemented. Created Python-Rust bridge layer with subprocess dispatch, structured error handling, output verification, and StageExecutor integration. All 12 tasks complete. 42 Python tests (33 unit + 9 live) and 17 Rust tests pass. 935 regression tests pass with zero failures.

### File List

**Files Created:**
- `src/rust/crates/common/src/error_types.rs` — StructuredError, ErrorCategory, BacktesterError, panic hook
- `src/rust/crates/common/src/arrow_schemas.rs` — Arrow schema definitions for trade-log, equity-curve, metrics
- `src/rust/crates/backtester/src/bin/forex_backtester.rs` — CLI binary entry point
- `src/rust/crates/backtester/src/progress.rs` — Progress reporting module
- `src/rust/crates/backtester/src/output.rs` — Crash-safe Arrow IPC output writer
- `src/rust/crates/backtester/src/memory.rs` — Memory budget enforcement
- `src/rust/crates/backtester/tests/test_bridge_cli.rs` — Rust CLI integration tests
- `src/python/rust_bridge/batch_runner.py` — BatchRunner, BacktestJob, BatchResult
- `src/python/rust_bridge/error_parser.py` — RustError, parse_rust_error, map_to_pipeline_error
- `src/python/rust_bridge/output_verifier.py` — BacktestOutputRef, verify_output, validate_schemas
- `src/python/rust_bridge/backtest_executor.py` — BacktestExecutor (StageExecutor impl)
- `src/python/tests/test_rust_bridge/__init__.py` — Test package init
- `src/python/tests/test_rust_bridge/test_batch_runner.py` — 33 unit tests + 9 live integration tests

**Files Modified:**
- `src/rust/crates/common/src/lib.rs` — Added pub mod error_types; pub mod arrow_schemas;
- `src/rust/crates/common/Cargo.toml` — Added serde, serde_json, thiserror deps
- `src/rust/crates/backtester/src/lib.rs` — Replaced stub with pub mod memory, output, progress
- `src/rust/crates/backtester/Cargo.toml` — Added clap, serde, serde_json, sha2, ctrlc, common, strategy_engine deps + binary target
- `src/python/rust_bridge/__init__.py` — Added all module exports
