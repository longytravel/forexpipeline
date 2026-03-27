# RB-3A Deep Research: Backtesting Engine Architecture and Competitive Validation

## Research context and evaluation lens

This research targets external validation of a specific architectural direction: subprocess orchestration, Arrow IPC for high-throughput data interchange, a pipeline state machine, and checkpoint/resume designed for windowed evaluation (to support Stories 3-3, 3-4, 3-5). fileciteturn0file0

Across production and widely-used open-source backtesters, there is a consistent “shape” to high-performance design decisions:

Backtesting engines optimise either for **throughput at scale** (testing many parameter sets quickly) or **execution realism and parity with live trading**, and systems that aim for both tend to become **hybrids**: vectorised or batch computation where causality constraints allow it, and event-driven simulation for anything involving order lifecycle, fills, slippage, and latency-like sequencing. citeturn5search1turn19view0turn21view2

A second pattern: engines that scale to large optimisation workloads typically do so by treating each backtest run (or run-slice) as an **independent unit of work** that can be scheduled across processes/threads/agents and re-run if a worker crashes. This “embarrassingly parallel optimisation” model shows up explicitly in retail-professional platforms such as NinjaTrader and MetaTrader 5, and in cloud platforms such as QuantConnect’s optimisation jobs. citeturn9search2turn9search1turn1search5turn4search7turn4search3

The remainder of this report uses that lens—**data movement, determinism, parallelism, orchestration state, and crash recovery**—to evaluate whether Arrow IPC + subprocess + state-machine checkpointing is aligned with how strong systems actually behave.

## Competitive architecture matrix

The table below focuses on what is architecturally transferable to a *single-pair forex V1*, rather than multi-asset breadth.

| System | Engine paradigm | Core runtime + extensibility model | Parallelism and scaling model | State + checkpoint posture | Evidence relevant to your design |
|---|---|---|---|---|---|
| VectorBT (open source) | Hybrid: vectorised arrays + event-driven callbacks (inside Numba loops) | Python API operating on pandas/NumPy; heavy use of Numba; portfolio engine exposes “records/logs” structures | Primarily “single-process speed”: Numba compilation and operating on arrays; parallelism is mostly within compiled functions or via wide arrays | No first-class checkpoint/resume; typical workflow is rerun-fast rather than resume-mid-run | Two simulation modes are explicitly supported (vectorised signals/records and event-driven callbacks). citeturn19view0 |
| VectorBT PRO | Extension of VectorBT with chunking + parallel execution backends | Adds chunking specs and infra around Numba functions and simulation functions; adds structured decorators for sweeping params and tasks | Explicit support for: chunking (split arrays, merge results), parallel Numba, multithreading, multiprocessing, and even Ray-backed execution for chunk backends | Still largely “rerun tasks” rather than resume; but chunking creates a natural mid-level granularity for progress tracking | Chunking as a first-class mechanism (split/execute/merge) maps closely to “windowed evaluation” and evaluation-level checkpoints. citeturn20view0turn20view1 |
| Backtrader | Event-driven core, with batch/“runonce” acceleration for indicators | Strategy lifecycle and engine orchestration via Cerebro; batch computation for indicators (“runonce”) reduces overhead vs per-bar calculations | Supports multi-core optimisation via Python multiprocessing, plus optimisations to reduce repeated data loading and to reduce return payload | Optimisation improvements explicitly reduce what is returned from workers (“optreturn”) and preload data once (“optdatas”), implying a design that expects many repeated runs | Backtrader explicitly improves multiprocessing optimisation by preloading once in the main process before spawning subprocesses and by returning reduced result objects. citeturn21view0turn21view1 |
| Zipline (Quantopian) + maintained forks (Zipline Trader / Zipline Reloaded) | Event-driven engine with vectorised factor computation via Pipeline API | Pythonic algorithm interface; “bundles” preload/store data; Pipeline expresses cross-sectional/time-window computations more efficiently than pure event loops | Parallelism is not the core story; the main “speed lever” is efficient data handling and vectorised factor computation | Data bundles are a durable cache layer; checkpoint/resume is generally “rerun backtest” | Data bundles are a deliberate preload-and-cache boundary; Zipline is described as event-driven, and Pipeline is described as vectorising factor computations where possible. citeturn0search14turn10search2turn10search15 |
| QuantConnect Lean (open-source engine) | Event-driven, professional-grade modular engine | C# engine with plug-in points; supports Python strategies (via wrapper) and modular modelling (slippage, brokerage models etc.) | Cloud-side scaling achieved via running many backtests; optimisation jobs enable running multiple backtests concurrently | Cloud jobs are naturally restartable because each run is a separate job unit; emphasis is on consistent modelling rather than mid-run resume | Lean positions itself as modular and event-driven; QuantRocket analysis highlights that bridging Python into the C# engine can add overhead compared to native use of scientific libraries. citeturn11view0turn16view0turn11view1 |
| NinjaTrader (platform) | Event-driven (strategy execution), with heavy focus on optimisation workflows | .NET/NinjaScript; strategy analysis tooling designed for repeated backtest/optimisation runs | Strategy Analyzer optimisation uses multiple cores/threads; users confirm multi-core utilisation is tied to backtests/optimisations | Work is organised as iterative runs over parameter ranges; crash recovery is generally at the run/unit level | NinjaTrader support forums state Strategy Analyzer optimisation uses multiple cores/threads and that multi-core utilisation is tied to backtest/optimisation workloads. citeturn9search2turn9search3turn9search5turn9search11 |
| MetaTrader 5 (platform by entity["company","MetaQuotes","metatrader developer"]) | Event-driven execution for EAs, with industrialised distributed optimisation | MQL5 strategy tester; supports remote agents and a cloud agent network | Distributed optimisation is explicitly “many independent runs” distributed across agents; remote agents run as separate processes; cloud network distributes tasks among agents | The tester model strongly encourages run-level restartability: each “run” is independent; practical checkpointing is via splitting the search space | Remote agents are a dedicated service; each optimisation run is performed as a separate process on a separate agent, and cloud network distributes optimisation tasks among agents. citeturn9search1turn1search5turn1search2turn1search15 |
| NautilusTrader | Deterministic event-driven runtime for research + live parity | Rust-native core, Python as control plane; bindings via PyO3 with migration from Cython; layered architecture with message bus | Notably: a single-threaded core for determinism; background services can be threaded/async; guidance explicitly recommends one node per process for parallelism/isolation | Optional persistence (including Redis-backed state); strong “crash-only / fail-fast” orientation; process boundaries are a first-class design tool | This is the closest architectural analogue: single-threaded deterministic core, thread-local message bus + channels to core, and explicit recommendation to run each node in its own process for parallel execution/isolation. citeturn12view0turn12view1 |
| RustQuant | Mostly quant finance primitives (pricing/risk/data IO), not a full backtesting engine | Pure Rust library modules for data types, instruments/pricing, IO, error handling | Not positioned as an execution simulator | N/A for checkpointing; not the same problem space as an engine | Useful as a signal about Rust quant ecosystem direction (IO, data structures), but not directly comparable to backtesting orchestration. citeturn8search0turn8search17 |

### Cross-system takeaways that matter for Arrow IPC + state machine

A consistent theme is that “big” optimisation workloads are handled via **scheduling many independent runs** and aggregating results, rather than trying to parallelise the inner loop of one simulation while maintaining realism. This is explicit in Backtrader’s optimisation model (multiprocessing with preload + reduced returns), NinjaTrader’s Strategy Analyzer multicore optimisation, and MT5’s agent-based distributed optimisation. citeturn21view0turn9search2turn9search1turn1search5

The strongest architectural validation for your subprocess decision is NautilusTrader’s explicit “one node per process” stance for parallel execution or isolation, paired with a single-threaded deterministic core for event ordering. citeturn12view0turn12view1

## IPC and serialisation patterns

### What competitive backtesters actually do about IPC

Most open-source Python backtest frameworks (VectorBT, Backtrader, Zipline) are primarily designed as **in-process libraries**, so they don’t adopt elaborate orchestration/compute IPC layers by default; a typical workflow is “Python process loads data, runs simulation, emits results”. citeturn19view0turn21view2turn0search14

When these systems *do* cross process boundaries, it is usually for **parameter optimisation**, and the IPC is usually whatever the host runtime provides:

Backtrader uses Python multiprocessing for optimisation, and its own docs focus on reducing process overhead by preloading once (optdatas) and returning smaller payloads (optreturn)—a strong signal that payload size and serialisation overhead are a real bottleneck in practice. citeturn21view0turn7search11

Python’s own documentation describes how multiprocessing “send/recv” over pipes serialises objects and recreates them on the other side, and warns that `recv()` unpickles the received data. That’s both performance-relevant (copying/serialisation cost) and a security note about unpickling. citeturn14view1turn14view0

### What that implies for Arrow IPC

Arrow IPC is directly positioned as a binary serialisation format for RecordBatches with a streaming format (sequential) and a file/random-access format that supports random access and is “very useful when used with memory maps”. citeturn3search0

That “file/random access + memory map” point is significant for your architecture because it gives you a concrete route to **low-copy transfer** of large columnar datasets across process boundaries using OS page cache semantics, rather than Python object graphs. citeturn3search0

Arrow also provides a higher-level RPC stack (Arrow Flight) built on gRPC and the Arrow IPC format, structured around streams of record batches. Flight is *not required* for a local subprocess design, but it is a strong signal that the Arrow ecosystem treats “record batch streams” as a first-class IPC primitive even over the network. citeturn3search5turn3search9

### Shared memory alternatives and what they prove

If you want **process-to-process zero-copy semantics**, the “shared memory object store” family matters. The (historical) Plasma object store (originating in the Arrow ecosystem and used in Ray) is described as holding immutable objects in shared memory so they can be accessed efficiently by many clients across process boundaries, and Ray’s docs also emphasise an immutable shared-memory object store for transferring objects across processes/nodes. citeturn2search10turn2search7

This does not mean you should adopt Plasma/Ray, but it reinforces a key architectural point: “high-performance multiprocess compute” tends to converge on **immutable shared buffers + metadata references**, rather than pickling mutable Python objects. Arrow IPC and Arrow-based memory models fit that direction. citeturn2search10turn2search7turn3search0

### Validation verdict for Arrow IPC in your specific context

Evidence from the backtesting competitors suggests:

* Arrow IPC is **not the norm** inside classic Python backtest libraries because they are not structured as orchestration/compute layers.
* Subprocess boundaries *are* extremely common for scaling optimisation workloads (Backtrader; NinjaTrader; MT5; QuantConnect optimisation jobs), which validates “one run per process/agent” as a realistic scaling unit. citeturn21view0turn9search2turn9search1turn4search7
* Where those systems rely on default IPC (Python multiprocessing pipes/pickling), the ecosystem actively works to minimise payloads, implying that **your decision to design an efficient, schema’d, columnar IPC** is directionally aligned with real pain points. citeturn21view0turn14view0

One caveat: Arrow IPC will only “pay for itself” if you are actually transferring **large tabular/columnar data** or high-frequency batch results across the process boundary. If most messages are small control-plane events (progress, metrics, errors), then the transport can be simpler, and Arrow can be reserved for the heavy payloads. This “split control-plane vs data-plane” stance is also common in systems thinking around message buses and background services (see Nautilus’ message bus / threaded services to core). citeturn12view0

## Python–Rust bridge patterns and best practices from real systems

### Pattern family: Rust core, Python control plane

NautilusTrader is the closest example to your target: a Rust-native core runtime, with Python serving as the control plane, and Python bindings provided via PyO3 (with an ongoing migration away from Cython). citeturn12view1turn1search1

Architecturally, Nautilus also makes two points that map directly to your “state machine + subprocess isolation” thesis:

* The **core runtime is single-threaded** to preserve deterministic event ordering and backtest/live parity; concurrency is pushed to background services and adapters, with results delivered into the core via a message bus. citeturn12view0  
* Parallel execution / workload isolation is achieved by running each node in its **own process** (and they explicitly note that multiple nodes concurrently in one process are not supported due to global singleton state). citeturn12view0

That combination (deterministic core + process-isolated parallelism) is a strong external validation of your “subprocess compute workers + state machine orchestration” direction, even though Nautilus’ particular IPC approach is via native bindings rather than Arrow IPC. citeturn12view0turn12view1

### Pattern family: In-process “zero-copy” interchange using Arrow C interfaces

For same-process Python–Rust data exchange, the Arrow ecosystem has converged on ABI-stable interfaces:

DataFusion’s Python bindings explicitly implement the Arrow PyCapsule interface / Arrow C Data Interface for exporting record batches, described as enabling zero-copy interchange with libraries supporting that interface. citeturn2search5turn2search1turn3search2turn3search6

This establishes a best-practice principle:

*If Python and Rust can coexist in-process safely (e.g., via PyO3), then use Arrow C Data Interface / PyCapsule-style interchange to avoid serialisation copies.*

For your design, that principle becomes a decision rule:

* If you keep the Rust backtester in a **separate process** for crash isolation and lifecycle control, Arrow IPC and/or shared-memory-backed Arrow buffers become your “data plane”.
* If you later introduce an **in-process fast path** (e.g., for low-latency interactive research), the Arrow C Data Interface can become the “same-process fast path”, consistent with DataFusion-style interchange. citeturn3search0turn3search6turn2search5

### Pattern family: Arrow memory model as the lingua franca for columnar analytics

Polars’ documentation explicitly describes the computation engine as written in Rust and built on the Apache Arrow columnar memory format, and Polars’ docs discuss moving data into/out of Arrow with (optionally) zero-copy. citeturn2search8turn3search14turn2search12

The “pyo3-polars” crate documents wrapper types (`PySeries`, `PyDataFrame`) that are designed to convert to/from Python by implementing the necessary PyO3 conversion traits. citeturn3search11

Together, these sources point to a practical best practice for Python↔Rust bridge design:

* Use Arrow-compatible columnar buffers and schema discipline as your interoperability foundation, regardless of whether you physically transmit via Arrow IPC streams/files, shared memory, or in-process PyCapsules. citeturn3search0turn3search6turn2search8turn2search5

### Process lifecycle and failure semantics

PyO3 positions itself as the standard way to write native Python modules in Rust or embed Python in Rust. citeturn2search0

However, subprocess designs provide failure isolation benefits that are hard to replicate in-process (segfaults, UB, accidental interpreter crashes). Nautilus explicitly leans on “one node per process” for parallel execution/isolation, and Prefect’s notion of CRASHED (interrupted by OS signal like SIGTERM) shows why distinguishing “crash” from “logical failure” matters in orchestration. citeturn12view0turn6search2

This distinction should directly inform Story 3-4 and Story 3-3: treat **worker crash** as a first-class state distinct from **strategy failure** or **validation failure**.

## Parallelism models in production backtesting workflows

### Parallelism “shapes” that show up repeatedly

In the studied systems, parallelism tends to take one of these forms:

1) **Per-parameter-set / per-run parallelism** (dominant in optimisation tooling)  
NinjaTrader defines optimisation as iterative backtests over parameter ranges, and support forum statements indicate the Strategy Analyzer optimisation uses multiple cores/threads. citeturn9search11turn9search2turn9search5  
MetaTrader 5’s remote agents model explicitly performs each run as a separate process on a separate agent, and its cloud network distributes optimisation tasks among agents. citeturn9search1turn1search5turn1search2turn1search15  
QuantConnect’s optimisation jobs are explicitly designed to run multiple backtests concurrently without requiring the user to provision multiple backtesting nodes. citeturn4search7turn4search3

2) **Chunked execution over data or parameter grids** (explicit in VectorBT PRO)  
VectorBT PRO introduces explicit chunking specifications (split arrays, execute, merge), and integrates multithreading, multiprocessing, and Ray backends for running chunks. citeturn20view0

3) **In-process throughput via compilation and vectorisation** (dominant in research-first libraries)  
VectorBT’s core value proposition is operating on pandas/NumPy objects and accelerating computations with Numba, with claims about very fast order fill simulation and explicit support for vectorised signals/records as well as event-driven callbacks. citeturn19view0

4) **Single-thread deterministic core + process-level scaling** (explicit in NautilusTrader)  
NautilusTrader describes a single-threaded deterministic core for event ordering, with background services and adapters running elsewhere and communicating into the core, and recommends one node per process for parallel execution/isolation. citeturn12view0turn12view1

### What this means for a single-pair forex V1

For single-pair forex, “per-pair parallelism” is irrelevant at V1 by design; what matters is how you scale:

* parameter grids (signals, thresholds, stop/take-profit variants),
* walk-forward windows (training slice → evaluation slice),
* and potentially multiple “scenarios” (fees, spreads, slippage assumptions).

The competitive evidence strongly suggests the safest scaling unit is the **independent run** (parameter set × window × scenario), mapped to processes/agents/threads depending on cost, while keeping the inner simulation core deterministic and simple. This is aligned with Backtrader optimisation via subprocesses, MT5 agent runs, NinjaTrader optimisation, QuantConnect optimisation, and Nautilus’ “node per process”. citeturn21view0turn9search1turn9search2turn4search7turn12view0

image_group{"layout":"carousel","aspect_ratio":"16:9","query":["MetaTrader 5 Strategy Tester remote agents","MQL5 Cloud Network agents optimization diagram","NinjaTrader 8 Strategy Analyzer optimization window"],"num_per_query":1}

## State machine patterns and checkpoint/resume at scale

### Proven state concepts from workflow orchestration

Even though Airflow/Dagster/Prefect are not backtesting-specific, they embody failure and resume semantics that map well to “millions of evaluations”:

Airflow defines a rich set of task instance states (none/scheduled/queued/running/success/failed/up_for_retry/etc.), explicitly modelling retries and upstream failures as different states. citeturn18search2turn18search12

Dagster provides run status sensors that react to run statuses (e.g., launching other runs, sending alerts on run failure, reporting success), reinforcing the idea that “status changes are events” useful for an engine-level state machine. citeturn6search1turn6search17

Prefect distinguishes `FAILED` from `CRASHED`, where CRASHED is explicitly tied to OS signals such as SIGTERM/KeyboardInterrupt, which is directly relevant to subprocess-based compute layers. citeturn6search2turn6search10

Manual approval gates are also a common pattern in orchestrators: Dagster discussions address manual approval processes conceptually, and Argo Workflows has an explicit “suspend” concept used for pausing and resuming pipelines (often used as a manual gate). citeturn6search5turn6search11

### Checkpointing: why “granularity” is the real decision

In large-scale computation, checkpointing is fundamentally a tradeoff between:

* the cost to write checkpoints, and
* the expected lost work when failures occur.

A classical result in HPC checkpointing literature is that an approximately optimal checkpoint period scales with the square root of (mean time between failures × checkpoint duration), often referenced as a Young/Daly-style relationship. citeturn15search1turn15search4

While a backtest optimisation workload is usually *not* a tightly-coupled MPI job, the same intuition applies: checkpointing too frequently adds overhead; checkpointing too rarely risks losing too much work when a process dies.

Crucially, competitive systems implicitly choose checkpoint granularity by designing optimisation around **independent runs**:

* MT5: each optimisation run is executed as a **separate process** on an agent, and optimisation tasks are distributed across agents. citeturn9search1turn1search5turn1search2  
* Backtrader: optimisation uses multiprocessing and invests in avoiding repeated preload and avoiding returning large strategy objects across process boundaries—suggesting that restarting failed or slow runs is acceptable because each run is bounded. citeturn21view0  
* VectorBT PRO: chunking splits large workloads into chunks, executes, merges, and supports many backends—again creating a natural “checkpointable” unit at the chunk boundary. citeturn20view0

### Recommendation: checkpointing strategy consistent with competitive reality

For a forex single-pair V1, the evidence supports a pragmatic checkpoint hierarchy:

**Data/materialisation checkpoint (coarse, durable)**  
Use a Zipline-like “bundle” concept: data plus metadata is preloaded/prepared once and cached for repeated runs. Zipline’s bundle documentation explicitly frames bundles as a way to preload all data needed for backtests and store it for future runs. citeturn10search2turn0search6

**Evaluation-level checkpoint (dominant, cheap, restartable)**  
Treat each (parameter set × window × scenario) evaluation as an idempotent unit, writing an append-only result record (metrics + provenance + schema version). This matches how optimisation systems are organised (MT5 agents, NinjaTrader optimisation, QuantConnect optimisation jobs). citeturn1search5turn9search2turn4search3turn4search7

**Optional mid-run checkpoint (only if runs are truly long)**  
Only add “resume from bar index N” style checkpoints if a single evaluation is long-running enough that re-running it is materially expensive. Competitive evidence suggests most platforms avoid requiring mid-run resume by structuring work into smaller independent runs (distributed optimisation “runs” rather than one monolith). citeturn9search1turn21view0turn20view0

Operationally, ensuring idempotency is a well-established reliability practice in job systems: Google’s guidance for retried jobs explicitly recommends making jobs idempotent so restarts don’t corrupt or duplicate output. citeturn15search5

## Validated recommendations for Stories 3-3, 3-4, 3-5

### Pipeline state machine design cues for Story 3-3

A robust backtesting pipeline state machine should borrow more from durable workflow engines than from “ad-hoc scripts”, because your runtime is explicitly multiprocess and failure-prone by design.

A concrete, externally-validated pattern is to model “failure” as multiple distinct terminal outcomes:

* `FAILED` (logic/validation failure) vs `CRASHED` (process death / OS signal), aligned with Prefect’s separation. citeturn6search2turn6search10  
* `UP_FOR_RETRY`/`RETRYING` as a first-class state, aligned with Airflow’s explicit modelling. citeturn18search2turn14view0  
* `PAUSED_FOR_APPROVAL`/`SUSPENDED` as a first-class gate state, aligned with Argo suspend patterns and Dagster’s “manual approval process” discussions. citeturn6search11turn6search5

Designing transitions around “status events” enables a Dagster-like sensor model for actions (notify, enqueue next stage, halt on anomaly, request human sign-off). citeturn6search1turn6search17

### Python–Rust boundary recommendations for Story 3-4

External evidence supports a “two-lane” interface approach:

**Lane A: control-plane messages (small, frequent)**  
Use a simple, versioned envelope that carries: run-id, stage-id, schema version, and error/trace payloads. This lane can tolerate normal serialisation because payloads are small.

**Lane B: data-plane payloads (large, tabular)**  
Use Arrow to move large columnar data and results efficiently. Arrow IPC explicitly supports streaming batches and a file/random-access format that is well-suited to memory mapping. citeturn3search0  
This is conceptually consistent with the Arrow ecosystem’s broader “table/batch interchange” story: Arrow Flight is built on IPC + gRPC for high-performance batch streaming over RPC. citeturn3search5turn3search9

Where you can keep things in-process, DataFusion’s Python interface demonstrates a best-practice “zero-copy interchange” approach via the Arrow C Data Interface / PyCapsule mechanism (exporting record batches as ArrowArray/ArrowSchema capsules). citeturn2search1turn2search5turn3search6

If you later need multi-worker shared datasets on one machine, the Ray/Plasma style shared-memory object store model is evidence that “immutable shared buffers” are a proven way to avoid cross-process copying. citeturn2search10turn2search7

Finally, account for operational reality: Python’s multiprocessing defaults and “safe start methods” have evolved (e.g., forkserver becoming default on POSIX platforms in Python 3.14) and resource tracking/leaked shared resources are discussed in the docs—this matters if you layer shared memory or memory maps under Arrow IPC. citeturn14view0turn13search2

### Backtester core architecture recommendations for Story 3-5

The external systems provide two strong, convergent signals:

**Determinism and event ordering are central.**  
NautilusTrader explicitly prefers a single-threaded core runtime to ensure deterministic event ordering and to preserve backtest/live parity, with other services feeding into that core. citeturn12view0turn12view1

**Optimisation scaling is outside the core loop.**  
MT5 and NinjaTrader push scaling into distributed/multicore “run many variants” machinery (agents/threads), not into a heavily parallelised single run, because the single-run simulation is fundamentally causal. citeturn9search1turn1search5turn9search2turn9search11

In practice this suggests:

* Build the Rust backtester crate as a **deterministic event-driven simulator** (single-threaded core, explicit time model, explicit order lifecycle), optimised for speed but not dependent on intrarun threading to scale. citeturn12view0turn5search19  
* Use the orchestrator (Python control plane + state machine) to run many independent evaluations in parallel across processes, and checkpoint at the evaluation/chunk boundary (VectorBT PRO and MT5 both reveal this pattern in different forms). citeturn20view0turn9search1turn1search5

### “Steal these ideas” list

The following are the most directly reusable ideas from competitors, given your subprocess + Arrow IPC + state-machine direction:

VectorBT PRO’s explicit chunking-and-merge infrastructure is a near-direct analogue to windowed evaluation: it makes workload partitioning a first-class concern and supports multiple parallel execution backends. citeturn20view0

Backtrader’s optimisation improvements (“preload once in main process”, “return placeholder results instead of full strategy objects”) are a concrete reminder that cross-process payload size dominates quickly; your Arrow IPC should prioritise small result payloads (metrics + minimal traces) and avoid shipping giant intermediate arrays unless needed. citeturn21view0

Zipline’s data bundle concept validates “durable precomputed datasets for repeated backtests” as a strong boundary for checkpointing and reproducibility. citeturn10search2turn0search6

NautilusTrader’s combination of (a) deterministic single-threaded core and (b) process-level isolation for parallel execution is the strongest architectural analogue for a production-grade simulator that needs backtest/live parity. citeturn12view0turn12view1

MetaTrader 5’s remote agents model is a canonical example of “run = process = scheduling unit” for distributed optimisation; it validates that treating each evaluation as an independent unit is not just academically clean, but commercially battle-tested at scale. citeturn9search1turn1search5

Airflow/Prefect state semantics validate modelling retries, crashes, and manual gates explicitly in the pipeline state machine, rather than smearing them into one generic “failed” state. citeturn18search2turn6search2turn6search11