# Story 3-4-python-rust-bridge-batch-evaluation-dispatch: Story 3.4: Python-Rust Bridge — Batch Evaluation Dispatch — Codex PIR

**Reviewer:** Codex GPT-5.4 (high effort, read-only sandbox)
**Date:** 2026-03-18
**Type:** Post-Implementation Review (alignment analysis)

---

**1. Objective Alignment**  
Assessment: `ADEQUATE`

Specific evidence:
- The strongest alignment is on process reproducibility and crash isolation: the architecture requires subprocess + Arrow IPC + structured stderr errors ([architecture.md#L290](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L290), [architecture.md#L314](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L314)), and this is implemented through the CLI wrapper and D8 error mapping in [forex_backtester.rs#L74](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L74), [error_types.rs#L19](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/common/src/error_types.rs#L19), and [error_parser.py#L99](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/error_parser.py#L99).
- Crash-safe artifact handling is real and directly supports NFR15/artifact integrity: progress, checkpoint, and result files all use write → fsync → rename in [progress.rs#L22](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/progress.rs#L22), [forex_backtester.rs#L248](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L248), and [output.rs#L87](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/output.rs#L87).
- The main objective gap is evidence quality: the “Arrow” outputs are explicitly JSON placeholders, not Arrow IPC ([output.rs#L41](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/output.rs#L41)), while `validate_schemas()` only checks existence/non-empty files ([output_verifier.py#L94](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/output_verifier.py#L94)). That conflicts with the PRD’s emphasis on reviewable evidence packs and reproducible stage artifacts ([prd.md#L83](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L83), [prd.md#L99](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L99), [prd.md#L517](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L517)).
- Operator-facing progress is only synthetic start/end status with `total_bars = 1` and zero ETA in [forex_backtester.rs#L184](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L184) and [forex_backtester.rs#L218](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L218), which is weak support for FR40 stage status visibility ([prd.md#L518](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/prd.md#L518)).

Concrete observations:
- This story materially improves “Python can drive Rust safely and deterministically as a process boundary.”
- It does not yet materially improve “the backtest stage emits trustworthy review evidence,” which is central to V1.
- It mostly fits V1 scope because the story explicitly allows a stub bridge and defers trade simulation to Story 3.5 ([3-4 story#L539](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-4-python-rust-bridge-batch-evaluation-dispatch.md#L539)). The fold/window/batch args are architecture-driven, not gratuitous ([3-4 story#L10](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-4-python-rust-bridge-batch-evaluation-dispatch.md#L10), [architecture.md#L288](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L288), [architecture.md#L346](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L346)).

**2. Simplification**  
Assessment: `CONCERN`

Specific evidence:
- There is a schema layer in [arrow_schemas.rs#L1](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/common/src/arrow_schemas.rs#L1), but the runtime neither writes real Arrow from it nor validates against it; the writer emits JSON stubs ([output.rs#L49](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/output.rs#L49)) and the verifier is existence-only ([output_verifier.py#L94](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/output_verifier.py#L94)).
- `verify_fold_scores()` expects `fold-scores.json` ([output_verifier.py#L111](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/output_verifier.py#L111)), even though the story’s published deterministic outputs are only the three `.arrow` files ([3-4 story#L473](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/implementation-artifacts/3-4-python-rust-bridge-batch-evaluation-dispatch.md#L473)) and the architecture treats Arrow IPC as the canonical compute artifact format ([architecture.md#L360](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L360)).
- `BacktestOutputRef` is created in [output_verifier.py#L23](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/output_verifier.py#L23), but `BacktestExecutor` discards it and returns only the directory path plus minimal metrics ([backtest_executor.py#L137](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/backtest_executor.py#L137)).

Concrete observations:
- A simpler story could have delivered subprocess dispatch, D8 errors, crash-safe progress/checkpointing, and clearly-labeled placeholder outputs, while deferring schema and fold-output abstractions until real Arrow writing exists.
- The subprocess boundary itself is not over-engineered; the unnecessary complexity is the pseudo-Arrow validation layer that looks more complete than it is.
- Some of this code is likely transitional rather than foundational.

**3. Forward Look**  
Assessment: `CONCERN`

Specific evidence:
- The good part is stable process/error plumbing for downstream stories: CLI args in [forex_backtester.rs#L22](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L22), shared D8 categories in [error_types.rs#L95](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/common/src/error_types.rs#L95), and Python mapping in [error_parser.py#L99](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/error_parser.py#L99).
- The weak part is the output contract: `manifest_ref=None` by design in [backtest_executor.py#L137](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/backtest_executor.py#L137), while architecture expects manifest-backed reproducibility proof and published-artifact consumption ([architecture.md#L558](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L558), [architecture.md#L1361](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L1361), [architecture.md#L1422](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L1422)).
- Fold-aware downstream needs are not really established yet: the binary only parses fold JSON ([forex_backtester.rs#L124](/c/Users/ROG/Projects/Forex Pipeline/src/rust/crates/backtester/src/bin/forex_backtester.rs#L124)), the verifier assumes `fold-scores.json` ([output_verifier.py#L120](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/output_verifier.py#L120)), and no producer writes it, despite architecture expecting per-fold scores as artifacts ([architecture.md#L439](/c/Users/ROG/Projects/Forex Pipeline/_bmad-output/planning-artifacts/architecture.md#L439)).
- Orchestration identity is thin: `dispatch()` creates an internal unique process key ([batch_runner.py#L154](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/batch_runner.py#L154)), but `cancel()` only prefix-matches a caller-supplied id and no durable job handle is returned ([batch_runner.py#L206](/c/Users/ROG/Projects/Forex Pipeline/src/python/rust_bridge/batch_runner.py#L206)). That is brittle once true batch evaluation grows.

Concrete observations:
- This story does set up next stories to avoid interface churn around spawning Rust and routing failures.
- It does not yet give downstream evidence-pack/artifact stories what they actually need: valid Arrow IPC, contract-validated schemas, manifest/data hashes, and settled fold-output artifacts.
- The biggest baked-in assumption is that placeholder `.arrow` files can temporarily stand in for published stage artifacts without harming operator trust. That assumption is risky.

**Overall**  
Assessment: `REVISIT`

The bridge scaffolding is directionally aligned, but as implemented it still leaves significant gaps against BMAD Backtester’s actual V1 gates: reproducible evidence, operator confidence, and artifact completeness. The placeholder artifact layer is the main reason.
