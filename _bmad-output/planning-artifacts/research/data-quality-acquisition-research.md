# Data Quality & Acquisition Research

**Date:** 2026-03-14
**Researcher:** Claude Opus 4.6 (1M context)
**Depends on:** Story 1.1 — ClaudeBackTester Data Pipeline Review
**Architecture Reference:** `_bmad-output/planning-artifacts/architecture.md`

---

## 1. Executive Summary

This research validates the Architecture's data quality specifications against industry practices and Dukascopy-specific behavior. The Architecture's quality scoring formula, gap thresholds, and quarantine approach are well-designed for M1 forex data. Three minor adjustments are recommended: (1) add extreme range and OHLC violation checks to the quality gate, (2) consider the `dukascopy-python` library as the primary download mechanism instead of raw bi5, and (3) add session-specific gap thresholds for Asian session tolerance.

The Dukascopy download mechanism is well-understood: the `dukascopy-python` library (v4.0.1, MIT license, Python 3.10+) provides a clean REST API for M1 bar data with both bid and ask sides. For tick data, either `dukascopy-python` (supports `INTERVAL_TICK`) or the `TickVault` library (raw bi5 with gap detection) are viable options. The recommended approach is to use `dukascopy-python` for M1 bars (proven in ClaudeBackTester) and evaluate `TickVault` only if raw tick data becomes a requirement for scalping strategies.

---

## 2. Data Quality Scoring Methodologies

### 2.1 Industry Approaches

**Quant shop approaches to M1 forex data quality:**

Data quality for financial time series is assessed at multiple levels:

1. **Tick-level cleaning** (Brownlees & Gallo, 2006): Rolling confidence intervals within each trading day assess tick error probability. Calibrated assuming < 2% of ticks are erroneous. This is the academic gold standard for high-frequency data.

2. **Bar-level validation**: For M1 data, standard checks include:
   - Zero/negative price detection (immediate rejection)
   - OHLC consistency (high >= low, high >= open, high >= close, low <= open, low <= close)
   - Gap detection with session/weekend awareness
   - Volume anomaly detection
   - Spread reasonableness checks

3. **Statistical outlier detection**: Rolling median +/- N standard deviations. Commonly 3σ for conservative, 5σ for aggressive filtering. Applied to price changes, spreads, and volumes.

4. **Completeness scoring**: Expected bars vs actual bars per hour/day. Forex M1 should have ~1,440 bars per trading day (24 hours × 60 minutes), minus weekend closure.

### 2.2 Architecture's Scoring Formula Assessment

The Architecture specifies:

```
quality_score = 1.0 - (gap_penalty + integrity_penalty + staleness_penalty)

gap_penalty     = min(1.0, total_gap_minutes / total_expected_minutes × 10)
integrity_penalty = min(1.0, bad_price_bars / total_bars × 100)
staleness_penalty = min(1.0, stale_bars / total_bars × 50)
```

**Assessment: REASONABLE with caveats.**

- **Gap penalty multiplier (×10):** This means that if gaps represent 10% of expected trading time, the penalty maxes out at 1.0 (instant RED). For a year of M1 data (~373,000 expected trading minutes), 10% = 37,300 gap minutes = ~26 full trading days of gaps. This is appropriately aggressive — 26 days of missing data in a year should indeed block the pipeline.

- **Integrity penalty multiplier (×100):** If 1% of bars have integrity issues, the penalty maxes out. For 525K bars, that's 5,250 bad bars. This is very conservative — even 0.1% bad bars (525) would produce a penalty of 0.1, which combined with other penalties could push to YELLOW. This is appropriate — price integrity errors are serious.

- **Staleness penalty multiplier (×50):** If 2% of bars are stale, penalty maxes out. This is aggressive but appropriate — widespread stale quotes indicate a systemic data feed issue.

- **Score thresholds (GREEN >= 0.95, YELLOW 0.80-0.95, RED < 0.80):**
  - GREEN (>= 0.95) means total penalties < 0.05 — very clean data. Reasonable for production use.
  - YELLOW (0.80-0.95) means penalties between 0.05 and 0.20 — some issues but potentially usable with review. Appropriate.
  - RED (< 0.80) means penalties > 0.20 — serious quality issues. Correct to block pipeline.

**Recommendation: Confirm the formula as-is.** The penalty weights are well-calibrated for M1 forex data. The only suggestion is to ensure the formula is applied AFTER excluding weekend/holiday gaps (which the Architecture already specifies).

### 2.3 Baseline's Scoring Model Comparison

The ClaudeBackTester uses a 0-100 point deduction system:
- Unexpected gaps: -0.5 each, max -20
- NaN values: -5 each, max -20
- Zero values: -5 each, max -20
- OHLC violations: -10 each, max -20
- Extreme range: -0.1 each, max -5
- Coverage penalty: up to -15

**Verdict: Replace with Architecture formula.** The baseline model is ad hoc and doesn't penalize proportionally to data volume. A single NaN in 5 million bars loses 5 points — the same penalty as 1 NaN in 5,000 bars. The Architecture's proportional formula is mathematically sounder.

---

## 3. Quarantine Patterns

### 3.1 Industry Approaches

Three main approaches exist for handling bad data in backtesting:

| Approach | Description | Pros | Cons |
|---|---|---|---|
| **Mark-and-skip** | Flag bad bars, backtester ignores them | Simple, preserves data structure, reversible | Indicators crossing quarantine boundaries may produce artifacts |
| **Exclude-and-compact** | Remove bad bars entirely, renumber | Clean data for backtester | Loses temporal information, introduces artificial adjacency |
| **Interpolation** | Fill missing/bad data with estimated values | No gaps in time series | Introduces synthetic data, can mask real issues, explicitly forbidden by Architecture |

### 3.2 Architecture's Chosen Approach Assessment

The Architecture specifies: "Quarantined periods are marked in the Arrow IPC with a `quarantined: bool` column. Backtester skips quarantined bars."

**Assessment: CORRECT.** Mark-and-skip is the right approach for these reasons:

1. **Preserves temporal structure** — timestamps remain accurate, session boundaries stay correct
2. **Reversible** — changing quarantine criteria doesn't require re-downloading data
3. **Transparent** — quality report shows exactly what was quarantined and why
4. **No synthetic data** — avoids the interpolation trap

### 3.3 Quarantine Boundary Effects

**Key edge case:** If bars 100-110 are quarantined, how should a 20-period moving average at bar 111 handle the gap?

**Recommended approach:**
- Indicators that require lookback (MA, RSI, ATR, etc.) should be computed on non-quarantined bars only
- At quarantine boundaries, the indicator "warms up" from the last non-quarantined bar
- For a 20-period MA at bar 111, use the 20 most recent non-quarantined bars before bar 111 (which may span bars 80-99)
- This is the backtester's responsibility (not the data pipeline's), but the data pipeline should document quarantine boundaries clearly in the quality report

**Implementation note:** The `quarantined: bool` column is sufficient. The backtester should filter `quarantined == False` before computing indicators. This naturally handles boundary effects because indicators only see clean data.

### 3.4 What Gets Quarantined

Based on the Architecture's quality checks, bars should be quarantined when:

| Condition | Quarantine Scope | Rationale |
|---|---|---|
| Gap > 5 consecutive M1 bars | Bars immediately adjacent to gap boundaries (1 bar before, 1 bar after) | Adjacent bars may have unreliable prices due to reconnection effects |
| bid <= 0 or ask <= bid | The specific bar | Clearly invalid price data |
| spread > 10× session median | The specific bar | Likely a data feed error or extreme illiquidity event |
| bid=ask or spread=0 for > 5 bars | The entire stale run | Not tradeable data — any signals here would be unreliable |
| OHLC violation (high < low) | The specific bar | Corrupt data |

---

## 4. Gap Handling Approaches

### 4.1 Types of Gaps in Dukascopy M1 Data

Based on research and the ClaudeBackTester review:

| Gap Type | Expected? | Duration | Handling |
|---|---|---|---|
| **Weekend closure** | Yes | Friday ~22:00 UTC to Sunday ~22:00 UTC (~48h) | Exclude from gap detection entirely |
| **Holiday closure** | Yes | Varies (Christmas: Dec 24-26, New Year: Dec 31-Jan 2) | Exclude from gap detection, document in quality report |
| **Server maintenance** | Occasional | Minutes to 1-2 hours | Flag as unexpected gap, quarantine boundaries |
| **Data feed interruption** | Rare | Minutes | Flag, quarantine boundaries |
| **Low-liquidity periods** | Common | 1-5 missing M1 bars, typically Asian session or holidays | Below gap threshold, not flagged |
| **Dukascopy data revision** | Known issue | N/A — bars may be added retroactively | Can change OHLC values; handle via versioned artifacts |

### 4.2 Gap Threshold Assessment

**Architecture specifies:** > 5 consecutive M1 bars (5 minutes)

**Assessment: APPROPRIATE.** Rationale:
- 1-3 missing M1 bars are common during low-liquidity periods (Asian session, pre-holiday) and do not indicate data quality issues
- 5 minutes is long enough to represent a genuine feed interruption, short enough to catch meaningful gaps
- The baseline uses 3× expected interval (3 minutes for M1), which is more aggressive and produces more false positives
- Industry practice varies: 5-15 minutes is a common threshold for M1 data

**Recommendation: Keep the 5-bar threshold.** Consider a session-aware adjustment:
- Active sessions (London, NY, overlap): 5 consecutive M1 bars
- Low-activity sessions (Asian, off-hours): 10 consecutive M1 bars (to reduce false positives during naturally thinner markets)

This session-aware threshold is OPTIONAL — the Architecture's flat 5-bar threshold is defensible. Only implement session-aware thresholds if Story 1.5 produces excessive false positives during Asian session validation.

### 4.3 Gap Severity Levels

**Architecture specifies:**
- WARNING: < 10 gaps/year
- ERROR: > 50 gaps/year or any gap > 30 min

**Assessment: APPROPRIATE.** For a year of M1 data:
- 10 gaps/year = less than 1 per month. Very clean data. Reasonable for WARNING.
- 50 gaps/year = ~1 per week. Indicates systematic data feed issues. Reasonable for ERROR.
- Any gap > 30 min = a significant interruption. A 30-minute gap in forex means the feed was down for an extended period, not just a low-liquidity blip.

### 4.4 Architecture's "No Interpolation" Rule

**Architecture states:** "Interpolation NOT allowed."

**Research finding:** The professional consensus for backtesting data is that interpolation introduces synthetic data that can mask real market conditions. Forward-fill (using the last known price) is sometimes used in live trading systems as a safety measure, but for backtesting it creates unreliable results. The Architecture's position is correct and aligned with professional practice.

---

## 5. Dukascopy API & Data Format

### 5.1 Download Mechanism

**Two approaches exist:**

| Approach | Library | Endpoint | Data Format | Best For |
|---|---|---|---|---|
| **REST API** | `dukascopy-python` (v4.0.1) | `freeserv.dukascopy.com/2.0/index.php` | JSON/JSONP → pandas DataFrame | M1 bar data, simplest integration |
| **Raw bi5** | `TickVault`, `duka`, custom | `datafeed.dukascopy.com/datafeed/{PAIR}/{year}/{month}/{day}/{hour}h_ticks.bi5` | LZMA-compressed binary, 20-byte records | Tick data, maximum control |

### 5.2 `dukascopy-python` Library Details

- **Version:** 4.0.1 (released April 2025)
- **License:** MIT
- **Python:** >= 3.10
- **Intervals:** Supports `INTERVAL_TICK`, `INTERVAL_MIN_1`, `INTERVAL_MIN_5`, `INTERVAL_HOUR_1`, and more
- **Offer sides:** `OFFER_SIDE_BID`, `OFFER_SIDE_ASK`
- **Functions:** `fetch()` for historical batch, `live_fetch()` for streaming
- **Data source:** Dukascopy's free charting API (not a direct data feed)
- **Proven:** Successfully used in ClaudeBackTester for 25 pairs × 20 years

**Key limitation:** For non-tick intervals, `fetch()` returns slightly delayed data (the API caches). For backtesting with historical data, this is irrelevant. For live trading, `live_fetch()` is needed.

**Tick data support:** The library supports `INTERVAL_TICK` directly. When using tick intervals, the raw data includes: timestamp (ms), bidPrice, askPrice, bidVolume, askVolume. This is sufficient for the Architecture's tick_data schema.

### 5.3 `TickVault` Library (Alternative for Tick Data)

- **Features:** Raw bi5 download, LZMA decompression, NumPy-based decoding, SQLite metadata tracking, automatic gap detection, proxy rotation, resume-capable
- **Data format:** Stores original compressed .bi5 files, decodes on-demand
- **Assessment:** More complex but provides raw tick data with gap detection built in. Consider ONLY if `dukascopy-python`'s tick support proves insufficient.

### 5.4 Dukascopy Data Quirks

Known issues identified through research and community reports:

1. **Historical data revisions:** Dukascopy occasionally adds ticks to historical data, which can change OHLC values for M1 bars. This means data downloaded at different times may not be identical. **Mitigation:** Versioned artifacts (FR8) — each download creates a new version.

2. **Session opening spreads:** After holidays/weekends, Dukascopy data shows wider spreads than other aggregators for the first ~60 minutes. **Mitigation:** Session-aware spread outlier detection should use per-session medians, not global medians.

3. **Gaps and spikes:** Occasional data gaps and price spikes exist, especially for less liquid pairs and during news events. **Mitigation:** Quality scoring and quarantine system handles this.

4. **Zero-volume bars:** Some M1 bars may have zero volume during very low-liquidity periods. This is expected behavior, not an error. **Mitigation:** Do not flag zero-volume bars as errors. The Architecture's `volume` column is not in the quality checks, which is correct.

5. **Timezone:** All Dukascopy data is in UTC. No DST issues in the raw data. **Mitigation:** Verify UTC on ingest as a sanity check.

### 5.5 Recommended Download Approach for Story 1.4

**Primary: `dukascopy-python` library**
- Use for M1 bar data (proven, simple, reliable)
- Download bid and ask sides separately (as ClaudeBackTester does)
- Store bid close as `bid` column, ask close as `ask` column (per Architecture schema)
- Yearly chunk strategy for resume support (from ClaudeBackTester pattern)

**Optional: Tick data support**
- `dukascopy-python` supports `INTERVAL_TICK` — try this first
- If insufficient, evaluate `TickVault` for raw bi5 tick data
- Tick data is optional (for scalping strategies) — M1 bars are the default

**Rate limiting:** 1-second delay between requests (from ClaudeBackTester pattern). Configurable via `config/base.toml`.

---

## 6. Architecture Comparison Table

| Topic | Architecture Specification | Research Finding | Verdict | Recommendation |
|---|---|---|---|---|
| Quality scoring formula | `1.0 - (gap_penalty + integrity_penalty + staleness_penalty)` | Proportional penalty approach is aligned with professional practice. Better than fixed-point deduction systems. | **Confirm** | Keep as-is |
| Gap penalty weight (×10) | Maxes at 10% gap time | Aggressive but appropriate — 10% missing data is serious | **Confirm** | Keep as-is |
| Integrity penalty weight (×100) | Maxes at 1% bad bars | Conservative, appropriate for price data | **Confirm** | Keep as-is |
| Staleness penalty weight (×50) | Maxes at 2% stale bars | Appropriate for forex M1 | **Confirm** | Keep as-is |
| Score thresholds (GREEN/YELLOW/RED) | >= 0.95 / 0.80-0.95 / < 0.80 | Well-calibrated for production use | **Confirm** | Keep as-is |
| Gap detection threshold | > 5 consecutive M1 bars | Appropriate; 3-bar threshold (baseline) produces false positives | **Confirm** | Keep. Consider optional session-aware adjustment (10 bars for Asian session) |
| Gap severity (WARNING/ERROR) | < 10/year WARNING, > 50/year or > 30min ERROR | Reasonable boundaries | **Confirm** | Keep as-is |
| Price integrity (bid > 0, ask > bid) | Specific checks listed | Standard practice, well-defined | **Confirm** | Keep as-is |
| Spread outlier (10× session median) | Per-session detection | Session-aware is better than global median. 10× is reasonable. | **Confirm** | Keep. Session awareness is critical. |
| Stale quote (bid=ask, spread=0, > 5 bars) | Consecutive bar threshold | Reasonable. Zero-spread indicates frozen feed. | **Confirm** | Keep as-is |
| Quarantine (bool column, backtester skips) | Mark-and-skip approach | Correct approach per industry practice. Preserves data, reversible. | **Confirm** | Keep as-is |
| No interpolation | Explicit prohibition | Correct. Professional consensus for backtesting. | **Confirm** | Keep as-is |
| Consistent sourcing (hash ID) | `{pair}_{start}_{end}_{source}_{hash}` | Essential for reproducibility. Not present in baseline. | **Confirm** | Keep. Build new in Story 1.8. |
| Download mechanism | Story 1.4 describes raw bi5 binary decoder | Baseline uses `dukascopy-python` library (simpler, proven) | **Improve** | Use `dukascopy-python` as primary. Raw bi5 only if tick data needs it. |
| OHLC violation checks | Not explicitly in quality gate table | Baseline detects high < low. Standard check. | **Improve** | Add to quality gate: OHLC violations (high < low, high < open, etc.) |
| Extreme range detection | Not explicitly in quality gate table | Baseline uses adaptive thresholds (50×/20×/10× median by TF) | **Improve** | Add to quality gate as WARNING level check |

---

## 7. Proposed Architecture Updates

### 7.1 Add OHLC Violation and Extreme Range Checks to Quality Gate

**Section:** Data Quality Gate Specifications → Quality Checks table

**Proposed additions:**

| Check | Method | Severity | Action |
|---|---|---|---|
| **OHLC violation** | high < low, high < max(open, close), low > min(open, close) | ERROR | Quarantine bar |
| **Extreme range** | (high - low) > 50× rolling median range for M1 | WARNING | Log, include in quality report. Do NOT quarantine (may be real volatility events like flash crashes or news spikes) |

**Rationale:** These checks exist in the ClaudeBackTester baseline and are standard practice. OHLC violations are always data corruption. Extreme range is informational — real volatility events (e.g., SNB CHF floor removal, flash crashes) produce genuine extreme ranges that should not be quarantined.

### 7.2 Update Story 1.4 Download Approach

**Section:** Story 1.4 Dev Notes → Technical Requirements

**Current:** Describes building a raw bi5 binary decoder with URL pattern `https://datafeed.dukascopy.com/datafeed/...`

**Proposed:** Update to recommend `dukascopy-python` library as the primary download mechanism for M1 bar data. Reserve raw bi5 only for tick data if the library's `INTERVAL_TICK` support proves insufficient.

**Rationale:** The `dukascopy-python` library (v4.0.1, MIT, Python 3.10+) is proven in production in ClaudeBackTester (25 pairs × 20 years), handles pagination, retry, and JSONP parsing cleanly, and supports both M1 bars and tick data. Building a custom bi5 decoder adds complexity without clear benefit for M1 bars.

### 7.3 Consider Session-Aware Gap Thresholds (OPTIONAL)

**Section:** Data Quality Gate Specifications → Gap detection

**Current:** "Flag gaps > 5 consecutive M1 bars"

**Proposed (optional):** Add note: "During low-activity sessions (Asian, off-hours), gaps of 5-10 consecutive M1 bars may be normal for less liquid pairs. If Story 1.5 validation produces excessive false positives during Asian session, consider raising the gap threshold to 10 bars for Asian/off-hours sessions."

**Rationale:** Asian session liquidity for some pairs is naturally thinner, producing occasional 5-7 minute gaps that are normal market behavior, not data feed issues. This is a soft recommendation — only implement if needed.

### 7.4 No Changes Needed

The following Architecture specifications are **confirmed by research — no changes needed:**
- Quality scoring formula and penalty weights
- Score thresholds (GREEN/YELLOW/RED)
- Gap severity levels (WARNING/ERROR)
- Quarantine approach (bool column, mark-and-skip)
- No interpolation rule
- Stale quote detection (bid=ask or spread=0 for > 5 bars)
- Spread outlier detection (10× session median)
- Consistent data sourcing (hash-based identification)
- Arrow IPC market_data schema (timestamp, OHLC, bid, ask, session, quarantined)

---

## 8. Build Plan for Stories 1.3-1.9

Using Story 1.1's verdict table combined with this research:

| Story | Title | Build Approach | Key Dependencies | Notes |
|---|---|---|---|---|
| **1.3** | Project Structure, Config & Logging | **Build new** | None | Config is hardcoded in baseline (not TOML). Logging uses structlog but not structured JSON. Build per Architecture specs. No baseline code to port. |
| **1.4** | Dukascopy Data Download | **Adapt** | 1.3 (config, logging, crash-safe write) | Port ClaudeBackTester's download flow using `dukascopy-python` library. Adapt: config-driven params, structured JSON logging, crash-safe writes with fsync, versioned artifacts, download manifest. Store separate bid/ask columns instead of computed spread. Add yearly chunk resume pattern from baseline. |
| **1.5** | Data Validation & Quality Scoring | **Adapt checks, replace scoring** | 1.4 (raw data) | Port baseline's gap detection (weekend/holiday awareness), zero/NaN checks, anomaly detection. **Replace** quality scoring with Architecture's formula. **Build new:** session-aware spread outlier detection, stale quote detection, quarantine marking, quality report artifact, session labeler utility. |
| **1.6** | Parquet Storage & Arrow IPC | **Build new (Arrow IPC), adapt (Parquet)** | 1.5 (validated data) | Baseline has Parquet writing (reusable pattern). Arrow IPC is entirely new: schema loading from contracts, mmap verification, session column stamping. Build new: schema validation, three-format strategy, conversion manifest. |
| **1.7** | Timeframe Conversion | **Adapt** | 1.6 (Arrow IPC data) | Port baseline's OHLCV aggregation logic (correct: first open, max high, min low, last close). **Adapt:** Arrow IPC tables instead of pandas, quarantined bar exclusion (new), session column handling (new), tick-to-M1 (new), fix weekly alignment (forex week vs ISO week). |
| **1.8** | Data Splitting & Consistent Sourcing | **Adapt split, build new hashing** | 1.7 (converted data) | Port baseline's chronological split logic (correct approach). **Build new:** dataset ID with SHA-256 hash (FR8), manifest creation, versioned artifact storage, multi-timeframe splitting, consistent sourcing verification. |
| **1.9** | E2E Pipeline Proof | **Build new** | 1.3-1.8 (all components) | No baseline equivalent. Capstone verification. Build from scratch per story spec. |

### Key Decisions for Implementation

1. **`dukascopy-python` is the primary download library** for M1 bars. Do not build a raw bi5 decoder unless tick data requires it.

2. **Quality scoring uses the Architecture's formula**, not the baseline's 0-100 model. The formula is confirmed as well-designed.

3. **Quarantine uses mark-and-skip** with a `quarantined: bool` column. No interpolation. Backtester handles boundary effects.

4. **Gap threshold stays at 5 consecutive M1 bars.** Session-aware adjustment (10 bars for Asian session) is optional and only needed if validation produces false positives.

5. **All Architecture specifications are confirmed** except the three minor updates proposed in Section 7.

---

## Sources

- [dukascopy-python on PyPI](https://pypi.org/project/dukascopy-python/) — v4.0.1, MIT license, supports tick + M1 data
- [TickVault on GitHub](https://github.com/keyhankamyar/TickVault) — Alternative for raw bi5 tick data
- [QuantPedia: Working with High-Frequency Tick Data](https://quantpedia.com/working-with-high-frequency-tick-data-cleaning-the-data/) — Brownlees & Gallo methodology
- [Data Intellect: Measuring Stale Data](https://dataintellect.com/blog/stale-data-measuring-what-isnt-there/) — Poisson process stale detection
- [StrategyQuant: Dukascopy Data Issues](https://strategyquant.com/forum/topic/3516-those-using-dukascopy-data-be-warned/) — Known Dukascopy quirks
- [Forex Factory: Dukascopy Historic Data](https://www.forexfactory.com/thread/492086-dukascopy-historic-data) — Community experience
- [KDnuggets: Missing Data in Time Series](https://www.kdnuggets.com/how-to-identify-missing-data-in-timeseries-datasets) — Gap identification methods
- ClaudeBackTester codebase review (Story 1.1) — `backtester/data/` modules
