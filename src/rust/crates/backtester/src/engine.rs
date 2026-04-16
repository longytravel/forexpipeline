//! Backtest evaluation engine — main loop (AC #2, #4, #8, #9).
//!
//! Iterates bars chronologically: evaluate exits → update trailing stops →
//! skip quarantined → evaluate entry signals → record equity → checkpoint.
//! Shares core evaluation logic with future live daemon via strategy_engine crate.

use std::collections::HashMap;
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Instant;

use arrow::array::*;
use arrow::ipc::reader::FileReader;
use arrow::record_batch::RecordBatch;

use common::error_types::BacktesterError;
use cost_model::{CostModel, PIP_VALUE};
use strategy_engine::{Condition, StrategySpec};

use crate::fold::FoldConfig;
use crate::metrics::{compute_metrics, EquityPoint, Metrics};
use crate::position::{Bar, Direction, ExitReason, Position, PositionManager, TrailingStop};
use crate::progress::{write_progress, should_report, ProgressReport};
use crate::trade_simulator::{
    build_trade_record, compute_pnl, simulate_entry_fill, simulate_exit_fill, TradeRecord,
};

/// Result of a completed backtest run.
#[derive(Debug)]
pub struct BacktestResult {
    pub trades: Vec<TradeRecord>,
    pub equity_curve: Vec<EquityPoint>,
    pub equity_timestamps: Vec<i64>,
    pub equity_unrealized: Vec<f64>,
    pub equity_drawdown_pips: Vec<f64>,
    pub equity_open_trades: Vec<i64>,
    pub metrics: Metrics,
    pub total_bars: u64,
}

/// Checkpoint data for crash recovery.
#[derive(serde::Serialize, serde::Deserialize, Debug)]
pub struct Checkpoint {
    pub stage: String,
    pub progress_pct: f64,
    pub last_completed_bar: u64,
    pub total_bars: u64,
    pub open_position: Option<SerializedPosition>,
    pub cumulative_pnl: f64,
    pub trade_count: u64,
    pub checkpoint_at: String,
}

/// Serializable position state for checkpoints.
#[derive(serde::Serialize, serde::Deserialize, Debug)]
pub struct SerializedPosition {
    pub direction: String,
    pub entry_price_raw: f64,
    pub entry_price: f64,
    pub entry_time: i64,
    pub entry_spread: f64,
    pub entry_slippage: f64,
    pub session: String,
    pub entry_signal_id: u64,
    pub stop_loss: Option<f64>,
    pub take_profit: Option<f64>,
    pub trailing_stop_distance: Option<f64>,
    pub trailing_stop_level: Option<f64>,
    pub entry_bar_index: u64,
    pub lot_size: f64,
}

/// Signal from evaluating a bar against the strategy.
#[derive(Debug)]
pub struct Signal {
    pub direction: Option<Direction>,
    pub signal_id: u64,
}

/// Load Arrow IPC market data into a single concatenated RecordBatch.
///
/// Extracted for reuse: batch mode loads data once and shares the immutable
/// RecordBatch across parallel Rayon threads.
pub fn load_market_data(data_path: &Path) -> Result<RecordBatch, BacktesterError> {
    let file = std::fs::File::open(data_path)?;
    let reader = FileReader::try_new(file, None)
        .map_err(|e| BacktesterError::ArrowIpc(format!("Failed to open Arrow IPC: {e}")))?;

    let batches: Vec<RecordBatch> = reader
        .into_iter()
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| BacktesterError::ArrowIpc(format!("Failed to read batches: {e}")))?;

    if batches.is_empty() {
        return Err(BacktesterError::Validation("Empty Arrow IPC data".into()));
    }

    let batch = arrow::compute::concat_batches(&batches[0].schema(), &batches)
        .map_err(|e| BacktesterError::ArrowIpc(format!("Failed to concat batches: {e}")))?;

    if batch.num_rows() == 0 {
        return Err(BacktesterError::Validation("Zero rows in market data".into()));
    }

    Ok(batch)
}

/// Run a backtest from a pre-loaded RecordBatch (no progress/checkpoint I/O).
///
/// Used by batch mode where data is loaded once and shared across Rayon threads.
/// Skips progress file writing and checkpoint creation to avoid I/O contention.
pub fn run_backtest_from_batch(
    spec: &StrategySpec,
    batch: &RecordBatch,
    cost_model: &CostModel,
    cancel_flag: Arc<AtomicBool>,
    fold_config: Option<FoldConfig>,
    window_start: Option<u64>,
    window_end: Option<u64>,
) -> Result<BacktestResult, BacktesterError> {
    run_backtest_inner(spec, batch, cost_model, None, "", cancel_flag, fold_config, None, window_start, window_end)
}

/// Run a complete backtest evaluation.
pub fn run_backtest(
    spec: &StrategySpec,
    data_path: &Path,
    cost_model: &CostModel,
    output_dir: &Path,
    config_hash: &str,
    cancel_flag: Arc<AtomicBool>,
    fold_config: Option<FoldConfig>,
    checkpoint: Option<Checkpoint>,
    window_start: Option<u64>,
    window_end: Option<u64>,
) -> Result<BacktestResult, BacktesterError> {
    let batch = load_market_data(data_path)?;
    run_backtest_inner(spec, &batch, cost_model, Some(output_dir), config_hash, cancel_flag, fold_config, checkpoint, window_start, window_end)
}

/// Internal backtest implementation shared by `run_backtest` and `run_backtest_from_batch`.
///
/// When `output_dir` is `None`, progress/checkpoint I/O is skipped (batch mode).
fn run_backtest_inner(
    spec: &StrategySpec,
    batch: &RecordBatch,
    cost_model: &CostModel,
    output_dir: Option<&Path>,
    config_hash: &str,
    cancel_flag: Arc<AtomicBool>,
    fold_config: Option<FoldConfig>,
    checkpoint: Option<Checkpoint>,
    window_start: Option<u64>,
    window_end: Option<u64>,
) -> Result<BacktestResult, BacktesterError> {
    let total_rows = batch.num_rows();

    // Extract columns by name
    let timestamps = get_i64_column(batch, "timestamp")?;
    let opens = get_f64_column(batch, "open")?;
    let highs = get_f64_column(batch, "high")?;
    let lows = get_f64_column(batch, "low")?;
    let closes = get_f64_column(batch, "close")?;
    let bids = get_f64_column(batch, "bid")?;
    let asks = get_f64_column(batch, "ask")?;
    let sessions = get_string_column(batch, "session")?;
    let quarantined = get_bool_column(batch, "quarantined")?;

    // Determine evaluation range
    let start_bar = window_start.unwrap_or(0) as usize;
    let end_bar = window_end.map(|e| e as usize).unwrap_or(total_rows);
    let end_bar = end_bar.min(total_rows);

    // V1 has no stochastic elements; seed reserved for future stochastic cost sampling (AC #8)
    let _seed = hash_to_seed(config_hash);

    // Pre-allocate buffers
    let bar_count = end_bar.saturating_sub(start_bar);
    let mut trades: Vec<TradeRecord> = Vec::with_capacity(bar_count / 100 + 1);
    let mut equity_points: Vec<EquityPoint> = Vec::with_capacity(bar_count);
    let mut equity_timestamps: Vec<i64> = Vec::with_capacity(bar_count);
    let mut equity_unrealized: Vec<f64> = Vec::with_capacity(bar_count);
    let mut equity_drawdown_pips: Vec<f64> = Vec::with_capacity(bar_count);
    let mut equity_open_trades: Vec<i64> = Vec::with_capacity(bar_count);

    let mut position_manager = PositionManager::new();
    let mut trade_counter: u64 = 0;
    let mut signal_counter: u64 = 0;
    let mut closed_pnl: f64 = 0.0;
    let mut peak_equity: f64 = 0.0;

    // Resume from checkpoint if available
    let resume_bar = if let Some(ref cp) = checkpoint {
        closed_pnl = cp.cumulative_pnl;
        trade_counter = cp.trade_count;
        if let Some(ref sp) = cp.open_position {
            let pos = deserialize_position(sp);
            position_manager.open_position(pos);
        }
        (cp.last_completed_bar + 1) as usize
    } else {
        start_bar
    };

    // Compute exit level configuration from strategy spec.
    // For atr_multiple stop/TP, the value is a multiplier applied to ATR at entry time.
    // For fixed_pips, the value is used directly as pips.
    let sl_config = &spec.exit_rules.stop_loss;
    let tp_config = spec.exit_rules.take_profit.as_ref();
    let trailing_config = &spec.exit_rules.trailing;

    // Pre-load ATR column if needed for atr_multiple exits or chandelier trailing
    let atr_period = match trailing_config {
        Some(strategy_engine::TrailingConfig::Chandelier(params)) => params.atr_period as i64,
        _ => 14, // default ATR period
    };
    let needs_atr = sl_config.exit_type == "atr_multiple"
        || tp_config.map_or(false, |tp| tp.exit_type == "atr_multiple")
        || matches!(trailing_config, Some(strategy_engine::TrailingConfig::Chandelier(_)));

    let atr_col_name = format!("atr_{}", atr_period);
    let atr_column: Option<&Float64Array> = if needs_atr {
        match batch.schema().index_of(&atr_col_name).ok() {
            Some(idx) => batch.column(idx).as_any().downcast_ref::<Float64Array>(),
            None => {
                eprintln!(
                    "{{\"level\":\"error\",\"msg\":\"ATR column '{}' not found in data — atr_multiple exits will use fallback. Run signal precompute with ATR.\"}}",
                    atr_col_name
                );
                None
            }
        }
    } else {
        None
    };

    let trailing_distance = match trailing_config {
        Some(strategy_engine::TrailingConfig::TrailingStop(params)) => Some(params.distance_pips),
        Some(strategy_engine::TrailingConfig::Chandelier(_)) => None, // Computed per-trade from ATR
        None => None,
    };

    let lot_size = if spec.position_sizing.method == "fixed_lots" {
        spec.position_sizing.max_lots
    } else {
        spec.position_sizing.min_lots // Fixed risk sizing simplified for V1
    };

    // Progress tracking
    let progress_start = Instant::now();
    let mut last_progress_bar: u64 = 0;
    let mut last_progress_time = Instant::now();
    let checkpoint_interval: u64 = 50_000;

    // Track previous bar values for crossover detection (crosses_above/crosses_below)
    let mut prev_bar_values: HashMap<String, f64> = HashMap::new();
    // Once-only warning flags for unsupported filters
    let mut warned_day_of_week = false;
    let mut warned_volatility = false;

    // Main evaluation loop
    for i in resume_bar..end_bar {
        // 1. Check cancellation
        if cancel_flag.load(Ordering::Relaxed) {
            if let Some(out) = output_dir {
                write_checkpoint(out, i as u64, bar_count as u64, &position_manager, closed_pnl, trade_counter)?;
            }
            return Err(BacktesterError::SignalReceived);
        }

        let bar = Bar {
            index: i as u64,
            timestamp: timestamps.value(i),
            open: opens.value(i),
            high: highs.value(i),
            low: lows.value(i),
            close: closes.value(i),
            bid: bids.value(i),
            ask: asks.value(i),
            session: sessions.value(i).to_string(),
            quarantined: quarantined.value(i),
        };

        // Check fold embargo — skip new entries but still allow exit checks (like quarantine)
        if let Some(ref fc) = fold_config {
            if fc.is_embargo_bar(bar.index) {
                // Exit checks still fire during embargo to protect open positions
                if position_manager.has_position() {
                    if let Some(reason) = position_manager.check_exit_conditions(&bar) {
                        let pos = position_manager.current_position.as_ref().unwrap();
                        let exit_fill = simulate_exit_fill(&bar, pos, reason, cost_model)
                            .map_err(|e| BacktesterError::CostModel(e))?;
                        let pos = position_manager.close_position().unwrap();
                        let trade = build_trade_record(trade_counter, &pos, &exit_fill, bar.index, reason);
                        closed_pnl += trade.pnl;
                        trades.push(trade);
                        trade_counter += 1;
                    }
                }
                if position_manager.has_position() {
                    position_manager.update_trailing_stops(&bar);
                }
                let unrealized = compute_unrealized_pnl(&position_manager, &bar);
                record_equity_point(
                    &bar, closed_pnl, unrealized, &mut peak_equity,
                    &mut equity_points, &mut equity_timestamps,
                    &mut equity_unrealized, &mut equity_drawdown_pips,
                    &mut equity_open_trades, position_manager.has_position(),
                );
                continue;
            }
        }

        // 2. If position open → check exit conditions (runs even on quarantined bars, AC #9)
        if position_manager.has_position() {
            if let Some(reason) = position_manager.check_exit_conditions(&bar) {
                let pos = position_manager.current_position.as_ref().unwrap();
                let exit_fill = simulate_exit_fill(&bar, pos, reason, cost_model)
                    .map_err(|e| BacktesterError::CostModel(e))?;

                let pos = position_manager.close_position().unwrap();
                let trade = build_trade_record(trade_counter, &pos, &exit_fill, bar.index, reason);
                closed_pnl += trade.pnl;
                trades.push(trade);
                trade_counter += 1;
            }
        }

        // 3. Update trailing stops (if position open)
        if position_manager.has_position() {
            position_manager.update_trailing_stops(&bar);
        }

        // 4. If quarantined → skip signal evaluation (AC #9)
        if bar.quarantined {
            let unrealized = compute_unrealized_pnl(&position_manager, &bar);
            record_equity_point(
                &bar, closed_pnl, unrealized, &mut peak_equity,
                &mut equity_points, &mut equity_timestamps,
                &mut equity_unrealized, &mut equity_drawdown_pips,
                &mut equity_open_trades, position_manager.has_position(),
            );
            continue;
        }

        // 5-7. Evaluate entry signal and open position if appropriate
        if !position_manager.has_position() {
            let signal = evaluate_bar_signal(spec, &bar, batch, i, &mut signal_counter, &mut prev_bar_values, &mut warned_day_of_week, &mut warned_volatility);

            if let Some(dir) = signal.direction {
                let entry_fill = simulate_entry_fill(&bar, dir, cost_model)
                    .map_err(|e| BacktesterError::CostModel(e))?;

                // Compute exit levels based on entry price.
                // For atr_multiple: stop distance = ATR_value * multiplier (in price).
                // ATR is already in price units (e.g., 0.0015 for 15 pips).
                let pip = PIP_VALUE;

                // Resolve ATR value at entry bar for atr_multiple calculations
                let atr_value = atr_column.map(|col| col.value(i));

                let sl_distance_price = match sl_config.exit_type.as_str() {
                    "atr_multiple" => {
                        match atr_value {
                            Some(atr) if atr > 0.0 => atr * sl_config.value,
                            _ => sl_config.value * pip, // fallback: treat as pips
                        }
                    }
                    _ => sl_config.value * pip, // fixed_pips: value is in pips
                };

                let tp_distance_price = tp_config.map(|tp| {
                    match tp.exit_type.as_str() {
                        "atr_multiple" => {
                            match atr_value {
                                Some(atr) if atr > 0.0 => atr * tp.value,
                                _ => tp.value * pip,
                            }
                        }
                        "risk_reward" => {
                            // Risk:Reward ratio — TP distance = SL distance * RR ratio
                            sl_distance_price * tp.value
                        }
                        _ => tp.value * pip,
                    }
                });

                let (sl_level, tp_level) = match dir {
                    Direction::Long => {
                        let sl = entry_fill.price_adjusted - sl_distance_price;
                        let tp = tp_distance_price.map(|d| entry_fill.price_adjusted + d);
                        (Some(sl), tp)
                    }
                    Direction::Short => {
                        let sl = entry_fill.price_adjusted + sl_distance_price;
                        let tp = tp_distance_price.map(|d| entry_fill.price_adjusted - d);
                        (Some(sl), tp)
                    }
                };

                // Chandelier trailing: distance = ATR * multiplier
                let effective_trailing = match trailing_distance {
                    Some(d) => Some(d), // Fixed trailing stop in pips
                    None => {
                        // Check for chandelier trailing
                        match trailing_config {
                            Some(strategy_engine::TrailingConfig::Chandelier(params)) => {
                                match atr_value {
                                    Some(atr) if atr > 0.0 => {
                                        // Convert ATR-based distance to pips for TrailingStop
                                        Some(atr * params.atr_multiplier / pip)
                                    }
                                    _ => None,
                                }
                            }
                            _ => None,
                        }
                    }
                };

                let trailing = effective_trailing.map(|d| {
                    let level = match dir {
                        Direction::Long => entry_fill.price_adjusted - d * pip,
                        Direction::Short => entry_fill.price_adjusted + d * pip,
                    };
                    TrailingStop {
                        distance_pips: d,
                        current_level: level,
                    }
                });

                let position = Position {
                    direction: dir,
                    entry_price_raw: entry_fill.price_raw,
                    entry_price: entry_fill.price_adjusted,
                    entry_time: entry_fill.timestamp,
                    entry_spread: entry_fill.spread_pips,
                    entry_slippage: entry_fill.slippage_pips,
                    session: entry_fill.session,
                    entry_signal_id: signal.signal_id,
                    stop_loss: sl_level,
                    take_profit: tp_level,
                    trailing_stop: trailing,
                    entry_bar_index: bar.index,
                    lot_size,
                };

                position_manager.open_position(position);
            }
        }

        // 8. Record equity curve point
        let unrealized = compute_unrealized_pnl(&position_manager, &bar);
        record_equity_point(
            &bar, closed_pnl, unrealized, &mut peak_equity,
            &mut equity_points, &mut equity_timestamps,
            &mut equity_unrealized, &mut equity_drawdown_pips,
            &mut equity_open_trades, position_manager.has_position(),
        );

        // 9. Periodic checkpoint and progress (skip in batch mode — no output_dir)
        if let Some(out) = output_dir {
            let bars_since = (i as u64).saturating_sub(last_progress_bar);
            let secs_since = last_progress_time.elapsed().as_secs_f64();
            if should_report(bars_since, secs_since, 10_000, 1.0) {
                let elapsed = progress_start.elapsed().as_secs_f64();
                let bars_remaining = (end_bar - i) as f64;
                let bars_per_sec = (i - start_bar).max(1) as f64 / elapsed.max(0.001);
                let est_remaining = bars_remaining / bars_per_sec;

                let _ = write_progress(out, &ProgressReport {
                    bars_processed: (i - start_bar) as u64,
                    total_bars: bar_count as u64,
                    estimated_seconds_remaining: est_remaining,
                    memory_used_mb: 0, // TODO: query actual usage
                    updated_at: crate::progress::now_iso(),
                });

                last_progress_bar = i as u64;
                last_progress_time = Instant::now();
            }

            // Periodic checkpoint
            if i as u64 % checkpoint_interval == 0 && i > resume_bar {
                write_checkpoint(out, i as u64, bar_count as u64, &position_manager, closed_pnl, trade_counter)?;
            }
        }
    }

    // Close any remaining position at end of data
    if position_manager.has_position() {
        let last_idx = end_bar.saturating_sub(1);
        let last_bar = Bar {
            index: last_idx as u64,
            timestamp: timestamps.value(last_idx),
            open: opens.value(last_idx),
            high: highs.value(last_idx),
            low: lows.value(last_idx),
            close: closes.value(last_idx),
            bid: bids.value(last_idx),
            ask: asks.value(last_idx),
            session: sessions.value(last_idx).to_string(),
            quarantined: quarantined.value(last_idx),
        };

        let pos = position_manager.current_position.as_ref().unwrap();
        let exit_fill = simulate_exit_fill(&last_bar, pos, ExitReason::EndOfData, cost_model)
            .map_err(|e| BacktesterError::CostModel(e))?;
        let pos = position_manager.close_position().unwrap();
        let trade = build_trade_record(trade_counter, &pos, &exit_fill, last_bar.index, ExitReason::EndOfData);
        closed_pnl += trade.pnl;
        trades.push(trade);

        // Record final equity point after EOD close (AC #6)
        record_equity_point(
            &last_bar, closed_pnl, 0.0, &mut peak_equity,
            &mut equity_points, &mut equity_timestamps,
            &mut equity_unrealized, &mut equity_drawdown_pips,
            &mut equity_open_trades, false,
        );
    }

    // Sort trades by (entry_time, trade_id) for deterministic ordering (AC #8)
    trades.sort_by(|a, b| {
        a.entry_time.cmp(&b.entry_time)
            .then(a.trade_id.cmp(&b.trade_id))
    });

    // Compute metrics
    let metrics = compute_metrics(&trades, &equity_points);

    Ok(BacktestResult {
        trades,
        equity_curve: equity_points,
        equity_timestamps,
        equity_unrealized,
        equity_drawdown_pips,
        equity_open_trades,
        metrics,
        total_bars: bar_count as u64,
    })
}

/// Evaluate entry signal for a bar against the strategy spec.
///
/// Phase 1 (D14): Evaluates pre-computed signal columns from the Arrow data
/// against strategy rules. Does NOT compute indicators in Rust.
///
/// Condition evaluation: Each condition is evaluated independently. If multiple
/// conditions use the same indicator but different comparators (e.g., crosses_above
/// and crosses_below for long/short), they are treated as OR — the first condition
/// that passes determines the signal direction. Non-directional conditions
/// (>, <, >=, <=, ==) are treated as filters that ALL must pass alongside
/// the directional trigger.
fn evaluate_bar_signal(
    spec: &StrategySpec,
    bar: &Bar,
    batch: &RecordBatch,
    row_index: usize,
    signal_counter: &mut u64,
    prev_bar_values: &mut HashMap<String, f64>,
    warned_day_of_week: &mut bool,
    warned_volatility: &mut bool,
) -> Signal {
    // Separate conditions into directional triggers (crosses_above/below) and
    // threshold filters (>, <, >=, <=, ==).
    let mut directional_conditions: Vec<&Condition> = Vec::new();
    let mut filter_conditions: Vec<&Condition> = Vec::new();

    for condition in &spec.entry_rules.conditions {
        match condition.comparator.as_str() {
            "crosses_above" | "crosses_below" => directional_conditions.push(condition),
            _ => filter_conditions.push(condition),
        }
    }


    // Helper: resolve a condition's indicator value from Arrow data or bar fields.
    let resolve_value = |condition: &Condition| -> Option<f64> {
        let col_name = build_signal_column_name(&condition.indicator, &condition.parameters);
        if let Some(col_idx) = batch.schema().index_of(&col_name).ok() {
            let col = batch.column(col_idx);
            if let Some(arr) = col.as_any().downcast_ref::<Float64Array>() {
                Some(arr.value(row_index))
            } else {
                eprintln!(
                    "{{\"level\":\"warn\",\"msg\":\"Signal column '{}' has wrong type (expected Float64), skipping condition\"}}",
                    col_name
                );
                None
            }
        } else if matches!(condition.indicator.as_str(), "close" | "open" | "high" | "low") {
            Some(match condition.indicator.as_str() {
                "close" => bar.close,
                "open" => bar.open,
                "high" => bar.high,
                "low" => bar.low,
                _ => bar.close,
            })
        } else {
            let available: Vec<String> = batch
                .schema()
                .fields()
                .iter()
                .map(|f| f.name().clone())
                .collect();
            eprintln!(
                "{{\"level\":\"error\",\"msg\":\"MISSING pre-computed signal column '{}' — signal precompute stage may not have run. Available columns: {:?}\"}}",
                col_name, available
            );
            None
        }
    };

    // 1. Check all threshold filter conditions (must ALL pass)
    let mut all_filters_pass = true;
    for condition in &filter_conditions {
        let col_name = build_signal_column_name(&condition.indicator, &condition.parameters);
        let value = match resolve_value(condition) {
            Some(v) => v,
            None => { all_filters_pass = false; break; }
        };
        let threshold = condition.threshold;
        let passes = match condition.comparator.as_str() {
            ">" => value > threshold,
            "<" => value < threshold,
            ">=" => value >= threshold,
            "<=" => value <= threshold,
            "==" => (value - threshold).abs() < 1e-10,
            _ => false,
        };
        prev_bar_values.insert(col_name, value);
        if !passes {
            all_filters_pass = false;
            break;
        }
    }

    // 2. Evaluate directional conditions: resolve all current values FIRST,
    //    check crossovers against previous bar's values, then update prev_bar_values.
    //    This two-phase approach prevents conditions sharing the same column from
    //    corrupting each other's crossover detection.
    let mut fired_direction: Option<Direction> = None;

    // Phase 2a: Resolve current values for all directional conditions
    let mut resolved: Vec<(&Condition, String, f64)> = Vec::new();
    for condition in &directional_conditions {
        let col_name = build_signal_column_name(&condition.indicator, &condition.parameters);
        if let Some(value) = resolve_value(condition) {
            resolved.push((condition, col_name, value));
        }
    }

    // Phase 2b: Check crossovers against OLD prev_bar_values (before any updates)
    if all_filters_pass {
        for (condition, col_name, value) in &resolved {
            if fired_direction.is_some() {
                break; // First match wins
            }
            let threshold = condition.threshold;
            let prev_val = prev_bar_values.get(col_name).copied();
            let passes = match condition.comparator.as_str() {
                "crosses_above" => {
                    match prev_val {
                        Some(prev) => prev <= threshold && *value > threshold,
                        None => false,
                    }
                }
                "crosses_below" => {
                    match prev_val {
                        Some(prev) => prev >= threshold && *value < threshold,
                        None => false,
                    }
                }
                _ => false,
            };
            if passes {
                fired_direction = Some(match condition.comparator.as_str() {
                    "crosses_above" | ">" | ">=" => Direction::Long,
                    "crosses_below" | "<" | "<=" => Direction::Short,
                    _ => Direction::Long,
                });
            }
        }
    }

    // Phase 2c: NOW update prev_bar_values for next bar's crossover detection
    for (_condition, col_name, value) in resolved {
        prev_bar_values.insert(col_name, value);
    }

    // If no directional conditions exist, fall back to all-conditions-AND logic
    // for backward compatibility with simple threshold strategies.
    if directional_conditions.is_empty() && all_filters_pass && !filter_conditions.is_empty() {
        fired_direction = Some(Direction::Long); // Default to long for non-directional
    }

    // 3. Apply strategy filters (session, day_of_week, volatility)
    if fired_direction.is_some() {
        for filter in &spec.entry_rules.filters {
            match filter {
                strategy_engine::Filter::Session(params) => {
                    if !params.include.contains(&bar.session) {
                        fired_direction = None;
                        break;
                    }
                }
                strategy_engine::Filter::DayOfWeek(_params) => {
                    if !*warned_day_of_week {
                        eprintln!(
                            "{{\"level\":\"warn\",\"msg\":\"DayOfWeek filter not implemented in V1 — all days pass\"}}"
                        );
                        *warned_day_of_week = true;
                    }
                }
                strategy_engine::Filter::Volatility(_params) => {
                    if !*warned_volatility {
                        eprintln!(
                            "{{\"level\":\"warn\",\"msg\":\"Volatility filter not implemented in V1 — all bars pass\"}}"
                        );
                        *warned_volatility = true;
                    }
                }
            }
        }
    }

    if let Some(dir) = fired_direction {
        *signal_counter += 1;
        Signal {
            direction: Some(dir),
            signal_id: *signal_counter,
        }
    } else {
        Signal {
            direction: None,
            signal_id: 0,
        }
    }
}

/// Build a column name for a pre-computed signal.
fn build_signal_column_name(indicator: &str, params: &strategy_engine::IndicatorParams) -> String {
    // Convention: indicator_param1_param2 (e.g., sma_20, ema_50)
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

/// Compute unrealized P&L for an open position.
fn compute_unrealized_pnl(pm: &PositionManager, bar: &Bar) -> f64 {
    match &pm.current_position {
        Some(pos) => {
            let current_price = match pos.direction {
                Direction::Long => bar.bid,
                Direction::Short => bar.ask,
            };
            compute_pnl(pos.entry_price, current_price, pos.direction)
        }
        None => 0.0,
    }
}

/// Record an equity curve point.
#[allow(clippy::too_many_arguments)]
fn record_equity_point(
    bar: &Bar,
    closed_pnl: f64,
    unrealized: f64,
    peak_equity: &mut f64,
    equity_points: &mut Vec<EquityPoint>,
    timestamps: &mut Vec<i64>,
    unrealized_vec: &mut Vec<f64>,
    drawdown_pips_vec: &mut Vec<f64>,
    open_trades_vec: &mut Vec<i64>,
    has_position: bool,
) {
    let equity = closed_pnl + unrealized;
    if equity > *peak_equity {
        *peak_equity = equity;
    }

    // Drawdown reported in absolute pips. Equity is tracked in pips from a
    // zero base, so a percentage has no meaningful denominator.
    let dd_pips = (*peak_equity - equity).max(0.0);

    equity_points.push(EquityPoint {
        bar_index: bar.index,
        equity,
    });
    timestamps.push(bar.timestamp);
    unrealized_vec.push(unrealized);
    drawdown_pips_vec.push(dd_pips);
    open_trades_vec.push(if has_position { 1 } else { 0 });
}

/// Write a checkpoint file for crash recovery.
fn write_checkpoint(
    output_dir: &Path,
    last_bar: u64,
    total_bars: u64,
    pm: &PositionManager,
    cumulative_pnl: f64,
    trade_count: u64,
) -> Result<(), BacktesterError> {
    let partial_dir = output_dir.join(".partial");
    std::fs::create_dir_all(&partial_dir)?;

    let open_position = pm.current_position.as_ref().map(serialize_position);

    let progress_pct = if total_bars > 0 {
        last_bar as f64 / total_bars as f64 * 100.0
    } else {
        0.0
    };

    let checkpoint = Checkpoint {
        stage: "backtest-running".to_string(),
        progress_pct,
        last_completed_bar: last_bar,
        total_bars,
        open_position,
        cumulative_pnl,
        trade_count,
        checkpoint_at: crate::progress::now_iso(),
    };

    let json = serde_json::to_string_pretty(&checkpoint)
        .map_err(|e| BacktesterError::Validation(format!("Checkpoint serialization failed: {e}")))?;

    let path = partial_dir.join("checkpoint.json");
    let temp = partial_dir.join("checkpoint.json.tmp");

    {
        use std::io::Write;
        let mut f = std::fs::File::create(&temp)?;
        f.write_all(json.as_bytes())?;
        f.flush()?;
        f.sync_all()?;
    }
    std::fs::rename(&temp, &path)?;

    Ok(())
}

fn serialize_position(pos: &Position) -> SerializedPosition {
    SerializedPosition {
        direction: pos.direction.to_string(),
        entry_price_raw: pos.entry_price_raw,
        entry_price: pos.entry_price,
        entry_time: pos.entry_time,
        entry_spread: pos.entry_spread,
        entry_slippage: pos.entry_slippage,
        session: pos.session.clone(),
        entry_signal_id: pos.entry_signal_id,
        stop_loss: pos.stop_loss,
        take_profit: pos.take_profit,
        trailing_stop_distance: pos.trailing_stop.as_ref().map(|ts| ts.distance_pips),
        trailing_stop_level: pos.trailing_stop.as_ref().map(|ts| ts.current_level),
        entry_bar_index: pos.entry_bar_index,
        lot_size: pos.lot_size,
    }
}

fn deserialize_position(sp: &SerializedPosition) -> Position {
    let direction = if sp.direction == "long" {
        Direction::Long
    } else {
        Direction::Short
    };

    let trailing_stop = match (sp.trailing_stop_distance, sp.trailing_stop_level) {
        (Some(d), Some(l)) => Some(TrailingStop {
            distance_pips: d,
            current_level: l,
        }),
        _ => None,
    };

    Position {
        direction,
        entry_price_raw: sp.entry_price_raw,
        entry_price: sp.entry_price,
        entry_time: sp.entry_time,
        entry_spread: sp.entry_spread,
        entry_slippage: sp.entry_slippage,
        session: sp.session.clone(),
        entry_signal_id: sp.entry_signal_id,
        stop_loss: sp.stop_loss,
        take_profit: sp.take_profit,
        trailing_stop,
        entry_bar_index: sp.entry_bar_index,
        lot_size: sp.lot_size,
    }
}

/// Hash config_hash to a u64 seed for deterministic PRNG.
fn hash_to_seed(config_hash: &str) -> u64 {
    use sha2::{Digest, Sha256};
    let hash = Sha256::digest(config_hash.as_bytes());
    u64::from_le_bytes(hash[0..8].try_into().unwrap())
}

// ----------- Arrow column extraction helpers -----------

fn get_i64_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a Int64Array, BacktesterError> {
    let col = batch.column(
        batch.schema().index_of(name)
            .map_err(|_| BacktesterError::ArrowIpc(format!("Missing column: {name}")))?
    );
    col.as_any()
        .downcast_ref::<Int64Array>()
        .ok_or_else(|| BacktesterError::ArrowIpc(format!("Column '{name}' is not Int64")))
}

fn get_f64_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a Float64Array, BacktesterError> {
    let col = batch.column(
        batch.schema().index_of(name)
            .map_err(|_| BacktesterError::ArrowIpc(format!("Missing column: {name}")))?
    );
    col.as_any()
        .downcast_ref::<Float64Array>()
        .ok_or_else(|| BacktesterError::ArrowIpc(format!("Column '{name}' is not Float64")))
}

fn get_string_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a StringArray, BacktesterError> {
    let col = batch.column(
        batch.schema().index_of(name)
            .map_err(|_| BacktesterError::ArrowIpc(format!("Missing column: {name}")))?
    );
    col.as_any()
        .downcast_ref::<StringArray>()
        .ok_or_else(|| BacktesterError::ArrowIpc(format!("Column '{name}' is not Utf8")))
}

fn get_bool_column<'a>(batch: &'a RecordBatch, name: &str) -> Result<&'a BooleanArray, BacktesterError> {
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
    fn test_hash_to_seed_deterministic() {
        let s1 = hash_to_seed("abc123");
        let s2 = hash_to_seed("abc123");
        assert_eq!(s1, s2);
    }

    #[test]
    fn test_hash_to_seed_different() {
        let s1 = hash_to_seed("abc123");
        let s2 = hash_to_seed("def456");
        assert_ne!(s1, s2);
    }

    #[test]
    fn test_build_signal_column_name() {
        let mut params = std::collections::BTreeMap::new();
        params.insert("period".to_string(), toml::Value::Integer(20));
        let name = build_signal_column_name("sma", &params);
        assert_eq!(name, "sma_20");
    }

    #[test]
    fn test_serialize_deserialize_position_roundtrip() {
        let pos = Position {
            direction: Direction::Long,
            entry_price_raw: 1.10000,
            entry_price: 1.10085,
            entry_time: 1000000,
            entry_spread: 0.8,
            entry_slippage: 0.05,
            session: "london".to_string(),
            entry_signal_id: 42,
            stop_loss: Some(1.09500),
            take_profit: Some(1.10500),
            trailing_stop: Some(TrailingStop {
                distance_pips: 50.0,
                current_level: 1.09500,
            }),
            entry_bar_index: 10,
            lot_size: 0.1,
        };

        let serialized = serialize_position(&pos);
        let restored = deserialize_position(&serialized);

        assert_eq!(restored.direction, Direction::Long);
        assert!((restored.entry_price - 1.10085).abs() < 1e-10);
        assert_eq!(restored.entry_signal_id, 42);
        assert!(restored.trailing_stop.is_some());
        let ts = restored.trailing_stop.unwrap();
        assert!((ts.distance_pips - 50.0).abs() < 1e-10);
    }
}
