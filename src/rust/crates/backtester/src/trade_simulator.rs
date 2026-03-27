//! Trade simulator / fill engine (AC #3, #5).
//!
//! V1 fill model: fills occur on signal bar at bar prices.
//! Long entry uses ask price, long exit uses bid price.
//! Short entry uses bid price, short exit uses ask price.
//! Session-aware costs applied via cost_model crate.

use cost_model::{CostModel, Direction as CostDirection, PIP_VALUE};

use crate::position::{Bar, Direction, ExitReason, Position};

/// A completed fill event.
#[derive(Debug, Clone)]
pub struct Fill {
    pub timestamp: i64,
    pub price_raw: f64,
    pub price_adjusted: f64,
    pub spread_pips: f64,
    pub slippage_pips: f64,
    pub direction: Direction,
    pub session: String,
}

/// A completed trade record with full cost attribution.
#[derive(Debug, Clone)]
pub struct TradeRecord {
    pub trade_id: u64,
    pub entry_time: i64,
    pub exit_time: i64,
    pub entry_price_raw: f64,
    pub entry_price: f64,
    pub exit_price_raw: f64,
    pub exit_price: f64,
    pub entry_spread: f64,
    pub entry_slippage: f64,
    pub exit_spread: f64,
    pub exit_slippage: f64,
    pub direction: Direction,
    pub entry_session: String,
    pub exit_session: String,
    pub signal_id: u64,
    pub pnl: f64,
    pub holding_duration_bars: u64,
    pub exit_reason: ExitReason,
    pub lot_size: f64,
}

/// Simulate an entry fill on the given bar.
/// Long entry: uses ask price. Short entry: uses bid price.
pub fn simulate_entry_fill(
    bar: &Bar,
    direction: Direction,
    cost_model: &CostModel,
) -> Result<Fill, String> {
    let raw_price = match direction {
        Direction::Long => bar.ask,
        Direction::Short => bar.bid,
    };

    // Use canonical apply_cost path for adjusted price (AC #3)
    let cost_dir = match direction {
        Direction::Long => CostDirection::Buy,
        Direction::Short => CostDirection::Sell,
    };
    let adjusted_price = cost_model
        .apply_cost(raw_price, &bar.session, cost_dir)
        .map_err(|e| e.to_string())?;

    // Get component breakdown for trade record attribution
    let profile = cost_model
        .get_cost(&bar.session)
        .map_err(|e| e.to_string())?;
    let spread_pips = profile.mean_spread_pips;
    let slippage_pips = profile.mean_slippage_pips;

    Ok(Fill {
        timestamp: bar.timestamp,
        price_raw: raw_price,
        price_adjusted: adjusted_price,
        spread_pips,
        slippage_pips,
        direction,
        session: bar.session.clone(),
    })
}

/// Simulate an exit fill on the given bar.
/// Long exit: uses bid price. Short exit: uses ask price.
pub fn simulate_exit_fill(
    bar: &Bar,
    position: &Position,
    _reason: ExitReason,
    cost_model: &CostModel,
) -> Result<Fill, String> {
    // Exit uses opposite side from entry
    let raw_price = match position.direction {
        Direction::Long => bar.bid,
        Direction::Short => bar.ask,
    };

    // Use canonical apply_cost path (AC #3); exit direction is opposite
    let cost_dir = match position.direction {
        Direction::Long => CostDirection::Sell,
        Direction::Short => CostDirection::Buy,
    };
    let adjusted_price = cost_model
        .apply_cost(raw_price, &bar.session, cost_dir)
        .map_err(|e| e.to_string())?;

    // Get component breakdown for trade record attribution
    let profile = cost_model
        .get_cost(&bar.session)
        .map_err(|e| e.to_string())?;
    let spread_pips = profile.mean_spread_pips;
    let slippage_pips = profile.mean_slippage_pips;

    Ok(Fill {
        timestamp: bar.timestamp,
        price_raw: raw_price,
        price_adjusted: adjusted_price,
        spread_pips,
        slippage_pips,
        direction: position.direction,
        session: bar.session.clone(),
    })
}

/// Compute P&L in pips for a completed trade.
pub fn compute_pnl(entry_price: f64, exit_price: f64, direction: Direction) -> f64 {
    let raw_diff = exit_price - entry_price;
    let pnl_price = match direction {
        Direction::Long => raw_diff,
        Direction::Short => -raw_diff,
    };
    pnl_price / PIP_VALUE
}

/// Build a TradeRecord from entry/exit fills and position data.
pub fn build_trade_record(
    trade_id: u64,
    position: &Position,
    exit_fill: &Fill,
    exit_bar_index: u64,
    exit_reason: ExitReason,
) -> TradeRecord {
    let pnl = compute_pnl(position.entry_price, exit_fill.price_adjusted, position.direction);
    let holding_duration = exit_bar_index.saturating_sub(position.entry_bar_index);

    TradeRecord {
        trade_id,
        entry_time: position.entry_time,
        exit_time: exit_fill.timestamp,
        entry_price_raw: position.entry_price_raw,
        entry_price: position.entry_price,
        exit_price_raw: exit_fill.price_raw,
        exit_price: exit_fill.price_adjusted,
        entry_spread: position.entry_spread,
        entry_slippage: position.entry_slippage,
        exit_spread: exit_fill.spread_pips,
        exit_slippage: exit_fill.slippage_pips,
        direction: position.direction,
        entry_session: position.session.clone(),
        exit_session: exit_fill.session.clone(),
        signal_id: position.entry_signal_id,
        pnl,
        holding_duration_bars: holding_duration,
        exit_reason,
        lot_size: position.lot_size,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_cost_model() -> CostModel {
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
        cost_model::load_from_str(json).unwrap()
    }

    fn make_bar(bid: f64, ask: f64) -> Bar {
        Bar {
            index: 0,
            timestamp: 1000000,
            open: (bid + ask) / 2.0,
            high: ask + 0.0010,
            low: bid - 0.0010,
            close: (bid + ask) / 2.0,
            bid,
            ask,
            session: "london".to_string(),
            quarantined: false,
        }
    }

    #[test]
    fn test_long_entry_uses_ask_price() {
        let cm = test_cost_model();
        let bar = make_bar(1.09990, 1.10010);
        let fill = simulate_entry_fill(&bar, Direction::Long, &cm).unwrap();
        assert!((fill.price_raw - 1.10010).abs() < 1e-10, "Long entry should use ask");
        assert!(fill.price_adjusted > fill.price_raw, "Cost-adjusted should be higher for long");
    }

    #[test]
    fn test_short_entry_uses_bid_price() {
        let cm = test_cost_model();
        let bar = make_bar(1.09990, 1.10010);
        let fill = simulate_entry_fill(&bar, Direction::Short, &cm).unwrap();
        assert!((fill.price_raw - 1.09990).abs() < 1e-10, "Short entry should use bid");
        assert!(fill.price_adjusted < fill.price_raw, "Cost-adjusted should be lower for short");
    }

    #[test]
    fn test_session_aware_cost_application() {
        let cm = test_cost_model();

        // London: spread 0.8, slippage 0.05 = 0.85 pips
        let london_bar = make_bar(1.10000, 1.10020);
        let london_fill = simulate_entry_fill(&london_bar, Direction::Long, &cm).unwrap();
        assert!((london_fill.spread_pips - 0.8).abs() < 1e-10);
        assert!((london_fill.slippage_pips - 0.05).abs() < 1e-10);

        // Asian: spread 1.2, slippage 0.1 = 1.3 pips
        let mut asian_bar = make_bar(1.10000, 1.10020);
        asian_bar.session = "asian".to_string();
        let asian_fill = simulate_entry_fill(&asian_bar, Direction::Long, &cm).unwrap();
        assert!((asian_fill.spread_pips - 1.2).abs() < 1e-10);
        assert!((asian_fill.slippage_pips - 0.1).abs() < 1e-10);
    }

    #[test]
    fn test_pnl_computation_long() {
        // Long: profit = (exit - entry) / pip_value
        // 1.10500 - 1.10000 = 0.00500 / 0.0001 = 50 pips
        let pnl = compute_pnl(1.10000, 1.10500, Direction::Long);
        assert!((pnl - 50.0).abs() < 1e-6, "Expected 50 pips profit, got {pnl}");

        // Long loss: 1.09500 - 1.10000 = -0.00500 / 0.0001 = -50 pips
        let pnl = compute_pnl(1.10000, 1.09500, Direction::Long);
        assert!((pnl - (-50.0)).abs() < 1e-6, "Expected -50 pips loss, got {pnl}");
    }

    #[test]
    fn test_pnl_computation_short() {
        // Short: profit = -(exit - entry) / pip_value
        // -(1.10000 - 1.10500) / 0.0001 = 50 pips
        let pnl = compute_pnl(1.10500, 1.10000, Direction::Short);
        assert!((pnl - 50.0).abs() < 1e-6, "Expected 50 pips profit, got {pnl}");

        // Short loss: -(1.10000 - 1.09500) / 0.0001 = -50 pips
        let pnl = compute_pnl(1.09500, 1.10000, Direction::Short);
        assert!((pnl - (-50.0)).abs() < 1e-6, "Expected -50 pips loss, got {pnl}");
    }
}
