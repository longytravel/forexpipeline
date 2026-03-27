//! Arrow IPC output writer for backtest results (AC #5, #6, #8).
//!
//! Writes trade-log.arrow, equity-curve.arrow, metrics.arrow using
//! crash-safe semantics: write to .partial → fsync → atomic rename.
//! Schemas match contracts/arrow_schemas.toml definitions.

use std::io;
use std::path::Path;
use std::sync::Arc;

use arrow::array::*;
use arrow::datatypes::{DataType, Field, Schema};
use arrow::ipc::writer::FileWriter;
use arrow::record_batch::RecordBatch;

use common::error_types::BacktesterError;

use crate::engine::BacktestResult;

/// Write all backtest result files to the output directory.
pub fn write_results(
    output_dir: &Path,
    result: &BacktestResult,
    config_hash: &str,
    strategy_id: &str,
) -> Result<(), BacktesterError> {
    let partial_dir = output_dir.join(".partial");
    std::fs::create_dir_all(&partial_dir)?;

    // Write trade log
    let trade_batch = build_trade_log_batch(&result.trades, strategy_id)?;
    write_arrow_ipc(&partial_dir, output_dir, "trade-log.arrow", &trade_batch)?;

    // Write equity curve
    let equity_batch = build_equity_curve_batch(result)?;
    write_arrow_ipc(&partial_dir, output_dir, "equity-curve.arrow", &equity_batch)?;

    // Write metrics
    let metrics_batch = build_metrics_batch(result, strategy_id, config_hash)?;
    write_arrow_ipc(&partial_dir, output_dir, "metrics.arrow", &metrics_batch)?;

    // Write run_metadata.json (ephemeral, not deterministic)
    write_run_metadata(output_dir, config_hash)?;

    // Clean up .partial dir if empty
    let _ = std::fs::remove_dir(&partial_dir);

    Ok(())
}

/// Build Arrow RecordBatch for trade log with full cost attribution (AC #5).
/// Schema matches [backtest_trades] in contracts/arrow_schemas.toml.
fn build_trade_log_batch(
    trades: &[crate::trade_simulator::TradeRecord],
    strategy_id: &str,
) -> Result<RecordBatch, BacktesterError> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("trade_id", DataType::Int64, false),
        Field::new("strategy_id", DataType::Utf8, false),
        Field::new("direction", DataType::Utf8, false),
        Field::new("entry_time", DataType::Int64, false),
        Field::new("exit_time", DataType::Int64, false),
        Field::new("entry_price_raw", DataType::Float64, false),
        Field::new("entry_price", DataType::Float64, false),
        Field::new("exit_price_raw", DataType::Float64, false),
        Field::new("exit_price", DataType::Float64, false),
        Field::new("entry_spread", DataType::Float64, false),
        Field::new("entry_slippage", DataType::Float64, false),
        Field::new("exit_spread", DataType::Float64, false),
        Field::new("exit_slippage", DataType::Float64, false),
        Field::new("pnl_pips", DataType::Float64, false),
        Field::new("entry_session", DataType::Utf8, false),
        Field::new("exit_session", DataType::Utf8, false),
        Field::new("signal_id", DataType::Int64, false),
        Field::new("holding_duration_bars", DataType::Int64, false),
        Field::new("exit_reason", DataType::Utf8, false),
        Field::new("lot_size", DataType::Float64, false),
    ]));

    let n = trades.len();
    let mut trade_ids = Int64Builder::with_capacity(n);
    let mut strategy_ids = StringBuilder::with_capacity(n, n * strategy_id.len());
    let mut directions = StringBuilder::with_capacity(n, n * 5);
    let mut entry_times = Int64Builder::with_capacity(n);
    let mut exit_times = Int64Builder::with_capacity(n);
    let mut entry_prices_raw = Float64Builder::with_capacity(n);
    let mut entry_prices = Float64Builder::with_capacity(n);
    let mut exit_prices_raw = Float64Builder::with_capacity(n);
    let mut exit_prices = Float64Builder::with_capacity(n);
    let mut entry_spreads = Float64Builder::with_capacity(n);
    let mut entry_slippages = Float64Builder::with_capacity(n);
    let mut exit_spreads = Float64Builder::with_capacity(n);
    let mut exit_slippages = Float64Builder::with_capacity(n);
    let mut pnls = Float64Builder::with_capacity(n);
    let mut entry_sessions = StringBuilder::with_capacity(n, n * 10);
    let mut exit_sessions = StringBuilder::with_capacity(n, n * 10);
    let mut signal_ids = Int64Builder::with_capacity(n);
    let mut holding_durations = Int64Builder::with_capacity(n);
    let mut exit_reasons = StringBuilder::with_capacity(n, n * 15);
    let mut lot_sizes = Float64Builder::with_capacity(n);

    for t in trades {
        trade_ids.append_value(t.trade_id as i64);
        strategy_ids.append_value(strategy_id);
        directions.append_value(t.direction.to_string());
        entry_times.append_value(t.entry_time);
        exit_times.append_value(t.exit_time);
        entry_prices_raw.append_value(t.entry_price_raw);
        entry_prices.append_value(t.entry_price);
        exit_prices_raw.append_value(t.exit_price_raw);
        exit_prices.append_value(t.exit_price);
        entry_spreads.append_value(t.entry_spread);
        entry_slippages.append_value(t.entry_slippage);
        exit_spreads.append_value(t.exit_spread);
        exit_slippages.append_value(t.exit_slippage);
        pnls.append_value(t.pnl);
        entry_sessions.append_value(&t.entry_session);
        exit_sessions.append_value(&t.exit_session);
        signal_ids.append_value(t.signal_id as i64);
        holding_durations.append_value(t.holding_duration_bars as i64);
        exit_reasons.append_value(t.exit_reason.to_string());
        lot_sizes.append_value(t.lot_size);
    }

    RecordBatch::try_new(schema, vec![
        Arc::new(trade_ids.finish()),
        Arc::new(strategy_ids.finish()),
        Arc::new(directions.finish()),
        Arc::new(entry_times.finish()),
        Arc::new(exit_times.finish()),
        Arc::new(entry_prices_raw.finish()),
        Arc::new(entry_prices.finish()),
        Arc::new(exit_prices_raw.finish()),
        Arc::new(exit_prices.finish()),
        Arc::new(entry_spreads.finish()),
        Arc::new(entry_slippages.finish()),
        Arc::new(exit_spreads.finish()),
        Arc::new(exit_slippages.finish()),
        Arc::new(pnls.finish()),
        Arc::new(entry_sessions.finish()),
        Arc::new(exit_sessions.finish()),
        Arc::new(signal_ids.finish()),
        Arc::new(holding_durations.finish()),
        Arc::new(exit_reasons.finish()),
        Arc::new(lot_sizes.finish()),
    ]).map_err(|e| BacktesterError::ArrowIpc(format!("Failed to build trade log batch: {e}")))
}

/// Build Arrow RecordBatch for equity curve with unrealized P&L (AC #6).
/// Schema matches [equity_curve] in contracts/arrow_schemas.toml.
fn build_equity_curve_batch(result: &BacktestResult) -> Result<RecordBatch, BacktesterError> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("timestamp", DataType::Int64, false),
        Field::new("equity_pips", DataType::Float64, false),
        Field::new("unrealized_pnl", DataType::Float64, false),
        Field::new("drawdown_pct", DataType::Float64, false),
        Field::new("open_trades", DataType::Int64, false),
    ]));

    let n = result.equity_timestamps.len();
    let mut timestamps = Int64Builder::with_capacity(n);
    let mut equities = Float64Builder::with_capacity(n);
    let mut unrealized = Float64Builder::with_capacity(n);
    let mut drawdowns = Float64Builder::with_capacity(n);
    let mut open_trades = Int64Builder::with_capacity(n);

    for i in 0..n {
        timestamps.append_value(result.equity_timestamps[i]);
        equities.append_value(result.equity_curve[i].equity);
        unrealized.append_value(result.equity_unrealized[i]);
        drawdowns.append_value(result.equity_drawdown_pct[i]);
        open_trades.append_value(result.equity_open_trades[i]);
    }

    RecordBatch::try_new(schema, vec![
        Arc::new(timestamps.finish()),
        Arc::new(equities.finish()),
        Arc::new(unrealized.finish()),
        Arc::new(drawdowns.finish()),
        Arc::new(open_trades.finish()),
    ]).map_err(|e| BacktesterError::ArrowIpc(format!("Failed to build equity curve batch: {e}")))
}

/// Build Arrow RecordBatch for metrics — all AC #7 fields (single-row).
/// Schema matches [backtest_metrics] in contracts/arrow_schemas.toml.
fn build_metrics_batch(
    result: &BacktestResult,
    strategy_id: &str,
    config_hash: &str,
) -> Result<RecordBatch, BacktesterError> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("total_trades", DataType::Int64, false),
        Field::new("winning_trades", DataType::Int64, false),
        Field::new("losing_trades", DataType::Int64, false),
        Field::new("win_rate", DataType::Float64, false),
        Field::new("profit_factor", DataType::Float64, false),
        Field::new("sharpe_ratio", DataType::Float64, false),
        Field::new("r_squared", DataType::Float64, false),
        Field::new("max_drawdown_pips", DataType::Float64, false),
        Field::new("max_drawdown_pct", DataType::Float64, false),
        Field::new("max_drawdown_duration_bars", DataType::Int64, false),
        Field::new("avg_trade_duration_bars", DataType::Float64, false),
        Field::new("avg_win", DataType::Float64, false),
        Field::new("avg_loss", DataType::Float64, false),
        Field::new("largest_win", DataType::Float64, false),
        Field::new("largest_loss", DataType::Float64, false),
        Field::new("net_pnl_pips", DataType::Float64, false),
        Field::new("avg_trade_pips", DataType::Float64, false),
        Field::new("strategy_id", DataType::Utf8, false),
        Field::new("config_hash", DataType::Utf8, false),
    ]));

    let m = &result.metrics;
    // Clamp f64::MAX to f64::MAX (preserve actual value — downstream must handle infinity)
    let profit_factor = if m.profit_factor.is_infinite() || m.profit_factor == f64::MAX {
        f64::MAX
    } else {
        m.profit_factor
    };

    RecordBatch::try_new(schema, vec![
        Arc::new(Int64Array::from(vec![m.total_trades as i64])),
        Arc::new(Int64Array::from(vec![m.winning_trades as i64])),
        Arc::new(Int64Array::from(vec![m.losing_trades as i64])),
        Arc::new(Float64Array::from(vec![m.win_rate])),
        Arc::new(Float64Array::from(vec![profit_factor])),
        Arc::new(Float64Array::from(vec![m.sharpe_ratio])),
        Arc::new(Float64Array::from(vec![m.r_squared])),
        Arc::new(Float64Array::from(vec![m.max_drawdown_pips])),
        Arc::new(Float64Array::from(vec![m.max_drawdown_pct])),
        Arc::new(Int64Array::from(vec![m.max_drawdown_duration_bars as i64])),
        Arc::new(Float64Array::from(vec![m.avg_trade_duration_bars])),
        Arc::new(Float64Array::from(vec![m.avg_win])),
        Arc::new(Float64Array::from(vec![m.avg_loss])),
        Arc::new(Float64Array::from(vec![m.largest_win])),
        Arc::new(Float64Array::from(vec![m.largest_loss])),
        Arc::new(Float64Array::from(vec![m.net_pnl_pips])),
        Arc::new(Float64Array::from(vec![m.avg_trade_pips])),
        Arc::new(StringArray::from(vec![strategy_id])),
        Arc::new(StringArray::from(vec![config_hash])),
    ]).map_err(|e| BacktesterError::ArrowIpc(format!("Failed to build metrics batch: {e}")))
}

/// Write a RecordBatch to an Arrow IPC file with crash-safe semantics.
fn write_arrow_ipc(
    partial_dir: &Path,
    final_dir: &Path,
    filename: &str,
    batch: &RecordBatch,
) -> Result<(), BacktesterError> {
    let partial_path = partial_dir.join(filename);
    let final_path = final_dir.join(filename);

    {
        let file = std::fs::File::create(&partial_path)?;
        let mut writer = FileWriter::try_new(file, &batch.schema())
            .map_err(|e| BacktesterError::ArrowIpc(format!("Failed to create IPC writer: {e}")))?;
        writer.write(batch)
            .map_err(|e| BacktesterError::ArrowIpc(format!("Failed to write batch: {e}")))?;
        writer.finish()
            .map_err(|e| BacktesterError::ArrowIpc(format!("Failed to finish IPC: {e}")))?;

        // fsync the underlying file
        let inner = writer.into_inner()
            .map_err(|e| BacktesterError::ArrowIpc(format!("Failed to get file handle: {e}")))?;
        inner.sync_all()?;
    }

    // Atomic rename from partial to final
    std::fs::rename(&partial_path, &final_path).map_err(|e| {
        let _ = std::fs::remove_file(&partial_path);
        BacktesterError::Io(e)
    })?;

    Ok(())
}

/// Write run_metadata.json (ephemeral, not deterministic).
fn write_run_metadata(output_dir: &Path, config_hash: &str) -> Result<(), BacktesterError> {
    let path = output_dir.join("run_metadata.json");
    let partial = output_dir.join("run_metadata.json.partial");

    let metadata = serde_json::json!({
        "config_hash": config_hash,
        "binary_version": env!("CARGO_PKG_VERSION"),
        "crate": "backtester",
        "timestamp": crate::progress::now_iso(),
    });

    let bytes = serde_json::to_vec_pretty(&metadata)
        .map_err(|e| BacktesterError::Validation(format!("Metadata serialization failed: {e}")))?;

    crash_safe_write_bytes(&partial, &path, &bytes)?;
    Ok(())
}

/// Crash-safe binary write: write to partial → fsync → atomic rename.
fn crash_safe_write_bytes(partial: &Path, final_path: &Path, data: &[u8]) -> Result<(), BacktesterError> {
    {
        use std::io::Write;
        let mut f = std::fs::File::create(partial)?;
        f.write_all(data)?;
        f.flush()?;
        f.sync_all()?;
    }

    std::fs::rename(partial, final_path).map_err(|e| {
        let _ = std::fs::remove_file(partial);
        BacktesterError::Io(e)
    })?;

    Ok(())
}

/// Verify no .partial files remain in the output directory.
pub fn verify_no_partials(output_dir: &Path) -> io::Result<bool> {
    for entry in std::fs::read_dir(output_dir)? {
        let entry = entry?;
        let name = entry.file_name();
        if name.to_string_lossy().ends_with(".partial") {
            return Ok(false);
        }
    }
    Ok(true)
}
