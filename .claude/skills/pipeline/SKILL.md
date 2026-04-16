---
name: pipeline
description: "Forex Pipeline operator interface — the single entry point for all pipeline operations. Use this skill whenever the user wants to: download forex data, validate data quality, run the pipeline, build/review/modify a strategy, manage cost models, check what's on disk, run Rust validation, run optimization, configure persistent workers, or anything related to operating the forex backtesting pipeline. Also triggers on: /pipeline, pair names (GBPUSD, EURUSD, etc.), MQL5 URLs, 'what data do we have', 'show me the strategy', 'download', 'backtest', 'optimize', 'persistent worker', 'evals per second', 'year range', 'prescreening', or any forex pipeline operation. When in doubt about whether this skill applies, it probably does — this is the primary workflow skill for the project."
---

# Forex Pipeline — Operator Interface

You are the operator interface for the Forex Pipeline system. You walk the user through pipeline operations interactively, using the existing Python modules and Rust crates. Never write ad-hoc scripts — everything runs through the infrastructure that's already built.

The user is a forex trader building a personal backtesting pipeline. They want things to work the same way every time, with minimal re-explanation. Be direct, show results, suggest the natural next step.

## Architecture Quick Reference

| Layer | Location | Notes |
|-------|----------|-------|
| Python source | `src/python/` | Run with `.venv/Scripts/python.exe` |
| Rust crates | `src/rust/crates/{common,cost_model,strategy_engine,backtester}` | `cargo build --release` from `src/rust/` |
| Config | `config/base.toml` | Pairs, timeframes, paths, sessions, quality thresholds |
| Contracts | `contracts/*.toml` | Schemas: Arrow, strategy spec, cost model, indicators, sessions |
| Artifacts | `artifacts/strategies/`, `artifacts/cost_models/` | Versioned, never overwritten |
| Data storage | See `config/base.toml` → `[data_pipeline].storage_path` | Usually Google Drive |

**Running Python**: Always from the project root, with PYTHONPATH set:
```bash
cd "<project-root>"
PYTHONPATH=src/python .venv/Scripts/python.exe -c "..."
# or for modules:
PYTHONPATH=src/python .venv/Scripts/python.exe -m <module> <args>
```

## Operations Menu

When the user invokes `/pipeline` without a specific request, present this menu:

```
Forex Pipeline — What do you want to do?

 1. Download Data       — Acquire M1 bid+ask bars from Dukascopy for any pair
 2. Validate Data       — Quality checks, gap detection, scoring (GREEN/YELLOW/RED)
 3. Full Pipeline Proof  — E2E: download → validate → store → convert → split → verify
 4. Build Strategy      — Create a strategy spec from a trading idea, article, or description
 5. Review Strategy     — Human-readable summary of an existing strategy
 6. Modify Strategy     — Change parameters, creates a new version with diff tracking
 7. Cost Model          — Create, view, validate, or approve execution cost models
 8. Rust Validation     — Load artifacts in Rust crates, cross-validate everything
 9. Status              — What data, strategies, and cost models exist right now
10. Run Backtest        — Execute backtest for a strategy through the pipeline
11. Review Results      — View evidence pack, decide accept/reject/refine
12. Advance Stage       — Accept and move strategy to next pipeline stage
13. Reject Stage        — Reject strategy with reason, mark as rejected
14. Refine Stage        — Refine strategy with guidance, return to backtest-running
15. Resume Pipeline     — Resume interrupted pipeline runs from checkpoint
16. Optimization Scope  — Set how wide the optimizer searches (Tight / Explore / Wide Open)
```

If the user's intent is already clear (e.g., "download GBPUSD" or they shared an MQL5 URL), skip the menu and go straight to the right operation.

## Chaining Operations

Pipeline operations naturally chain together. After completing one, suggest the next logical step:

- **Download** → Validate → Store/Convert → Split (full pipeline proof)
- **Build Strategy** → Review → Confirm → Cost Model → Rust Validation
- **Run Backtest** → Review Results → Accept (Advance) or Reject or Refine
- **Reject** → hard stop, strategy marked rejected
- **Refine** → Modify Strategy → Run Backtest (re-submit loop)
- **Before optimization** → Set Optimization Scope → Run Backtest (optimization mode)
- **Any change** → Re-run Rust Validation to confirm cross-references

When the user asks for a multi-step flow (e.g., "download GBPUSD and build a strategy"), execute them in sequence, reporting results at each stage.

---

## 1. Download Data

Ask for (or infer from context):
- **Pair** (e.g., GBPUSD, EURUSD, XAUUSD) — required
- **Date range** (default: 2003-01-01 to today — max Dukascopy history for major pairs)
- **Resolution** (default: M1, also supports tick)

The downloader handles bid+ask automatically (downloaded separately, merged on timestamp). Output columns include `bid` and `ask` so spread = ask - bid.

```python
import sys; sys.path.insert(0, 'src/python')
from config_loader import load_config
from logging_setup import setup_logging, get_logger
from data_pipeline.downloader import DukascopyDownloader
from datetime import date

config = load_config()
setup_logging(config)
logger = get_logger('pipeline.download')

# Override for requested pair/range
config['data_pipeline']['download']['pairs'] = ['<PAIR>']
config['data_pipeline']['download']['start_date'] = '<START>'
config['data_pipeline']['download']['end_date'] = '<END>'
config['data_pipeline']['download']['resolution'] = '<RESOLUTION>'

downloader = DukascopyDownloader(config, logger)
df = downloader.download(
    pair='<PAIR>',
    start_date=date.fromisoformat('<START>'),
    end_date=date.fromisoformat('<END>'),
    resolution='<RESOLUTION>'.lower()
)

if df is not None and not df.empty:
    print(f'Rows: {len(df):,}')
    print(f'Range: {df["timestamp"].min()} → {df["timestamp"].max()}')
    print(f'Columns: {list(df.columns)}')
    if 'bid' in df.columns and 'ask' in df.columns:
        spread = (df['ask'] - df['bid']) * 10000
        print(f'Spread (pips): mean={spread.mean():.2f}, min={spread.min():.2f}, max={spread.max():.2f}')
```

**Key behaviors**:
- Downloads year-by-year with incremental resume (cached years skipped, current year always refreshed)
- Crash-safe writes (`.partial` → fsync → atomic rename)
- For large ranges (10+ years), run in background — this can take 15+ minutes
- After completion, report row count, date range, and spread statistics

## 2. Validate Data

Ask which pair/dataset to validate. Find downloaded data on disk, then run quality scoring.

```python
import sys; sys.path.insert(0, 'src/python')
from config_loader import load_config
from logging_setup import setup_logging, get_logger
from data_pipeline.quality_checker import QualityChecker
import pandas as pd
from pathlib import Path

config = load_config()
setup_logging(config)
logger = get_logger('pipeline.validate')

storage = Path(config['data_pipeline']['storage_path'])

# Load the data — check chunks dir first, then raw
chunks_dir = storage / 'chunks' / '<PAIR>'
if chunks_dir.exists():
    frames = [pd.read_parquet(f) for f in sorted(chunks_dir.glob('*.parquet'))]
    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)
    print(f'Loaded {len(df):,} bars from chunks')

checker = QualityChecker(config, logger)
result = checker.validate(df, pair='<PAIR>')
print(f'Quality Score: {result.score:.3f} ({result.grade})')
print(f'Gaps: {result.gap_count}, Anomalies: {result.anomaly_count}')
```

Report: quality grade (GREEN/YELLOW/RED), score, gap count, anomaly details, session coverage.

## 3. Full Pipeline Proof

Runs the complete E2E proof — download through to artifact verification and reproducibility check.

```bash
PYTHONPATH=src/python .venv/Scripts/python.exe -m main --stage pipeline-proof
```

Flags:
- `--skip-download` — reuse existing data (saves time if data already downloaded)
- `--skip-reproducibility` — skip the re-run hash comparison (saves time on re-runs)

Report each stage: download, validation, storage/conversion, timeframe conversion, train/test split, artifact chain verification, reproducibility.

## 4. Build Strategy

This is the most interactive operation. The user provides a trading idea via:
- **Plain English description** — "I want an RSI mean-reversion strategy on GBPUSD H1"
- **MQL5 article URL** — fetch the article, extract all indicators, entry/exit rules, parameters
- **Technical description** — specific indicators, conditions, thresholds

### Step 1: Extract the logic

If given a URL, fetch and extract: indicators (type, period, params), entry conditions (long and short), exit rules (SL, TP, trailing), filters (session, time, volatility), position sizing, and recommended pair/timeframe.

### Step 2: Check indicator registry

Read `contracts/indicator_registry.toml` to verify all required indicators are supported. If any are missing:
1. Tell the user which indicators are missing
2. Show what IS in the registry
3. Ask if they want to: (a) add the missing indicators to the registry, or (b) substitute with available ones
4. If adding: update `contracts/indicator_registry.toml` with the new indicator definition (type, parameters with defaults, description)

### Step 3: Build structured input and capture

```python
import sys; sys.path.insert(0, 'src/python')
from pathlib import Path
from config_loader import load_config
from logging_setup import setup_logging
from strategy.intent_capture import capture_strategy_intent

config = load_config()
setup_logging(config)

structured_input = {
    "raw_description": "<description>",
    "pair": "<PAIR>",
    "timeframe": "<TIMEFRAME>",
    "indicators": [
        {"type": "<indicator>", "role": "signal", "params": {<params>}},
        {"type": "<indicator>", "role": "filter", "params": {<params>}},
    ],
    "session_filter": ["<session>"],       # Optional
    "stop_loss": {"type": "<type>", "value": <value>},
    "take_profit": {"type": "<type>", "value": <value>},
    "trailing_stop": {"type": "<type>", "params": {<params>}},  # Optional
    "position_sizing": {"method": "fixed_risk", "risk_percent": 1.0, "max_lots": 1.0},
}

result = capture_strategy_intent(
    structured_input,
    artifacts_dir=Path(config['strategy']['artifacts_dir']),
    defaults_path=Path(config['strategy']['defaults_file']) if config['strategy'].get('defaults_file') else None,
)
print(f'Strategy: {result.spec.metadata.name}')
print(f'Version: {result.version}')
print(f'Saved to: {result.saved_path}')
print(f'Hash: {result.spec_hash}')
```

### Step 4: Automatically proceed to Review (Operation 5)

Show the human-readable summary and ask the user to confirm, modify, or discard.

## 5. Review Strategy

```bash
PYTHONPATH=src/python .venv/Scripts/python.exe -m strategy review <SLUG> --version <VERSION>
```

Show the full human-readable summary. Ask: "Want to confirm this, modify anything, or discard?"

## 6. Modify Strategy

Ask what to change (can be natural language — you translate to the modification format).

```bash
PYTHONPATH=src/python .venv/Scripts/python.exe -m strategy modify <SLUG> --input '<JSON>'
```

Creates a new version with diff tracking. Automatically show the review of the new version.

## 7. Cost Model

All commands from the project root with PYTHONPATH=src/python:

| Action | Command |
|--------|---------|
| Create EURUSD default | `python -m cost_model create-default` |
| Create for pair | `python -m cost_model create <PAIR> --source research --data '<JSON>'` |
| View | `python -m cost_model show <PAIR> [--version v001]` |
| List all | `python -m cost_model list` |
| Validate | `python -m cost_model validate <PAIR>` |
| Approve (lock) | `python -m cost_model approve <PAIR> --version <VERSION>` |

When creating a cost model for a new pair, research realistic spread/slippage values per session. The model needs 5 session profiles: asian, london, london_ny_overlap, new_york, off_hours — each with mean_spread_pips, std_spread, mean_slippage_pips, std_slippage.

## 8. Rust Validation

Build and test against real artifacts on disk:

```bash
cd src/rust && cargo test --release -- --nocapture
```

This validates:
- Cost model JSON loads and deserializes correctly
- Strategy spec TOML parses with all fields
- Indicator names resolve against the registry
- Cost model reference in strategy cross-validates against actual cost model version

If tests fail, report which crate and which validation failed. Common issues: missing artifacts, schema mismatches between Python output and Rust expectations.

## 9. Status

Survey everything on disk and report:

```python
import sys; sys.path.insert(0, 'src/python')
from config_loader import load_config
from pathlib import Path
import json

config = load_config()
storage = Path(config['data_pipeline']['storage_path'])
artifacts = Path(config['pipeline']['artifacts_dir'])

print('=== Data ===')
for d in ['chunks', 'raw', 'validated', 'arrow', 'parquet']:
    p = storage / d
    if p.exists():
        pairs = [x.name for x in p.iterdir() if x.is_dir()]
        print(f'  {d}/: {pairs if pairs else "empty"}')

print('\n=== Strategies ===')
strat_dir = artifacts / 'strategies'
if strat_dir.exists():
    for s in strat_dir.iterdir():
        if s.is_dir():
            versions = list(s.glob('*.toml'))
            print(f'  {s.name}: {[v.stem for v in versions]}')

print('\n=== Cost Models ===')
cm_dir = artifacts / 'cost_models'
if cm_dir.exists():
    for c in cm_dir.iterdir():
        if c.is_dir():
            manifest = c / 'manifest.json'
            if manifest.exists():
                m = json.loads(manifest.read_text())
                print(f'  {c.name}: {m}')

print('\n=== Pipeline Status ===')
from orchestrator.operator_actions import get_pipeline_status
statuses = get_pipeline_status(config)
if statuses:
    for s in statuses:
        gate = f' [{s["gate_status"]}]' if s.get('gate_status') else ''
        blocking = f' BLOCKED: {s["blocking_reason"]}' if s.get('blocking_reason') else ''
        print(f'  {s["strategy_id"]}: {s["stage"]} ({s["progress_pct"]:.0f}%){gate}{blocking}')
        if s.get('anomaly_count', 0) > 0:
            print(f'    Anomalies: {s["anomaly_count"]}')
        if s.get('evidence_pack_ref'):
            print(f'    Evidence pack: {s["evidence_pack_ref"]}')
else:
    print('  No pipeline runs found')

print('\n=== Last Pipeline Proof ===')
proof = storage / 'data-pipeline' / 'pipeline_proof_result.json'
if proof.exists():
    r = json.loads(proof.read_text())
    print(f'  Status: {r.get("overall_status")}')
    print(f'  Dataset: {r.get("dataset_id")}')
```

## 10. Run Backtest

Ask for (or infer from context):
- **Strategy ID** — the strategy slug (e.g., `ma-crossover`)

### How backtesting works (D14 architecture)

The backtest pipeline has three phases that MUST happen in order:

1. **Signal precompute** (`orchestrator/signal_precompute.py`) — Takes M1 data + strategy spec, rolls up to strategy timeframe (e.g., H1), computes ALL indicators (entry AND exit), forward-fills to M1 with no-lookahead-bias, writes enriched Arrow IPC
2. **Rust backtester** (`crates/backtester`) — Reads enriched Arrow, evaluates pre-computed signal columns, executes trades at M1 granularity with session-aware costs
3. **Evidence pack** — Trade log, equity curve, metrics, all as Arrow IPC

The signal precompute is the critical bridge. It MUST compute:
- **Entry indicators** — whatever the strategy's `entry_rules.conditions` reference (e.g., `sma_crossover`)
- **Exit indicators** — whatever `exit_rules` reference (e.g., `atr` for ATR-based stops, chandelier trailing)
- **All of them** — if the precompute misses an indicator, the Rust backtester will fail fast with a missing-column error

### Pre-flight checks

Before running, verify:
1. **M1 Arrow data exists** for the strategy's pair
2. **Cost model exists and is approved** for the pair
3. **Strategy spec is complete** — entry rules, exit rules, session filter, position sizing
4. **Google Drive files are synced** — if storage is on Google Drive, read the data file first to force sync

### Running the backtest

```python
import sys; sys.path.insert(0, 'src/python')
from config_loader import load_config
from logging_setup import setup_logging
from orchestrator.operator_actions import run_backtest

config = load_config()
setup_logging(config)

result = run_backtest(strategy_id='<STRATEGY_ID>', config=config)

if result['status'] == 'success':
    print(f'Backtest complete for {result["backtest_id"]}')
    print(f'Output: {result["output_dir"]}')
    if result.get('evidence_pack_path'):
        print(f'Evidence pack: {result["evidence_pack_path"]}')
        print('Proceed to Review Results (Operation 11) to inspect.')
else:
    print(f'Backtest failed: {result["error"]}')
```

### Sanity checks after backtest

After a successful run, always check for these red flags:
- **Zero trades** — signal precompute likely missed an indicator, or session filter is too restrictive
- **All trades same direction** — strategy spec may only have one-directional entries (check if both `crosses_above` and `crosses_below` conditions exist)
- **Very short hold times** (1-3 bars for an H1 strategy) — ATR-based stop is probably miscalibrated (precompute didn't add ATR column, so stop used a raw multiplier as pip value)
- **Identical costs on every trade** — session-aware cost model is working, but all entries may be in the same session by design (check exit costs for variation)
- **"Access is denied" error on Windows** — data file on Google Drive not synced, or config paths not resolving (check `[backtesting]` section in base.toml)

After success, automatically chain to **Review Results** (Operation 11).

## 11. Review Results

Ask for (or infer from context):
- **Strategy ID** — the strategy to review

Loads the evidence pack and presents it to the operator.

```python
import sys; sys.path.insert(0, 'src/python')
from config_loader import load_config
from logging_setup import setup_logging
from orchestrator.operator_actions import load_evidence_pack

config = load_config()
setup_logging(config)

# State-driven evidence lookup: extract evidence_pack_ref from pipeline state
from orchestrator.operator_actions import get_pipeline_status as _get_status
statuses = _get_status(config)
evidence_ref = None
for s in statuses:
    if s['strategy_id'] == '<STRATEGY_ID>':
        evidence_ref = s.get('evidence_pack_ref')
        break

pack = load_evidence_pack(strategy_id='<STRATEGY_ID>', config=config, evidence_pack_ref=evidence_ref)
```

If `pack` is None, display: "No evidence pack available. Run a backtest first (Operation 10)."

Otherwise, format and display the evidence pack with: narrative overview, key metrics (total trades, win rate, profit factor, max drawdown, sharpe), strengths, weaknesses, session breakdown, anomalies with severity, risk assessment, trade distribution.

Then prompt: **Decision: Accept / Reject / Refine?**

Based on operator response:
- **Accept** → chain to Advance Stage (Operation 12)
- **Reject** → chain to Reject Stage (Operation 13)
- **Refine** → chain to Refine Stage (Operation 14)

## 12. Advance Stage

Asks the operator for a confirmation reason, then advances.

```python
import sys; sys.path.insert(0, 'src/python')
from config_loader import load_config
from logging_setup import setup_logging
from orchestrator.operator_actions import advance_stage

config = load_config()
setup_logging(config)

result = advance_stage(
    strategy_id='<STRATEGY_ID>',
    reason='<OPERATOR_REASON>',
    config=config,
)
print(f'Advanced: {result["from_stage"]} -> {result["to_stage"]}')
print(f'Decided at: {result["decided_at"]}')
```

## 13. Reject Stage

Asks for the rejection reason, then records the rejection.

```python
import sys; sys.path.insert(0, 'src/python')
from config_loader import load_config
from logging_setup import setup_logging
from orchestrator.operator_actions import reject_stage

config = load_config()
setup_logging(config)

result = reject_stage(
    strategy_id='<STRATEGY_ID>',
    reason='<REJECTION_REASON>',
    config=config,
)
print(f'Rejected at stage: {result["stage"]}')
print(f'Reason: {result["reason"]}')
```

Strategy stays at current stage — progression halted.

## 14. Refine Stage

Asks for refinement guidance, then returns strategy to `strategy-ready` for modification and re-submission.

```python
import sys; sys.path.insert(0, 'src/python')
from config_loader import load_config
from logging_setup import setup_logging
from orchestrator.operator_actions import refine_stage

config = load_config()
setup_logging(config)

result = refine_stage(
    strategy_id='<STRATEGY_ID>',
    reason='<REFINEMENT_GUIDANCE>',
    config=config,
)
print(f'Refined: {result["from_stage"]} -> {result["to_stage"]}')
print(f'Guidance: {result["reason"]}')
print('Strategy returned to strategy-ready. Modify the strategy (Operation 6), then re-run backtest (Operation 10).')
```

## 15. Resume Pipeline

Resumes interrupted pipeline runs. Can target a specific strategy or scan for all interrupted runs.

```python
import sys; sys.path.insert(0, 'src/python')
from config_loader import load_config
from logging_setup import setup_logging
from orchestrator.operator_actions import resume_pipeline

config = load_config()
setup_logging(config)

# For a specific strategy:
results = resume_pipeline(strategy_id='<STRATEGY_ID>', config=config)
# Or scan for all interrupted:
# results = resume_pipeline(strategy_id=None, config=config)

for r in results:
    ckpt = '(from checkpoint)' if r['checkpoint_found'] else '(no checkpoint)'
    print(f'Resumed {r["strategy_id"]} from {r["resumed_from_stage"]} {ckpt}')
```

## 16. Set Optimization Scope

Before optimization, the operator decides how wide the parameter search should be. This prevents wasted compute on overly broad searches when you already have good baseline values, and prevents overly narrow searches when you're genuinely exploring.

### When to trigger

- Operator says "set optimization scope", "how wide should we search", or any of: "tight", "explore", "wide open", "open it up", "narrow the ranges", "search everything"
- Before kicking off optimization if the operator hasn't explicitly chosen a scope yet
- When modifying optimization ranges on any strategy

### Step 1: Read the strategy spec

Load the strategy TOML and extract three things:

1. **Baseline values** — the default parameter values from the strategy's indicator definitions, exit rules, and position sizing sections. These are the "starting point" values the strategy was designed around.
2. **Current optimization ranges** — from `optimization_plan.parameters` (schema v2) or `optimization_plan.parameter_groups.ranges` (schema v1).
3. **Parameter classification** — assign each optimizable parameter a type using the table below.

### Step 2: Classify each parameter

Match parameter names to types. When ambiguous, use the parameter's role in the strategy (entry indicator vs exit rule) and its baseline value magnitude as hints.

| Type | Name patterns | Examples |
|------|--------------|----------|
| **period** | `*_period`, `*_length`, `*_window` | atr_period, fast_period, slow_period, trailing_atr_period |
| **bar_count** | `*_bars`, `*_count`, `*_lookback` | swing_bars, confirmation_bars |
| **multiplier** | `*_multiplier`, `*_mult`, `*_factor` | atr_multiplier, exit_atr_multiplier, sl_atr_multiplier |
| **ratio** | `*_rr`, `*_ratio`, `take_profit_*`, `tp_*` | take_profit_rr, tp_rr_ratio |
| **threshold** | `*_threshold`, `*_level`, `*_pct` | range_threshold |
| **categorical** | has `choices` field in spec | session_filter, htf_timeframe |

### Step 3: Present the intents

```
Optimization Scope — How wide should we search?

  Tight      — Validate around baseline (±20%)
               "I think these params are roughly right, prove it"

  Explore    — Moderate ranges, semantics-aware
               "Not sure what's optimal, find what works"

  Wide Open  — Full theoretical ranges per parameter type
               "No idea, search everything"

Pick one, or mix: "tight on entry, wide on exits"
```

**Mixed intents** are supported — the operator can set different scopes per parameter group (entry vs exit) or per individual parameter. Natural language works: "open up the exit params but keep entry tight" → Tight for channel_params group, Wide Open for exit_levels group.

### Step 4: Compute proposed ranges

Apply these rules based on intent + parameter type. All computed ranges are clamped to the floor/ceiling values to prevent nonsensical configurations.

**Tight** — validate what you have (±20% of baseline)

| Type | Rule | Floor / Ceiling | Step |
|------|------|-----------------|------|
| period | baseline ± max(3, baseline × 0.2) | 2 – 200 | 1 |
| bar_count | baseline ± max(1, baseline × 0.2) | 1 – 20 | 1 |
| multiplier | baseline ± 0.5 | 0.1 – 10.0 | 0.25 |
| ratio | baseline ± 0.5 | 0.5 – 10.0 | 0.5 |
| threshold | baseline ± 0.05 | 0.01 – 0.99 | 0.01 |
| categorical | all choices | — | — |

**Explore** — find what works (~±100% of baseline, semantics-aware)

| Type | Rule | Floor / Ceiling | Step |
|------|------|-----------------|------|
| period | baseline ± max(10, baseline × 1.0) | 2 – 200 | 1 if range ≤ 30, else 5 |
| bar_count | baseline ± max(3, baseline × 1.0) | 1 – 30 | 1 |
| multiplier | baseline × 0.25 to baseline × 3.0 | 0.1 – 10.0 | 0.25 |
| ratio | 0.5 to max(4.0, baseline × 2.0) | 0.5 – 10.0 | 0.5 |
| threshold | baseline ± 0.15 | 0.01 – 0.99 | 0.05 |
| categorical | all choices | — | — |

**Wide Open** — search everything (fixed ranges, baseline-independent)

| Type | Range | Step |
|------|-------|------|
| period | 5 – 50 (ATR-family), 2 – 200 (MA-family) | 1 |
| bar_count | 1 – 30 | 1 |
| multiplier | 0.25 – 8.0 | 0.25 |
| ratio | 0.5 – 8.0 | 0.5 |
| threshold | 0.05 – 0.95 | 0.05 |
| categorical | all choices | — |

For Wide Open periods: use 5–50 for ATR-related periods (atr_period, trailing_atr_period) and 2–200 for moving-average periods (fast_period, slow_period). The distinction matters because ATR is stable beyond ~50 bars while MA periods can meaningfully vary up to 200.

### Step 5: Display the comparison table

Show current vs proposed so the operator can see exactly what changes:

```
Optimization Scope: EXPLORE for channel-breakout v001

Parameter            Type        Baseline   Current        Proposed       Steps
────────────────────────────────────────────────────────────────────────────────
swing_bars           bar_count   3          2 – 20         1 – 6          6
atr_period           period      14         5 – 50         4 – 28         25
atr_multiplier       multiplier  1.0        0.25 – 5.0     0.25 – 3.0     12
confirmation_bars    bar_count   1          1 – 10         1 – 4          4
stop_loss_atr        multiplier  2.0        0.5 – 6.0      0.5 – 6.0      12
take_profit_rr       ratio       2.0        0.5 – 5.0      0.5 – 4.0      8
exit_atr_multiplier  multiplier  2.0        0.5 – 8.0      0.5 – 6.0      12
trailing_atr_period  period      14         5 – 50         4 – 28         25

Search space: ~6.9M combinations
Guidance:    Large — optimizer will need 100+ generations, but CMA-ES handles this well
```

### Search space estimation

Multiply step counts: for each parameter, `(max - min) / step + 1`. Then multiply all together for the grid equivalent. The optimizer doesn't enumerate — CMA-ES and DE search intelligently — but the number indicates complexity.

| Grid size | Guidance |
|-----------|----------|
| < 10K | Quick convergence — optimizer will finish fast |
| 10K – 1M | Good balance of exploration and speed |
| 1M – 100M | Large — needs 100+ generations, still tractable |
| > 100M | Very large — suggest coarsening steps or narrowing some ranges |

If the search space exceeds 100M, proactively suggest which parameters to coarsen (usually periods can go from step=1 to step=2 or step=5 without losing much).

### Step 6: Confirm and write

Ask: **"Look good? You can tweak individual params (e.g. 'make swing_bars wider', 'tighten the ATR period') or confirm to write."**

On confirmation, update the strategy TOML:
- **Schema v1** (parameter_groups): update `optimization_plan.parameter_groups.ranges.<param>` min/max/step values
- **Schema v2** (flat registry): update `optimization_plan.parameters.<param>` min/max/step values
- If a parameter wasn't previously in the optimization plan (e.g. it was fixed), add it to the appropriate group/section

After writing, show a one-line summary: "Wrote EXPLORE scope to channel-breakout/v001.toml — 8 params, ~6.9M search space."

---

## 17. Persistent Worker Optimization Mode

The optimization pipeline supports a high-performance persistent worker mode that keeps Rust worker processes alive across generations, eliminating per-generation data loading. This achieves **1000+ evals/sec** (vs ~50 evals/sec in subprocess mode).

### Architecture

- **Rust binary:** `forex_worker.exe` (sibling to `forex_backtester.exe` in the same target dir)
- **Protocol:** JSON-lines over stdin/stdout. Python sends commands, Rust responds with results.
- **Cache:** Each worker holds an LRU cache of Arrow data in memory (keyed by signal hash)
- **Parallelism:** N workers run in parallel (one eval at a time per worker, CPU-bound)

### Config (`config/base.toml` → `[optimization]`)

```toml
[optimization]
score_mode = "composite"        # "composite" (default, recommended) or "sharpe"
use_persistent_worker = true   # false = subprocess mode (default, backwards compatible)
persistent_workers = 4          # number of long-lived worker processes
persistent_eval_timeout = 120   # seconds before killing unresponsive worker
memory_budget_mb = 5632         # total memory budget across all workers

[optimization.progressive_narrowing]
enabled = false                 # narrow search space after N generations
trigger_generation = 50         # when to start narrowing
range_multiplier = 2.0          # how much wider than top-10% range
```

### Strategy TOML additions (`optimization_plan` section)

```toml
[optimization_plan]
objective_function = "composite" # "composite" (recommended) or "sharpe", "calmar", "profit_factor", "expectancy"
year_range = [2018, 2025]       # optional — filter data to year range (proportional speedup)

[optimization_plan.prescreening]
enabled = true                  # optional, default false
mode = "H1"                     # "H1" (trend strategies) or "M1_slice" (scalping)
m1_slice_months = 3             # months for M1_slice mode
n_generations = 5               # quick screening generations
survival_ratio = 0.2            # keep top 20% of signal groups
```

### Running optimization with persistent workers

```python
# Enable in config before running:
config['optimization']['use_persistent_worker'] = True

# The orchestrator handles everything:
# 1. Starts WorkerPool (N forex_worker processes)
# 2. Preloads enriched Arrow data into worker caches (0.06s per file)
# 3. Sends batched eval requests (100+ candidates per group = 1000+ evals/sec)
# 4. Checkpoints to optimization_checkpoint.json after each generation
# 5. Shuts down workers on completion or crash
```

### Performance characteristics

| Feature | Speedup | Mechanism |
|---------|---------|-----------|
| Persistent worker | 10-20x | Eliminate per-generation data reload |
| Year-range filtering | Proportional | Less data (e.g., 8yr = ~3x faster) |
| Pre-screening | Eliminate 80% weak groups | Fast H1 or M1-slice triage |
| Adaptive batching | 1.2-1.5x | Auto-adjusts batch size (5s-60s target per gen) |
| Progressive narrowing | Faster convergence | Tightens bounds after burn-in |
| Warm-start from pre-screen | Fewer gens needed | Seeds CMA-ES with pre-screen winners |

**Key insight:** Batch size matters. 100+ candidates per group achieves 1000+ evals/sec per worker due to vectorized evaluation. The orchestrator's default batch_size=2048 is tuned for this.

### Troubleshooting

- **Worker binary not found:** Build with `cargo build --release` from `src/rust/crates/backtester`. Both `forex_backtester.exe` and `forex_worker.exe` are built.
- **NaN scores:** Check enriched data has bid/ask/session/quarantined columns. Missing columns = broken evals.
- **Slow evals/sec:** Ensure using release binary (not debug). Check candidates-per-group is >10.
- **Worker crash:** Python auto-restarts crashed workers and replays load_data calls.
- **Checkpoint resume:** If orchestrator crashes, restart with same config — it resumes from `optimization_checkpoint.json`.

---

## Behavioral Rules

1. **Never write ad-hoc scripts** — use the existing modules and CLIs. The infrastructure is built; use it.
2. **Always confirm before long-running operations** — downloads and full pipeline proofs can take minutes. Get a yes first.
3. **Run large downloads in background** — use `run_in_background` for 10+ year date ranges.
4. **Show progress** — for multi-step operations, report each stage completion.
5. **Suggest the next step** — after download suggest validate, after strategy build suggest review, etc.
6. **Use the real config** — always `load_config()`, never hardcode paths.
7. **Windows/Git Bash** — `.venv/Scripts/python.exe`, forward slashes, `PYTHONPATH=src/python`.
8. **When indicators are missing from the registry** — don't silently fail. Tell the user what's missing and offer to add them.
9. **Spread is always available** — the downloader captures bid+ask separately. Spread = ask - bid. Always report spread stats after download.
10. **Never block pipeline progression based on profitability metrics** — the operator makes the final call. Even strategies with negative P&L, zero trades, or poor metrics can be advanced. Anomalies are informational only.
11. **Signal precompute must cover ALL indicators** — entry indicators AND exit indicators (ATR for stops, trailing parameters). If the strategy uses `atr_multiple` or `chandelier` exit rules, ATR must be precomputed. Missing columns cause silent zero-trade backtests or miscalibrated stops.
12. **M1 data is the execution layer, strategy timeframe is the signal layer** — the backtester always receives M1 (or tick) data. Signal precompute rolls up to the strategy timeframe for indicator computation, then forward-fills back to M1 with no-lookahead-bias. Each M1 bar only sees indicator values from the most recently COMPLETED strategy-timeframe bar.
13. **Session relabeling** — raw downloaded data often has all bars labeled `off_hours`. The signal precompute stage relabels sessions from the config schedule. Always verify session distribution in the enriched data before trusting session-filtered results.
14. **Google Drive data sync** — storage is on Google Drive. Files may not be locally synced. Before backtesting, read the Arrow data file to force sync. "Access is denied" on Windows usually means the file hasn't synced yet.
15. **Strategy specs need both directions** — a vanilla crossover strategy should have both `crosses_above` (long) and `crosses_below` (short) entry conditions unless explicitly designed as directional. When building a strategy, always ask if it should trade both directions.
16. **Validate backtest results** — after every backtest, check: trade count (zero = broken precompute), hold duration (too short = stop calibration), cost variation (should differ by session), direction distribution (long+short if bidirectional). These are pipeline health checks, not strategy quality judgements.
17. **Indicator registry is dual-write** — when adding new indicators, update BOTH `contracts/indicator_registry.toml` AND the `default_registry()` function in `src/rust/crates/strategy_engine/src/registry.rs`. The Rust registry is hardcoded — the TOML file alone is not enough. Also update the registry test assertions for indicator count (`test_default_registry_contains_all_indicators` and `test_registry_is_extensible`).
18. **Never `cargo clean` on Windows** — Smart App Control blocks freshly compiled build-script binaries and the build becomes unrecoverable from the original target dir. If you need a clean rebuild, use `CARGO_TARGET_DIR="C:/Users/ROG/AppData/Local/Temp/rust-target"` instead. After building to temp, copy the binary to `target/debug/` where the pipeline expects it.
19. **Pipeline binary path is target/debug/** — `run_backtest` looks for the Rust binary at `src/rust/target/debug/forex_backtester.exe` (not release). If the binary isn't there, copy it from wherever it was built.
20. **Debug opaque backtest failures directly** — when `run_backtest` fails with "exit code -1", run the binary directly with explicit arguments to see the real error: `src/rust/target/debug/forex_backtester.exe --spec <path> --data <enriched-arrow> --cost-model <path> --output <dir> --config-hash <hash> --memory-budget 512`.
21. **Trade log stores costs in pips** — the trade log Arrow file stores spread and slippage values already in pips (e.g., 1.2 = 1.2 pips). Do NOT multiply by 10000 when analyzing — that produces nonsense like 12000 pip spreads.
22. **Multi-TF composite indicators** — indicators like `swing_pullback` work through the signal precompute's `_compute_indicator` function which accepts an optional `m1_df` parameter. The composite indicator internally rolls M1 to HTF for bias computation. The strategy `metadata.timeframe` is the LTF (entry timeframe), and `htf_timeframe` is passed as an indicator parameter.
23. **Prompt for optimization scope before optimization** — if the operator hasn't explicitly chosen a scope (Tight/Explore/Wide Open) in this session and the strategy has an optimization_plan, present the 3 intents before running optimization. This ensures the operator consciously decides how wide to search rather than inheriting whatever ranges happen to be in the TOML. Skip the prompt only if the operator already set scope earlier or explicitly says to use existing ranges.
24. **Persistent worker binary is forex_worker.exe** — sibling to forex_backtester.exe in the same target directory. When `use_persistent_worker = true`, the orchestrator derives the worker path from the backtester path by replacing the filename. Both binaries must be built (`cargo build --release` builds both).
25. **Batch candidates for throughput** — persistent worker evals/sec scales with candidates-per-group. 1 candidate/group = ~11 evals/sec. 100 candidates/group = ~800 evals/sec. 200+ = 1000+. The orchestrator's batch_size distributes candidates across groups automatically.
26. **Year-range and prescreening are backwards compatible** — year_range defaults to None (full dataset), prescreening defaults to disabled. Strategy TOMLs without these fields work unchanged. The Rust types accept but ignore these fields.
27. **Optimization checkpointing** — the orchestrator saves state to optimization_checkpoint.json every N generations (configurable via checkpoint_interval_generations). On crash/restart, it resumes from the last checkpoint. Don't delete checkpoint files during active optimization runs.
28. **Composite scoring is the default optimization objective** — the optimizer uses a weighted composite of Sharpe (0.25), R-squared (0.25), profit factor (0.15), max drawdown (0.15), trade count (0.10), and win rate (0.10) with a hard profitability gate: any candidate with Sharpe <= 0 scores zero. This was data-driven: Sharpe-only optimization produced candidates that all failed CPCV validation because the optimizer and validator were misaligned. Composite aligns them. Strategy specs should use `objective_function = "composite"` and config should use `score_mode = "composite"`.
29. **Score mode flows through two paths** — the Rust binary accepts `--score-mode` on the CLI (overrides manifest), and the manifest JSON can contain a `score_mode` field. The CLI flag takes priority. The Python `batch_dispatch.py` reads `config["optimization"]["score_mode"]` and includes it in manifest JSON. When building or modifying strategy specs, always set `objective_function = "composite"` unless the operator explicitly requests otherwise.
30. **Never use Sharpe-only for optimization** — data analysis on 10,185 candidates showed Sharpe and composite rankings are anti-correlated (rho=-0.56) when composite lacks a profitability gate. With the hard gate, they correlate positively (rho=0.71) among profitable candidates but composite still reshuffles rankings to favor robust strategies (only 8/20 top-20 overlap). This differentiation is what helps candidates survive CPCV validation.
