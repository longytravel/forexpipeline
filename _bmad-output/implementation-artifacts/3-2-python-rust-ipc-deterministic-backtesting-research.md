# Story 3.2: Python-Rust IPC & Deterministic Backtesting Research

Status: review

## Story

As the **operator**,
I want **Python-Rust IPC mechanisms validated and reproducibility, checkpoint, and memory contracts defined**,
so that **Stories 3.3–3.5 can implement the backtesting pipeline on a proven technical foundation, and Stories 3.6–3.9 have clear dependency notes**.

## Acceptance Criteria

1. **Given** the architecture specifies Arrow IPC multi-process (D1) **and** the ClaudeBackTester uses PyO3 in-process FFI,
   **When** the researcher compares IPC options,
   **Then** the research artifact includes a comparison matrix of at least 3 Python-Rust IPC mechanisms (PyO3 FFI, subprocess + Arrow IPC files, shared memory/mmap) evaluating: latency, serialization cost, crash isolation, implementation complexity, debugging experience, and Windows compatibility.
   *(Ref: D1 — Multi-Process with Arrow IPC; FR18 — deterministic reproducibility; NFR10 — crash prevention)*

2. **Given** FR18 requires identical outputs from identical inputs **and** Rust uses Rayon for parallel evaluation,
   **When** the researcher investigates deterministic backtesting,
   **Then** the research artifact documents concrete strategies for: floating-point reproducibility across runs, random seed management for stochastic elements, deterministic iteration order with Rayon parallel evaluation, timestamp precision requirements (microsecond int64 per D2), and Windows-specific platform concerns.
   **And** the research artifact includes a **Reproducibility Contract** that explicitly resolves the tension between PRD Technical Success ("materially identical results within defined tolerance") and Epic 3 Story 3.9 AC #9 ("bit-identical results"), stating for each output type (trade log, equity curve, metrics, manifest hash) whether V1 requires bit identity or tolerance-based equivalence, and how compliance is verified.
   *(Ref: FR18 — deterministic reproducibility; D2 — Arrow IPC artifact schema; D14 — strategy engine shared crate; PRD Technical Success — reproducibility definition)*

3. **Given** NFR5 requires incremental checkpointing for long-running optimization runs **and** NFR11 requires crash-safe resume **and** D3 specifies within-stage checkpointing for Rust batch binaries,
   **When** the researcher evaluates checkpoint/resume patterns,
   **Then** the research artifact documents: incremental checkpoint strategies applicable to both backtests and optimization runs within a single Rust binary execution, crash-safe write semantics (write-then-rename per NFR15), resume verification that detects and recovers from partial checkpoints, checkpoint granularity trade-offs (per-bar vs per-trade vs per-batch), and the distinction between within-stage checkpointing (Rust binary) and cross-stage resume (Python orchestrator per D3).
   *(Ref: NFR5 — incremental checkpointing for optimization; NFR11 — crash recovery; NFR15 — data integrity; D3 — pipeline state machine with within-stage checkpointing)*

4. **Given** NFR4 requires deterministic memory pre-allocation **and** NFR10 requires crash prevention as highest priority,
   **When** the researcher evaluates memory budgeting patterns,
   **Then** the research artifact documents: pre-allocation strategies for Rust batch processes (inventory system memory, reserve 2-4GB OS margin, pre-allocate remainder), mmap access patterns for Arrow IPC market data (zero-copy reads), streaming result output to avoid equity curve accumulation, per-thread trade buffer sizing (architecture targets 16 × 50MB = 800MB), and throttle-before-OOM strategies.
   *(Ref: NFR4 — deterministic memory budgeting; NFR10 — crash prevention; D1 — Arrow IPC mmap)*

5. **Given** the architecture decisions D1, D3, D8 define the system topology,
   **When** the researcher validates recommendations against architecture,
   **Then** each recommendation explicitly states alignment or proposed deviation from: D1 (multi-process topology), D2 (Arrow IPC/SQLite/Parquet hybrid), D3 (sequential state machine + checkpoint), D8 (structured errors at process boundaries), D13 (cost model as library crate), D14 (strategy engine shared crate).
   **Note:** D15 (named pipes for live daemon) is explicitly OUT OF SCOPE — it addresses live IPC, not batch IPC. Confirm no impact on live-daemon path, but do not evaluate D15 as a batch IPC option.
   *(Ref: Architecture Decisions D1–D14; D15 scoped out — separate live IPC mechanism)*

6. **Given** the research may reveal better approaches than currently documented,
   **When** the researcher identifies architecture improvements,
   **Then** the research artifact includes a "Proposed Architecture Updates" section with specific edits to architecture.md, each justified by research evidence and noting which downstream stories are affected.
   *(Ref: Architecture document maintenance)*

7. **Given** Stories 3.3–3.5 are direct consumers of this research's contracts,
   **When** the researcher finalizes the build plan,
   **Then** the research artifact includes:
   - **Detailed build plan for Stories 3.3–3.5** with columns: story ID, component, approach (port-from-baseline / build-new / hybrid), key dependencies, estimated complexity, specific questions resolved, and interface contracts consumed from this research.
   - **Dependency notes for Stories 3.6–3.9** with columns: story ID, component, upstream dependency on 3.3–3.5, any research findings relevant to that story.
   *(Ref: Epic 3 story sequence; Story 3-1 V1 Port Boundary output)*

## Tasks / Subtasks

- [x] **Task 1: Consume Story 3-1 Output** (AC: #1, #5, #7)
  - [x] Read `_bmad-output/implementation-artifacts/3-1-claudebacktester-backtest-engine-review.md` (completed story file with findings)
  - [x] Extract the V1 Port Boundary table (keep/adapt/replace/build-new verdicts)
  - [x] Extract the PyO3 Bridge & Data Flow specification (batch_evaluate interface, 64-slot parameter layout, numpy marshalling)
  - [x] Extract the downstream handoff subsection specifically for story 3-2
  - [x] Extract lifecycle specification and metrics/storage specification findings
  - [x] Document which ClaudeBackTester components are relevant to IPC research

- [x] **Task 2: IPC Mechanism Comparison Matrix** (AC: #1)
  - [x] Research **Option A: PyO3 in-process FFI** — document ClaudeBackTester's current `batch_evaluate()` approach, measure latency characteristics, assess crash isolation (process-coupled), evaluate debugging (mixed Python/Rust stack traces), note Windows compilation requirements (MSVC toolchain)
  - [x] Research **Option B: Subprocess + Arrow IPC files** — document the D1-specified approach, prototype `subprocess.run()` → `forex_backtester` binary with Arrow IPC file paths as args, measure file I/O overhead vs mmap, evaluate crash isolation (full process boundary), assess error propagation (structured JSON stderr per D8)
  - [x] Research **Option C: Shared memory / mmap** — evaluate `mmap` of Arrow IPC files for zero-copy data sharing, assess Windows compatibility of memory-mapped files, evaluate coordination primitives needed, document complexity vs benefit trade-off
  - [x] Build comparison matrix with columns: latency (μs), serialization cost, crash isolation (none/partial/full), complexity (LOC estimate), debug experience, Windows compat, alignment with D1
  - [x] Write recommendation with justification (expected: subprocess + Arrow IPC per D1, but research must validate)

- [x] **Task 3: Deterministic Backtesting Research** (AC: #2)
  - [x] Research **floating-point reproducibility**: IEEE 754 guarantees on Windows x86-64, Rust `f64` determinism with `#[no_std]` math vs libm, fused multiply-add (FMA) instruction impact, compiler flag requirements (`-C target-feature=-fma` or equivalent)
  - [x] Research **Rayon parallel determinism**: `par_iter()` vs `par_bridge()` ordering guarantees, `IndexedParallelIterator` for deterministic chunk assignment, reduction order stability, document pattern for deterministic parallel evaluation that produces identical results
  - [x] Research **random seed management**: strategy for any stochastic elements (Monte Carlo in validation, bootstrap confidence intervals), `rand` crate `SeedableRng` with `StdRng` or `ChaCha8Rng` for reproducibility, seed propagation across parallel workers
  - [x] Research **timestamp precision**: validate int64 microsecond epoch format (per D2 Arrow schema), timezone handling (UTC-only enforcement), session boundary precision requirements
  - [x] Research **Windows-specific concerns**: MSVC vs GNU toolchain floating-point behavior, `_controlfp` precision settings, `std::env::set_var("RUST_BACKTRACE", "1")` for debugging, Windows file locking semantics for Arrow IPC
  - [x] Document concrete code patterns / compiler flags required for each determinism guarantee

- [x] **Task 4: Checkpoint/Resume Pattern Research** (AC: #3)
  - [x] Research **checkpoint granularity options**: per-bar (finest, highest I/O), per-N-bars (configurable batch), per-trade (natural boundary), per-optimization-parameter-set (coarsest for optimizer)
  - [x] Research **crash-safe write semantics**: write-to-temp → fsync → atomic rename pattern on Windows (NTFS rename semantics), validate with Arrow IPC writer (pyarrow and arrow-rs flush/sync APIs)
  - [x] Research **resume verification**: how to detect partial/corrupt checkpoints (file size validation, Arrow IPC footer verification, checksum approach), recovery strategy (discard partial, resume from last complete)
  - [x] Research **checkpoint file format**: extend pipeline state JSON (D3) vs separate checkpoint files per stage, include: last processed bar index, cumulative metrics snapshot, open position state, config hash for identity verification
  - [x] Research **cross-process checkpoint**: how Python orchestrator tracks Rust binary progress (periodic file writes vs stdout progress protocol vs exit code + final state file)
  - [x] Document recommended checkpoint strategy with estimated I/O overhead

- [x] **Task 5: Memory Budgeting Pattern Research** (AC: #4)
  - [x] Research **system memory inventory**: Rust APIs for querying available memory (`sysinfo` crate), Windows-specific memory APIs (`GlobalMemoryStatusEx`), reserve 2-4GB for OS per NFR4
  - [x] Research **pre-allocation strategy**: arena allocators in Rust (`bumpalo`, `typed-arena`), pre-sized `Vec::with_capacity()` for trade buffers, calculate per-thread buffer sizes (architecture target: 16 P-cores × 50MB = 800MB for trade buffers)
  - [x] Research **mmap patterns for Arrow IPC**: `memmap2` crate for memory-mapped Arrow IPC files, read-only mmap for market data (zero-copy), Windows memory-mapped file semantics and file locking
  - [x] Research **streaming result output**: write Arrow IPC results incrementally during backtest (avoid accumulating full equity curve in memory), `arrow-rs` `StreamWriter` vs `FileWriter` trade-offs, buffer flush frequency
  - [x] Research **throttle-before-OOM**: runtime memory monitoring (periodic `sysinfo` checks), batch size reduction strategy, Rayon thread pool sizing based on available memory, document trigger thresholds
  - [x] Calculate concrete memory budget for reference workload: 10-year EURUSD M1 (~400MB Arrow IPC mmap) + 16 worker threads × 50MB trade buffers + streaming output overhead

- [x] **Task 6: Architecture Alignment & Updates** (AC: #5, #6)
  - [x] Validate each research recommendation against D1 (multi-process), D2 (storage formats), D3 (state machine), D8 (error handling), D13 (cost model crate), D14 (strategy engine crate); confirm D15 (named pipes) is unaffected
  - [x] Document any deviations from architecture with evidence-based justification
  - [x] Draft specific architecture.md edits if research reveals improvements (exact line changes, not vague suggestions)
  - [x] Note which downstream stories (3.3–3.9) are affected by any proposed changes

- [x] **Task 7: Build Plan & Dependency Notes** (AC: #7)
  - [x] Create **detailed build plan for Stories 3.3–3.5** (direct consumers of research contracts):
    - 3-3: Pipeline State Machine & Checkpoint Infrastructure — approach, dependencies, which checkpoint contract consumed
    - 3-4: Python-Rust Bridge & Batch Evaluation Dispatch — approach, dependencies, which CLI/IPC contract consumed
    - 3-5: Rust Backtester Crate & Trade Simulation Engine — port vs build-new, which reproducibility/memory contracts consumed
  - [x] For Stories 3.3–3.5: components from ClaudeBackTester to port/adapt (with exact file paths), new components to build, key interfaces/contracts from this research, estimated complexity (S/M/L/XL)
  - [x] Create **dependency notes for Stories 3.6–3.9** (lighter detail):
    - 3-6: Backtest Results Artifact Storage & SQLite Ingest — upstream deps on 3.3–3.5, relevant findings
    - 3-7: AI Analysis Layer — upstream deps, relevant findings
    - 3-8: Operator Pipeline Skills — upstream deps, relevant findings
    - 3-9: E2E Pipeline Proof — integration scope, which contracts to verify
  - [x] Identify critical path dependencies between stories 3.3–3.5
  - [x] List open questions that must be resolved before implementation begins

- [x] **Task 8: Write Research Artifact** (AC: #1–#7)
  - [x] Create `_bmad-output/planning-artifacts/research/3-2-ipc-determinism-research.md` as the comprehensive research output (per architecture Phase 0 research output location)
  - [x] Use this structure (each section is mandatory):
    1. **Executive Summary** — key recommendations in ≤10 bullet points
    2. **IPC Comparison Matrix** — table with 3+ options × 6 criteria, followed by recommendation with evidence
    3. **Determinism Strategies** — concrete code patterns for each of 5 areas (floating-point, Rayon, seeds, timestamps, Windows)
    4. **Reproducibility Contract** — per-output-type (trade log, equity curve, metrics, manifest hash): bit-identical vs tolerance-based, verification method, and rationale resolving PRD vs Epic 3 tension
    5. **Checkpoint/Resume Patterns** — recommended strategy with granularity, file format, crash-safe write patterns, resume verification logic, distinction between within-stage (Rust) and cross-stage (Python orchestrator) checkpointing
    6. **Memory Budgeting** — concrete budget calculation for reference workload, pre-allocation code patterns, throttle thresholds
    7. **Architecture Alignment Matrix** — table: recommendation × D-number (D1–D14) → aligned/deviation/rationale (D15 excluded — out of scope, confirmed no impact)
    8. **Proposed Architecture Updates** — specific edits to architecture.md (if any) with diff-style changes
    9. **Downstream Contracts** — concrete interface definitions consumed by Stories 3.3–3.5:
       - Batch job CLI contract (arguments, exit codes, progress protocol)
       - Checkpoint schema (file format, identity fields, crash-safe write pattern)
       - Reproducibility policy (what is guaranteed identical, how verified)
       - Memory budget model (inputs, calculation, enforcement mechanism)
    10. **Build Plan for Stories 3.3–3.5** — detailed table: story ID, component, approach, dependencies, complexity, interface contracts consumed, questions resolved
    11. **Dependency Notes for Stories 3.6–3.9** — lighter table: story ID, upstream dependencies, relevant research findings
    12. **Open Questions** — unresolved items requiring further investigation or stakeholder input
  - [x] Include interface examples and code patterns for recommended approaches (not full compilable programs — this is a research artifact, not implementation)
  - [x] Cross-reference architecture decisions by number (D1–D14; D15 noted as out of scope)
  - [x] Cross-reference PRD requirements by number (FR14–FR19, FR42, FR58–FR61, NFR1–NFR5, NFR10–NFR15)
  - [x] This artifact is the SOLE deliverable — no production code changes except architecture.md if warranted by AC #6

- [x] **Task 9: Validate & Test** (AC: #1–#7)
  - [x] `test_ipc_recommendation_justified` — verify IPC recommendation includes benchmark method or quantitative rationale tied to repo-local constraints (existing Arrow IPC patterns, Windows subprocess behavior), not just theoretical comparison
  - [x] `test_reproducibility_contract_resolves_ambiguity` — verify the reproducibility contract explicitly resolves tolerance vs bit-identical for each output type and states how compliance is tested
  - [x] `test_determinism_strategies_actionable` — verify all 5 determinism areas have concrete strategies with code patterns or compiler flags, not just descriptions
  - [x] `test_checkpoint_schema_defined` — verify checkpoint schema includes identity fields (config hash, last processed index, open position state) and crash-safe write pattern documented with Windows NTFS specifics
  - [x] `test_memory_budget_grounded` — verify concrete memory budget calculated for reference workload using the data volume context (10-year EURUSD M1, 16 threads), with specific thresholds for throttle-before-OOM
  - [x] `test_architecture_alignment_complete` — verify D1–D14 referenced with alignment/deviation status and evidence-based rationale for any deviations; D15 confirmed out of scope
  - [x] `test_downstream_contracts_consumable` — verify batch job CLI contract, checkpoint schema, reproducibility policy, and memory budget model are defined with enough specificity that Stories 3.3–3.5 can implement against them without ambiguity
  - [x] `test_build_plan_differentiated` — verify stories 3.3–3.5 have detailed build plans with interface contracts, and stories 3.6–3.9 have dependency notes

## Dev Notes

### Architecture Constraints

- **D1 (Multi-Process with Arrow IPC):** The architecture has decided on subprocess + Arrow IPC. This research VALIDATES and HARDENS that decision with evidence — it does not re-open it. The comparison matrix exists to provide evidence supporting D1 (or, in the unlikely case research reveals a fatal flaw, to propose a specific, justified deviation). PyO3 is the ClaudeBackTester baseline being replaced; research documents why the move to subprocess + Arrow IPC is correct.
- **D2 (Arrow IPC / SQLite / Parquet Hybrid):** Three-format storage. Arrow IPC is the compute hot path (mmap-friendly, zero-copy). SQLite is derived/rebuildable. Research must account for this flow.
- **D3 (Sequential State Machine):** Pipeline state is JSON per strategy. Checkpoint/resume research must work within this model, not replace it.
- **D8 (Structured Errors at Process Boundaries):** Rust stderr produces structured JSON error objects. Research on subprocess IPC must validate this error propagation pattern.
- **D13 (Cost Model Crate):** Library crate consumed by backtester directly (inner-loop performance). NOT a separate process. Research must account for this dependency architecture.
- **D14 (Strategy Engine Shared Crate):** Core evaluation logic shared between backtester and live daemon. Signal fidelity guaranteed by identical code paths. Determinism research directly impacts this crate's implementation.
- **D15 (Named Pipes for Live Daemon):** **OUT OF SCOPE for this story.** D15 addresses live daemon IPC (Windows Named Pipes), which is a completely separate mechanism from batch IPC (Arrow files). This research focuses exclusively on batch IPC. The only D15 obligation is to confirm that batch IPC recommendations do not conflict with the live daemon path.

### Critical NFR Context

- **NFR4 (Memory Budgeting):** Pre-allocate at startup. No dynamic heap allocation on compute hot paths. If operation can't fit, reduce batch size BEFORE starting — never mid-run, never crash.
- **NFR10 (Crash Prevention):** HIGHEST-PRIORITY NFR. Resource exhaustion → throttle, reduce, pause. Never process termination.
- **NFR5 + NFR11 (Checkpoint + Resume):** Incremental checkpointing at configurable granularity. Resume from last checkpoint, not from zero.
- **NFR15 (Data Integrity):** Crash-safe write semantics. Write-ahead patterns: write-then-rename. Partial artifacts never overwrite complete ones.

### Data Volume Context

- 1 year EURUSD M1: ~525.6K bars, ~40 MB Arrow IPC
- 10 years EURUSD M1: ~5.26M bars, ~400 MB Arrow IPC
- Single backtest result: ~80 KB Arrow IPC (~500 trades × 20 fields)
- Equity curve: ~125 MB Arrow IPC (~5.26M data points × 3 fields)
- 10K optimization backtests: ~800 MB Arrow IPC total
- Total disk per full run (single strategy, single pair): ~2 GB

### What Story 3-1 Must Deliver First

Story 3-2 depends on Story 3-1's research output. Key deliverables to consume:
1. **V1 Port Boundary Table:** Keep/adapt/replace/build-new verdicts for each ClaudeBackTester component
2. **PyO3 Bridge Specification:** `batch_evaluate()` interface, 64-slot parameter layout (PL_*), numpy marshalling, rayon parallelism, exec_mode dispatch
3. **Downstream Handoff (3.2 section):** Interface candidates, migration boundaries, V1 port decisions, deferred items, open questions
4. **Lifecycle Specification:** engine.py lifecycle, encoding.py parameter layout, rust_loop.py wrapper, signal precomputation flow
5. **Metrics & Storage Specification:** Current metrics calculation, checkpoint patterns in ClaudeBackTester

**Story 3-1 is a HARD PREREQUISITE.** Do not begin Story 3-2 until Story 3-1 is complete and its research output is available. The build plan and downstream contracts produced by this story depend on 3-1's V1 Port Boundary verdicts — working without them would produce provisional results requiring rework. If `sprint-status.yaml` shows 3-1 as `ready-for-dev` or `in-progress`, STOP and wait.

### Existing Code Patterns to Reference

**Current Arrow IPC pipeline (already implemented):**
- `src/python/data_pipeline/arrow_converter.py` — DataFrame → Arrow Table → IPC file conversion
- `src/python/data_pipeline/utils/safe_write.py` — `safe_write_arrow_ipc(table, output_path)` with atomic write pattern
- Timestamps stored as int64 epoch microseconds (validated in Epic 1)

**Current subprocess patterns (already implemented):**
- `src/python/tests/test_cost_model/test_rust_crate.py` — `_run_cargo()` helper spawns Rust binaries
- `src/python/tests/test_cost_model/test_e2e.py` — `subprocess.run()` with capture_output
- Pattern: JSON via stdin/stdout + file paths for Arrow IPC data

**Rust crate workspace (already structured):**
- `src/rust/Cargo.toml` — Workspace root defining all crate members
- `src/rust/crates/cost_model/` — Library crate with CLI binary wrapper (429 lines, fully implemented)
- `src/rust/crates/strategy_engine/` — Shared crate (spec parser, indicator registry, validator)
- `src/rust/crates/backtester/` — Stub (3 lines, re-exports cost_model — implementation is Story 3-5)
- `src/rust/crates/common/` — Shared types: Arrow schemas, error types, config, logging
- `src/python/rust_bridge/__init__.py` — Empty module placeholder (intentionally not PyO3)
- Key Rust dependencies already in use: `serde`, `serde_json`, `thiserror`, `arrow` (check Cargo.toml for exact versions)

**ClaudeBackTester baseline (source for comparison):**
- `ClaudeBackTester/rust/src/lib.rs` — PyO3 `batch_evaluate()` with numpy arrays, rayon parallel execution
- `ClaudeBackTester/rust/src/constants.rs` — 64-slot parameter layout constants (PL_*)
- `ClaudeBackTester/backtester/pipeline/checkpoint.py` — Crash-safe checkpointing with 10 performance metrics
- `ClaudeBackTester/backtester/engine.py` — Python orchestration lifecycle
- `ClaudeBackTester/backtester/encoding.py` — Parameter encoding for Rust bridge

### What to Reuse from ClaudeBackTester

| Component | Verdict | Notes |
|-----------|---------|-------|
| `batch_evaluate()` interface | **Analyze, don't port** | PyO3 approach being replaced by subprocess + Arrow IPC. Study for parameter flow understanding |
| 64-slot parameter layout | **Analyze, don't port** | Strategy engine crate (D14) uses TOML spec, not fixed-slot encoding |
| Rayon parallelism | **Port pattern** | Same parallel iteration approach, but research deterministic ordering |
| Checkpoint logic | **Adapt** | Python-side checkpoint.py has proven patterns; adapt for Rust-side implementation |
| 10 performance metrics | **Port calculations** | Win rate, profit factor, Sharpe, R², max drawdown — same formulas needed |
| Trade simulation loop | **Port to Rust** | Core backtest loop moves from hybrid Python/Rust to pure Rust (Story 3-5) |

### Anti-Patterns to Avoid

1. **Don't assume PyO3 is the answer** — The architecture (D1) explicitly chose subprocess + Arrow IPC for crash isolation. Research must validate this with evidence, not default to the ClaudeBackTester's PyO3 approach.
2. **Don't ignore Windows-specific behavior** — This runs on Windows 11 with Git Bash. File locking, mmap semantics, NTFS atomic rename, MSVC toolchain quirks all matter.
3. **Don't research in isolation from existing code** — The project already has Arrow IPC writing, subprocess spawning, and Rust crate patterns. Build on what exists.
4. **Don't produce theoretical research without actionable code patterns** — Every recommendation must include concrete Rust/Python code snippets or compiler flags the dev agent can copy.
5. **Don't scope-creep into implementation** — This is a research story. Output is a research artifact document. No production code changes except architecture.md updates if warranted.
6. **Don't assume full Rust migration** — Story 3-1's V1 Port Boundary may recommend keeping some components in Python. Await those findings.
7. **Don't optimize for optimization** — V1 gates on reproducibility and evidence quality, NOT optimization sophistication (per PRD). Focus IPC research on backtest hot path, not optimizer parallelism.
8. **Don't conflate batch IPC with live IPC** — Batch backtesting uses Arrow IPC files (D1). Live daemon uses Named Pipes (D15). These are separate mechanisms for separate use cases.
9. **Don't produce research without consumable contracts** — Stories 3.3–3.5 need specific interface definitions (CLI contract, checkpoint schema, reproducibility policy, memory budget model) they can implement against. Broad research findings without concrete contracts will cause each downstream story to invent its own interface, leading to drift.

### Project Structure Notes

**Research artifact output location:**
- `_bmad-output/planning-artifacts/research/3-2-ipc-determinism-research.md` — Primary research deliverable (per architecture Phase 0 research process)

**Files to read (not modify):**
- `_bmad-output/implementation-artifacts/3-1-claudebacktester-backtest-engine-review.md` — Story 3-1 output
- `_bmad-output/planning-artifacts/architecture.md` — Architecture decisions D1–D15
- `_bmad-output/planning-artifacts/prd.md` — FR and NFR requirements
- `src/python/data_pipeline/arrow_converter.py` — Existing Arrow IPC patterns
- `src/python/data_pipeline/utils/safe_write.py` — Existing safe write patterns
- `src/rust/crates/cost_model/src/lib.rs` — Existing Rust crate interface pattern
- `src/rust/crates/backtester/src/lib.rs` — Backtester stub (context for Story 3-5)
- `ClaudeBackTester/rust/src/lib.rs` — Baseline PyO3 bridge
- `ClaudeBackTester/backtester/pipeline/checkpoint.py` — Baseline checkpoint logic

**Files that MAY be modified:**
- `_bmad-output/planning-artifacts/architecture.md` — ONLY if research reveals warranted updates (AC #6)

**Directory to create:**
- `_bmad-output/planning-artifacts/research/` — If not already present, create for Phase 0 research artifact output

### References

- [Source: _bmad-output/planning-artifacts/architecture.md — D1: System Topology — Multi-Process with Arrow IPC]
- [Source: _bmad-output/planning-artifacts/architecture.md — D2: Artifact Schema & Storage]
- [Source: _bmad-output/planning-artifacts/architecture.md — D3: Pipeline Orchestration — Sequential State Machine]
- [Source: _bmad-output/planning-artifacts/architecture.md — D8: Error Handling Strategy]
- [Source: _bmad-output/planning-artifacts/architecture.md — D13: Cost Model Crate]
- [Source: _bmad-output/planning-artifacts/architecture.md — D14: Strategy Engine Shared Crate]
- [Source: _bmad-output/planning-artifacts/architecture.md — D15: Live Daemon Communication — Named Pipes]
- [Source: _bmad-output/planning-artifacts/prd.md — FR14-FR19: Backtesting Requirements]
- [Source: _bmad-output/planning-artifacts/prd.md — FR18: Deterministic Reproducibility]
- [Source: _bmad-output/planning-artifacts/prd.md — FR42: Resume Interrupted Pipeline Runs]
- [Source: _bmad-output/planning-artifacts/prd.md — FR58-FR61: Reproducibility Requirements]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR1-NFR5: Performance Requirements]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR4: Deterministic Memory Budgeting]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR10: Crash Prevention (Highest Priority)]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR11: Crash Recovery]
- [Source: _bmad-output/planning-artifacts/prd.md — NFR15: Data Integrity]
- [Source: _bmad-output/planning-artifacts/epics.md — Epic 3: Backtesting & Pipeline Operations]
- [Source: _bmad-output/implementation-artifacts/3-1-claudebacktester-backtest-engine-review.md — Story 3-1 Research Output]
- [Source: reviews/story-reviews/story-3-1-claudebacktester-backtest-engine-review-codex-review.md — Codex Review Findings]
- [Source: reviews/story-reviews/3-1-claudebacktester-backtest-engine-review-synthesis-report.md — Synthesis Report]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (1M context)

### Debug Log References

- All 81 tests pass (78 unit + 3 live) — `pytest src/python/tests/test_research/test_story_3_2_ipc_determinism_research.py -v` → 78 passed, 3 skipped; with `-m live` → 3 passed

### Completion Notes List

- ✅ Comprehensive research artifact written: 12 mandatory sections + 2 appendices, ~650 lines at `_bmad-output/planning-artifacts/research/3-2-ipc-determinism-research.md`
- ✅ IPC comparison matrix: 3 options (PyO3 FFI, Subprocess+Arrow IPC, Shared Memory) × 7 criteria with weighted scoring. Subprocess+Arrow IPC recommended (8.90/10) — validated D1 with quantitative evidence
- ✅ Deterministic backtesting: 5 areas with concrete code patterns and compiler flags — FMA disabled via `.cargo/config.toml`, `IndexedParallelIterator` with fixed chunks for Rayon, `ChaCha8Rng` for seeds, int64 μs UTC timestamps, Windows MSVC/NTFS specifics
- ✅ Reproducibility Contract resolves PRD "defined tolerance" vs Epic 3 "bit-identical": trade logs, equity curves, metrics = bit-identical (SHA-256 verified); manifest hashes = tolerance-based (temporal fields excluded). Verification protocol defined for Story 3-9
- ✅ Checkpoint/resume: two-level strategy — within-stage (Rust, per-batch for optimization) + cross-stage (Python orchestrator, per-stage). Crash-safe write (temp→fsync→atomic rename) with NTFS specifics. Resume verification via Arrow IPC footer + config hash match
- ✅ Memory budget: concrete calculation for 10yr EURUSD M1 reference workload — ~1.5GB active heap (800MB trade buffers + 200MB working + overhead), 400MB mmap (not counted), 2-4GB OS reserve. Throttle-before-OOM thresholds at 4 levels
- ✅ Architecture alignment: all recommendations aligned with D1-D14, no deviations. D15 confirmed no impact. Story 3-1 proposed updates (9.1-9.4) validated
- ✅ Four downstream contracts defined: (1) Batch job CLI contract with args, exit codes, progress protocol; (2) Checkpoint schema with identity fields; (3) Reproducibility policy; (4) Memory budget model with inputs/calculation/enforcement
- ✅ Build plan: Stories 3.3→3.4→3.5 critical path with complexity estimates (L/L/XL). 6 Rust files to port, 7 new components to build (~1300 LOC estimated)
- ✅ Dependency notes for Stories 3.6-3.9 with upstream dependencies and relevant findings
- ✅ 5 open questions documented with recommendations for each
- ✅ 81 tests: 78 unit tests (8 test classes mapping to 8 AC-specific test requirements) + 3 @pytest.mark.live tests
- ✅ No production code changes — research artifact is the sole deliverable. No architecture.md changes needed (all recommendations fit within existing decisions)

### File List

- `_bmad-output/planning-artifacts/research/3-2-ipc-determinism-research.md` — Primary research artifact (NEW)
- `src/python/tests/test_research/test_story_3_2_ipc_determinism_research.py` — Test suite: 78 unit + 3 live tests (NEW)
- `_bmad-output/implementation-artifacts/3-2-python-rust-ipc-deterministic-backtesting-research.md` — Story file (MODIFIED: tasks checked, dev record, status)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — Sprint status (MODIFIED: 3-2 → review)

### Change Log

- 2026-03-18: Story 3-2 implementation complete. Research artifact with 12 sections covering IPC, determinism, checkpoint, memory, architecture alignment, build plan, and downstream contracts. 81 tests all passing.
