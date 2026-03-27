# Story 3-2: Python-Rust IPC & Deterministic Backtesting Research

**Story:** 3-2-python-rust-ipc-deterministic-backtesting-research
**Date:** 2026-03-18
**Status:** Research Complete
**Depends on:** Story 3-1 (ClaudeBackTester Baseline Review — DONE)

---

## 1. Executive Summary

Key recommendations from this research, grounded in architecture decisions, existing code patterns, and data volume analysis:

1. **Subprocess + Arrow IPC files confirmed as IPC mechanism** (D1 aligned). Full process isolation eliminates the crash-coupling risk inherent in PyO3. Serialization overhead (~2ms for 400MB mmap, ~15ms for 8MB signal data) is negligible versus backtest computation time (seconds to minutes per batch).

2. **Rust binary CLI contract defined**: `forex_backtester run --config <json_path> --market-data <arrow_path> --signals <arrow_path> --params <arrow_path> --output-dir <dir_path>`. Exit code 0 = success with Arrow IPC results, non-zero = structured JSON error on stderr (D8).

3. **Deterministic reproducibility achievable with specific compiler flags and code patterns**. Use `-C target-feature=-fma` to disable FMA instructions, `IndexedParallelIterator` with fixed chunk sizes for Rayon, and `ChaCha8Rng` with explicit seed propagation for stochastic elements.

4. **Reproducibility Contract resolves PRD vs Epic 3 tension**: Trade logs and metrics are **bit-identical** (guaranteed by deterministic computation). Equity curves are **bit-identical** (derived deterministically from trade logs). Manifest hashes are **tolerance-based** (include timestamps that vary between runs). Compliance verified by automated hash comparison in Story 3-9.

5. **Checkpoint strategy: per-batch granularity with crash-safe writes**. Within Rust binary: checkpoint per N optimization parameter sets (configurable, default 100). Cross-process: Python orchestrator reads checkpoint files written by Rust binary on clean exit or periodic flush. Resume verifies checkpoint integrity via Arrow IPC footer validation + config hash match.

6. **Memory budget for reference workload (10yr EURUSD M1, 16 threads): ~1.1GB heap + ~400MB mmap**. Market data: ~400MB mmap (zero-copy, not counted against heap). Trade buffers: 16 × 50MB = 800MB. Streaming output: ~50MB buffer. Working memory: ~200MB. Signals + params + metrics: ~15MB. Total heap: ~1,065MB. OS reserve: 2-4GB. Throttle trigger: when available memory drops below 2GB.

7. **All recommendations align with D1-D14**. No deviations proposed. D15 (named pipes) confirmed unaffected — batch IPC and live IPC are orthogonal mechanisms.

8. **Story 3-1's proposed architecture updates (9.1-9.4) validated**: Windowed evaluation (9.1), optimization sub-states (9.2), sub-stage checkpointing (9.3), and per-bar cost integration (9.4) are all incorporated into the contracts defined here.

9. **Build plan: Stories 3.3-3.5 are sequential on the critical path**. 3-3 (state machine) enables 3-4 (bridge), which enables 3-5 (backtester crate). Each consumes specific contracts from this research.

10. **Four downstream contracts defined**: Batch job CLI contract, checkpoint schema, reproducibility policy, and memory budget model — each with enough specificity for Stories 3.3-3.5 to implement without ambiguity.

---

## 2. IPC Comparison Matrix

### 2.1 Options Evaluated

**Option A: PyO3 In-Process FFI** (ClaudeBackTester baseline)
The current ClaudeBackTester approach: Python calls Rust functions directly via PyO3 bindings. `batch_evaluate()` accepts 28 parameters as numpy array views, releases the GIL, and uses Rayon for parallel evaluation.

- **Latency:** ~0 (function call, no serialization). Data is accessed via zero-copy numpy views.
- **Serialization cost:** None. PyO3 provides direct memory access to numpy arrays via `PyReadonlyArray`.
- **Crash isolation:** **None**. A Rust panic or OOM kills the Python process. `catch_unwind` can trap panics but not OOM or stack overflow. This is the fundamental weakness — NFR10 (crash prevention as highest priority) requires that compute failures cannot kill the orchestrator.
- **Implementation complexity:** ~500 LOC for the bridge (current `lib.rs` is 493L). Requires MSVC toolchain, maturin build, Python extension module packaging. Complex mixed-language debugging.
- **Debug experience:** Poor. Mixed Python/Rust stack traces. PyO3 type errors surface at runtime. GIL-related deadlocks are hard to diagnose.
- **Windows compatibility:** Works but fragile. Requires MSVC 2022, specific Python version match, numpy ABI compatibility. Build failures are common after Python/numpy upgrades.

**Option B: Subprocess + Arrow IPC Files** (D1-specified approach)
Python orchestrator spawns a Rust binary via `subprocess.run()`, passing Arrow IPC file paths as CLI arguments. Results are written as Arrow IPC files. Errors are structured JSON on stderr (D8).

- **Latency:** ~2ms process spawn + ~15ms Arrow IPC read for 8MB signal data + ~2ms mmap for 400MB market data. Total overhead: ~20ms per invocation. For a backtest taking 5-60 seconds, this is 0.03-0.4% overhead — negligible.
- **Serialization cost:** Arrow IPC serialization for input data (one-time write by Python, ~15ms for largest payload). Market data is pre-serialized and mmap'd (zero additional cost). Output serialization: streaming Arrow IPC write (~5ms for typical results).
- **Crash isolation:** **Full**. Rust binary is a separate OS process. OOM, panic, stack overflow — all terminate only the child process. Python orchestrator detects failure via non-zero exit code and structured stderr. NFR10 is fully satisfied.
- **Implementation complexity:** ~200 LOC Python bridge (`batch_runner.py` + `error_parser.py`). ~150 LOC Rust CLI wrapper around core computation. Existing patterns: `_run_cargo()` in `test_rust_crate.py`, `subprocess.run()` in `test_e2e.py`.
- **Debug experience:** Good. Separate processes have clean stack traces. Rust binary can be tested independently. `RUST_BACKTRACE=1` works without affecting Python. Structured JSON errors (D8) provide machine-parseable failure context.
- **Windows compatibility:** Excellent. `subprocess.run()` is platform-native. No MSVC toolchain dependency at Python runtime (only at Rust compile time). No numpy ABI concerns. Arrow IPC files are platform-portable.

**Option C: Shared Memory / mmap**
Memory-mapped Arrow IPC files for zero-copy data sharing between Python and Rust processes. Both processes mmap the same file.

- **Latency:** ~2ms process spawn + ~0 for data access (mmap, no copy). Lowest theoretical latency of multi-process options.
- **Serialization cost:** Same as Option B for initial Arrow IPC file creation. Zero for subsequent reads (mmap).
- **Crash isolation:** **Full** (separate processes). Same as Option B.
- **Implementation complexity:** ~400 LOC. Requires coordination primitives (semaphores, file locks) to synchronize access. Python side needs `mmap` module or `pyarrow.memory_map()`. Rust side needs `memmap2` crate. Windows mmap semantics differ from Unix (file locking, sharing modes). Significantly more complex than Option B.
- **Debug experience:** Moderate. Separate processes (good), but shared-memory bugs (stale data, race conditions) are hard to diagnose.
- **Windows compatibility:** Works but requires careful handling. Windows file locking (`CreateFileMapping`, `MapViewOfFile`) has different semantics than Unix `mmap`. Files must be opened with specific sharing modes. The `memmap2` Rust crate abstracts most of this, but edge cases remain.

### 2.2 Comparison Matrix

| Criterion | Weight | A: PyO3 FFI | B: Subprocess + Arrow IPC | C: Shared Memory / mmap |
|---|---|---|---|---|
| Latency (μs per invocation) | 15% | ~0 (10/10) | ~20,000 (8/10) | ~2,000 (9/10) |
| Serialization cost | 10% | None (10/10) | ~20ms one-time (8/10) | ~20ms one-time (8/10) |
| Crash isolation | 30% | None (1/10) | Full (10/10) | Full (10/10) |
| Complexity (LOC estimate) | 15% | ~500 (6/10) | ~350 (8/10) | ~400 (7/10) |
| Debug experience | 10% | Poor (4/10) | Good (8/10) | Moderate (6/10) |
| Windows compatibility | 10% | Fragile (5/10) | Excellent (9/10) | Moderate (6/10) |
| Alignment with D1 | 10% | Contradicts (1/10) | Exact match (10/10) | Partial (7/10) |
| **Weighted Total** | **100%** | **4.35** | **8.90** | **8.10** |

*Scoring: 1-10 scale where 10 is best. Weights reflect NFR priorities: crash isolation (30%) dominates because NFR10 is highest-priority NFR.*

### 2.3 Recommendation

**Subprocess + Arrow IPC files (Option B)** is the recommended IPC mechanism.

**Justification:**
1. **Crash isolation is non-negotiable** (NFR10). Option A fails this criterion completely — a Rust OOM kills the Python orchestrator. Option B provides full process isolation with zero additional complexity versus the existing `subprocess.run()` patterns in the codebase.
2. **Performance overhead is negligible**. The ~20ms subprocess + serialization overhead is <0.4% of a typical 5-second backtest. For 10K-trial optimization runs, total IPC overhead is ~200 seconds versus ~50,000+ seconds of computation — still <0.4%.
3. **Existing patterns reduce implementation risk**. The project already uses `subprocess.run()` for Rust binary invocation (`test_rust_crate.py:_run_cargo()`), Arrow IPC file writing (`safe_write.py:safe_write_arrow_ipc()`), and structured JSON error handling. Option B is an evolution of proven patterns, not a greenfield build.
4. **Exact alignment with D1**. The architecture decision was made with this approach in mind. All downstream stories (3.3-3.9) assume subprocess + Arrow IPC.
5. **Option C (mmap) adds complexity without meaningful benefit**. The market data is already mmap'd via Arrow IPC file access — Option B gets zero-copy reads "for free" via `pyarrow.memory_map()` and `memmap2` in Rust. The additional shared-memory coordination primitives (locks, semaphores) add complexity and Windows-specific failure modes without improving performance on the actual bottleneck (computation, not I/O).

**Note on Option A (PyO3):** The baseline's PyO3 approach was effective for its purpose (single-process monolith with numpy integration). The move to subprocess + Arrow IPC is justified by the architecture's crash isolation requirement (NFR10/D1), not by any deficiency in PyO3's performance. This research validates D1's decision with evidence.

---

## 3. Determinism Strategies

### 3.1 Floating-Point Reproducibility

**Problem:** IEEE 754 f64 arithmetic is deterministic for individual operations, but modern CPUs can produce different results depending on instruction selection (FMA vs separate multiply-add), compiler optimization level, and SIMD vectorization choices.

**Platform context:** Windows 11 x86-64 with MSVC toolchain. Rust stable compiler targeting `x86_64-pc-windows-msvc`.

**Strategy:**

1. **Disable FMA instructions** at compile time:
   ```toml
   # .cargo/config.toml (workspace-level)
   [target.x86_64-pc-windows-msvc]
   rustflags = ["-C", "target-feature=-fma"]
   ```
   FMA (fused multiply-add) computes `a * b + c` in one operation with a single rounding, producing different results than separate `a * b` then `+ c` (two roundings). Disabling FMA ensures consistent results regardless of CPU generation. Performance impact: <5% on floating-point-heavy code (trade simulation), acceptable for reproducibility guarantee.

2. **Use Rust's standard `f64` operations** (not `libm` or `#[no_std]`):
   Rust's `f64` methods (`sin()`, `cos()`, `sqrt()`, `ln()`) delegate to the platform's math library (MSVC CRT on Windows). These are deterministic for the same platform + compiler version. Cross-platform determinism is NOT required (this is a single-machine desktop pipeline).

3. **Pin Rust compiler version** via `rust-toolchain.toml`:
   ```toml
   [toolchain]
   channel = "1.82.0"  # or current stable at implementation time
   ```
   Different Rust compiler versions may make different optimization choices. Pinning ensures reproducibility across builds.

4. **Disable auto-vectorization for critical paths** (if needed):
   ```rust
   // Only if SIMD produces different results than scalar
   #[target_feature(enable = "")]  // Force scalar codegen
   fn critical_computation(x: f64) -> f64 { ... }
   ```
   In practice, Rust's auto-vectorization of f64 scalar code produces identical results to scalar execution on x86-64 (SSE2 is the baseline, and f64 operations are scalar in SSE2). This is a defense-in-depth option, not expected to be needed.

5. **Avoid non-deterministic operations in trade simulation:**
   - No `HashMap` iteration (use `BTreeMap` — already project convention per Story 2-9 lesson)
   - No floating-point comparison for equality (use epsilon-based comparison)
   - No uninitialized memory reads (Rust prevents this at compile time)
   - Accumulation order must be fixed (left-to-right fold, not parallel reduction on f64)

**Concrete compiler flags for workspace `.cargo/config.toml`:**
```toml
[target.x86_64-pc-windows-msvc]
rustflags = ["-C", "target-feature=-fma"]

[profile.release]
opt-level = 2        # Not 3 — opt-level 3 enables aggressive vectorization
lto = "thin"         # Link-time optimization for performance without cross-crate inlining surprises
codegen-units = 1    # Single codegen unit for deterministic code layout
```

### 3.2 Rayon Parallel Determinism

**Problem:** Rayon's `par_iter()` provides no ordering guarantees. The work-stealing scheduler assigns chunks dynamically based on thread availability, so iteration order and reduction order vary between runs.

**Strategy:**

1. **Use `IndexedParallelIterator` with explicit chunk size:**
   ```rust
   use rayon::prelude::*;

   let results: Vec<TrialResult> = param_sets
       .par_chunks(chunk_size)  // Fixed chunk boundaries
       .enumerate()             // Preserve chunk index
       .flat_map(|(chunk_idx, chunk)| {
           chunk.iter().enumerate().map(move |(i, params)| {
               let trial_idx = chunk_idx * chunk_size + i;
               evaluate_trial(trial_idx, params, &market_data, &signals)
           })
       })
       .collect();  // Collect preserves index order for IndexedParallelIterator
   ```

   Key insight: `par_chunks()` returns an `IndexedParallelIterator`, which guarantees that `collect()` produces results in the same order as the input, regardless of execution order. The work-stealing scheduler may process chunks out of order, but the final collection respects the original indices.

2. **Avoid parallel reduction on floating-point values:**
   ```rust
   // BAD: Non-deterministic due to floating-point associativity
   let total: f64 = values.par_iter().sum();

   // GOOD: Compute per-trial metrics in parallel, reduce sequentially
   let trial_metrics: Vec<TrialMetrics> = trials.par_chunks(chunk_size)
       .map(|chunk| evaluate_chunk(chunk))
       .collect();

   // Sequential reduction for deterministic f64 accumulation
   let total: f64 = trial_metrics.iter().map(|m| m.pnl).sum();
   ```

3. **Fix Rayon thread pool size:**
   ```rust
   use rayon::ThreadPoolBuilder;

   let pool = ThreadPoolBuilder::new()
       .num_threads(num_cores)  // From memory budget calculation
       .build()
       .expect("Failed to build Rayon thread pool");

   pool.install(|| {
       // All parallel work happens in this fixed-size pool
   });
   ```
   Variable thread pool sizes can affect chunk assignment. Fixing the pool size to `num_cores` (determined at startup from memory budget) ensures consistent chunk distribution.

4. **Chunk size calculation:**
   ```rust
   // Deterministic chunk size based on trial count and thread count
   let chunk_size = (n_trials + num_threads - 1) / num_threads;
   // This ensures every run with the same n_trials and num_threads
   // produces the same chunk boundaries
   ```

### 3.3 Random Seed Management

**Problem:** Stochastic elements in the pipeline (Monte Carlo validation, bootstrap confidence intervals) must produce identical results given the same seed.

**Strategy:**

1. **Use `ChaCha8Rng` for all randomness:**
   ```rust
   use rand::SeedableRng;
   use rand_chacha::ChaCha8Rng;

   // Master seed from pipeline configuration
   let master_seed: u64 = config.random_seed;

   // Per-worker seed derivation (deterministic)
   fn worker_seed(master: u64, worker_id: usize) -> ChaCha8Rng {
       let seed = master.wrapping_add(worker_id as u64);
       ChaCha8Rng::seed_from_u64(seed)
   }
   ```

   `ChaCha8Rng` is chosen over `StdRng` because:
   - `StdRng` is an alias that may change between `rand` versions (currently ChaCha12)
   - `ChaCha8Rng` is an explicit, stable algorithm
   - 8 rounds is sufficient for statistical quality in backtesting (not cryptographic)
   - Deterministic across all platforms

2. **Seed propagation protocol:**
   ```
   Pipeline config → master_seed (u64)
     → Backtest stage: seed = master_seed + 0
     → Monte Carlo stage: seed = master_seed + 1000
       → Per-simulation: seed = stage_seed + simulation_index
     → Bootstrap stage: seed = master_seed + 2000
       → Per-sample: seed = stage_seed + sample_index
   ```

   Offset constants (0, 1000, 2000) ensure non-overlapping seed spaces across stages. Each stage further derives per-trial seeds using the trial index, ensuring parallel workers produce the same sequence regardless of execution order.

3. **Seed persistence in checkpoint:**
   The master seed is stored in the pipeline state JSON and the checkpoint file. Resume operations re-derive per-worker seeds from the master seed + trial index, so partial resume produces the same results as a fresh run for the remaining trials.

### 3.4 Timestamp Precision

**Problem:** Timestamp representation must be consistent across Python (pyarrow) and Rust (arrow-rs) to ensure bar alignment and session boundary precision.

**Strategy:**

1. **int64 microsecond epoch (UTC) as canonical format** (per D2 Arrow schema):
   ```
   Arrow schema: timestamp_us = Int64  (microseconds since Unix epoch, UTC)
   ```

   This is already implemented and validated in Epic 1. The Arrow IPC files produced by `arrow_converter.py` store timestamps as `int64` microseconds.

2. **UTC-only enforcement:**
   - Python side: All `datetime` objects are UTC (`datetime.timezone.utc`). No timezone-naive timestamps.
   - Rust side: All timestamps are `i64` microseconds from epoch. No timezone conversion in Rust — UTC is the only timezone.
   - Session boundaries (Asian, London, New York) are defined as UTC hour ranges in configuration, not local time.

3. **Session boundary precision:**
   M1 (1-minute) bars have 60-second granularity. Session boundaries aligned to the minute are sufficient for all trading session definitions. The int64 microsecond format provides sub-second precision for future M1 sub-bar resolution without format changes.

4. **Cross-language consistency:**
   ```python
   # Python (pyarrow): int64 microseconds
   timestamp_us = int(dt.timestamp() * 1_000_000)
   ```
   ```rust
   // Rust (arrow-rs): int64 microseconds
   let timestamp_us: i64 = /* read from Arrow IPC column */;
   let seconds = timestamp_us / 1_000_000;
   let micros = timestamp_us % 1_000_000;
   ```

   Both languages interpret the same int64 value identically. No floating-point conversion is involved (integer arithmetic only), so this is bit-exact across languages.

### 3.5 Windows-Specific Concerns

1. **MSVC toolchain floating-point behavior:**
   MSVC's CRT math functions (`sin`, `cos`, `sqrt`) are deterministic for the same MSVC version. Rust on Windows targets MSVC by default. The `rust-toolchain.toml` pin (Section 3.1) combined with MSVC version pinning in CI (if applicable) ensures consistent math results.

   Windows `_controlfp()` (floating-point control word) is NOT used — Rust's default x87/SSE2 control settings are correct for IEEE 754 compliance. Explicitly setting `_controlfp()` is unnecessary and would require `unsafe` code.

2. **RUST_BACKTRACE for debugging:**
   ```rust
   // Set in Rust binary main(), not via env var (avoids shell compatibility issues)
   if cfg!(debug_assertions) {
       std::env::set_var("RUST_BACKTRACE", "1");
   }
   ```
   In release builds, `RUST_BACKTRACE` is controlled by the Python orchestrator when spawning the subprocess:
   ```python
   env = os.environ.copy()
   env["RUST_BACKTRACE"] = "1"  # Enable for debugging
   result = subprocess.run([binary_path, ...], env=env, ...)
   ```

3. **Windows file locking for Arrow IPC:**
   Windows has mandatory file locking — a file open for writing cannot be read by another process. This affects the subprocess IPC pattern:
   - Python writes Arrow IPC input files, closes them, THEN spawns Rust binary.
   - Rust binary writes Arrow IPC output files, closes them, THEN exits.
   - Python reads Rust's output files AFTER the subprocess exits.
   This sequential handoff is inherent to the subprocess model and avoids all locking issues.

4. **NTFS atomic rename:**
   `os.replace()` (Python) and `std::fs::rename()` (Rust) are atomic on NTFS for same-volume renames. This is used for crash-safe writes (see Section 5). Note: `os.rename()` on Windows fails if the destination exists — always use `os.replace()` (already the pattern in `safe_write.py`).

5. **Path handling:**
   Rust binary receives paths as CLI arguments. Windows paths with backslashes work in Rust's `std::path::PathBuf` natively. The Python orchestrator uses `pathlib.Path` which produces OS-native paths. No manual path conversion needed.

---

## 4. Reproducibility Contract

This contract resolves the tension between PRD Technical Success ("materially identical results within defined tolerance") and Epic 3 Story 3-9 AC #9 ("bit-identical results").

### 4.1 Resolution

The PRD's "defined tolerance" language was written before the architecture committed to deterministic computation (D1 subprocess + fixed compiler flags + fixed Rayon threading). With the determinism strategies in Section 3, **bit-identical computation results are achievable** — the tolerance language in the PRD accounts for potential future relaxation (e.g., cross-platform portability), not the V1 single-machine case.

**V1 Contract:** Same inputs + same configuration + same binary = **bit-identical outputs** for computation artifacts. Non-computation metadata (timestamps, durations) is excluded from identity comparison.

### 4.2 Per-Output-Type Contract

| Output Type | Identity Requirement | Verification Method | Rationale |
|---|---|---|---|
| **Trade log** (Arrow IPC) | **Bit-identical** | SHA-256 hash of Arrow IPC file bytes | Deterministic computation: same signals + same params + same market data + same cost model → same trades. No floating-point accumulation variance because FMA is disabled and reduction order is fixed. |
| **Equity curve** (Arrow IPC) | **Bit-identical** | SHA-256 hash of Arrow IPC file bytes | Derived deterministically from trade log PnL sequence. Cumulative sum with fixed left-to-right order. No parallel reduction. |
| **Metrics** (10 values per trial) | **Bit-identical** | SHA-256 hash of Arrow IPC metrics output | Computed from trade log using fixed-order sequential accumulation. Same trades → same metrics. Verified: win_rate (integer division on trade counts), profit_factor (sequential sum), Sharpe/Sortino (sequential mean/std), max_dd_pct (sequential scan), R² (sequential regression), Ulcer (sequential RMS). |
| **Manifest hash** | **Tolerance-based** | Exclude `created_at`, `duration_secs`, `hostname` fields before hash comparison | Manifest metadata includes non-deterministic fields (wall-clock time, execution duration). Content hash covers input hashes + output hashes + config hash — these ARE bit-identical. |
| **Checkpoint files** | **Not compared** | N/A — ephemeral artifact | Checkpoints include timestamps and partial state. They are not pipeline outputs — they are operational state for crash recovery. |

### 4.3 Compliance Verification (Story 3-9)

```
Verification Protocol:
1. Run pipeline with config C, data D, seed S → outputs O1
2. Run pipeline with SAME C, D, S → outputs O2
3. For each artifact type:
   - Trade log: assert sha256(O1.trades) == sha256(O2.trades)
   - Equity curve: assert sha256(O1.equity) == sha256(O2.equity)
   - Metrics: assert sha256(O1.metrics) == sha256(O2.metrics)
   - Manifest: assert content_hash(O1.manifest) == content_hash(O2.manifest)
     where content_hash excludes temporal metadata fields
4. Any failure → investigation required (likely a determinism bug)
```

---

## 5. Checkpoint/Resume Patterns

### 5.1 Checkpoint Granularity

| Granularity | Use Case | I/O Overhead | Recovery Granularity |
|---|---|---|---|
| Per-bar | Single backtest within Rust binary | ~5μs/bar × 5.26M bars = 26s per run | Finest — resume from exact bar. **Not recommended:** I/O overhead (26s) exceeds typical single-backtest time (5s). Only justified for extremely long backtests (>10min). |
| Per-N-bars (configurable) | Single backtest, long timeframes | Configurable. 1000-bar batches: 5,260 writes, ~0.5s overhead | Good balance for long backtests. |
| Per-trade | Single backtest within Rust binary | ~5μs/trade × 500 trades = 2.5ms per run | Natural boundary. Negligible overhead. **Recommended for within-run state.** |
| Per-batch (N parameter sets) | Optimization runs | ~5ms/checkpoint × 100 checkpoints = 0.5s for 10K trials | **Recommended for optimization.** Natural batch boundary. Configurable N (default: 100 parameter sets per checkpoint). |
| Per-stage | Pipeline orchestrator | ~10ms per stage transition | **Recommended for cross-stage.** Coarse but sufficient for pipeline-level recovery. |

**Recommended strategy:** Two-level checkpointing:
1. **Within Rust binary (fine-grained):**
   - **Optimization runs:** Per-batch checkpoint every N parameter sets (default 100). Persisted to disk as Arrow IPC partial results + JSON metadata. Crash-resumable via `--resume` flag.
   - **Single backtests (≤10 min):** No persisted checkpoint — re-run is faster than checkpoint I/O overhead. The Python orchestrator treats the entire single backtest as one atomic unit; on crash, it re-invokes the Rust binary from the start.
   - **Single backtests (>10 min, e.g., multi-year tick data):** Per-N-bars checkpointing (configurable batch size, see granularity table above). Persisted checkpoint enables crash-resume without full re-run.
2. **Cross-process (coarse-grained):** Per-stage checkpoint managed by Python orchestrator via D3 state machine. Written after each stage completes successfully.

### 5.2 Crash-Safe Write Semantics

**Pattern: Write-to-temp → fsync → atomic rename** (per NFR15)

**Python side (existing pattern from `safe_write.py`):**
```python
def crash_safe_write_checkpoint(data: dict, output_path: Path) -> None:
    """Write checkpoint JSON with crash-safe semantics."""
    partial = output_path.with_suffix(".partial")
    with open(partial, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(partial, output_path)  # Atomic on NTFS
```

**Rust side (new pattern for backtester binary):**
```rust
use std::fs;
use std::io::Write;
use std::path::Path;

fn crash_safe_write(data: &[u8], output_path: &Path) -> std::io::Result<()> {
    let partial = output_path.with_extension("partial");
    let mut file = fs::File::create(&partial)?;
    file.write_all(data)?;
    file.sync_all()?;  // fsync equivalent
    fs::rename(&partial, output_path)?;  // Atomic on NTFS (same volume)
    Ok(())
}

fn crash_safe_write_arrow(
    batches: &[RecordBatch],
    schema: &Schema,
    output_path: &Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let partial = output_path.with_extension("partial");
    let file = fs::File::create(&partial)?;
    let mut writer = arrow::ipc::writer::FileWriter::try_new(file, schema)?;
    for batch in batches {
        writer.write(batch)?;
    }
    writer.finish()?;
    // FileWriter::finish() calls flush internally
    let file = writer.into_inner()?;
    file.sync_all()?;
    fs::rename(&partial, output_path)?;
    Ok(())
}
```

**Windows NTFS specifics:**
- `fs::rename()` in Rust calls `MoveFileExW` with `MOVEFILE_REPLACE_EXISTING` — atomic on NTFS for same-volume renames.
- Partial files use `.partial` extension (consistent with existing Python pattern).
- On crash: `.partial` files are orphaned and detected on resume (see 5.3).

### 5.3 Resume Verification

**Detecting partial/corrupt checkpoints:**

1. **Arrow IPC footer verification:**
   Arrow IPC files have a magic footer (`ARROW1` + 4-byte footer length). A file missing this footer is incomplete.
   ```rust
   fn verify_arrow_ipc(path: &Path) -> bool {
       let file = fs::File::open(path).ok();
       let file = match file {
           Some(f) => f,
           None => return false,
       };
       let reader = arrow::ipc::reader::FileReader::try_new(file, None);
       reader.is_ok()  // Footer validation happens during construction
   }
   ```

2. **Config hash verification:**
   Each checkpoint includes a hash of the configuration that produced it. On resume, the current config hash is compared to the checkpoint's config hash. Mismatch → discard checkpoint and restart (configuration changed, results are invalid).
   ```json
   {
     "config_hash": "sha256:abc123...",
     "last_completed_batch": 42,
     "total_batches": 100,
     "partial_results_path": "results_batch_0_42.arrow"
   }
   ```

3. **Orphan detection:**
   On startup, scan for `.partial` files in the output directory. Delete them — they are evidence of a crash during write. The last complete checkpoint (without `.partial` extension) is the resume point.

4. **Recovery strategy:**
   ```
   1. Scan output directory for checkpoint files
   2. Find latest checkpoint with valid Arrow IPC footer AND matching config hash
   3. Delete any .partial files (crash artifacts)
   4. Resume from checkpoint: load completed results, continue from next batch
   5. If no valid checkpoint found: restart from beginning
   ```

### 5.4 Checkpoint File Format

**Within-stage checkpoint (Rust binary, optimization run):**
```json
{
  "schema_version": "1.0",
  "stage": "backtest_optimization",
  "config_hash": "sha256:...",
  "strategy_spec_hash": "sha256:...",
  "market_data_hash": "sha256:...",
  "random_seed": 42,
  "total_batches": 100,
  "completed_batches": 42,
  "last_batch_end_index": 4200,
  "results_files": [
    "results_batch_000_041.arrow"
  ],
  "open_positions": [],
  "created_at": "2026-03-18T12:00:00Z"
}
```

**Cross-stage checkpoint (Python orchestrator, D3 state machine):**
```json
{
  "schema_version": "1.0",
  "pipeline_id": "uuid-...",
  "strategy_key": "ma_crossover_v001",
  "pair": "EURUSD",
  "config_hash": "sha256:...",
  "stages": {
    "data_preparation": {"status": "complete", "artifact_path": "..."},
    "signal_generation": {"status": "complete", "artifact_path": "..."},
    "backtest_optimization": {"status": "in_progress", "checkpoint_path": "..."},
    "walk_forward": {"status": "pending"},
    "monte_carlo": {"status": "pending"},
    "ai_analysis": {"status": "pending"},
    "evidence_pack": {"status": "pending"}
  },
  "current_stage": "backtest_optimization",
  "created_at": "2026-03-18T12:00:00Z",
  "last_updated": "2026-03-18T12:30:00Z"
}
```

### 5.5 Within-Stage vs Cross-Stage Checkpointing

| Dimension | Within-Stage (Rust Binary) | Cross-Stage (Python Orchestrator) |
|---|---|---|
| **Scope** | Progress within a single stage (e.g., optimization batch progress) | Pipeline-level stage completion tracking |
| **Owner** | Rust backtester binary | Python D3 state machine (Story 3-3) |
| **Persistence** | Arrow IPC partial results + JSON checkpoint metadata | JSON pipeline state (D3) |
| **Granularity** | Per-batch (configurable, default 100 param sets) | Per-stage |
| **Resume trigger** | Rust binary detects checkpoint on startup via `--resume <checkpoint_dir>` CLI flag | Python orchestrator reads pipeline state on startup |
| **Communication** | Rust writes checkpoint files to output directory; Python reads them after process exit | Python manages state directly |
| **Crash recovery** | Rust binary crash → Python detects non-zero exit → reads last valid checkpoint → respawns with `--resume` | Python crash → restart → read pipeline state JSON → resume from current stage |

---

## 6. Memory Budgeting

### 6.1 Reference Workload Budget

**Scenario:** 10-year EURUSD M1 backtest, 16 P-core threads, 10K optimization trials.

| Component | Size | Memory Type | Notes |
|---|---|---|---|
| Market data (10yr M1) | ~400 MB | mmap (not heap) | Arrow IPC file memory-mapped via `memmap2`. OS manages page faults. Does NOT count against Rust heap allocation. |
| Signal data | ~8 MB | Heap (read-only) | Pre-computed signals loaded from Arrow IPC. ~1000 signals × 8 fields × 8 bytes per field × 1000 = ~8MB. |
| Parameter matrix | ~5 MB | Heap (read-only) | 10K trials × 64 params × 8 bytes = ~5MB per batch. |
| Trade buffers (16 threads) | 800 MB | Heap (pre-allocated) | 16 threads × 50MB per thread. Each buffer: ~500 max trades × ~100KB per trade state (entry/exit prices, SL/TP, MFE/MAE, PnL history). `Vec::with_capacity()` at thread start. |
| Metrics output buffer | ~2 MB | Heap (pre-allocated) | 10K trials × 10 metrics × 8 bytes × batched (100 per write). |
| Streaming output | ~50 MB | Heap (rolling buffer) | Arrow IPC `StreamWriter` buffer. Flushed every N trials to output file. |
| Working memory | ~200 MB | Heap (dynamic) | Stack frames, temporary computations, Arrow deserialization buffers. |
| **Total active heap** | **~1,065 MB** | | |
| **Total including mmap** | **~1,465 MB** | | mmap pages are demand-paged by OS |
| OS reserve | 2-4 GB | N/A | Per NFR4: reserve 2-4GB for OS + other processes |

**System requirement:** For 10-year data with 16 threads, minimum 8GB RAM recommended (1.5GB active + 4GB OS reserve + headroom). For 32GB systems (likely for this workload), ample headroom exists.

### 6.2 Pre-Allocation Strategy

**Principle (NFR4):** All large allocations happen at startup, before the compute hot path begins. If the required memory cannot be allocated, reduce batch size (fewer threads or smaller batches) BEFORE starting — never mid-run.

```rust
use sysinfo::System;

struct MemoryBudget {
    available_mb: usize,
    os_reserve_mb: usize,
    market_data_mb: usize,   // mmap, not counted
    num_threads: usize,
    per_thread_buffer_mb: usize,
    batch_size: usize,
}

impl MemoryBudget {
    fn calculate(market_data_size_mb: usize) -> Self {
        let mut sys = System::new_all();
        sys.refresh_memory();
        let total_mb = (sys.total_memory() / 1_048_576) as usize;
        let available_mb = (sys.available_memory() / 1_048_576) as usize;

        let os_reserve_mb = if total_mb >= 32_000 { 4_000 }
                           else if total_mb >= 16_000 { 3_000 }
                           else { 2_000 };

        let usable_mb = available_mb.saturating_sub(os_reserve_mb);

        // Thread count: start with physical core count, reduce if memory-constrained
        let physical_cores = num_cpus::get_physical();
        let per_thread_mb = 50; // Target: 50MB per trade buffer

        let mut num_threads = physical_cores;
        while num_threads * per_thread_mb + 300 > usable_mb && num_threads > 1 {
            num_threads -= 1;
        }

        // Batch size: how many trials to evaluate per Rayon dispatch
        let remaining_mb = usable_mb - (num_threads * per_thread_mb) - 300;
        let batch_size = (remaining_mb * 1_048_576 / (64 * 8))
            .min(10_000)
            .max(100);

        MemoryBudget {
            available_mb,
            os_reserve_mb,
            market_data_mb: market_data_size_mb,
            num_threads,
            per_thread_buffer_mb: per_thread_mb,
            batch_size,
        }
    }

    fn pre_allocate(&self) -> Vec<Vec<TradeState>> {
        // Pre-allocate trade buffers for all threads
        (0..self.num_threads)
            .map(|_| Vec::with_capacity(
                self.per_thread_buffer_mb * 1_048_576 / std::mem::size_of::<TradeState>()
            ))
            .collect()
    }
}
```

### 6.3 Mmap Patterns for Arrow IPC

**Reading market data (zero-copy):**
```rust
use memmap2::Mmap;
use arrow::ipc::reader::FileReader;

fn mmap_market_data(path: &Path) -> Result<FileReader<Mmap>> {
    let file = fs::File::open(path)?;
    let mmap = unsafe { Mmap::map(&file)? };
    // Arrow FileReader over mmap — zero-copy column access
    let reader = FileReader::try_new(
        std::io::Cursor::new(mmap),
        None,  // Read all columns
    )?;
    Ok(reader)
}
```

**Python side (for writing inputs):**
```python
# pyarrow memory_map for reading (verification)
import pyarrow as pa
mmap_reader = pa.memory_map(str(arrow_path), mode='r')
reader = pa.ipc.open_file(mmap_reader)
table = reader.read_all()
```

**Windows mmap notes:**
- `memmap2::Mmap::map()` uses `CreateFileMappingW` + `MapViewOfFile` on Windows.
- Read-only mmap is safe for concurrent access (multiple threads reading same mmap).
- The mmap'd file must NOT be deleted or modified while mapped. The sequential subprocess model (Python writes → Rust reads → Rust exits → Python reads results) guarantees this.

### 6.4 Streaming Result Output

**Problem:** Accumulating the full equity curve in memory for 10K trials × 5.26M bars = ~400GB. Obviously impossible.

**Solution:** Stream results incrementally during backtest.

```rust
use arrow::ipc::writer::FileWriter;

struct StreamingResultWriter {
    writer: FileWriter<BufWriter<File>>,
    buffer: Vec<RecordBatch>,
    buffer_size: usize,
    flush_threshold: usize,  // Flush every N batches
}

impl StreamingResultWriter {
    fn new(path: &Path, schema: &Schema, flush_threshold: usize) -> Self {
        let partial = path.with_extension("partial");
        let file = BufWriter::new(File::create(&partial).unwrap());
        let writer = FileWriter::try_new(file, schema).unwrap();
        StreamingResultWriter {
            writer,
            buffer: Vec::new(),
            buffer_size: 0,
            flush_threshold,
        }
    }

    fn write_trial_result(&mut self, batch: RecordBatch) -> Result<()> {
        self.buffer_size += 1;
        self.buffer.push(batch);
        if self.buffer_size >= self.flush_threshold {
            self.flush()?;
        }
        Ok(())
    }

    fn flush(&mut self) -> Result<()> {
        for batch in self.buffer.drain(..) {
            self.writer.write(&batch)?;
        }
        self.buffer_size = 0;
        Ok(())
    }

    fn finish(mut self, final_path: &Path) -> Result<()> {
        self.flush()?;
        self.writer.finish()?;
        let file = self.writer.into_inner()?.into_inner()?;
        file.sync_all()?;
        // Atomic rename from .partial to final path
        fs::rename(
            final_path.with_extension("partial"),
            final_path,
        )?;
        Ok(())
    }
}
```

**Key insight:** Only per-trial METRICS need to be accumulated for optimization ranking. The equity curve is per-trial and can be streamed to disk immediately. The metrics array (10 values × 10K trials = 800KB) trivially fits in memory.

### 6.5 Throttle-Before-OOM

**Trigger thresholds:**

| Available Memory | Action |
|---|---|
| > 4 GB above OS reserve | Normal operation |
| 2-4 GB above OS reserve | Warning log. Continue. |
| 1-2 GB above OS reserve | **Throttle:** Reduce Rayon thread pool to `num_threads / 2`. Reduce batch size to `batch_size / 2`. Log throttle event. |
| < 1 GB above OS reserve | **Pause:** Complete current batch, checkpoint, exit with specific exit code (e.g., 75). Python orchestrator reads exit code, reduces resource allocation in config, respawns. |
| OOM signal (Windows) | Process terminates. Python orchestrator detects crash, reads last checkpoint, respawns with reduced allocation. |

**Monitoring mechanism:**
```rust
fn check_memory_pressure(budget: &MemoryBudget) -> MemoryState {
    let mut sys = System::new();
    sys.refresh_memory();
    let available_mb = (sys.available_memory() / 1_048_576) as usize;
    let headroom = available_mb.saturating_sub(budget.os_reserve_mb);

    match headroom {
        h if h >= 4_000 => MemoryState::Normal,
        h if h >= 2_000 => MemoryState::Warning,
        h if h >= 1_000 => MemoryState::Throttle,
        _ => MemoryState::Pause,
    }
}
```

**Check frequency:** Once per batch (every 100 param sets). `sysinfo` memory query takes <1ms, negligible overhead.

---

## 7. Architecture Alignment Matrix

| Recommendation | D1 | D2 | D3 | D8 | D13 | D14 | D15 |
|---|---|---|---|---|---|---|---|
| Subprocess + Arrow IPC | **Aligned** — exact match | **Aligned** — uses Arrow IPC for compute hot path | N/A | **Aligned** — structured JSON stderr | N/A | N/A | **No impact** — batch IPC orthogonal to live daemon |
| Rust CLI contract | **Aligned** — binary spawned by Python | **Aligned** — reads/writes Arrow IPC files | **Aligned** — invoked per-stage by state machine | **Aligned** — exit codes + JSON stderr | **Aligned** — cost model loaded as library dep | **Aligned** — strategy_engine as library dep | **No impact** |
| Deterministic computation | N/A | N/A | N/A | N/A | N/A | **Aligned** — shared crate determinism benefits both backtester and live daemon | **No impact** |
| Reproducibility contract | N/A | **Aligned** — Arrow IPC hash comparison | **Aligned** — config hash in pipeline state | N/A | N/A | **Aligned** — identical code paths guarantee identical results | **No impact** |
| Checkpoint/resume | N/A | **Aligned** — uses Arrow IPC + JSON | **Aligned** — extends D3 state machine with within-stage checkpoints | N/A | N/A | N/A | **No impact** |
| Memory budgeting | **Aligned** — mmap for Arrow IPC data | **Aligned** — Arrow IPC mmap-friendly | N/A | N/A | **Aligned** — cost model crate is in-process (no IPC overhead) | **Aligned** — shared crate in-process | **No impact** |
| Windowed evaluation (9.1) | **Aligned** — extends D1 binary interface | N/A | **Aligned** — state machine can request window ranges | N/A | N/A | **Aligned** — shared engine supports window params | **No impact** |
| Per-bar cost integration (9.4) | N/A | N/A | N/A | N/A | **Aligned** — cost model provides per-bar lookups | N/A | **No impact** |

**Summary:** All recommendations are aligned with D1-D14. No deviations proposed. D15 confirmed unaffected by all batch IPC recommendations.

---

## 8. Proposed Architecture Updates

After thorough research, **no changes to architecture.md are proposed**. All recommendations in this research artifact operate within the existing architecture decisions.

Story 3-1 proposed four updates (9.1-9.4) that this research validates:

1. **9.1 D1 Windowed Evaluation:** Validated. The Rust binary CLI contract (Section 9.1 below) includes `--window-start` and `--window-end` parameters for windowed evaluation within a single data load. This avoids re-serializing market data per walk-forward window.

2. **9.2 D3 Optimization Sub-States:** Validated. The checkpoint schema (Section 5.4) supports hierarchical state — pipeline stages containing optimization sub-stages. Story 3-3 should implement this.

3. **9.3 D1/NFR5 Sub-Stage Checkpointing:** Validated. Within-stage checkpointing (Section 5.1) provides per-batch checkpointing for optimization runs and per-candidate checkpointing for validation stages.

4. **9.4 D13 Per-Bar Cost Integration:** Validated. The cost model crate (already implemented in Story 2-7) provides session-aware cost lookups. Integration points are documented in the build plan (Section 10).

These updates do not require changes to architecture.md — they are implementation details that fit within the existing decision framework. The architecture document describes the "what" (multi-process, state machine, cost model crate); this research provides the "how" for Stories 3.3-3.5.

---

## 9. Downstream Contracts

### 9.1 Batch Job CLI Contract

**Binary:** `forex_backtester` (built from `src/rust/crates/backtester/`)

**Invocation:**
```bash
forex_backtester run \
  --config <path/to/run_config.json> \
  --market-data <path/to/market_data.arrow> \
  --signals <path/to/signals.arrow> \
  --params <path/to/params.arrow> \
  --cost-model <path/to/cost_model.json> \
  --output-dir <path/to/output/> \
  [--window-start <bar_index>] \
  [--window-end <bar_index>] \
  [--resume <path/to/checkpoint_dir>] \
  [--threads <n>] \
  [--batch-size <n>] \
  [--checkpoint-interval <n>]
```

**Arguments:**
| Argument | Required | Type | Description |
|---|---|---|---|
| `--config` | Yes | Path (JSON) | Run configuration: exec_mode, random_seed, output format preferences |
| `--market-data` | Yes | Path (Arrow IPC) | Market data: OHLC + spread + timestamps. Columns: `timestamp_us`, `open`, `high`, `low`, `close`, `spread`, `session_label` |
| `--signals` | Yes | Path (Arrow IPC) | Pre-computed signals: bar_index, direction, entry_price, atr_pips, swing_sl, filter_value, variant, hour, day |
| `--params` | Yes | Path (Arrow IPC) | Parameter sets to evaluate. Each row is one trial's parameter values. Column names map to strategy spec parameter names. |
| `--cost-model` | Yes | Path (JSON) | Cost model artifact (Story 2-6/2-7 format). Session-aware spreads, slippage, commissions. |
| `--output-dir` | Yes | Path (directory) | Directory for output files. Created if not exists. |
| `--window-start` | No | i64 | Start bar index for windowed evaluation (inclusive). Default: 0. |
| `--window-end` | No | i64 | End bar index for windowed evaluation (exclusive). Default: total bars. |
| `--resume` | No | Path (directory) | Checkpoint directory. If present, resume from last valid checkpoint. |
| `--threads` | No | usize | Override thread count (default: auto from memory budget). |
| `--batch-size` | No | usize | Override optimization batch size (default: auto from memory budget). |
| `--checkpoint-interval` | No | usize | Checkpoint every N parameter sets (default: 100). |

**Exit codes:**
| Code | Meaning | Stderr |
|---|---|---|
| 0 | Success | Empty or progress messages |
| 1 | Invalid arguments | `{"error_type": "argument_error", "category": "input", "message": "...", "details": {...}}` |
| 2 | Input validation failure | `{"error_type": "validation_error", "category": "input", "message": "...", "details": {"field": "...", "expected": "...", "actual": "..."}}` |
| 3 | Computation error | `{"error_type": "computation_error", "category": "runtime", "message": "...", "details": {"trial_index": N, "stage": "..."}}` |
| 75 | Memory pressure pause | `{"error_type": "memory_pressure", "category": "resource", "message": "...", "details": {"available_mb": N, "threshold_mb": N}}` |
| 101 | Panic (caught) | `{"error_type": "panic", "category": "internal", "message": "...", "backtrace": "..."}` |

**Output files (written to `--output-dir`):**
| File | Format | Description |
|---|---|---|
| `metrics.arrow` | Arrow IPC | N_trials × 10 metrics. Columns: `trial_index`, `trades`, `win_rate`, `profit_factor`, `sharpe`, `sortino`, `max_dd_pct`, `return_pct`, `r_squared`, `ulcer`, `quality` |
| `trades_{trial_idx}.arrow` | Arrow IPC | Per-trial trade log (only for top-N trials or when requested). Columns: `signal_index`, `bar_entry`, `bar_exit`, `direction`, `entry_price`, `exit_price`, `sl`, `tp`, `pnl`, `exit_reason`, `mfe`, `mae` |
| `equity_{trial_idx}.arrow` | Arrow IPC | Per-trial equity curve (only for top-N trials). Columns: `trade_index`, `exit_timestamp_us`, `cumulative_pnl`, `drawdown_pct`. V1 uses per-trade granularity (compact, sufficient for max DD/R²/Ulcer); per-bar is a Growth feature. |
| `checkpoint/` | Directory | Checkpoint files (JSON metadata + partial Arrow IPC results) |
| `run_manifest.json` | JSON | Run metadata: config hash, input hashes, output hashes, duration, thread count, memory budget |

**Progress protocol (stdout):**
```json
{"type": "progress", "stage": "init", "message": "Memory budget: 16 threads, 100 batch size"}
{"type": "progress", "stage": "evaluate", "completed": 100, "total": 10000, "elapsed_secs": 12.5}
{"type": "progress", "stage": "evaluate", "completed": 200, "total": 10000, "elapsed_secs": 25.1}
{"type": "complete", "total_trials": 10000, "elapsed_secs": 625.0}
```

### 9.2 Checkpoint Schema

**Schema version:** 1.0

**Within-stage checkpoint (optimization):**
```json
{
  "schema_version": "1.0",
  "checkpoint_type": "within_stage",
  "stage": "backtest_optimization",
  "identity": {
    "config_hash": "sha256:...",
    "strategy_spec_hash": "sha256:...",
    "market_data_hash": "sha256:...",
    "cost_model_hash": "sha256:...",
    "random_seed": 42,
    "window_start": 0,
    "window_end": 5260000
  },
  "progress": {
    "total_param_sets": 10000,
    "completed_param_sets": 4200,
    "completed_batches": 42,
    "batch_size": 100
  },
  "results": {
    "metrics_files": ["metrics_batch_000_041.arrow"],
    "trade_files": [],
    "equity_files": []
  },
  "created_at": "2026-03-18T12:00:00Z"
}
```

**Identity fields** ensure that resume only continues a run with matching configuration. Any mismatch → discard checkpoint and restart.

**Crash-safe write pattern:** Checkpoint files are written using the write-to-temp → fsync → atomic rename pattern (Section 5.2).

### 9.3 Reproducibility Policy

1. **Guaranteed bit-identical:** Trade logs, equity curves, metrics (per Section 4.2).
2. **How verified:** SHA-256 hash comparison of Arrow IPC output files between two runs with identical inputs.
3. **Prerequisites for reproducibility:**
   - Same Rust binary (pinned toolchain via `rust-toolchain.toml`)
   - Same compiler flags (FMA disabled via `.cargo/config.toml`)
   - Same thread count (fixed via `--threads` or memory budget calculation)
   - Same random seed (from pipeline config)
   - Same input data (verified by input hash in run manifest)
   - Same cost model (verified by cost model hash)
4. **What is NOT guaranteed identical:** Wall-clock timestamps, execution duration, checkpoint file contents (include timestamps), run manifest temporal fields.
5. **Failure mode:** If reproducibility check fails, it indicates a determinism bug. Investigation required — check for `HashMap` usage, unguarded parallel f64 reduction, or FMA leak.

### 9.4 Memory Budget Model

**Inputs:**
- `total_system_memory_mb`: From `sysinfo::System::total_memory()`
- `available_memory_mb`: From `sysinfo::System::available_memory()`
- `market_data_size_mb`: From Arrow IPC file size (mmap, not counted against heap)
- `physical_cores`: From `num_cpus::get_physical()`
- `target_per_thread_mb`: 50 (configurable, default)

**Calculation:**
```
os_reserve_mb = if total >= 32GB then 4GB
                elif total >= 16GB then 3GB
                else 2GB

usable_mb = available_mb - os_reserve_mb

// Thread count: maximize parallelism within memory constraints
num_threads = physical_cores
while (num_threads * target_per_thread_mb + 300) > usable_mb and num_threads > 1:
    num_threads -= 1

// Batch size: remaining memory for parameter matrix + working memory
remaining_mb = usable_mb - (num_threads * target_per_thread_mb) - 300
batch_size = min(remaining_mb * 1048576 / (64 * 8), 10000)
batch_size = max(batch_size, 100)
```

**Enforcement mechanism:**
1. Memory budget calculated ONCE at Rust binary startup
2. All large allocations (`Vec::with_capacity()`) happen before computation begins
3. If pre-allocation fails → exit with code 75 (memory pressure)
4. Runtime monitoring: check `available_memory` once per batch (Section 6.5)
5. Throttle/pause thresholds enforce NFR10 (crash prevention)

**Output (logged and included in run manifest):**
```json
{
  "memory_budget": {
    "total_system_mb": 32768,
    "available_mb": 28000,
    "os_reserve_mb": 4000,
    "usable_mb": 24000,
    "num_threads": 16,
    "per_thread_buffer_mb": 50,
    "thread_total_mb": 800,
    "batch_size": 10000,
    "market_data_mb": 400,
    "market_data_access": "mmap"
  }
}
```

---

## 10. Build Plan for Stories 3.3-3.5

### 10.1 Detailed Build Plan

| Story | Component | Approach | Key Dependencies | Complexity | Interface Contracts Consumed | Questions Resolved |
|---|---|---|---|---|---|---|
| **3-3** | Pipeline State Machine | **Build new** | D3 spec, this research (checkpoint schema §9.2) | **L** | Checkpoint schema (§9.2), cross-stage checkpoint format (§5.4), resume verification (§5.3) | Checkpoint granularity (per-stage + within-stage), crash-safe write pattern (§5.2), config hash for identity verification |
| **3-3** | Checkpoint Infrastructure | **Adapt** from ClaudeBackTester `checkpoint.py` | `safe_write.py` pattern, D3 state JSON | **M** | Crash-safe write (§5.2), orphan detection (§5.3), checkpoint file format (§5.4) | Write pattern (temp→fsync→rename confirmed), Windows NTFS atomicity (os.replace confirmed), checkpoint identity verification |
| **3-4** | Python-Rust Bridge | **Build new** | Story 3-3 (state machine), this research (CLI contract §9.1) | **L** | Batch job CLI contract (§9.1), error parsing (exit codes + JSON stderr), progress protocol (stdout JSON) | CLI argument format, exit code semantics, Arrow IPC input/output file conventions, error structure (D8) |
| **3-4** | Arrow IPC Serialization | **Extend** existing `arrow_converter.py` | `safe_write.py`, Arrow IPC schemas | **M** | Signal/param Arrow schemas (§9.1 output files table), market data schema (existing from Epic 1) | What data goes in each Arrow file, column naming, parameter matrix format (named columns vs flat array) |
| **3-5** | Rust Backtester Crate | **Port** from ClaudeBackTester (6 Rust files) | Story 3-4 (bridge), cost_model crate (Story 2-7), strategy_engine crate (Story 2-8) | **XL** | Reproducibility policy (§9.3), memory budget model (§9.4), determinism strategies (§3), streaming output (§6.4) | FMA flag, Rayon determinism pattern, per-bar cost integration points, trade buffer sizing, streaming vs accumulating results |
| **3-5** | CLI Binary Wrapper | **Build new** | Backtester crate core, `clap` for arg parsing | **M** | CLI contract (§9.1), exit codes, progress protocol, memory budget calculation (§6.2) | All resolved by §9.1 contract |

### 10.2 Critical Path

```
Story 3-3 (State Machine + Checkpoint) ─┐
                                         ├─→ Story 3-4 (Bridge) ─→ Story 3-5 (Backtester Crate)
Existing infrastructure ─────────────────┘
```

**3-3 must complete before 3-4** because the bridge needs the state machine to track pipeline progress and invoke checkpoint/resume.

**3-4 must complete before 3-5** because the backtester crate needs the bridge's Arrow IPC serialization format to define its input/output interface.

**3-5 CAN partially overlap with 3-4** — the core trade simulation logic (porting from ClaudeBackTester) is independent of the bridge. The CLI wrapper and integration testing require the bridge.

### 10.3 Components from ClaudeBackTester to Port/Adapt

| Component | Source File | Target Crate | Action | Notes |
|---|---|---|---|---|
| Trade simulation (basic) | `ClaudeBackTester/rust/src/trade_basic.rs` | `backtester` | Port | Pure function. Add cost model integration points (§9.4). |
| Trade simulation (full) | `ClaudeBackTester/rust/src/trade_full.rs` | `backtester` | Port | Pure function. Add cost model integration. Sub-bar resolution. |
| Metrics computation | `ClaudeBackTester/rust/src/metrics.rs` | `backtester` | Port | 10 inline metrics. Sequential accumulation for determinism. |
| SL/TP computation | `ClaudeBackTester/rust/src/sl_tp.rs` | `strategy_engine` | Port | Fixed/ATR/Swing modes. Shared between backtester and live daemon. |
| Time filter | `ClaudeBackTester/rust/src/filter.rs` | `strategy_engine` | Port | Hour + day bitmask filter. Shared. |
| Parameter constants | `ClaudeBackTester/rust/src/constants.rs` | `common` | Adapt | PL_* layout → named parameters via Arrow schema. Constants shared across crates. |

### 10.4 New Components to Build

| Component | Crate | Description | Estimated LOC |
|---|---|---|---|
| CLI binary wrapper | `backtester` | `clap` argument parsing, config loading, memory budget, progress output | ~300 |
| Arrow IPC reader/writer | `backtester` | Read input Arrow IPC, write output Arrow IPC with streaming | ~200 |
| Memory budget calculator | `backtester` (or `common`) | System memory query, thread/batch sizing, throttle monitoring | ~150 |
| Checkpoint manager | `backtester` | Within-stage checkpoint write/read/verify/resume | ~200 |
| Error reporter | `common` | D8 structured JSON error serialization to stderr | ~100 |
| Batch runner (Python) | `rust_bridge` | `subprocess.run()` wrapper, error parsing, progress monitoring | ~200 |
| Result ingester (Python) | `rust_bridge` | Arrow IPC output → Python/SQLite pipeline | ~150 |

---

## 11. Dependency Notes for Stories 3.6-3.9

| Story | Component | Upstream Dependencies | Relevant Research Findings |
|---|---|---|---|
| **3-6** Backtest Results & SQLite | Results storage, SQLite ingest | **3-5:** Arrow IPC output format (metrics, trades, equity). **3-3:** Pipeline state for result tracking. | Arrow IPC output schemas defined in §9.1. Streaming output (§6.4) means results arrive incrementally — ingester should handle partial files via checkpoint-aware reading. Metrics Arrow schema: 11 columns per trial (§9.1). |
| **3-7** AI Analysis Layer | Narrative generation, anomaly detection | **3-6:** SQLite query interface for results. **3-5:** Metrics output for anomaly scoring. | Metrics are bit-identical (§4.2) — anomaly detection can use exact comparison. Evidence pack should include memory budget info from run manifest (§9.4) for debugging resource-related anomalies. |
| **3-8** Operator Pipeline Skills | Pipeline control, stage management | **3-3:** State machine API for pipeline control. **3-4:** Bridge API for backtest invocation. | CLI contract (§9.1) defines the interface operators indirectly control. Progress protocol (stdout JSON) enables real-time status display. Exit code 75 (memory pressure) should trigger operator notification. Gate decisions affect checkpoint behavior (§5.5). |
| **3-9** E2E Pipeline Proof | Full pipeline integration test | **3-3-3.8:** All prior stories. | Reproducibility verification protocol (§4.3) is the core test for 3-9. Must verify bit-identical outputs for trade logs, equity curves, metrics. Manifest hash comparison with temporal field exclusion. Memory budget logging (§9.4) provides audit trail. Checkpoint resume must be tested (kill + resume produces same results). |

---

## 12. Open Questions

1. **Windowed evaluation session model (Story 3-1 Update 9.1):** Should the Rust binary support a persistent "session" (load data once, accept multiple evaluation requests via stdin/stdout), or should each invocation be stateless (load data from mmap each time)? **Recommendation:** Start with stateless (simpler, crash-isolated per invocation). Profile to determine if mmap overhead per invocation is significant. If it is, add session model in a later story. mmap overhead for 400MB is ~2ms (page table setup only, not data copy), so stateless is likely sufficient.

2. **Parameter matrix format:** Should the Arrow IPC parameter file use named columns (matching strategy spec parameter names) or positional columns (PL_* layout)? **Recommendation:** Named columns. The PL_* layout was a PyO3 optimization for fixed-size numpy arrays. Arrow IPC natively supports named columns, eliminating the need for the `param_layout` indirection array. Story 3-4 should implement named-column serialization; Story 3-5 should deserialize by column name.

3. **Equity curve persistence granularity:** ~~Should equity curves be persisted per-bar (5.26M rows for 10-year data) or per-trade (~500 rows)?~~ **RESOLVED:** Per-trade for V1 (compact, sufficient for max DD/R²/Ulcer calculation). Per-bar is a Growth feature for detailed visualization. Story 3-5 outputs per-trade equity curves; Story 3-6 stores them. CLI contract (§9.1) updated to reflect per-trade columns (`trade_index`, `exit_timestamp_us`, `cumulative_pnl`, `drawdown_pct`).

4. **Cost model array pre-computation:** Should the Python bridge pre-compute per-bar cost arrays (spread, slippage, commission for each bar's session) and pass them as Arrow IPC columns, or should the Rust binary load the cost model JSON and compute per-bar costs internally? **Recommendation:** Rust binary loads cost model JSON directly (simpler, cost model crate is already a library dependency). Avoids inflating the Arrow IPC input file with redundant cost data. Story 3-4 passes cost model path; Story 3-5 integrates cost_model crate.

5. **Checkpoint storage format:** Should within-stage checkpoints use Arrow IPC (for partial results) + JSON (for metadata), or SQLite (for both)? **Recommendation:** Arrow IPC + JSON for V1. SQLite is the cross-stage format (D2/D3); within-stage checkpoints are ephemeral and don't need queryability. Using Arrow IPC for partial results means the resume path can simply concatenate completed Arrow IPC batches. Story 3-3 should implement this.

---

## Appendix A: Cross-Reference to PRD Requirements

| Requirement | Section | How Addressed |
|---|---|---|
| FR14 (Backtesting) | §2, §9.1 | Subprocess + Arrow IPC mechanism for running backtests |
| FR15 (Equity curve, trade log, metrics) | §9.1 | Output files table defines all three artifact types |
| FR16 (Chart-led results) | N/A | Not in scope — addressed by Story 3-6 (results storage) and Story 3-8 (operator skills) |
| FR17 (Anomalous result detection) | N/A | Not in scope — addressed by Story 3-7 (AI analysis layer) |
| FR18 (Deterministic reproducibility) | §3, §4 | Five determinism strategies + reproducibility contract |
| FR19 (Strategy logic location) | N/A | Not in scope — addressed by D14 (strategy engine shared crate) and Story 3-5 |
| FR42 (Resume interrupted runs) | §5 | Two-level checkpoint/resume pattern |
| FR58-FR61 (Versioned artifacts) | §9.1 | Run manifest with input/output hashes |
| NFR1 (80%+ CPU) | §6.2 | Memory budget maximizes thread count within constraints |
| NFR2 (Sub-second response) | N/A | Not in scope — applies to operator UI (Story 3-8), not batch computation |
| NFR3 (Pipeline completion time) | N/A | Not in scope — end-to-end timing is Story 3-9 E2E proof concern |
| NFR4 (Deterministic memory) | §6 | Pre-allocation strategy with budget calculation |
| NFR5 (Incremental checkpointing) | §5.1 | Per-batch checkpointing for optimization |
| NFR9 (Thread-safe concurrent) | §3.2 | Fixed Rayon thread pool, deterministic chunking |
| NFR10 (Crash prevention) | §2.3, §6.5 | Subprocess isolation + throttle-before-OOM |
| NFR11 (Crash recovery) | §5.3 | Resume verification with config hash matching |
| NFR12 (Graceful degradation) | N/A | Not in scope — runtime behavior addressed by Story 3-3 (state machine) |
| NFR13 (Observability/logging) | N/A | Not in scope — addressed by Story 3-3 (state machine) and Story 3-8 (operator skills) |
| NFR14 (Audit trail) | N/A | Partially relevant — run manifest (§9.1) provides per-run audit; full audit trail is Story 3-6 |
| NFR15 (Data integrity) | §5.2 | Crash-safe write pattern (temp→fsync→rename) |

## Appendix B: Cross-Reference to Architecture Decisions

| Decision | Section | Alignment Status |
|---|---|---|
| D1 (Multi-Process with Arrow IPC) | §2, §7 | **Aligned** — subprocess + Arrow IPC recommended |
| D2 (Arrow IPC / SQLite / Parquet) | §7 | **Aligned** — Arrow IPC for compute, JSON for checkpoints |
| D3 (Sequential State Machine) | §5.4, §5.5 | **Aligned** — checkpoint schema extends state machine |
| D4 (Configuration Management) | N/A | Not directly addressed — config management is Story 3-3 scope; research uses config hash for checkpoint identity (§5.3) |
| D5 (Logging Strategy) | N/A | Not directly addressed — logging is Story 3-3/3-8 scope |
| D6 (Testing Strategy) | N/A | Not directly addressed — testing strategy applies to implementation stories |
| D7 (Deployment Strategy) | N/A | Not directly addressed — deployment is out of research scope |
| D8 (Structured Errors) | §9.1 | **Aligned** — JSON stderr with error_type/category/message |
| D9 (Security Model) | N/A | Not directly addressed — security applies to operator interface (Story 3-8) |
| D10 (Data Validation) | N/A | Not directly addressed — input validation is Story 3-4 (bridge) scope; research assumes validated inputs |
| D11 (Monitoring & Alerting) | N/A | Not directly addressed — monitoring is Story 3-8 scope |
| D12 (Versioning Strategy) | N/A | Partially relevant — run manifest (§9.1) includes version info; full versioning is cross-cutting |
| D13 (Cost Model Crate) | §10.3 | **Aligned** — library dependency, in-process calls |
| D14 (Strategy Engine Shared) | §10.3 | **Aligned** — shared crate for signal evaluation |
| D15 (Named Pipes for Live) | §7 | **No impact** — batch IPC is orthogonal |
