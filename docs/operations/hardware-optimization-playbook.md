# Hardware Optimization Playbook — 32-Thread / 64GB RAM

> Source-grounded research from 315 sources via NotebookLM deep research.
> Notebook: `b5f173cd-16de-4333-839a-84598a765a00`
> Generated: 2026-03-12

---

## 1. MEMORY ARCHITECTURE

To load and process 64GB of market history efficiently, avoid dynamic heap allocations (`Box::new`, `malloc`) during the backtest, as modern allocators introduce 100-500ns of latency per allocation and cause unacceptable jitter.

### Mmap & Zero-Copy
Treat your dataset as an extension of RAM using a memory-mapped file (`mmap`) architecture. By mapping your data files directly into the process's virtual address space, the OS lazily loads pages into RAM without expensive user/kernel space copying. Combine this with zero-copy deserialization to completely eliminate data decoding overhead.

### SoA over AoS
Standard object-oriented "Array of Structs" (AoS)—where Open, High, Low, Close, and Volume are grouped per tick—pollutes the CPU cache. If your strategy only calculates a moving average on the `close` price, loading the full struct wastes up to 80% of the 64-byte cache line.

Switch to a "Struct of Arrays" (SoA) layout. SoA aligns perfectly with the CPU's load port architecture, guaranteeing that every byte loaded into the L1 cache is utilized, yielding a **40–60% performance improvement**.

| Access Pattern | Layout | Cache Line Utilization | Typical Performance Gain |
|---|---|---|---|
| Sequential field-specific sum | SoA | 100% (All data useful) | ~40-60% |
| Sequential field-specific sum | AoS | ~20% (Much wasted space) | Baseline |
| Multi-field update per element | AoS | High (All data used) | Variable |
| SIMD vectorized processing | SoA | Perfect (Uniform types) | 10x - 100x |

### Pre-allocated Buffers
Rather than arena allocators for intra-backtest state, pre-allocate object pools or fixed-size arrays at startup. For dynamically sized but small collections (like a limited order queue), use the `SmallVec` crate to keep allocations strictly on the stack, degrading gracefully to the heap only when absolutely necessary.

**Key Rust Crates:** `memmap2`, `SmallVec`, `zerocopy` / `rkyv`

---

## 2. THREAD STRATEGY

Your hybrid Intel CPU architecture creates severe "hardware noise" for backtesting if left to the OS. Rayon's default work-stealing pool treats all 32 threads equally. Because parallel iterations synchronize at the end of a loop, if a heavy evaluation thread is assigned to an E-core, your entire backtest will be throttled to the speed of that slow E-core.

### P-Core Affinity
Use the `core_affinity` crate to strictly pin your latency-critical Rayon worker threads to the 16 P-cores. Windows indexes logical processors by putting P-cores (and their hyper-threads) first, followed by E-cores. **Pinning to P-cores only can instantly yield a 2x throughput increase** by preventing the OS from parking your threads on E-cores to save power.

### Workload Split
Never mix scalar/branch-heavy work with SIMD-heavy work on the same thread pool. Isolate your backtest evaluations to the P-core pool, and assign asynchronous tasks, logging, or data ingestion to the E-cores using OS-level Eco QoS APIs.

### Thread Pool Configuration
```rust
// P-core pool for compute-heavy backtesting
use rayon::ThreadPoolBuilder;
use core_affinity;

let p_core_ids = core_affinity::get_core_ids()
    .unwrap()
    .into_iter()
    .take(16) // First 16 = P-cores on Windows
    .collect::<Vec<_>>();

let pool = ThreadPoolBuilder::new()
    .num_threads(p_core_ids.len())
    .spawn_handler(move |thread| {
        // Pin each worker to a P-core
        let core_id = p_core_ids[thread.index()];
        std::thread::spawn(move || {
            core_affinity::set_for_current(core_id);
            thread.run();
        });
        Ok(())
    })
    .build()
    .unwrap();
```

| Architecture Component | P-Core Characteristics | E-Core Characteristics | HT Support |
|---|---|---|---|
| Focus | Raw speed, IPC | Efficiency, MT Scale | Yes (P-Core) |
| Die Area | ~4x of an E-Core | 1/4 of a P-Core | No (E-Core) |
| Scheduling Priority | High (Foreground) | Low (Background) | 3rd Priority |

**Key Rust Crates:** `core_affinity`, `rayon`, `crossbeam`

---

## 3. SIMD / BRANCHLESS

Modern CPUs execute instructions much faster when they aren't stalled by branch mispredictions, which cost **10–20 cycles each**.

### Branchless Execution
Financial time series are highly volatile, making branch prediction ineffective. Convert control-flow (`if/else`) to data-flow:

```rust
// BRANCHED (bad for volatile data):
if price > threshold { sum += price; }

// BRANCHLESS (consistent pipeline):
sum += (price > threshold) as u64 as f64 * price;
```

For more complex state changes, use XOR or conditional move (`cmov`) instructions.

### SIMD with `simd-kernels`
Use the `simd-kernels` crate, built on top of `std::simd`, to vectorize mathematical indicators and statistics. It utilizes 64-byte aligned buffers (`Vec64`) to feed AVX-512 registers, processing **eight `f64` or sixteen `f32` values in a single cycle**.

**Critical compiler flag:**
```
RUSTFLAGS="-C target-cpu=native"
```

#### `simd-kernels` capabilities:
- **Arithmetic:** All numeric types (i8–u64, f32/f64) with overflow handling
- **Statistics:** Mean, variance, standard deviation, z-score normalisation
- **Probability Distributions:** 19 PDFs, CDFs, and quantiles with <1e-12 error bounds
- **Scientific Functions:** erf, gamma, FFT, matrix/vector ops
- **Linear Algebra:** Optional BLAS/LAPACK backend integration
- **FFT:** Blocked radix-2/4/8 pipelines with SIMD and complex arithmetic

**Key Rust Crates:** `simd-kernels`, `std::simd`, `packed_simd2`

---

## 4. DATA PIPELINE

### Parquet vs Arrow IPC

| Format | Archival Stability | Random Access | Decode Overhead | Typical Disk Size |
|---|---|---|---|---|
| Parquet | High (5+ years) | Costly | High (CPU decoding) | Small (Compressed) |
| Arrow IPC | Evolving | O(1) | Zero (Zero-copy) | Large (Up to 10x Parquet) |
| CSV | Excellent | Linear | High (Parsing) | Massive |

**Strategy:** Store archival tick data as Parquet, but for the active backtest, map it into memory as Apache Arrow IPC files. Arrow IPC provides O(1) random access and zero-copy semantics.

### Late Materialization
When reading Parquet datasets via the `arrow-rs` crate, use its "Late Materialization" (LM-pipelined) feature. If your backtest filters data (e.g., `volume > X`), this evaluates the predicate column first to build a bitmask, **completely skipping decompression and decoding of price columns for filtered rows**.

### Parquet vs CSV Performance

| Feature | CSV / Row-Based | Parquet / Columnar | Impact on Backtesting |
|---|---|---|---|
| Read Speed | 18.7 s | 0.8 s | >20x faster data ingestion |
| Write Speed | 112 s | 7 s | Faster storage of results |
| File Size | 1.48 GB | 230 MB | Reduced storage and I/O costs |
| Metadata | None | Rich (min/max per page) | Enables page pruning |

### Metadata Optimization
Leverage `arrow-rs` version 57.0.0+, which implements a custom Rust Thrift parser that reads Parquet footers **3x–9x faster**. Avoid creating more than 10,000 distinct partitions; over-partitioning causes small files where metadata parsing outweighs actual data reading.

**Key Rust Crates:** `arrow-rs`, `parquet`, `arrow-ipc`

---

## 5. PARALLEL PARAMETER OPTIMIZATION

### MAP-Elites (Quality-Diversity)
Relying solely on genetic algorithms (like L-SHADE) often leads to curve-fitting. Implement MAP-Elites to map strategies into a grid based on behavioral descriptors like *liquidity* and *volatility*.

This guarantees your algorithm retains the **highest-performing strategy for every distinct market condition**, yielding a diverse archive of robust strategies rather than a single overfitted set of parameters.

### Walk-Forward Parallelization
Parallelize walk-forward analysis using overlapping windows (e.g., an 8-month training window with a 4-month step). Distribute these independent time-windows as discrete jobs to your P-core Rayon pool to ensure maximum core saturation without data contention.

### Architecture Pattern
```
┌─────────────────────────────────────────────┐
│           MAP-Elites Controller              │
│  (maintains archive grid: liquidity × vol)   │
├─────────────────────────────────────────────┤
│        Rayon P-Core Pool (16 threads)        │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐       │
│  │ WF-1 │ │ WF-2 │ │ WF-3 │ │ WF-N │       │
│  │Window│ │Window│ │Window│ │Window│  ...    │
│  └──────┘ └──────┘ └──────┘ └──────┘       │
├─────────────────────────────────────────────┤
│     Arrow IPC mmap'd market data (64GB)      │
└─────────────────────────────────────────────┘
```

**Key Rust Crates:** Implement MAP-Elites in Rust (reference: `pyribs` Python lib for algorithm design)

---

## 6. CONCRETE PERFORMANCE TARGETS

For a highly optimized Rust engine on a 32-thread (16 P-core) system with 64GB RAM:

| Metric | Target | Source Context |
|---|---|---|
| **Strategy evaluations/sec** | 30,000 | Full parameter sweep throughput |
| **10-year minute backtest (7 assets, 6.8M points)** | ~30 seconds | End-to-end including results |
| **400 genetic iterations** | < 1.2 seconds | From 45s baseline = 99.89% reduction |
| **Tick-to-trade simulation (P50)** | 4.2 μs | Order book processing hot path |
| **Order throughput** | 2M orders/sec | Single server, pure Rust |

### Performance Tier Comparison

| Engine Tier | Complexity | 10-Year Backtest Time | Key Optimization |
|---|---|---|---|
| Retail Standard | 1M Data points | 33 - 78 seconds | Basic parallelization |
| Naive Rust | Minute OHLCV | 22 seconds | Memory safety, compiled speed |
| Optimized Rust | 6.8M Data points | 30.41 seconds | Multi-asset concurrency |
| **HFT-Grade (SIMD)** | **100-asset genetic** | **292 milliseconds** | **mmap, Rayon, SIMD kernels** |

---

## Key Rust Dependencies

```toml
[dependencies]
rayon = "1.10"
core_affinity = "0.8"
arrow = "53"
parquet = "53"
simd-kernels = "0.1"
memmap2 = "0.9"
smallvec = "1.13"
crossbeam = "0.8"
rkyv = "0.8"           # zero-copy deserialization
```

## Compiler Configuration

```toml
# .cargo/config.toml
[build]
rustflags = ["-C", "target-cpu=native"]

[profile.release]
opt-level = 3
lto = "fat"
codegen-units = 1
panic = "abort"
```

---

## NotebookLM Reference

For deeper queries grounded in all 315 sources:
- **Notebook ID:** `b5f173cd-16de-4333-839a-84598a765a00`
- **URL:** https://notebooklm.google.com/notebook/b5f173cd-16de-4333-839a-84598a765a00
- **Query via MCP:** Use `notebook_query` with the notebook ID above
