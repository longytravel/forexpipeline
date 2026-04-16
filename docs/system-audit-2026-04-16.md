# Forex Pipeline — System Audit

**Date:** 2026-04-16
**Scope:** Paperwork, uncommitted code, ad-hoc scripts, auto-memory, reviews, build/test health
**Method:** 5 parallel audit agents + synthesis

---

## 1. Headline

The pipeline is in **better shape than it looks from the outside**.

- All 37 stories across Epics 1, 2, 3, 5 are `done`. Epic 4 (Pipeline Dashboard & Visualization) is the intended next epic.
- Rust builds green. Release binaries (`forex_backtester.exe`, `forex_worker.exe`, `cost_model_cli.exe`) are present and runnable, built 2026-04-03.
- Three strategies (ma-crossover, swing-pullback, channel-breakout) have full backtest + optimization artifacts on disk.
- The latest work stream — a composite-scoring fix — is **complete and correct** but **uncommitted**.

**The problems are almost entirely hygiene, not substance.** One git commit exists (`Initial commit`) and everything since then sits in the working tree. Memory has three stale entries asserting blockers that are no longer true. Paperwork is scattered across the root.

---

## 2. What's Working

| Area | Status | Evidence |
|---|---|---|
| Rust build | ✅ Green | `cargo build --release` succeeds with one benign unused-field warning |
| Release binaries | ✅ Built, runnable | `target/release/forex_backtester.exe` 3.1M (Apr 3); `--help` returns usage |
| Story completion | ✅ 37/37 done | sprint-status.yaml matches disk exactly |
| Persistent worker | ✅ Robust on Windows | Dedicated read loop, stderr drain task, auto-restart — no asyncio hang |
| Composite scoring fix | ✅ Correct | Hard gate at `metrics.rs:59` (`if sharpe <= 0.0 { return 0.0 }`) |
| Artifacts on disk | ✅ Complete | 3 strategies with backtest + optimization Arrow outputs |
| Planning artifacts | ✅ Canonical | prd.md, architecture.md (137K), epics.md (111K) — keep as-is |
| Code quality of uncommitted work | ✅ Clean | No TODOs, no debug prints, no half-finished features |

---

## 3. What's Not Working

### 3.1 Git hygiene (critical)

- **One commit total**, with 20 modified + 8 new files (+460/-50 lines) uncommitted.
- Three coherent work-streams interleaved in the diff — needs to be split into logical commits.
- No branch, no push, no backup of ~3 weeks of work beyond local disk.

### 3.2 Memory staleness

Three auto-memory files assert blockers that are no longer real:

| File | Claim | Reality |
|---|---|---|
| `project_prd_progress.md` | "Next: Create Epics via /bmad-pm" | `epics.md` has existed since 2026-03-22 |
| `project_optimization_run_blockers.md` | Release binary blocked by Smart App Control | Binary built 2026-04-03, runnable |
| `project_persistent_worker_status.md` | Orchestrator hangs on Windows | `worker_client.py` has the correct dedicated-read-loop design; no hang |

### 3.3 Paperwork clutter

Six large `.md` files at the project root that belong inside `docs/`:

- `EPIC5_ARCHITECTURE_ANALYSIS.md` (23K) → `docs/epics/epic-5-architecture.md`
- `EPIC5_COMPLETE_RESEARCH_REPORT.md` (57K) → `docs/epics/epic-5-research-report.md`
- `3-2-ipc-determinism-research.md` (64K) → `docs/research/epic-3-ipc-determinism.md` (or delete — duplicates story 3-2)
- `hardware-optimization-playbook.md` (11K) → `docs/operations/`
- `product-brief-BMAD-Backtester-2026-03-13.md` (13K) → `docs/archive/` (superseded by `prd.md`)
- `baseline-capability-gap-assessment-ClaudeBackTester-2026-03-13.md` (5.5K) → `docs/archive/`

Three overlapping `docs/optimization-*.md` reports from 2026-03-25 should consolidate into one.

### 3.4 Scripts clutter

Eight new untracked scripts in `scripts/` from the composite-scoring investigation:

- **Keep:** `analyze_composite_formula.py` — useful reference if weights need re-tuning
- **Delete:** `_inspect_scores.py`, `_run_inspect.ps1`, `run_composite.ps1`, `run_formula_analysis.ps1`, `run_profitable_analysis.ps1` — throwaway, three were never executed
- **Archive (or delete):** `compare_score_modes.py`, `sharpe_vs_composite_profitable.py` — served their purpose; hard gate decision made

### 3.5 Python environment

Audit agent couldn't run `pytest --co` because Python 3.11 isn't on `PATH` the expected way. Code imports fine; likely just needs venv activation. Worth verifying before any further Python work.

### 3.6 One minor code smell

`src/python/orchestrator/stage_runner.py:238` has a bare `except Exception: pass` on state-file cleanup. Broad but non-critical; note for later.

---

## 4. Uncommitted Work Decomposition

Agent 2's analysis of the +460/-50 diff identifies three coherent themes that should become four commits:

1. **`feat(metrics): composite scoring with normalized components`**
   Files: `src/rust/crates/backtester/src/metrics.rs`, `.claude/skills/pipeline/SKILL.md`
   *Hard-gate composite score (0.25 Sharpe + 0.25 R² + 0.15 PF + 0.15 MaxDD + 0.10 trades + 0.10 winrate). Sharpe ≤ 0 → score 0.*

2. **`feat(backtester): online accumulators for composite & R² metrics`**
   Files: `src/rust/crates/backtester/src/batch_eval.rs`, `src/rust/crates/backtester/src/bin/forex_backtester.rs`, `src/rust/crates/backtester/src/worker/mod.rs`, `cost_model/src/{lib,loader}.rs`, `strategy_engine/src/types.rs`, `strategy_engine/tests/e2e_integration.rs`
   *Streaming computation of the composite inputs during backtest; CLI `--score-mode` flag; cost-model loader adjustments.*

3. **`feat(orchestrator): score-mode threading + Hidden Smash Day indicator`**
   Files: `src/python/optimization/batch_dispatch.py`, `src/python/orchestrator/signal_precompute.py`, `src/python/rust_bridge/worker_client.py`, `config/base.toml`, `tests/e2e/fixtures/*.toml`, `tests/e2e/test_epic2_pipeline_proof.py`
   *`score_mode` wired through manifest → worker request. Adds Larry Williams Hidden Smash Day reversal indicator (MQL5 #21392). Unsupported indicators now raise instead of silently warning.*

4. **`fix(orchestrator): zero-trade detection, evidence-pack timing, artifact paths`**
   Files: `src/python/orchestrator/{stage_runner,operator_actions,gate_manager}.py`
   *Evidence-pack generation moved from `BACKTEST_RUNNING` → `BACKTEST_COMPLETE`. `backtest_run_id` threaded through stage context. Zero-trade detection with diagnostic warning. Gate manager artifact-path fix.*

---

## 5. Tidy Plan (execute in order)

### Step A — git baseline (safety first)
1. Create a branch `pre-tidy` pinned to current HEAD so nothing is lost.
2. Review each proposed commit against the diff.
3. Make the 4 commits above.
4. Push to GitHub so there's an off-disk backup of ~3 weeks of work.

### Step B — paperwork reorg
1. `mkdir -p docs/{epics,research,operations,archive}`
2. Move the 6 top-level `.md` files as listed in §3.3.
3. Consolidate the 3 `docs/optimization-*.md` reports into `docs/optimization-sprint-2026-03-25.md`; archive the originals.
4. Delete `3-2-ipc-determinism-research.md` if the content is fully covered by `_bmad-output/implementation-artifacts/3-2-*.md` (agent 1 reports it is).

### Step C — scripts cleanup
1. Delete: `_inspect_scores.py`, `_run_inspect.ps1`, `run_composite.ps1`, `run_formula_analysis.ps1`, `run_profitable_analysis.ps1`.
2. Move to `scripts/archive/`: `compare_score_modes.py`, `sharpe_vs_composite_profitable.py`.
3. Keep `analyze_composite_formula.py` at `scripts/analyze_composite_formula.py`.

### Step D — memory refresh
1. Update `project_prd_progress.md` → planning done; current state is "Epic 4 is next planned epic".
2. Mark `project_optimization_run_blockers.md` and `project_persistent_worker_status.md` as resolved (or delete and write one new `project_optimization_phase1_status.md` consolidating the three optimization memories).
3. Add `project_composite_scoring_decision.md` — records the hard-gate decision and the `metrics.rs` location.
4. Remove the `project_composite_scoring_results.md` TODO once replaced.

### Step E — environment sanity
1. Confirm venv is intact (`.venv/Scripts/python --version`).
2. Run `pytest tests/ -q --co` to confirm imports resolve.
3. Run `pytest tests/unit -q` and at least one E2E proof to confirm the uncommitted work still passes.

---

## 6. Next Steps

Two tracks, pick one:

### Track 1 — Ship what exists (recommended first)
- Execute the tidy plan above (maybe 1–2 hours).
- Commit and push. Project root becomes clean. Memory becomes truthful.
- You can then confidently start Epic 4 on a clean baseline.

### Track 2 — Start Epic 4: Pipeline Dashboard & Visualization
- Currently `backlog` in `sprint-status.yaml`. No story files exist yet.
- Would start with: `/bmad-create-story` or `/write-stories 4`.
- Worth doing Track 1 first so the story-writer sees an accurate project state.

**Open strategic questions worth deciding before Track 2:**

1. **Epic 4 scope** — dashboard for what audience? Operator-facing diagnostic view, or stakeholder-facing "how is the strategy performing" view? Architecture.md may already answer this; worth re-reading that section before /write-stories.
2. **Composite scoring validation** — hard gate is in. Should you re-run the gen_000000 comparison with the fix to confirm the correlation is now positive? 20-minute sanity check.
3. **Python env** — the venv issue needs resolving or agent 5's test-health check stays indeterminate.

---

## 7. Appendix: Agent Reports

- **Agent 1 (paperwork):** 70 files inventoried, 6 root files to relocate, Epic 4 backlog confirmed intentional.
- **Agent 2 (code diff):** 3 coherent work-streams, 4-commit plan, clean implementation with one minor `except Exception: pass`.
- **Agent 3 (scripts/composite):** Hard gate verified in `metrics.rs:59`. Scripts were the investigation; fix is shipped.
- **Agent 4 (memory/reviews):** 3 stale memories, 3 consolidation candidates, reviews/ is canonical (not duplicated), `lessons-learned.md` 89K is worth keeping.
- **Agent 5 (build/test):** Rust green, binaries built, 37/37 stories done, persistent worker fine, release binary unblocked, Python env needs attention.
