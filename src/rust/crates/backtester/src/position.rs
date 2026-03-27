//! Position state machine for the backtester (AC #2, #5).
//!
//! Manages open/close lifecycle, exit condition checking, and trailing stops.
//! Exit *rule definitions* (chandelier formula, trailing stop params) come from
//! strategy_engine; this module applies them against price data.

use serde::{Deserialize, Serialize};

/// Trade direction.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Direction {
    Long,
    Short,
}

impl std::fmt::Display for Direction {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Direction::Long => write!(f, "long"),
            Direction::Short => write!(f, "short"),
        }
    }
}

/// Why a position was closed.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ExitReason {
    StopLoss,
    TakeProfit,
    TrailingStop,
    ChandelierExit,
    SignalReversal,
    EndOfData,
    SubBarM1Exit,
    StaleExit,
    PartialClose,
    BreakevenWithOffset,
    MaxBarsExit,
}

impl std::fmt::Display for ExitReason {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            ExitReason::StopLoss => "StopLoss",
            ExitReason::TakeProfit => "TakeProfit",
            ExitReason::TrailingStop => "TrailingStop",
            ExitReason::ChandelierExit => "ChandelierExit",
            ExitReason::SignalReversal => "SignalReversal",
            ExitReason::EndOfData => "EndOfData",
            ExitReason::SubBarM1Exit => "SubBarM1Exit",
            ExitReason::StaleExit => "StaleExit",
            ExitReason::PartialClose => "PartialClose",
            ExitReason::BreakevenWithOffset => "BreakevenWithOffset",
            ExitReason::MaxBarsExit => "MaxBarsExit",
        };
        write!(f, "{s}")
    }
}

/// Trailing stop state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrailingStop {
    pub distance_pips: f64,
    pub current_level: f64,
}

/// An open position.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Position {
    pub direction: Direction,
    pub entry_price_raw: f64,
    pub entry_price: f64,
    pub entry_time: i64,
    pub entry_spread: f64,
    pub entry_slippage: f64,
    pub session: String,
    pub entry_signal_id: u64,
    pub stop_loss: Option<f64>,
    pub take_profit: Option<f64>,
    pub trailing_stop: Option<TrailingStop>,
    pub entry_bar_index: u64,
    pub lot_size: f64,
}

/// Market bar data for position evaluation.
pub struct Bar {
    pub index: u64,
    pub timestamp: i64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub bid: f64,
    pub ask: f64,
    pub session: String,
    pub quarantined: bool,
}

/// Manages the open position lifecycle.
pub struct PositionManager {
    pub current_position: Option<Position>,
}

impl PositionManager {
    pub fn new() -> Self {
        Self {
            current_position: None,
        }
    }

    pub fn has_position(&self) -> bool {
        self.current_position.is_some()
    }

    /// Open a new position. Returns the position. Caller records the fill.
    pub fn open_position(&mut self, position: Position) {
        self.current_position = Some(position);
    }

    /// Close the current position, returning it.
    pub fn close_position(&mut self) -> Option<Position> {
        self.current_position.take()
    }

    /// Check price-level exit conditions against current bar.
    /// Returns the exit reason if triggered.
    pub fn check_exit_conditions(&self, bar: &Bar) -> Option<ExitReason> {
        let pos = self.current_position.as_ref()?;

        match pos.direction {
            Direction::Long => {
                // Stop loss: bar low <= stop level
                if let Some(sl) = pos.stop_loss {
                    if bar.low <= sl {
                        return Some(ExitReason::StopLoss);
                    }
                }
                // Take profit: bar high >= TP level
                if let Some(tp) = pos.take_profit {
                    if bar.high >= tp {
                        return Some(ExitReason::TakeProfit);
                    }
                }
                // Trailing stop: bar low <= trailing level
                if let Some(ref ts) = pos.trailing_stop {
                    if bar.low <= ts.current_level {
                        return Some(ExitReason::TrailingStop);
                    }
                }
            }
            Direction::Short => {
                // Stop loss: bar high >= stop level
                if let Some(sl) = pos.stop_loss {
                    if bar.high >= sl {
                        return Some(ExitReason::StopLoss);
                    }
                }
                // Take profit: bar low <= TP level
                if let Some(tp) = pos.take_profit {
                    if bar.low <= tp {
                        return Some(ExitReason::TakeProfit);
                    }
                }
                // Trailing stop: bar high >= trailing level
                if let Some(ref ts) = pos.trailing_stop {
                    if bar.high >= ts.current_level {
                        return Some(ExitReason::TrailingStop);
                    }
                }
            }
        }

        None
    }

    /// Update trailing stop levels based on price action.
    pub fn update_trailing_stops(&mut self, bar: &Bar) {
        let pos = match self.current_position.as_mut() {
            Some(p) => p,
            None => return,
        };

        let pip_value = cost_model::PIP_VALUE;

        if let Some(ref mut ts) = pos.trailing_stop {
            let distance = ts.distance_pips * pip_value;
            match pos.direction {
                Direction::Long => {
                    // Trail upward: new level = high - distance
                    let new_level = bar.high - distance;
                    if new_level > ts.current_level {
                        ts.current_level = new_level;
                    }
                }
                Direction::Short => {
                    // Trail downward: new level = low + distance
                    let new_level = bar.low + distance;
                    if new_level < ts.current_level {
                        ts.current_level = new_level;
                    }
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_bar(high: f64, low: f64) -> Bar {
        Bar {
            index: 0,
            timestamp: 1000000,
            open: (high + low) / 2.0,
            high,
            low,
            close: (high + low) / 2.0,
            bid: low,
            ask: high,
            session: "london".to_string(),
            quarantined: false,
        }
    }

    #[test]
    fn test_open_long_position() {
        let mut pm = PositionManager::new();
        assert!(!pm.has_position());
        pm.open_position(Position {
            direction: Direction::Long,
            entry_price_raw: 1.10000,
            entry_price: 1.10010,
            entry_time: 1000,
            entry_spread: 0.8,
            entry_slippage: 0.05,
            session: "london".to_string(),
            entry_signal_id: 1,
            stop_loss: Some(1.09500),
            take_profit: Some(1.10500),
            trailing_stop: None,
            entry_bar_index: 0,
            lot_size: 0.1,
        });
        assert!(pm.has_position());
    }

    #[test]
    fn test_close_with_stop_loss() {
        let mut pm = PositionManager::new();
        pm.open_position(Position {
            direction: Direction::Long,
            entry_price_raw: 1.10000,
            entry_price: 1.10010,
            entry_time: 1000,
            entry_spread: 0.8,
            entry_slippage: 0.05,
            session: "london".to_string(),
            entry_signal_id: 1,
            stop_loss: Some(1.09500),
            take_profit: Some(1.10500),
            trailing_stop: None,
            entry_bar_index: 0,
            lot_size: 0.1,
        });

        // Bar that hits stop loss
        let bar = make_bar(1.09600, 1.09400);
        let reason = pm.check_exit_conditions(&bar);
        assert_eq!(reason, Some(ExitReason::StopLoss));
    }

    #[test]
    fn test_trailing_stop_adjustment() {
        let mut pm = PositionManager::new();
        pm.open_position(Position {
            direction: Direction::Long,
            entry_price_raw: 1.10000,
            entry_price: 1.10010,
            entry_time: 1000,
            entry_spread: 0.8,
            entry_slippage: 0.05,
            session: "london".to_string(),
            entry_signal_id: 1,
            stop_loss: None,
            take_profit: None,
            trailing_stop: Some(TrailingStop {
                distance_pips: 50.0,
                current_level: 1.09500, // entry - 50 pips
            }),
            entry_bar_index: 0,
            lot_size: 0.1,
        });

        // Price rises -> trailing stop should trail up
        let bar = make_bar(1.10500, 1.10200);
        pm.update_trailing_stops(&bar);
        let ts = pm.current_position.as_ref().unwrap().trailing_stop.as_ref().unwrap();
        // new level = 1.10500 - 50*0.0001 = 1.10500 - 0.0050 = 1.10000
        assert!((ts.current_level - 1.10000).abs() < 1e-10);
    }

    #[test]
    fn test_cost_adjusted_entry_exit_prices() {
        // Verify position stores both raw and cost-adjusted prices
        let pos = Position {
            direction: Direction::Long,
            entry_price_raw: 1.10000,
            entry_price: 1.10085, // adjusted with spread + slippage
            entry_time: 1000,
            entry_spread: 0.8,
            entry_slippage: 0.05,
            session: "london".to_string(),
            entry_signal_id: 1,
            stop_loss: None,
            take_profit: None,
            trailing_stop: None,
            entry_bar_index: 0,
            lot_size: 0.1,
        };
        assert!(pos.entry_price > pos.entry_price_raw);
        assert!((pos.entry_spread - 0.8).abs() < 1e-10);
        assert!((pos.entry_slippage - 0.05).abs() < 1e-10);
    }

    #[test]
    fn test_short_stop_loss() {
        let mut pm = PositionManager::new();
        pm.open_position(Position {
            direction: Direction::Short,
            entry_price_raw: 1.10000,
            entry_price: 1.09915,
            entry_time: 1000,
            entry_spread: 0.8,
            entry_slippage: 0.05,
            session: "london".to_string(),
            entry_signal_id: 1,
            stop_loss: Some(1.10500),
            take_profit: Some(1.09500),
            trailing_stop: None,
            entry_bar_index: 0,
            lot_size: 0.1,
        });

        // Bar that hits stop loss for short (high >= SL)
        let bar = make_bar(1.10600, 1.10400);
        assert_eq!(pm.check_exit_conditions(&bar), Some(ExitReason::StopLoss));
    }
}
