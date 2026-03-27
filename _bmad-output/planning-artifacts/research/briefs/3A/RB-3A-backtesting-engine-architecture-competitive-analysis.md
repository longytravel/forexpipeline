# Research Brief RB-3A: Backtesting Engine Architecture & Competitive Analysis

## Research Objective
Understand how the best backtesting systems architect their engines — IPC patterns, parallelism, state management, and checkpoint/resume — to validate and improve our Arrow IPC + state machine design before building Stories 3-3, 3-4, 3-5.

## Why This Matters
Stories 3-1 and 3-2 made foundational architecture decisions (subprocess + Arrow IPC, two-level checkpointing, windowed evaluation) based on internal analysis of ClaudeBackTester. These decisions need external validation against what production systems actually do. Getting this wrong means rebuilding the entire backtesting pipeline.

## Scope

### Primary Questions
1. **Engine architecture patterns:** How do VectorBT, Backtrader, Zipline, QuantConnect, NinjaTrader, and MT5 architect their backtesting engines? Event-driven vs vectorized vs hybrid?
2. **IPC & serialization:** What IPC mechanisms do high-performance quant systems use between orchestration and compute layers? Arrow IPC, shared memory, gRPC, ZeroMQ, pipes?
3. **Python-Rust bridge patterns:** What real-world projects use Python orchestration + Rust compute? How do they handle data transfer, error propagation, and process lifecycle?
4. **Parallelism models:** How do production backtesting systems parallelize? Per-pair? Per-timeframe? Per-parameter-set? Per-window? What are the tradeoffs?
5. **State machine patterns for pipelines:** How do ML/quant pipeline systems (Airflow, Dagster, Prefect, custom) manage stage transitions, gates, and operator approval?
6. **Checkpoint/resume at scale:** How do systems that run millions of evaluations handle crash recovery? What granularity? What's the overhead vs benefit tradeoff?

### Competitive Systems to Study

| System | Why Study It | Key Questions |
|--------|-------------|---------------|
| **VectorBT** | Best-in-class vectorized Python backtester | How does it achieve speed? What are its parallelism limits? How does it handle large datasets? |
| **VectorBT PRO** | Commercial evolution with more features | What did they add? Portfolio-level? Multi-asset? |
| **Backtrader** | Most popular event-driven Python backtester | Architecture patterns, extensibility model, why it's slow |
| **Zipline** | Quantopian's engine, institutional quality | Pipeline API, data bundles, how they handle universes |
| **QuantConnect/Lean** | C# engine, cloud-native, production grade | Multi-asset, live trading, how they bridge research→production |
| **NinjaTrader** | .NET, retail-professional, real-time focus | Strategy development workflow, indicator architecture |
| **MetaTrader 5** | Most widely used retail platform | MQL5 strategy tester architecture, distributed optimization, cloud agents |
| **Nautilus Trader** | Rust+Python, closest to our architecture | Their Python-Rust bridge pattern, Cython vs PyO3, performance claims |
| **RustQuant** | Pure Rust financial library | Pricing/risk patterns, how Rust quant ecosystem is evolving |

### Source Strategy

| Source | What to Extract |
|--------|----------------|
| **GitHub repos** | Architecture patterns, data flow, serialization code, benchmark results |
| **Reddit r/algotrading** | Real user experiences, performance comparisons, pain points, "I switched from X to Y because..." |
| **Reddit r/QuantFinance** | Academic-practitioner bridge, validation methodology debates |
| **Reddit r/rust** | Python-Rust FFI experiences, Arrow IPC usage patterns, PyO3 vs subprocess debates |
| **Academic papers** | "Backtesting methodology" surveys, high-performance simulation architectures |
| **QuantConnect forums** | Production challenges, scaling patterns, what breaks at scale |
| **MT5 MQL5 forums** | Distributed optimization patterns (their cloud agent system is sophisticated) |
| **Blog posts / Medium** | Architecture deep-dives, "how I built my backtester" posts with lessons learned |
| **YouTube** | Conference talks on quant infrastructure, system design presentations |

## Expected Deliverables
1. **Competitive architecture matrix** — side-by-side comparison of engine patterns across all systems
2. **IPC pattern validation** — evidence for/against our Arrow IPC decision with real-world benchmarks
3. **Python-Rust bridge best practices** — concrete patterns from Nautilus, Polars, DataFusion, etc.
4. **State machine pattern catalog** — proven patterns for pipeline orchestration with gates
5. **Checkpoint strategy recommendation** — validated granularity and overhead model
6. **"Steal these ideas" list** — specific features/patterns from competitors worth adopting

## Informs Stories
- **3-3** Pipeline State Machine (state transitions, gates, checkpoint infrastructure)
- **3-4** Python-Rust Bridge (IPC pattern, data serialization, error propagation)
- **3-5** Rust Backtester Crate (trade simulation architecture, parallelism model)

## Research Constraints
- Focus on **what we can learn and apply**, not comprehensive product reviews
- Prioritize open-source systems where we can read architecture code
- Weight real user experience (Reddit, forums) heavily — docs lie, users don't
- Our system is forex-focused single-pair initially; don't over-index on multi-asset patterns we don't need for V1
