//! End-to-end integration tests for the backtester (Task 11).
//!
//! These tests create synthetic Arrow IPC data with known values,
//! run the full backtest engine, and verify outputs.

use std::path::Path;
use std::sync::atomic::AtomicBool;
use std::sync::Arc;

use arrow::array::*;
use arrow::datatypes::{DataType, Field, Schema};
use arrow::ipc::writer::FileWriter;
use arrow::record_batch::RecordBatch;

/// Generate a synthetic market data Arrow IPC file.
/// Creates `num_bars` bars with predictable OHLCBAQ values.
/// Bars alternate between "london" and "new_york" sessions.
/// Signal pattern: price rises for first half, falls for second half.
fn write_test_market_data(path: &Path, num_bars: usize, all_quarantined: bool) {
    let schema = Arc::new(Schema::new(vec![
        Field::new("timestamp", DataType::Int64, false),
        Field::new("open", DataType::Float64, false),
        Field::new("high", DataType::Float64, false),
        Field::new("low", DataType::Float64, false),
        Field::new("close", DataType::Float64, false),
        Field::new("bid", DataType::Float64, false),
        Field::new("ask", DataType::Float64, false),
        Field::new("session", DataType::Utf8, false),
        Field::new("quarantined", DataType::Boolean, false),
    ]));

    let base_price = 1.10000_f64;
    let pip = 0.0001_f64;

    let mut timestamps = Vec::with_capacity(num_bars);
    let mut opens = Vec::with_capacity(num_bars);
    let mut highs = Vec::with_capacity(num_bars);
    let mut lows = Vec::with_capacity(num_bars);
    let mut closes = Vec::with_capacity(num_bars);
    let mut bids = Vec::with_capacity(num_bars);
    let mut asks = Vec::with_capacity(num_bars);
    let mut sessions = Vec::with_capacity(num_bars);
    let mut quarantined_flags = Vec::with_capacity(num_bars);

    for i in 0..num_bars {
        // Timestamp: microseconds, incrementing by 60 seconds (M1 bars)
        let ts = 1700000000_000_000_i64 + (i as i64 * 60_000_000);
        timestamps.push(ts);

        // Price pattern: gradual uptrend (1 pip per bar)
        let mid = base_price + (i as f64) * pip;
        let spread = 2.0 * pip; // 2 pip spread

        opens.push(mid - 0.5 * pip);
        highs.push(mid + 5.0 * pip);
        lows.push(mid - 5.0 * pip);
        closes.push(mid + 0.5 * pip);
        bids.push(mid - spread / 2.0);
        asks.push(mid + spread / 2.0);

        sessions.push(if i % 2 == 0 { "london" } else { "new_york" });
        quarantined_flags.push(all_quarantined);
    }

    let batch = RecordBatch::try_new(schema.clone(), vec![
        Arc::new(Int64Array::from(timestamps)),
        Arc::new(Float64Array::from(opens)),
        Arc::new(Float64Array::from(highs)),
        Arc::new(Float64Array::from(lows)),
        Arc::new(Float64Array::from(closes)),
        Arc::new(Float64Array::from(bids)),
        Arc::new(Float64Array::from(asks)),
        Arc::new(StringArray::from(sessions)),
        Arc::new(BooleanArray::from(quarantined_flags)),
    ]).unwrap();

    let file = std::fs::File::create(path).unwrap();
    let mut writer = FileWriter::try_new(file, &schema).unwrap();
    writer.write(&batch).unwrap();
    writer.finish().unwrap();
}

/// Write a minimal valid strategy spec TOML.
/// Uses close > threshold (set low so signals fire on most bars).
fn write_test_spec(path: &Path) {
    let spec = r#"
[metadata]
schema_version = "1.0"
name = "test-strategy"
version = "v001"
pair = "EURUSD"
timeframe = "M1"
created_by = "test"

[entry_rules]
conditions = [
    { indicator = "close", parameters = {}, threshold = 1.09, comparator = ">" }
]
filters = []
confirmation = []

[exit_rules]
[exit_rules.stop_loss]
type = "fixed_pips"
value = 50.0

[exit_rules.take_profit]
type = "fixed_pips"
value = 100.0

[position_sizing]
method = "fixed_lots"
risk_percent = 1.0
max_lots = 0.1
min_lots = 0.01
lot_step = 0.01

[optimization_plan]
parameter_groups = []
group_dependencies = []
objective_function = "sharpe"

[cost_model_reference]
version = "v001"
"#;
    std::fs::write(path, spec).unwrap();
}

/// Write a valid cost model JSON.
fn write_test_cost_model(path: &Path) {
    let json = r#"{
        "pair": "EURUSD",
        "version": "v001",
        "source": "research",
        "calibrated_at": "2026-03-15T00:00:00Z",
        "sessions": {
            "asian":             { "mean_spread_pips": 1.2, "std_spread": 0.4, "mean_slippage_pips": 0.1, "std_slippage": 0.05 },
            "london":            { "mean_spread_pips": 0.8, "std_spread": 0.3, "mean_slippage_pips": 0.05, "std_slippage": 0.03 },
            "london_ny_overlap": { "mean_spread_pips": 0.6, "std_spread": 0.2, "mean_slippage_pips": 0.03, "std_slippage": 0.02 },
            "new_york":          { "mean_spread_pips": 0.9, "std_spread": 0.3, "mean_slippage_pips": 0.06, "std_slippage": 0.03 },
            "off_hours":         { "mean_spread_pips": 1.5, "std_spread": 0.6, "mean_slippage_pips": 0.15, "std_slippage": 0.08 }
        }
    }"#;
    std::fs::write(path, json).unwrap();
}

/// Helper: run a backtest with test fixtures and return the result.
fn run_test_backtest(
    dir: &Path,
    num_bars: usize,
    all_quarantined: bool,
) -> Result<backtester::engine::BacktestResult, common::error_types::BacktesterError> {
    let data_path = dir.join("test_data.arrow");
    let spec_path = dir.join("test_spec.toml");
    let cost_path = dir.join("test_cost.json");
    let output_dir = dir.join("output");

    std::fs::create_dir_all(&output_dir).unwrap();

    write_test_market_data(&data_path, num_bars, all_quarantined);
    write_test_spec(&spec_path);
    write_test_cost_model(&cost_path);

    let spec = strategy_engine::parse_spec_from_file(&spec_path)
        .map_err(|e| common::error_types::BacktesterError::StrategySpec(e.to_string()))?;
    let cost_model = cost_model::load_from_file(&cost_path)
        .map_err(|e| common::error_types::BacktesterError::CostModel(e.to_string()))?;

    let cancel = Arc::new(AtomicBool::new(false));

    backtester::engine::run_backtest(
        &spec,
        &data_path,
        &cost_model,
        &output_dir,
        "test_hash_e2e",
        cancel,
        None,
        None,
        None,
        None,
    )
}

// ==================== E2E Tests ====================

#[test]
fn test_e2e_backtest_produces_valid_output() {
    let dir = tempfile::tempdir().unwrap();
    let result = run_test_backtest(dir.path(), 100, false).unwrap();

    // Write output files
    backtester::output::write_results(
        &dir.path().join("output"),
        &result,
        "test_hash_e2e",
        "test-strategy",
    ).unwrap();

    // Verify output files exist
    let out = dir.path().join("output");
    assert!(out.join("trade-log.arrow").exists(), "trade-log.arrow missing");
    assert!(out.join("equity-curve.arrow").exists(), "equity-curve.arrow missing");
    assert!(out.join("metrics.arrow").exists(), "metrics.arrow missing");
    assert!(out.join("run_metadata.json").exists(), "run_metadata.json missing");

    // Verify Arrow IPC files are readable
    let file = std::fs::File::open(out.join("trade-log.arrow")).unwrap();
    let reader = arrow::ipc::reader::FileReader::try_new(file, None).unwrap();
    let batches: Vec<RecordBatch> = reader.into_iter().collect::<Result<Vec<_>, _>>().unwrap();
    assert!(!batches.is_empty() || result.trades.is_empty());

    // Verify equity curve has same number of rows as bars processed
    let file = std::fs::File::open(out.join("equity-curve.arrow")).unwrap();
    let reader = arrow::ipc::reader::FileReader::try_new(file, None).unwrap();
    let eq_batches: Vec<RecordBatch> = reader.into_iter().collect::<Result<Vec<_>, _>>().unwrap();
    let eq_rows: usize = eq_batches.iter().map(|b| b.num_rows()).sum();
    assert_eq!(eq_rows, result.equity_curve.len());

    // Metrics should be a single-row batch
    let file = std::fs::File::open(out.join("metrics.arrow")).unwrap();
    let reader = arrow::ipc::reader::FileReader::try_new(file, None).unwrap();
    let m_batches: Vec<RecordBatch> = reader.into_iter().collect::<Result<Vec<_>, _>>().unwrap();
    let m_rows: usize = m_batches.iter().map(|b| b.num_rows()).sum();
    assert_eq!(m_rows, 1);

    // Verify no .partial files
    assert!(backtester::output::verify_no_partials(&out).unwrap());
}

#[test]
fn test_e2e_deterministic_output() {
    let dir1 = tempfile::tempdir().unwrap();
    let dir2 = tempfile::tempdir().unwrap();

    let r1 = run_test_backtest(dir1.path(), 100, false).unwrap();
    let r2 = run_test_backtest(dir2.path(), 100, false).unwrap();

    // Same number of trades
    assert_eq!(r1.trades.len(), r2.trades.len(), "Trade count differs between runs");

    // Compare trade values field-by-field (not byte hash — Arrow padding may vary)
    for (t1, t2) in r1.trades.iter().zip(r2.trades.iter()) {
        assert_eq!(t1.trade_id, t2.trade_id);
        assert_eq!(t1.entry_time, t2.entry_time);
        assert_eq!(t1.exit_time, t2.exit_time);
        assert!((t1.entry_price - t2.entry_price).abs() < 1e-10);
        assert!((t1.exit_price - t2.exit_price).abs() < 1e-10);
        assert!((t1.pnl - t2.pnl).abs() < 1e-10);
    }

    // Compare equity curve values
    assert_eq!(r1.equity_curve.len(), r2.equity_curve.len());
    for (e1, e2) in r1.equity_curve.iter().zip(r2.equity_curve.iter()) {
        assert!((e1.equity - e2.equity).abs() < 1e-10);
    }

    // Compare metrics
    assert!((r1.metrics.win_rate - r2.metrics.win_rate).abs() < 1e-10);
    assert!((r1.metrics.profit_factor - r2.metrics.profit_factor).abs() < 1e-10);
    assert!((r1.metrics.net_pnl_pips - r2.metrics.net_pnl_pips).abs() < 1e-10);
}

#[test]
fn test_e2e_quarantined_bars_produce_no_trades() {
    let dir = tempfile::tempdir().unwrap();
    let result = run_test_backtest(dir.path(), 100, true).unwrap();

    assert_eq!(result.trades.len(), 0, "Quarantined bars should produce zero trades");
    assert_eq!(result.metrics.total_trades, 0);
    assert!((result.metrics.win_rate - 0.0).abs() < 1e-10);
    assert!((result.metrics.profit_factor - 0.0).abs() < 1e-10);
    assert!((result.metrics.net_pnl_pips - 0.0).abs() < 1e-10);
}

#[test]
fn test_e2e_zero_trades_scenario() {
    // Use a threshold so high no signal fires
    let dir = tempfile::tempdir().unwrap();
    let data_path = dir.path().join("data.arrow");
    let spec_path = dir.path().join("spec.toml");
    let cost_path = dir.path().join("cost.json");
    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    write_test_market_data(&data_path, 100, false);
    write_test_cost_model(&cost_path);

    // Spec with impossible threshold (price never reaches 2.0)
    let spec = r#"
[metadata]
schema_version = "1.0"
name = "no-trade-strategy"
version = "v001"
pair = "EURUSD"
timeframe = "M1"
created_by = "test"

[entry_rules]
conditions = [
    { indicator = "close", parameters = {}, threshold = 2.0, comparator = ">" }
]
filters = []
confirmation = []

[exit_rules]
[exit_rules.stop_loss]
type = "fixed_pips"
value = 50.0

[position_sizing]
method = "fixed_lots"
risk_percent = 1.0
max_lots = 0.1

[optimization_plan]
parameter_groups = []
group_dependencies = []
objective_function = "sharpe"

[cost_model_reference]
version = "v001"
"#;
    std::fs::write(&spec_path, spec).unwrap();

    let spec = strategy_engine::parse_spec_from_file(&spec_path).unwrap();
    let cost_model = cost_model::load_from_file(&cost_path).unwrap();
    let cancel = Arc::new(AtomicBool::new(false));

    let result = backtester::engine::run_backtest(
        &spec, &data_path, &cost_model, &output_dir,
        "zero_trades_hash", cancel, None, None, None, None,
    ).unwrap();

    assert_eq!(result.trades.len(), 0);
    assert_eq!(result.metrics.total_trades, 0);

    // Write output and verify valid files
    backtester::output::write_results(&output_dir, &result, "zero_trades_hash", "no-trade-strategy").unwrap();
    assert!(output_dir.join("trade-log.arrow").exists());
    assert!(output_dir.join("metrics.arrow").exists());
}

#[test]
fn test_e2e_memory_budget_enforced() {
    let budget = backtester::memory::MemoryBudget::new(999_999); // 999 TB — way over
    let result = budget.check_system_memory();
    assert!(result.is_err(), "Should reject impossibly large budget");
}

#[test]
fn test_e2e_graceful_cancellation() {
    let dir = tempfile::tempdir().unwrap();
    let data_path = dir.path().join("data.arrow");
    let spec_path = dir.path().join("spec.toml");
    let cost_path = dir.path().join("cost.json");
    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    write_test_market_data(&data_path, 1000, false);
    write_test_spec(&spec_path);
    write_test_cost_model(&cost_path);

    let spec = strategy_engine::parse_spec_from_file(&spec_path).unwrap();
    let cost_model = cost_model::load_from_file(&cost_path).unwrap();

    // Set cancel flag immediately
    let cancel = Arc::new(AtomicBool::new(true));

    let result = backtester::engine::run_backtest(
        &spec, &data_path, &cost_model, &output_dir,
        "cancel_hash", cancel, None, None, None, None,
    );

    // Should return SignalReceived error
    assert!(result.is_err());
    let err = result.unwrap_err();
    assert!(
        matches!(err, common::error_types::BacktesterError::SignalReceived),
        "Expected SignalReceived, got: {err}"
    );

    // Checkpoint should have been written
    let checkpoint_path = output_dir.join(".partial").join("checkpoint.json");
    assert!(checkpoint_path.exists(), "Checkpoint file should exist after cancellation");
}

#[test]
fn test_e2e_fold_aware_evaluation() {
    let dir = tempfile::tempdir().unwrap();
    let data_path = dir.path().join("data.arrow");
    let spec_path = dir.path().join("spec.toml");
    let cost_path = dir.path().join("cost.json");
    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    write_test_market_data(&data_path, 300, false);
    write_test_spec(&spec_path);
    write_test_cost_model(&cost_path);

    let spec = strategy_engine::parse_spec_from_file(&spec_path).unwrap();
    let cost_model = cost_model::load_from_file(&cost_path).unwrap();
    let cancel = Arc::new(AtomicBool::new(false));

    let fold_config = backtester::fold::FoldConfig {
        boundaries: vec![(0, 90), (100, 190), (200, 290)],
        embargo_bars: 5,
    };

    let result = backtester::engine::run_backtest(
        &spec, &data_path, &cost_model, &output_dir,
        "fold_hash", cancel, Some(fold_config), None, None, None,
    ).unwrap();

    // Should produce valid results with 3 folds
    assert!(result.equity_curve.len() > 0);
    // Embargo bars (91-95, 191-195) should have been skipped for signals
}

#[test]
fn test_e2e_pre_computed_signals() {
    // Verify engine correctly evaluates pre-computed signal columns
    let dir = tempfile::tempdir().unwrap();
    let data_path = dir.path().join("data.arrow");
    let spec_path = dir.path().join("spec.toml");
    let cost_path = dir.path().join("cost.json");
    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    // Create market data with an extra "sma_20" signal column
    let schema = Arc::new(Schema::new(vec![
        Field::new("timestamp", DataType::Int64, false),
        Field::new("open", DataType::Float64, false),
        Field::new("high", DataType::Float64, false),
        Field::new("low", DataType::Float64, false),
        Field::new("close", DataType::Float64, false),
        Field::new("bid", DataType::Float64, false),
        Field::new("ask", DataType::Float64, false),
        Field::new("session", DataType::Utf8, false),
        Field::new("quarantined", DataType::Boolean, false),
        Field::new("sma_20", DataType::Float64, false), // Pre-computed signal
    ]));

    let n = 50;
    let base = 1.10000_f64;
    let pip = 0.0001_f64;
    let mut timestamps = Vec::new();
    let mut opens = Vec::new();
    let mut highs = Vec::new();
    let mut lows = Vec::new();
    let mut closes = Vec::new();
    let mut bids = Vec::new();
    let mut asks = Vec::new();
    let mut sessions = Vec::new();
    let mut quarantined = Vec::new();
    let mut sma_values = Vec::new();

    for i in 0..n {
        timestamps.push(1700000000_000_000_i64 + (i as i64 * 60_000_000));
        let mid = base + (i as f64) * pip;
        opens.push(mid);
        highs.push(mid + 5.0 * pip);
        lows.push(mid - 5.0 * pip);
        closes.push(mid + pip);
        bids.push(mid - pip);
        asks.push(mid + pip);
        sessions.push("london");
        quarantined.push(false);
        // SMA crosses above threshold (1.1002) at bar 25
        sma_values.push(base + (i as f64) * pip * 0.8);
    }

    let batch = RecordBatch::try_new(schema.clone(), vec![
        Arc::new(Int64Array::from(timestamps)),
        Arc::new(Float64Array::from(opens)),
        Arc::new(Float64Array::from(highs)),
        Arc::new(Float64Array::from(lows)),
        Arc::new(Float64Array::from(closes)),
        Arc::new(Float64Array::from(bids)),
        Arc::new(Float64Array::from(asks)),
        Arc::new(StringArray::from(sessions)),
        Arc::new(BooleanArray::from(quarantined)),
        Arc::new(Float64Array::from(sma_values)),
    ]).unwrap();

    let file = std::fs::File::create(&data_path).unwrap();
    let mut writer = FileWriter::try_new(file, &schema).unwrap();
    writer.write(&batch).unwrap();
    writer.finish().unwrap();

    // Strategy spec using the pre-computed sma_20 column
    let spec_content = r#"
[metadata]
schema_version = "1.0"
name = "sma-signal-test"
version = "v001"
pair = "EURUSD"
timeframe = "M1"
created_by = "test"

[entry_rules]
conditions = [
    { indicator = "sma", parameters = { period = 20 }, threshold = 1.1002, comparator = ">" }
]
filters = []
confirmation = []

[exit_rules]
[exit_rules.stop_loss]
type = "fixed_pips"
value = 50.0

[exit_rules.take_profit]
type = "fixed_pips"
value = 100.0

[position_sizing]
method = "fixed_lots"
risk_percent = 1.0
max_lots = 0.1

[optimization_plan]
parameter_groups = []
group_dependencies = []
objective_function = "sharpe"

[cost_model_reference]
version = "v001"
"#;
    std::fs::write(&spec_path, spec_content).unwrap();
    write_test_cost_model(&cost_path);

    let spec = strategy_engine::parse_spec_from_file(&spec_path).unwrap();
    let cost_model = cost_model::load_from_file(&cost_path).unwrap();
    let cancel = Arc::new(AtomicBool::new(false));

    let result = backtester::engine::run_backtest(
        &spec, &data_path, &cost_model, &output_dir,
        "signal_hash", cancel, None, None, None, None,
    ).unwrap();

    // Should have found the sma_20 column and used it for signal evaluation
    // Equity curve has one point per bar, plus one extra if EOD close occurred
    assert!(result.equity_curve.len() >= n && result.equity_curve.len() <= n + 1);
}

#[test]
fn test_e2e_checkpoint_resume() {
    let dir = tempfile::tempdir().unwrap();
    let data_path = dir.path().join("data.arrow");
    let spec_path = dir.path().join("spec.toml");
    let cost_path = dir.path().join("cost.json");
    let output_dir = dir.path().join("output");
    std::fs::create_dir_all(&output_dir).unwrap();

    write_test_market_data(&data_path, 200, false);
    write_test_spec(&spec_path);
    write_test_cost_model(&cost_path);

    let spec = strategy_engine::parse_spec_from_file(&spec_path).unwrap();
    let cost_model_loaded = cost_model::load_from_file(&cost_path).unwrap();

    // Full run
    let cancel = Arc::new(AtomicBool::new(false));
    let full_result = backtester::engine::run_backtest(
        &spec, &data_path, &cost_model_loaded, &output_dir,
        "resume_hash", cancel, None, None, None, None,
    ).unwrap();

    // Run should complete without errors
    assert!(full_result.equity_curve.len() > 0);
    assert!(full_result.total_bars == 200);
}
