//! Arrow schema definitions for the Forex Pipeline.
//!
//! These schemas are the Rust-side representation of `contracts/arrow_schemas.toml`.
//! The backtester binary writes output files conforming to these schemas;
//! Python `output_verifier.py` validates them on the reading side.

/// Column definition matching contracts/arrow_schemas.toml structure.
#[derive(Debug, Clone)]
pub struct ColumnDef {
    pub name: &'static str,
    pub arrow_type: ArrowType,
    pub nullable: bool,
}

/// Supported Arrow types matching the TOML contract types.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ArrowType {
    Int64,
    Float64,
    Utf8,
    Bool,
}

/// Schema definition for a table.
#[derive(Debug, Clone)]
pub struct SchemaDefinition {
    pub name: &'static str,
    pub columns: &'static [ColumnDef],
}

// ---------------------------------------------------------------------------
// Schema: backtest_trades → trade-log.arrow
// Matches [backtest_trades] in contracts/arrow_schemas.toml
// ---------------------------------------------------------------------------

pub static TRADE_LOG_COLUMNS: &[ColumnDef] = &[
    ColumnDef { name: "trade_id",              arrow_type: ArrowType::Int64,   nullable: false },
    ColumnDef { name: "strategy_id",           arrow_type: ArrowType::Utf8,    nullable: false },
    ColumnDef { name: "direction",             arrow_type: ArrowType::Utf8,    nullable: false },
    ColumnDef { name: "entry_time",            arrow_type: ArrowType::Int64,   nullable: false },
    ColumnDef { name: "exit_time",             arrow_type: ArrowType::Int64,   nullable: false },
    ColumnDef { name: "entry_price_raw",       arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "entry_price",           arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "exit_price_raw",        arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "exit_price",            arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "entry_spread",          arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "entry_slippage",        arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "exit_spread",           arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "exit_slippage",         arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "pnl_pips",              arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "entry_session",         arrow_type: ArrowType::Utf8,    nullable: false },
    ColumnDef { name: "exit_session",          arrow_type: ArrowType::Utf8,    nullable: false },
    ColumnDef { name: "signal_id",             arrow_type: ArrowType::Int64,   nullable: false },
    ColumnDef { name: "holding_duration_bars", arrow_type: ArrowType::Int64,   nullable: false },
    ColumnDef { name: "exit_reason",           arrow_type: ArrowType::Utf8,    nullable: false },
    ColumnDef { name: "lot_size",              arrow_type: ArrowType::Float64, nullable: false },
];

pub static TRADE_LOG_SCHEMA: SchemaDefinition = SchemaDefinition {
    name: "trade_log",
    columns: TRADE_LOG_COLUMNS,
};

// ---------------------------------------------------------------------------
// Schema: equity_curve → equity-curve.arrow
// Bar-level equity tracking for the backtest run.
// ---------------------------------------------------------------------------

pub static EQUITY_CURVE_COLUMNS: &[ColumnDef] = &[
    ColumnDef { name: "timestamp",      arrow_type: ArrowType::Int64,   nullable: false },
    ColumnDef { name: "equity_pips",    arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "unrealized_pnl", arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "drawdown_pips",  arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "open_trades",    arrow_type: ArrowType::Int64,   nullable: false },
];

pub static EQUITY_CURVE_SCHEMA: SchemaDefinition = SchemaDefinition {
    name: "equity_curve",
    columns: EQUITY_CURVE_COLUMNS,
};

// ---------------------------------------------------------------------------
// Schema: metrics → metrics.arrow
// Summary metrics per backtest run (single-row table).
// ---------------------------------------------------------------------------

pub static METRICS_COLUMNS: &[ColumnDef] = &[
    ColumnDef { name: "total_trades",              arrow_type: ArrowType::Int64,   nullable: false },
    ColumnDef { name: "winning_trades",            arrow_type: ArrowType::Int64,   nullable: false },
    ColumnDef { name: "losing_trades",             arrow_type: ArrowType::Int64,   nullable: false },
    ColumnDef { name: "win_rate",                  arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "profit_factor",             arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "sharpe_ratio",              arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "r_squared",                 arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "max_drawdown_pips",         arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "max_drawdown_duration_bars", arrow_type: ArrowType::Int64,  nullable: false },
    ColumnDef { name: "avg_trade_duration_bars",   arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "avg_win",                   arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "avg_loss",                  arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "largest_win",               arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "largest_loss",              arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "net_pnl_pips",              arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "avg_trade_pips",            arrow_type: ArrowType::Float64, nullable: false },
    ColumnDef { name: "strategy_id",               arrow_type: ArrowType::Utf8,    nullable: false },
    ColumnDef { name: "config_hash",               arrow_type: ArrowType::Utf8,    nullable: false },
];

pub static METRICS_SCHEMA: SchemaDefinition = SchemaDefinition {
    name: "metrics",
    columns: METRICS_COLUMNS,
};

/// Validate that a list of column names matches the expected schema.
/// Returns Ok(()) if the names match in order, or Err with a description.
pub fn validate_column_names(
    schema: &SchemaDefinition,
    actual_names: &[&str],
) -> Result<(), String> {
    let expected: Vec<&str> = schema.columns.iter().map(|c| c.name).collect();
    if actual_names == expected.as_slice() {
        Ok(())
    } else {
        Err(format!(
            "Schema mismatch for '{}': expected columns {:?}, got {:?}",
            schema.name, expected, actual_names,
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_trade_log_schema_has_expected_columns() {
        // Must match contracts/arrow_schemas.toml [backtest_trades]
        let names: Vec<&str> = TRADE_LOG_COLUMNS.iter().map(|c| c.name).collect();
        assert_eq!(names, vec![
            "trade_id", "strategy_id", "direction",
            "entry_time", "exit_time",
            "entry_price_raw", "entry_price", "exit_price_raw", "exit_price",
            "entry_spread", "entry_slippage", "exit_spread", "exit_slippage",
            "pnl_pips", "entry_session", "exit_session",
            "signal_id", "holding_duration_bars", "exit_reason", "lot_size",
        ]);
    }

    #[test]
    fn test_validate_column_names_ok() {
        let names: Vec<&str> = TRADE_LOG_COLUMNS.iter().map(|c| c.name).collect();
        assert!(validate_column_names(&TRADE_LOG_SCHEMA, &names).is_ok());
    }

    #[test]
    fn test_validate_column_names_mismatch() {
        let names = vec!["wrong_col"];
        let result = validate_column_names(&TRADE_LOG_SCHEMA, &names);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Schema mismatch"));
    }

    #[test]
    fn test_equity_curve_schema() {
        let names: Vec<&str> = EQUITY_CURVE_COLUMNS.iter().map(|c| c.name).collect();
        assert_eq!(names, vec!["timestamp", "equity_pips", "unrealized_pnl", "drawdown_pips", "open_trades"]);
    }

    #[test]
    fn test_metrics_schema() {
        let names: Vec<&str> = METRICS_COLUMNS.iter().map(|c| c.name).collect();
        assert!(names.contains(&"total_trades"));
        assert!(names.contains(&"sharpe_ratio"));
        assert!(names.contains(&"r_squared"));
        assert!(names.contains(&"max_drawdown_pips"));
        assert!(names.contains(&"max_drawdown_duration_bars"));
        assert!(names.contains(&"avg_trade_duration_bars"));
        assert!(names.contains(&"avg_win"));
        assert!(names.contains(&"avg_loss"));
        assert!(names.contains(&"largest_win"));
        assert!(names.contains(&"largest_loss"));
        assert!(names.contains(&"config_hash"));
    }
}
