# Competitive analysis of backtesting engine architectures

**Your subprocess + Arrow IPC architecture is a defensible but unconventional choice.** Every major Python-Rust production system (Nautilus Trader, Polars, DataFusion) uses in-process PyO3 bindings for zero-copy data transfer — none use subprocess IPC as their primary bridge. However, your specific constraint (Windows NRT memory accumulation causing ACCESS_VIOLATION crashes) provides a legitimate engineering reason to diverge. The two-level checkpointing design aligns with proven HPC patterns and, combined with SQLite WAL-backed result caching, can achieve near-zero lost work at under 1% overhead for your 50ms-per-evaluation target.

This report covers eight backtesting systems across six architectural dimensions, validating decisions made in Stories 3-1 and 3-2 while cataloging patterns worth adopting.

---

## Deliverable 1: The competitive architecture matrix

The backtesting landscape divides cleanly into three paradigms — vectorized engines optimized for parameter sweeps, event-driven engines built for execution realism, and hybrid systems attempting both. Your system occupies a unique position: a Rust vectorized core with Python orchestration connected via subprocess IPC.

| System | Architecture | Language | IPC Mechanism | Parallelism Strategy | State Management | Checkpoint Approach |
|--------|-------------|----------|---------------|---------------------|-----------------|-------------------|
| **VectorBT** | Vectorized | Python/NumPy/Numba | None (single-process) | SIMD via NumPy broadcasting + Numba prange | Stateless (array ops) | None built-in |
| **Backtrader** | Event-driven | Python | None (single-process) | multiprocessing per parameter set | Cerebro lines-based | None built-in |
| **Zipline** | Hybrid (Pipeline vectorized + event execution) | Python | None (single-process) | None built-in | Time-frontier streaming | None built-in |
| **QuantConnect/Lean** | Event-driven streaming | C# (.NET) | Python.NET in-process bridge | Docker container per backtest | Slice-based event state | Cloud node isolation |
| **NinjaTrader** | Event-driven | C#/.NET 4.8 | None (monolithic GUI) | Multi-threaded Strategy Analyzer | State machine lifecycle | None documented |
| **MetaTrader 5** | Event-driven | MQL5 (native x64) | TCP/IP to distributed agents | **50,000+ cloud agents** per-param-set | OnTick event callbacks | Agent-level task caching |
| **Nautilus Trader** | Event-driven | Rust core + Python/Cython/PyO3 | In-process FFI (no IPC) | Single-threaded by design; multi-process for isolation | MessageBus pub/sub + Cache | Redis-backed state optional |
| **RustQuant** | N/A (math library) | Rust | N/A | N/A | N/A | N/A |

**RustQuant is not a backtesting engine.** It provides stochastic process simulation, option pricing, and automatic differentiation — comparable to QuantLib, not Backtrader. For Rust-native backtesting, Barter-rs provides an actual event-driven engine with broker/order/strategy abstractions.

The fundamental tradeoff splits along one axis: **speed versus realism**. VectorBT processes 1,000,000 strategy simulations in ~20 seconds by treating each backtest as a column in a NumPy matrix. Nautilus Trader models full order-book depth with nanosecond-resolution timestamps but runs single-threaded backtests by design. Your system's Rust evaluator achieving **500+ evals/sec with 32 Numba threads** positions it closer to VectorBT's throughput philosophy while maintaining M1 sub-bar simulation fidelity — a combination no existing system achieves.

MetaTrader 5 stands alone in distributed parallelism. Its MQL5 Cloud Network has completed over **16 billion optimization tasks** using ~50,000 remote agents. Each agent receives price data on first run, caches locally, and executes independent parameter evaluations. Genetic optimization caps at 256 passes per generation via a single network access point due to synchronization requirements — a constraint your NSGA-II Island Model sidesteps by keeping the entire population in shared NumPy memory.

Three insights emerge from comparing architectures. First, no production system uses subprocess + Arrow IPC as its primary Python-Rust bridge — this is genuinely novel territory. Second, the "vectorized screening → event-driven validation" workflow appears across multiple quant teams, suggesting your staged pipeline (Signal → Time → Risk → Refinement) follows an established pattern. Third, backtest-to-live parity drives event-driven adoption (Nautilus, Lean, Backtrader all emphasize "same code for backtest and live"), but since your system is optimization-focused rather than live-trading-focused, this consideration is less relevant for V1.

---

## Deliverable 2: IPC pattern validation — evidence for and against Arrow IPC

Arrow IPC is technically excellent but architecturally unnecessary if in-process FFI is viable. The evidence from production systems strongly favors PyO3 in-process bindings, with Arrow IPC as a solid fallback when process isolation is genuinely required.

### Measured IPC transport performance

| Mechanism | 1 KB Throughput | 100 MB Transfer Time | Latency per Message |
|-----------|----------------|---------------------|-------------------|
| Shared memory (POSIX shm) | 1,049 MB/s | ~6 ms | ~2 μs |
| Unix socket | 5,690 MB/s (large) | ~18 ms | ~26 μs |
| Named pipe (FIFO) | 388 MB/s | ~258 ms | ~57 μs |
| Memory-mapped file (mmap) | 1.7M msg/s at 1KB | ~6 ms | varies |
| **PyO3 in-process FFI** | **Memory speed** | **~0 ms** | **~25-70 ns** |

The serialization comparison reveals Arrow's unique advantage: **zero serialization overhead** when both sides use Arrow format. Protobuf encode/decode costs 884/1,179 ns per operation. FlatBuffers decode at 19 ns via pointer access. Arrow IPC requires no encode/decode at all — the wire format IS the in-memory format.

Arrow IPC file reads with memory mapping show **0 MB RSS** — effectively free I/O via zero-copy mmap. Feather V2 (uncompressed Arrow IPC) reads a 1.52 GB CSV dataset to an Arrow Table in ~1.5 seconds versus ~2.0 seconds for Parquet with Snappy. With LZ4 compression, Arrow IPC files shrink 44% while adding only ~0.2 seconds of decompression overhead.

### What production systems actually do

**Nautilus Trader** runs Rust and Python in the **same process** via Cython FFI and PyO3 bindings — no cross-process IPC at all. Data streams at up to **5 million rows per second** through the in-process boundary. Arrow is used only for data persistence (StreamingFeatherWriter for the data catalog), not for runtime IPC.

**Polars** uses PyO3 with the Arrow C Data Interface and PyCapsule protocol for **zero-copy** data exchange. The `pyo3-arrow` crate implements `__arrow_c_array__`, `__arrow_c_stream__`, and `__arrow_c_schema__` methods. When integrated with Ray for distributed computing, Polars data can be stored/retrieved from Ray's object store without serialization because both use Arrow format internally.

**DataFusion** uses PyO3 for Python bindings (in-process). For distributed execution via Ballista, it uses gRPC + protobuf for scheduler-executor communication and **Arrow IPC for data transfer** between executor nodes. This is the canonical example of Arrow IPC for cross-process data movement.

**The Feast project** (feature store) documented in GitHub issue #2013 that "serialization costs for protobuf are very high" and investigated switching to Arrow to "decrease serialization costs by a lot" — real-world evidence that Arrow IPC outperforms protobuf for large tabular data transfer.

### Subprocess + Arrow IPC overhead model for your system

For a typical evaluation batch of ~100 MB (96K bars × multiple parameters):

| Component | Estimated Time | Notes |
|-----------|---------------|-------|
| Arrow IPC serialization (Python) | 10-20 ms | Near-zero for numeric columns |
| Pipe write (100 MB) | 20-258 ms | 5.7 GB/s via socket; 388 MB/s via named pipe |
| Arrow IPC deserialization (Rust) | 1-5 ms | Predominantly zero-copy |
| **Total IPC round-trip** | **~30-280 ms** | Socket vs. pipe varies 9x |
| Subprocess spawn (one-time) | 50-200 ms | Amortized if long-running |

At 50ms per evaluation with batches of 100 parameters, each batch takes ~5 seconds of compute. IPC overhead of 30-280ms represents **0.6-5.6%** of batch compute time — acceptable but not negligible. Switching from named pipes to Unix sockets (or shared memory on Linux) would reduce this to under 1%.

### Verdict on your Arrow IPC decision

**The architecture is defensible for your specific constraints but not the industry-standard approach.** Your Windows NRT memory accumulation issue that causes ACCESS_VIOLATION crashes provides a genuine engineering reason for subprocess isolation. However, consider a migration path: start with subprocess + Arrow IPC for V1 stability, but design the Rust engine's API so it can be wrapped with PyO3 bindings later. This gives you the escape hatch to move to in-process FFI once you've resolved the memory management issues or moved to Linux.

---

## Deliverable 3: Python-Rust bridge best practices from production systems

Six production systems reveal three distinct bridge patterns, with PyO3 in-process being the overwhelming consensus choice.

### Bridge pattern comparison

| Dimension | PyO3 In-Process | Subprocess + IPC | Hybrid CFFI + PyO3 |
|-----------|----------------|-----------------|-------------------|
| **Used by** | Polars, pydantic-core, DataFusion | Ruff (old ruff-lsp, since abandoned) | Nautilus Trader, cryptography |
| **Per-call overhead** | 25-70 ns bare; 200-400 ns with arg conversion | ~1-10 ms (IPC + serialization) | Similar to PyO3 |
| **Crash isolation** | Rust panic → PanicException (same process) | Full process isolation | Same process |
| **Data transfer** | Zero-copy possible via Arrow PyCapsule | Requires serialization | Pointer-based FFI |
| **GIL impact** | Must explicitly release via `py.allow_threads()` | No GIL contention | Must explicitly release |

### Nautilus Trader's bridge (the most relevant precedent)

Nautilus Trader employs a **triple-mechanism hybrid**: PyO3 bindings, Cython C extensions, and C FFI via `cbindgen`, controlled by Rust feature flags (`ffi`, `python`, `extension-module`). The production path statically links Rust libraries to Cython-generated C extension modules. The PyO3 bindings are compiled into a single `nautilus_trader.core.nautilus_pyo3` extension module.

Domain objects cross the boundary via dedicated conversion functions (`instrument_any_to_pyobject`, `pyobject_to_instrument_any`). Interned strings (`Ustr`) minimize allocations for repeated identifiers like venue names and instrument IDs. The critical architectural insight: **events are immutable and timestamped**, flowing through an in-process message bus — the same pattern your system uses for evaluation results flowing from Rust to Python.

Nautilus uses a **crash-only design** where startup and crash recovery share the same code path. Unrecoverable errors (data corruption, invariant violations) trigger immediate process termination via `panic = abort`. This philosophy argues against subprocess isolation — instead of trying to survive Rust crashes, design the Rust code to be correct and restart fast.

### Polars' zero-copy pattern (the gold standard for data transfer)

Polars demonstrates the optimal data transfer pattern. Python `Series` objects store a `_s: PySeries` attribute that is a direct FFI bridge to the Rust struct. Multiple conversion paths exist: `sequence_to_pyseries`, `numpy_to_pyseries`, `arrow_to_pyseries`, `pandas_to_pyseries`. The **Arrow PyCapsule Interface** provides zero-copy exchange — no serialization, no copying, just pointer transfer.

For your system, the equivalent pattern would be: Python constructs parameter batches as Arrow arrays → passes to Rust via PyCapsule (zero-copy) → Rust computes results → returns result arrays via PyCapsule (zero-copy). Total per-batch boundary crossing cost: **~100-500 ns** versus the ~30-280 ms your subprocess approach requires.

### The Ruff lesson: subprocess → in-process migration

Ruff's evolution provides the strongest cautionary tale about subprocess architecture. The old `ruff-lsp` used Python to invoke `ruff` as a subprocess for each request. The documented problems: "Repeatedly running Ruff as a stateless subprocess resulted in unnecessary overhead for each request" and "Couldn't implement LSP features that required tracking state across multiple requests." The solution was `ruff server` — a Rust-native server built into the binary itself. Your system faces the analogous challenge: as the optimizer becomes more sophisticated, it will want to share state with the Rust evaluator (cached indicator computations, pre-allocated buffers) that subprocess isolation makes expensive.

### Concrete recommendations for your system

**Error handling:** Define a Rust error enum with variants mapping to Python exception types. Implement `From<YourError> for PyErr` for automatic conversion. Set `panic = abort` for production if crash-only recovery is appropriate (the Nautilus pattern). Never rely on PanicException for control flow.

**GIL management:** Always release the GIL explicitly via `py.allow_threads()` for compute-heavy Rust calls. The GIL is never automatically released in PyO3, even if the `py` token is unused. Enable `pyo3_disable_reference_pool` for tight loops to eliminate global ref-count synchronization overhead.

**Data transfer:** For columnar bulk data, use Arrow via `pyo3-arrow` with PyCapsule Interface. For domain objects, create dedicated wrapper types following the `PyDataFrame`/`PySeries` pattern. For repeated string identifiers (pair names, timeframe labels), use interned strings. Avoid passing Python lists/dicts across the boundary in hot paths — convert to Rust types immediately.

**Build/distribution:** Use `maturin` + `pyproject.toml`. Provide pre-built binary wheels so users don't need a Rust toolchain. Use the `pyo3/abi3` feature for stable ABI across Python versions (the cryptography pattern). Test the PyO3 boundary with mocked shims (the Nautilus pattern).

---

## Deliverable 4: State machine pattern catalog for pipeline orchestration

Six orchestration systems were analyzed for their state management, gate conditions, approval workflows, and failure recovery patterns. The findings directly inform your walk-forward optimization pipeline design.

### Pattern 1 — Quality gate ("proceed only if metric exceeds threshold")

The most universal pattern. Implementation varies by system:

- **Temporal.io**: Native in workflow code — `if sharpe < threshold: raise ApplicationError("Quality gate failed")` with automatic compensation via saga pattern. The workflow state survives crashes transparently.
- **Dagster**: Declarative `@asset_check` decorators produce PASS/FAIL results attached to assets, with `Severity.ERROR` blocking downstream execution. The most elegant declarative approach.
- **Airflow**: `BranchPythonOperator` evaluates metrics and routes to success or failure task paths. Functional but imperative.
- **Argo Workflows**: `when` expressions on DAG tasks — `when: '{{steps.evaluate.outputs.parameters.sharpe}} > 1.0'` — the most readable for YAML-based pipelines.

For your pipeline, quality gates should fire after each walk-forward window's optimization completes, checking aggregate metrics (Sharpe, max drawdown, walk-forward efficiency) before proceeding to the next pipeline stage.

### Pattern 2 — Approval gate ("wait for human review")

Only Temporal and Argo provide first-class approval workflows. Temporal uses signals: the workflow calls `await workflow.wait_condition(lambda: self.approved)` and an external system (Slack bot, web UI) sends a Signal when the operator approves. Timeout handling is built-in — if no approval within N hours, the workflow executes compensating actions automatically. Argo provides a native `suspend: {}` template with a UI dropdown for YES/NO input and optional duration timeout.

Airflow, Dagster, and Luigi require workarounds — typically external sensors polling a database or API for an approval flag. Prefect offers `pause_flow_run()` / `suspend_flow_run()` with API-based resume, which is functional but less ergonomic than Temporal's signal pattern.

### Pattern 3 — Checkpoint-resume ("restart from last successful state")

Three fundamentally different approaches exist:

**Target-based (Luigi):** A task is "done" if its output file exists. On restart, the system walks the dependency tree backward, checking which outputs exist, and skips completed tasks. Simple, robust, and the closest to your "result cache keyed by parameter hash" approach.

**Event History replay (Temporal):** Every activity result, timer, and signal is durably recorded. On worker crash, the server detects a missed heartbeat, replays the Event History on a new worker, and resumes from the last recorded event. Zero checkpoint code required — this is Temporal's core value proposition. The strongest guarantee of any system surveyed.

**IO Manager persistence (Dagster):** Op outputs are persisted via IO Managers (S3, local filesystem, etc.). The `FROM_FAILURE` retry strategy loads prior successful outputs from storage and re-executes only from the failure point. Requires explicit configuration of what to persist and where.

### Pattern 4 — Saga (compensating transactions for rollback)

Temporal provides native saga support that survives crashes:

```
try:
    model_id = await activity(train_model)
    compensations.append(delete_model)
    await activity(validate_model, model_id)
    registry_id = await activity(register_model, model_id)
    compensations.append(unregister_model)
except:
    for comp in reversed(compensations):
        await comp()
```

Prefect 2+ offers `on_rollback` transaction lifecycle hooks. Argo uses exit handlers with conditional failure steps. Airflow and Dagster require manual implementation.

### Recommended orchestration for your pipeline

For a walk-forward optimization pipeline with quality gates and operator approval between stages, the recommended stage design follows this state machine:

```
WINDOW_PENDING → DATA_LOADED → OPTIMIZATION_RUNNING → 
OPTIMIZATION_COMPLETE → QUALITY_GATE_CHECK → 
  [if passed] → AWAITING_APPROVAL → 
    [if approved] → NEXT_STAGE
    [if rejected or timeout] → COMPENSATE → TERMINATED
  [if failed] → RETRY_OR_ESCALATE
```

Each gate has four components: metric thresholds (Sharpe > 1.0, MaxDD < 15%), timeout with default-reject, compensation actions (cleanup partial results), and notification/escalation on failure. **Temporal.io** provides the strongest implementation for this pattern due to its durable execution model and native signal-based approval gates. For a simpler V1, implement this as a Python state machine with SQLite-backed state persistence — you can migrate to Temporal later if the pipeline complexity grows.

---

## Deliverable 5: Checkpoint strategy recommendation

### Recommended approach: two-level with SQLite WAL result caching

Your system's architecture — millions of parameter evaluations across walk-forward windows, each evaluation taking ~2ms (at 500 evals/sec) via subprocess Rust compute — maps optimally to a two-level checkpoint strategy borrowed from HPC's SCR (Scalable Checkpoint/Restart) pattern.

**Level 1 (fine-grained): Per-evaluation result persistence to SQLite WAL.** After each evaluation batch completes, INSERT results into SQLite keyed by `hash(parameter_set + window_id) → result`. With WAL mode and `PRAGMA synchronous=NORMAL`, each INSERT costs ~0.1-0.5ms. For 2ms evaluations, this represents **5-25% overhead per evaluation** — too high for individual inserts. The fix: batch commits. Accumulate 100 results in memory, then COMMIT once. Overhead drops to **0.05-0.25%** — negligible. Maximum lost work on crash: 100 evaluations ≈ 0.2 seconds of compute.

**Level 2 (coarse-grained): Per-window comprehensive checkpoint.** After completing each walk-forward window, write: all evaluation results for the window (already in SQLite), optimizer state (population, generation counter, RNG state as pickle), and window metadata (boundaries, training/test dates, completion timestamp). This checkpoint enables restarting the entire optimization from any completed window boundary.

### SQLite configuration for high-throughput checkpointing

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;  -- Safe in WAL mode, avoids per-commit fsync
PRAGMA cache_size = -64000;    -- 64MB cache
PRAGMA temp_store = MEMORY;
PRAGMA mmap_size = 30000000000;
```

With WAL mode, writes are sequential (append to WAL file) and reads are non-blocking. The `synchronous=NORMAL` setting is **completely corruption-safe in WAL mode** — only WAL checkpoint operations require fsync, not every individual commit. Run `PRAGMA wal_checkpoint(PASSIVE)` every ~10,000 evaluations in a background thread to prevent WAL file growth.

### Overhead model for your system

| Metric | Per-Eval Insert | Batched (N=100) | Per-Window |
|--------|----------------|-----------------|------------|
| Checkpoint cost | 0.1-0.5 ms | 0.1-0.5 ms total | ~10 ms |
| Overhead (at 2ms/eval) | 5-25% | 0.05-0.25% | <0.01% |
| Max lost work | 0 evals | 100 evals (0.2s) | 1 window |
| DB size (1M evals) | ~200 MB | ~200 MB | +pickle files |

**Recovery procedure:** On startup, query SQLite for all completed evaluations. Build a set of `(parameter_hash, window_id) → result`. For each evaluation needed, check the cache first. Skip any evaluation already in the cache. Resume the optimizer from saved state plus completed results. Recovery time: **under 1 second** regardless of how many evaluations were previously completed.

### Comparison with alternative approaches

The Optuna per-trial DB persistence pattern validates this approach — Optuna stores every completed trial via `load_if_exists=True` and handles millions of trials with PostgreSQL/MySQL. Your SQLite-based approach is simpler and avoids network latency for a single-machine system.

PyTorch's CheckFreq research (USENIX FAST'21) demonstrated that iteration-level checkpointing with automatic frequency tuning bounds overhead within **3.5%** while reducing recovery time from hours to seconds. Your batched-commit approach achieves similar properties.

The HPC multi-level philosophy (SCR) proves that handling 85% of failures with cheap local checkpoints (Level 1) and reserving expensive persistent checkpoints (Level 2) for catastrophic failures yields up to **35% efficiency gains** over single-level approaches. Your two-level design follows this proven pattern.

---

## Deliverable 6: "Steal these ideas" — innovations worth adopting

### From VectorBT: chunked parameter processing with garbage collection

VectorBT PRO's `@vbt.chunked` decorator processes parameter combinations in batches (e.g., 100 at a time) with explicit cache clearing and garbage collection between chunks. This directly solves the RAM limitation that constrains vectorized approaches. **Steal this:** Apply the same pattern to your Rust evaluator — process parameter batches of configurable size, explicitly free intermediate memory between batches. This prevents the memory accumulation that causes your Windows NRT crashes without requiring subprocess isolation.

### From MetaTrader 5: automatic optimization mode switching

MT5 auto-triggers genetic optimization when the parameter space exceeds **100 million combinations**. Below that threshold, exhaustive search runs. **Steal this:** Implement automatic optimizer selection based on parameter space size. For small spaces (<10K combinations), use exhaustive grid search for guaranteed coverage. For medium spaces (10K-1M), use your NSGA-II. For large spaces (>1M), use the Island Model with stochastic cross-validation as a regularizer.

### From Nautilus Trader: crash-only design with interned strings

Nautilus uses `Ustr` (interned strings) for repeated identifiers — venue names, instrument IDs, order types. Each unique string is stored once in a global pool; subsequent uses are just pointer comparisons. The crash-only design means startup and recovery share the same code path — no special "resume" logic exists. **Steal this:** Intern all repeated string identifiers in your Rust evaluator (pair names, timeframe labels, parameter names). Design your evaluator so starting fresh and resuming from a checkpoint use the same initialization path — only the input differs (empty vs. cached results).

### From Polars: Arrow PyCapsule Interface for zero-copy boundary crossing

Polars implements `__arrow_c_array__`, `__arrow_c_stream__`, and `__arrow_c_schema__` PyCapsule methods, enabling any Arrow-compatible library to exchange data with zero copying. Even if you start with subprocess IPC, **design your Rust evaluator's API around Arrow RecordBatch input/output** so you can later switch to PyCapsule-based zero-copy transfer via PyO3 with no changes to the Rust computation code.

### From Temporal.io: signal-based approval with durable execution

Temporal's pattern of workflows waiting on signals (`await workflow.wait_condition(lambda: self.approved)`) with automatic timeout and compensation is the cleanest human-in-the-loop pattern discovered. **Steal this:** Even without adopting Temporal, implement a similar pattern in your Python orchestrator. After each pipeline stage completes, write a "pending approval" record to your SQLite state DB with a timeout. A separate process (or manual script) can update this record to "approved" or "rejected." Your orchestrator polls for the approval state, proceeding or compensating accordingly. This gives you Temporal-style approval gates with zero infrastructure overhead.

### From Luigi: target-based idempotency as core design principle

Luigi's insight that "a task is done if its output exists" eliminates an entire class of state management bugs. **Steal this:** Make every evaluation in your system idempotent and keyed by `hash(parameters + window_boundaries + data_version)`. Before running any evaluation, check if the result already exists in SQLite. This makes your system naturally crash-resilient — restart simply means "re-run the script," and it automatically skips all completed work.

### From DataFusion/Ballista: Arrow IPC for distributed data transfer

Ballista uses gRPC for coordination (small messages) and Arrow IPC for data transfer (large datasets) between distributed executors. **Steal this:** If you ever scale to multi-machine optimization, use the same split — lightweight coordination protocol (even simple TCP or ZeroMQ) for task assignment, and Arrow IPC for shipping price data and results. This avoids the latency tax of serializing large datasets through protobuf while keeping coordination messages simple.

### From Ruff's migration story: design for in-process escape hatch

Ruff started as a subprocess tool and migrated to an in-process server when "repeatedly running as a stateless subprocess resulted in unnecessary overhead." **Steal this:** Structure your Rust evaluator's code so the core computation functions are a library (`lib.rs`), with the subprocess binary (`main.rs`) being a thin wrapper that reads Arrow IPC from stdin and writes results to stdout. When you're ready to migrate to PyO3, you build PyO3 bindings around the same library functions — no rewrite of computation logic required. The subprocess binary becomes a fallback for debugging and testing.

---

## Architectural synthesis and the path forward

Your system occupies a unique and defensible position in this landscape. No existing backtesting system combines Rust-speed vectorized evaluation, Python-orchestrated walk-forward optimization with cross-validation objectives, and subprocess-based process isolation with Arrow IPC. The closest analogs are VectorBT (vectorized throughput without Rust or WFO), Nautilus Trader (Rust+Python without vectorized optimization), and MT5 (distributed optimization without Python/Rust).

The **highest-impact architectural change** this research suggests is designing the Rust evaluator as a library with a subprocess wrapper, not a subprocess-only binary. This costs nothing now and provides a zero-friction migration path to PyO3 in-process bindings later. The potential speedup is significant: eliminating IPC overhead of 30-280ms per batch at your target scale of millions of evaluations translates to saving **8-78 hours of pure IPC overhead** per million-evaluation optimization run.

The **lowest-risk, highest-value immediate adoption** is SQLite WAL-backed result caching with batched commits. At 0.05-0.25% overhead, it provides per-evaluation crash recovery and enables the "restart by re-running the script" pattern that eliminates complex recovery logic entirely. Combined with your two-level checkpointing design, this matches the robustness of enterprise HPC systems at a fraction of the complexity.