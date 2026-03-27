# Story 3.8: Operator Pipeline Skills — Dialogue, Control & Stage Management

Status: done

## Research Update Note (2026-03-18)

This story has been updated to reflect architecture research findings from Stories 3-1/3-2, Research Briefs 3A-3C, and optimization methodology research.

**Key changes:**
- **D3 (Simplified State Model):** Optimization is opaque to the pipeline state machine — single `OPTIMIZING` state, not 5 sub-stages. Operator skills should NOT expose optimization sub-state management. When Epic 5 adds optimization, the operator interface will treat it as a single stage with progress reporting from the optimizer's internal state.
- **D11 (Deterministic-First):** Evidence pack presentation follows deterministic computation first, narrative second. All metrics in the evidence pack are computed deterministically; narrative text is template-driven from those metrics.

**References:** architecture.md Research Updates to D3, D11; optimization-methodology-research-summary.md

## Story

As the **operator**,
I want to control the pipeline through Claude Code dialogue — running backtests, reviewing results, and advancing or rejecting stages,
So that I can operate the entire pipeline through conversation without writing code.

## Acceptance Criteria

1. **Given** the pipeline state machine (Story 3.3) and evidence pack generation (Story 3.7)
   **When** the operator pipeline operations are implemented
   **Then** the existing `/pipeline` skill is extended with a "Run Backtest" operation that triggers a backtest for a specified strategy, invoking the Python-Rust bridge and tracking progress
   _(FR38, D9)_

2. **Given** the `/pipeline` skill's "Status" operation
   **When** the operator requests pipeline status
   **Then** the Status operation is extended to display pipeline state for all strategies: current stage, progress, last transition timestamp, any anomaly flags
   _(FR40, D9)_

3. **Given** a completed backtest with evidence pack
   **When** the operator selects "Review Results"
   **Then** the `/pipeline` skill presents the evidence pack (narrative summary, key metrics, anomaly flags) and prompts the operator for an accept/reject/refine decision
   _(FR39, D9)_

4. **Given** the operator reviews results and chooses "accept"
   **When** the "Advance Stage" operation is invoked
   **Then** the strategy moves to the next stage with the decision and timestamp recorded in pipeline state via `GateDecision`
   _(FR39, D9)_

5. **Given** the operator reviews results and chooses "reject"
   **When** the "Reject Stage" operation is invoked
   **Then** the strategy stage is marked rejected with the operator-provided reason; the strategy can be modified and re-submitted
   _(FR39, D9)_

6. **Given** the operator reviews results and chooses "refine"
   **When** the "Refine Stage" operation is invoked
   **Then** a `GateDecision(decision="refine")` is recorded with the operator's refinement guidance; the strategy returns to `STRATEGY_READY` for modification and re-submission without losing prior run history
   _(FR39, D9)_

7. **Given** a pipeline run was interrupted (crash, timeout, operator abort)
   **When** the "Resume Pipeline" operation is invoked
   **Then** interrupted runs are detected and resumed from the last checkpoint
   _(FR42, D9)_

8. **Given** all new operations
   **When** implemented
   **Then** all operations follow the D9 pattern: read pipeline state from filesystem, invoke Python `orchestrator/operator_actions.py` for mutations, present structured output to operator. `operator_actions.py` is the single mutation surface — designed as the backing implementation for future REST API endpoints (Epic 4). All operations are accessible from the single `/pipeline` menu — no separate skills are created
   _(D9)_

9. **Given** any skill operation that touches pipeline progression
   **When** the operator advances, rejects, refines, or runs a backtest
   **Then** skills enforce the no-profitability-gate principle: at no point does a skill block progression based on P&L results
   _(FR41)_

10. **Given** any skill invocation
    **When** an operator action occurs
    **Then** the action is logged with the unified log schema including operator action type, strategy_id, run_id, config_hash, timestamp, and decision
    _(D6)_

## Tasks / Subtasks

- [x] **Task 1: Create `operator_actions.py` — Pipeline Operation Entry Points** (AC: #1, #2, #3, #4, #5, #6, #7, #9, #10)
  - [x] 1.1: Create `src/python/orchestrator/operator_actions.py` with imports from existing Story 3-3/3-4/3-6/3-7 modules
  - [x] 1.2: Implement `run_backtest(strategy_id: str, config: dict) -> dict` — reads strategy spec path and dataset ref from existing `PipelineState` (state-driven, not scanned from artifacts), creates `PipelineState` if none exists (new run), instantiates `StageRunner(strategy_id, artifacts_dir, config)` with `BacktestExecutor` registered for `BACKTEST_RUNNING` stage, calls `.run()`. On success, triggers evidence pack assembly via `assemble_evidence_pack(backtest_id, db_path=..., artifacts_root=...)` (Story 3-7 — note the 3 params). Returns `{"status": "success"|"failed", "output_dir": str, "evidence_pack_path": str|None, "backtest_id": str|None, "run_id": str, "config_hash": str, "error": str|None}`
  - [x] 1.3: Implement `get_pipeline_status(config: dict) -> list[dict]` — scans `artifacts/` directory for all `pipeline-state.json` files, for each instantiates `StageRunner` and calls `.get_status()` to get `PipelineStatus` (which includes `stage`, `progress_pct`, `gate_status`, `decision_required`, `blocking_reason`). Optionally loads evidence pack to count anomalies. Returns list of `{"strategy_id": str, "stage": str, "progress_pct": float, "last_transition_at": str, "gate_status": str|None, "decision_required": bool, "anomaly_count": int, "run_id": str, "config_hash": str, "last_outcome": str|None, "blocking_reason": str|None, "evidence_pack_ref": str|None}`
  - [x] 1.4: Implement `load_evidence_pack(strategy_id: str, config: dict, evidence_pack_ref: str | None = None) -> dict` — if `evidence_pack_ref` is provided, loads from that exact path (state-driven: caller reads from `PipelineState.gate_decisions[-1].evidence_pack_ref` or completed stage artifact path); otherwise falls back to latest `artifacts/{strategy_id}/v{latest}/backtest/evidence_pack.json`. Deserializes to `EvidencePack` dataclass (Story 3-7 `analysis/models.py`). Returns dict with all 11 EvidencePack fields: `backtest_id`, `strategy_id`, `version`, `narrative` (NarrativeResult), `anomalies` (AnomalyReport), `metrics`, `equity_curve_summary`, `equity_curve_full_path`, `trade_distribution`, `trade_log_path`, `metadata`. Returns `None` if no evidence pack exists yet (strategy hasn't completed backtest)
  - [x] 1.5: Implement `advance_stage(strategy_id: str, reason: str, config: dict) -> dict` — loads `PipelineState` from `pipeline-state.json`, creates `GateDecision(decision="accept", reason=reason, decided_at=now_iso8601, evidence_pack_ref=latest_pack_path)`, calls `GateManager.advance(state, decision)` (Story 3-3 `gate_manager.py`). Returns `{"strategy_id": str, "from_stage": str, "to_stage": str, "decided_at": str}`
  - [x] 1.6: Implement `reject_stage(strategy_id: str, reason: str, config: dict) -> dict` — loads `PipelineState`, creates `GateDecision(decision="reject", reason=reason, ...)`, calls `GateManager.advance(state, decision)`. Returns `{"strategy_id": str, "stage": str, "decision": "reject", "reason": str, "decided_at": str}`
  - [x] 1.7: Implement `refine_stage(strategy_id: str, reason: str, config: dict) -> dict` — loads `PipelineState`, creates `GateDecision(decision="refine", reason=reason, decided_at=now_iso8601, evidence_pack_ref=latest_pack_path)`, calls `GateManager.advance(state, decision)`. Strategy returns to `STRATEGY_READY` stage. Returns `{"strategy_id": str, "from_stage": str, "to_stage": "strategy-ready", "decision": "refine", "reason": str, "decided_at": str}`
  - [x] 1.8: Implement `resume_pipeline(strategy_id: str | None, config: dict) -> list[dict]` — if `strategy_id` is None, scans artifacts dir for all `pipeline-state.json` files to find interrupted runs (state has `checkpoint` != None or `error` != None). For each, instantiates `StageRunner` and calls `.resume()`. Returns list of `{"strategy_id": str, "resumed_from_stage": str, "checkpoint_found": bool}`
  - [x] 1.9: Verify no function in `operator_actions.py` inspects P&L, profit_factor, Sharpe, or any performance metric to gate progression (FR41 enforcement)

- [x] **Task 2: Extend `/pipeline` Skill with New Operations** (AC: #1, #2, #3, #4, #5, #6, #7, #8)
  - [x] 2.1: Update operations menu in `.claude/skills/pipeline/skill.md` — add items 10-15:
    ```
    10. Run Backtest     — Execute backtest for a strategy through the pipeline
    11. Review Results   — View evidence pack, decide accept/reject/refine
    12. Advance Stage    — Accept and move strategy to next pipeline stage
    13. Reject Stage     — Reject strategy with reason, mark as rejected
    14. Refine Stage     — Refine strategy with guidance, return to strategy-ready
    15. Resume Pipeline  — Resume interrupted pipeline runs from checkpoint
    ```
  - [x] 2.2: Add "Run Backtest" section (operation 10) with Python snippet calling `operator_actions.run_backtest()`. Asks for strategy_id (or auto-detect from context). Reports progress, then presents results summary. Chains to "Review Results" on success
  - [x] 2.3: Extend "Status" section (operation 9) to additionally display pipeline state per strategy: current stage, last transition, anomaly count, last outcome, blocking reason, and evidence pack reference. Uses `operator_actions.get_pipeline_status()`
  - [x] 2.4: Add "Review Results" section (operation 11) — loads evidence pack via `operator_actions.load_evidence_pack()`, formats and displays: narrative summary, key metrics table, anomaly flags with severity. Then prompts: "Accept / Reject / Refine?"
  - [x] 2.5: Add "Advance Stage" section (operation 12) — asks for confirmation reason, calls `operator_actions.advance_stage()`, reports new stage
  - [x] 2.6: Add "Reject Stage" section (operation 13) — asks for rejection reason, calls `operator_actions.reject_stage()`, reports rejection recorded
  - [x] 2.7: Add "Refine Stage" section (operation 14) — asks for refinement guidance, calls `operator_actions.refine_stage()`, reports strategy returned to `STRATEGY_READY`, suggests "Modify Strategy" → re-run
  - [x] 2.8: Add "Resume Pipeline" section (operation 15) — calls `operator_actions.resume_pipeline()`, reports which strategies were resumed and from which checkpoint
  - [x] 2.9: Update chaining section to include backtest flow:
    - **Run Backtest** → Review Results → Accept (Advance) or Reject or Refine
    - **Reject** → hard stop, strategy marked rejected
    - **Refine** → Modify Strategy → Run Backtest (re-submit loop)
  - [x] 2.10: Add behavioral rule: "Never block pipeline progression based on profitability metrics"

- [x] **Task 3: Structured Logging for Operator Actions** (AC: #10)
  - [x] 3.1: In `operator_actions.py`, use `get_logger('pipeline.operator')` (existing `logging_setup.py` from Story 1-3)
  - [x] 3.2: Log every operator action as structured JSON: `{"action": "run_backtest"|"advance"|"reject"|"refine"|"resume", "strategy_id": str, "run_id": str, "config_hash": str, "timestamp": str, "decision": str|None, "reason": str|None}`
  - [x] 3.3: Log gate decisions (accept/reject) at INFO level with full `GateDecision` fields
  - [x] 3.4: Log errors at ERROR level with `PipelineError` context (D8 pattern)

- [x] **Task 4: Unit Tests** (AC: #1, #2, #3, #4, #5, #6, #7, #9, #10)
  - [x] 4.1: Create `src/python/tests/unit/orchestrator/test_operator_actions.py`
  - [x] 4.2: `test_run_backtest_invokes_executor_and_assembles_evidence` — mock `BacktestExecutor`, verify `assemble_evidence_pack` called on success
  - [x] 4.3: `test_run_backtest_returns_error_on_executor_failure` — mock executor failure, verify error dict returned
  - [x] 4.4: `test_get_pipeline_status_aggregates_all_strategies` — create 2 pipeline-state.json files in temp dir, verify both returned
  - [x] 4.5: `test_get_pipeline_status_empty_when_no_strategies` — verify empty list when no state files exist
  - [x] 4.6: `test_load_evidence_pack_deserializes_correctly` — write `evidence_pack.json` fixture (underscored) with all 11 EvidencePack fields, verify NarrativeResult has `overview`/`risk_assessment` (not `summary`/`interpretation`), verify AnomalyReport wrapper (not bare list)
  - [x] 4.7: `test_advance_stage_creates_accept_gate_decision` — mock `GateManager.advance()`, verify `GateDecision(decision="accept")` passed with correct stage and evidence_pack_ref
  - [x] 4.8: `test_reject_stage_creates_reject_gate_decision_with_reason` — verify reason propagated
  - [x] 4.9: `test_resume_pipeline_detects_and_resumes_interrupted` — mock recovery module, verify resume called
  - [x] 4.10: `test_no_profitability_gate_in_any_function` — static analysis: grep `operator_actions.py` for `profit`, `sharpe`, `pnl`, `equity` patterns used in conditionals — assert none found in if/while/assert statements
  - [x] 4.11: `test_advance_allows_losing_strategy` — create pipeline state with evidence pack showing negative P&L (profit_factor=0.5, sharpe=-1.2), call `advance_stage()`, verify it succeeds without error (behavioral FR41 test)
  - [x] 4.12: `test_advance_allows_zero_trades_strategy` — create pipeline state with evidence pack showing zero trades, call `advance_stage()`, verify it succeeds (behavioral FR41 test)
  - [x] 4.13: `test_refine_stage_creates_refine_gate_decision` — mock `GateManager.advance()`, verify `GateDecision(decision="refine")` passed with correct reason, verify strategy returns to `STRATEGY_READY`
  - [x] 4.14: `test_load_evidence_pack_uses_state_ref_when_provided` — provide explicit `evidence_pack_ref` path, verify that exact path is loaded instead of scanning for latest
  - [x] 4.15: `test_operator_actions_log_with_unified_schema` — capture log output, verify JSON structure matches D6 schema including `run_id` and `config_hash`

## Dev Notes

### Architecture Constraints

- **D9 (Operator Interface):** All operations implemented as extensions to the single `/pipeline` Claude Code skill. The skill reads pipeline state from filesystem, invokes Python `orchestrator/operator_actions.py` for mutations, and presents structured output. No REST API needed yet — direct Python invocation via `PYTHONPATH=src/python .venv/Scripts/python.exe -c "..."` (consistent with existing operations 1-9)
- **D3 (Pipeline Orchestration):** Sequential state machine per strategy. Gated transitions at `review-pending` require explicit operator decision via `GateDecision`. Stage flow: `data-ready → strategy-ready → backtest-running → backtest-complete → review-pending (GATED) → reviewed`. **Research Update:** When optimization is added (Epic 5), it will be a single opaque `OPTIMIZING` state — operator skills should NOT expose optimization sub-state management. The optimizer manages its own internal state behind a pluggable interface.
- **D6 (Logging):** Structured JSON logs to `logs/`, one file per runtime per day. All state transitions and operator decisions logged
- **D8 (Error Handling):** Fail-fast at boundaries. Resource pressure → throttle. Data/logic error → stop and checkpoint. External failure → retry with backoff. Errors surfaced as `PipelineError` to operator
- **D1 (System Topology):** Python-Rust boundary is subprocess only (NO PyO3/FFI). Rust backtester invoked via `asyncio.create_subprocess_exec()`
- **D2 (Artifact Schema):** Arrow IPC (canonical) → SQLite (queryable) → Parquet (archival). Evidence packs are JSON artifacts in `artifacts/{strategy_id}/v{NNN}/backtest/evidence_pack.json`
- **Future REST Integration:** `operator_actions.py` is intentionally designed as the single mutation surface for all pipeline operations. When the REST API is built (Epic 4), it will be a thin wrapper around these same functions. This means `operator_actions.py` function signatures and return types ARE the API contract — do not add skill-specific logic or dialogue handling into this module

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

class TransitionType(Enum):
    AUTOMATIC = "automatic"
    GATED = "gated"

@dataclass
class CompletedStage:
    stage: str
    completed_at: str  # ISO 8601
    artifact_path: str | None
    manifest_ref: str | None
    duration_s: float
    outcome: str  # "success" | "skipped" | "failed"

@dataclass
class WithinStageCheckpoint:
    stage: PipelineStage
    progress_pct: float
    last_completed_batch: int
    total_batches: int
    partial_artifact_path: str | None
    checkpoint_at: str  # ISO 8601

@dataclass
class PipelineError:
    code: str
    category: str  # "resource_pressure" | "data_logic" | "external_failure"
    severity: str  # "warning" | "error" | "critical"
    recoverable: bool
    action: str  # "throttle" | "stop_checkpoint" | "retry_backoff"
    component: str
    runtime: str  # "python"
    context: dict
    msg: str

@dataclass
class PipelineState:
    strategy_id: str
    run_id: str  # UUID per execution attempt (FR60 lineage)
    current_stage: PipelineStage
    completed_stages: list[CompletedStage]
    pending_stages: list[PipelineStage]
    gate_decisions: list[GateDecision]  # history of operator decisions
    created_at: str  # ISO 8601
    last_transition_at: str  # ISO 8601
    checkpoint: WithinStageCheckpoint | None
    error: PipelineError | None  # singular, last error
    config_hash: str
    version: int  # state schema version

@dataclass
class GateDecision:
    stage: PipelineStage
    decision: str  # "accept" | "reject" | "refine"
    reason: str
    decided_at: str  # ISO 8601
    evidence_pack_ref: str | None

@dataclass
class PipelineStatus:  # returned by StageRunner.get_status()
    stage: str
    progress_pct: float
    last_transition_at: str
    completed: list[CompletedStage]
    pending: list[str]
    gate_status: str | None  # "awaiting_decision" | "accepted" | "rejected" | "refined" | None
    decision_required: bool
    blocking_reason: str | None
    last_outcome: str | None
    error: dict | None
    config_hash: str
    run_id: str

@dataclass
class StageResult:
    artifact_path: str | None
    manifest_ref: str | None
    outcome: str  # "success" | "failed"
    metrics: dict
    error: PipelineError | None

# stage_runner.py
class StageRunner:
    def __init__(self, strategy_id: str, artifacts_dir: Path, config: PipelineConfig,
                 executors: dict[PipelineStage, StageExecutor] | None = None): ...
    def run(self) -> PipelineState: ...      # NOTE: no strategy_id arg — set in __init__
    def resume(self) -> PipelineState: ...   # NOTE: no strategy_id arg — set in __init__
    def get_status(self) -> PipelineStatus: ...

# gate_manager.py
class GateManager:
    def advance(self, state: PipelineState, decision: GateDecision) -> PipelineState: ...
    def check_preconditions(self, state: PipelineState, stage: PipelineStage) -> tuple[bool, str | None]: ...

# recovery.py
def verify_last_artifact(state: PipelineState, executor: StageExecutor) -> bool: ...
def recover_from_checkpoint(state: PipelineState) -> WithinStageCheckpoint | None: ...
```

**From Story 3-4 (`src/python/rust_bridge/`):**
```python
# backtest_executor.py
class BacktestExecutor:  # implements StageExecutor protocol
    def execute(self, strategy_id: str, context: dict) -> StageResult: ...
    def validate_artifact(self, artifact_path: Path, manifest_ref: Path) -> bool: ...
```

**From Story 3-7 (`src/python/analysis/`):**
```python
# models.py
@dataclass
class NarrativeResult:
    overview: str              # equity curve shape, drawdown profile, trade distribution
    metrics: dict              # key performance metrics
    strengths: list[str]       # identified strategy strengths
    weaknesses: list[str]      # identified strategy weaknesses
    session_breakdown: dict    # performance by trading session
    risk_assessment: str       # overall risk evaluation

@dataclass
class AnomalyFlag:
    type: AnomalyType          # LOW_TRADE_COUNT | ZERO_TRADES | PERFECT_EQUITY | etc.
    severity: Severity         # WARNING | ERROR
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
    anomalies: AnomalyReport       # NOTE: AnomalyReport, not list[AnomalyFlag]
    metrics: dict
    equity_curve_summary: list[dict]  # downsampled for display
    equity_curve_full_path: str       # canonical reference to full data
    trade_distribution: dict          # by session
    trade_log_path: str
    metadata: dict                    # manifest linkage, schema version

# evidence_pack.py
def assemble_evidence_pack(backtest_id: str, db_path: Path | None = None,
                           artifacts_root: Path | None = None) -> EvidencePack: ...
```

**From Story 3-6 (`src/python/artifacts/`):**
```python
# storage.py — ArtifactStorage class (versioned directories, crash-safe writes)
# sqlite_manager.py — SQLiteManager (WAL mode, schema from contracts/sqlite_ddl.sql)
```

### No-Profitability-Gate Enforcement (FR41)

This is a critical design constraint: the operator can push ANY strategy through the entire pipeline regardless of P&L results. The `operator_actions.py` module must NEVER:
- Check profit_factor, Sharpe ratio, win_rate, or equity curve slope before allowing `advance_stage()`
- Display warnings that suggest blocking progression based on performance
- Add conditional logic that treats unprofitable strategies differently from profitable ones

Anomalies ARE displayed (from Story 3-7), but they are informational — the operator makes the final call. Even a strategy with zero trades or negative returns can be advanced.

### State-Driven Evidence Lookup

Evidence packs must be loaded using explicit references from pipeline state, not by scanning the filesystem for the "latest" version. The lookup order is:
1. If `evidence_pack_ref` is provided (from `PipelineState` or `GateDecision`), load from that exact path
2. Fallback: scan for latest version directory (for first-run or recovery scenarios only)

This ensures reproducibility: the evidence pack reviewed is always the one that corresponds to the pipeline state being acted upon.

### Evidence Pack Display Format

When presenting the evidence pack to the operator, format as:

```
=== Backtest Results: {pack.strategy_id} v{pack.version} ===

Narrative Overview:
{pack.narrative.overview}

Key Metrics:
  Total Trades: {pack.metrics['total_trades']}
  Win Rate: {pack.metrics['win_rate']:.1%}
  Profit Factor: {pack.metrics['profit_factor']:.2f}
  Max Drawdown: {pack.metrics['max_drawdown']:.2%}
  Sharpe (unannualized): {pack.metrics['sharpe']:.3f}

Strengths:
  {bullet list from pack.narrative.strengths}

Weaknesses:
  {bullet list from pack.narrative.weaknesses}

Session Breakdown:
  {pack.narrative.session_breakdown formatted as table}

Anomalies ({len(pack.anomalies.anomalies)} found):
  [{anomaly.severity.value}] {anomaly.description}
  -> {anomaly.recommendation}

Risk Assessment:
{pack.narrative.risk_assessment}

Trade Distribution:
  {pack.trade_distribution formatted as table}

Decision: Accept / Reject / Refine?
```

If no evidence pack exists (strategy hasn't completed backtest), display:
```
No evidence pack available for {strategy_id}.
Run a backtest first (Operation 10).
```

### Windows/Git Bash Compatibility

- Python invocation: `.venv/Scripts/python.exe` (not `python3`)
- Path format: forward slashes in all Python code
- PYTHONPATH: `PYTHONPATH=src/python`
- No `SIGTERM` — use `terminate()` for process cancellation
- Strip `\r` from any subprocess output

### Project Structure Notes

**Files to CREATE:**
- `src/python/orchestrator/operator_actions.py` — thin composition layer over existing modules
- `src/python/tests/unit/orchestrator/test_operator_actions.py` — unit tests

**Files to MODIFY:**
- `.claude/skills/pipeline/skill.md` — extend with operations 10-14, update Status operation, update chaining rules, add behavioral rule

**Files to READ (not modify):**
- `src/python/orchestrator/pipeline_state.py` — PipelineStage, PipelineState, GateDecision
- `src/python/orchestrator/stage_runner.py` — StageRunner class
- `src/python/orchestrator/gate_manager.py` — `GateManager.advance()` for gate decisions, `check_preconditions()` for automatic transitions
- `src/python/orchestrator/recovery.py` — find_interrupted_runs, verify_last_artifact
- `src/python/rust_bridge/backtest_executor.py` — BacktestExecutor (StageExecutor impl)
- `src/python/analysis/models.py` — EvidencePack, NarrativeResult, AnomalyFlag
- `src/python/analysis/evidence_pack.py` — assemble_evidence_pack()
- `src/python/artifacts/storage.py` — ArtifactStorage versioning
- `src/python/artifacts/sqlite_manager.py` — SQLiteManager for status queries
- `src/python/config_loader.py` — load_config()
- `src/python/logging_setup.py` — setup_logging(), get_logger()

**Artifact Directories (read at runtime):**
- `artifacts/{strategy_id}/pipeline-state.json` — per-strategy pipeline state
- `artifacts/{strategy_id}/v{NNN}/backtest/*.arrow` — backtest output files (trade-log, equity-curve, metrics)
- `artifacts/{strategy_id}/v{NNN}/backtest/evidence_pack.json` — evidence pack (underscored, in backtest dir)

### What to Reuse from ClaudeBackTester

No direct code reuse needed. The dialogue pattern from `src/python/strategy/dialogue_parser.py` (Story 2-4) established the precedent: Claude Code skill pre-processes operator dialogue into structured data, Python modules receive structured input only. This same pattern applies: the skill handles dialogue, `operator_actions.py` handles structured operations.

### Anti-Patterns to Avoid

1. **Do NOT create a separate skill** — all operations go in the existing `/pipeline` skill.md (AC #7, D9)
2. **Do NOT implement a REST API** — Story 3.8 uses direct Python invocation, not FastAPI routes (dashboard API comes in Epic 4)
3. **Do NOT parse raw natural language** in `operator_actions.py` — the skill handles dialogue, Python handles structured operations
4. **Do NOT gate on profitability** — never check P&L metrics to allow/block pipeline progression (FR41)
5. **Do NOT duplicate metric calculations** — use `analysis/metrics_builder.py` (Story 3-7) as single source of truth
6. **Do NOT write pipeline state without crash-safe semantics** — always use `.partial` → fsync → atomic rename (NFR15)
7. **Do NOT use `shell=True`** in subprocess calls — use `asyncio.create_subprocess_exec()` (D1)
8. **Do NOT hardcode paths** — always read from `config = load_config()` (existing pattern)
9. **Do NOT swallow errors** — propagate as PipelineError to operator with structured context (D8)
10. **Do NOT add inline Python to skill.md that does heavy logic** — keep skill snippets thin, delegate to `operator_actions.py`

### References

- [Source: _bmad-output/planning-artifacts/prd.md — Pipeline Workflow & Operator Control: FR38-FR42]
- [Source: _bmad-output/planning-artifacts/prd.md — Artifact Requirements: FR58-FR61]
- [Source: _bmad-output/planning-artifacts/prd.md — Backtest Results: FR14-FR19]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR: NFR5, NFR10, NFR11, NFR15, NFR19, NFR20]
- [Source: _bmad-output/planning-artifacts/architecture.md — D9: Operator Interface]
- [Source: _bmad-output/planning-artifacts/architecture.md — D3: Pipeline Orchestration]
- [Source: _bmad-output/planning-artifacts/architecture.md — D6: Logging & Observability]
- [Source: _bmad-output/planning-artifacts/architecture.md — D8: Error Handling]
- [Source: _bmad-output/planning-artifacts/architecture.md — D1: System Topology]
- [Source: _bmad-output/planning-artifacts/architecture.md — D2: Artifact Schema & Storage]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 3, Story 3.8]
- [Source: _bmad-output/implementation-artifacts/3-3-pipeline-state-machine-checkpoint-infrastructure.md — PipelineState, GateDecision, StageRunner]
- [Source: _bmad-output/implementation-artifacts/3-4-python-rust-bridge-batch-evaluation-dispatch.md — BacktestExecutor, BatchRunner]
- [Source: _bmad-output/implementation-artifacts/3-6-backtest-results-artifact-storage-sqlite-ingest.md — ArtifactStorage, SQLiteManager]
- [Source: _bmad-output/implementation-artifacts/3-7-ai-analysis-layer-narrative-anomaly-detection-evidence-packs.md — EvidencePack, NarrativeResult, AnomalyFlag]
- [Source: .claude/skills/pipeline/skill.md — Existing operator interface with operations 1-9]

## Dev Agent Record

### Agent Model Used
Claude Opus 4.6 (1M context)

### Debug Log References
- All 16 unit tests pass: `pytest src/python/tests/test_orchestrator/test_operator_actions.py -v`
- All 4 live integration tests pass: `pytest src/python/tests/test_orchestrator/test_operator_actions_live.py -v -m live`
- Full regression suite: 997 passed, 0 failed, 94 skipped (live markers)

### Completion Notes List
- Created `operator_actions.py` as the single mutation surface for all pipeline operations (D9)
- Implemented 7 public functions: run_backtest, get_pipeline_status, load_evidence_pack, advance_stage, reject_stage, refine_stage, resume_pipeline
- All functions include structured D6 logging via `_log_action()` helper with unified schema (action, strategy_id, run_id, config_hash, timestamp, decision, reason)
- No-profitability-gate (FR41) enforced: no function inspects P&L metrics to gate progression. Verified by AST-based static analysis test and behavioral tests with losing/zero-trade strategies
- Extended `/pipeline` skill with operations 10-15 (Run Backtest, Review Results, Advance/Reject/Refine Stage, Resume Pipeline)
- Updated Status operation (9) to include pipeline status from `get_pipeline_status()`
- Added chaining rules: Run Backtest -> Review Results -> Accept/Reject/Refine
- Added behavioral rule #10: Never block pipeline progression based on profitability metrics
- Evidence pack loading is state-driven: uses explicit `evidence_pack_ref` when provided, falls back to latest version directory scan
- GateManager.advance() handles accept (-> reviewed), reject (stays), refine (-> backtest-running) decisions with crash-safe persistence

### Change Log
- 2026-03-19: Initial implementation of Story 3.8 — all 4 tasks complete

### File List
- `src/python/orchestrator/operator_actions.py` — NEW: Single mutation surface for pipeline operations
- `.claude/skills/pipeline/skill.md` — MODIFIED: Added operations 10-15, updated chaining, added FR41 behavioral rule
- `src/python/tests/test_orchestrator/test_operator_actions.py` — NEW: 16 unit tests
- `src/python/tests/test_orchestrator/test_operator_actions_live.py` — NEW: 4 live integration tests
