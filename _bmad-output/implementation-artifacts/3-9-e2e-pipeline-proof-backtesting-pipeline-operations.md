# Story 3.9: E2E Pipeline Proof — Backtesting & Pipeline Operations

Status: done

## Research Update Note (2026-03-18)

This story has been updated to reflect architecture research findings from Stories 3-1/3-2, Research Briefs 3A-3C, and optimization methodology research.

**Key alignment notes:**
- **Stories 3-3 through 3-8** have been updated with research findings. This E2E proof validates the updated specifications, including: opaque optimization state model (D3), fold-aware evaluation interfaces (D1), expanded exit types (D10), pre-computed signals (D14), deterministic-first evidence packs (D11), and per-fold score storage.
- **Epic 3 scope boundary:** This proof validates the infrastructure interfaces. Optimization algorithm selection, DSR/PBO validation gates, and candidate compression are Epic 5 scope. The E2E proof verifies the interfaces exist and are exercisable, not that optimization produces good results.

**References:** architecture.md Research Updates to D1, D3, D10, D11, D14; all updated story specs (3-3 through 3-8)

## Story

As the **operator**,
I want to run the full backtesting pipeline end-to-end — from market data through strategy evaluation to reviewed results — and verify deterministic reproducibility,
So that I know the backtesting engine and pipeline operations work correctly before building optimization on top of them.

## Acceptance Criteria

1. **Given** all backtesting and pipeline components are implemented (Stories 3.3–3.8)
   **When** the pipeline proof is executed using Epic 1's reference dataset and Epic 2's reference strategy and cost model
   **Then** the pipeline state machine initializes for the reference strategy and tracks progression through stages (D3, FR40)

2. **And** the Python-Rust bridge dispatches the backtest job with correct parameters: strategy spec path, market data path, cost model path, memory budget (D1)

3. **And** the Rust backtester evaluates the strategy against the reference dataset with session-aware cost application and produces trade log (with expanded exit types per D10: StopLoss, TakeProfit, TrailingStop, ChandelierExit, SignalReversal, EndOfData, SubBarM1Exit, StaleExit, PartialClose, BreakevenWithOffset, MaxBarsExit), equity curve, and key metrics (FR14, FR15, D10)

4. **And** results are stored as versioned artifacts in Arrow IPC, ingested into SQLite, and archived to Parquet — following the three-format storage chain (D2, FR58)

5. **And** the manifest links all inputs: dataset hash, strategy spec version, cost model version, config hash (FR59)

6. **And** the AI analysis layer generates a deterministic narrative summary (computation first, narration second per D11 Research Update), runs anomaly detection, and assembles an evidence pack (FR16, FR17, D11)

7. **And** the operator reviews the evidence pack via `/pipeline` → "Review Results" and advances the pipeline via `/pipeline` → "Advance Stage" (FR39, D9)

8. **And** `/pipeline` → "Status" shows the correct stage progression with timestamps (FR40)

9. **And** a second run with identical inputs produces bit-identical results: same trade log, same equity curve, same metrics, and same deterministic manifest fields (dataset_hash, strategy_spec_version, cost_model_version, config_hash). Volatile fields (run_id, created_at, completed_at) are excluded from comparison. (FR18, FR61)

10. **And** pipeline resume works: if the backtest is interrupted mid-run and restarted, it resumes from the last checkpoint rather than restarting (FR42). Note: NFR5 specifically targets optimization runs; this proof tests the general pipeline resume infrastructure (FR42) that optimization will later build upon.

11. **And** all structured logs are present and correctly formatted across both Python and Rust runtimes (D6)

12. **And** this backtest result and pipeline state are saved for use in all subsequent epic pipeline proofs

## Tasks / Subtasks

- [x] **Task 1: E2E Test Infrastructure & Reference Inputs** (AC: #1, #2, #9, #12)
  - [x]1.1: Create `tests/e2e/epic3_pipeline_proof.py` — main E2E orchestrator script following the established pattern from `tests/e2e/epic1_pipeline_proof.py` and `tests/e2e/epic2_pipeline_proof.py`
  - [x]1.2: Create `tests/e2e/fixtures/epic3/` directory for Epic 3-specific fixtures
  - [x]1.3: Write `conftest.py` additions: register `@pytest.mark.e2e` if not already present, add Epic 3 fixture paths, artifact directory setup for `artifacts/{strategy_id}/v001/backtest/`
  - [x]1.4: Load Epic 1's reference dataset — read `tests/e2e/fixtures/epic1/fixture_manifest.json` to discover the exact Arrow IPC filename and its SHA-256 hash. Load the referenced file (EURUSD 1 year M1) and its associated manifest for dataset hash verification. Fail with a clear message if the fixture manifest is missing or the referenced file doesn't exist.
  - [x]1.5: Load Epic 2's reference strategy spec and cost model — read `tests/e2e/fixtures/epic2/fixture_manifest.json` to discover exact filenames and hashes for:
    - Strategy spec: locked TOML file (MA crossover EURUSD H1)
    - Cost model artifact: session-aware EURUSD cost model
    - Use the fixture manifest as the SSOT for filenames — do not hardcode assumed names
  - [x]1.6: Verify all three reference inputs exist and have valid SHA-256 hashes before proceeding — compare against hashes recorded in their respective fixture manifests. Fail fast with clear message listing which inputs are missing or have mismatched hashes.
  - [x]1.7: Create a test-local config overlay `tests/e2e/fixtures/epic3/test_config_overlay.toml` with backtesting reference paths. Do NOT mutate `config/base.toml` — the test must be self-contained and not create implicit drift in global config. The overlay contains:
    ```toml
    [backtesting.reference]
    strategy_id = "ma_crossover_eurusd_h1"
    strategy_spec_path = "tests/e2e/fixtures/epic2/{strategy_spec_file}"  # from fixture_manifest
    dataset_path = "tests/e2e/fixtures/epic1/{dataset_file}"              # from fixture_manifest
    cost_model_path = "tests/e2e/fixtures/epic2/{cost_model_file}"        # from fixture_manifest
    ```
    Load this overlay merged with `config/base.toml` at test startup, following the existing config layering pattern.

- [x] **Task 2: Pipeline State Machine Initialization & Stage Tracking** (AC: #1, #8)
  - [x]2.1: Import `PipelineState`, `PipelineStage`, `StageRunner`, `GateManager` from `src/python/orchestrator/` (Story 3-3)
  - [x]2.2: Create or load `PipelineState` for the reference strategy — if `artifacts/{strategy_id}/pipeline-state.json` exists from a prior run, verify it's in a resumable state; otherwise initialize fresh with `current_stage=DATA_READY`
  - [x]2.3: Advance state from `DATA_READY` → `STRATEGY_READY` (automatic, using Epic 1 + 2 artifacts already present)
  - [x]2.4: Verify `pipeline-state.json` written correctly with `strategy_id`, `run_id` (UUID), `current_stage`, `completed_stages`, `created_at`, `config_hash`
  - [x]2.5: Assert stage transitions are logged with structured JSON: `stage`, `strategy_id`, `timestamp`, `correlation_id`, `from_stage`, `to_stage`

- [x] **Task 3: Python-Rust Bridge Backtest Dispatch** (AC: #2, #3)
  - [x]3.1: Call `operator_actions.run_backtest(strategy_id, config)` (Story 3-8) which internally:
    - Reads strategy spec path and dataset ref from `PipelineState` (state-driven, not scanned)
    - Creates `BacktestExecutor` (Story 3-4) and registers it with `StageRunner`
    - Transitions state to `BACKTEST_RUNNING`
    - Spawns Rust backtester via `asyncio.create_subprocess_exec()` (D1 — subprocess only, NO PyO3/FFI)
    - Passes context dict with required keys: `{"strategy_spec_path": str, "dataset_path": str, "cost_model_path": str, "memory_budget_mb": int, "output_dir": str, "correlation_id": str}`
  - [x]3.2: Verify Rust process exits with code 0. Use `asyncio.wait_for()` with timeout from config (default 300s for backtesting). On non-zero exit: capture stderr, parse as structured error, fail with full error context. On timeout: kill process, report timeout.
  - [x]3.3: Verify the Rust backtester wrote Arrow IPC output files to `artifacts/{strategy_id}/v001/backtest/`. Expected filenames per Story 3-6 implementation artifact and `contracts/arrow_schemas.toml` (SSOT):
    - Trade log Arrow IPC — individual trades with entry/exit timestamps, prices, session, P&L, exit_reason (expanded D10 enum values)
    - Equity curve Arrow IPC — per-bar equity values
    - Metrics Arrow IPC — summary metrics (win rate, profit factor, Sharpe ratio, max drawdown, R-squared)
    - **Note:** Read actual filenames from `contracts/arrow_schemas.toml` section headers — do not hardcode names that may differ from the schema contract
  - [x]3.4: Verify state transitions to `BACKTEST_COMPLETE` (automatic) after Rust process completes

- [x] **Task 4: Three-Format Artifact Storage & Manifest** (AC: #4, #5)
  - [x]4.1: Verify Arrow IPC files are readable via `pyarrow.ipc.open_file()` (mmap-compatible) and schemas match `contracts/arrow_schemas.toml` (the SSOT). Read the schema TOML at test startup to discover section names and expected fields — do not hardcode field lists in the test. Validate that each Arrow file's schema contains all fields declared in its corresponding TOML section.
  - [x]4.2: Verify SQLite ingest completed — `artifacts/{strategy_id}/v001/pipeline.db` exists at the version root (NOT inside `backtest/` subdirectory — per D2 directory structure). Contains:
    - `trades` table with indexed columns (strategy_id, entry_time, exit_time, session)
    - `equity_curve` table with per-bar records
    - `metrics` table with summary row
    - Row counts match Arrow IPC source data
  - [x]4.3: Verify Parquet archival — `artifacts/{strategy_id}/v001/backtest/trade_log.parquet` exists with snappy compression
  - [x]4.4: Verify `artifacts/{strategy_id}/v001/manifest.json` contains:
    - `dataset_hash` — matching Epic 1 reference dataset hash
    - `strategy_spec_version` — matching Epic 2 reference spec version + hash
    - `cost_model_version` — matching Epic 2 reference cost model hash
    - `config_hash` — computed from all input parameters
    - `run_id` — matching PipelineState.run_id
    - `created_at` — ISO 8601 timestamp
  - [x]4.5: Verify all hashes are deterministic (SHA-256 of file contents)

- [x] **Task 5: AI Analysis Layer & Evidence Pack** (AC: #6)
  - [x]5.1: Verify `operator_actions.run_backtest()` triggered evidence pack assembly after successful backtest (chained call to `assemble_evidence_pack(backtest_id, db_path=..., artifacts_root=...)` from Story 3-7)
  - [x]5.2: Verify evidence pack saved at `artifacts/{strategy_id}/v001/backtest/evidence_pack.json` (underscored filename)
  - [x]5.3: Load and validate `EvidencePack` contains all 11 fields:
    - `backtest_id: str`
    - `strategy_id: str`
    - `version: str`
    - `narrative: NarrativeResult` — with `overview`, `metrics`, `strengths`, `weaknesses`, `session_breakdown`, `risk_assessment` (NOT `summary`/`interpretation`)
    - `anomalies: AnomalyReport` — wrapper with `backtest_id`, `anomalies: list[AnomalyFlag]`, `run_timestamp` (NOT bare list)
    - `metrics: dict`
    - `equity_curve_summary: list[dict]` — downsampled for display
    - `equity_curve_full_path: str` — canonical reference
    - `trade_distribution: dict` — by session
    - `trade_log_path: str`
    - `metadata: dict` — manifest linkage, schema version
  - [x]5.4: Verify narrative `overview` describes equity curve shape and drawdown profile
  - [x]5.5: Verify anomaly detection ran — `AnomalyReport.anomalies` may be empty (no anomalies) or populated (flags found), but the report structure must exist. **Research Update:** Verify `AnomalyType` enum includes forward-compatible DSR_BELOW_THRESHOLD and PBO_HIGH_PROBABILITY values (stubs returning None in Epic 3).

- [x] **Task 6: Operator Review & Pipeline Advancement via `/pipeline` Skill** (AC: #7, #8)
  - [x]6.1: Verify state is `REVIEW_PENDING` (gated) after evidence pack assembly
  - [x]6.2: Call `operator_actions.load_evidence_pack(strategy_id, config)` — verify it returns the `EvidencePack` from Task 5 with all fields correctly deserialized
  - [x]6.3: Call `operator_actions.get_pipeline_status(config)` — verify returned list includes the reference strategy with:
    - `stage: "review-pending"`
    - `decision_required: True`
    - `gate_status: "awaiting_decision"`
    - `anomaly_count: int` (matching evidence pack)
    - `evidence_pack_ref: str` (path to evidence_pack.json)
  - [x]6.4: Call `operator_actions.advance_stage(strategy_id, reason="E2E proof: results accepted", config=config)` — verify it creates `GateDecision(decision="accept", stage=REVIEW_PENDING, reason="E2E proof: results accepted", evidence_pack_ref=...)`
  - [x]6.5: Verify state transitions to `REVIEWED` after advance
  - [x]6.6: Verify `pipeline-state.json` updated with the `GateDecision` in `gate_decisions` history
  - [x]6.7: Verify advancing does NOT check profitability — a losing strategy must also be advanceable (FR41)
  - [x]6.8: Verify reject path exists: call `operator_actions.reject_stage(strategy_id, reason="E2E proof: testing reject path", config=config)` on a separate test run, verify state does NOT advance to REVIEWED and the rejection is recorded in `gate_decisions` history. This validates the three-way decision model (accept/reject/refine) without exhaustive coverage — full reject/refine flow testing belongs in Story 3-8 unit tests.

- [x] **Task 7: Deterministic Reproducibility Verification** (AC: #9)
  - [x]7.1: Reset test environment: create a new version directory `v002` (or use a separate temp directory)
  - [x]7.2: Run the full pipeline again with identical inputs: same strategy spec, same dataset, same cost model, same config
  - [x]7.3: Compare Run 1 vs Run 2 outputs byte-by-byte:
    - `trade_log.arrow` — SHA-256 hash must match
    - `equity_curve.arrow` — SHA-256 hash must match
    - `metrics.arrow` — SHA-256 hash must match
  - [x]7.4: Compare manifest deterministic fields only: `dataset_hash`, `strategy_spec_version`, `cost_model_version`, `config_hash` must match. Fields expected to differ between runs: `run_id`, `created_at`, `completed_at` — exclude these from comparison.
  - [x]7.5: Compare SQLite trade data: query `SELECT * FROM trades ORDER BY entry_time, direction` from both runs (include `direction` as tiebreaker for same-bar entries), compare row-by-row — all numeric fields must be exactly equal, not approximately equal.
  - [x]7.6: Compare evidence pack `metrics` dict — key performance numbers must be identical
  - [x]7.7: If any mismatch found, fail with detailed diff showing which field diverged

- [x] **Task 8: Checkpoint & Resume Verification** (AC: #10)
  - [x]8.1: Start a backtest run, then simulate interruption:
    - Option A (preferred): Mock the Rust subprocess to write a `WithinStageCheckpoint` after processing 50% of data, then exit with non-zero code
    - Option B: Use a test hook to kill the Rust process after checkpoint is written
  - [x]8.2: Verify `pipeline-state.json` has `checkpoint` field populated with:
    - `stage: BACKTEST_RUNNING`
    - `progress_pct: float > 0`
    - `last_completed_batch: int`
    - `total_batches: int`
    - `partial_artifact_path: str`
    - `checkpoint_at: str` (ISO 8601)
  - [x]8.3: Call `operator_actions.resume_pipeline(strategy_id, config)` (Story 3-8)
  - [x]8.4: Verify resume calls `recover_from_checkpoint(state)` (Story 3-3 `recovery.py`) which reads the checkpoint and continues from `last_completed_batch`
  - [x]8.5: Verify the resumed run completes successfully and produces valid artifacts
  - [x]8.6: Verify state eventually reaches `BACKTEST_COMPLETE` → `REVIEW_PENDING`

- [x] **Task 9: Structured Logging Verification** (AC: #11)
  - [x]9.1: After the full proof run, scan `logs/` directory for today's log file(s)
  - [x]9.2: Parse each log line as JSON and verify required fields present: `timestamp`, `level`, `stage`, `strategy_id`, `correlation_id`, `component`, `runtime`
  - [x]9.3: Verify Python-side logs contain: state transitions, operator actions (run_backtest, advance_stage), evidence pack assembly, artifact storage operations
  - [x]9.4: Verify Rust-side logs contain (captured from Rust stderr or a separate log file): backtest start/end, bar processing progress, trade signals, checkpoint writes
  - [x]9.5: Verify `correlation_id` is consistent across Python and Rust for the same run — the bridge passes it to the Rust subprocess

- [x] **Task 10: Save Reference Artifacts for Future Epics** (AC: #12)
  - [x]10.1: Save sanitized reference fixtures to `tests/e2e/fixtures/epic3/`. Strip volatile fields (`run_id`, `created_at`, `completed_at`, `last_transition_at`, `decided_at`, `checkpoint_at`, `run_timestamp`) from copies before saving — downstream epics should depend on stable contract shapes, not incidental runtime values:
    - `reference_backtest_manifest.json` — sanitized copy of `manifest.json` (volatile fields replaced with `"<volatile>"` placeholder)
    - `reference_evidence_pack.json` — sanitized copy of `evidence_pack.json`
    - `reference_pipeline_state.json` — sanitized copy of final `pipeline-state.json` (showing REVIEWED state)
    - `reference_metrics.json` — extracted key metrics for quick comparison (no volatile fields)
  - [x]10.2: Create `tests/e2e/fixtures/epic3/fixture_manifest.json` recording:
    ```json
    {
      "epic": 3,
      "story": "3-9",
      "created_by": "epic3_pipeline_proof.py",
      "volatile_fields_stripped": true,
      "schema_versions": {
        "arrow_schema": "<version from contracts/arrow_schemas.toml>",
        "sqlite_schema": "<version from Story 3-6 schema>",
        "evidence_pack_schema": "<version from Story 3-7>",
        "pipeline_state_version": "<PipelineState.version field>"
      },
      "fixture_hashes": {
        "reference_backtest_manifest.json": "<sha256 of sanitized copy>",
        "reference_evidence_pack.json": "<sha256 of sanitized copy>",
        "reference_pipeline_state.json": "<sha256 of sanitized copy>",
        "reference_metrics.json": "<sha256>"
      },
      "contract_dependencies": {
        "story_3_3": "PipelineState, GateDecision, WithinStageCheckpoint",
        "story_3_7": "EvidencePack, NarrativeResult, AnomalyReport",
        "story_3_8": "operator_actions API surface"
      }
    }
    ```
  - [x]10.3: Add `tests/e2e/fixtures/epic3/README.md` explaining what each fixture represents, which story produced it, and how Epic 4 should load them
  - [x]10.4: Verify all fixture hashes are deterministic — rerunning the proof should produce identical fixtures with matching hashes

## Dev Notes

### Scope Clarifications

- **FR16 (Chart-First Review):** This proof verifies the evidence pack contains all data needed for chart-first display (equity curve summary, trade distribution, metrics). Actual chart rendering is dashboard scope (FR62-FR65). The narrative generator produces chart-oriented text descriptions; visual rendering is not tested here.
- **Operator Boundary:** This proof tests through `operator_actions.py` (Story 3-8), which IS the boundary that the `/pipeline` Claude Code skill calls. Architecture D9 mentions REST API as the dashboard-to-backend boundary (D4), not the skill-to-pipeline boundary. For V1 with one operator, skills invoke `operator_actions.py` directly. REST API testing belongs in dashboard integration tests.
- **Artifact Naming:** File names in this story (e.g., `evidence_pack.json`) are derived from the **implementation artifact** specs (Stories 3-6, 3-7), which are the SSOT. The **epic summaries** in `epics.md` may use older names (e.g., `narrative.json`, `results.arrow`). When in doubt, the implementation artifact contracts and `contracts/arrow_schemas.toml` take precedence over epic-level descriptions.

### Architecture Constraints

- **D1 (System Topology):** Python-Rust boundary is subprocess ONLY (NO PyO3/FFI). Rust backtester invoked via `asyncio.create_subprocess_exec()`. Arrow IPC eliminates serialization overhead.
- **D2 (Artifact Schema):** Three-format storage: Arrow IPC (canonical, compute) → SQLite (queryable, indexed) → Parquet (archival, compressed). Directory: `artifacts/{strategy_id}/v{NNN}/backtest/`.
- **D3 (Pipeline Orchestration):** Sequential state machine per strategy. Stage flow: `data-ready → strategy-ready → backtest-running → backtest-complete → review-pending (GATED) → reviewed`. Gated transitions require explicit `GateDecision`. State is `pipeline-state.json` per strategy.
- **D6 (Logging):** Structured JSON logs to `logs/`, one file per runtime per day. All state transitions and operator decisions logged. Both Python and Rust must emit logs with matching `correlation_id`.
- **D8 (Error Handling):** Fail-fast at boundaries. Resource pressure → throttle. Data/logic error → stop and checkpoint. External failure → retry with backoff.
- **D9 (Operator Interface):** All operations via `/pipeline` Claude Code skill → Python `operator_actions.py`. Direct invocation: `PYTHONPATH=src/python .venv/Scripts/python.exe -c "..."`.
- **D11 (AI Analysis):** Evidence packs assembled after backtest complete. Narrative + anomaly detection + metrics for operator review. **Research Update:** Deterministic computation first, narrative second. All metrics are computed deterministically; narrative text is template-driven. Two-pass design (triage + deep review) architecturally defined but single-call in Epic 3.
- **D10 (Extended Strategy Spec):** Strategy spec supports sub-bar M1 SL/TP, stale exit, partial close, breakeven with offset, max bars exit, SignalCausality enum, and conditional parameter activation. Trade log exit_reason field uses expanded enum values.
- **D14 (Deterministic Backtesting / Pre-Computed Signals):** Same inputs MUST produce identical outputs. No floating-point non-determinism, no random seeds, no timestamp-dependent logic in the compute path. **Research Update:** Phase 1 (Epic 3) indicators stay in Python — pre-computed signals passed via Arrow IPC to Rust. Rust does NOT compute indicators in Epic 3.

### Key Integration Contracts

**From Story 3-3 (`src/python/orchestrator/`):**
```python
# pipeline_state.py
class PipelineStage(Enum):
    DATA_READY = "data-ready"
    STRATEGY_READY = "strategy-ready"
    BACKTEST_RUNNING = "backtest-running"
    BACKTEST_COMPLETE = "backtest-complete"
    REVIEW_PENDING = "review-pending"  # GATED
    REVIEWED = "reviewed"

@dataclass
class PipelineState:
    strategy_id: str
    run_id: str  # UUID per execution attempt
    current_stage: PipelineStage
    completed_stages: list[CompletedStage]
    pending_stages: list[PipelineStage]
    gate_decisions: list[GateDecision]
    created_at: str  # ISO 8601
    last_transition_at: str
    checkpoint: WithinStageCheckpoint | None
    error: PipelineError | None
    config_hash: str
    version: int

@dataclass
class GateDecision:
    stage: PipelineStage
    decision: str  # "accept" | "reject" | "refine"
    reason: str
    decided_at: str
    evidence_pack_ref: str | None

@dataclass
class WithinStageCheckpoint:
    stage: PipelineStage
    progress_pct: float
    last_completed_batch: int
    total_batches: int
    partial_artifact_path: str | None
    checkpoint_at: str

@dataclass
class CompletedStage:
    stage: str
    completed_at: str
    artifact_path: str | None
    manifest_ref: str | None
    duration_s: float
    outcome: str  # "success" | "skipped" | "failed"

# stage_runner.py
class StageRunner:
    def __init__(self, strategy_id, artifacts_dir, config): ...
    def register_executor(self, stage, executor): ...
    def run(self) -> StageResult: ...
    def get_status(self) -> PipelineStatus: ...

# gate_manager.py
class GateManager:
    def advance(self, state, decision: GateDecision) -> PipelineState: ...
    def check_preconditions(self, state, stage) -> tuple[bool, str | None]: ...

# recovery.py
def verify_last_artifact(state, executor) -> bool: ...
def recover_from_checkpoint(state) -> WithinStageCheckpoint | None: ...
```

**From Story 3-4 (`src/python/rust_bridge/`):**
```python
# backtest_executor.py
class BacktestExecutor:  # implements StageExecutor protocol
    def execute(self, strategy_id: str, context: dict) -> StageResult: ...
    def validate_artifact(self, artifact_path: Path, manifest_ref: Path) -> bool: ...

# context dict required keys for execute():
# {
#   "strategy_spec_path": str,      # Path to locked TOML strategy spec
#   "dataset_path": str,            # Path to Arrow IPC market data
#   "cost_model_path": str,         # Path to cost model artifact
#   "memory_budget_mb": int,        # From config, default 4096
#   "output_dir": str,              # artifacts/{strategy_id}/v{NNN}/backtest/
#   "correlation_id": str,          # Passed to Rust for log correlation
#   "checkpoint_dir": str | None,   # Resume path, None for fresh run
# }
```

**From Story 3-7 (`src/python/analysis/`):**
```python
# models.py
@dataclass
class NarrativeResult:
    overview: str
    metrics: dict
    strengths: list[str]
    weaknesses: list[str]
    session_breakdown: dict
    risk_assessment: str

@dataclass
class AnomalyFlag:
    type: AnomalyType  # LOW_TRADE_COUNT | ZERO_TRADES | PERFECT_EQUITY | etc.
    severity: Severity  # WARNING | ERROR
    description: str
    evidence: dict
    recommendation: str

@dataclass
class AnomalyReport:
    backtest_id: str
    anomalies: list[AnomalyFlag]
    run_timestamp: str

@dataclass
class EvidencePack:
    backtest_id: str
    strategy_id: str
    version: str
    narrative: NarrativeResult
    anomalies: AnomalyReport  # NOT bare list
    metrics: dict
    equity_curve_summary: list[dict]  # downsampled
    equity_curve_full_path: str
    trade_distribution: dict
    trade_log_path: str
    metadata: dict  # manifest linkage, schema version

# evidence_pack.py
def assemble_evidence_pack(backtest_id: str, db_path: Path | None = None,
                           artifacts_root: Path | None = None) -> EvidencePack: ...
```

**From Story 3-8 (`src/python/orchestrator/`):**
```python
# operator_actions.py
def run_backtest(strategy_id: str, config: dict) -> dict:
    """Returns {"status": "success"|"failed", "output_dir": str,
     "evidence_pack_path": str|None, "backtest_id": str|None,
     "run_id": str, "config_hash": str, "error": str|None}"""
    ...

def get_pipeline_status(config: dict) -> list[dict]:
    """Returns [{"strategy_id": str, "stage": str, "progress_pct": float,
     "last_transition_at": str, "gate_status": str|None,
     "decision_required": bool, "anomaly_count": int|None,
     "evidence_pack_ref": str|None, "blocking_reason": str|None,
     "last_outcome": str|None, "error": dict|None,
     "config_hash": str, "run_id": str}]"""
    ...

def load_evidence_pack(strategy_id: str, config: dict) -> dict:
    """Loads and returns deserialized EvidencePack from state-driven path"""
    ...

def advance_stage(strategy_id: str, reason: str, config: dict) -> dict:
    """Creates GateDecision(decision='accept') via GateManager.advance()"""
    ...

def reject_stage(strategy_id: str, reason: str, config: dict) -> dict: ...
def refine_stage(strategy_id: str, guidance: str, config: dict) -> dict: ...
def resume_pipeline(strategy_id: str, config: dict) -> dict: ...
```

### No-Profitability-Gate Enforcement (FR41)

The operator can push ANY strategy through the entire pipeline regardless of P&L results. The E2E proof MUST verify this — `advance_stage()` must NOT check profit_factor, Sharpe ratio, win_rate, or equity curve slope. Anomalies are informational only. Even a strategy with zero trades or negative returns can be advanced. Test this explicitly in Task 6.7.

### Deterministic Reproducibility Requirements (FR18, FR61)

The E2E proof must verify bit-identical results across two runs. This means:
- Arrow IPC files must hash identically (SHA-256)
- SQLite trade data must be row-identical when queried in deterministic order
- Metrics must be numerically identical (not "close enough" — exact match)
- Manifest `config_hash` must match
- `run_id` and timestamps are expected to differ — only compare deterministic fields

### What to Reuse from Previous E2E Proofs

**From Story 1-9 (`tests/e2e/epic1_pipeline_proof.py`):**
- Test infrastructure pattern: orchestrator script + conftest + fixtures
- Reference dataset fixture loading approach
- Reproducibility verification pattern (hash comparison)
- Structured logging verification approach
- Fixture saving pattern for downstream epics

**From Story 2-9 (`tests/e2e/epic2_pipeline_proof.py`):**
- Reference strategy and cost model fixture loading
- Schema version recording in fixture manifests
- Deterministic hash comparison pattern
- `@pytest.mark.e2e` marker usage

**Do NOT reuse:**
- Epic 1's pipeline_proof.py script directly — that's the data pipeline proof, not backtesting
- Any test patterns that hardcode paths rather than reading from config

### Anti-Patterns to Avoid

1. **Do NOT hardcode file paths** — read from `config/base.toml` and `PipelineState`. The proof must work on any machine with correct config.
2. **Do NOT bypass `operator_actions.py`** — always call the Story 3-8 entry points, never import internal modules directly. This tests the actual integration surface.
3. **Do NOT use approximate floating-point comparisons** for determinism checks — Arrow IPC binary comparison is exact. If hashes don't match, there's a real bug.
4. **Do NOT create profitability gates** — no assertions on positive P&L, positive Sharpe, or minimum win rate. The proof must work with any strategy result.
5. **Do NOT skip the three-format verification** — Arrow IPC, SQLite, AND Parquet must all be verified. Skipping one breaks the artifact chain guarantee.
6. **Do NOT mock the Rust subprocess** for the main proof (Tasks 2-7) — the whole point is E2E integration. Only Task 8 (checkpoint/resume) may mock for controlled interruption.
7. **Do NOT ignore Rust stderr** — capture and verify structured log output from the Rust process.
8. **Do NOT use `time.sleep()` for Rust process completion** — use `asyncio` subprocess APIs with proper `await`.

### Project Structure Notes

**Files to create:**
```
tests/e2e/
  epic3_pipeline_proof.py          # Main E2E orchestrator (new)
  fixtures/epic3/                  # Epic 3 reference fixtures (new dir)
    test_config_overlay.toml       # Test-local config overlay (new, NOT config/base.toml)
    README.md                      # Fixture descriptions (new)
```

**Files to modify:**
```
tests/e2e/conftest.py              # Add Epic 3 fixtures, paths
```

**Files to read/verify (NOT modify):**
```
src/python/orchestrator/
  operator_actions.py              # Story 3-8 — entry point for all operations
  pipeline_state.py                # Story 3-3 — PipelineState, PipelineStage, GateDecision
  stage_runner.py                  # Story 3-3 — StageRunner orchestration
  gate_manager.py                  # Story 3-3 — GateManager for gated transitions
  recovery.py                      # Story 3-3 — Checkpoint recovery

src/python/rust_bridge/
  backtest_executor.py             # Story 3-4 — BacktestExecutor subprocess bridge

src/python/analysis/
  evidence_pack.py                 # Story 3-7 — assemble_evidence_pack()
  narrative.py                     # Story 3-7 — Narrative generation
  anomaly_detector.py              # Story 3-7 — Anomaly detection
  models.py                        # Story 3-7 — EvidencePack, NarrativeResult, AnomalyReport

src/python/artifacts/
  storage.py                       # Story 3-6 — ArtifactStorage, SQLite ingest

artifacts/{strategy_id}/v001/      # Runtime output directory
  pipeline-state.json
  manifest.json
  pipeline.db                      # SQLite
  backtest/
    trade_log.arrow
    equity_curve.arrow
    metrics.arrow
    trade_log.parquet
    evidence_pack.json
```

**Rust crate (invoked as subprocess, not modified):**
```
src/rust/backtester/               # Story 3-5 — Rust backtester binary
```

### Windows Compatibility Notes

- Python invocation: `PYTHONPATH=src/python .venv/Scripts/python.exe -c "..."`
- Path separators: use `pathlib.Path` everywhere, never hardcode `/` or `\`
- Rust subprocess: use `asyncio.create_subprocess_exec()` with proper Windows process handling
- Line endings: ensure `\r\n` stripping when parsing Rust stderr output

### References

- [Source: _bmad-output/planning-artifacts/epics.md — Epic 3, Story 3.9]
- [Source: _bmad-output/planning-artifacts/architecture.md — D1: System Topology]
- [Source: _bmad-output/planning-artifacts/architecture.md — D2: Artifact Schema & Storage]
- [Source: _bmad-output/planning-artifacts/architecture.md — D3: Pipeline Orchestration]
- [Source: _bmad-output/planning-artifacts/architecture.md — D6: Logging & Observability]
- [Source: _bmad-output/planning-artifacts/architecture.md — D8: Error Handling]
- [Source: _bmad-output/planning-artifacts/architecture.md — D9: Operator Interface]
- [Source: _bmad-output/planning-artifacts/architecture.md — D11: AI Analysis Layer]
- [Source: _bmad-output/planning-artifacts/architecture.md — D14: Deterministic Backtesting]
- [Source: _bmad-output/planning-artifacts/prd.md — FR14-FR19: Backtesting]
- [Source: _bmad-output/planning-artifacts/prd.md — FR38-FR42: Pipeline Workflow & Operator Control]
- [Source: _bmad-output/planning-artifacts/prd.md — FR58-FR61: Artifact Requirements]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR5: Checkpointing]
- [Source: _bmad-output/implementation-artifacts/1-9-e2e-pipeline-proof-market-data-flow.md — E2E proof pattern, fixture saving]
- [Source: _bmad-output/implementation-artifacts/2-9-e2e-pipeline-proof-strategy-definition-cost-model.md — E2E proof pattern, determinism verification]
- [Source: _bmad-output/implementation-artifacts/3-3-pipeline-state-machine-checkpoint-infrastructure.md — PipelineState, StageRunner, GateManager, recovery]
- [Source: _bmad-output/implementation-artifacts/3-4-python-rust-bridge-batch-evaluation-dispatch.md — BacktestExecutor, BatchRunner]
- [Source: _bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md — ArtifactStorage, SQLiteManager]
- [Source: _bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md — EvidencePack, NarrativeResult, AnomalyReport, assemble_evidence_pack]
- [Source: _bmad-output/implementation-artifacts/3-8-operator-pipeline-skills-dialogue-control-stage-management.md — operator_actions.py function signatures]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

### Completion Notes List

- Fixed 3 integration bugs discovered during E2E proof:
  1. `operator_actions.py`: `BatchRunner(config)` passed dict as Path — added `_resolve_binary_path()` to extract binary path from config
  2. `stage_runner.py`: Executor context was minimal `{"artifacts_dir": ...}` — added `_build_executor_context()` to pass strategy_spec_path, market_data_path, cost_model_path, config_hash, memory_budget_mb, output_directory
  3. `stage_runner.py`: Evidence pack generation hook at `BACKTEST_COMPLETE` never fired (no executor → early return) — moved to `BACKTEST_RUNNING` post-success hook; also fixed db_path resolution to use versioned strategy directory
- Wrote 38 `@pytest.mark.live` tests covering all 10 tasks and 12 acceptance criteria
- Tests exercise real file I/O with real Python pipeline components (no mocks for system under test)
- Verified deterministic reproducibility: Arrow IPC SHA-256 hashes match across runs, SQLite data is row-identical, evidence pack metrics are identical
- Verified operator actions: advance, reject, and status all work correctly through `operator_actions.py`
- Verified evidence pack assembly produces all 11 required fields with correct narrative and anomaly report structures
- All 1072 existing unit tests pass — zero regressions

### File List

- `tests/e2e/test_epic3_pipeline_proof.py` — new: E2E pipeline proof with 38 live tests
- `tests/e2e/fixtures/epic3/test_config_overlay.toml` — new: test-local config overlay
- `tests/e2e/fixtures/epic3/README.md` — new: fixture documentation
- `src/python/orchestrator/operator_actions.py` — modified: fixed BatchRunner instantiation, added `_resolve_binary_path()`
- `src/python/orchestrator/stage_runner.py` — modified: stored `full_config`, added `_build_executor_context()`, fixed evidence pack trigger and db_path

### Change Log

- 2026-03-19: Implemented Epic 3 E2E pipeline proof — 38 live tests, 3 integration bug fixes, zero regressions
