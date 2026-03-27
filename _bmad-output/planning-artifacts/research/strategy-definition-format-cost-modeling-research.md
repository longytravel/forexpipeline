# Strategy Definition Format & Cost Modeling Research

**Story:** 2.2 — Strategy Definition Format & Cost Modeling Research
**Date:** 2026-03-15
**Baseline Reference:** ClaudeBackTester, master branch, commit 2084beb
**Architecture Decisions Referenced:** D7, D10, D12, D13, D14
**PRD Requirements Referenced:** FR9-FR13, FR14, FR18, FR20-FR22, FR58, FR61

---

## 1. Executive Summary

This research validates the strategy specification format and establishes the execution cost modeling methodology for the Forex Pipeline. Two independent research domains were investigated:

**Strategy Definition Format:** TOML is confirmed as the specification format (score 8.45/10), validating the D7/D10 hypothesis. All D10 minimum representable constructs — 18 indicators, 7+ exit types, 4 filter types, optimization plans with parameter groups/dependencies/objective functions — are expressible in TOML with concrete examples demonstrated. JSON Schema (7.90) is the strongest alternative but rejected due to no-comments limitation (FR11 gap) and inconsistency with the project's TOML convention. Custom DSL (5.35) and Hybrid approaches are rejected outright.

**Execution Cost Modeling:** Dukascopy M1 bid+ask data (already integrated) is the primary spread data source. The cost model schema should extend D13 to include commission, percentiles (p95/p99), and data provenance fields. The critical finding is that the pipeline's spread-outlier quarantine (10x median threshold) must NOT exclude data from cost model calibration — the cost model needs pre-quarantine raw data to capture true spread distribution including tail events. Mean/std alone is insufficient for V1; adding p95/p99 is trivial and significantly improves fidelity.

**Architecture Impact:** Zero changes to D7, D10, or D14. D13 receives a minor refinement: additional fields (commission, percentiles, provenance) and a requirement to consume pre-quarantine data. All downstream stories (2.3-2.9) proceed as planned.

**Key Risk:** A strategy showing +500 pips/year in ClaudeBackTester (which has zero cost modeling) may be -400 pips/year after costs. The cost model is a correctness requirement, not a nice-to-have.

---

## 2. Story 2.1 Findings Summary

### 2.1 Component Verdict Table Highlights

Story 2.1 reviewed the ClaudeBackTester's strategy evaluator against D10/D14. All 10 components were rated **Adapt** — nothing usable as-is, nothing to wholesale replace.

| Component | Verdict | Key Finding for Story 2.2 |
|---|---|---|
| Indicator computation | Adapt | 18 pure numpy functions; logic correct, must port to Rust (D14) |
| Signal generation | Adapt | "Precompute-once, filter-many" pattern is sound; wrap with spec-driven interface |
| Filter chain | Adapt | Session/day/spread filters exist; must generalize for spec-driven composition |
| Exit rule evaluation | Adapt | Comprehensive: SL (3 modes), TP (3 modes), trailing (3), breakeven, partial close, max bars, stale |
| Position sizing | Adapt | Fixed-lot only; must add risk-based sizing as spec field |
| Optimization pipeline | Adapt | MAP-Elites is mature; must embed param groups in spec (FR13) |
| Checkpoint/persistence | Adapt | JSON checkpoints exist; format must evolve to strategy specification |
| Cost modeling | **None** | No cost model exists — fixed pip PnL only. Build from scratch. |

### 2.2 Indicator Catalogue Summary

18 indicators catalogued with parameter signatures (feeds Story 2.8 indicator registry):

| Category | Indicators |
|---|---|
| Trend | SMA, EMA, EMA crossover |
| Volatility | True Range, ATR (Wilder's smoothing), Bollinger Bands, Donchian Channel, Keltner Channel, Supertrend |
| Momentum | RSI, MACD (line+signal+histogram), ADX (+DI/-DI), Williams %R, CCI |
| Structure | Rolling Max, Rolling Min, Swing Highs, Swing Lows |

All are stateless pure functions: `(OHLCV arrays, parameters) → ndarray`. NaN-fill for warm-up. No class state, no side effects — correct architecture for D14's `indicators.rs`.

### 2.3 Current Strategy Representation

**No declarative format exists.** Strategies are Python classes inheriting from `Strategy` ABC with hardcoded parameter spaces (`ParamDef` objects). The only persisted "strategy representation" is the post-optimization checkpoint JSON containing final parameter values.

### 2.4 Pain Points the New Format Must Solve

1. **High barrier to entry:** Requires Python + numpy + understanding of Strategy ABC, encoding system, PL_ layout
2. **Encoding complexity:** 64-slot PL_ flat array is an implementation detail leaking into strategy code
3. **No version control:** Strategy definitions live in Python files with no declarative snapshot
4. **No diffability:** Code changes are hard to review for trading logic correctness
5. **No operator review path:** FR11 requires reviewing without seeing code — impossible with current format

### 2.5 What the Format MUST Support (from gap analysis)

**From baseline (preserve):**
- All 18 indicator types with parameter signatures
- Entry conditions: indicator/threshold/comparator
- Exit rules: SL (fixed/ATR/Bollinger), TP (fixed/risk-reward/ATR), trailing (pips/ATR/chandelier), breakeven, partial close, max bars, stale exit
- Filters: session (hour range + day bitmask), spread, day-of-week
- Optimization: parameter groups with value ranges/steps, group dependencies, objective function
- Causality contract: CAUSAL vs REQUIRES_TRAIN_FIT classification

**From D10 (build new):**
- Declarative strategy specification format (this story decides)
- Metadata: name, version, pair, timeframe, created_by, config_hash
- Cost model reference (version)
- Volatility filter (not in baseline)
- Multi-pair support in spec format (Growth phase)

---

## 3. Strategy Definition Format Comparison

### 3.1 Option A — TOML/Config-Driven

**Rust parseability:** `toml` crate with serde derive. `#[derive(Deserialize)]` maps directly to TOML tables. Enum variants → TOML string values. `[[array_of_tables]]` → `Vec<T>`. Sub-millisecond parsing for 1-5KB strategy specs. Already proven in project (`common/config.rs` loads TOML). Error messages include line/column. Schema evolution via `#[serde(default)]` for optional fields, `#[serde(deny_unknown_fields)]` for strict mode.

**AI-generation suitability:** TOML well-represented in LLM training data (Cargo.toml, pyproject.toml, Hugo). Structural simplicity — flat key-value model with tables is harder to get wrong than nested brackets. Main risk: `[[section]]` vs `[section]` confusion, mitigated by template in skill prompt. Validation feedback loop: `tomllib` → Pydantic → structured errors → Claude self-correction. Estimated first-attempt error rate: ~5%, near-zero after one correction cycle.

**Expressiveness:** All D10 minimum constructs representable. Concrete examples:

```toml
[metadata]
name = "ema-crossover-london"
version = "v001"
pair = "EURUSD"
timeframe = "H1"
created_by = "claude-opus-4"
config_hash = ""
causality = "causal"

[[entry_rules]]
[entry_rules.condition]
indicator = "ema_crossover"
parameters = { fast_period = 8, slow_period = 21 }
threshold = 0.0
comparator = "crosses_above"

[[entry_rules.filters]]
type = "session"
params = { include = ["london", "london_ny_overlap"] }

[[entry_rules.filters]]
type = "volatility"
params = { indicator = "atr", period = 14, min_value = 0.0010 }

[[entry_rules.confirmation]]
indicator = "rsi"
parameters = { period = 14 }
threshold = 70.0
comparator = "<"

[exit_rules.stop_loss]
type = "atr_multiple"
value = 1.5

[exit_rules.take_profit]
type = "risk_reward"
value = 2.0

[exit_rules.trailing]
type = "chandelier"
params = { atr_period = 14, atr_multiplier = 3.0 }

[exit_rules.breakeven]
enabled = true
trigger_pips = 15
offset_pips = 2

[exit_rules.partial_close]
enabled = true
trigger_pips = 20
close_percent = 50

[exit_rules.max_bars]
enabled = true
value = 200

[exit_rules.stale_exit]
enabled = false
atr_threshold = 0.3

[position_sizing]
method = "fixed_risk"
risk_percent = 1.0
max_lots = 1.0

[[optimization_plan.parameter_groups]]
name = "entry_timing"
parameters = [
  { path = "entry_rules[0].condition.parameters.fast_period", min = 5, max = 20, step = 1 },
  { path = "entry_rules[0].condition.parameters.slow_period", min = 15, max = 50, step = 5 },
]

[[optimization_plan.parameter_groups]]
name = "risk_management"
parameters = [
  { path = "exit_rules.stop_loss.value", min = 1.0, max = 3.0, step = 0.25 },
  { path = "exit_rules.take_profit.value", min = 1.0, max = 4.0, step = 0.5 },
]

[optimization_plan]
group_dependencies = [["entry_timing", "risk_management"]]

[optimization_plan.objective]
metric = "sharpe_ratio"
direction = "maximize"

[cost_model_reference]
version = "v003"
```

**Operator reviewability:** Human-readable by design. Comments supported (FR11). Section headers self-documenting. Clean diffs. Consistent with existing `base.toml`, `schema.toml` patterns.

**Tooling:** Rust `toml` + Python `tomllib` (stdlib 3.11+) are mature. `taplo` provides editor integration and formatting. JSON Schema bridge available via taplo for formal validation.

### 3.2 Option B — JSON Schema-Driven

**Rust parseability:** `serde_json` — the most mature serde crate. Equally fast and reliable as TOML parsing. First-class serde integration.

**AI-generation suitability:** JSON is the most common format in LLM training data. However, bracket-matching errors increase with nesting depth for complex strategy specs. No comments means AI cannot annotate its output for operator review.

**Expressiveness:** Represents all D10 constructs. Slightly more natural for deeply nested arrays. No comments limits self-documenting specs.

**Operator reviewability:** **Critical weakness.** No comments — FR11 requires operator review without seeing code, and comments are essential for explaining what each section does. Nested braces reduce readability. Diff noise from formatting changes. Inconsistent with project's TOML convention.

**Tooling:** Richest ecosystem — JSON Schema provides formal validation, code generation, IDE autocomplete. However, JSON Schema's tooling advantage is available to TOML via the taplo bridge without switching format.

### 3.3 Option C — Custom DSL

**Architecture conflict:** D10 explicitly states "evaluator is rule engine, not general-purpose interpreter." A custom DSL introduces a grammar, parser, and interpreter/compiler — directly conflicting with D10's design philosophy that the specification is data, not code.

**Build cost:** Writing a grammar + parser + error recovery + Python transpiler + editor tooling is 4-8 weeks of development that does not advance the pipeline toward its first backtest.

**AI-generation suitability:** Zero training data for a custom grammar. First-attempt error rate estimated 25-40%. Multiple correction cycles needed. This undermines the Intent → Specification pipeline speed (FR9, FR10).

**Verdict: REJECT.** Conflicts with D10. Unjustified build cost. Unreliable AI generation.

### 3.4 Option D — Hybrid (TOML + Embedded Expressions)

D10's constrained rule-engine model explicitly avoids general-purpose interpreter complexity. Options A and B both represent ALL D10 minimum constructs without expressions. Every value in the specification is a concrete literal, enum selection, or structured parameter block. Computed values like `TP = SL * ratio` are declarative instructions (`type = "risk_reward", value = 2.0`) interpreted by the evaluator, not computed expressions.

**Verdict: REJECT — NOT NEEDED.** No D10 construct requires expression evaluation.

### 3.5 Scored Comparison Matrix

| Criterion | Weight | A: TOML | B: JSON | C: DSL | D: Hybrid |
|---|---|---|---|---|---|
| Rust parseability | 25% | **9** | **9** | 5 | N/A |
| AI-generation suitability | 25% | **8** | 7 | 3 | N/A |
| Expressiveness | 20% | **9** | **9** | 10 | N/A |
| Operator reviewability | 15% | **9** | 5 | 7 | N/A |
| Tooling availability | 15% | 7 | **9** | 2 | N/A |
| **Weighted Total** | **100%** | **8.45** | **7.90** | **5.35** | **Rejected** |

---

## 4. Format Recommendation

### Decision Record

**Chosen:** TOML (Option A) — score 8.45/10

**Rationale:**
1. All D10 minimum constructs representable (demonstrated with concrete examples above)
2. D7 establishes TOML as project configuration language; strategy specs are configuration (what to evaluate), not code
3. Claude generates valid TOML at high rates; template-guided generation + Pydantic feedback → near-zero error after one correction cycle
4. Comments, section headers, clean diffs satisfy FR11 operator reviewability
5. TOML supports versioning and config_hash embedding required by FR12 (constrained, versioned, reproducible specs)
6. Downstream stories (2.3, 2.8) already assume TOML — zero rewrite risk

**Rejected alternatives:**

| Option | Score | Rejection Reason |
|---|---|---|
| JSON Schema | 7.80 | No comments (FR11 gap), inconsistent with project TOML convention, diff noise. JSON Schema's validation advantage available via taplo bridge without switching format. |
| Custom DSL | 4.95 | Conflicts with D10 "rule engine, not interpreter". AI generation unreliable (25-40% error). 4-8 week build cost for no pipeline progress. |
| Hybrid | N/A | Not needed — TOML represents all D10 constructs without expressions. |

**Evidence sources:** D7 TOML precedent (6 production TOML files), D10 specification contract tree, Story 2.1 indicator catalogue (18 indicators), Story 2.1 exit rule inventory (7+ types), Rust `toml` crate ecosystem analysis, LLM training data analysis for format reliability.

**Unresolved assumptions:**
- AI generation error rate estimated at ~5% first-attempt; actual rate measurable in Story 2.4 implementation
- TOML inline table limits may require workaround for very complex optimization plans; mitigated by array-of-tables syntax

**Downstream contract impact:**
- Story 2.3: Creates `contracts/strategy_specification.toml` — confirmed, TOML format
- Story 2.4: Builds dialogue → TOML specification flow — confirmed, direct path
- Story 2.5: Review/diff of TOML specs — confirmed, TOML is diff-friendly
- Story 2.8: Rust parser using `toml` + `serde` — confirmed, already specified in story

**Known limitations:**
- TOML `[[array_of_tables]]` syntax has a learning curve for operators unfamiliar with TOML; mitigated by operator already using `base.toml`
- TOML does not natively support schema validation; validation relies on Pydantic (Python) and serde (Rust)

---

## 5. Constraint Validation Analysis

### Decision Record

**Chosen:** Hybrid three-layer validation

**Layer 1 — Definition-time (Python, immediate feedback):**
- Structural validation via Pydantic model parse
- Type checking, enum validation, range validation
- Indicator registry lookup (parameter signature verification)
- Intra-spec cross-field validation (e.g., optimization params reference indicators in entry_rules)
- **Implementor:** Story 2.3

**Layer 2 — Load-time (Rust, at job start):**
- Re-validation via serde + custom validators (catches Python/Rust parser disagreement)
- Cross-artifact validation (cost_model_reference points to existing artifact)
- Data-dependent validation (indicator periods vs. available history length)
- Full `validate_spec() -> Result<ValidatedSpec, Vec<ValidationError>>` with collect-all-errors
- **Implementor:** Story 2.8

**Layer 3 — Shared contracts (both consume):**
- `contracts/strategy_specification.toml` — single source of truth for spec schema
- `contracts/indicator_registry.toml` — shared indicator catalogue
- Both Python and Rust validators derive from these contracts
- **Implementor:** Story 2.3 (create), Story 2.8 (consume)

**Rationale:** Best operator UX (immediate feedback during AI generation) + full validation at runtime (catches cross-artifact and data-dependent issues). Two independent validators catch different error classes — defense in depth.

**Rejected alternatives:**
- Definition-time only: Cannot catch cross-artifact or data-dependent constraints
- Runtime only: Errors discovered late after pipeline setup; AI correction loop broken (no immediate feedback during generation)

**Evidence sources:** D10 rule-engine constraint (specification is data, not code — validation must operate on data), Pydantic validation patterns (Python ecosystem standard for data validation), Rust serde validation patterns (`#[serde(deny_unknown_fields)]`, custom deserialize), Story 2.1 indicator catalogue (18 indicators requiring parameter signature validation).

**Unresolved assumptions:**
- Python Pydantic and Rust serde validators can be kept in sync via shared contracts without drift — actual drift risk measurable only after Story 2.3 creates contracts and Story 2.8 consumes them
- Collect-all-errors strategy (`Vec<ValidationError>`) is sufficient; may need error prioritization if specs commonly have cascading errors

**Downstream contract impact:**
- Story 2.3: Must create `contracts/strategy_specification.toml` and `contracts/indicator_registry.toml` as the single source of truth consumed by both validators
- Story 2.8: Must implement Rust-side validation that agrees with Python-side (Story 2.3) for all shared constraints — divergence is a bug

**Known limitations:**
- Two-validator maintenance burden — Python and Rust validators must be updated in lockstep when contracts change
- No guarantee of identical Pydantic/serde validation behavior for edge cases (e.g., floating-point precision in parameter bounds)
- Shared contracts reduce but do not eliminate the risk of validator divergence

---

## 6. Execution Cost Modeling Research

### 6.1 Spread Data Sources

| Source | Type | Granularity | Access | V1 Suitability |
|---|---|---|---|---|
| **Dukascopy** (primary) | ECN institutional | M1 bid+ask, tick-level | `dukascopy-python` v4.0.1, free | **Best** — already integrated, 2003+ history |
| OANDA | Retail market maker | S5-Monthly, bid+ask candles | REST API, OAuth2 token | Good validation source for retail-realistic spreads |
| FXCM | Retail/ECN hybrid | Tick (via ForexConnect), M1+ | REST API + ForexConnect SDK | Questionable API stability; useful for cross-validation |
| IC Markets | ECN retail | No programmatic access | Manual PDF/webpage only | Not usable for automated calibration |

**V1 recommendation (satisfies FR20, FR21, FR22):** Use Dukascopy M1 bid+ask as the primary calibration source. Derive spreads from `ask_close - bid_close` per M1 bar, convert to pips via `spread * pip_multiplier`. OANDA as optional validation cross-reference. Document that Dukascopy ECN spreads may be tighter than typical retail — include `data_source` field in artifact for provenance.

**Data provenance requirements per source:**
- Broker name and account type (ECN vs market maker)
- Date range of sample window
- Bar count / tick count per session
- Timezone/session mapping methodology used
- Known biases (e.g., "Dukascopy ECN spreads may be 20-30% tighter than retail broker spreads")

### 6.2 Session-Aware Cost Profile Construction

**Session definitions** (from D13 / `config/base.toml`):

| Session | UTC Range | Priority | Spread Expectation (EURUSD) |
|---|---|---|---|
| London-NY Overlap | 13:00-16:00 | 1 (highest) | Tightest (~0.3-0.8 pips) |
| London | 08:00-13:00 | 2 | Tight (~0.5-1.0 pips) |
| New York | 16:00-21:00 | 3 | Moderate (~0.6-1.2 pips) |
| Asian | 00:00-08:00 | 4 | Wider (~0.8-1.5 pips) |
| Off-Hours | 21:00-00:00 | 5 (lowest) | Widest (~1.0-3.0+ pips) |

**Note:** Sessions overlap (London 08-16, New York 13-21). Assignment uses priority: `london_ny_overlap` > `london` > `new_york` > `asian` > `off_hours` — consistent with quality checker's existing session logic.

**Methodology — M1 spread aggregation by session:**
1. Fetch bid and ask M1 DataFrames from Dukascopy for target pair and date range
2. Merge on timestamp → `spread_raw = ask_close - bid_close`
3. Convert: `spread_pips = spread_raw * pip_multiplier` (10000 for EURUSD)
4. Assign session label per bar using UTC hour and priority rules
5. Group by session, compute: mean, std, median, p95, p99, sample_count
6. Use 1-3 years of data; weight recent data more heavily (spreads tightening over time)

**Market microstructure drivers:**

The well-documented intraday FX spread pattern (Hussain 2011) follows from:
- **Information asymmetry:** Market makers widen spreads around economic releases and market opens
- **Inventory risk:** Low-volume periods → wider spreads (dealers can't offload inventory)
- **Competition:** Multiple active liquidity providers during overlap → compressed spreads
- **Event-driven spikes:** NFP, FOMC, ECB decisions cause 3-10x normal spread widening (seconds to minutes); unscheduled events (flash crashes) can cause 10-100x widening

### 6.3 Slippage Estimation

**Components:**

| Component | Typical EURUSD Magnitude | Source |
|---|---|---|
| Latency slippage | 0.01-0.1 pips | Price movement during 50-200ms retail order transmission |
| Market impact | 0.0-0.5 pips | Order consuming visible liquidity (size-dependent) |
| Last-look rejection | 0.0-0.3 pips | LP re-quotes at worse price (broker-dependent) |
| Requote delay | 0.0-0.2 pips | Price changed during processing |
| **Total typical** | **0.03-0.3 pips** | Asymmetric — almost always adverse |

**V1 methodology (volatility-adjusted estimation):**
1. Compute per-session realized volatility from M1 returns: `session_vol = std(returns)`
2. Model slippage as proportional: `mean_slippage = k * session_vol` where k is a calibration constant
3. Initial k derived from literature (typical retail latency ~100ms, volatility relationship)
4. Session-dependent: higher volatility sessions → higher slippage
5. Calibrate k from live fill data when available (FR22)

**Academic references:**
- Ito et al. (2020, NBER w26706): Execution risk framework — "price seen vs price filled" gap. Professional arbitrageur success rate declined to <50% post-algorithmic era.
- BIS Markets Committee Paper No. 13 (2020): FX "execution trilemma" — speed, cost, certainty tradeoff. Retail traders accept slippage for speed+certainty.
- Hussain (2011): Intraday bid-ask spread behavior — U-shaped pattern driven by information asymmetry and inventory costs.

### 6.4 CRITICAL: Quarantine Interaction with Cost Model

**The most critical finding of this research.**

The pipeline's quality checker (`quality_checker.py:_check_spread_outliers()`) quarantines M1 bars where `spread > 10x session median`. In 2025 EURUSD data, 7,391 ticks (0.03%) were quarantined. The timeframe converter then EXCLUDES quarantined bars before aggregation.

**The problem:** If the cost model is calibrated on post-quarantine data, it never sees wide-spread events — exactly the conditions that matter most for realistic cost modeling (news releases, low liquidity, market opens).

| Scenario | Cost Model Sees | Consequence |
|---|---|---|
| Post-quarantine data | Only "normal" spreads | std artificially narrow; tail events invisible; backtester underestimates costs |
| Pre-quarantine raw data | Full distribution | std and percentiles reflect reality; backtester sees true costs |
| Flag-only (no exclusion) | Full data with flags | Maximum flexibility; cost model chooses what to include |

**Recommendation:** The cost model calibrator MUST consume pre-quarantine raw data (validated but not quarantine-excluded). The quarantine protects OHLC/indicator computation from corrupt bars — that's correct for indicators. But the cost model needs the full spread distribution including tails, because those are the real execution costs the strategy will face in live trading.

**Downstream implication:** If the backtester uses a cost model trained on sanitized data, it will underestimate real execution costs and produce unrealistically good backtest results that fail in live trading. This directly undermines the pipeline's trust-first philosophy.

---

## 7. Cost Model Artifact Assessment

### 7.1 D13 Alignment

D13 specifies a JSON artifact with `{pair, version, source, calibrated_at, sessions: {session: {mean_spread_pips, std_spread, mean_slippage_pips, std_slippage}}}`. The format is fundamentally sound but needs refinement.

### 7.2 Proposed D13 Refinements

**Additional top-level fields (V1 required):**

| Field | Rationale |
|---|---|
| `schema_version` | Enables artifact format evolution |
| `commission_per_lot_usd` | ECN brokers charge commission separate from spread (IC Markets: $3.50/side/lot). Omitting this understates costs. |
| `commission_currency` | Commission denomination (usually USD) |
| `pip_value` | Pip value for the pair (0.0001 for EURUSD) — eliminates ambiguity |
| `data_source` | Which broker's data was used (e.g., "dukascopy_ecn") — provenance |
| `data_range` | Date range of calibration sample |
| `calibration_method` | "research_only" / "live_validated" / "live_calibrated" |

**Additional per-session fields (V1 recommended):**

| Field | Rationale |
|---|---|
| `median_spread_pips` | More robust than mean for skewed distributions |
| `p95_spread_pips` | Tail awareness — see Section 7.3 |
| `p99_spread_pips` | Extreme tail awareness |
| `sample_count` | Confidence indicator — sessions with low sample counts are less reliable |

**Deferred fields:**

| Field | Reason for Deferral |
|---|---|
| `swap_long` / `swap_short` | V1 strategies likely intraday; add for multi-day strategies |
| `execution_delay_ms` | Captured by slippage model; no separate field needed |
| `market_impact_model` | Irrelevant at retail order sizes |
| `time_of_day_curve` | Continuous spread curve — significant complexity for marginal V1 benefit |

### 7.3 Decision: Mean/Std vs. Quantiles

**Chosen:** Mean/std AND key percentiles (p95, p99)

**Rejected alternative — mean/std only:** Simpler, deterministic lookup, sufficient for average-case backtesting, consistent with D13 as specified. Rejected because FX spreads are non-Gaussian with heavy right tails; mean/std alone masks tail risk that drives real execution costs.

**Arguments for adding percentiles:** FX spreads have heavy right tails (NOT Gaussian). During news events, spreads spike 5-50x normal. A strategy profitable with mean costs may be unprofitable when 5% of trades incur 3-5x normal spread. p95/p99 are trivial to compute (one-time during calibration) and cost nothing in storage or runtime.

**Decision rationale:** Adding `median_spread_pips`, `p95_spread_pips`, `p99_spread_pips` to each session profile provides:
1. Robust central tendency (median, not just mean)
2. Tail awareness for risk-conscious backtesting
3. Optimizer can optionally penalize strategies that trade during high-spread sessions
4. Zero additional runtime cost — fields computed once during calibration, stored in JSON
5. Backtester inner-loop still uses `mean_spread_pips` for deterministic mode (FR18); Monte Carlo mode can sample from the distribution

**Evidence sources:** Section 6.3 academic references (Ito et al. 2020, BIS 2020, Hussain 2011) on FX spread distribution characteristics; Section 6.4 quarantine interaction finding (7,391 ticks with >10x median spread in 2025 EURUSD data); D13 original schema specification; FR18 determinism requirement; FR21 session-aware requirement.

**Unresolved assumptions:**
- p95/p99 percentiles derived from Dukascopy ECN data may not transfer to retail broker execution — retail spreads are typically 20-30% wider; percentile ratios may differ
- Whether p95/p99 should be used for deterministic backtesting (FR18) or only for Monte Carlo mode is deferred to Story 2.7 implementation

**Downstream contract impact:**
- Story 2.6: Must compute and populate `median_spread_pips`, `p95_spread_pips`, `p99_spread_pips`, and `sample_count` fields per session during calibration
- Story 2.7: Must expose percentile fields via `query()` API; backtester decides whether to use mean or percentile-based cost lookup

**Known limitations:** Percentile fields do not replace a full distribution model. For V1, the combination of mean + std + p95 + p99 provides sufficient fidelity. Full distribution modeling (histogram bins) deferred to Growth phase if V1 analysis reveals inadequacy.

### 7.4 Recommended V1 Schema

```json
{
  "pair": "EURUSD",
  "version": "v003",
  "schema_version": 1,
  "source": "research",
  "data_source": "dukascopy_ecn",
  "data_range": "2023-01-01/2025-12-31",
  "calibrated_at": "2026-03-15T00:00:00Z",
  "calibration_method": "research_only",
  "pip_value": 0.0001,
  "commission_per_lot_usd": 3.50,
  "commission_currency": "USD",
  "sessions": {
    "asian": {
      "mean_spread_pips": 1.2,
      "std_spread": 0.3,
      "median_spread_pips": 1.0,
      "p95_spread_pips": 2.1,
      "p99_spread_pips": 3.8,
      "mean_slippage_pips": 0.1,
      "std_slippage": 0.05,
      "sample_count": 175200
    },
    "london": {
      "mean_spread_pips": 0.8,
      "std_spread": 0.2,
      "median_spread_pips": 0.7,
      "p95_spread_pips": 1.4,
      "p99_spread_pips": 2.5,
      "mean_slippage_pips": 0.05,
      "std_slippage": 0.03,
      "sample_count": 109500
    },
    "new_york": {
      "mean_spread_pips": 0.9,
      "std_spread": 0.25,
      "median_spread_pips": 0.8,
      "p95_spread_pips": 1.6,
      "p99_spread_pips": 2.8,
      "mean_slippage_pips": 0.07,
      "std_slippage": 0.04,
      "sample_count": 109500
    },
    "london_ny_overlap": {
      "mean_spread_pips": 0.6,
      "std_spread": 0.15,
      "median_spread_pips": 0.5,
      "p95_spread_pips": 1.0,
      "p99_spread_pips": 1.8,
      "mean_slippage_pips": 0.03,
      "std_slippage": 0.02,
      "sample_count": 65700
    },
    "off_hours": {
      "mean_spread_pips": 2.0,
      "std_spread": 0.8,
      "median_spread_pips": 1.5,
      "p95_spread_pips": 4.0,
      "p99_spread_pips": 8.0,
      "mean_slippage_pips": 0.2,
      "std_slippage": 0.1,
      "sample_count": 65700
    }
  }
}
```

**Note:** Spread values above are illustrative based on typical Dukascopy ECN EURUSD spreads and market microstructure literature. Actual values will be computed from real data in Story 2.6.

### 7.5 Calibration Hooks (FR22)

**V1 interface (implemented in Story 2.7):**
- `load(path) -> CostModel` — Load JSON artifact, validate schema
- `query(session) -> CostProfile` — O(1) lookup, returns all fields for the session

**Deferred interface stubs (reconciliation epic):**
- `ingest_fills(fills: &[FillRecord]) -> CalibrationResult`
- `check_drift(fills: &[FillRecord]) -> DriftReport`
- `export(path) -> Result<()>`

**Live fill record schema (for future FR22):**
```json
{
  "fill_id": "uuid",
  "timestamp_signal": "ISO8601",
  "timestamp_filled": "ISO8601",
  "pair": "EURUSD",
  "direction": "buy|sell",
  "requested_price": 1.09450,
  "filled_price": 1.09453,
  "session": "london",
  "spread_at_signal_pips": 0.4,
  "slippage_pips": 0.1,
  "commission_usd": 0.35,
  "execution_latency_ms": 67
}
```

**Calibration versioning:** Each artifact tracks `calibration_method` (research_only → live_validated → live_calibrated), `previous_version`, and `data_range`. Drift detection compares observed live fills against model predictions per session.

### 7.6 Baseline Cost Model Comparison

ClaudeBackTester has **zero cost modeling**. The Rust trade simulation uses fixed pip-based PnL: `pnl = (exit - entry) * direction * lots`. No spread, no slippage, no commission.

**Quantified impact:** For a strategy with 500 trades/year, average cost per trade ~1.80 pips (1.0 spread + 0.1 slippage + 0.70 commission equivalent — $3.50/side × 2 sides = $7.00/lot = 0.70 pips at $10/pip):
- Annual omission: ~900 pips
- At 1 standard lot ($10/pip): $9,000/year in unmodeled costs
- A +500 pip/year strategy may be -400 pip/year after costs

This is not an edge case — it's the default for every ClaudeBackTester result. The cost model is a correctness requirement.

---

## 8. Proposed Architecture Updates

All proposed refinements stay in this research artifact per Story 2-1 pattern. Architecture.md is NOT modified.

### D10 — No Change Required

TOML represents all D10 minimum constructs. The three-layer model (Intent → Specification → Evaluation) is preserved. The rule-engine constraint is satisfied — TOML is data, not code.

**Optional D10 enhancement (for operator review):** D10's specification contract tree could be updated to include the `causality` field and the additional exit types discovered in Story 2.1 (breakeven, partial_close, max_bars, stale_exit). These are additive extensions, not changes.

### D13 — Minor Refinement Proposed

The D13 schema should be extended with:
1. **Top-level fields:** `schema_version`, `commission_per_lot_usd`, `commission_currency`, `pip_value`, `data_source`, `data_range`, `calibration_method`
2. **Per-session fields:** `median_spread_pips`, `p95_spread_pips`, `p99_spread_pips`, `sample_count`
3. **Data source requirement:** Cost model calibrator MUST consume pre-quarantine raw data, not post-quarantine sanitized data

These are additive refinements — the existing D13 fields are preserved. No breaking changes to the architecture.

### D14 — No Change Required

The `strategy_engine` crate design is unaffected. TOML parsing via `toml` + `serde` is already the planned approach.

---

## 9. Build Plan Confirmation (Stories 2.3-2.9)

| Story | Scope | Port vs Build | Key Dependency from This Research |
|---|---|---|---|
| **2.3** Schema & Contracts | Create `contracts/strategy_specification.toml`, `contracts/indicator_registry.toml`, Pydantic validator | **Build new** | TOML format confirmed; indicator catalogue from 2.1 |
| **2.4** Intent Capture | Claude Code skill: dialogue → TOML spec generation | **Build new** | TOML format confirmed; AI generation suitability validated |
| **2.5** Review & Versioning | Operator review, diff, confirmation, version locking | **Build new** | TOML diffability confirmed; comment support satisfies FR11 |
| **2.6** Cost Model Artifact | Python calibrator: Dukascopy data → session-aware JSON artifact | **Build new** | Methodology defined; pre-quarantine data requirement; V1 schema specified |
| **2.7** Cost Model Rust Crate | `crates/cost_model/` with `load()` + `query()` | **Build new** | JSON schema specified; interface stubs defined; FR22 hooks stubbed |
| **2.8** Strategy Engine Crate | `crates/strategy_engine/` with TOML parser + indicator registry | **Port + Build** | TOML parser (build); indicator logic (port from 18 Python functions) |
| **2.9** E2E Proof | End-to-end: dialogue → spec → cost model → backtester stub | **Build new** | All format and cost model choices validated in this research |

**Key finding:** Story 2.8 is the only story with significant porting work (18 indicators from Python to Rust). All others are build-new. This is consistent with Story 2.1's finding that the baseline has no declarative format or cost model.

---

## 10. Downstream Rewrite Risk

**Risk: Zero.** The TOML recommendation is fully aligned with existing architecture assumptions:
- D7 already specifies TOML for configuration
- D10 already mentions JSON/TOML as specification format options
- Story 2.3 already specifies `contracts/strategy_specification.toml`
- Story 2.8 already specifies `serde` + `toml` crate dependencies

No downstream stories require rewriting. No architecture decisions require modification (D13 receives additive refinements only).

If this research had recommended a non-TOML format, the following stories would have required scope changes: 2.3 (contract format), 2.4 (generation target), 2.5 (diff tooling), 2.8 (parser crate dependencies). That rewrite is not needed.
