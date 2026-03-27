# PIR: Story 3-4-python-rust-bridge-batch-evaluation-dispatch — Story 3.4: Python-Rust Bridge — Batch Evaluation Dispatch

**Reviewer:** Claude Opus 4.6 (1M context)
**Date:** 2026-03-18
**Type:** Post-Implementation Review (final alignment decision)

---

## Codex Assessment Summary

Codex rated **Objective Alignment: ADEQUATE**, **Simplification: CONCERN**, **Forward Look: CONCERN**, with an overall verdict of **REVISIT**. Key observations and my assessment of each:

### 1. Subprocess + D8 errors + crash-safe writes are well-aligned
**Codex says:** Process boundary, structured errors, and write→fsync→rename pattern directly serve reproducibility and crash isolation (D1, D8, NFR15).
**I AGREE.** The implementation is faithful to the architecture. The Rust binary uses `clap` for a clean CLI contract, `StructuredError` maps to exactly three D8 categories, and Python's `error_parser.py` correctly routes them to orchestrator recovery actions. The crash-safe write pattern is consistent across `progress.rs`, `output.rs`, and `forex_backtester.rs`. This is the core value of Story 3-4 and it delivers.

### 2. Arrow outputs are JSON placeholders, conflicting with PRD evidence quality
**Codex says:** The `.arrow` files are JSON stubs, `validate_schemas()` is existence-only, conflicting with PRD's emphasis on reviewable evidence packs.
**I PARTIALLY DISAGREE.** The story spec explicitly states: *"Do NOT implement trade simulation in this story — that's Story 3-5. The backtester binary can start as a stub."* The synthesis report also rejected this concern with the same reasoning. The PRD's evidence quality objectives are served by the *full pipeline*, not by this single bridge story. The stub nature is architecturally correct for this scope. However, I note the `.arrow` extension on JSON files is a naming hazard — the synthesis correctly fixed the misleading comments, but automated tools could still be confused. The stub outputs should have been named `.arrow.stub` or similar to make their placeholder nature unmistakable.

### 3. Progress reporting is only synthetic start/end
**Codex says:** `total_bars = 1` and zero ETA is weak support for FR40 stage status.
**I DISAGREE.** The `should_report()` throttling function is implemented in `progress.rs` with configurable bar-count and time-interval triggers. There is no bar-processing loop yet because trade simulation is Story 3-5. The infrastructure is correctly in place; it simply has nothing to drive it yet. This is the expected state for a stub binary.

### 4. Arrow schema layer exists but runtime doesn't use it
**Codex says:** `arrow_schemas.rs` defines schemas that nothing validates against at runtime; the verifier is existence-only; `verify_fold_scores()` expects a file nobody produces. This is over-engineering.
**I PARTIALLY DISAGREE.** The schemas are architecture-mandated infrastructure (D2: "Schema SSOT: `contracts/arrow_schemas.toml`"). They must exist before Story 3-5 can write real Arrow IPC. The `verify_fold_scores()` function is forward infrastructure for fold-aware evaluation, which the CLI already accepts as arguments. These are *foundational* pieces, not premature abstractions. That said, Codex is right that `BacktestOutputRef` is constructed by `verify_output()` but then only its `output_dir` is used — the individual path fields are wasted. This is a minor inefficiency, not a design problem.

### 5. Output contract is weak — manifest_ref=None, no settled fold artifacts
**Codex says:** `manifest_ref=None` by design, but architecture expects manifest-backed reproducibility proof. No producer writes `fold-scores.json` despite verifier expecting it.
**I PARTIALLY AGREE.** The `manifest_ref=None` is explicitly documented: *"manifest_ref (None — manifest created by Story 3.6)"*. This is correct scope bounding. However, the `verify_fold_scores()` function existing without any producer is premature — it creates a false impression of completeness and adds dead code. It would have been cleaner to add this verification when Story 3-5 actually produces fold outputs. This is a minor simplification opportunity, not a structural concern.

### 6. Orchestration identity is thin — cancel() prefix-matches
**Codex says:** `dispatch()` creates internal unique key but `cancel()` only prefix-matches, which is brittle for batch evaluation growth.
**I AGREE this is a design smell, but DISAGREE on severity.** The synthesis already fixed the collision issue (config_hash + uuid key). The prefix-match cancellation is adequate for the current single-job model. When batch evaluation grows in Epic 4/5, the cancellation interface will need revision regardless. This is a reasonable deferral.

### 7. Placeholder .arrow files risk harming operator trust
**Codex says:** The biggest baked-in assumption is that placeholder files can stand in without harming trust.
**I DISAGREE on framing.** These placeholders never reach the operator. They exist in the output directory for the bridge to verify the dispatch→output→verify flow works. Story 3-5 replaces them with real data. Story 3-6 creates the manifest. Story 3-7+ surfaces results to the operator. The operator never sees `.arrow` stubs.

---

## Objective Alignment
**Rating:** ADEQUATE

This story serves the following system objectives:

- **Reproducibility (FR18, FR61):** The subprocess boundary with deterministic CLI arguments, crash-safe writes, and config_hash tracing establish the reproducibility infrastructure. The actual byte-identical output guarantee is deferred to Story 3-5 (correctly).
- **Crash isolation (D1, NFR10):** Process isolation is complete — Python spawns Rust as a subprocess, captures structured errors on stderr, and continues running on crash. This is the core architectural requirement and it's solidly implemented.
- **Artifact integrity (NFR15):** The write→fsync→rename pattern is implemented across all output paths. No `.partial` files remain on success.
- **Error propagation (D8):** Three-category structured errors flow correctly from Rust → stderr JSON → Python `parse_rust_error()` → `map_to_pipeline_error()` → orchestrator recovery actions.
- **Memory safety (NFR4):** Pre-allocation at startup with OS reserve margin, batch size reduction on tight budget, no dynamic allocation on hot path.

**What this story does NOT yet serve** (correctly deferred):
- Evidence quality / reviewable evidence packs → Story 3-5 (real outputs), Story 3-6 (manifests)
- Operator-facing progress visibility → Story 3-5 (actual bar processing drives `should_report()`)
- Arrow IPC validation against schemas → Story 3-5 (real Arrow writing enables real validation)

The story achieves its stated scope: *"Python can drive Rust safely and deterministically as a process boundary."* The deferred items are all explicitly scoped to downstream stories per the epic plan.

---

## Simplification
**Rating:** ADEQUATE

The core bridge architecture is appropriately sized:
- **BatchRunner** — clean async subprocess dispatch with timeout, cancellation, progress polling
- **ErrorParser** — minimal, focused D8→PipelineError mapping
- **BacktestExecutor** — thin StageExecutor adapter bridging async/sync boundary
- **forex_backtester CLI** — clap-derived args matching the published CLI contract

Areas where simplification was possible but not critical:
1. **`verify_fold_scores()` without a producer** — Dead code that should have been deferred to Story 3-5. Not harmful but unnecessary.
2. **`BacktestOutputRef` fields unused by `BacktestExecutor`** — The ref is created but only `output_dir` matters. Could have been a simple path return for now.
3. **`arrow_schemas.rs` without runtime consumers** — This is architecture-mandated infrastructure, not premature abstraction. It defines the contract that Story 3-5 must implement against.

None of these rise to the level of over-engineering. The subprocess boundary itself — which is the hard part of this story — is well-designed with no unnecessary complexity.

---

## Forward Look
**Rating:** STRONG

This story sets up downstream stories effectively:

- **Story 3-5 (Trade Simulation):** The CLI contract is established (`forex_backtester.rs` Args struct). The output writer interface (`write_results()`) accepts the output directory and config_hash. The progress infrastructure (`should_report()`, `write_progress()`) is ready to be called from the processing loop. The memory budget (`compute_batch_size()`) returns the batch size for the simulation to use. Story 3-5 can replace stub implementations without changing any interface.
- **Story 3-6 (Artifact Management):** `BacktestExecutor` returns `manifest_ref=None` with a clear comment that Story 3-6 creates it. The `BacktestOutputRef` dataclass already has the right shape for manifest creation.
- **Story 3-3 Integration:** The `StageExecutor` protocol is correctly implemented. `BacktestExecutor.execute()` returns `StageResult` with proper outcome/metrics/error fields. Error propagation through `PipelineError` is wired.
- **Fold-aware evaluation (Epic 4/5):** CLI args for `--fold-boundaries`, `--embargo-bars`, `--window-start`, `--window-end`, `--param-batch` are parsed and validated. The plumbing is in place even though processing is deferred.

**One concern:** The `arrow` crate is intentionally not in `Cargo.toml` (the synthesis report rejected adding it since nothing imports it). Story 3-5 must add it. This is documented in the synthesis action items but could be missed if someone doesn't read the synthesis report. The story's Task 12 completion note incorrectly claims `arrow = "53"` was added — this documentation inaccuracy could cause confusion.

---

## Observations for Future Stories

1. **Stub file naming convention:** When a story produces placeholder files that will be replaced by a later story, use a distinct extension (e.g., `.arrow.stub`) rather than the final extension. This prevents automated tools from trying to parse them and makes the placeholder nature visible without reading comments.

2. **Don't ship verifiers for outputs that don't exist yet:** `verify_fold_scores()` verifies `fold-scores.json` but no story in Epic 3 produces it. Ship the verification function in the same story that ships the producer. This reduces dead code and false completeness signals.

3. **Task completion notes must match reality:** The Dev Agent Record claims `arrow = "53"` was added to Cargo.toml, but the synthesis report correctly rejected this. Completion notes that don't match the final code state erode trust in the dev record. Future stories should verify completion notes against the final committed state.

4. **Windows CTRL_BREAK cancellation remains deferred:** `process.terminate()` on Windows calls `TerminateProcess()`, not `GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT)`. This means graceful checkpoint-on-cancel (AC #5) doesn't work on Windows. This is documented in the synthesis action items but should be tracked as a cross-cutting concern, not just a Story 3-5 item. It affects any story that relies on graceful Rust cancellation.

5. **Consistency pattern: OS reserve margin.** The synthesis correctly fixed Python's memory pre-check to subtract `OS_RESERVE_MB = 2048` matching Rust's `OS_RESERVE_MB: u64 = 2048`. This cross-language constant duplication is a maintenance risk. Future stories should consider a shared constant in `contracts/` (like `arrow_schemas.toml` serves for schemas).

---

## Verdict

**VERDICT: OBSERVE**

Story 3-4 delivers its core mission: a working Python-Rust subprocess bridge with structured error handling, crash isolation, crash-safe writes, and memory budget enforcement. The architecture's most critical requirement — process boundary with no FFI — is faithfully implemented. The StageExecutor integration, D8 error routing, and CLI contract are all correctly wired for downstream consumption.

Codex's REVISIT verdict overweights the placeholder nature of outputs, which is explicitly by design for a bridge/dispatch story that precedes the trade simulation story. The evidence quality, operator visibility, and Arrow IPC validation gaps that Codex flags are all correctly scoped to Stories 3-5, 3-6, and 3-7.

The observations above (stub naming, premature verifiers, completion note accuracy, Windows cancellation) are worth noting for future story writing but do not constitute alignment concerns. The bridge infrastructure is solid and downstream stories can build on it without interface churn.
