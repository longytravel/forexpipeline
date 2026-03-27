//! Vectorized batch evaluator — single-pass multi-candidate scoring (D14).
//!
//! All candidates in a signal group share the SAME entry signals (same
//! fast_period/slow_period). Only their exit params differ (sl_atr_multiplier,
//! tp_rr_ratio, trailing_atr_multiplier). This module evaluates ALL candidates
//! in a single chronological pass through the data, achieving O(bars) instead
//! of O(bars * candidates).
//!
//! Data layout uses Structure-of-Arrays (SoA) for cache/SIMD friendliness:
//! contiguous f64 arrays per field, iterated together per bar.
//!
//! Optimizations:
//! - Column indices pre-resolved once before the bar loop (no per-bar string lookups)
//! - Signal plan compiled once: conditions classified, column slices cached
//! - Session labels encoded as integer codes (no per-bar string comparisons)
//! - Cost model pre-computed per session (single f64 constant per session)
//! - Online Welford Sharpe (no Vec<f64> heap allocation per candidate)
//! - Active/idle index sets (iterate only candidates that need work)

use std::collections::{BTreeMap, HashMap};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use arrow::array::*;
use arrow::record_batch::RecordBatch;

use common::error_types::BacktesterError;
use cost_model::{CostModel, PIP_VALUE};
use strategy_engine::StrategySpec;

// ---------------------------------------------------------------------------
// Pre-compiled signal plan (Task #1)
// ---------------------------------------------------------------------------

/// A single condition with its column data pre-resolved to a f64 slice.
struct CompiledCondition {
    /// Index into the prev_values array for crossover tracking.
    prev_idx: usize,
    threshold: f64,
    comparator: CompiledComparator,
}

/// Pre-compiled comparator — avoids per-bar string matching.
#[derive(Clone, Copy)]
enum CompiledComparator {
    CrossesAbove,
    CrossesBelow,
    Gt,
    Lt,
    Gte,
    Lte,
    Eq,
    Unknown,
}

impl CompiledComparator {
    fn from_str(s: &str) -> Self {
        match s {
            "crosses_above" => Self::CrossesAbove,
            "crosses_below" => Self::CrossesBelow,
            ">" => Self::Gt,
            "<" => Self::Lt,
            ">=" => Self::Gte,
            "<=" => Self::Lte,
            "==" => Self::Eq,
            _ => Self::Unknown,
        }
    }

    fn is_directional(self) -> bool {
        matches!(self, Self::CrossesAbove | Self::CrossesBelow)
    }
}

/// Pre-compiled signal plan: all column indices resolved, conditions classified.
struct CompiledSignalPlan {
    /// Indices into `condition_col_slices` for directional conditions (crosses_above/below).
    directional: Vec<usize>,
    /// Indices into `condition_col_slices` for threshold filter conditions.
    filters: Vec<usize>,
    /// All conditions with pre-resolved data.
    conditions: Vec<CompiledCondition>,
    /// Column index in the RecordBatch for each condition (for f64 array access).
    col_indices: Vec<usize>,
    /// Total number of prev_values slots needed.
    n_prev: usize,
    /// Allowed session codes for entry (empty = all allowed).
    allowed_sessions: Vec<u8>,
    /// True if there are no directional conditions (fallback to long).
    no_directional: bool,
}

/// Pre-computed cost model: one cost_price (in price units) per session code.
struct PrecomputedCosts {
    /// cost_price[session_code] = (mean_spread + mean_slippage) * PIP_VALUE
    /// For buy: price + cost_price; for sell: price - cost_price.
    cost_by_session: Vec<f64>,
}

impl PrecomputedCosts {
    /// Pre-compute cost for each session code.
    fn new(session_map: &HashMap<String, u8>, cost_model: &CostModel) -> Self {
        let max_code = session_map.values().copied().max().unwrap_or(0) as usize;
        let mut cost_by_session = vec![0.0; max_code + 1];

        for (session_name, &code) in session_map {
            if let Ok(profile) = cost_model.get_cost(session_name) {
                cost_by_session[code as usize] =
                    (profile.mean_spread_pips + profile.mean_slippage_pips) * PIP_VALUE;
            }
        }

        PrecomputedCosts { cost_by_session }
    }

    /// Apply entry cost (buy = price + cost, sell = price - cost).
    #[inline]
    fn apply_entry(&self, price: f64, session_code: u8, dir: i8) -> f64 {
        let cost = self.cost_by_session[session_code as usize];
        if dir > 0 { price + cost } else { price - cost }
    }

    /// Apply exit cost (long exit = sell = price - cost, short exit = buy = price + cost).
    #[inline]
    fn apply_exit(&self, price: f64, session_code: u8, dir: i8) -> f64 {
        let cost = self.cost_by_session[session_code as usize];
        if dir > 0 { price - cost } else { price + cost }
    }
}

/// Build the session string -> integer code mapping by scanning the session column.
fn build_session_map(sessions: &StringArray) -> HashMap<String, u8> {
    let mut map = HashMap::new();
    let mut next_code: u8 = 0;
    for i in 0..sessions.len() {
        let s = sessions.value(i);
        if !map.contains_key(s) {
            map.insert(s.to_string(), next_code);
            next_code = next_code.saturating_add(1);
        }
    }
    map
}

/// Encode session column as integer codes for the bar range.
fn encode_sessions(sessions: &StringArray, map: &HashMap<String, u8>, start: usize, end: usize) -> Vec<u8> {
    let mut codes = Vec::with_capacity(end - start);
    for i in start..end {
        codes.push(*map.get(sessions.value(i)).unwrap_or(&0));
    }
    codes
}

/// Build signal column name — mirrors engine.rs convention.
fn build_signal_column_name(indicator: &str, params: &strategy_engine::IndicatorParams) -> String {
    let mut name = indicator.to_string();
    for (key, val) in params {
        if key == "period" || key == "length" || key == "window" {
            if let Some(n) = val.as_integer() {
                name = format!("{name}_{n}");
            } else if let Some(f) = val.as_float() {
                name = format!("{name}_{}", f as i64);
            }
        }
    }
    name
}

/// Compile the signal plan once before the bar loop.
fn compile_signal_plan(
    spec: &StrategySpec,
    data: &RecordBatch,
    session_map: &HashMap<String, u8>,
) -> Result<CompiledSignalPlan, BacktesterError> {
    let schema = data.schema();
    let mut directional = Vec::new();
    let mut filters = Vec::new();
    let mut conditions = Vec::new();
    let mut col_indices = Vec::new();
    let mut prev_idx_counter = 0usize;

    for cond in &spec.entry_rules.conditions {
        let comp = CompiledComparator::from_str(&cond.comparator);
        let col_name = build_signal_column_name(&cond.indicator, &cond.parameters);

        // Resolve column index: try signal column name first, then raw indicator name
        let col_idx = schema.index_of(&col_name).ok()
            .or_else(|| schema.index_of(&cond.indicator).ok())
            .ok_or_else(|| BacktesterError::ArrowIpc(
                format!("Signal column not found: '{}' or '{}'", col_name, cond.indicator)
            ))?;

        // Verify the column is Float64
        data.column(col_idx).as_any().downcast_ref::<Float64Array>()
            .ok_or_else(|| BacktesterError::ArrowIpc(
                format!("Signal column '{}' is not Float64", col_name)
            ))?;

        let idx = conditions.len();
        if comp.is_directional() {
            directional.push(idx);
        } else {
            filters.push(idx);
        }

        conditions.push(CompiledCondition {
            prev_idx: prev_idx_counter,
            threshold: cond.threshold,
            comparator: comp,
        });
        col_indices.push(col_idx);
        prev_idx_counter += 1;
    }

    // Pre-compute allowed session codes from entry filters
    let mut allowed_sessions = Vec::new();
    for filter in &spec.entry_rules.filters {
        if let strategy_engine::Filter::Session(params) = filter {
            for session_name in &params.include {
                if let Some(&code) = session_map.get(session_name.as_str()) {
                    allowed_sessions.push(code);
                }
            }
        }
    }

    let no_directional = directional.is_empty();

    Ok(CompiledSignalPlan {
        directional,
        filters,
        conditions,
        col_indices,
        n_prev: prev_idx_counter,
        allowed_sessions,
        no_directional,
    })
}

/// Detect entry signal using pre-compiled plan — no per-bar string lookups.
#[inline]
fn detect_entry_signal_compiled(
    plan: &CompiledSignalPlan,
    data: &RecordBatch,
    row: usize,
    prev_values: &mut [f64],
    session_code: u8,
) -> Option<i8> {
    // Helper: read f64 from pre-resolved column index
    let read_val = |cond_idx: usize| -> f64 {
        let col = data.column(plan.col_indices[cond_idx]);
        // SAFETY: compile_signal_plan verified this column is Float64Array at plan
        // construction time (line 194). The RecordBatch is immutable so the type
        // cannot change between plan build and bar-loop execution.
        unsafe {
            col.as_any().downcast_ref::<Float64Array>().unwrap_unchecked().value(row)
        }
    };

    // 1. All threshold filters must pass
    let mut all_pass = true;
    for &idx in &plan.filters {
        let cond = &plan.conditions[idx];
        let value = read_val(idx);
        let passes = match cond.comparator {
            CompiledComparator::Gt => value > cond.threshold,
            CompiledComparator::Lt => value < cond.threshold,
            CompiledComparator::Gte => value >= cond.threshold,
            CompiledComparator::Lte => value <= cond.threshold,
            CompiledComparator::Eq => (value - cond.threshold).abs() < 1e-10,
            _ => false,
        };
        prev_values[cond.prev_idx] = value;
        if !passes {
            all_pass = false;
            // Still need to update prev_values for remaining filter conditions
            for &remaining_idx in &plan.filters {
                if remaining_idx > idx {
                    let rc = &plan.conditions[remaining_idx];
                    prev_values[rc.prev_idx] = read_val(remaining_idx);
                }
            }
            break;
        }
    }

    // 2. Read directional condition values and check crossovers
    let mut fired: Option<i8> = None;
    for &idx in &plan.directional {
        let cond = &plan.conditions[idx];
        let value = read_val(idx);
        let prev = prev_values[cond.prev_idx];

        if all_pass && fired.is_none() && prev.is_finite() {
            let passes = match cond.comparator {
                CompiledComparator::CrossesAbove => prev <= cond.threshold && value > cond.threshold,
                CompiledComparator::CrossesBelow => prev >= cond.threshold && value < cond.threshold,
                _ => false,
            };
            if passes {
                fired = Some(match cond.comparator {
                    CompiledComparator::CrossesAbove => 1,  // Long
                    _ => -1,                                 // Short
                });
            }
        }

        // Always update prev_values
        prev_values[cond.prev_idx] = value;
    }

    // Fallback: non-directional strategies
    if plan.no_directional && all_pass && !plan.filters.is_empty() {
        fired = Some(1); // Default long
    }

    // Apply session filter via pre-computed allowed set
    if fired.is_some() && !plan.allowed_sessions.is_empty() {
        if !plan.allowed_sessions.contains(&session_code) {
            return None;
        }
    }

    fired
}

// ---------------------------------------------------------------------------
// SoA candidate state (Task #2: online Welford Sharpe, active/idle sets)
// ---------------------------------------------------------------------------

/// Per-candidate state laid out as Structure-of-Arrays for cache efficiency.
/// Uses Welford's online algorithm instead of Vec<f64> for Sharpe computation.
struct BatchCandidateState {
    // -- Exit parameters (set once from param_batch) --
    sl_atr_mult: Vec<f64>,
    tp_rr_ratio: Vec<f64>,
    trailing_atr_mult: Vec<f64>,

    // -- Per-candidate position state (updated each bar) --
    direction: Vec<i8>, // 1=long, -1=short, 0=none
    entry_price: Vec<f64>,
    sl_price: Vec<f64>,
    tp_price: Vec<f64>,
    trailing_level: Vec<f64>,
    trailing_best: Vec<f64>,
    trailing_distance: Vec<f64>, // in price units

    // -- Online Welford accumulators (replaces Vec<Vec<f64>>) --
    welford_count: Vec<u32>,
    welford_mean: Vec<f64>,
    welford_m2: Vec<f64>,

    // -- Active/idle index sets (replaces Vec<bool> in_trade scan) --
    /// Candidates currently in a trade.
    active: Vec<usize>,
    /// Candidates not in a trade (available for entry).
    idle: Vec<usize>,
    /// Reverse lookup: is_active[i] = true if candidate i is in active set.
    is_active: Vec<bool>,
}

impl BatchCandidateState {
    fn new(candidates: &[BTreeMap<String, f64>]) -> Self {
        let n = candidates.len();
        let mut sl_atr_mult = vec![1.5; n];
        let mut tp_rr_ratio = vec![2.0; n];
        let mut trailing_atr_mult = vec![2.5; n];

        for (i, params) in candidates.iter().enumerate() {
            if let Some(&v) = params.get("sl_atr_multiplier") {
                sl_atr_mult[i] = v;
            }
            if let Some(&v) = params.get("tp_rr_ratio") {
                tp_rr_ratio[i] = v;
            }
            if let Some(&v) = params.get("trailing_atr_multiplier") {
                trailing_atr_mult[i] = v;
            }
        }

        BatchCandidateState {
            sl_atr_mult,
            tp_rr_ratio,
            trailing_atr_mult,
            direction: vec![0; n],
            entry_price: vec![0.0; n],
            sl_price: vec![0.0; n],
            tp_price: vec![0.0; n],
            trailing_level: vec![0.0; n],
            trailing_best: vec![0.0; n],
            trailing_distance: vec![0.0; n],
            welford_count: vec![0; n],
            welford_mean: vec![0.0; n],
            welford_m2: vec![0.0; n],
            active: Vec::new(),
            idle: (0..n).collect(),
            is_active: vec![false; n],
        }
    }

    /// Record a trade PnL using Welford's online algorithm.
    #[inline]
    fn record_pnl(&mut self, i: usize, pnl: f64) {
        self.welford_count[i] += 1;
        let count = self.welford_count[i] as f64;
        let delta = pnl - self.welford_mean[i];
        self.welford_mean[i] += delta / count;
        let delta2 = pnl - self.welford_mean[i];
        self.welford_m2[i] += delta * delta2;
    }

    /// Move candidate from active to idle.
    #[inline]
    fn deactivate(&mut self, i: usize) {
        if !self.is_active[i] {
            return; // Guard: avoid duplicate idle entries if called on already-idle candidate
        }
        self.is_active[i] = false;
        self.direction[i] = 0;
        // Remove from active (swap-remove for O(1))
        if let Some(pos) = self.active.iter().position(|&x| x == i) {
            self.active.swap_remove(pos);
        }
        self.idle.push(i);
    }

    /// Open positions for ALL idle candidates at an entry signal bar.
    #[inline]
    fn open_all(
        &mut self,
        dir: i8,
        entry_price_adjusted: f64,
        atr_value: f64,
        sl_type: &str,
        tp_type: Option<&str>,
        sl_value_spec: f64,
        tp_value_spec: Option<f64>,
    ) {
        let pip = PIP_VALUE;

        // Drain idle into active
        let to_open: Vec<usize> = self.idle.drain(..).collect();

        for i in to_open {
            self.is_active[i] = true;
            self.active.push(i);
            self.direction[i] = dir;
            self.entry_price[i] = entry_price_adjusted;

            // --- Stop loss distance (in price units) ---
            let sl_distance = match sl_type {
                "atr_multiple" if atr_value > 0.0 => atr_value * self.sl_atr_mult[i],
                _ => sl_value_spec * pip, // fixed_pips fallback uses spec value
            };

            // --- Take profit distance (in price units) ---
            let tp_distance = match tp_type {
                Some("atr_multiple") if atr_value > 0.0 => {
                    sl_distance * self.tp_rr_ratio[i]
                }
                Some("risk_reward") => {
                    sl_distance * self.tp_rr_ratio[i]
                }
                Some(_) => {
                    tp_value_spec.unwrap_or(2.0) * pip
                }
                None => 0.0, // No TP configured
            };

            // --- Trailing distance (in price units) ---
            let trail_dist = if atr_value > 0.0 {
                atr_value * self.trailing_atr_mult[i]
            } else {
                0.0
            };
            self.trailing_distance[i] = trail_dist;

            // --- Compute levels based on direction ---
            if dir > 0 {
                // LONG
                self.sl_price[i] = entry_price_adjusted - sl_distance;
                self.tp_price[i] = if tp_distance > 0.0 {
                    entry_price_adjusted + tp_distance
                } else {
                    f64::MAX // No TP
                };
                self.trailing_level[i] = if trail_dist > 0.0 {
                    entry_price_adjusted - trail_dist
                } else {
                    f64::NEG_INFINITY // No trailing
                };
                self.trailing_best[i] = entry_price_adjusted;
            } else {
                // SHORT
                self.sl_price[i] = entry_price_adjusted + sl_distance;
                self.tp_price[i] = if tp_distance > 0.0 {
                    entry_price_adjusted - tp_distance
                } else {
                    f64::MIN // No TP
                };
                self.trailing_level[i] = if trail_dist > 0.0 {
                    entry_price_adjusted + trail_dist
                } else {
                    f64::INFINITY // No trailing
                };
                self.trailing_best[i] = entry_price_adjusted;
            }
        }
    }

    /// Check exits and update trailing for ALL active candidates against one bar.
    #[inline]
    fn process_bar(&mut self, high: f64, low: f64, costs: &PrecomputedCosts, session_code: u8) {
        // Snapshot active indices to avoid borrow conflict (self.active is small).
        let n_active = self.active.len();
        if n_active == 0 {
            return;
        }

        // Use a stack buffer for typical candidate counts, heap fallback for large.
        let active_snapshot: Vec<usize> = self.active.clone();
        let mut to_deactivate = Vec::new();

        for &i in &active_snapshot {
            let dir = self.direction[i];
            let (sl_hit, tp_hit, trail_hit) = if dir > 0 {
                (
                    low <= self.sl_price[i],
                    high >= self.tp_price[i],
                    low <= self.trailing_level[i],
                )
            } else {
                (
                    high >= self.sl_price[i],
                    low <= self.tp_price[i],
                    high >= self.trailing_level[i],
                )
            };

            if sl_hit || tp_hit || trail_hit {
                let exit_price_raw = if sl_hit {
                    self.sl_price[i]
                } else if tp_hit {
                    self.tp_price[i]
                } else {
                    self.trailing_level[i]
                };

                let exit_price = costs.apply_exit(exit_price_raw, session_code, dir);
                let pnl = (exit_price - self.entry_price[i]) * dir as f64 / PIP_VALUE;
                self.record_pnl(i, pnl);
                to_deactivate.push(i);
            } else {
                // Update trailing stop
                if dir > 0 {
                    if high > self.trailing_best[i] {
                        self.trailing_best[i] = high;
                        if self.trailing_distance[i] > 0.0 {
                            let new_level = high - self.trailing_distance[i];
                            if new_level > self.trailing_level[i] {
                                self.trailing_level[i] = new_level;
                            }
                        }
                    }
                } else {
                    if low < self.trailing_best[i] {
                        self.trailing_best[i] = low;
                        if self.trailing_distance[i] > 0.0 {
                            let new_level = low + self.trailing_distance[i];
                            if new_level < self.trailing_level[i] {
                                self.trailing_level[i] = new_level;
                            }
                        }
                    }
                }
            }
        }

        for i in to_deactivate {
            self.deactivate(i);
        }
    }

    /// Close all remaining open positions at end-of-data.
    fn close_all_eod(&mut self, bid: f64, ask: f64, costs: &PrecomputedCosts, session_code: u8) {
        let active_snapshot: Vec<usize> = self.active.clone();
        for i in active_snapshot {
            let dir = self.direction[i];
            let exit_price_raw = if dir > 0 { bid } else { ask };
            let exit_price = costs.apply_exit(exit_price_raw, session_code, dir);
            let pnl = (exit_price - self.entry_price[i]) * dir as f64 / PIP_VALUE;
            self.record_pnl(i, pnl);
            self.deactivate(i);
        }
    }

    /// Compute unannualized Sharpe from Welford accumulators.
    /// Matches metrics.rs convention: returns 0.0 for < 2 trades or zero std.
    fn compute_sharpe(&self, i: usize) -> f64 {
        let count = self.welford_count[i];
        if count < 2 {
            return 0.0;
        }
        let mean = self.welford_mean[i];
        // Sample variance = M2 / (n - 1), matching the original compute_sharpe
        let variance = self.welford_m2[i] / (count as f64 - 1.0);
        let std = variance.sqrt();
        if std == 0.0 {
            return 0.0;
        }
        mean / std // unannualized
    }
}

// ---------------------------------------------------------------------------
// Sharpe computation (kept for tests, delegates to same formula)
// ---------------------------------------------------------------------------

/// Compute unannualized Sharpe ratio from trade PnLs (matches metrics.rs convention).
/// Kept for tests to verify Welford online accumulator produces identical results.
#[cfg(test)]
fn compute_sharpe(pnls: &[f64]) -> f64 {
    let n = pnls.len();
    if n < 2 {
        return 0.0; // Match metrics.rs: returns 0.0 for < 2 trades
    }
    let mean = pnls.iter().sum::<f64>() / n as f64;
    let variance = pnls.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / (n as f64 - 1.0);
    let std = variance.sqrt();
    if std == 0.0 {
        return 0.0;
    }
    mean / std // unannualized, matching metrics.rs
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/// Run vectorized batch evaluation: single pass through data, ALL candidates
/// scored simultaneously.
///
/// Returns one Sharpe ratio per candidate.
pub fn run_batch_vectorized(
    data: &RecordBatch,
    candidates: &[BTreeMap<String, f64>],
    base_spec: &StrategySpec,
    cost_model: &CostModel,
    cancelled: Arc<AtomicBool>,
    window_start: Option<u64>,
    window_end: Option<u64>,
) -> Result<Vec<f64>, BacktesterError> {
    let total_rows = data.num_rows();
    let start = window_start.unwrap_or(0) as usize;
    let end = window_end.map(|e| e as usize).unwrap_or(total_rows).min(total_rows);

    // Pre-resolve OHLC + market columns as f64 slices (once)
    let highs = get_f64_col(data, "high")?;
    let lows = get_f64_col(data, "low")?;
    let bids = get_f64_col(data, "bid")?;
    let asks = get_f64_col(data, "ask")?;
    let sessions = get_string_col(data, "session")?;
    let quarantined = get_bool_col(data, "quarantined")?;

    // ATR column for exit level computation (pre-resolved once)
    let atr_period = match &base_spec.exit_rules.trailing {
        Some(strategy_engine::TrailingConfig::Chandelier(p)) => p.atr_period as i64,
        _ => 14,
    };
    let atr_col_name = format!("atr_{}", atr_period);
    let atr_column: Option<&Float64Array> = data.schema().index_of(&atr_col_name).ok()
        .and_then(|idx| data.column(idx).as_any().downcast_ref::<Float64Array>());

    // Exit config from spec (pre-resolved once)
    let sl_type = base_spec.exit_rules.stop_loss.exit_type.as_str();
    let sl_value_spec = base_spec.exit_rules.stop_loss.value;
    let tp_type = base_spec.exit_rules.take_profit.as_ref().map(|tp| tp.exit_type.as_str());
    let tp_value_spec = base_spec.exit_rules.take_profit.as_ref().map(|tp| tp.value);

    // --- Task #1: Pre-compute session codes and cost model ---
    let session_map = build_session_map(sessions);
    let session_codes = encode_sessions(sessions, &session_map, start, end);
    let costs = PrecomputedCosts::new(&session_map, cost_model);

    // --- Task #1: Compile signal plan once ---
    let plan = compile_signal_plan(base_spec, data, &session_map)?;
    let mut prev_values = vec![f64::NAN; plan.n_prev]; // NaN = no previous value

    // Initialize SoA state (Task #2: online Welford + active/idle sets)
    let mut state = BatchCandidateState::new(candidates);

    let n_candidates = candidates.len();

    eprintln!(
        "{{\"level\":\"info\",\"msg\":\"Vectorized batch: {} candidates, bars {}..{} ({} total)\"}}",
        n_candidates, start, end, end - start
    );

    // Single pass through all bars
    for bar in start..end {
        // Check cancellation every 10K bars
        if bar % 10_000 == 0 && cancelled.load(Ordering::Relaxed) {
            eprintln!("{{\"level\":\"warn\",\"msg\":\"Vectorized batch cancelled at bar {bar}\"}}");
            break;
        }

        let high = highs.value(bar);
        let low = lows.value(bar);
        let bid = bids.value(bar);
        let ask = asks.value(bar);
        let session_code = session_codes[bar - start];
        let is_quarantined = quarantined.value(bar);

        // 1. Check exits for ALL active candidates (iterates only active set)
        state.process_bar(high, low, &costs, session_code);

        // 2. Skip entry on quarantined bars
        if is_quarantined {
            continue;
        }

        // 3. Detect entry signal using compiled plan (no string lookups)
        if let Some(dir) = detect_entry_signal_compiled(&plan, data, bar, &mut prev_values, session_code) {
            // Compute entry fill price using pre-computed costs
            let entry_price_raw = if dir > 0 { ask } else { bid };
            let entry_price_adjusted = costs.apply_entry(entry_price_raw, session_code, dir);

            let atr_value = atr_column.map(|col| col.value(bar)).unwrap_or(0.0);

            // Open positions for ALL idle candidates
            state.open_all(
                dir,
                entry_price_adjusted,
                atr_value,
                sl_type,
                tp_type,
                sl_value_spec,
                tp_value_spec,
            );
        }
    }

    // Close remaining positions at end of data
    if end > start {
        let last = end - 1;
        let last_session_code = session_codes[last - start];
        state.close_all_eod(
            bids.value(last),
            asks.value(last),
            &costs,
            last_session_code,
        );
    }

    // Compute Sharpe per candidate from Welford accumulators (no Vec allocation)
    let scores: Vec<f64> = (0..n_candidates)
        .map(|i| state.compute_sharpe(i))
        .collect();

    let finite_count = scores.iter().filter(|s| s.is_finite() && **s != 0.0).count();
    eprintln!(
        "{{\"level\":\"info\",\"msg\":\"Vectorized batch complete: {}/{} candidates with non-zero scores\"}}",
        finite_count, n_candidates
    );

    Ok(scores)
}

// ---------------------------------------------------------------------------
// Arrow column extraction helpers (local to this module)
// ---------------------------------------------------------------------------

fn get_f64_col<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a Float64Array, BacktesterError> {
    let col = batch.column(
        batch.schema().index_of(name)
            .map_err(|_| BacktesterError::ArrowIpc(format!("Missing column: {name}")))?
    );
    col.as_any()
        .downcast_ref::<Float64Array>()
        .ok_or_else(|| BacktesterError::ArrowIpc(format!("Column '{name}' is not Float64")))
}

fn get_string_col<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a StringArray, BacktesterError> {
    let col = batch.column(
        batch.schema().index_of(name)
            .map_err(|_| BacktesterError::ArrowIpc(format!("Missing column: {name}")))?
    );
    col.as_any()
        .downcast_ref::<StringArray>()
        .ok_or_else(|| BacktesterError::ArrowIpc(format!("Column '{name}' is not Utf8")))
}

fn get_bool_col<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a BooleanArray, BacktesterError> {
    let col = batch.column(
        batch.schema().index_of(name)
            .map_err(|_| BacktesterError::ArrowIpc(format!("Missing column: {name}")))?
    );
    col.as_any()
        .downcast_ref::<BooleanArray>()
        .ok_or_else(|| BacktesterError::ArrowIpc(format!("Column '{name}' is not Bool")))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sharpe_zero_trades() {
        assert_eq!(compute_sharpe(&[]), 0.0);
    }

    #[test]
    fn test_sharpe_one_trade() {
        assert_eq!(compute_sharpe(&[10.0]), 0.0);
    }

    #[test]
    fn test_sharpe_positive() {
        let pnls = vec![10.0, 20.0, -5.0, 15.0];
        let s = compute_sharpe(&pnls);
        assert!(s > 0.0, "Sharpe should be positive for net-positive trades");
    }

    #[test]
    fn test_sharpe_all_same() {
        // All identical PnLs -> std=0 -> sharpe=0
        let pnls = vec![5.0, 5.0, 5.0, 5.0];
        assert_eq!(compute_sharpe(&pnls), 0.0);
    }

    #[test]
    fn test_welford_matches_batch() {
        // Verify Welford online Sharpe matches the batch compute_sharpe
        let pnls = vec![10.0, 20.0, -5.0, 15.0, -3.0, 8.0, 12.0, -1.0];
        let batch_sharpe = compute_sharpe(&pnls);

        // Simulate Welford accumulation
        let mut count: u32 = 0;
        let mut mean: f64 = 0.0;
        let mut m2: f64 = 0.0;
        for &pnl in &pnls {
            count += 1;
            let delta = pnl - mean;
            mean += delta / count as f64;
            let delta2 = pnl - mean;
            m2 += delta * delta2;
        }
        let variance = m2 / (count as f64 - 1.0);
        let std = variance.sqrt();
        let welford_sharpe = if std == 0.0 { 0.0 } else { mean / std };

        assert!(
            (batch_sharpe - welford_sharpe).abs() < 1e-10,
            "Welford Sharpe ({}) must match batch Sharpe ({})",
            welford_sharpe, batch_sharpe
        );
    }

    #[test]
    fn test_welford_two_trades() {
        let pnls = vec![10.0, -10.0];
        let batch_sharpe = compute_sharpe(&pnls);

        let mut count: u32 = 0;
        let mut mean: f64 = 0.0;
        let mut m2: f64 = 0.0;
        for &pnl in &pnls {
            count += 1;
            let delta = pnl - mean;
            mean += delta / count as f64;
            let delta2 = pnl - mean;
            m2 += delta * delta2;
        }
        let variance = m2 / (count as f64 - 1.0);
        let std = variance.sqrt();
        let welford_sharpe = if std == 0.0 { 0.0 } else { mean / std };

        assert!(
            (batch_sharpe - welford_sharpe).abs() < 1e-10,
            "Welford ({}) must match batch ({})",
            welford_sharpe, batch_sharpe
        );
    }
}
