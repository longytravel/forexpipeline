# Story 3-8 Review: Operator Pipeline Skills

**Reviewer:** Independent Quality Validator
**Date:** 2026-03-17
**Story:** 3-8-operator-pipeline-skills-dialogue-control-stage-management.md
**Verdict:** 4 critical issues must be fixed before dev

---

## CRITICAL ISSUES (must fix)

### C1: GateManager vs StageRunner — Wrong Class for Gate Decisions

Story 3-8 references `StageRunner.apply_gate_decision()` in Tasks 1.5, 1.6, and the integration contracts section. **This method does not exist on StageRunner.** Story 3-3 defines gate decisions on a separate `GateManager` class:

```python
# Story 3-3 ACTUAL interface:
class GateManager:
    def advance(self, state: PipelineState, decision: GateDecision) -> PipelineState: ...
    def check_preconditions(self, state: PipelineState, stage: PipelineStage) -> tuple[bool, str | None]: ...
```

**Fix — replace in Key Integration Contracts, From Story 3-3 section:**
```python
# REMOVE:
# stage_runner.py
class StageRunner:
    def run(self, strategy_id: str) -> StageResult: ...
    def resume(self, strategy_id: str) -> StageResult: ...
    def apply_gate_decision(self, strategy_id: str, decision: GateDecision) -> None: ...

# ADD:
# stage_runner.py
class StageRunner:
    def __init__(self, strategy_id: str, artifacts_dir: Path, config: PipelineConfig,
                 executors: dict[PipelineStage, StageExecutor] | None = None): ...
    def run(self) -> PipelineState: ...
    def resume(self) -> PipelineState: ...
    def get_status(self) -> PipelineStatus: ...

# gate_manager.py
class GateManager:
    def advance(self, state: PipelineState, decision: GateDecision) -> PipelineState: ...
    def check_preconditions(self, state: PipelineState, stage: PipelineStage) -> tuple[bool, str | None]: ...
```

**Fix — update Tasks 1.5 and 1.6:**
- Task 1.5: Change "calls `StageRunner.apply_gate_decision()`" to "loads `PipelineState` from filesystem, calls `GateManager().advance(state, decision)`, saves updated state"
- Task 1.6: Same change — use `GateManager().advance()` not `StageRunner.apply_gate_decision()`

**Fix — update Task 1.7:**
- Change `StageRunner.resume()` signature. Story 3-3's actual `resume()` takes no args (strategy_id set at `__init__`). Change "calls `StageRunner.resume()`" to "creates `StageRunner(strategy_id, ...)` then calls `.resume()`"

### C2: Evidence Pack Path Mismatch — Wrong Directory and Filename

Story 3-8 Task 1.4 reads from `artifacts/{strategy_id}/v{latest}/analysis/evidence-pack.json` (hyphenated, `/analysis/` subdir). Story 3-7 actually saves to `artifacts/{strategy_id}/v{NNN}/backtest/evidence_pack.json` (underscored, `/backtest/` subdir). Dev agent will get FileNotFoundError.

**Fix — Task 1.4:**
Replace: `artifacts/{strategy_id}/v{latest}/analysis/evidence-pack.json`
With: `artifacts/{strategy_id}/v{latest}/backtest/evidence_pack.json`

**Fix — Dev Notes → D2 reference:**
Replace: `artifacts/{strategy_id}/v{NNN}/analysis/evidence-pack.json`
With: `artifacts/{strategy_id}/v{NNN}/backtest/evidence_pack.json`

**Fix — Artifact Directories section:**
Replace: `artifacts/{strategy_id}/v{NNN}/analysis/evidence-pack.json — evidence pack`
With: `artifacts/{strategy_id}/v{NNN}/backtest/evidence_pack.json — evidence pack`

### C3: EvidencePack Dataclass Contract Mismatch

Story 3-8 documents `EvidencePack` with fields `{backtest_id, narrative, anomalies, artifacts, assembled_at}`. Story 3-7's actual definition is significantly different:

```python
# Story 3-7 ACTUAL:
@dataclass
class EvidencePack:
    backtest_id: str
    strategy_id: str           # MISSING from 3-8
    version: str               # MISSING from 3-8
    narrative: NarrativeResult
    anomalies: AnomalyReport   # Not list[AnomalyFlag] as 3-8 implies
    metrics: dict              # MISSING from 3-8
    equity_curve_summary: list[dict]   # MISSING from 3-8
    equity_curve_full_path: str        # MISSING from 3-8
    trade_distribution: dict           # MISSING from 3-8
    trade_log_path: str                # MISSING from 3-8
    metadata: dict                     # MISSING from 3-8
```

Also `NarrativeResult` in Story 3-7 has fields `(overview, metrics, strengths, weaknesses, session_breakdown, risk_assessment)` — NOT `(summary, key_metrics, interpretation)` as Story 3-8's contract and display template claim.

**Fix — replace the EvidencePack contract in Key Integration Contracts:**
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
    type: AnomalyType
    severity: Severity
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
    anomalies: AnomalyReport
    metrics: dict
    equity_curve_summary: list[dict]
    equity_curve_full_path: str
    trade_distribution: dict
    trade_log_path: str
    metadata: dict

# evidence_pack.py
def assemble_evidence_pack(backtest_id: str, db_path: Path | None = None, artifacts_root: Path | None = None) -> EvidencePack: ...
```

**Fix — update Evidence Pack Display Format template:**
Replace `{narrative.summary}` with `{narrative.overview}`
Replace `{narrative.interpretation}` with `{narrative.risk_assessment}`
Replace `{metrics.total_trades}` etc with `{pack.metrics['total_trades']}` (metrics is a dict on EvidencePack, not on narrative)
Replace `{len(anomalies)}` with `{len(pack.anomalies.anomalies)}`

### C4: PipelineState Contract Mismatch

Story 3-8 documents `PipelineState` with `transition_timestamps: dict[str, str]` and `errors: list[PipelineError]`. Story 3-3's actual definition has different fields:

```python
# Story 3-3 ACTUAL:
@dataclass
class PipelineState:
    strategy_id: str
    run_id: str
    current_stage: PipelineStage
    completed_stages: list[CompletedStage]
    pending_stages: list[PipelineStage]
    gate_decisions: list[GateDecision]    # NOT transition_timestamps
    created_at: str                        # NEW
    last_transition_at: str                # single str, NOT dict
    checkpoint: WithinStageCheckpoint | None  # NEW
    error: PipelineError | None            # SINGULAR, not list
    config_hash: str
```

**Fix — replace the PipelineState dataclass in Key Integration Contracts:**
```python
@dataclass
class PipelineState:
    strategy_id: str
    run_id: str
    current_stage: PipelineStage
    completed_stages: list[CompletedStage]
    pending_stages: list[PipelineStage]
    gate_decisions: list[GateDecision]
    created_at: str
    last_transition_at: str
    checkpoint: WithinStageCheckpoint | None
    error: PipelineError | None
    config_hash: str
```

**Fix — Task 1.3 (`get_pipeline_status`):** Update the return dict to source `last_transition` from `state.last_transition_at` (not `transition_timestamps`).

---

## ENHANCEMENTS (should add)

### E1: Missing `PipelineStatus` Contract

Story 3-3 defines a `PipelineStatus` dataclass returned by `StageRunner.get_status()` with fields: `stage, progress_pct, gate_status, decision_required, blocking_reason, anomaly_count, last_outcome, error, config_hash, run_id`. Task 1.3 (`get_pipeline_status`) should use this existing method rather than manually scanning pipeline-state.json files.

**Suggested addition to Task 1.3:** "Use `StageRunner(strategy_id, ...).get_status() -> PipelineStatus` to get structured status per strategy instead of manually parsing pipeline-state.json."

### E2: Missing `gate_manager.py` in "Files to READ" List

Story 3-8's Project Structure Notes lists `gate_manager.py` in "Files to READ" but it is not in the Integration Contracts section. Since C1 requires using `GateManager`, add `gate_manager.py` to the integration contracts with its interface.

### E3: Task 1.4 `load_evidence_pack` Should Use `EvidencePack.from_json()`

Story 3-7 specifies `to_json()` / `from_json()` serialization on each dataclass. Task 1.4 should explicitly state: "Deserialize using `EvidencePack.from_json(json_data)`" rather than ad-hoc dict parsing.

### E4: Missing `StageResult` Dataclass in Contracts

`BacktestExecutor.execute()` returns `StageResult` and `StageRunner.run()/resume()` return `PipelineState`, but `StageResult` is never defined in the contracts section. The dev agent won't know its structure.

**Add to Integration Contracts, From Story 3-3:**
```python
@dataclass
class StageResult:
    stage: PipelineStage
    outcome: str  # "success" | "skipped" | "failed"
    output_refs: dict[str, str]  # artifact paths produced
    error: PipelineError | None
    started_at: str
    completed_at: str
```

### E5: Missing Error Handling for "Evidence Pack Unavailable"

Story 3-7 Task 5 explicitly states: "If evidence pack fails: set `evidence_pack_available: false` in pipeline state metadata so Story 3.8 can surface this to the operator." Story 3-8 never handles this case. Task 1.4 (`load_evidence_pack`) and Task 2.4 ("Review Results" skill section) should handle the case where evidence_pack_available is false.

**Add to Task 1.4:** "If `evidence_pack_available` is `false` in pipeline state metadata, return `{"status": "unavailable", "reason": "Evidence pack generation failed — inspect raw artifacts or re-trigger analysis"}` instead of raising FileNotFoundError."

### E6: `assemble_evidence_pack` Signature Has Extra Parameters

Story 3-8 Task 1.2 calls `assemble_evidence_pack()` but Story 3-7's actual signature is `assemble_evidence_pack(backtest_id: str, db_path: Path | None = None, artifacts_root: Path | None = None)`. Task 1.2 should document passing `db_path` and `artifacts_root` from config.

---

## OPTIMIZATIONS (nice to have)

### O1: Existing Skill Operation Numbering

The current skill.md has 9 operations. Task 2.1 adds operations 10-14. Verify no other story between 3-3 and 3-7 already added operations to the skill — if so, the numbering may conflict. Current skill.md shows exactly 9, so 10-14 is correct.

### O2: Display Template Uses Emojis

The Evidence Pack Display Format uses emoji characters. Per the existing skill.md behavioral rules, this is fine for operator-facing output, but worth noting for consistency.

### O3: Test Task 4.10 Static Analysis Approach

The `test_no_profitability_gate_in_any_function` test uses grep-based static analysis. This is brittle — consider also adding a runtime test that calls `advance_stage()` with a strategy that has negative P&L and verifies it succeeds without error.

### O4: `run_backtest` Missing Strategy Spec Loading

Task 1.2 says "loads strategy spec + cost model from `artifacts/`" but doesn't specify which module/function to use for loading. Should reference the strategy loading infrastructure from Epic 2 (e.g., `strategy.intent_capture` or direct TOML loading from `artifacts/strategies/{slug}/v{NNN}.toml`).

---

## Section Completeness Checklist

| Section | Present | Quality |
|---------|---------|---------|
| Story (user story format) | YES | Good — matches epics |
| Acceptance Criteria | YES | Good — 9 ACs match epics exactly, FR/D refs present |
| Tasks / Subtasks | YES | Good — detailed with AC mapping on each task |
| Dev Notes | YES | Good — architecture constraints, integration contracts |
| Project Structure Notes | YES | Good — files to create/modify/read specified |
| References | YES | Good — comprehensive with source links |
| Anti-Patterns | YES | Good — 10 numbered items |
| What to Reuse | YES | Good — ClaudeBackTester dialogue pattern noted |
| Dev Agent Record | YES | Present (empty, as expected for ready-for-dev) |
| AC → Task traceability | YES | Every AC maps to tasks; every task references ACs |
| Function signatures with types | YES | All functions have param types and return types |
| File paths | YES | Exact paths for create/modify/read |
| Test method names | YES | 11 specific test names |
| Architecture decision refs | YES | D1, D2, D3, D6, D8, D9 referenced |
| FR references | YES | FR38-FR42 referenced |

---

## Summary

**4 Critical, 6 Enhancements, 4 Optimizations**

The story is well-structured and comprehensive, but has **dangerous integration contract mismatches** with upstream stories (3-3 and 3-7) that would cause the dev agent to write code against wrong interfaces. The critical issues are all about incorrect class/method/field names that will produce runtime errors. Fix those four and this story is ready for dev.
