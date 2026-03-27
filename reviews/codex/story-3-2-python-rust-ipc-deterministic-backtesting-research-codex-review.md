# Story 3-2-python-rust-ipc-deterministic-backtesting-research: Story 3.2: Python-Rust IPC & Deterministic Backtesting Research — Codex Review

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-18
**Method:** Static analysis (no pytest execution — sandbox policy)
**Pipeline Stage:** Automated (non-blocking second opinion)

---

**High Findings**
1. AC3 is only partially implemented: the artifact explicitly recommends per-trade checkpointing for single backtests, then says that state is “not persisted,” which means there is no crash-resumable within-run checkpoint strategy for backtests at all. The only persisted within-stage strategy left is per-batch optimization checkpoints, so the “applicable to both backtests and optimization runs” requirement is not actually satisfied. [3-2-ipc-determinism-research.md](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/research/3-2-ipc-determinism-research.md#L370) [3-2-ipc-determinism-research.md](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/research/3-2-ipc-determinism-research.md#L377) [3-2-ipc-determinism-research.md](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/research/3-2-ipc-determinism-research.md#L529)

2. AC7 is only partially implemented: the downstream interface contract for equity curves is internally contradictory. The CLI contract defines `equity_{trial_idx}.arrow` as a bar-level artifact with `bar_index` and `timestamp_us`, but the “Open Questions” section says V1 should instead persist per-trade equity curves and directs Stories 3.5/3.6 to implement that. A contract that still has a core output format unresolved is not consumable “without ambiguity” for downstream stories. [3-2-ipc-determinism-research.md](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/research/3-2-ipc-determinism-research.md#L840) [3-2-ipc-determinism-research.md](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/research/3-2-ipc-determinism-research.md#L1028)

**Medium Findings**
1. The memory budget contract is numerically inconsistent. The executive summary says `~2.4GB active`, while the detailed table totals `~1,065 MB` active heap and `~1,465 MB` including mmap. That weakens the credibility of the resource model the downstream stories are supposed to implement against. [3-2-ipc-determinism-research.md](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/research/3-2-ipc-determinism-research.md#L24) [3-2-ipc-determinism-research.md](/C:/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/research/3-2-ipc-determinism-research.md#L551)

2. The test suite is largely substring-based, so it does not validate semantic consistency. Examples: section presence is just `section_lower in text_lower`; checkpoint coverage only looks for `open_position` anywhere; CLI output coverage only checks `metrics.arrow`; memory-budget “calculation” passes on any mention of `os_reserve` and `thread`. That is why the AC3 and AC7 contradictions above are not caught. [test_story_3_2_ipc_determinism_research.py](/C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_research/test_story_3_2_ipc_determinism_research.py#L107) [test_story_3_2_ipc_determinism_research.py](/C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_research/test_story_3_2_ipc_determinism_research.py#L350) [test_story_3_2_ipc_determinism_research.py](/C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_research/test_story_3_2_ipc_determinism_research.py#L552) [test_story_3_2_ipc_determinism_research.py](/C:/Users/ROG/Projects/Forex Pipeline/src/python/tests/test_research/test_story_3_2_ipc_determinism_research.py#L581)

**Acceptance Criteria Scorecard**

| AC | Status | Notes |
|---|---|---|
| 1 | Fully Met | 3-option IPC matrix, required criteria, recommendation, and repo-local rationale are present. |
| 2 | Fully Met | All five determinism areas and a per-output reproducibility contract are documented. |
| 3 | Partially Met | Optimization checkpointing is concrete; single-backtest persisted resume strategy is not. |
| 4 | Fully Met | Pre-allocation, mmap, streaming, thread buffers, and throttle strategy are documented. |
| 5 | Fully Met | Alignment matrix covers D1/D2/D3/D8/D13/D14 and confirms D15 has no impact. |
| 6 | Fully Met | Proposed Architecture Updates section exists; conclusion is that no new architecture edits are required. |
| 7 | Partially Met | Build/dependency tables exist, but the equity-curve contract is still unresolved. |

**Test Coverage Gaps**
- No test checks that single-backtest checkpointing is both persisted and resumable; current checks only verify keywords like `open_position`, progress fields, and `within-stage`/`cross-stage`.
- No test checks contract consistency across sections, so the per-bar vs per-trade equity-curve conflict passes.
- No test validates arithmetic consistency of the documented memory budget.
- No test independently verifies the claimed pytest results here; I could not rerun the suite because command execution for `pytest` was blocked in this environment.

**Summary**
5 of 7 criteria are fully met, 2 are partially met, 0 are not met. The main gaps are the missing persisted single-backtest resume contract and the unresolved equity-curve output contract for downstream consumers.
